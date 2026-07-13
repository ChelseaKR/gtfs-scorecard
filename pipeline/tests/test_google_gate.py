"""Tests for the Google/Apple Maps acceptance gate."""

from __future__ import annotations

import datetime as dt
from typing import Any

from scorecard_pipeline.google_gate import (
    MIN_FORWARD_DAYS,
    GoogleGate,
    forward_coverage_days,
    from_artifact,
    google_acceptance,
)

TODAY = dt.date(2026, 6, 20)


def test_forward_coverage_days_counts_remaining_days() -> None:
    assert forward_coverage_days(TODAY + dt.timedelta(days=90), TODAY) == 90


def test_forward_coverage_days_negative_when_expired() -> None:
    assert forward_coverage_days(TODAY - dt.timedelta(days=5), TODAY) == -5


def test_forward_coverage_days_none_when_no_end_date() -> None:
    assert forward_coverage_days(None, TODAY) is None


def test_ninety_days_forward_passes() -> None:
    gate = google_acceptance(TODAY + dt.timedelta(days=90), TODAY)
    assert isinstance(gate, GoogleGate)
    assert gate.status == "pass"
    assert gate.days_forward == 90
    assert gate.detail


def test_ten_days_forward_is_at_risk() -> None:
    gate = google_acceptance(TODAY + dt.timedelta(days=10), TODAY)
    assert gate.status == "at_risk"
    assert gate.days_forward == 10
    assert "10 days" in gate.detail


def test_expired_feed_fails() -> None:
    gate = google_acceptance(TODAY - dt.timedelta(days=3), TODAY)
    assert gate.status == "fail"
    assert gate.days_forward == -3


def test_last_day_today_fails() -> None:
    # Zero days forward: the last day of service is today, which does not clear
    # the upcoming-service window.
    gate = google_acceptance(TODAY, TODAY)
    assert gate.status == "fail"
    assert gate.days_forward == 0


def test_none_end_date_fails() -> None:
    gate = google_acceptance(None, TODAY)
    assert gate.status == "fail"
    assert gate.days_forward is None
    assert gate.detail


def test_exactly_min_days_passes() -> None:
    gate = google_acceptance(TODAY + dt.timedelta(days=MIN_FORWARD_DAYS), TODAY)
    assert gate.status == "pass"
    assert gate.days_forward == MIN_FORWARD_DAYS


def test_one_day_short_of_min_is_at_risk() -> None:
    gate = google_acceptance(TODAY + dt.timedelta(days=MIN_FORWARD_DAYS - 1), TODAY)
    assert gate.status == "at_risk"
    assert gate.days_forward == MIN_FORWARD_DAYS - 1


def test_custom_min_days_is_respected() -> None:
    last = TODAY + dt.timedelta(days=40)
    assert google_acceptance(last, TODAY, min_days=60).status == "at_risk"
    assert google_acceptance(last, TODAY, min_days=30).status == "pass"


def test_gate_is_frozen() -> None:
    import dataclasses

    import pytest

    gate = google_acceptance(TODAY + dt.timedelta(days=90), TODAY)
    with pytest.raises(dataclasses.FrozenInstanceError):
        gate.status = "fail"  # type: ignore[misc]


def _artifact(last_service_date: str | None) -> dict[str, Any]:
    return {
        "categories": {
            "freshness": {
                "details": {"last_service_date": last_service_date},
            },
        },
    }


def test_from_artifact_pass() -> None:
    iso = (TODAY + dt.timedelta(days=90)).isoformat()
    gate = from_artifact(_artifact(iso), TODAY)
    assert gate.status == "pass"
    assert gate.days_forward == 90


def test_from_legacy_distant_artifact_keeps_pass_without_huge_countdown() -> None:
    artifact = _artifact("2099-12-31")
    artifact["snapshot_date"] = "2026-07-13"
    artifact["categories"]["freshness"]["details"]["days_until_expiry"] = 26_834
    gate = from_artifact(artifact, dt.date(2026, 7, 13))
    assert gate.status == "pass"
    assert gate.days_forward == 26_834
    assert "unusually distant" in gate.detail
    assert "26834" not in gate.detail


def test_from_artifact_at_risk() -> None:
    iso = (TODAY + dt.timedelta(days=10)).isoformat()
    gate = from_artifact(_artifact(iso), TODAY)
    assert gate.status == "at_risk"
    assert gate.days_forward == 10


def test_from_artifact_none_fails() -> None:
    gate = from_artifact(_artifact(None), TODAY)
    assert gate.status == "fail"
    assert gate.days_forward is None


def test_from_artifact_missing_keys_fails() -> None:
    gate = from_artifact({}, TODAY)
    assert gate.status == "fail"
    assert gate.days_forward is None


def test_from_artifact_unparsable_date_fails() -> None:
    gate = from_artifact(_artifact("not-a-date"), TODAY)
    assert gate.status == "fail"
    assert gate.days_forward is None
