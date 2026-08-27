"""Tests for the planned-boundary read the alert surfaces share.

The load-bearing property is asymmetric. Reading a lapse as planned would let
an abandoned feed be described gently, so every one of those paths is tested
against a hostile artifact. Reading a planned boundary as a lapse is only the
old behaviour, so those tests assert the softer wording is reached exactly when
the published record already supports it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from scorecard_pipeline.gtfs import FeedDates
from scorecard_pipeline.metrics import STALE_FEED_DAYS, freshness
from scorecard_pipeline.service_periods import (
    PLANNED_FINDING_CODES,
    read_service_period,
)

TODAY = dt.date(2026, 6, 11)


def feed_dates(end: dt.date, *, seasonal_boundary: bool = False) -> FeedDates:
    return FeedDates(
        has_feed_info=True,
        feed_publisher_name="Test",
        feed_version="v1",
        feed_start_date=dt.date(2026, 1, 1),
        feed_end_date=end,
        last_service_date=end,
        seasonal_boundary=seasonal_boundary,
    )


def artifact(
    *,
    details: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A minimal published artifact carrying only the freshness card."""
    freshness_block: dict[str, Any] = {"details": details if details is not None else {}}
    if findings is not None:
        freshness_block["findings"] = findings
    return {"categories": {"freshness": freshness_block}}


def finding(code: str) -> dict[str, Any]:
    return {"code": code, "severity": "WARNING", "count": 1}


class TestClosedCalendar:
    """After expiry the scoring path has already decided. Defer to it."""

    @pytest.mark.parametrize("code", sorted(PLANNED_FINDING_CODES))
    def test_published_planned_finding_reads_as_planned(self, code: str) -> None:
        read = read_service_period(artifact(findings=[finding(code)]), -30)
        assert read.planned

    def test_no_published_finding_reads_as_a_lapse(self) -> None:
        assert not read_service_period(artifact(findings=[]), -30).planned

    def test_an_unrelated_freshness_finding_reads_as_a_lapse(self) -> None:
        expired = artifact(findings=[finding("scorecard_feed_expired")])
        assert not read_service_period(expired, -30).planned

    def test_seasonal_details_alone_do_not_soften_a_closed_calendar(self) -> None:
        """The pre-expiry facts are not a second route around the finding gate.

        A feed can encode distinct periods and still be genuinely abandoned at
        one of them. `metrics.freshness` decides which, and after expiry its
        published finding is the only evidence this module accepts.
        """
        looks_seasonal = artifact(
            details={"seasonal_boundary": True, "service_type": "seasonal"},
            findings=[finding("scorecard_feed_expired")],
        )
        assert not read_service_period(looks_seasonal, -30).planned

    def test_day_zero_uses_the_closed_calendar_rule(self) -> None:
        """Zero days left means the window closes today, not that it is open."""
        assert not read_service_period(
            artifact(details={"seasonal_boundary": True}, findings=[]), 0
        ).planned


class TestStaleFloor:
    """A feed dead a year or more is never described as a planned transition."""

    @pytest.mark.parametrize("code", sorted(PLANNED_FINDING_CODES))
    def test_planned_finding_cannot_soften_a_year_old_lapse(self, code: str) -> None:
        record = artifact(
            details={"seasonal_boundary": True, "service_type": "seasonal"},
            findings=[finding(code)],
        )
        assert not read_service_period(record, -STALE_FEED_DAYS).planned
        assert not read_service_period(record, -STALE_FEED_DAYS - 400).planned

    def test_the_floor_is_the_same_day_scoring_uses(self) -> None:
        """One day inside the floor still reads as planned, so the two agree."""
        record = artifact(
            details={"seasonal_boundary": True},
            findings=[finding("scorecard_planned_service_boundary")],
        )
        assert read_service_period(record, -STALE_FEED_DAYS + 1).planned


