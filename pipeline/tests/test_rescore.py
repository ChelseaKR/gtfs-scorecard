"""The intraday rescore: several feeds in flight, the serial loop's guarantees kept.

Scheduling runs on a fake clock with fake children, so every rule is checked
by what started when rather than by reading refresh.yml's text.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from scorecard_pipeline import cli, rescore
from scorecard_pipeline.config import AGENCIES, Agency
from scorecard_pipeline.liveness import LivenessRecord, load_state, save_state
from scorecard_pipeline.rescore import (
    UNCHANGED_EXIT,
    RescoreJob,
    RescoreTally,
    job_for,
    launch_run,
    next_startable,
    ordered,
    report,
    run_batch,
)
from scorecard_pipeline.worklock import HEAVY_LOCK_ENV


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


@dataclass
class FakeChild:
    clock: Clock
    ends_at: float
    code: int
    text: str

    def poll(self) -> int | None:
        return self.code if self.clock.t >= self.ends_at else None

    def output(self) -> str:
        return self.text


class Launcher:
    """Starts fake runs that take ``seconds[id]`` and exit ``codes[id]``."""

    def __init__(
        self,
        clock: Clock,
        seconds: dict[str, float] | None = None,
        codes: dict[str, int] | None = None,
    ) -> None:
        self.clock = clock
        self.seconds = seconds or {}
        self.codes = codes or {}
        self.spans: dict[str, tuple[float, float]] = {}

    def __call__(self, job: RescoreJob) -> FakeChild:
        start = self.clock.t
        end = start + self.seconds.get(job.agency_id, 10.0)
        self.spans[job.agency_id] = (start, end)
        return FakeChild(
            self.clock, end, self.codes.get(job.agency_id, 0), f"scored {job.agency_id}\n"
        )

    def overlapping(self, a: str, b: str) -> bool:
        (a0, a1), (b0, b1) = self.spans[a], self.spans[b]
        return a0 < b1 and b0 < a1

    def max_in_flight(self) -> int:
        edges = sorted(
            [(s, 1) for s, _ in self.spans.values()] + [(e, -1) for _, e in self.spans.values()]
        )
        live = peak = 0
        for _, delta in edges:
            live += delta
            peak = max(peak, live)
        return peak


def _job(
    agency_id: str, *hosts: str, exclusive: bool = False, realtime: bool = False
) -> RescoreJob:
    own_host = (f"{agency_id}.example",)
    return RescoreJob(agency_id, frozenset(hosts or own_host), exclusive, realtime)


def _run(
    jobs: list[RescoreJob],
    launcher: Launcher,
    clock: Clock,
    *,
    workers: int = 4,
    deadline: float = 1e9,
) -> tuple[RescoreTally, list[str]]:
    lines: list[str] = []
    tally = run_batch(
        jobs,
        workers=workers,
        deadline=deadline,
        launch=launcher,
        now=clock.now,
        sleep=clock.sleep,
        emit=lines.append,
    )
    return tally, lines


# ---------------------------------------------------------------------------
# What may run together


def test_no_more_than_the_workers_run_at_once() -> None:
    clock = Clock()
    launcher = Launcher(clock)
    tally, _ = _run([_job(f"feed-{n}") for n in range(10)], launcher, clock, workers=3)

    assert launcher.max_in_flight() == 3
    assert tally.attempted == tally.refreshed == 10


def test_waiting_overlaps_so_the_batch_takes_a_fraction_of_the_serial_time() -> None:
    clock = Clock()
    launcher = Launcher(clock, seconds={f"feed-{n}": 60.0 for n in range(8)})
    _run([_job(f"feed-{n}") for n in range(8)], launcher, clock, workers=4)

    # Serially 480 seconds; four at a time, two rounds plus a poll or two.
    assert clock.t < 130


def test_two_feeds_on_one_host_are_never_in_flight_together() -> None:
    """Politeness: no host sees more concurrent requests than the serial loop sent it."""
    clock = Clock()
    launcher = Launcher(clock)
    jobs = [
        _job("a", "shared.example"),
        _job("b", "shared.example", "b-rt.example"),
        _job("c", "c.example"),
    ]
    _run(jobs, launcher, clock, workers=4)

    assert not launcher.overlapping("a", "b")
    assert launcher.overlapping("a", "c")


def test_a_realtime_host_counts_as_a_shared_host_too() -> None:
    clock = Clock()
    launcher = Launcher(clock)
    jobs = [_job("a", "a.example", "rt.example"), _job("b", "b.example", "rt.example")]
    _run(jobs, launcher, clock, workers=4)

    assert not launcher.overlapping("a", "b")


def test_a_large_feed_runs_with_nothing_else_in_flight() -> None:
    """The isolation the daily run gives a large feed with a shard of its own (#297)."""
    clock = Clock()
    launcher = Launcher(clock, seconds={"big": 100.0})
    jobs = [_job("small-1"), _job("big", exclusive=True), _job("small-2"), _job("small-3")]
    _run(jobs, launcher, clock, workers=4)

    for other in ("small-1", "small-2", "small-3"):
        assert not launcher.overlapping("big", other)


def test_a_pending_large_feed_is_not_jumped() -> None:
    """Later small feeds must not start while a large feed waits for the runner to empty."""
    running = [_job("small-1")]
    pending = [_job("big", exclusive=True), _job("small-2")]

    assert next_startable(pending, running) is None
    assert next_startable(pending, []) == pending[0]


def test_nothing_starts_beside_a_running_large_feed() -> None:
    assert next_startable([_job("small")], [_job("big", exclusive=True)]) is None


def test_large_feeds_go_first_then_realtime_publishers_then_the_rest() -> None:
    jobs = [
        _job("b-static"),
        _job("a-static"),
        _job("z-realtime", realtime=True),
        _job("y-large", exclusive=True),
        _job("c-realtime", realtime=True),
    ]
    assert [job.agency_id for job in ordered(jobs)] == [
        "y-large",
        "c-realtime",
        "z-realtime",
        "a-static",
        "b-static",
    ]


def test_workers_below_one_is_refused() -> None:
    clock = Clock()
    with pytest.raises(ValueError, match="at least 1"):
        _run([_job("a")], Launcher(clock), clock, workers=0)


# ---------------------------------------------------------------------------
# The deadline


def test_nothing_starts_after_the_deadline_and_what_waited_is_deferred_by_name() -> None:
    clock = Clock()
    launcher = Launcher(clock, seconds={"a": 50.0, "b": 50.0, "c": 50.0})
    tally, lines = _run(
        [_job("a"), _job("b"), _job("c")], launcher, clock, workers=1, deadline=60.0
    )

    assert set(launcher.spans) == {"a", "b"}
    assert tally.deferred == ["c"]
    assert tally.attempted == 2
    # The run in flight when the deadline passed was left to finish.
    assert tally.refreshed == 2
    assert launcher.spans["b"][0] < 60.0 <= launcher.spans["b"][1]
    assert any("rescore b" in line for line in lines)


def test_a_deadline_already_past_attempts_nothing() -> None:
    clock = Clock()
    clock.t = 100.0
    tally, _ = _run([_job("a"), _job("b")], Launcher(clock), clock, deadline=50.0)

    assert tally.attempted == 0
    assert tally.deferred == ["a", "b"]


# ---------------------------------------------------------------------------
# Outcomes, the floor, and what the log says


def test_exit_two_is_an_unchanged_feed_not_a_failure() -> None:
    """Counted as the shell loop counted it, so --skip-unchanged cannot trip the floor."""
    clock = Clock()
    launcher = Launcher(clock, codes={"same": UNCHANGED_EXIT})
    tally, lines = _run([_job("same")], launcher, clock)

    assert tally.refreshed == 1
    assert tally.failed == []
    assert "feed unchanged, keeping last artifact" in lines
    assert report(tally, budget_minutes=155, requeued=False, emit=lines.append) == 0


def test_a_failed_feed_is_named_and_the_batch_carries_on() -> None:
    clock = Clock()
    launcher = Launcher(clock, codes={"down": 1})
    tally, lines = _run([_job("down"), _job("up")], launcher, clock)

    assert tally.failed == ["down"]
    assert tally.refreshed == 1
    assert "::warning title=rescore failed::down kept its last good artifact" in lines


def test_each_feed_s_output_is_one_group_however_the_runs_interleaved() -> None:
    clock = Clock()
    launcher = Launcher(clock, seconds={"slow": 30.0, "fast": 5.0})
    _, lines = _run([_job("slow"), _job("fast")], launcher, clock)

    fast_at = next(i for i, line in enumerate(lines) if line.startswith("::group::rescore fast"))
    assert lines[fast_at + 1] == "scored fast"
    assert lines[fast_at + 2] == "::endgroup::"
    assert fast_at < next(i for i, line in enumerate(lines) if "rescore slow" in line)


def test_a_cycle_that_attempted_feeds_and_refreshed_none_fails() -> None:
    lines: list[str] = []
    tally = RescoreTally(attempted=3, refreshed=0, failed=["a", "b", "c"])

    assert report(tally, budget_minutes=155, requeued=False, emit=lines.append) == 1
    assert any(line.startswith("::error::None of the 3 changed feeds") for line in lines)


def test_a_cycle_that_deferred_everything_is_not_a_failure() -> None:
    """It still applied the freshness sweep, and publishes that."""
    lines: list[str] = []
    tally = RescoreTally(attempted=0, refreshed=0, deferred=["a", "b"])

    assert report(tally, budget_minutes=155, requeued=True, emit=lines.append) == 0
    warning = next(line for line in lines if "refresh budget exhausted" in line)
    assert "a, b" in warning
    assert "155 minutes into the job" in warning
    assert "next check reads them as changed again" in warning


def test_the_deferral_warning_does_not_promise_a_requeue_that_did_not_happen() -> None:
    lines: list[str] = []
    report(RescoreTally(deferred=["a"]), budget_minutes=155, requeued=False, emit=lines.append)

    warning = next(line for line in lines if "refresh budget exhausted" in line)
    assert "next daily run" in warning
    assert "changed again" not in warning


def test_a_partial_refresh_says_how_partial_and_names_the_feeds() -> None:
    lines: list[str] = []
    tally = RescoreTally(attempted=3, refreshed=2, failed=["down"])

    assert report(tally, budget_minutes=155, requeued=False, emit=lines.append) == 0
    assert lines[0] == "re-scored 2 of 3 changed feeds (1 failed, 0 deferred)"
    assert any(
        line.startswith("::warning title=partial refresh::1 of 3") and "down" in line
        for line in lines
    )


# ---------------------------------------------------------------------------
# From the registry, and the real launcher


def test_a_job_knows_every_host_its_run_talks_to() -> None:
    agency = Agency(
        id="yolobus",
        name="Yolobus",
        static_gtfs_url="https://Static.Example/gtfs.zip",
        rt_urls={
            "trip_updates": "https://rt.example/tu",
            "vehicle_positions": "https://rt.example/vp",
        },
        large_feed=True,
    )
    job = job_for(agency)

    assert job.hosts == frozenset({"static.example", "rt.example"})
    assert job.exclusive
    assert job.realtime


def test_the_launcher_hands_the_lock_to_the_child_and_keeps_its_output(tmp_path: Path) -> None:
    script = (
        "import os, sys; print(os.environ.get('SCORECARD_HEAVY_LOCK'), sys.argv[1:]); sys.exit(3)"
    )
    child = launch_run(
        _job("unitrans"),
        log_dir=tmp_path,
        heavy_lock=tmp_path / "heavy.lock",
        command=(sys.executable, "-c", script),
    )
    code = None
    for _ in range(500):
        code = child.poll()
        if code is not None:
            break
        time.sleep(0.02)

    assert code == 3
    assert str(tmp_path / "heavy.lock") in child.output()
    assert "['run', '--agency', 'unitrans']" in child.output()


def test_without_a_lock_the_child_inherits_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(HEAVY_LOCK_ENV, raising=False)
    script = "import os; print(os.environ.get('SCORECARD_HEAVY_LOCK'))"
    child = launch_run(
        _job("unitrans"), log_dir=tmp_path, heavy_lock=None, command=(sys.executable, "-c", script)
    )
    while child.poll() is None:
        time.sleep(0.02)
    assert child.output().strip() == "None"


def test_the_default_command_is_the_cli_of_this_interpreter() -> None:
    assert rescore.SCORECARD_COMMAND[0] == sys.executable
    assert "from scorecard_pipeline.cli import main" in rescore.SCORECARD_COMMAND[2]


# ---------------------------------------------------------------------------
# `scorecard rescore`


def _registry(root: Path, *ids: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "agencies.yaml").write_text(
        "agencies:\n"
        + "".join(
            f"  - id: {agency_id}\n    name: {agency_id}\n"
            f"    static_gtfs_url: https://{agency_id}.example/gtfs.zip\n"
            for agency_id in ids
        )
    )


@dataclass
class FakeRuns:
    codes: dict[str, int]
    started: list[str]


@pytest.fixture
def fake_runs(monkeypatch: pytest.MonkeyPatch) -> FakeRuns:
    """Replace the real launcher with runs that finish at once and exit ``codes[id]``."""
    runs = FakeRuns({}, [])

    def launch(job: RescoreJob, **_: object) -> FakeChild:
        runs.started.append(job.agency_id)
        return FakeChild(Clock(), 0.0, runs.codes.get(job.agency_id, 0), "")

    monkeypatch.setattr(rescore, "launch_run", launch)
    return runs


def _rescore_args(ids: Path, tmp_path: Path, *extra: str, started: int | None = None) -> list[str]:
    return [
        "rescore",
        "--ids",
        str(ids),
        "--started-epoch",
        str(int(time.time()) if started is None else started),
        "--budget-seconds",
        "9300",
        "--deferred-out",
        str(tmp_path / "deferred.txt"),
        *extra,
    ]


def test_no_changed_feeds_is_a_quiet_success(
    isolated_repo_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _registry(isolated_repo_root, "unitrans")

    assert cli.main(_rescore_args(tmp_path / "missing.txt", tmp_path)) == 0
    assert "No changed feeds to re-score." in capsys.readouterr().out
    assert (tmp_path / "deferred.txt").read_text() == ""


def test_the_command_scores_every_listed_feed(
    isolated_repo_root: Path,
    tmp_path: Path,
    fake_runs: FakeRuns,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _registry(isolated_repo_root, "unitrans", "yolobus")
    ids = tmp_path / "changed.txt"
    ids.write_text("unitrans\n\nyolobus\n")

    assert cli.main(_rescore_args(ids, tmp_path, "--workers", "2")) == 0
    assert sorted(fake_runs.started) == ["unitrans", "yolobus"]
    assert "re-scored 2 of 2 changed feeds (0 failed, 0 deferred)" in capsys.readouterr().out


def test_the_command_fails_a_cycle_that_refreshed_nothing(
    isolated_repo_root: Path, tmp_path: Path, fake_runs: FakeRuns
) -> None:
    _registry(isolated_repo_root, "unitrans")
    fake_runs.codes["unitrans"] = 1
    ids = tmp_path / "changed.txt"
    ids.write_text("unitrans\n")

    assert cli.main(_rescore_args(ids, tmp_path)) == 1


def test_an_id_outside_the_registry_is_a_named_failure_not_an_unchanged_feed(
    isolated_repo_root: Path,
    tmp_path: Path,
    fake_runs: FakeRuns,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`scorecard run` answers an unknown id with argparse's exit 2, which the
    loop would have counted as "unchanged"."""
    _registry(isolated_repo_root, "unitrans")
    ids = tmp_path / "changed.txt"
    ids.write_text("ghost\n")

    assert cli.main(_rescore_args(ids, tmp_path)) == 1
    assert "ghost" not in fake_runs.started
    assert "::warning title=rescore failed::ghost is not in the registry" in capsys.readouterr().out


def test_deferred_feeds_are_written_out_and_put_back_for_their_next_check(
    isolated_repo_root: Path,
    tmp_path: Path,
    fake_runs: FakeRuns,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _registry(isolated_repo_root, "unitrans", "yolobus")
    ids = tmp_path / "changed.txt"
    ids.write_text("unitrans\nyolobus\n")

    before = LivenessRecord(url="https://unitrans.example/gtfs.zip", sha256="old")
    baseline = tmp_path / "liveness.before.json"
    save_state(baseline, {"unitrans": before})
    state_path = isolated_repo_root / "data" / "liveness.json"
    save_state(
        state_path,
        {
            "unitrans": LivenessRecord(url=before.url, sha256="new"),
            "yolobus": LivenessRecord(url="https://yolobus.example/gtfs.zip", sha256="first"),
        },
    )

    # A budget that ran out before the rescore began defers both feeds.
    args = _rescore_args(ids, tmp_path, "--liveness-baseline", str(baseline), started=0)
    assert cli.main(args) == 0
    assert fake_runs.started == []

    assert (tmp_path / "deferred.txt").read_text() == "unitrans\nyolobus\n"
    state = load_state(state_path)
    assert state["unitrans"].sha256 == "old"
    # No record before this cycle: dropped, so the next check reads it as new.
    assert "yolobus" not in state
    assert "next check reads them as changed again" in capsys.readouterr().out
    assert json.loads(state_path.read_text())["schema_version"] == "1.0"


def test_deferral_without_a_baseline_leaves_liveness_alone(
    isolated_repo_root: Path, tmp_path: Path, fake_runs: FakeRuns
) -> None:
    _registry(isolated_repo_root, "unitrans")
    ids = tmp_path / "changed.txt"
    ids.write_text("unitrans\n")
    state_path = isolated_repo_root / "data" / "liveness.json"
    save_state(state_path, {"unitrans": LivenessRecord(url="u", sha256="new")})

    assert cli.main(_rescore_args(ids, tmp_path, started=0)) == 0
    assert load_state(state_path)["unitrans"].sha256 == "new"


@pytest.mark.parametrize("value", ["0", "-2", "four"])
def test_workers_must_be_a_positive_whole_number(
    isolated_repo_root: Path, tmp_path: Path, value: str
) -> None:
    _registry(isolated_repo_root, "unitrans")
    with pytest.raises(SystemExit):
        cli.main(_rescore_args(tmp_path / "ids.txt", tmp_path, "--workers", value))


def test_the_registry_is_what_the_command_schedules_from(
    isolated_repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _registry(isolated_repo_root, "unitrans")
    seen: list[RescoreJob] = []

    def launch(job: RescoreJob, **_: object) -> FakeChild:
        seen.append(job)
        return FakeChild(Clock(), 0.0, 0, "")

    monkeypatch.setattr(rescore, "launch_run", launch)
    ids = tmp_path / "changed.txt"
    ids.write_text("unitrans\n")

    assert cli.main(_rescore_args(ids, tmp_path)) == 0
    assert seen == [job_for(AGENCIES["unitrans"])]
    assert seen[0].hosts == frozenset({"unitrans.example"})
