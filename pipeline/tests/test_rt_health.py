"""Tests for longitudinal realtime health (pure observation + summary + I/O)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import scorecard_pipeline.rt_health as rt_health
from scorecard_pipeline.rt import RtSample, RtWindow
from scorecard_pipeline.rt_health import (
    RtHealthRecordCorruptError,
    RtObservation,
    append_observation,
    load_observations,
    summarize,
)


def _window(*samples: RtSample) -> RtWindow:
    w = RtWindow()
    w.samples.extend(samples)
    return w


# `observe` returns None when no sample in a window is evidence about the feed;
# tests/test_rt_not_measured.py owns that case. Every window below holds at
# least one real sample, so this wrapper keeps the call sites unchanged.
def observe(*args: Any, **kwargs: Any) -> RtObservation:
    obs = rt_health.observe(*args, **kwargs)
    assert obs is not None, "this window holds a real sample and must be observable"
    return obs


def test_observe_counts_reachable_feeds_and_worst_lag() -> None:
    window = _window(
        RtSample(kind="trip_updates", fetched_at=1000, ok=True, header_timestamp=970),
        RtSample(kind="vehicle_positions", fetched_at=1000, ok=True, header_timestamp=900),
    )
    obs = observe(window, kinds_total=2)
    assert obs.kinds_reachable == 2
    assert obs.kinds_total == 2
    assert obs.worst_lag_seconds == 100  # 1000 - 900
    assert obs.up is True
    assert obs.coverage_pct is None  # no scheduled trips passed


def test_observe_marks_down_when_no_feed_parses() -> None:
    window = _window(RtSample(kind="trip_updates", fetched_at=1000, ok=False, error="boom"))
    obs = observe(window, kinds_total=1)
    assert obs.kinds_reachable == 0
    assert obs.up is False


def test_observe_records_coverage_when_trips_scheduled() -> None:
    window = _window(
        RtSample(
            kind="trip_updates",
            fetched_at=1000,
            ok=True,
            header_timestamp=990,
            trip_ids=frozenset({"t1", "t2"}),
        )
    )
    obs = observe(window, kinds_total=1, scheduled={"t1", "t2", "t3", "t4"})
    assert obs.coverage_pct == 50.0


def test_summarize_uptime_and_median_lag() -> None:
    obs = [
        RtObservation(
            ts=1, kinds_reachable=1, kinds_total=1, worst_lag_seconds=30, coverage_pct=None
        ),
        RtObservation(
            ts=2, kinds_reachable=0, kinds_total=1, worst_lag_seconds=None, coverage_pct=None
        ),
        RtObservation(
            ts=3, kinds_reachable=1, kinds_total=1, worst_lag_seconds=90, coverage_pct=80.0
        ),
        RtObservation(
            ts=4, kinds_reachable=1, kinds_total=1, worst_lag_seconds=50, coverage_pct=60.0
        ),
    ]
    s = summarize(obs)
    assert s.observations == 4
    assert s.uptime_pct == 75.0  # 3 of 4 responded
    assert s.median_lag_seconds == 50  # median of [30, 50, 90]
    assert s.median_coverage_pct == 70.0  # median of [60, 80]
    assert s.first_ts == 1 and s.last_ts == 4


def test_summarize_empty_is_zeroed() -> None:
    s = summarize([])
    assert s.observations == 0
    assert s.uptime_pct == 0.0
    assert s.median_lag_seconds is None


def test_append_and_load_round_trip_and_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rt_health, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(rt_health, "MAX_OBSERVATIONS", 3)
    for i in range(5):
        append_observation(
            "demo",
            RtObservation(
                ts=i, kinds_reachable=1, kinds_total=1, worst_lag_seconds=i, coverage_pct=None
            ),
        )
    loaded = load_observations("demo")
    assert [o.ts for o in loaded] == [2, 3, 4]  # capped to the last 3, oldest first


def test_load_missing_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt_health, "repo_root", lambda: tmp_path)
    assert load_observations("nobody") == []


def test_load_corrupt_record_raises_instead_of_reading_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record file that exists but fails to parse is corruption, not an
    empty history, and must never be silently read as one (see
    RtHealthRecordCorruptError's docstring: reading it as empty would let the
    next ``append_observation`` overwrite it, destroying real history)."""
    monkeypatch.setattr(rt_health, "repo_root", lambda: tmp_path)
    path = rt_health.state_path("demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<<<<<<< HEAD\nnot valid json\n=======\n>>>>>>> branch\n")

    with pytest.raises(RtHealthRecordCorruptError):
        load_observations("demo")


def test_append_refuses_to_overwrite_a_corrupt_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The destructive case this guards against: real accumulated history,
    corrupted on disk (e.g. a bad merge), must survive the next monitor run
    rather than being replaced by a single new observation."""
    monkeypatch.setattr(rt_health, "repo_root", lambda: tmp_path)
    for i in range(5):
        append_observation(
            "demo",
            RtObservation(
                ts=i, kinds_reachable=1, kinds_total=1, worst_lag_seconds=i, coverage_pct=None
            ),
        )
    path = rt_health.state_path("demo")
    original = path.read_text()
    path.write_text(original[:20])  # truncate mid-JSON, simulating corruption

    with pytest.raises(RtHealthRecordCorruptError):
        append_observation(
            "demo",
            RtObservation(
                ts=999, kinds_reachable=1, kinds_total=1, worst_lag_seconds=1, coverage_pct=None
            ),
        )

    # The corrupt file on disk is untouched, not replaced by a fresh
    # single-observation record.
    assert path.read_text() == original[:20]
