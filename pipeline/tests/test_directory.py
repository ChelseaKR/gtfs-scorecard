"""Tests for the scorecard directory: size tiers and guarded rollups."""

from __future__ import annotations

from typing import Any

import pytest

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.directory import build_directory, size_tier
from scorecard_pipeline.location import COUNTRY_NAMES
from scorecard_pipeline.validate import VALIDATOR_VERSION


def _rec(
    id_: str,
    score: float,
    grade: str,
    *,
    state: str = "California",
    stops: int = 50,
    expiry: str = "current",
    days: int = 120,
    fix: str = "x",
    country: str = "US",
    subdivision_code: str = "US-CA",
    subdivision_name: str = "California",
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": id_.title(),
        "date": "2026-07-01",
        "grade": grade,
        "score": score,
        "correctness": score,
        "freshness": score,
        "completeness": score,
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": RUBRIC_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "feed_sha256": f"sha-{id_}",
        "state": state,
        "country": country,
        "subdivision_code": subdivision_code,
        "subdivision_name": subdivision_name,
        "stops": stops,
        "expiry_status": expiry,
        "days_until_expiry": days,
        "top_fix": fix,
        "scorecard_url": f"/agency/{id_}/",
    }


def test_size_tier_breakpoints() -> None:
    assert size_tier(0) == "small"
    assert size_tier(99) == "small"
    assert size_tier(100) == "medium"
    assert size_tier(999) == "medium"
    assert size_tier(1000) == "large"
    assert size_tier(None) == "unknown"


def test_directory_suppresses_individual_percentiles() -> None:
    recs = [_rec("a", 90, "A"), _rec("b", 70, "C"), _rec("c", 50, "F")]
    out = build_directory(recs, "2026-06-19T00:00:00+00:00")
    assert all(record["national_percentile"] is None for record in out["agencies"])
    assert all(record["peer_percentile"] is None for record in out["agencies"])
    assert all(record["comparison_eligible"] is True for record in out["agencies"])
    assert out["summary"]["comparison"]["individual_percentiles_published"] is False


def test_size_tier_remains_available_without_peer_ranking() -> None:
    recs = [
        _rec("small-top", 80, "B", stops=40),
        _rec("small-mid", 60, "D", stops=40),
        _rec("big", 95, "A", stops=5000),
    ]
    out = build_directory(recs, "t")
    by_id = {r["id"]: r for r in out["agencies"]}
    assert by_id["small-top"]["size_tier"] == "small"
    assert by_id["big"]["size_tier"] == "large"
    assert by_id["small-top"]["peer_percentile"] is None
    assert by_id["small-top"]["national_percentile"] is None


def test_directory_carries_a_data_license() -> None:
    out = build_directory([_rec("a", 90, "A")], "t")
    assert out["license"] == "CC-BY-4.0"
    assert "gtfsscorecard.org" in out["attribution"]


def test_summary_counts_grades_and_expiry() -> None:
    recs = [
        _rec("a", 95, "A"),
        _rec("b", 85, "B"),
        _rec("c", 40, "F", expiry="lapsed", days=-10),
        _rec("d", 30, "F", expiry="stale", days=-500),
        _rec("e", 75, "C", expiry="expiring_soon", days=12),
    ]
    summary = build_directory(recs, "t")["summary"]
    assert summary["agencies"] == 5
    assert summary["feed_records"] == 5
    assert summary["scored_feed_records"] == 5
    assert summary["comparison_eligible_count"] == 4
    assert summary["grade_distribution"] == {"A": 1, "B": 1, "C": 1, "D": 0, "F": 1}
    assert summary["expired"] == {"lapsed": 1, "stale": 1, "total": 2}
    assert summary["expiring_soon"] == 1
    assert summary["median_score"] == 80
    assert summary["comparison"]["exclusion_counts"] == {"service_data_long_expired": 1}
    by_id = {record["id"]: record for record in build_directory(recs, "t")["agencies"]}
    assert by_id["d"]["comparison_eligible"] is False
    assert all(
        by_id[record_id]["comparison_eligible"] is True for record_id in ("a", "b", "c", "e")
    )


