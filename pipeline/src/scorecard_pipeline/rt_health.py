"""Longitudinal realtime health: uptime and freshness over time.

The realtime category scores one sampling window per daily run. That answers
"how is the feed right now", not "how reliable has it been". No canonical tool
tracks GTFS-Realtime over time (docs/expansion.md, Phase B), so this adds the
missing longitudinal layer: a lightweight monitor that captures a short burst on
a schedule and appends one small observation per run to a per-agency record. From
that record it reports uptime and median header lag over the window.

This is the serverless tier of national realtime monitoring. It runs on a GitHub
Actions cron rather than a continuous worker fleet (ADR 0012): a cron cannot poll
on the spec's 30-60s cadence, so each run takes a small in-run burst and the
record accumulates coverage across runs. The escalation to a worker fleet is
documented, not built, until the agency count and cadence demand it.

Pure observation and summary are unit-tested; the sampling and file I/O are thin.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import repo_root
from .rt import RtWindow

# Keep a bounded history so the record stays small and commit-friendly. At a few
# runs a day this is roughly two months of observations.
MAX_OBSERVATIONS = 200


@dataclass(frozen=True)
class RtObservation:
    """One monitor run's reading for one agency."""

    ts: int  # unix seconds of the capture
    kinds_reachable: int
    kinds_total: int
    worst_lag_seconds: int | None
    coverage_pct: float | None

    @property
    def up(self) -> bool:
        """The realtime endpoint responded at all (at least one feed parsed)."""
        return self.kinds_reachable >= 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "kinds_reachable": self.kinds_reachable,
            "kinds_total": self.kinds_total,
            "worst_lag_seconds": self.worst_lag_seconds,
            "coverage_pct": self.coverage_pct,
        }


def observe(
    window: RtWindow, *, kinds_total: int, scheduled: set[str] | None = None
) -> RtObservation:
    """Derive a lightweight observation from a sampled window.

    ``kinds_total`` is how many realtime feeds the agency publishes, so uptime is
    measured against what exists rather than a fixed three. Coverage is recorded
    only when trips were scheduled during the window; otherwise it is None and
    drops out of the summary rather than reading as zero.
    """
    from .rt import RT_KINDS

    ts = max((s.fetched_at for s in window.samples), default=0)
    kinds_reachable = sum(1 for kind in RT_KINDS if window.kind_ok(kind))
    lags = [window.worst_lag(k) for k in ("trip_updates", "vehicle_positions")]
    known = [lag for lag in lags if lag is not None]
    worst_lag = max(known) if known else None

    coverage_pct: float | None = None
    if scheduled:
        seen = window.seen_trip_ids()
        coverage_pct = round(len(scheduled & seen) / len(scheduled) * 100, 1)

    return RtObservation(
        ts=ts,
        kinds_reachable=kinds_reachable,
        kinds_total=kinds_total,
        worst_lag_seconds=worst_lag,
        coverage_pct=coverage_pct,
    )


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


@dataclass(frozen=True)
class RtHealth:
    """A summary of an agency's realtime reliability over the recorded window."""

    observations: int
    uptime_pct: float
    median_lag_seconds: int | None
    median_coverage_pct: float | None
    first_ts: int | None
    last_ts: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observations": self.observations,
            "uptime_pct": self.uptime_pct,
            "median_lag_seconds": self.median_lag_seconds,
            "median_coverage_pct": self.median_coverage_pct,
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
        }


def summarize(observations: list[RtObservation]) -> RtHealth:
    """Roll a list of observations into uptime and median freshness.

    Uptime is the share of observations where the realtime endpoint responded.
    Median lag and median coverage are taken over the observations that recorded
    one, so a run outside service hours (no scheduled trips) does not distort
    coverage, and a feed without a header timestamp does not distort lag.
    """
    if not observations:
        return RtHealth(0, 0.0, None, None, None, None)
    up = sum(1 for o in observations if o.up)
    uptime_pct = round(up / len(observations) * 100, 1)
    lags = [float(o.worst_lag_seconds) for o in observations if o.worst_lag_seconds is not None]
    covs = [o.coverage_pct for o in observations if o.coverage_pct is not None]
    return RtHealth(
        observations=len(observations),
        uptime_pct=uptime_pct,
        median_lag_seconds=int(_median(lags)) if lags else None,
        median_coverage_pct=round(_median(covs), 1) if covs else None,
        first_ts=min(o.ts for o in observations),
        last_ts=max(o.ts for o in observations),
    )


class RtHealthRecordCorruptError(RuntimeError):
    """An agency's rt-health record file exists but its contents can't be parsed.

    Deliberately distinct from "no record file exists yet". That case is a
    real, legitimate empty history (an agency the monitor hasn't observed
    yet) and ``load_observations`` returns ``[]`` for it. A record that
    exists but fails to parse — a bad git merge leaving conflict markers in
    the tracked JSON, a truncated write, hand editing gone wrong — is
    corruption, not absence, and must never be treated as the same thing:
    ``append_observation`` builds its payload from ``load_observations``, so
    silently reading corruption as "no history" would make the very next
    monitor run overwrite months of recorded uptime with a single new
    observation, with nothing in the logs to say why.
    """


def _state_dir() -> Path:
    return repo_root() / "data" / "rt-health"


def state_path(agency_id: str) -> Path:
    return _state_dir() / f"{agency_id}.json"


def load_observations(agency_id: str) -> list[RtObservation]:
    """The recorded observations for an agency, oldest first; empty when none.

    Raises ``RtHealthRecordCorruptError`` when the record file exists but is
    not valid JSON, so a corrupt file is never mistaken for an empty history
    (see that error's docstring for why that distinction matters).
    """
    path = state_path(agency_id)
    try:
        text = path.read_text()
    except FileNotFoundError:
        return []
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise RtHealthRecordCorruptError(
            f"{path} exists but is not valid JSON; refusing to read it as an empty history."
        ) from exc
    out: list[RtObservation] = []
    for row in data.get("observations", []):
        out.append(
            RtObservation(
                ts=int(row.get("ts", 0)),
                kinds_reachable=int(row.get("kinds_reachable", 0)),
                kinds_total=int(row.get("kinds_total", 0)),
                worst_lag_seconds=row.get("worst_lag_seconds"),
                coverage_pct=row.get("coverage_pct"),
            )
        )
    return out


def append_observation(agency_id: str, observation: RtObservation) -> Path:
    """Append one observation to an agency's record, capping the history."""
    observations = [*load_observations(agency_id), observation][-MAX_OBSERVATIONS:]
    path = state_path(agency_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "agency_id": agency_id,
        "observations": [o.to_dict() for o in observations],
        "summary": summarize(observations).to_dict(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
    return path
