"""Tests for CLI helpers that don't require fetching or the Java validator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scorecard_pipeline.cli import _try_gate


def _artifact(grade: str, days: int | None) -> dict:  # type: ignore[type-arg]
    return {
        "overall": {"grade": grade, "score": 0},
        "categories": {"freshness": {"details": {"days_until_expiry": days}}},
    }


def _args(min_grade: str | None = None, min_days: int | None = None) -> argparse.Namespace:
    return argparse.Namespace(min_grade=min_grade, min_days_to_expiry=min_days)


def test_gate_passes_without_thresholds() -> None:
    assert _try_gate(_artifact("F", -5), _args()) == 0


def test_gate_fails_below_min_grade() -> None:
    assert _try_gate(_artifact("C", 90), _args(min_grade="B")) == 1
    assert _try_gate(_artifact("B", 90), _args(min_grade="B")) == 0
    assert _try_gate(_artifact("A", 90), _args(min_grade="B")) == 0


def test_gate_fails_when_expiring_too_soon() -> None:
    assert _try_gate(_artifact("A", 10), _args(min_days=30)) == 1
    assert _try_gate(_artifact("A", 45), _args(min_days=30)) == 0
    assert _try_gate(_artifact("A", None), _args(min_days=30)) == 1  # no expiry date fails


def test_gate_combines_thresholds() -> None:
    # Grade ok but expiring too soon still fails.
    assert _try_gate(_artifact("A", 5), _args(min_grade="B", min_days=30)) == 1


def test_prune_reports_orphans_without_deleting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scorecard_pipeline import cli

    art = tmp_path / "data" / "artifacts"
    (art / "still-here").mkdir(parents=True)
    (art / "long-gone").mkdir()
    monkeypatch.setenv("SCORECARD_ROOT", str(tmp_path))
    monkeypatch.setattr(cli, "AGENCIES", {"still-here": object()})
    parser = argparse.ArgumentParser()

    args = argparse.Namespace(delete=False)
    assert cli._cmd_prune(args, parser) == 0
    out = capsys.readouterr().out
    assert "orphan\tlong-gone" in out
    assert "Report only" in out
    assert (art / "long-gone").exists()  # never deletes without --delete

    args = argparse.Namespace(delete=True)
    assert cli._cmd_prune(args, parser) == 0
    assert not (art / "long-gone").exists()
    assert (art / "still-here").exists()


def test_prune_never_flags_reserved_dirs_as_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """rollups/, changes/, and run/ (FIX-11's run-health summary) hold published
    aggregates, not agencies, so prune must never report them as orphans."""
    from scorecard_pipeline import cli

    art = tmp_path / "data" / "artifacts"
    (art / "rollups").mkdir(parents=True)
    (art / "changes").mkdir()
    (art / "run").mkdir()
    monkeypatch.setenv("SCORECARD_ROOT", str(tmp_path))
    monkeypatch.setattr(cli, "AGENCIES", {})
    parser = argparse.ArgumentParser()

    args = argparse.Namespace(delete=False)
    assert cli._cmd_prune(args, parser) == 0
    out = capsys.readouterr().out
    assert "no orphaned artifact directories" in out


def test_run_summary_build_and_merge_end_to_end(tmp_path: Path, isolated_repo_root: Path) -> None:
    """`scorecard run-summary build` turns an outcome log into a shard summary;
    `scorecard run-summary merge` combines shard summaries into the artifact
    /status/ reads."""
    from scorecard_pipeline.cli import main
    from scorecard_pipeline.run_summary import AgencyOutcome, append_outcome

    isolated_repo_root.mkdir(parents=True, exist_ok=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: unitrans\n"
        "    name: Unitrans\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )

    outcomes_path = tmp_path / "outcomes.ndjson"
    append_outcome(outcomes_path, AgencyOutcome("unitrans", "scored", cache_hit=True))
    append_outcome(outcomes_path, AgencyOutcome("yolobus", "unreachable"))

    summary_path = tmp_path / "run-summary-0.json"
    exit_code = main(
        [
            "run-summary",
            "build",
            "--shard",
            "0",
            "--outcomes",
            str(outcomes_path),
            "--started",
            "2026-07-08T13:23:00+00:00",
            "--out",
            str(summary_path),
        ]
    )
    assert exit_code == 0
    summary = json.loads(summary_path.read_text())
    assert summary["scored"] == 1
    assert summary["unreachable"] == 1
    assert summary["unreachable_agencies"] == ["yolobus"]

    merged_path = tmp_path / "run" / "latest.json"
    exit_code = main(["run-summary", "merge", "--out", str(merged_path), str(summary_path)])
    assert exit_code == 0
    merged = json.loads(merged_path.read_text())
    assert merged["scored"] == 1
    assert merged["unreachable"] == 1
    assert merged["shard_count"] == 1


def test_run_summary_merge_skips_missing_shard_files(
    tmp_path: Path, isolated_repo_root: Path
) -> None:
    """A shard whose runner crashed before uploading its summary is simply
    absent; merge must not raise, and totals undercount rather than fail."""
    from scorecard_pipeline.cli import main

    isolated_repo_root.mkdir(parents=True, exist_ok=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: unitrans\n"
        "    name: Unitrans\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )

    merged_path = tmp_path / "run" / "latest.json"
    exit_code = main(
        ["run-summary", "merge", "--out", str(merged_path), str(tmp_path / "missing.json")]
    )
    assert exit_code == 0
    merged = json.loads(merged_path.read_text())
    assert merged["shard_count"] == 0
    assert merged["agency_count"] == 0
