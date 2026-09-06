"""High-cadence realtime archiving: the bridge from the cron to a worker fleet.

The cron monitor (rt_health.py) takes a small burst every few hours. The
expansion plan's continuous monitoring polls every feed on the spec's 20-60s
cadence, which the Cal-ITP archiver does with an always-on worker fleet (ADR
0012). This module is the runnable middle: a bounded archiving *session* that
polls a feed at the spec cadence for a fixed window inside one timed run, writing
a high-resolution observation per poll round. A ten-minute session at 20 seconds
is thirty observations, far finer than the cron, and it runs in a single Actions
job with no fleet to operate.

The session schedule is pure and unit-tested; the polling reuses the existing
realtime sampler, and each round is summarized with the same rt_health code, so a
later worker-fleet producer writes the identical record shape.
"""

from __future__ import annotations

import datetime as dt
import logging
import time

from .config import Agency
from .rt import RtWindow, fetch_sample
from .rt_health import RtObservation, append_observation, observe

log = logging.getLogger(__name__)

# Polling etiquette (docs/feeds.md): never poll faster than this, even if asked.
MIN_INTERVAL_SECONDS = 15
# A safety cap so a session can't run unbounded.
MAX_POLLS = 240


def session_plan(duration_seconds: int, interval_seconds: int) -> list[int]:
    """The poll offsets (seconds from the start) for an archiving session.

    Honors the minimum interval and the poll cap, and always polls at least once.
    The offsets are evenly spaced from 0 up to (not past) the duration, so a
    10-minute session at 20s yields 0, 20, ... 580.
    """
    interval = max(interval_seconds, MIN_INTERVAL_SECONDS)
    duration = max(0, duration_seconds)
    count = duration // interval + 1
    count = min(count, MAX_POLLS)
    return [i * interval for i in range(count)]


def _poll_round(agency: Agency) -> RtObservation | None:
    """One poll of every realtime endpoint, summarized as one observation.

    None when not one endpoint could be sampled, so a round our own fetcher
    lost is never recorded as an outage in the agency's uptime record.
    """
    window = RtWindow()
    for kind, url in agency.rt_urls.items():
        window.samples.append(fetch_sample(kind, url))
    # Coverage needs the static feed and stays with the daily score; the archiver
    # tracks uptime and freshness at high resolution.
    return observe(window, kinds_total=len(agency.rt_urls), scheduled=None)


def run_session(
    agency: Agency,
    *,
    duration_seconds: int,
    interval_seconds: int,
    sleeper: object = time.sleep,
    poller: object = None,
) -> int:
    """Run an archiving session for one agency, appending one observation per
    round. ``sleeper`` and ``poller`` are injectable so the loop is testable
    without real time or network. Returns the number of observations recorded.
    """
    if not agency.rt_urls:
        return 0
    offsets = session_plan(duration_seconds, interval_seconds)
    do_poll = poller if poller is not None else _poll_round
    do_sleep = sleeper
    recorded = 0
    previous = 0
    for offset in offsets:
        if offset > previous:
            do_sleep(offset - previous)  # type: ignore[operator]
            previous = offset
        observation = do_poll(agency)  # type: ignore[operator]
        if observation is None:
            log.warning(
                "%s: no realtime endpoint could be sampled this round; recording nothing.",
                agency.id,
            )
            continue
        append_observation(agency.id, observation)
        recorded += 1
    log.info(
        "%s: archiving session recorded %d observations over %ds at %ds cadence.",
        agency.id,
        recorded,
        duration_seconds,
        max(interval_seconds, MIN_INTERVAL_SECONDS),
    )
    return recorded


def session_started_at() -> str:
    """An ISO timestamp for when a session began, for logs and records."""
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
