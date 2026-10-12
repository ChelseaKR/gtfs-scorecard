"""Rescoring stored earlier-rubric records under the current rubric (offline)."""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.comparisons import current_producer_contract_suffix
from scorecard_pipeline.config import Agency
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.gtfs import FeedDates
from scorecard_pipeline.metrics import CategoryResult, Finding, correctness, freshness
from scorecard_pipeline.national_trend import as_of_points
from scorecard_pipeline.publish import _history_entry, backfill_index_history, build_artifact
from scorecard_pipeline.rescore_history import (
    RESCORED_HISTORY_SCHEMA,
    ROW_COLUMNS,
    build_rescored_history,
    native_completeness_scores,
    reproduces_native,
    rescore_artifact,
    rescored_history_rows,
    splice_rescored,
)
from scorecard_pipeline.score import build_scorecard
from scorecard_pipeline.validate import VALIDATOR_VERSION, NoticeGroup, ValidationReport

AGENCY = Agency(
    id="unitrans",
    name="Unitrans",
    static_gtfs_url="https://example.org/gtfs.zip",
    license_note="test",
)
SHA = "b" * 64


def _completeness(score: float, *, missing_headsigns: int = 0) -> CategoryResult:
    findings = []
    if missing_headsigns:
        findings.append(
            Finding(
                code="scorecard_missing_headsigns",
                severity="WARNING",
                count=missing_headsigns,
                what="w",
                why="y",
                fix="f",
                effort="e",
                deduction=3.0,
            )
        )
    return CategoryResult(
        name="completeness",
        score=score,
        summary="s",
        findings=findings,
        details={
            "stops": 10,
            "trips": 40,
            "mixed_case_stop_name_pct": 100.0,
            "unmeasured_components": [],
            "fare_free": False,
        },
    )


def native_artifact(
    day: dt.date,
    *,
    completeness_score: float = 71.37,
    realtime: float | None = 88.81,
    missing_headsigns: int = 0,
) -> dict[str, Any]:
    """A record exactly as the current pipeline publishes one."""
    report = ValidationReport(
        validator_version=VALIDATOR_VERSION,
        notices=[
            NoticeGroup("mixed_case_recommended_field", "WARNING", 120),
            NoticeGroup("unusable_trip", "ERROR", 2),
            NoticeGroup("feed_info_lang_and_agency_lang_mismatch", "INFO", 1),
        ],
    )
    dates = FeedDates(
        has_feed_info=True,
        feed_publisher_name=None,
        feed_version="v1",
        feed_start_date=dt.date(2026, 1, 1),
        feed_end_date=dt.date(2026, 12, 1),
        last_service_date=dt.date(2026, 12, 1),
        seasonal_boundary=False,
    )
    fresh = freshness(dates, day)
    assert fresh is not None
    cats = [
        correctness(report),
        fresh,
        _completeness(completeness_score, missing_headsigns=missing_headsigns),
    ]
    if realtime is not None:
        cats.append(CategoryResult(name="realtime", score=realtime, summary="s"))
    fetch = FetchResult(
        agency_id=AGENCY.id,
        path=Path("/tmp/gtfs.zip"),
        url=AGENCY.static_gtfs_url,
        fetched_date=day,
        sha256=SHA,
        size_bytes=1024,
        reused=False,
    )
    artifact = build_artifact(
        AGENCY, fetch, build_scorecard(cats), dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
    )
    artifact["validator_version"] = VALIDATOR_VERSION
    return artifact


def as_rubric(artifact: dict[str, Any], version: str) -> dict[str, Any]:
    old = copy.deepcopy(artifact)
    old["rubric_version"] = version
    old["scoring_profile"] = {"id": f"gtfs-scorecard-{version}", "rubric_version": version}
    return old


def test_native_record_reproduces_exactly() -> None:
    """The control: the method returns what the current rubric published."""
    artifact = native_artifact(dt.date(2026, 10, 5))
    assert reproduces_native(artifact) is True


def test_native_reproduction_detects_a_difference() -> None:
    artifact = native_artifact(dt.date(2026, 10, 5))
    artifact["overall"]["score"] = round(artifact["overall"]["score"] + 0.1, 1)
    assert reproduces_native(artifact) is False


