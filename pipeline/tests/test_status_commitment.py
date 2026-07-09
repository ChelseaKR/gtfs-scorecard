"""Tests for the consumer-facing freshness/uptime commitment (pure, EXP-10)."""

from __future__ import annotations

import datetime as dt

from scorecard_pipeline.metrics import STALE_FEED_DAYS, UNREACHABLE_STREAK_CHECKS
from scorecard_pipeline.status_commitment import (
    build_status_commitment,
    cadence_commitment,
    degradation_policy,
    refresh_success_record,
)

NOW = dt.datetime(2026, 7, 8, 12, 0, tzinfo=dt.UTC)


def _feed(checked_at: str, *, failures: int = 0) -> dict[str, object]:
    return {"checked_at": checked_at, "consecutive_failures": failures}


def test_cadence_commitment_has_all_three_tiers_with_a_cadence() -> None:
    tiers = cadence_commitment()
    names = {t["tier"] for t in tiers}
    assert names == {"priority", "standard", "full_validation"}
    for t in tiers:
        assert t["cadence"]
        assert t["applies_to"]
        assert t["schedule_cron"]


def test_degradation_policy_uses_the_real_code_thresholds() -> None:
    policy = degradation_policy()
    assert policy["unreachable_after_consecutive_checks"] == UNREACHABLE_STREAK_CHECKS
    assert policy["stale_after_days_past_expiry"] == STALE_FEED_DAYS
    assert len(policy["statements"]) >= 3


def test_refresh_success_record_empty_feeds_degrades_cleanly() -> None:
    record = refresh_success_record({}, NOW)
    assert record["feeds_tracked"] == 0
    assert record["success_rate_pct"] is None


def test_refresh_success_record_classifies_healthy_degraded_unreachable() -> None:
    feeds = {
        "healthy-a": _feed("2026-07-08T11:00:00+00:00", failures=0),
        "healthy-b": _feed("2026-07-08T10:00:00+00:00", failures=0),
        "degraded": _feed("2026-07-08T09:00:00+00:00", failures=3),
        "dead": _feed("2026-07-01T00:00:00+00:00", failures=UNREACHABLE_STREAK_CHECKS),
    }
    record = refresh_success_record(feeds, NOW)
    assert record["feeds_tracked"] == 4
    assert record["healthy"] == 2
    assert record["degraded"] == 1
    assert record["unreachable"] == 1
    assert record["success_rate_pct"] == 50.0
    # The dead feed hasn't checked in a week; max staleness reflects that.
    assert record["hours_since_last_check"]["max"] > 24


def test_refresh_success_record_tolerates_malformed_timestamps() -> None:
    feeds = {"bad": {"checked_at": "not-a-date", "consecutive_failures": 0}}
    record = refresh_success_record(feeds, NOW)
    assert record["feeds_tracked"] == 1
    assert record["hours_since_last_check"]["max"] is None


def test_build_status_commitment_assembles_every_section() -> None:
    feeds = {"a": _feed("2026-07-08T11:30:00+00:00")}
    doc = build_status_commitment(feeds, NOW, "https://gtfsscorecard.org")
    assert doc["license"]
    assert doc["attribution"]
    assert doc["human_readable"] == "https://gtfsscorecard.org/status/"
    assert doc["commitment"]["tiers"]
    assert doc["refresh_success_record"]["feeds_tracked"] == 1
    assert doc["degradation_policy"]["statements"]
