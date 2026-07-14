"""Tests for the open national quality dataset builder."""

from __future__ import annotations

import csv
import io
from typing import Any

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.dataset import (
    COLUMNS,
    build_quality_dataset,
    national_summary,
    to_csv,
)
from scorecard_pipeline.validate import VALIDATOR_VERSION


def _history_point(
    date: str,
    grade: str,
    score: float,
    *,
    correctness: float,
    freshness: float,
    completeness: float,
    realtime: float | None = None,
    days_until_expiry: int | None = None,
    service_horizon_status: str = "within_review_threshold",
) -> dict[str, Any]:
    categories: dict[str, float] = {
        "correctness": correctness,
        "freshness": freshness,
        "completeness": completeness,
    }
    if realtime is not None:
        categories["realtime"] = realtime
    return {
        "date": date,
        "grade": grade,
        "score": score,
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": RUBRIC_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "feed_sha256": f"sha-{date}-{score}-{grade}",
        "categories": categories,
        "days_until_expiry": days_until_expiry,
        "service_horizon_status": service_horizon_status,
    }


def _sample_index() -> dict[str, Any]:
    return {
        "agencies": {
            "yolobus": {
                "name": "Yolobus",
                "history": [
                    _history_point(
                        "2026-05-01",
                        "C",
                        72.0,
                        correctness=70.0,
                        freshness=60.0,
                        completeness=80.0,
                        days_until_expiry=10,
                    ),
                    # Latest point: this is the one that should land in the row.
                    _history_point(
                        "2026-06-01",
                        "B",
                        85.0,
                        correctness=88.0,
                        freshness=90.0,
                        completeness=80.0,
                        realtime=82.0,
                        days_until_expiry=120,
                    ),
                ],
            },
            "unitrans": {
                "name": "Unitrans",
                "history": [
                    # No realtime feed -> realtime score absent.
                    _history_point(
                        "2026-06-02",
                        "A",
                        93.0,
                        correctness=95.0,
                        freshness=90.0,
                        completeness=94.0,
                        days_until_expiry=-5,
                    ),
                ],
            },
        }
    }


def test_rows_use_latest_history_point_only() -> None:
    dataset = build_quality_dataset(_sample_index())
    assert dataset["schema_version"] == "1.2"
    assert dataset["generated_fields"] == list(COLUMNS)
    rows = dataset["rows"]
    # Sorted by id: unitrans before yolobus.
    assert [r["id"] for r in rows] == ["unitrans", "yolobus"]

    yolo = rows[1]
    assert yolo == {
        "id": "yolobus",
        "name": "Yolobus",
        "date": "2026-06-01",
        "grade": "B",
        "score": 85.0,
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": RUBRIC_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "feed_sha256": "sha-2026-06-01-85.0-B",
        "comparison_eligible": True,
        "correctness": 88.0,
        "freshness": 90.0,
        "completeness": 80.0,
        "realtime": 82.0,
        "days_until_expiry": 120,
        "service_horizon_status": "within_review_threshold",
    }
    assert dataset["comparison"]["eligible_count"] == 1
    assert dataset["comparison"]["required_measured_categories"] == [
        "correctness",
        "freshness",
        "completeness",
        "realtime",
    ]
    # Unitrans publishes no realtime feed: realtime is None, not zero. This
    # synthetic tie selects the larger measured-category signature, so Unitrans
    # remains public but is marked outside that one homogeneous cohort.
    assert rows[0]["realtime"] is None
    assert rows[0]["comparison_eligible"] is False


def test_schema_version_override() -> None:
    dataset = build_quality_dataset(_sample_index(), schema_version="2.1")
    assert dataset["schema_version"] == "2.1"


def test_agencies_without_history_are_skipped() -> None:
    index = {
        "agencies": {
            "new": {"name": "Brand New Transit", "history": []},
            "real": {
                "name": "Real Transit",
                "history": [
                    _history_point(
                        "2026-06-01",
                        "A",
                        91.0,
                        correctness=90.0,
                        freshness=92.0,
                        completeness=91.0,
                        days_until_expiry=30,
                    )
                ],
            },
        }
    }
    rows = build_quality_dataset(index)["rows"]
    assert [r["id"] for r in rows] == ["real"]


