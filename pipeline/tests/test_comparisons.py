"""Tests for public comparison eligibility and cohort suppression."""

from __future__ import annotations

from scorecard_pipeline.comparisons import comparison_eligible, comparison_exclusions


def _row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "one",
        "date": "2026-07-01",
        "score": 80,
        "correctness": 80,
        "freshness": 80,
        "completeness": 80,
        "days_until_expiry": 60,
    }
    row.update(changes)
    return row


def test_current_fully_measured_feed_is_comparable() -> None:
    assert comparison_eligible(_row())
    assert comparison_exclusions(_row()) == ()


def test_long_expired_and_partially_measured_feeds_are_excluded_with_reasons() -> None:
    reasons = comparison_exclusions(_row(days_until_expiry=-500, completeness=None))
    assert "service_data_long_expired" in reasons
    assert "completeness_not_measured" in reasons
    assert not comparison_eligible(_row(days_until_expiry=-500))
