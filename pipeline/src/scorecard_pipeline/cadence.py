"""Per-feed cadence tiers for the intraday refresh.

The intraday refresh (ADR 0010) checks feeds for change far more cheaply than a
full score, but checking all ~1,100 feeds on the tightest cadence is neither
polite to every host nor useful: most feeds are stable and change at most a few
times a year. This splits feeds into tiers so the ones where a change matters
soonest are checked every cycle, while the stable long tail is spread out.

Priority feeds (checked every cycle):
- realtime publishers, whose feeds change constantly and whose health is the
  point of the realtime category;
- feeds in the expiry danger or recovery window (expiring soon, or recently
  lapsed and likely to be re-exported), where catching the change early is the
  whole value.

Everything else is standard: checked once per period, with each feed assigned a
stable bucket from its id so the load spreads evenly across cycles instead of
hammering every host at once.

Pure and testable: the live check still happens in liveness.py.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .metrics import expiry_status

PRIORITY = "priority"
STANDARD = "standard"

# How many hours a standard feed waits between checks: one check per six-hour
# period, whatever the refresh cadence is.
STANDARD_PERIOD = 6

# Hours between intraday refresh cycles. Must match the cron in
# .github/workflows/refresh.yml; test_status_commitment.py cross-reads that file
# and fails if the two drift.
#
# This has to be known here, not inferred from the clock, because the due-list
# math is keyed to the cycle a run belongs to. `hour % STANDARD_PERIOD` worked
# only while a run happened every hour: at a three-hour cadence the run hours are
# 0, 3, 6, ... and `hour % 6` can only ever equal 0 or 3, so feeds in buckets
# 1, 2, 4 and 5 would silently never come due again.
REFRESH_STEP_HOURS = 3


def cadence_tier(artifact: dict[str, Any]) -> str:
    """Classify a feed from its latest artifact into a check cadence tier."""
    categories = artifact.get("categories", {})
    if categories.get("realtime", {}).get("status") == "measured":
        return PRIORITY
    days = categories.get("freshness", {}).get("details", {}).get("days_until_expiry")
    if expiry_status(days) in ("expiring_soon", "lapsed"):
        return PRIORITY
    return STANDARD


def _bucket(agency_id: str, buckets: int) -> int:
    """A stable 0..buckets-1 bucket for a feed, so standard checks spread evenly."""
    digest = hashlib.sha256(agency_id.encode()).hexdigest()
    return int(digest, 16) % buckets


def cycles_per_period(period: int = STANDARD_PERIOD, step: int = REFRESH_STEP_HOURS) -> int:
    """How many refresh cycles fall inside one standard period.

    That count is also the number of buckets the long tail spreads across: a
    six-hour period at a three-hour cadence gives two cycles, so half the
    standard feeds are checked on each. Never less than one, so a cadence slower
    than the period degrades to "every cycle" rather than to "never".
    """
    return max(1, period // step)


def is_due(
    agency_id: str,
    tier: str,
    hour: int,
    *,
    period: int = STANDARD_PERIOD,
    step: int = REFRESH_STEP_HOURS,
) -> bool:
    """Whether a feed should be checked on the cycle at `hour` (0-23).

    Keyed to the cycle index (`hour // step`) rather than to the raw hour, so
    every bucket still comes round exactly once per period no matter how far
    apart the cycles are. At `step=1` this is the same arithmetic as before.
    """
    if tier == PRIORITY:
        return True
    buckets = cycles_per_period(period, step)
    return (hour // step) % buckets == _bucket(agency_id, buckets)


def due_now(
    tiers_by_id: dict[str, str],
    hour: int,
    *,
    period: int = STANDARD_PERIOD,
    step: int = REFRESH_STEP_HOURS,
) -> list[str]:
    """The feed ids due to be checked on the cycle at `hour`, sorted."""
    return sorted(
        aid
        for aid, tier in tiers_by_id.items()
        if is_due(aid, tier, hour, period=period, step=step)
    )