def test_earlier_rubric_record_is_rescored_onto_the_current_contract() -> None:
    native = native_artifact(dt.date(2026, 9, 20))
    old = as_rubric(native, "1.3")
    result = rescore_artifact(old, {})
    assert result.reason is None
    assert result.completeness_source == "stored_headsigns_complete"
    row = result.row
    assert row is not None
    assert row["score"] == native["overall"]["score"]
    assert row["rescored_from_rubric"] == "1.3"
    assert row["measured"] == ["correctness", "freshness", "completeness", "realtime"]


def test_freshness_is_recomputed_as_of_the_record_date() -> None:
    """A stale stored freshness reading is replaced by the current rule's."""
    native = native_artifact(dt.date(2026, 9, 20))
    old = as_rubric(native, "1.3")
    old["categories"]["freshness"]["score"] = 12.3
    row = rescore_artifact(old, {}).row
    assert row is not None
    assert row["categories"]["freshness"] == native["categories"]["freshness"]["score"]


def test_missing_headsign_record_needs_native_bytes_or_is_left_out() -> None:
    old = as_rubric(native_artifact(dt.date(2026, 9, 20), missing_headsigns=5), "1.3")
    result = rescore_artifact(old, {})
    assert result.row is None
    assert result.reason == "completeness_headsign_credit_needs_feed_bytes"

    # The same bytes scored natively under the current rubric settle it.
    newer = native_artifact(dt.date(2026, 10, 3), completeness_score=80.0)
    native = native_completeness_scores([newer])
    result = rescore_artifact(old, native)
    assert result.completeness_source == "same_feed_bytes_native"
    assert result.row is not None
    assert result.row["categories"]["completeness"] == 80.0


def test_disagreeing_native_bytes_are_not_used() -> None:
    a = native_artifact(dt.date(2026, 10, 3), completeness_score=80.0)
    b = native_artifact(dt.date(2026, 10, 4), completeness_score=81.0)
    assert native_completeness_scores([a, b]) == {}


def test_realtime_before_rubric_1_2_is_not_rescored() -> None:
    old = as_rubric(native_artifact(dt.date(2026, 7, 1)), "1.1")
    assert rescore_artifact(old, {}).reason == "realtime_rule_predates_1_2"
    no_rt = as_rubric(native_artifact(dt.date(2026, 7, 1), realtime=None), "1.1")
    assert rescore_artifact(no_rt, {}).row is not None


def test_incomplete_correctness_inputs_are_not_rescored() -> None:
    old = as_rubric(native_artifact(dt.date(2026, 9, 20)), "1.3")
    old["categories"]["correctness"]["findings"].pop()
    assert rescore_artifact(old, {}).reason == "correctness_inputs_incomplete"


def test_record_without_provenance_is_not_rescored() -> None:
    old = as_rubric(native_artifact(dt.date(2026, 6, 12)), "1.3")
    old["rubric_version"] = None
    assert rescore_artifact(old, {}).reason == "no_rubric_provenance"


def _write(root: Path, artifact: dict[str, Any]) -> None:
    path = root / AGENCY.id / f"{artifact['snapshot_date']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact))


def test_build_and_splice_extend_the_contract_suffix(tmp_path: Path) -> None:
    days = [dt.date(2026, 9, d) for d in (28, 29, 30)] + [dt.date(2026, 10, 2)]
    records = [as_rubric(native_artifact(day), "1.3") for day in days[:3]]
    records.append(native_artifact(days[3]))
    # The middle 1.3 record cannot be rescored.
    records[1]["categories"]["correctness"]["findings"].pop()
    for record in records:
        _write(tmp_path, record)

    document = build_rescored_history(tmp_path, [AGENCY.id])
    assert document["schema"] == RESCORED_HISTORY_SCHEMA
    assert document["reproduction"]["native_records_checked"] == 1
    assert document["reproduction"]["native_records_exact"] == 1
    assert document["coverage"]["records_rescored"] == 2
    assert document["coverage"]["not_rescored_by_reason"] == {"correctness_inputs_incomplete": 1}
    control = document["reproduction"]["native_average_by_date"]["2026-10-02"]
    assert control["rescored_average"] == control["published_average"]

    history = [_history_entry(record) for record in records]
    rows = rescored_history_rows(json.loads(json.dumps(document)))[AGENCY.id]
    spliced = splice_rescored(history, rows)
    # The unrescorable 2026-09-29 row still ends the suffix: nothing is
    # carried across a record that could not be rescored.
    assert [r["date"] for r in current_producer_contract_suffix(spliced)] == [
        "2026-09-30",
        "2026-10-02",
    ]
    points = as_of_points({"agencies": {AGENCY.id: {"history": spliced[2:]}}})
    assert [p["rescored_agency_count"] for p in points] == [1, 0]


