"""Contract tests for the richer GitHub Action result surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_action_declares_stable_outputs_and_json_input() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    assert set(action["outputs"]) == {
        "grade",
        "score",
        "days-to-expiry",
        "passed",
        "result-json",
    }
    assert action["inputs"]["json"]["required"] is False
    assert action["inputs"]["summary"]["default"] == "true"
    run = action["runs"]["steps"][-1]["run"]
    assert '--json-out "$result_json"' in run
    assert 'exit "$gate_rc"' in run


def test_result_script_writes_outputs_summary_and_annotation(tmp_path: Path) -> None:
    artifact = {
        "agency": {"name": "Example Transit"},
        "overall": {"grade": "C", "score": 72.5},
        "categories": {"freshness": {"details": {"days_until_expiry": 12}}},
        "top_fixes": [{"fix": "Extend the service calendar."}],
    }
    result = tmp_path / "result.json"
    output = tmp_path / "output.txt"
    summary = tmp_path / "summary.md"
    result.write_text(json.dumps(artifact))
    env = os.environ | {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)}

    run = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        [
            sys.executable,
            str(ROOT / "action/render_result.py"),
            "--json",
            str(result),
            "--gate-rc",
            "1",
            "--min-grade",
            "B",
            "--write-summary",
            "true",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    outputs = output.read_text()
    assert "grade=C" in outputs
    assert "days-to-expiry=12" in outputs
    assert "passed=false" in outputs
    assert "Example Transit: grade C" in summary.read_text()
    assert "::error title=GTFS Scorecard gate::" in run.stdout


def test_cli_json_output_is_written_before_gate_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse

    from scorecard_pipeline import cli

    artifact = {
        "agency": {"name": "Example Transit"},
        "feed": {"static_url": "https://example.org/gtfs.zip"},
        "overall": {"grade": "C", "score": 72.5},
        "categories": {
            "correctness": {"status": "measured", "score": 70},
            "freshness": {
                "status": "measured",
                "score": 80,
                "details": {"days_until_expiry": 12},
            },
        },
        "top_fixes": [],
    }
    monkeypatch.setattr(cli, "run_adhoc", lambda *_args: artifact)
    output = tmp_path / "nested/result.json"
    args = argparse.Namespace(
        url="https://example.org/gtfs.zip",
        name=None,
        date=None,
        html=None,
        comment=None,
        page_url=None,
        json_out=str(output),
        min_grade="B",
        min_days_to_expiry=None,
    )
    assert cli._cmd_try(args, argparse.ArgumentParser()) == 1
    assert json.loads(output.read_text())["overall"]["grade"] == "C"
