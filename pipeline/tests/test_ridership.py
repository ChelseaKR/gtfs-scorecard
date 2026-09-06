"""Tests for ridership-weighted impact (ridership.py)."""

from __future__ import annotations

import json
from pathlib import Path

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.cli import main
from scorecard_pipeline.ridership import (
    annual_trips_for,
    load_ridership,
    parse_ridership_csv,
    weighted_impact,
)
from scorecard_pipeline.validate import VALIDATOR_VERSION


def test_parse_finds_columns_by_header_and_sums_per_id() -> None:
    csv_text = (
        "Agency,NTD ID,Mode,UPT\n"
        "Alpha,90001,MB,1000\n"
        "Alpha,90001,DR,500\n"  # same reporter, second mode -> summed
        "Beta,90002,MB,2000\n"
    )
    rides = parse_ridership_csv(csv_text)
    assert rides == {"90001": 1500, "90002": 2000}


def test_parse_handles_commas_decimals_and_padding() -> None:
    csv_text = 'NTD ID,Unlinked Passenger Trips\n"0090001","1,234.0"\n90002,abc\n'
    rides = parse_ridership_csv(csv_text)
    # Thousands separator and decimal parsed; non-numeric row skipped; id digits kept.
    assert rides == {"90001": 1234}


def test_parse_returns_empty_when_columns_absent() -> None:
    assert parse_ridership_csv("Agency,State\nAlpha,CA\n") == {}
    assert parse_ridership_csv("") == {}


def test_weighted_impact_math() -> None:
    records = [
        {"ntd_id": "90001", "score": 90.0, "grade": "A", "expiry_status": "current"},
        {"ntd_id": "90002", "score": 50.0, "grade": "F", "expiry_status": "lapsed"},
        {"ntd_id": "99999", "score": 70.0, "grade": "C", "expiry_status": "current"},  # no rides
        {"ntd_id": "", "score": 80.0, "grade": "B", "expiry_status": "current"},  # no NTD id
    ]
    ridership = {"90001": 1_000_000, "90002": 100_000}
    imp = weighted_impact(records, ridership)
    assert imp["matched_agencies"] == 2
    assert imp["total_agencies"] == 4
    assert imp["matched_ntd_reporters"] == 2
    assert imp["total_feed_records"] == 4
    assert imp["duplicate_ntd_ids_excluded"] == []
    assert imp["total_annual_trips"] == 1_100_000
    # Only the lapsed feed's trips count as expired.
    assert imp["trips_on_expired_feeds"] == 100_000
    assert imp["expired_trips_pct"] == 9.1
    # Weighted by trips: (90*1e6 + 50*1e5) / 1.1e6 = 86.4
    assert imp["weighted_average_score"] == 86.4
    assert imp["trips_by_grade"]["A"] == 1_000_000
    assert imp["trips_by_grade"]["F"] == 100_000


def test_weighted_impact_empty_when_no_matches() -> None:
    records = [{"ntd_id": "90001", "score": 90.0, "grade": "A", "expiry_status": "current"}]
    imp = weighted_impact(records, {})  # no ridership data committed yet
    assert imp["matched_agencies"] == 0
    assert imp["total_annual_trips"] == 0
    assert imp["weighted_average_score"] is None
    # Both shares share a denominator of zero, so both are absent. This
    # asserted 0.0, which reads as a measured "no expired trips".
    assert imp["expired_trips_pct"] is None


def test_weighted_impact_quarantines_duplicate_ntd_reporters() -> None:
    records = [
        {
            "id": "alpha_local",
            "ntd_id": "90001",
            "score": 90.0,
            "grade": "A",
            "expiry_status": "current",
        },
        {
            "id": "alpha_regional",
            "ntd_id": "90001",
            "score": 50.0,
            "grade": "F",
            "expiry_status": "lapsed",
        },
        {
            "id": "beta",
            "ntd_id": "90002",
            "score": 80.0,
            "grade": "B",
            "expiry_status": "current",
        },
    ]

    impact = weighted_impact(records, {"90001": 1_000_000, "90002": 25_000})

    # Alpha's UPT is not guessed onto either of its two feed rows and therefore
    # cannot be counted twice. Only the unique Beta match contributes.
    assert impact["total_annual_trips"] == 25_000
    assert impact["matched_ntd_reporters"] == 1
    assert impact["duplicate_ntd_reporter_count"] == 1
    assert impact["duplicate_feed_records_excluded"] == 2
    assert impact["duplicate_ntd_ids_excluded"] == ["90001"]
    assert impact["trips_by_grade"]["B"] == 25_000
    assert impact["trips_by_grade"]["A"] == 0
    assert impact["trips_by_grade"]["F"] == 0


