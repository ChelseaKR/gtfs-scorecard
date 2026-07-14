"""Tests for guarded public comparison cohorts."""

from __future__ import annotations

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.comparisons import (
    build_comparison_cohort,
    comparison_eligible,
    comparison_exclusions,
)
from scorecard_pipeline.config import Agency
from scorecard_pipeline.validate import VALIDATOR_VERSION


def _row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "one",
        "date": "2026-07-01",
        "score": 80,
        "correctness": 80,
        "freshness": 80,
        "completeness": 80,
        "days_until_expiry": 60,
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": RUBRIC_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "feed_sha256": "sha-one",
    }
    row.update(changes)
    return row


def test_current_fully_measured_feed_is_comparable() -> None:
    assert comparison_eligible(_row())
    assert comparison_exclusions(_row()) == ()


def test_catalog_snapshot_date_is_accepted_as_the_check_date() -> None:
    row = _row(snapshot_date="2026-07-01")
    row.pop("date")

    assert comparison_exclusions(row) == ()


def test_long_expired_and_partially_measured_feeds_are_excluded_with_reasons() -> None:
    reasons = comparison_exclusions(_row(days_until_expiry=-500, completeness=None))
    assert "service_data_long_expired" in reasons
    assert "completeness_not_measured" in reasons
    assert not comparison_eligible(_row(days_until_expiry=-500))


def test_cohort_excludes_missing_and_mixed_rubric_versions() -> None:
    records = [
        _row(id="current", feed_sha256="sha-current"),
        _row(id="old", rubric_version="1.1", feed_sha256="sha-old"),
        _row(id="unknown", rubric_version=None, feed_sha256="sha-unknown"),
    ]

    eligible, comparison = build_comparison_cohort(records)

    assert [row["id"] for row in eligible] == ["current"]
    assert comparison["required_rubric_version"] == RUBRIC_VERSION
    assert comparison["eligible_count"] == 1
    assert comparison["excluded_count"] == 2
    assert comparison["exclusion_counts"] == {
        "rubric_version_mismatch": 1,
        "rubric_version_missing": 1,
    }


def test_cohort_excludes_duplicate_registry_urls_and_feed_hashes() -> None:
    records = [
        _row(id="url-a", feed_sha256="sha-url-a"),
        _row(id="url-b", feed_sha256="sha-url-b"),
        _row(id="hash-a", feed_sha256="same-bytes"),
        _row(id="hash-b", feed_sha256="same-bytes"),
        _row(id="unique", feed_sha256="sha-unique"),
    ]
    agencies = [
        Agency("url-a", "URL A", "https://example.org/feed.zip"),
        Agency("url-b", "URL B", "http://example.org/feed.zip"),
        Agency("hash-a", "Hash A", "https://one.example/feed.zip"),
        Agency("hash-b", "Hash B", "https://two.example/feed.zip"),
        Agency("unique", "Unique", "https://unique.example/feed.zip"),
    ]

    eligible, comparison = build_comparison_cohort(records, agencies=agencies)

    assert [row["id"] for row in eligible] == ["unique"]
    assert comparison["exclusion_counts"] == {"duplicate_feed_identity": 4}
    assert comparison["absolute_rankings_published"] is False
    assert comparison["individual_percentiles_published"] is False


def test_cohort_requires_one_producer_and_measured_category_contract() -> None:
    records = [
        _row(id="schedule-a", feed_sha256="schedule-a"),
        _row(id="schedule-b", feed_sha256="schedule-b"),
        _row(id="with-rt", realtime=90, feed_sha256="with-rt"),
        _row(id="old-validator", validator_version="0.0.0", feed_sha256="old-validator"),
        _row(id="old-profile", scoring_profile_id="old", feed_sha256="old-profile"),
    ]

    eligible, comparison = build_comparison_cohort(records)

    assert [row["id"] for row in eligible] == ["schedule-a", "schedule-b"]
    assert comparison["required_measured_categories"] == [
        "correctness",
        "freshness",
        "completeness",
    ]
    assert comparison["required_scoring_profile_id"] == SCORING_PROFILE_ID
    assert comparison["required_validator_version"] == VALIDATOR_VERSION
    assert comparison["exclusion_counts"] == {
        "measured_category_set_mismatch": 1,
        "scoring_profile_mismatch": 1,
        "validator_version_mismatch": 1,
    }
