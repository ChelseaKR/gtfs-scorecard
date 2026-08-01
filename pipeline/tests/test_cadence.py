"""Tests for per-feed cadence tiers (pure)."""

from __future__ import annotations

import itertools
from typing import Any

from scorecard_pipeline.cadence import (
    PRIORITY,
    REFRESH_STEP_HOURS,
    STANDARD,
    STANDARD_PERIOD,
    cadence_tier,
    cycles_per_period,
    due_now,
    is_due,
)

# The hours a refresh actually runs, given the cron. Tests that sweep `range(24)`
# hide cadence bugs, because 20 of those hours never host a run.
RUN_HOURS = list(range(0, 24, REFRESH_STEP_HOURS))


def _artifact(
    *, rt: str = "not_yet_measured", days: int | None = 100, grade: str = "B"
) -> dict[str, Any]:
    return {
        "overall": {"grade": grade},
        "categories": {
            "realtime": {"status": rt},
            "freshness": {"status": "measured", "details": {"days_until_expiry": days}},
        },
    }


def test_realtime_publisher_is_priority() -> None:
    assert cadence_tier(_artifact(rt="measured", days=200)) == PRIORITY


def test_expiring_or_recently_lapsed_is_priority() -> None:
    assert cadence_tier(_artifact(days=10)) == PRIORITY  # expiring soon
    assert cadence_tier(_artifact(days=-30)) == PRIORITY  # recently lapsed
    # Long dead (over a year) is likely abandoned, not worth the tight cadence.
    assert cadence_tier(_artifact(days=-400)) == STANDARD


def test_healthy_static_feed_is_standard() -> None:
    assert cadence_tier(_artifact(days=200)) == STANDARD
    # No readable expiry also falls to standard.
    assert cadence_tier(_artifact(days=None)) == STANDARD


def test_priority_feeds_are_due_every_cycle() -> None:
    for hour in range(24):
        assert is_due("anything", PRIORITY, hour) is True


def test_standard_feed_is_due_once_per_period() -> None:
    # Only the hours a run actually happens on count. Sweeping range(24) would
    # pass even if the cadence step and the bucket arithmetic disagreed.
    due_hours = [h for h in RUN_HOURS if is_due("some-agency", STANDARD, h)]
    # Once every STANDARD_PERIOD hours: 24 / 6 = 4 times a day, evenly spaced.
    assert len(due_hours) == 24 // STANDARD_PERIOD
    gaps = {b - a for a, b in itertools.pairwise(due_hours)}
    assert gaps == {STANDARD_PERIOD}


def test_every_standard_feed_is_reached_at_the_configured_cadence() -> None:
    """The regression guard for the bug this cadence change would have caused.

    `is_due` used to test `hour % STANDARD_PERIOD`, which only enumerated all
    six buckets while a run happened every hour. On a three-hour cron the run
    hours are 0, 3, 6, ..., `hour % 6` is only ever 0 or 3, and two thirds of
    the standard feeds would never have come due again: no liveness check, no
    growing failure streak, no `unreachable` label, just a `checked_at` frozen
    forever. Assert coverage over the hours that actually run.
    """
    ids = [f"agency-{i}" for i in range(500)]
    reached = {aid for h in RUN_HOURS for aid in ids if is_due(aid, STANDARD, h)}
    assert reached == set(ids)


def test_standard_feeds_spread_across_buckets() -> None:
    # Different ids land in different cycles rather than all checking at once.
    ids = [f"agency-{i}" for i in range(60)]
    tiers = dict.fromkeys(ids, STANDARD)
    period_hours = [h for h in RUN_HOURS if h < STANDARD_PERIOD]
    due_per_cycle = [len(due_now(tiers, h)) for h in period_hours]
    # Every standard feed is checked exactly once over a full period.
    assert sum(due_per_cycle) == len(ids)
    # And the load is spread, not all in one cycle.
    assert max(due_per_cycle) < len(ids)


def test_hourly_cadence_keeps_the_previous_arithmetic() -> None:
    # `step=1` has to reduce to the old `hour % period == bucket` behaviour, so
    # the change is a generalization rather than a different schedule.
    assert cycles_per_period(STANDARD_PERIOD, 1) == STANDARD_PERIOD
    hourly = [h for h in range(24) if is_due("some-agency", STANDARD, h, step=1)]
    assert len(hourly) == 24 // STANDARD_PERIOD
    assert {b - a for a, b in itertools.pairwise(hourly)} == {STANDARD_PERIOD}


def test_cadence_slower_than_the_period_degrades_to_every_cycle() -> None:
    # Never divide down to zero buckets: a step wider than the period means
    # every standard feed is checked on every cycle, not on none of them.
    assert cycles_per_period(STANDARD_PERIOD, 8) == 1
    assert is_due("some-agency", STANDARD, 8, step=8) is True


def test_due_now_includes_all_priority_plus_due_standard() -> None:
    tiers = {"rt": PRIORITY, "stable-a": STANDARD, "stable-b": STANDARD}
    for hour in RUN_HOURS:
        due = due_now(tiers, hour)
        assert "rt" in due  # priority always present
