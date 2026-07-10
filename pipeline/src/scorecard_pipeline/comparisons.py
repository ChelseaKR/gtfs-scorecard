"""Eligibility and sample-size guardrails for public cross-agency comparisons."""

from __future__ import annotations

from typing import Any

MIN_PUBLIC_COMPARISON_COHORT = 20
REQUIRED_CATEGORIES = ("correctness", "freshness", "completeness")


def comparison_exclusions(record: dict[str, Any]) -> tuple[str, ...]:
    """Reasons a latest-record row is not suitable for a public comparison.

    The underlying record remains in the open dataset. Exclusion only affects
    ranked and percentile surfaces, where comparing a long-stale or partially
    measured feed with a current, fully measured feed would overstate meaning.
    """
    reasons: list[str] = []
    if not isinstance(record.get("score"), (int, float)) or isinstance(record.get("score"), bool):
        reasons.append("score_not_measured")
    if not record.get("date"):
        reasons.append("snapshot_date_missing")
    for category in REQUIRED_CATEGORIES:
        if not isinstance(record.get(category), (int, float)) or isinstance(
            record.get(category), bool
        ):
            reasons.append(f"{category}_not_measured")
    days = record.get("days_until_expiry")
    if isinstance(days, (int, float)) and not isinstance(days, bool) and days < -365:
        reasons.append("service_data_long_expired")
    return tuple(reasons)


def comparison_eligible(record: dict[str, Any]) -> bool:
    return not comparison_exclusions(record)
