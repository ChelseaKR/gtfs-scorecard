"""A rejected push must cost a re-commit, not a cycle of observations.

`rt-monitor.yml` samples every agency's realtime feeds for over two hours and
commits at the end. `main` has usually moved to another monitor run's
observations by then, and the two runs appended different readings to the same
per-agency files, so the rebase the retry used to perform conflicted in every
record and threw the whole run away (run 34735712784, 2026-09-13). The two
sides are not in disagreement, so the repair is a union, and these tests own
what that union is allowed to do.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scorecard_pipeline.rt_health import (
    MAX_OBSERVATIONS,
    RtHealthRecordCorruptError,
    RtObservation,
    merge_records,
    read_record,
    write_record,
)

ROOT = Path(__file__).resolve().parents[2]


def _observation(ts: int, *, reachable: int = 3, lag: int | None = 10) -> RtObservation:
    return RtObservation(
        ts=ts,
        kinds_reachable=reachable,
        kinds_total=3,
        worst_lag_seconds=lag,
        coverage_pct=None,
    )


def _record(directory: Path, agency_id: str, *timestamps: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return write_record(
        directory / f"{agency_id}.json",
        agency_id,
        [_observation(ts) for ts in timestamps],
    )


def test_a_merge_keeps_both_runs_observations(tmp_path: Path) -> None:
    ours = tmp_path / "ours"
    into = tmp_path / "into"
    _record(ours, "yolobus", 100, 200, 300)
    _record(into, "yolobus", 100, 200, 400)

    changed = merge_records(ours, into)

    assert [path.name for path in changed] == ["yolobus.json"]
    assert [o.ts for o in read_record(into / "yolobus.json")] == [100, 200, 300, 400]


def test_a_merge_recomputes_the_summary_from_the_merged_history(tmp_path: Path) -> None:
    ours = tmp_path / "ours"
    into = tmp_path / "into"
    ours.mkdir()
    into.mkdir()
    write_record(ours / "yolobus.json", "yolobus", [_observation(100), _observation(300)])
    write_record(
        into / "yolobus.json",
        "yolobus",
        [_observation(100), _observation(400, reachable=0, lag=None)],
    )

    merge_records(ours, into)

    summary = json.loads((into / "yolobus.json").read_text())["summary"]
    # Three observations, one of them down: the summary is derived from the
    # union, not carried over from either side (each of which read 50.0/100.0).
    assert summary["observations"] == 3
    assert summary["uptime_pct"] == 66.7
    assert summary["first_ts"] == 100
    assert summary["last_ts"] == 400


def test_a_merge_caps_the_history_the_way_an_append_does(tmp_path: Path) -> None:
    ours = tmp_path / "ours"
    into = tmp_path / "into"
    _record(ours, "yolobus", *range(1, MAX_OBSERVATIONS + 1))
    _record(into, "yolobus", *range(MAX_OBSERVATIONS + 1, MAX_OBSERVATIONS * 2 + 1))

    merge_records(ours, into)

    merged = [o.ts for o in read_record(into / "yolobus.json")]
    assert len(merged) == MAX_OBSERVATIONS
    assert merged[-1] == MAX_OBSERVATIONS * 2
    assert merged[0] == MAX_OBSERVATIONS + 1


def test_a_merge_never_rewrites_a_record_it_adds_nothing_to(tmp_path: Path) -> None:
    ours = tmp_path / "ours"
    into = tmp_path / "into"
    _record(ours, "yolobus", 100, 200)
    published = _record(into, "yolobus", 100, 200, 300)
    before = published.read_bytes()

    assert merge_records(ours, into) == []
    assert published.read_bytes() == before


def test_a_merge_leaves_an_agency_only_the_other_run_recorded_alone(tmp_path: Path) -> None:
    ours = tmp_path / "ours"
    into = tmp_path / "into"
    _record(ours, "yolobus", 100)
    theirs = _record(into, "unitrans", 500)
    before = theirs.read_bytes()

    merge_records(ours, into)

    assert theirs.read_bytes() == before


def test_a_merge_creates_a_record_only_this_run_has(tmp_path: Path) -> None:
    ours = tmp_path / "ours"
    into = tmp_path / "into"
    _record(ours, "yolobus", 100)
    into.mkdir()

    merge_records(ours, into)

    assert [o.ts for o in read_record(into / "yolobus.json")] == [100]


def test_a_merge_refuses_a_corrupt_published_record(tmp_path: Path) -> None:
    ours = tmp_path / "ours"
    into = tmp_path / "into"
    _record(ours, "yolobus", 100)
    into.mkdir()
    (into / "yolobus.json").write_text("{ not json")

    # Reading corruption as an empty history would replace a published record
    # with this run's single observation and report success.
    with pytest.raises(RtHealthRecordCorruptError):
        merge_records(ours, into)


def test_the_monitor_resolves_a_rejected_push_by_merging_not_rebasing() -> None:
    workflow = (ROOT / ".github" / "workflows" / "rt-monitor.yml").read_text(encoding="utf-8")
    commit = workflow[workflow.index("name: Commit observations") :]

    assert "scripts/merge_rt_health.py" in commit
    assert "git rebase" not in commit, (
        "a rebase cannot resolve this: both sides append different readings to the "
        "same per-agency records, so every file conflicts and the run's observations "
        "are discarded"
    )
    # The retry re-commits the merged tree, so the loop must still end in a
    # failure when no attempt pushed (tests/test_workflow_safety.py owns the
    # shape; this asserts the merge did not quietly drop it).
    assert re.search(r'if \[ "\$pushed" != true \]', commit)
    assert (ROOT / "pipeline" / "scripts" / "merge_rt_health.py").is_file()
