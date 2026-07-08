"""Tests for run_summary.py (FIX-11): the per-shard outcome log, the
per-shard run-summary.json it builds into, and the merge into
data/artifacts/run/latest.json that /status/ reads."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from scorecard_pipeline.run_summary import (
    DEGRADED_THRESHOLD,
    AgencyOutcome,
    append_outcome,
    build_shard_summary,
    merge_run_summaries,
    read_outcomes,
)


def test_agency_outcome_json_roundtrip() -> None:
    outcome = AgencyOutcome(
        agency_id="unitrans", outcome="scored", mirrored=True, cache_hit=False, wall_seconds=1.5
    )
    restored = AgencyOutcome.from_json(outcome.to_json())
    assert restored == outcome


def test_append_and_read_outcomes_roundtrip(tmp_path: Path) -> None:
    log = tmp_path / "outcomes.ndjson"
    a = AgencyOutcome("unitrans", "scored", mirrored=False, cache_hit=True, wall_seconds=2.0)
    b = AgencyOutcome("yolobus", "reused", wall_seconds=0.1)
    append_outcome(log, a)
    append_outcome(log, b)

    outcomes = read_outcomes(log)
    assert outcomes == [a, b]


def test_read_outcomes_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_outcomes(tmp_path / "does-not-exist.ndjson") == []


def test_read_outcomes_skips_blank_lines(tmp_path: Path) -> None:
    log = tmp_path / "outcomes.ndjson"
    log.write_text(
        json.dumps(AgencyOutcome("a", "scored").to_json())
        + "\n\n"
        + json.dumps(AgencyOutcome("b", "unreachable").to_json())
        + "\n"
    )
    outcomes = read_outcomes(log)
    assert [o.agency_id for o in outcomes] == ["a", "b"]


def test_build_shard_summary_counts_outcomes() -> None:
    outcomes = [
        AgencyOutcome("a", "scored", mirrored=True, cache_hit=False),
        AgencyOutcome("b", "scored", mirrored=False, cache_hit=True),
        AgencyOutcome("c", "reused"),
        AgencyOutcome("d", "unreachable"),
        AgencyOutcome("e", "unreachable"),
    ]
    started = dt.datetime(2026, 7, 8, 13, 23, tzinfo=dt.UTC)
    finished = started + dt.timedelta(minutes=5)
    summary = build_shard_summary("0", outcomes, started, finished)

    assert summary["shard"] == "0"
    assert summary["agency_count"] == 5
    assert summary["scored"] == 2
    assert summary["reused"] == 1
    assert summary["unreachable"] == 2
    assert summary["mirrored"] == 1
    assert summary["cache_hit"] == 1
    assert summary["unreachable_agencies"] == ["d", "e"]
    assert summary["wall_clock_seconds"] == 300.0


def test_build_shard_summary_empty_outcomes() -> None:
    started = dt.datetime(2026, 7, 8, tzinfo=dt.UTC)
    summary = build_shard_summary("1", [], started, started)
    assert summary["agency_count"] == 0
    assert summary["scored"] == 0
    assert summary["unreachable_agencies"] == []


def test_merge_run_summaries_totals_and_healthy() -> None:
    shard0 = build_shard_summary(
        "0",
        [AgencyOutcome("a", "scored"), AgencyOutcome("b", "scored")],
        dt.datetime(2026, 7, 8, tzinfo=dt.UTC),
        dt.datetime(2026, 7, 8, 0, 1, tzinfo=dt.UTC),
    )
    shard1 = build_shard_summary(
        "1",
        [AgencyOutcome("c", "reused"), AgencyOutcome("d", "scored", mirrored=True)],
        dt.datetime(2026, 7, 8, tzinfo=dt.UTC),
        dt.datetime(2026, 7, 8, 0, 2, tzinfo=dt.UTC),
    )
    generated_at = dt.datetime(2026, 7, 8, 0, 5, tzinfo=dt.UTC)
    merged = merge_run_summaries([shard1, shard0], generated_at)

    # Merge sorts shards by id, regardless of input order.
    assert [s["shard"] for s in merged["shards"]] == ["0", "1"]
    assert merged["shard_count"] == 2
    assert merged["agency_count"] == 4
    assert merged["scored"] == 3
    assert merged["reused"] == 1
    assert merged["unreachable"] == 0
    assert merged["mirrored"] == 1
    assert merged["degraded"] is False
    assert merged["degraded_threshold"] == DEGRADED_THRESHOLD
    assert merged["generated_at"] == generated_at.isoformat()


def test_merge_run_summaries_flags_degraded_above_threshold() -> None:
    # 2 of 10 unreachable = 20%, well above the 5% threshold.
    outcomes = [AgencyOutcome(str(i), "scored") for i in range(8)] + [
        AgencyOutcome("u1", "unreachable"),
        AgencyOutcome("u2", "unreachable"),
    ]
    shard = build_shard_summary(
        "0",
        outcomes,
        dt.datetime(2026, 7, 8, tzinfo=dt.UTC),
        dt.datetime(2026, 7, 8, tzinfo=dt.UTC),
    )
    merged = merge_run_summaries([shard], dt.datetime(2026, 7, 8, tzinfo=dt.UTC))
    assert merged["degraded"] is True
    assert merged["unreachable_agencies"] == ["u1", "u2"]


def test_merge_run_summaries_empty_list_does_not_divide_by_zero() -> None:
    merged = merge_run_summaries([], dt.datetime(2026, 7, 8, tzinfo=dt.UTC))
    assert merged["agency_count"] == 0
    assert merged["degraded"] is False
    assert merged["shard_count"] == 0


def test_merge_run_summaries_dedupes_unreachable_across_shards() -> None:
    # The same agency id appearing unreachable in two shard summaries (should
    # not happen with a correct shard plan, but the union must not double
    # count it in the name list).
    shard_a = build_shard_summary(
        "0",
        [AgencyOutcome("dup", "unreachable")],
        dt.datetime(2026, 7, 8, tzinfo=dt.UTC),
        dt.datetime(2026, 7, 8, tzinfo=dt.UTC),
    )
    shard_b = build_shard_summary(
        "1",
        [AgencyOutcome("dup", "unreachable")],
        dt.datetime(2026, 7, 8, tzinfo=dt.UTC),
        dt.datetime(2026, 7, 8, tzinfo=dt.UTC),
    )
    merged = merge_run_summaries([shard_a, shard_b], dt.datetime(2026, 7, 8, tzinfo=dt.UTC))
    assert merged["unreachable_agencies"] == ["dup"]
    assert merged["unreachable"] == 2