def test_rescored_rows_for_another_rubric_are_ignored() -> None:
    document = {
        "schema": RESCORED_HISTORY_SCHEMA,
        "rubric_version": "9.9",
        "scoring_profile_id": "gtfs-scorecard-9.9",
        "validator_version": VALIDATOR_VERSION,
        "columns": list(ROW_COLUMNS),
        "agencies": {"x": [["2026-09-01", 70.0, 30, "1.3", "raw-v1", 90.0, 50.0, 62.4, None]]},
    }
    assert rescored_history_rows(document) == {}
    document.update(rubric_version=RUBRIC_VERSION, scoring_profile_id=SCORING_PROFILE_ID)
    row = rescored_history_rows(document)["x"]["2026-09-01"]
    assert row["score"] == 70.0
    assert row["grade"] == "C"
    # An unmeasured category stays absent; it is not turned into a number.
    assert row["categories"] == {"correctness": 90.0, "freshness": 50.0, "completeness": 62.4}


def test_rescored_row_without_a_score_contributes_nothing() -> None:
    """Absence stays absent: no row is invented for a missing score."""
    document = {
        "schema": RESCORED_HISTORY_SCHEMA,
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "validator_version": VALIDATOR_VERSION,
        "columns": list(ROW_COLUMNS),
        "agencies": {"x": [["2026-09-01", None, 30, "1.3", "raw-v1", 90.0, 50.0, 62.4, None]]},
    }
    assert rescored_history_rows(document) == {}


def test_backfill_restores_dropped_rows_only(tmp_path: Path) -> None:
    records = [native_artifact(dt.date(2026, 10, d)) for d in (1, 2, 3, 4)]
    for record in records:
        _write(tmp_path, record)
    # A mirrored record newer than the index tail and one under the wrong id.
    _write(tmp_path, native_artifact(dt.date(2026, 10, 9)))
    stray = native_artifact(dt.date(2026, 9, 30))
    stray["agency"]["id"] = "someone-else"
    _write(tmp_path, stray)

    kept = _history_entry(records[0])
    kept["score"] = 1.0  # an existing row is never replaced
    index = {"agencies": {AGENCY.id: {"history": [kept, _history_entry(records[3])]}}}
    counts = backfill_index_history(index, tmp_path)

    history = index["agencies"][AGENCY.id]["history"]
    assert [row["date"] for row in history] == [
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
    ]
    assert history[0]["score"] == 1.0
    assert counts["rows_added"] == 2
    assert counts["skipped"] == {"unreadable": 0, "mismatched": 1, "after_tail": 1}


def test_render_reads_rescored_file_and_keeps_native_points_unchanged(tmp_path: Path) -> None:
    from scorecard_pipeline.render_site import _rescored_trend

    days = [dt.date(2026, 9, 29), dt.date(2026, 9, 30), dt.date(2026, 10, 2)]
    records = [as_rubric(native_artifact(day), "1.3") for day in days[:2]]
    records.append(native_artifact(days[2]))
    for record in records:
        _write(tmp_path, record)
    document = build_rescored_history(tmp_path, [AGENCY.id])
    (tmp_path / "rescored-history.json").write_text(json.dumps(document))
    index = {"agencies": {AGENCY.id: {"history": [_history_entry(r) for r in records]}}}

    native_points = as_of_points(
        {
            "agencies": {
                AGENCY.id: {
                    "history": current_producer_contract_suffix(
                        index["agencies"][AGENCY.id]["history"]
                    )
                }
            }
        }
    )
    trend = _rescored_trend(tmp_path, index, {AGENCY.id}, native_points)
    assert trend is not None
    assert [p["date"] for p in trend["points"]] == ["2026-09-29", "2026-09-30", "2026-10-02"]
    assert [p["rescored_agency_count"] for p in trend["points"]] == [1, 1, 0]
    assert trend["native_points_since"] == "2026-10-02"
    assert trend["panel_feed_count"] == 1
    assert trend["reproduces_native_exactly"] is True
    # The index rows themselves are not rewritten.
    assert index["agencies"][AGENCY.id]["history"][0]["rubric_version"] == "1.3"
    # No file, no rescored block.
    (tmp_path / "rescored-history.json").unlink()
    assert _rescored_trend(tmp_path, index, {AGENCY.id}, native_points) is None
