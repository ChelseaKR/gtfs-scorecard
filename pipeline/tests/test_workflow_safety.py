"""Regression checks for workflows that publish or commit generated data."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_commit_retry_loops_fail_when_no_push_succeeds() -> None:
    for name in ("equity.yml", "canada-equity.yml", "rt-monitor.yml", "rt-archive.yml"):
        workflow = _workflow(name)
        assert "pushed=false" in workflow, name
        assert "pushed=true" in workflow, name
        assert 'if [ "$pushed" != true ]' in workflow, name
        assert "exit 1" in workflow, name


def test_pages_publishes_only_registry_bounded_artifact_directories() -> None:
    workflow = _workflow("pages.yml")
    assembler = (ROOT / "pipeline" / "scripts" / "assemble_public_artifacts.sh").read_text()

    assert "assemble_public_artifacts.sh" in workflow
    assert "jq -r '.agencies | keys[]' \"$index_path\"" in assembler
    assert "cp -r data/artifacts _site/data/artifacts" not in workflow
    assert 'cp -r "data/artifacts/run"' not in workflow