def test_weighted_impact_honors_duplicates_found_before_cohort_filtering() -> None:
    records = [
        {
            "id": "eligible-sibling",
            "ntd_id": "00007",
            "score": 90.0,
            "grade": "A",
            "expiry_status": "current",
        }
    ]

    impact = weighted_impact(records, {"7": 1_000_000}, quarantined_ntd_ids={"00007"})

    # A second registry sibling was filtered out before this call. Its reporter
    # id still quarantines the surviving row, and zero-padding cannot evade it.
    assert impact["matched_ntd_reporters"] == 0
    assert impact["duplicate_ntd_ids_excluded"] == ["7"]
    assert impact["duplicate_feed_records_excluded"] == 1
    assert impact["total_annual_trips"] == 0


def test_load_ridership_returns_none_when_file_absent(tmp_path: Path) -> None:
    assert load_ridership(tmp_path / "does-not-exist.csv") is None


def test_load_ridership_parses_present_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "ntd-ridership.csv"
    csv_path.write_text("NTD ID,UPT\n90001,1000\n90002,2000\n")
    assert load_ridership(csv_path) == {"90001": 1000, "90002": 2000}


def test_load_ridership_empty_file_is_empty_dict_not_none(tmp_path: Path) -> None:
    # "file present but matched nothing" must stay distinct from "no file".
    csv_path = tmp_path / "ntd-ridership.csv"
    csv_path.write_text("Agency,State\nAlpha,CA\n")
    assert load_ridership(csv_path) == {}


def test_annual_trips_for_resolves_matches_and_gaps() -> None:
    ridership = {"90001": 1_000_000}
    assert annual_trips_for({"ntd_id": "90001"}, ridership) == 1_000_000
    # Unmatched id, missing id, and absent map all yield None, never 0.
    assert annual_trips_for({"ntd_id": "99999"}, ridership) is None
    assert annual_trips_for({"ntd_id": ""}, ridership) is None
    assert annual_trips_for({}, ridership) is None
    assert annual_trips_for({"ntd_id": "90001"}, None) is None
    assert annual_trips_for({"ntd_id": "90001"}, {}) is None
    assert annual_trips_for({"ntd_id": "00007"}, {"7": 123}) == 123


def test_ntd_ridership_excludes_normalized_reader_profile(isolated_repo_root: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    isolated_repo_root.mkdir(parents=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: raw\n"
        "    name: Raw Transit\n"
        "    static_gtfs_url: https://example.org/raw.zip\n"
        "    ntd_id: '90001'\n"
        "  - id: normalized\n"
        "    name: Normalized Transit\n"
        "    static_gtfs_url: https://example.org/normalized.zip\n"
        "    ntd_id: '90002'\n"
    )

    def artifact(agency_id: str, *, normalized: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "agency": {"id": agency_id, "name": f"{agency_id.title()} Transit"},
            "snapshot_date": "2026-07-16",
            "rubric_version": RUBRIC_VERSION,
            "scoring_profile": {
                "id": SCORING_PROFILE_ID,
                "rubric_version": RUBRIC_VERSION,
            },
            "validator_version": VALIDATOR_VERSION,
            "feed": {
                "static_url": f"https://example.org/{agency_id}.zip",
                "sha256": ("a" if agency_id == "raw" else "b") * 64,
            },
            "overall": {"score": 80.0, "grade": "B"},
            "categories": {
                "correctness": {"status": "measured", "score": 80.0},
                "freshness": {
                    "status": "measured",
                    "score": 80.0,
                    "details": {"days_until_expiry": 90},
                },
                "completeness": {"status": "measured", "score": 80.0},
                "realtime": {"status": "not_yet_measured"},
            },
        }
        if normalized:
            payload["fetch"] = {"reader_archive_profile": "flat-single-root-v1"}
        return payload

    for agency_id, normalized in (("raw", False), ("normalized", True)):
        agency_dir = isolated_repo_root / "data" / "artifacts" / agency_id
        agency_dir.mkdir(parents=True)
        (agency_dir / "latest.json").write_text(
            json.dumps(artifact(agency_id, normalized=normalized))
        )
    ridership = isolated_repo_root / "ridership.csv"
    ridership.write_text("NTD ID,UPT\n90001,1000\n90002,2000\n")

    assert main(["ntd-ridership", "--csv", str(ridership)]) == 0
    impact = json.loads(capsys.readouterr().out)

    assert impact["total_feed_records"] == 1
    assert impact["matched_ntd_reporters"] == 1
    assert impact["total_annual_trips"] == 1000
