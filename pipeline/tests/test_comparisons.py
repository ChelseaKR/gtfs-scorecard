"""Tests for guarded public comparison cohorts."""

from __future__ import annotations

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.comparisons import (
    build_comparison_cohort,
    comparison_eligible,
    comparison_exclusions,
    current_producer_contract_suffix,
    reader_archive_profile,
    same_producer_contract,
)
from scorecard_pipeline.config import Agency
from scorecard_pipeline.fetch import RAW_READER_ARCHIVE_PROFILE
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
    assert reader_archive_profile(_row()) == RAW_READER_ARCHIVE_PROFILE


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
    assert comparison["required_reader_archive_profile"] == RAW_READER_ARCHIVE_PROFILE
    assert comparison["exclusion_counts"] == {
        "measured_category_set_mismatch": 1,
        "scoring_profile_mismatch": 1,
        "validator_version_mismatch": 1,
    }


def test_normalized_reader_view_stays_public_but_is_comparison_excluded() -> None:
    normalized = _row(reader_archive_profile="flat-single-root-v1")

    reasons = comparison_exclusions(normalized)
    eligible, comparison = build_comparison_cohort([normalized])

    assert reasons == ("reader_archive_profile_mismatch",)
    assert eligible == []
    assert comparison["required_reader_archive_profile"] == RAW_READER_ARCHIVE_PROFILE
    assert comparison["exclusion_counts"] == {"reader_archive_profile_mismatch": 1}


def test_explicit_unknown_reader_profile_fails_closed_even_when_both_match() -> None:
    left = _row(reader_archive_profile="future-unknown")
    right = _row(reader_archive_profile="future-unknown")
    left["categories"] = {"correctness": {"status": "measured"}}
    right["categories"] = {"correctness": {"status": "measured"}}

    assert reader_archive_profile(left) == ""
    assert same_producer_contract(left, right) is False


def test_explicit_empty_or_null_reader_profile_is_not_legacy_raw() -> None:
    assert reader_archive_profile(_row(reader_archive_profile="")) == ""
    assert reader_archive_profile(_row(reader_archive_profile=None)) == ""
    assert reader_archive_profile(_row(fetch={"reader_archive_profile": ""})) == ""
    assert reader_archive_profile(_row(fetch={"reader_archive_profile": None})) == ""


def test_contradictory_reader_archive_provenance_fails_closed() -> None:
    contradictory = [
        _row(
            reader_archive_profile="raw-v1",
            fetch={"reader_archive_profile": "flat-single-root-v1"},
        ),
        _row(
            reader_archive_profile="flat-single-root-v1",
            fetch={"reader_archive_profile": "raw-v1"},
        ),
        _row(
            fetch={
                "reader_archive_profile": "raw-v1",
                "reader_archive_normalized": True,
            }
        ),
        _row(
            fetch={
                "reader_archive_profile": "flat-single-root-v1",
                "reader_archive_normalized": False,
            }
        ),
        _row(fetch={"reader_archive_normalized": "true"}),
    ]

    for record in contradictory:
        record["categories"] = {"correctness": {"status": "measured"}}
        assert reader_archive_profile(record) == ""
        assert same_producer_contract(record, record) is False


def test_consistent_and_legacy_reader_archive_provenance_resolves() -> None:
    assert reader_archive_profile(_row(fetch={"reader_archive_normalized": True})) == (
        "flat-single-root-v1"
    )
    assert reader_archive_profile(_row(fetch={"reader_archive_normalized": False})) == "raw-v1"
    assert (
        reader_archive_profile(
            _row(
                reader_archive_profile="flat-single-root-v1",
                fetch={
                    "reader_archive_profile": "flat-single-root-v1",
                    "reader_archive_normalized": True,
                },
            )
        )
        == "flat-single-root-v1"
    )
    assert (
        reader_archive_profile(
            _row(
                reader_archive_profile="raw-v1",
                fetch={
                    "reader_archive_profile": "raw-v1",
                    "reader_archive_normalized": False,
                },
            )
        )
        == "raw-v1"
    )


def test_raw_to_flat_profile_breaks_transition_and_resets_suffix() -> None:
    raw = _row()
    flat = _row(reader_archive_profile="flat-single-root-v1")
    for record in (raw, flat):
        record["categories"] = {"correctness": {"status": "measured"}}

    assert same_producer_contract(raw, flat) is False
    assert current_producer_contract_suffix([raw, flat]) == [flat]
