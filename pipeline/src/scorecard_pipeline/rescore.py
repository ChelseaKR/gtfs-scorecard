"""Re-score the intraday refresh's changed feeds a few at a time.

The refresh used to re-score its changed feeds in a shell loop, one
`scorecard run` after another, and most of each run was waiting rather than
working. Measured on 2026-09-18 from Intraday refresh run 35345841643: 91
feeds took 48.0 minutes, of which 24.2 were the realtime sampling windows of
the 25 realtime publishers among them (three samples, thirty seconds apart,
by design), 4.8 were interpreter start-up and 2.4 were downloads. Validating
and scoring, the only part that needs the runner's memory, was 16.5.

This runs several feeds at once so that waiting overlaps, and keeps what the
serial loop guaranteed without having to say so:

* One feed at a time validates and scores. Each child takes the shared turn in
  worklock.py for that part and gives it back only to download or to wait out
  a sampling window, so the validator's memory profile is the serial loop's.
* A ``large_feed`` runs with nothing else in flight, the same isolation the
  daily run gives it with a shard of its own (issue #297).
* No two feeds that share a host name are in flight together, so no agency's
  server sees more concurrent requests than the serial loop sent it.
* Outcomes are counted the way the loop counted them: exit 0 re-scored, exit 2
  "the feed had not changed after all", anything else a failure that keeps
  the feed's last good artifact. Nothing new starts once the deadline has
  passed; what was not started is deferred, by name.

The process launcher, the clock and the sleep are injected so the scheduling
is tested without starting a pipeline.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .config import Agency
from .liveness import host_of
from .worklock import HEAVY_LOCK_ENV

#: `scorecard run` exits 2 for "the feed had not changed after all", an outcome
#: rather than a failure. Only --skip-unchanged produces it, and the intraday
#: tier does not pass that flag today; it is counted correctly anyway so adding
#: the flag later cannot turn a cycle with nothing to do into a failed one.
UNCHANGED_EXIT = 2

#: How to start `scorecard` as a child of this interpreter. Imported rather
#: than run as ``-m scorecard_pipeline.cli`` so the CLI module is never loaded
#: a second time under the name ``__main__``.
SCORECARD_COMMAND: tuple[str, ...] = (
    sys.executable,
    "-c",
    "import sys; from scorecard_pipeline.cli import main; sys.exit(main())",
)


@dataclass(frozen=True)
class RescoreJob:
    """One feed to re-score, with what the scheduler needs to know about it."""

    agency_id: str
    hosts: frozenset[str] = frozenset()
    exclusive: bool = False
    realtime: bool = False


def job_for(agency: Agency) -> RescoreJob:
    """The scheduling facts for one registry record.

    Its hosts are every host a `scorecard run` for it talks to: the schedule
    feed's and each configured realtime endpoint's.
    """
    urls = [agency.static_gtfs_url, *agency.rt_urls.values()]
    return RescoreJob(
        agency_id=agency.id,
        hosts=frozenset(host_of(url) for url in urls if url),
        exclusive=agency.large_feed,
        realtime=bool(agency.rt_urls),
    )


def ordered(jobs: Iterable[RescoreJob]) -> list[RescoreJob]:
    """Large feeds first, then realtime publishers, then the rest, each by id.

    Large feeds run alone, so they go while nothing else is waiting on them.
    Realtime publishers go next because each carries a sampling window of a
    minute or more, and starting the long jobs first is what keeps the batch's
    end close to its total work divided by the workers.
    """
    return sorted(jobs, key=lambda job: (not job.exclusive, not job.realtime, job.agency_id))


def next_startable(
    pending: Sequence[RescoreJob], running: Sequence[RescoreJob]
) -> RescoreJob | None:
    """The first pending job that may start alongside ``running``, if any.

    Nothing starts beside a large feed, and a large feed starts only once
    everything else has finished. A pending large feed is a barrier: later jobs
    do not jump it, or a steady stream of small feeds could hold it off until
    the deadline.
    """
    if any(job.exclusive for job in running):
        return None
    busy = {host for job in running for host in job.hosts}
    for job in pending:
        if job.exclusive:
            return None if running else job
        if not job.hosts & busy:
            return job
    return None


class Child(Protocol):
    """A started `scorecard run`."""

    def poll(self) -> int | None: ...

    def output(self) -> str: ...


@dataclass
class RescoreTally:
    """What the batch did, feed by feed where it matters."""

    attempted: int = 0
    refreshed: int = 0
    failed: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)


def run_batch(
    jobs: Iterable[RescoreJob],
    *,
    workers: int,
    deadline: float,
    launch: Callable[[RescoreJob], Child],
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    emit: Callable[[str], None] = print,
    poll_seconds: float = 1.0,
) -> RescoreTally:
    """Re-score ``jobs``, at most ``workers`` at a time, starting none after ``deadline``.

    Each child's output is printed as one group when it finishes, so the log
    reads feed by feed however the runs interleaved. A job that is running when
    the deadline passes is left to finish, as the serial loop left its current
    feed to finish.
    """
    if workers < 1:
        raise ValueError(f"workers must be at least 1, got {workers}")
    pending = ordered(jobs)
    running: dict[str, tuple[RescoreJob, Child, float]] = {}
    tally = RescoreTally()
    while pending or running:
        progressed = False
        for agency_id, (job, child, started) in list(running.items()):
            code = child.poll()
            if code is None:
                continue
            del running[agency_id]
            _record(job, child, code, now() - started, tally, emit)
            progressed = True
        while pending and len(running) < workers:
            if now() >= deadline:
                tally.deferred.extend(job.agency_id for job in pending)
                pending.clear()
                break
            startable = next_startable(pending, [entry[0] for entry in running.values()])
            if startable is None:
                break
            pending.remove(startable)
            running[startable.agency_id] = (startable, launch(startable), now())
            tally.attempted += 1
            progressed = True
        if running and not progressed:
            sleep(poll_seconds)
    return tally


def _record(
    job: RescoreJob,
    child: Child,
    code: int,
    seconds: float,
    tally: RescoreTally,
    emit: Callable[[str], None],
) -> None:
    emit(f"::group::rescore {job.agency_id} (exit {code}, {seconds:.0f}s)")
    text = child.output().rstrip("\n")
    if text:
        emit(text)
    if code == 0:
        tally.refreshed += 1
    elif code == UNCHANGED_EXIT:
        tally.refreshed += 1
        emit("feed unchanged, keeping last artifact")
    else:
        tally.failed.append(job.agency_id)
        emit(f"::warning title=rescore failed::{job.agency_id} kept its last good artifact")
    emit("::endgroup::")


def report(
    tally: RescoreTally,
    *,
    budget_minutes: int,
    requeued: bool,
    emit: Callable[[str], None] = print,
) -> int:
    """Say what the batch did and return the step's exit code.

    The floor is the one the shell loop had: a cycle that attempted feeds and
    re-scored none of them fails rather than republishing yesterday's corpus
    under today's deployment timestamp. A cycle that deferred everything to
    the budget (nothing attempted) is not that, and still publishes its sweep.
    """
    emit(
        f"re-scored {tally.refreshed} of {tally.attempted} changed feeds "
        f"({len(tally.failed)} failed, {len(tally.deferred)} deferred)"
    )
    if tally.deferred:
        after = (
            "Their liveness records were put back as they were before this cycle's check, "
            "so the next check reads them as changed again."
            if requeued
            else "The next daily run re-scores them."
        )
        emit(
            f"::warning title=refresh budget exhausted::{len(tally.deferred)} changed "
            f"feed(s) were not started this cycle: {', '.join(tally.deferred)}. The rescore "
            f"stopped starting feeds {budget_minutes} minutes into the job so it can still "
            f"publish what it scored. They kept their last good artifact. {after}"
        )
    if tally.attempted > 0 and tally.refreshed == 0:
        emit(
            f"::error::None of the {tally.attempted} changed feeds re-scored this cycle. "
            "Refusing to publish a refresh that refreshed nothing; each feed's cause is "
            "in the warnings above."
        )
        return 1
    if tally.failed:
        emit(
            f"::warning title=partial refresh::{len(tally.failed)} of {tally.attempted} "
            "changed feeds did not re-score this cycle and kept their previous scorecard: "
            f"{', '.join(tally.failed)}."
        )
    return 0


class _RunChild:
    """A `scorecard run` subprocess writing to its own log file."""

    def __init__(self, process: subprocess.Popen[bytes], log: Path) -> None:
        self._process = process
        self._log = log

    def poll(self) -> int | None:
        return self._process.poll()

    def output(self) -> str:
        return self._log.read_text(encoding="utf-8", errors="replace")


def launch_run(
    job: RescoreJob,
    *,
    log_dir: Path,
    heavy_lock: Path | None,
    command: Sequence[str] = SCORECARD_COMMAND,
) -> Child:
    """Start ``scorecard run --agency <id>`` for one job.

    The child gets ``SCORECARD_HEAVY_LOCK`` so it takes turns at the heavy
    part of its score with its siblings; everything else it inherits.
    """
    env = dict(os.environ)
    if heavy_lock is not None:
        env[HEAVY_LOCK_ENV] = str(heavy_lock)
    log = log_dir / f"{job.agency_id}.log"
    with log.open("wb") as sink:
        # Reasoning for S603: argv list, no shell; the id is a registry key
        # that already resolved to a record before this was called.
        process = subprocess.Popen(  # noqa: S603
            [*command, "run", "--agency", job.agency_id],
            stdout=sink,
            stderr=subprocess.STDOUT,
            env=env,
        )
    return _RunChild(process, log)
