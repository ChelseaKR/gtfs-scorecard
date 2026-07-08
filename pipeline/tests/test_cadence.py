"""Tests for per-feed cadence tiers (pure)."""

from __future__ import annotations

import itertools
from typing import Any

from scorecard_pipeline.cadence import (
    PRIORITY,
    STANDARD,
    STANDARD_PERIOD,
    cadence_tier,
    due_now,
    is_due,
)


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
    due_hours = [h for h in range(24) if is_due("some-agency", STANDARD, h)]
    # Once every STANDARD_PERIOD hours: 24 / 6 = 4 times a day, evenly spaced.
    assert len(due_hours) == 24 // STANDARD_PERIOD
    gaps = {b - a for a, b in itertools.pairwise(due_hours)}
    assert gaps == {STANDARD_PERIOD}


def test_standard_feeds_spread_across_buckets() -> None:
    # Different ids land in different cycles rather than all checking at once.
    ids = [f"agency-{i}" for i in range(60)]
    tiers = dict.fromkeys(ids, STANDARD)
    due_per_hour = [len(due_now(tiers, h)) for h in range(STANDARD_PERIOD)]
    # Every standard feed is checked exactly once over a full period.
    assert sum(due_per_hour) == len(ids)
    # And the load is spread, not all in one cycle.
    assert max(due_per_hour) < len(ids)


def test_due_now_includes_all_priority_plus_due_standard() -> None:
    tiers = {"rt": PRIORITY, "stable-a": STANDARD, "stable-b": STANDARD}
    for hour in range(24):
        due = due_now(tiers, hour)
        assert "rt" in due  # priority always present
