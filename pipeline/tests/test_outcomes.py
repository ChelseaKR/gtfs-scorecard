"""Tests for observed finding-resolution outcome analytics."""

from __future__ import annotations

import json
from pathlib import Path

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.cli import main
from scorecard_pipeline.outcomes import build_fix_outcomes, render_fix_outcomes_markdown
from scorecard_pipeline.validate import VALIDATOR_VERSION


def _artifact(
    date: str,
    codes: list[str],
    *,
    measured: bool = True,
    agency_id: str = "one",
) -> dict[str, object]:
    return {
        "snapshot_date": date,
        "agency": {"id": agency_id, "name": f"{agency_id.title()} Transit"},
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": RUBRIC_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "categories": {
            "correctness": {
                "status": "measured" if measured else "not_measured",
                "findings": [{"code": code, "what": code} for code in codes],
            }
        },
    }


def test_outcomes_measure_resolution_time_and_recurrence() -> None:
    histories = {
        "one": [
            _artifact("2026-01-01", ["unused_stop"]),
            _artifact("2026-01-11", []),
            _artifact("2026-01-20", ["unused_stop"]),
            _artifact("2026-01-25", []),
        ],
        "two": [
            _artifact("2026-01-01", ["unused_stop"], agency_id="two"),
            _artifact("2026-01-21", [], agency_id="two"),
        ],
    }

    report = build_fix_outcomes(histories)
    stats = report["codes"]["unused_stop"]
    assert stats["episodes"] == 3
    assert stats["resolved_episodes"] == 3
    assert stats["median_days_to_resolution"] == 10
    assert stats["agencies_with_recurrence"] == 1
    assert stats["observed_recurrence_rate_pct"] == 50.0


def test_unmeasured_category_does_not_fake_resolution() -> None:
    report = build_fix_outcomes(
        {
            "one": [
                _artifact("2026-01-01", ["unused_stop"]),
                _artifact("2026-01-05", [], measured=False),
            ]
        }
    )
    stats = report["codes"]["unused_stop"]
    assert stats["resolved_episodes"] == 0
    assert stats["still_open_episodes"] == 1
    assert "median_days_to_resolution" not in stats


def test_markdown_is_descriptive_and_filters_thin_codes() -> None:
    report = build_fix_outcomes(
        {
            "one": [
                _artifact("2026-01-01", ["common", "thin"]),
                _artifact("2026-01-10", []),
            ],
            "two": [
                _artifact("2026-01-01", ["common"], agency_id="two"),
                _artifact("2026-01-08", [], agency_id="two"),
            ],
        }
    )
    markdown = render_fix_outcomes_markdown(report, min_episodes=2)
    assert "| common |" in markdown
    assert "| thin |" not in markdown
    assert "descriptive, not causal" in markdown
    assert "do not show who changed a feed" in markdown


def test_outcomes_fail_closed_on_missing_or_changed_producer_contract() -> None:
    missing = _artifact("2026-01-01", ["x"])
    del missing["scoring_profile_id"]
    changed = _artifact("2026-01-02", [])
    changed["rubric_version"] = "different"
    report = build_fix_outcomes({"one": [missing, changed]})
    assert report["codes"] == {}


def test_recurrence_resets_across_reader_archive_profiles() -> None:
    raw_seen = _artifact("2026-01-01", ["x"])
    raw_clear = _artifact("2026-01-02", [])
    flat_seen = _artifact("2026-01-03", ["x"])
    flat_clear = _artifact("2026-01-04", [])
    for artifact in (flat_seen, flat_clear):
        artifact["fetch"] = {"reader_archive_profile": "flat-single-root-v1"}

    stats = build_fix_outcomes({"one": [raw_seen, raw_clear, flat_seen, flat_clear]})["codes"]["x"]

    assert stats["episodes"] == 2
    assert stats["resolved_episodes"] == 2
    assert stats["agencies_with_recurrence"] == 0
    assert stats["observed_recurrence_rate_pct"] == 0.0


def test_empty_histories_have_no_division_error() -> None:
    report = build_fix_outcomes({})
    assert report["overall"]["observed_resolution_rate_pct"] is None
    assert report["codes"] == {}


def test_cli_writes_outcome_report(isolated_repo_root: Path) -> None:
    isolated_repo_root.mkdir(parents=True, exist_ok=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: one\n"
        "    name: One Transit\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )
    agency_dir = isolated_repo_root / "data/artifacts/one"
    agency_dir.mkdir(parents=True)
    (agency_dir / "2026-01-01.json").write_text(json.dumps(_artifact("2026-01-01", ["x"])))
    (agency_dir / "2026-01-02.json").write_text(json.dumps(_artifact("2026-01-02", [])))
    output = isolated_repo_root / "outcomes.json"

    assert main(["fix-outcomes", "--out", str(output)]) == 0
    assert json.loads(output.read_text())["codes"]["x"]["resolved_episodes"] == 1
