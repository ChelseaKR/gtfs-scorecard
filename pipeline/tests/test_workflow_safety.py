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


def test_daily_and_intraday_publishers_share_one_concurrency_group() -> None:
    for name in ("scorecard.yml", "refresh.yml"):
        workflow = _workflow(name)
        assert "concurrency:" in workflow, name
        assert "group: artifact-publish" in workflow, name
        assert "cancel-in-progress: false" in workflow, name
