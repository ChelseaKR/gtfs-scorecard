"""Tests for the versioned static public API builders (pure)."""

from __future__ import annotations

from typing import Any

import pytest

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.config import Agency
from scorecard_pipeline.dataset import build_quality_dataset
from scorecard_pipeline.location import COUNTRY_NAMES
from scorecard_pipeline.publicapi import (
    agencies_endpoint,
    api_index,
    build_api,
    by_location,
    by_state,
    coverage_endpoint,
    leaderboard,
    stats_endpoint,
)
from scorecard_pipeline.validate import VALIDATOR_VERSION


def _pt(
    date: str,
    score: float,
    grade: str,
    *,
    feed_sha256: str | None = None,
    rubric_version: str = RUBRIC_VERSION,
) -> dict[str, Any]:
    return {
        "date": date,
        "score": score,
        "grade": grade,
        "rubric_version": rubric_version,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": rubric_version,
        "validator_version": VALIDATOR_VERSION,
        "feed_sha256": feed_sha256 or f"sha-{date}-{score}-{grade}",
        "categories": {"correctness": 80, "freshness": 80, "completeness": 80},
        "days_until_expiry": 100,
    }


def _index() -> dict[str, Any]:
    return {
        "agencies": {
            "alpha": {"name": "Alpha Transit", "history": [_pt("2026-06-10", 90.0, "A")]},
            "bravo": {
                "name": "Bravo Transit",
                "history": [_pt("2026-06-08", 60.0, "D"), _pt("2026-06-10", 80.0, "B")],
            },
            "charlie": {
                "name": "Charlie Transit",
                "history": [_pt("2026-06-08", 75.0, "C"), _pt("2026-06-10", 55.0, "F")],
            },
        }
    }


def test_agencies_endpoint_is_the_flat_list() -> None:
    ds = build_quality_dataset(_index())
    ep = agencies_endpoint(ds)
    assert ep["count"] == 3
    assert {a["id"] for a in ep["agencies"]} == {"alpha", "bravo", "charlie"}
    assert ep["comparison"]["eligible_count"] == 3
    assert all(row["comparison_eligible"] is True for row in ep["agencies"])


def test_leaderboard_suppresses_absolute_lists_but_keeps_guarded_movers() -> None:
    idx = _index()
    board = leaderboard(idx, build_quality_dataset(idx), min_cohort=1)
    assert board["top"] == []
    assert board["bottom"] == []
    assert board["comparison"]["suppression_reason"] == "policy_no_absolute_rankings"
    assert board["comparison"]["absolute_rankings_published"] is False
    # Bravo rose 60 -> 80; Charlie fell 75 -> 55.
    assert board["most_improved"][0]["id"] == "bravo"
    assert board["most_improved"][0]["score_delta"] == 20.0
    assert board["most_declined"][0]["id"] == "charlie"
    assert board["most_declined"][0]["score_delta"] == -20.0
    # Alpha has one history point, so it is not a mover.
    assert all(m["id"] != "alpha" for m in board["most_improved"])


def test_leaderboard_without_ridership_omits_trips_field() -> None:
    idx = _index()
    board = leaderboard(idx, build_quality_dataset(idx), min_cohort=1)
    movers = board["most_improved"] + board["most_declined"]
    assert movers
    assert all("annual_trips" not in entry for entry in movers)


def test_leaderboard_ridership_context_applies_only_to_named_changes() -> None:
    idx = {
        "agencies": {
            "alpha": {"name": "Alpha", "history": [_pt("2026-06-10", 90.0, "A")]},
            "big": {
                "name": "Big",
                "history": [
                    _pt("2026-06-08", 75.0, "C", feed_sha256="sha-big-old"),
                    _pt("2026-06-10", 55.0, "F", feed_sha256="sha-big"),
                ],
            },
            "small": {
                "name": "Small",
                "history": [
                    _pt("2026-06-08", 75.0, "C", feed_sha256="sha-small-old"),
                    _pt("2026-06-10", 55.0, "F", feed_sha256="sha-small"),
                ],
            },
        }
    }
    trips = {"big": 5_000_000, "small": 10_000}
    board = leaderboard(idx, build_quality_dataset(idx), trips, min_cohort=1)
    assert board["top"] == []
    assert board["bottom"] == []
    assert [entry["id"] for entry in board["most_declined"]] == ["big", "small"]
    assert board["most_declined"][0]["annual_trips"] == 5_000_000
    assert board["most_declined"][1]["annual_trips"] == 10_000