def test_csv_round_trips_header_and_values() -> None:
    dataset = build_quality_dataset(_sample_index())
    text = to_csv(dataset)
    reader = list(csv.reader(io.StringIO(text)))

    assert reader[0] == list(COLUMNS)
    assert len(reader) == 1 + len(dataset["rows"])

    # Parse the data rows back into dicts and compare against the dataset rows.
    parsed = [dict(zip(COLUMNS, line, strict=True)) for line in reader[1:]]
    yolo = next(p for p in parsed if p["id"] == "yolobus")
    assert yolo["name"] == "Yolobus"
    assert yolo["grade"] == "B"
    assert yolo["score"] == "85.0"
    assert yolo["rubric_version"] == RUBRIC_VERSION
    assert yolo["scoring_profile_id"] == SCORING_PROFILE_ID
    assert yolo["scoring_profile_rubric_version"] == RUBRIC_VERSION
    assert yolo["validator_version"] == VALIDATOR_VERSION
    assert yolo["feed_sha256"] == "sha-2026-06-01-85.0-B"
    assert yolo["comparison_eligible"] == "True"
    assert yolo["realtime"] == "82.0"
    assert yolo["days_until_expiry"] == "120"
    assert yolo["service_horizon_status"] == "within_review_threshold"

    # Missing realtime renders as an empty cell, not "None".
    unitrans = next(p for p in parsed if p["id"] == "unitrans")
    assert unitrans["realtime"] == ""


def test_csv_escapes_commas_in_names() -> None:
    index = {
        "agencies": {
            "x": {
                "name": "Davis, CA Transit",
                "history": [
                    _history_point(
                        "2026-06-01",
                        "B",
                        80.0,
                        correctness=80.0,
                        freshness=80.0,
                        completeness=80.0,
                        days_until_expiry=5,
                    )
                ],
            }
        }
    }
    text = to_csv(build_quality_dataset(index))
    (parsed_row,) = list(csv.reader(io.StringIO(text)))[1:]
    assert parsed_row[COLUMNS.index("name")] == "Davis, CA Transit"


def test_national_summary_aggregates() -> None:
    summary = national_summary(build_quality_dataset(_sample_index()))
    assert summary["agency_count"] == 2
    # (85.0 + 93.0) / 2 = 89.0
    assert summary["average_score"] == 89.0
    assert summary["grade_distribution"] == {"A": 1, "B": 1, "C": 0, "D": 0, "F": 0}
    # yolobus (120) current, unitrans (-5) expired -> 1 of 2.
    assert summary["pct_current"] == 50.0


def test_national_summary_unknown_expiry_is_not_current() -> None:
    index = {
        "agencies": {
            "a": {
                "name": "A",
                "history": [
                    _history_point(
                        "2026-06-01",
                        "A",
                        90.0,
                        correctness=90.0,
                        freshness=90.0,
                        completeness=90.0,
                        days_until_expiry=None,
                    )
                ],
            }
        }
    }
    summary = national_summary(build_quality_dataset(index))
    assert summary["pct_current"] == 0.0


def test_empty_index_yields_empty_rows_and_zeroed_summary() -> None:
    dataset = build_quality_dataset({})
    assert dataset["rows"] == []
    assert dataset["generated_fields"] == list(COLUMNS)
    assert dataset["comparison"]["eligible_count"] == 0

    # CSV is just the header row.
    assert to_csv(dataset).strip() == ",".join(COLUMNS)

    summary = national_summary(dataset)
    assert summary == {
        "agency_count": 0,
        "average_score": None,
        "grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
        "pct_current": 0.0,
    }


def test_legacy_history_derives_distant_horizon_for_first_api_publish() -> None:
    index = _sample_index()
    latest = index["agencies"]["unitrans"]["history"][-1]
    latest["date"] = "2026-07-13"
    latest["days_until_expiry"] = 26_834
    del latest["service_horizon_status"]
    row = build_quality_dataset(index)["rows"][0]
    assert row["days_until_expiry"] == 26_834
    assert row["service_horizon_status"] == "unusually_distant"


def test_legacy_history_without_date_or_expiry_stays_unknown() -> None:
    index = _sample_index()
    latest = index["agencies"]["unitrans"]["history"][-1]
    latest["date"] = None
    latest["days_until_expiry"] = None
    del latest["service_horizon_status"]
    row = build_quality_dataset(index)["rows"][0]
    assert row["service_horizon_status"] == "unknown"
