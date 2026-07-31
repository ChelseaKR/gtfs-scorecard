"""Tests for deterministic generated-site byte budgets."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "pipeline" / "scripts" / "check_site_budgets.py"


def _run_checker(
    tmp_path: Path,
    *,
    required: dict[str, int],
    patterns: dict[str, int],
    files: dict[str, bytes],
) -> subprocess.CompletedProcess[str]:
    site = tmp_path / "site"
    for relative, content in files.items():
        path = site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    config = tmp_path / "budgets.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "required": required,
                "patterns": patterns,
            }
        ),
        encoding="utf-8",
    )
    return subprocess.run(  # noqa: S603 - fixed interpreter and test-owned inputs
        [
            sys.executable,
            str(CHECKER),
            "--site-root",
            str(site),
            "--config",
            str(config),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_pages_within_every_budget_pass(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        required={"index.html": 10},
        patterns={"**/index.html": 20},
        files={"index.html": b"small", "agency/demo/index.html": b"also small"},
    )

    assert result.returncode == 0
    assert "budgets passed (3 checks)" in result.stdout


def test_checker_reports_all_overages(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        required={"index.html": 4},
        patterns={"**/index.html": 5},
        files={"index.html": b"123456", "agency/demo/index.html": b"1234567"},
    )

    assert result.returncode == 1
    assert "index.html: 6 bytes exceeds 4-byte budget" in result.stdout
    assert "index.html: 6 bytes exceeds 5-byte budget" in result.stdout
    assert "agency/demo/index.html: 7 bytes exceeds 5-byte budget" in result.stdout


def test_missing_required_page_fails(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        required={"index.html": 10},
        patterns={"**/index.html": 20},
        files={"agency/demo/index.html": b"small"},
    )

    assert result.returncode == 2
    assert "required generated page is missing: index.html" in result.stdout


def test_glob_that_matches_nothing_fails(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        required={"index.html": 10},
        patterns={"agency/*/index.html": 20},
        files={"index.html": b"small"},
    )

    assert result.returncode == 2
    assert "generated-page pattern matched no files" in result.stdout


def test_absolute_budget_path_is_rejected(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        required={"/index.html": 10},
        patterns={"**/index.html": 20},
        files={"index.html": b"small"},
    )

    assert result.returncode == 2
    assert "must stay inside the site root" in result.stderr


def test_parent_budget_path_is_rejected(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        required={"../index.html": 10},
        patterns={"**/index.html": 20},
        files={"index.html": b"small"},
    )

    assert result.returncode == 2
    assert "must stay inside the site root" in result.stderr