def test_state_rollup_sorted_by_count_and_buckets_unlocated() -> None:
    recs = [
        _rec("a", 90, "A", state="California"),
        _rec("b", 80, "B", state="California"),
        _rec("c", 70, "C", state="Vermont"),
        _rec("d", 60, "D", state=""),  # unlocated
    ]
    states = build_directory(recs, "t")["summary"]["states"]
    assert states[0]["state"] == "California"
    assert states[0]["agencies"] == 2
    assert states[0]["comparison_eligible_count"] == 2
    names = {s["state"] for s in states}
    assert "Unlocated" in names
    ca = next(s for s in states if s["state"] == "California")
    assert ca["average_score"] == 85.0


def test_country_rollup_nests_subdivisions_without_changing_legacy_states() -> None:
    recs = [
        _rec("ca", 90, "A", state="California"),
        _rec(
            "on",
            70,
            "C",
            state="",
            country="CA",
            subdivision_code="CA-ON",
            subdivision_name="Ontario",
        ),
        _rec(
            "unknown",
            60,
            "D",
            state="",
            country="CA",
            subdivision_code="",
            subdivision_name="",
        ),
    ]
    summary = build_directory(recs, "t")["summary"]
    countries = {row["country_code"]: row for row in summary["countries"]}
    assert countries["US"]["country_name"] == "United States"
    assert countries["CA"]["country_name"] == "Canada"
    assert countries["CA"]["agencies"] == 2
    subdivisions = {row["subdivision_code"]: row for row in countries["CA"]["subdivisions"]}
    assert subdivisions["CA-ON"]["subdivision_name"] == "Ontario"
    assert subdivisions[None]["subdivision_name"] == "Unlocated"
    assert summary["states"] == [
        {
            "state": "Canada",
            "agencies": 2,
            "feed_records": 2,
            "comparison_eligible_count": 2,
            "average_score": 65.0,
            "grade_distribution": {"A": 0, "B": 0, "C": 1, "D": 1, "F": 0},
            "expired": 0,
        },
        {
            "state": "California",
            "agencies": 1,
            "feed_records": 1,
            "comparison_eligible_count": 1,
            "average_score": 90.0,
            "grade_distribution": {"A": 1, "B": 0, "C": 0, "D": 0, "F": 0},
            "expired": 0,
        },
    ]


def test_country_rollup_defaults_historical_country_to_us() -> None:
    legacy = _rec("legacy", 80, "B")
    del legacy["country"]

    countries = build_directory([legacy], "t")["summary"]["countries"]

    assert countries[0]["country_code"] == "US"
    assert countries[0]["country_name"] == "United States"


def test_configured_non_us_country_keeps_legacy_place_rollup_findable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(COUNTRY_NAMES, "GB", "United Kingdom")
    summary = build_directory(
        [
            _rec(
                "eng",
                80,
                "B",
                state="",
                country="GB",
                subdivision_code="GB-ENG",
                subdivision_name="England",
            )
        ],
        "t",
    )["summary"]
    assert summary["states"][0]["state"] == "United Kingdom"
    assert summary["countries"][0]["country_name"] == "United Kingdom"


def test_records_without_a_score_remain_listed_but_not_aggregated() -> None:
    recs = [_rec("a", 90, "A")]
    recs.append({**_rec("b", 0, "F"), "score": None})
    out = build_directory(recs, "t")
    by_id = {r["id"]: r for r in out["agencies"]}
    assert by_id["b"]["national_percentile"] is None
    assert by_id["b"]["peer_percentile"] is None
    assert out["summary"]["feed_records"] == 2
    assert out["summary"]["scored_feed_records"] == 1
    assert out["summary"]["comparison_eligible_count"] == 1
    assert out["summary"]["comparison"]["exclusion_counts"]["score_not_measured"] == 1