class TestOpenCalendar:
    """Before expiry there is no finding yet, so the published facts stand in."""

    def test_detected_boundary_reads_as_planned(self) -> None:
        read = read_service_period(artifact(details={"seasonal_boundary": True}), 10)
        assert read.planned
        assert not read.declared

    @pytest.mark.parametrize(
        ("service_type", "noun"),
        [("seasonal", "seasonal"), ("demand_response", "on-demand")],
    )
    def test_declared_service_reads_as_planned_and_names_itself(
        self, service_type: str, noun: str
    ) -> None:
        read = read_service_period(artifact(details={"service_type": service_type}), 10)
        assert read.planned
        assert read.declared
        assert read.service_noun == noun

    def test_an_ordinary_fixed_route_feed_reads_as_a_lapse(self) -> None:
        read = read_service_period(
            artifact(details={"service_type": "fixed", "seasonal_boundary": False}), 10
        )
        assert not read.planned

    def test_missing_expiry_is_never_planned(self) -> None:
        """No date means no known pattern; the wording stays the strict one."""
        assert not read_service_period(artifact(details={"seasonal_boundary": True}), None).planned


class TestMalformedRecords:
    """Anything unreadable falls back to the existing lapse wording."""

    @pytest.mark.parametrize(
        "record",
        [
            None,
            {},
            {"categories": None},
            {"categories": {}},
            {"categories": {"freshness": None}},
            {"categories": {"freshness": {}}},
            {"categories": {"freshness": {"details": "not a mapping"}}},
        ],
    )
    def test_unreadable_artifact_is_not_planned(self, record: Any) -> None:
        assert not read_service_period(record, -30).planned
        assert not read_service_period(record, 10).planned

    def test_malformed_findings_list_is_not_planned(self) -> None:
        record = artifact(details={}, findings=None)
        record["categories"]["freshness"]["findings"] = "scorecard_planned_service_boundary"
        assert not read_service_period(record, -30).planned

    def test_non_mapping_finding_rows_are_skipped(self) -> None:
        record = artifact(details={})
        record["categories"]["freshness"]["findings"] = [
            "scorecard_planned_service_boundary",
            None,
        ]
        assert not read_service_period(record, -30).planned


class TestAgreesWithScoring:
    """The classifier and metrics.freshness must not disagree on real output.

    These build a real CategoryResult rather than a hand-written artifact, so a
    future rename of either finding code fails here instead of silently
    reverting every alert to the lapse wording.
    """

    @staticmethod
    def _scored(
        days_lapsed: int,
        *,
        seasonal_boundary: bool = False,
        service_type: str = "fixed",
    ) -> tuple[dict[str, Any], int]:
        """Score a lapsed feed for real, then shape it like a published artifact."""
        result = freshness(
            feed_dates(TODAY - dt.timedelta(days=days_lapsed), seasonal_boundary=seasonal_boundary),
            TODAY,
            service_type,
        )
        record = {
            "categories": {
                "freshness": {
                    "details": result.details,
                    "findings": [{"code": f.code} for f in result.findings],
                }
            }
        }
        return record, int(result.details["days_until_expiry"])

    def test_detected_boundary_scored_then_read_as_planned(self) -> None:
        record, days = self._scored(30, seasonal_boundary=True)
        read = read_service_period(record, days)
        assert read.planned
        assert not read.declared

    def test_declared_seasonal_scored_then_read_as_planned(self) -> None:
        record, days = self._scored(30, service_type="seasonal")
        read = read_service_period(record, days)
        assert read.planned
        assert read.declared

    def test_plain_expired_feed_scored_then_read_as_a_lapse(self) -> None:
        record, days = self._scored(30)
        assert not read_service_period(record, days).planned

    def test_long_dead_feed_scored_then_read_as_a_lapse(self) -> None:
        record, days = self._scored(STALE_FEED_DAYS + 10, seasonal_boundary=True)
        assert not read_service_period(record, days).planned
