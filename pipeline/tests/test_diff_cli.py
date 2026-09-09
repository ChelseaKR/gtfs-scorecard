"""Contract tests for `scorecard diff`.

The verb's whole reason to exist is that it decides whether a pair is the same
measurement **before** it reports anything, so most of what is asserted here is
what the command refuses to say.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.cli import (
    DIFF_EXIT_NOT_COMPARABLE,
    DIFF_EXIT_OK,
    DIFF_EXIT_REGRESSED,
    DIFF_EXIT_UNREADABLE,
    main,
)


def _artifact(
    *,
    validator: str = "8.0.1",
    grade: str = "B",
    score: float = 82.0,
    findings: list[dict[str, Any]] | None = None,
    date: str = "2026-06-12",
) -> dict[str, Any]:
    return {
        "snapshot_date": date,
        "agency": {"id": "example-transit", "name": "Example Transit"},
        "overall": {"grade": grade, "score": score},
        "feed": {"sha256": "aaa", "size_bytes": 1000},
        "rubric_version": "1.3",
        "validator_version": validator,
        "scoring_profile": {"id": "gtfs-scorecard-1.3", "rubric_version": "1.3"},
        "fetch": {"reader_archive_profile": "raw-v1"},
        "categories": {
            "correctness": {"status": "measured", "score": 90.0, "findings": findings or []},
            "freshness": {
                "status": "measured",
                "score": 80.0,
                "details": {"days_until_expiry": 90},
                "findings": [],
            },
            "completeness": {"status": "measured", "score": 75.0, "findings": []},
        },
    }


def _write(path: Path, artifact: dict[str, Any]) -> str:
    path.write_text(json.dumps(artifact))
    return str(path)


def test_an_artifact_against_itself_reports_no_change_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    same = _write(tmp_path / "a.json", _artifact())
    assert main(["diff", same, same]) == DIFF_EXIT_OK
    assert "Nothing changed" in capsys.readouterr().out


def test_a_new_finding_exits_regressed(tmp_path: Path) -> None:
    old = _write(tmp_path / "old.json", _artifact())
    new = _write(
        tmp_path / "new.json",
        _artifact(findings=[{"code": "unused_shape", "count": 3, "severity": "WARNING"}]),
    )
    assert main(["diff", old, new]) == DIFF_EXIT_REGRESSED


def test_an_improvement_is_not_a_regression(tmp_path: Path) -> None:
    old = _write(
        tmp_path / "old.json",
        _artifact(findings=[{"code": "unused_shape", "count": 9, "severity": "WARNING"}]),
    )
    new = _write(
        tmp_path / "new.json",
        _artifact(findings=[{"code": "unused_shape", "count": 2, "severity": "WARNING"}]),
    )
    assert main(["diff", old, new]) == DIFF_EXIT_OK


def test_a_different_validator_version_is_not_comparable_and_claims_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2, distinct from a regression, and no change vocabulary in the output."""
    old = _write(tmp_path / "old.json", _artifact())
    new = _write(
        tmp_path / "new.json",
        _artifact(
            validator="9.0.0",
            grade="D",
            score=61.0,
            findings=[{"code": "unused_shape", "count": 40, "severity": "WARNING"}],
        ),
    )
    assert main(["diff", old, new]) == DIFF_EXIT_NOT_COMPARABLE
    out = capsys.readouterr().out
    assert "NOT COMPARABLE" in out
    assert "validator_version_mismatch" in out
    for forbidden in ("New findings", "Cleared findings", "Grade B", "Nothing changed"):
        assert forbidden not in out


def test_the_json_format_omits_every_change_key_when_not_comparable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = _write(tmp_path / "old.json", _artifact())
    new = _write(tmp_path / "new.json", _artifact(validator="9.0.0"))
    assert main(["diff", old, new, "--format", "json"]) == DIFF_EXIT_NOT_COMPARABLE
    payload = json.loads(capsys.readouterr().out)
    assert payload["comparable"] is False
    assert "findings" not in payload
    assert "overall" not in payload


@pytest.mark.parametrize(
    ("name", "content"),
    [
        pytest.param("missing.json", None, id="no such file"),
        pytest.param("notjson.json", "<html>404</html>", id="not JSON"),
        pytest.param("notanartifact.json", '{"hello": "world"}', id="JSON but not an artifact"),
    ],
)
def test_an_unreadable_operand_exits_three_and_prints_no_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, content: str | None
) -> None:
    """An operand we never got is not a verdict about two artifacts.

    Exit 3 keeps it apart from exit 2. Reporting a broken input as a contract
    boundary would blame the feed's methodology for a broken configuration, and
    a caller acting on that would be acting on a fabricated cause.
    """
    good = _write(tmp_path / "good.json", _artifact())
    bad = tmp_path / name
    if content is not None:
        bad.write_text(content)
    assert main(["diff", good, str(bad)]) == DIFF_EXIT_UNREADABLE
    assert capsys.readouterr().out == ""


def test_agency_at_date_resolves_against_the_artifacts_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    agency_dir = root / "data" / "artifacts" / "example-transit"
    agency_dir.mkdir(parents=True)
    _write(agency_dir / "2026-06-12.json", _artifact(date="2026-06-12"))
    _write(agency_dir / "latest.json", _artifact(date="2026-06-19"))
    monkeypatch.setenv("SCORECARD_ROOT", str(root))
    assert main(["diff", "example-transit@2026-06-12", "example-transit@latest"]) == DIFF_EXIT_OK


def test_the_out_flag_writes_the_rendered_diff(tmp_path: Path) -> None:
    same = _write(tmp_path / "a.json", _artifact())
    out = tmp_path / "nested" / "diff.md"
    assert main(["diff", same, same, "--format", "markdown", "--out", str(out)]) == DIFF_EXIT_OK
    assert "Feed comparison" in out.read_text()


def test_diff_needs_no_agency_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The verb is registry-free, like `try`: it compares files it was handed."""
    import scorecard_pipeline.cli as cli_module

    def _explode() -> None:
        raise AssertionError("diff must not load the agency registry")

    monkeypatch.setattr(cli_module, "load_agencies", _explode)
    same = _write(tmp_path / "a.json", _artifact())
    assert main(["diff", same, same]) == DIFF_EXIT_OK