def test_leaderboard_suppresses_small_or_incomparable_cohort() -> None:
    idx = _index()
    dataset = build_quality_dataset(idx)
    dataset["rows"][0]["days_until_expiry"] = -500
    board = leaderboard(idx, dataset)
    assert board["comparison"]["suppressed"] is True
    assert board["comparison"]["suppression_reason"] == "policy_no_absolute_rankings"
    assert board["comparison"]["eligible_count"] == 2
    assert board["comparison"]["exclusion_counts"]["service_data_long_expired"] == 1
    assert board["top"] == []
    assert board["bottom"] == []


def test_leaderboard_does_not_publish_a_cross_rubric_change() -> None:
    idx = _index()
    idx["agencies"]["bravo"]["history"][-2]["rubric_version"] = "1.1"

    board = leaderboard(idx, build_quality_dataset(idx), min_cohort=1)

    assert all(entry["id"] != "bravo" for entry in board["most_improved"])
    assert board["comparison"]["eligible_count"] == 3


def test_by_state_aggregates_with_unlocated_fallback() -> None:
    ds = build_quality_dataset(_index())
    out = by_state(ds, {"alpha": "California", "bravo": "California"})
    states = {s["state"]: s for s in out["states"]}
    assert states["California"]["count"] == 2
    assert states["California"]["comparison_eligible_count"] == 2
    assert states["California"]["median_score"] == 85.0  # median of 90, 80
    assert states["Unlocated"]["count"] == 1  # charlie has no state
    assert states["California"]["grade_distribution"]["A"] == 1


def test_by_state_excludes_explicit_non_us_records() -> None:
    ds = build_quality_dataset(_index())
    out = by_state(
        ds,
        {"alpha": "California", "bravo": "Ontario"},
        {
            "alpha": {"country": "US"},
            "bravo": {"country": "CA"},
            # A missing historical location remains a U.S. unlocated record.
        },
    )
    states = {row["state"]: row for row in out["states"]}

    assert states["California"]["count"] == 1
    assert states["Unlocated"]["count"] == 1
    assert "Ontario" not in states


def test_by_location_groups_countries_and_nested_subdivisions() -> None:
    ds = build_quality_dataset(_index())
    out = by_location(
        ds,
        {
            "alpha": {
                "country": "US",
                "subdivision_code": "US-CA",
                "subdivision_name": "California",
            },
            "bravo": {
                "country": "CA",
                "subdivision_code": "CA-ON",
                "subdivision_name": "Ontario",
            },
        },
    )
    countries = {row["country_code"]: row for row in out["countries"]}
    assert countries["US"]["country_name"] == "United States"
    assert countries["CA"]["country_name"] == "Canada"
    assert countries["US"]["count"] == 2
    assert countries["US"]["comparison_eligible_count"] == 2
    us_subdivisions = {row["subdivision_code"]: row for row in countries["US"]["subdivisions"]}
    assert us_subdivisions["US-CA"]["subdivision_name"] == "California"
    assert countries["CA"]["subdivisions"][0]["subdivision_name"] == "Ontario"
    assert us_subdivisions[None]["count"] == 1


def test_by_location_uses_configured_country_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(COUNTRY_NAMES, "GB", "United Kingdom")
    ds = build_quality_dataset(
        {"agencies": {"alpha": {"name": "Alpha", "history": [_pt("2026-07-01", 90, "A")]}}}
    )
    out = by_location(
        ds,
        {
            "alpha": {
                "country": "GB",
                "subdivision_code": "GB-ENG",
                "subdivision_name": "England",
            }
        },
    )
    assert out["countries"][0]["country_name"] == "United Kingdom"


