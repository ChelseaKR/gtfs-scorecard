"""CLI propagation tests for capability-aware realtime scoring."""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

import scorecard_pipeline.cli as cli
from scorecard_pipeline import worklock
from scorecard_pipeline.config import Agency
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.rt import RT_KINDS, RtSample, RtWindow
from scorecard_pipeline.rt_drift import DriftStats, PlausibilityStats


@pytest.mark.parametrize(
    ("kinds", "expects_trip_updates", "expects_vehicle_positions"),
    [
        (("vehicle_positions",), False, True),
        (("trip_updates",), True, False),
        (("service_alerts",), False, False),
        (RT_KINDS, True, True),
    ],
)
def test_cli_runs_only_analysis_for_configured_realtime_kinds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kinds: tuple[str, ...],
    expects_trip_updates: bool,
    expects_vehicle_positions: bool,
) -> None:
    agency = Agency(
        id="partial-rt",
        name="Partial RT",
        static_gtfs_url="https://example.test/gtfs.zip",
        rt_urls={kind: f"https://example.test/{kind}.pb" for kind in kinds},
    )
    window = RtWindow(
        samples=[RtSample(kind=kind, fetched_at=1, ok=True, header_timestamp=1) for kind in kinds]
    )
    calls: list[str] = []
    scored: dict[str, object] = {}
    drift_result = DriftStats(
        observations=1,
        median_seconds=0,
        p90_abs_seconds=0,
        on_time_share=1.0,
    )
    plausibility_result = PlausibilityStats(
        vehicles_checked=1,
        plausible_share=1.0,
        worst_meters=0,
    )

    def capture(
        configured_agency: Agency,
        date: dt.date,
        samples: int,
        interval_seconds: int,
    ) -> RtWindow:
        assert configured_agency is agency
        assert date == dt.date(2026, 7, 13)
        assert (samples, interval_seconds) == (2, 30)
        calls.append("capture")
        return window

    def schedule(path: str, moment: dt.datetime) -> set[str]:
        assert path == str(tmp_path / "static.zip")
        assert moment.tzinfo is not None
        calls.append("schedule")
        return {"T1"}

    def drift(samples: list[RtSample], path: str) -> DriftStats:
        assert samples is window.samples
        assert path == str(tmp_path / "static.zip")
        calls.append("drift")
        return drift_result

    def plausibility(samples: list[RtSample], path: str) -> PlausibilityStats:
        assert samples is window.samples
        assert path == str(tmp_path / "static.zip")
        calls.append("plausibility")
        return plausibility_result

    def score(
        scored_window: RtWindow,
        scheduled: set[str] | None,
        drift: DriftStats | None = None,
        plausibility: PlausibilityStats | None = None,
        configured_kinds: Collection[str] | None = None,
    ) -> CategoryResult:
        scored.update(
            window=scored_window,
            scheduled=scheduled,
            drift=drift,
            plausibility=plausibility,
            configured_kinds=set(configured_kinds or ()),
        )
        calls.append("score")
        return CategoryResult("realtime", 100.0, "Measured.", [], {})

    monkeypatch.setattr(cli, "capture_window", capture)
    monkeypatch.setattr(cli, "scheduled_trip_ids_at", schedule)
    monkeypatch.setattr(cli, "compute_drift", drift)
    monkeypatch.setattr(cli, "vehicle_plausibility", plausibility)
    monkeypatch.setattr(cli, "realtime", score)

    categories = cli._realtime_categories(
        agency,
        tmp_path / "static.zip",
        dt.date(2026, 7, 13),
        rt_samples=2,
        rt_interval=30,
    )

    assert [c.score for c in categories] == [100.0]
    assert ("schedule" in calls) is expects_trip_updates
    assert ("drift" in calls) is expects_trip_updates
    assert ("plausibility" in calls) is expects_vehicle_positions
    assert scored == {
        "window": window,
        "scheduled": {"T1"} if expects_trip_updates else None,
        "drift": drift_result if expects_trip_updates else None,
        "plausibility": plausibility_result if expects_vehicle_positions else None,
        "configured_kinds": set(kinds),
    }


def test_the_sampling_window_gives_the_heavy_turn_back_and_dates_the_schedule_to_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A minute of sleeping between samples must not keep sibling runs out of
    their validators (worklock.py). And the trips expected to be running are
    the ones due when the samples were taken, not whenever this run next gets
    the turn: a later instant would shift the schedule the samples are held to."""
    monkeypatch.setenv(worklock.HEAVY_LOCK_ENV, str(tmp_path / "heavy.lock"))
    agency = Agency(
        id="yolobus",
        name="Yolobus",
        static_gtfs_url="https://example.test/gtfs.zip",
        rt_urls={"trip_updates": "https://example.test/tu.pb"},
    )
    seen: dict[str, object] = {}
    real_outside = worklock.outside_heavy_section

    @contextmanager
    def slow_to_retake() -> Iterator[None]:
        with real_outside():
            yield
            seen["window_closed"] = dt.datetime.now(dt.UTC)
        # A sibling's validator holding the turn when this run wants it back.
        time.sleep(0.01)

    def capture(*_args: object, **_kwargs: object) -> RtWindow:
        seen["capture_held"] = worklock.held()
        return RtWindow(samples=[RtSample(kind="trip_updates", fetched_at=1, ok=True)])

    def schedule(_path: str, moment: dt.datetime) -> set[str]:
        seen["schedule_held"] = worklock.held()
        seen["moment"] = moment
        return {"T1"}

    monkeypatch.setattr(cli, "outside_heavy_section", slow_to_retake)
    monkeypatch.setattr(cli, "capture_window", capture)
    monkeypatch.setattr(cli, "scheduled_trip_ids_at", schedule)
    monkeypatch.setattr(cli, "compute_drift", lambda *_a: None)
    monkeypatch.setattr(
        cli, "realtime", lambda *_a, **_k: CategoryResult("realtime", 90.0, "Measured.", [], {})
    )

    with worklock.heavy_section():
        cli._realtime_categories(
            agency, tmp_path / "static.zip", dt.date(2026, 9, 18), rt_samples=3, rt_interval=0
        )

    assert seen["capture_held"] is False
    assert seen["schedule_held"] is True
    assert isinstance(seen["moment"], dt.datetime)
    assert isinstance(seen["window_closed"], dt.datetime)
    assert seen["moment"] <= seen["window_closed"]
