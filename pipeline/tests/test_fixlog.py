"""Tests for fix receipts: dated, durable records of cleared findings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.fetch import (
    FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE,
    RAW_READER_ARCHIVE_PROFILE,
)
from scorecard_pipeline.fixlog import (
    diff_receipts,
    finding_codes,
    load_fixlog,
    merge_receipts,
    reconcile_receipts,
)
from scorecard_pipeline.validate import VALIDATOR_VERSION


def _artifact(date: str, *codes: tuple[str, str], measured: bool = True) -> dict[str, Any]:
    return {
        "snapshot_date": date,
        "agency": {"id": "demo", "name": "Demo Transit"},
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile": {
            "id": SCORING_PROFILE_ID,
            "rubric_version": RUBRIC_VERSION,
        },
        "validator_version": VALIDATOR_VERSION,
        "categories": {
            "correctness": {
                "status": "measured" if measured else "skipped",
                "findings": [{"code": c, "what": w} for c, w in codes],
            }
        },
    }


def test_receipt_records_both_dates_and_prior_wording() -> None:
    prev = _artifact("2026-06-30", ("expired_calendar", "3 calendars expired."))
    cur = _artifact("2026-07-01")
    receipts = diff_receipts(prev, cur)
    assert receipts == [
        {
            "code": "expired_calendar",
            "what": "3 calendars expired.",
            "last_seen": "2026-06-30",
            "cleared": "2026-07-01",
            "producer_contract": {
                "rubric_version": RUBRIC_VERSION,
                "scoring_profile_id": SCORING_PROFILE_ID,
                "scoring_profile_rubric_version": RUBRIC_VERSION,
                "validator_version": VALIDATOR_VERSION,
                "reader_archive_profile": RAW_READER_ARCHIVE_PROFILE,
                "measured_categories": ["correctness"],
            },
        }
    ]


def test_no_receipt_without_previous_artifact_or_when_still_present() -> None:
    cur = _artifact("2026-07-01", ("x", "still here"))
    assert diff_receipts(None, cur) == []
    prev = _artifact("2026-06-30", ("x", "still here"))
    assert diff_receipts(prev, cur) == []


def test_unmeasured_category_never_yields_a_receipt() -> None:
    # A category that went unmeasured (fetch failed, RT down) must not read as
    # "everything in it was fixed". The finding is invisible today, not fixed,
    # and this is a permanent record.
    prev = _artifact("2026-06-30", ("x", "w"))
    cur = _artifact("2026-07-01", measured=False)
    assert finding_codes(prev) == {"x": "w"}
    assert finding_codes(cur) == {}
    assert diff_receipts(prev, cur) == []


def test_methodology_change_never_yields_a_receipt() -> None:
    prev = _artifact("2026-06-30", ("x", "w"))
    prev["rubric_version"] = "older"
    cur = _artifact("2026-07-01")
    assert diff_receipts(prev, cur) == []


def test_reader_archive_profile_change_never_yields_a_receipt() -> None:
    prev = _artifact("2026-06-30", ("x", "w"))
    cur = _artifact("2026-07-01")
    cur["fetch"] = {"reader_archive_profile": FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE}
    assert diff_receipts(prev, cur) == []


def test_merge_is_idempotent_and_keeps_history() -> None:
    old = [{"code": "a", "what": "w1", "last_seen": "2026-06-01", "cleared": "2026-06-02"}]
    new = [
        {"code": "a", "what": "w1", "last_seen": "2026-06-01", "cleared": "2026-06-02"},
        {"code": "a", "what": "w1 again", "last_seen": "2026-06-10", "cleared": "2026-06-11"},
    ]
    merged = merge_receipts(old, new)
    # Same (cleared, code) dedupes; a later re-clear of the same code is distinct.
    assert len(merged) == 2
    assert merge_receipts(merged, new) == merged
    # Oldest first, so the log reads as a history.
    assert merged[0]["cleared"] == "2026-06-02"


def test_legacy_receipt_without_dated_evidence_fails_closed() -> None:
    old = [{"code": "gone", "what": "w", "last_seen": "2025-01-01", "cleared": "2025-01-02"}]
    assert reconcile_receipts(old, {}) == []


def test_legacy_receipt_is_upgraded_only_when_artifacts_reproduce_it() -> None:
    prev = _artifact("2026-06-30", ("x", "The original wording."))
    cur = _artifact("2026-07-01")
    legacy = [
        {
            "code": "x",
            "what": "untrusted stale wording",
            "last_seen": "2026-06-30",
            "cleared": "2026-07-01",
        }
    ]
    reconciled = reconcile_receipts(
        legacy,
        {"2026-06-30": prev, "2026-07-01": cur},
    )
    assert reconciled == diff_receipts(prev, cur)
    assert reconciled[0]["what"] == "The original wording."
    assert "producer_contract" in reconciled[0]


def test_legacy_receipt_is_dropped_across_producer_change() -> None:
    prev = _artifact("2026-06-30", ("x", "w"))
    cur = _artifact("2026-07-01")
    cur["validator_version"] = "different"
    legacy = [{"code": "x", "what": "w", "last_seen": "2026-06-30", "cleared": "2026-07-01"}]
    assert reconcile_receipts(legacy, {"2026-06-30": prev, "2026-07-01": cur}) == []


def test_provenance_receipt_survives_pruned_dated_artifacts() -> None:
    prev = _artifact("2026-06-30", ("x", "w"))
    cur = _artifact("2026-07-01")
    receipt = diff_receipts(prev, cur)
    assert reconcile_receipts(receipt, {}) == receipt


def test_available_artifact_must_match_persisted_receipt_contract() -> None:
    prev = _artifact("2026-06-30", ("x", "w"))
    cur = _artifact("2026-07-01")
    receipt = diff_receipts(prev, cur)
    cur["rubric_version"] = "new-rubric"
    assert reconcile_receipts(receipt, {"2026-07-01": cur}) == []


def test_load_fixlog_missing_or_bad_file(tmp_path: Path) -> None:
    assert load_fixlog(tmp_path) == []
    (tmp_path / "fixlog.json").write_text("not json")
    assert load_fixlog(tmp_path) == []
    (tmp_path / "fixlog.json").write_text(json.dumps({"receipts": [{"code": "a"}, "junk"]}))
    assert load_fixlog(tmp_path) == []


def test_load_fixlog_reconciles_legacy_receipt_from_local_evidence(tmp_path: Path) -> None:
    agency_dir = tmp_path / "demo"
    agency_dir.mkdir()
    prev = _artifact("2026-06-30", ("x", "The original wording."))
    cur = _artifact("2026-07-01")
    (agency_dir / "2026-06-30.json").write_text(json.dumps(prev))
    (agency_dir / "2026-07-01.json").write_text(json.dumps(cur))
    (agency_dir / "fixlog.json").write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "code": "x",
                        "what": "untrusted stale wording",
                        "last_seen": "2026-06-30",
                        "cleared": "2026-07-01",
                    }
                ]
            }
        )
    )
    assert load_fixlog(agency_dir) == diff_receipts(prev, cur)


def test_load_fixlog_keeps_provenance_receipt_after_dated_evidence_is_pruned(
    tmp_path: Path,
) -> None:
    agency_dir = tmp_path / "demo"
    agency_dir.mkdir()
    receipts = diff_receipts(
        _artifact("2026-06-30", ("x", "The original wording.")),
        _artifact("2026-07-01"),
    )
    (agency_dir / "fixlog.json").write_text(json.dumps({"receipts": receipts}))
    assert load_fixlog(agency_dir) == receipts