def test_stats_has_median_and_grade_distribution() -> None:
    ds = build_quality_dataset(_index())
    st = stats_endpoint(ds)
    assert st["agency_count"] == 3
    assert st["comparison_eligible_count"] == 3
    assert st["median_score"] == 80.0  # median of 90, 80, 55
    assert st["grade_distribution"]["A"] == 1
    assert st["grade_distribution"]["F"] == 1


def test_coverage_keeps_registry_and_publication_counts_separate() -> None:
    idx = _index()
    idx["agencies"]["unscored"] = {"name": "Not scored", "history": []}
    agencies = [
        Agency("alpha", "Alpha", "https://example.org/alpha.zip"),
        Agency(
            "bravo",
            "Bravo",
            "https://example.org/bravo.zip",
            organization_id="shared-operator",
            country="CA",
        ),
        Agency(
            "old",
            "Old",
            "https://example.org/old.zip",
            feed_status="deprecated",
            alias_of="alpha",
        ),
    ]

    coverage = coverage_endpoint(idx, build_quality_dataset(idx), agencies)
    assert coverage["configured_feed_records"] == 3
    assert coverage["active_canonical_feed_records"] == 2
    assert coverage["country_count"] == 2
    assert coverage["distinct_organization_keys"] == 2
    assert coverage["provisional_organization_keys"] == 1
    assert coverage["published_scorecard_pages"] == 4
    assert coverage["scored_latest_rows"] == 3


def test_api_index_lists_endpoints_and_license() -> None:
    idx = api_index("https://example.org", "2026-06-21T00:00:00+00:00")
    assert idx["version"] == "v1"
    assert idx["endpoints"]["agencies"].endswith("/api/v1/agencies.json")
    assert idx["endpoints"]["coverage"].endswith("/api/v1/coverage.json")
    assert idx["endpoints"]["by_location"].endswith("/api/v1/by-location.json")
    assert idx["endpoints"]["features"].endswith("/api/v1/features.json")
    assert idx["endpoints"]["global_coverage"].endswith("/api/v1/global-coverage.json")
    assert "{agency_id}" in idx["endpoints"]["agency_detail"]
    assert idx["license"]


def test_build_api_returns_every_endpoint() -> None:
    api = build_api(
        _index(),
        agencies=[Agency("alpha", "Alpha", "https://example.org/a.zip")],
        states={"alpha": "California"},
        locations={
            "alpha": {
                "country": "US",
                "subdivision_code": "US-CA",
                "subdivision_name": "California",
            }
        },
        base_url="https://x",
        generated_at="t",
    )
    assert set(api) == {
        "index.json",
        "agencies.json",
        "leaderboard.json",
        "by-state.json",
        "by-location.json",
        "stats.json",
        "coverage.json",
    }
    # V1 count fields continue to describe all published rows. Score
    # aggregates use only the guarded producer/identity cohort and publish that
    # narrower denominator explicitly.
    assert api["stats.json"]["agency_count"] == 3
    assert api["stats.json"]["comparison_eligible_count"] == 1
    assert api["stats.json"]["average_score"] == 90.0
    states = {row["state"]: row for row in api["by-state.json"]["states"]}
    assert states["California"]["count"] == 1
    assert states["California"]["comparison_eligible_count"] == 1
    assert states["Unlocated"]["count"] == 2
    assert states["Unlocated"]["comparison_eligible_count"] == 0
    (country,) = api["by-location.json"]["countries"]
    assert country["count"] == 3
    assert country["comparison_eligible_count"] == 1
    api_rows = {row["id"]: row for row in api["agencies.json"]["agencies"]}
    assert api_rows["alpha"]["comparison_eligible"] is True
    assert api_rows["bravo"]["comparison_eligible"] is False
    assert api["agencies.json"]["comparison"] == api["stats.json"]["comparison"]
