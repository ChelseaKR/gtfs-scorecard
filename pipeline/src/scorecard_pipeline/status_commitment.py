"""The consumer-facing data freshness and uptime commitment (EXP-10).

FIX-11's run-summary work publishes what the pipeline did each day for our own
operational visibility. This module is the outward-facing half: a downstream
consumer (an app developer, a researcher, a state program) should not have to
take "refreshed daily" on faith from a README. This builds the machine-readable
commitment they can check the pipeline against:

- the *intended* refresh cadence per tier, sourced from the same tiering the
  intraday refresh actually runs on (`cadence.py`, ADR 0010) rather than a
  separately maintained claim that can drift from reality;
- the current feed-URL liveness record, computed from the state
  (`data/liveness.json`) the intraday refresh already keeps: how many tracked
  feeds are checking clean, how old the latest checks are, and how many have
  been flagged unreachable;
- a stated degradation policy: what happens, and what a consumer sees, when a
  feed cannot be refreshed on schedule. No promise the static architecture
  cannot keep -- the point is to state the real commitment honestly and let a
  consumer verify it.

Pure over the liveness dict and a clock, so it is reproducible and unit-tested
without touching the filesystem or the network.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import DATA_ATTRIBUTION, DATA_LICENSE
from .cadence import STANDARD_PERIOD
from .metrics import STALE_FEED_DAYS, UNREACHABLE_STREAK_CHECKS

# The two workflows this commitment describes (ADR 0010). Kept as plain
# strings, not parsed from the workflow YAML, so a change to the schedule is a
# deliberate edit here too rather than a silent drift -- the CI check in
# test_status_commitment.py cross-reads the workflow files to catch that drift.
DAILY_FULL_SCORE_CRON = "23 13 * * *"  # .github/workflows/scorecard.yml
INTRADAY_REFRESH_CRON = "23 * * * *"  # .github/workflows/refresh.yml


def cadence_commitment() -> list[dict[str, Any]]:
    """The intended refresh cadence per tier: what a consumer should expect,
    not just what happened once. Mirrors `cadence.py`'s two tiers exactly."""
    return [
        {
            "tier": "priority",
            "applies_to": (
                "feeds with measured realtime data, and any feed in the "
                "expiry danger or recovery window (expiring soon, or recently "
                "lapsed)"
            ),
            "cadence": "one direct liveness check every hour",
            "schedule_cron": INTRADAY_REFRESH_CRON,
        },
        {
            "tier": "standard",
            "applies_to": "every other tracked feed",
            "cadence": f"one direct liveness check in each {STANDARD_PERIOD}-hour "
            "period, on a stable per-feed schedule that spreads requests across "
            "the period",
            "schedule_cron": INTRADAY_REFRESH_CRON,
        },
        {
            "tier": "full_validation",
            "applies_to": "every registered feed",
            "cadence": "one full validation each day",
            "schedule_cron": DAILY_FULL_SCORE_CRON,
        },
    ]


def degradation_policy() -> dict[str, Any]:
    """What a consumer sees, and what the pipeline does, when a feed cannot be
    refreshed on schedule. Every threshold here is imported, not restated, so
    this can never drift from the code that actually enforces it."""
    return {
        "unreachable_after_consecutive_checks": UNREACHABLE_STREAK_CHECKS,
        "stale_after_days_past_expiry": STALE_FEED_DAYS,
        "statements": [
            "If a fetch fails, the last successful scorecard remains available. "
            "The pipeline recalculates only its calendar-based freshness and "
            "expiry fields. It never rewrites an older snapshot.",
            "A feed whose calendar has been past its expiry date for more than "
            f"{STALE_FEED_DAYS} days is labeled 'stale' rather than 'lapsed', "
            "which changes how it is described but not whether it is served.",
            "A configured feed URL is labeled 'unreachable' after "
            f"{UNREACHABLE_STREAK_CHECKS} consecutive direct checks fail (roughly "
            "a week at standard cadence). This is separate from an expired "
            "calendar.",
            "These observations do not guarantee an agency's GTFS host will stay "
            "online. The status page records what the pipeline observed and when.",
        ],
    }


def refresh_success_record(feeds: dict[str, dict[str, Any]], now: dt.datetime) -> dict[str, Any]:
    """The current direct-URL liveness record computed from intraday state.

    ``success_rate_pct`` is retained as the v1 compatibility name for the
    current clean-feed share. It is not a historical request-success rate;
    ``currently_clean_pct`` is the accurately named additive field.
    """
    total = len(feeds)
    if total == 0:
        return {
            "as_of": now.isoformat(timespec="seconds"),
            "feeds_tracked": 0,
            "healthy": 0,
            "degraded": 0,
            "unreachable": 0,
            "currently_clean_pct": None,
            "success_rate_pct": None,
            "measurement_note": (
                "Current share of feed records with no consecutive failed direct check; "
                "not a historical request-success rate."
            ),
            "hours_since_last_check": {"min": None, "median": None, "max": None},
        }

    healthy = 0
    unreachable = 0
    hours_since: list[float] = []
    for record in feeds.values():
        failures = int(record.get("consecutive_failures") or 0)
        if failures >= UNREACHABLE_STREAK_CHECKS:
            unreachable += 1
        elif failures == 0:
            healthy += 1
        checked_at = record.get("checked_at")
        if checked_at:
            try:
                checked = dt.datetime.fromisoformat(str(checked_at))
            except ValueError:
                continue
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=dt.UTC)
            hours_since.append((now - checked).total_seconds() / 3600)

    degraded = total - healthy - unreachable
    hours_since.sort()
    n = len(hours_since)

    def _pick(fraction: float) -> float | None:
        if n == 0:
            return None
        idx = min(n - 1, int(fraction * n))
        return round(hours_since[idx], 1)

    currently_clean_pct = round(100 * healthy / total, 1)
    return {
        "as_of": now.isoformat(timespec="seconds"),
        "feeds_tracked": total,
        "healthy": healthy,
        "degraded": degraded,
        "unreachable": unreachable,
        "currently_clean_pct": currently_clean_pct,
        "success_rate_pct": currently_clean_pct,
        "measurement_note": (
            "Current share of feed records with no consecutive failed direct check; "
            "not a historical request-success rate."
        ),
        "hours_since_last_check": {
            "min": _pick(0.0),
            "median": _pick(0.5),
            "max": round(hours_since[-1], 1) if hours_since else None,
        },
    }


def build_status_commitment(
    feeds: dict[str, dict[str, Any]],
    now: dt.datetime,
    base_url: str,
) -> dict[str, Any]:
    """Assemble the full published commitment: cadence + historical record +
    degradation policy, in one machine-readable document."""
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "description": (
            "The intended refresh cadence, current direct feed-URL liveness, "
            "and what happens when a feed cannot be refreshed on schedule."
        ),
        "human_readable": f"{base_url}/status/",
        "commitment": {
            "tiers": cadence_commitment(),
            "source": (
                "ADR 0010 (docs/decisions/0010-update-cadence.md); tiering logic "
                "in pipeline/src/scorecard_pipeline/cadence.py"
            ),
        },
        "refresh_success_record": refresh_success_record(feeds, now),
        "degradation_policy": degradation_policy(),
    }
