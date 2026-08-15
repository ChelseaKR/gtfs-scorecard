"""Tests for the conformance trust mark (pure)."""

from __future__ import annotations

from typing import Any

import pytest

from scorecard_pipeline.badge import render_mark
from scorecard_pipeline.conformance import (
    AWARDED,
    CONFORMANCE_VERSION,
    NOT_YET,
    assess,
)


def _artifact(
    *,
    errors: int = 0,
    days: int = 120,
    stops_pct: float = 95.0,
    trips_pct: float = 95.0,
    measured: bool = True,
) -> dict[str, Any]:
    correctness = {
        "status": "measured" if measured else "skipped",
        "findings": [{"severity": "ERROR"} for _ in range(errors)],
    }
    return {
        "categories": {
            "correctness": correctness,
            "freshness": {"details": {"days_until_expiry": days}},
            "completeness": {
                "details": {
                    "accessibility": {
                        "stops_stated_pct": stops_pct,
                        "trips_stated_pct": trips_pct,
                    }
                }
            },
        }
    }


def test_clean_feed_earns_the_mark() -> None:
    mark = assess(_artifact())
    assert mark.awarded is True
    assert mark.to_dict()["version"] == CONFORMANCE_VERSION
    assert mark.to_dict()["status"] == AWARDED
    assert all(c.met for c in mark.criteria)


@pytest.mark.parametrize(
    ("expected_met", "errors", "days", "stops_pct", "trips_pct", "expected_lede"),
    [
        (
            0,
            1,
            -3,
            0.0,
            0.0,
            "This feed does not meet the conformance requirements yet. "
            "Here is what the mark needs:",
        ),
        (
            1,
            0,
            -3,
            0.0,
            0.0,
            "Two requirements remain for this feed to earn the conformance mark.",
        ),
        (
            2,
            0,
            120,
            0.0,
            0.0,
            "One requirement remains for this feed to earn the conformance mark.",
        ),
        (
            3,
            0,
            120,
            95.0,
            95.0,
            "This feed earns the conformance mark:",
        ),
    ],
    ids=["0-of-3", "1-of-3", "2-of-3", "3-of-3"],
)
def test_summary_matches_number_of_conformance_criteria_met(
    expected_met: int,
    errors: int,
    days: int,
    stops_pct: float,
    trips_pct: float,
    expected_lede: str,
) -> None:
    mark = assess(
        _artifact(
            errors=errors,
            days=days,
            stops_pct=stops_pct,
            trips_pct=trips_pct,
        )
    )

    assert sum(criterion.met for criterion in mark.criteria) == expected_met
    assert mark.summary.startswith(expected_lede)
    assert "close to" not in mark.summary.lower()
    assert all(criterion.detail in mark.summary for criterion in mark.criteria if not criterion.met)


def test_legacy_distant_horizon_keeps_mark_status_without_huge_countdown() -> None:
    artifact = _artifact(days=26_834)
    artifact["snapshot_date"] = "2026-07-13"
    mark = assess(artifact)
    current = next(c for c in mark.criteria if c.key == "current")
    assert current.met is True
    assert "unusually distant" in current.detail
    assert "26834" not in current.detail


def test_validator_error_blocks_the_mark() -> None:
    mark = assess(_artifact(errors=2))
    assert mark.awarded is False
    valid = next(c for c in mark.criteria if c.key == "valid")
    assert valid.met is False
    assert "2 validator errors" in valid.detail
    assert mark.to_dict()["status"] == NOT_YET


def test_expiring_feed_blocks_the_mark() -> None:
    mark = assess(_artifact(days=10))
    current = next(c for c in mark.criteria if c.key == "current")
    assert current.met is False
    assert mark.awarded is False


def test_lapsed_feed_blocks_the_mark() -> None:
    current = next(c for c in assess(_artifact(days=-3)).criteria if c.key == "current")
    assert current.met is False
    assert "expired" in current.detail


def test_low_accessibility_blocks_the_mark() -> None:
    mark = assess(_artifact(stops_pct=80.0, trips_pct=100.0))
    access = next(c for c in mark.criteria if c.key == "accessible")
    assert access.met is False
    assert "needs 90%" in access.detail
    assert mark.awarded is False


def test_at_the_floor_is_met() -> None:
    access = next(
        c
        for c in assess(_artifact(stops_pct=90.0, trips_pct=90.0)).criteria
        if c.key == "accessible"
    )
    assert access.met is True


def test_unmeasured_correctness_and_missing_accessibility_block() -> None:
    mark = assess({"categories": {"correctness": {"status": "skipped"}}})
    keys = {c.key: c.met for c in mark.criteria}
    assert keys["valid"] is False
    assert keys["accessible"] is False
    assert mark.awarded is False


def test_mark_badge_renders_self_contained_svg() -> None:
    svg = render_mark()
    assert svg.startswith("<svg")
    assert "conformant" in svg
    assert "<title>" in svg
    assert "http://www.w3.org/2000/svg" in svg
