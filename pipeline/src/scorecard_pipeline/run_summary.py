"""Per-shard and merged run-health summaries for the public /status/ page.

FIX-11 (docs/ideation/02-large-scale-fixes.md): the daily pipeline's own
operational outcome -- which agencies scored, which reused yesterday's
artifact because a conditional GET said the feed was unchanged, which were
unreachable, which fell back to the Mobility Database mirror, which reused a
cached validator report -- was visible only in private Actions logs. If one of
twelve shards failed, the agencies it owned silently kept showing yesterday's
data with no public signal anywhere.

Each `scorecard run` invocation (the CI shard loop runs one process per
agency, so scoring cannot abort the whole shard on one agency's failure)
appends one outcome line to an ndjson log via `--outcome-out`. At the end of
its loop, a shard turns that log into a small `run-summary.json`
(`scorecard run-summary build`). The collect job then merges every shard's
summary into the one artifact `/status/` reads,
`data/artifacts/run/latest.json` (`scorecard run-summary merge`).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import Any, Literal

Outcome = Literal["scored", "reused", "unreachable"]

# Above this fraction of a run's agencies going unreachable, /status/ badges
# the run as degraded rather than silently showing yesterday's data for all of
# them (the ideation doc's ">N% not refreshed" trigger).
DEGRADED_THRESHOLD = 0.05


@dataclasses.dataclass(frozen=True)
class AgencyOutcome:
    """What happened when the pipeline tried to score one agency this run."""

    agency_id: str
    outcome: Outcome
    mirrored: bool = False
    cache_hit: bool = False
    wall_seconds: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "agency_id": self.agency_id,
            "outcome": self.outcome,
            "mirrored": self.mirrored,
            "cache_hit": self.cache_hit,
            "wall_seconds": round(self.wall_seconds, 3),
        }

    @staticmethod
    def from_json(d: dict[str, Any]) -> AgencyOutcome:
        return AgencyOutcome(
            agency_id=d["agency_id"],
            outcome=d["outcome"],
            mirrored=bool(d.get("mirrored", False)),
            cache_hit=bool(d.get("cache_hit", False)),
            wall_seconds=float(d.get("wall_seconds", 0.0)),
        )


def append_outcome(path: str | Path, outcome: AgencyOutcome) -> None:
    """Append one outcome as an ndjson line.

    Each shard's agencies are scored by separate short-lived `scorecard run`
    processes (see module docstring), so outcomes accumulate across many
    invocations into one file rather than being collected in memory by a
    single process.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(outcome.to_json(), sort_keys=True) + "\n")


def read_outcomes(path: str | Path) -> list[AgencyOutcome]:
    """Read an ndjson outcome log. Missing file reads as no outcomes (a shard
    that scored zero agencies, e.g. an empty matrix slice)."""
    p = Path(path)
    if not p.exists():
        return []
    outcomes = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        outcomes.append(AgencyOutcome.from_json(json.loads(line)))
    return outcomes


def build_shard_summary(
    shard: str,
    outcomes: list[AgencyOutcome],
    started_at: dt.datetime,
    finished_at: dt.datetime,
) -> dict[str, Any]:
    """One shard's run-summary.json: outcome counts plus the unreachable
    agency ids, so /status/ can name them, not just count them."""
    scored = [o for o in outcomes if o.outcome == "scored"]
    reused = [o for o in outcomes if o.outcome == "reused"]
    unreachable = [o for o in outcomes if o.outcome == "unreachable"]
    return {
        "shard": shard,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "wall_clock_seconds": round((finished_at - started_at).total_seconds(), 1),
        "agency_count": len(outcomes),
        "scored": len(scored),
        "reused": len(reused),
        "unreachable": len(unreachable),
        "mirrored": sum(1 for o in outcomes if o.mirrored),
        "cache_hit": sum(1 for o in outcomes if o.cache_hit),
        "unreachable_agencies": sorted(o.agency_id for o in unreachable),
    }


def merge_run_summaries(
    summaries: list[dict[str, Any]],
    generated_at: dt.datetime,
    *,
    expected_shard_count: int | None = None,
) -> dict[str, Any]:
    """Merge every shard's run-summary.json into the one artifact /status/ reads.

    ``expected_shard_count`` is how many shards the run planned, which the
    merge cannot learn from the summaries themselves: a shard whose runner was
    killed uploads nothing, so it is absent from ``summaries`` rather than
    present and empty.

    Without that number this merge was structurally unable to report the one
    failure the module docstring says it exists to make visible, "if one of
    twelve shards failed, the agencies it owned silently kept showing
    yesterday's data with no public signal anywhere". Every total, including
    ``agency_count``, is summed over the shards that did report, so a dead
    shard shrank the denominator by exactly the agencies it lost and
    ``degraded`` stayed false. The daily run has ended that way on the same
    shard every day since 2026-08-17 and /status/ said "Run completed".

    So the merge now fails loudly in the only sense a report can: a shortfall
    against ``expected_shard_count`` degrades the run and is named in
    ``degraded_reasons``. Totals still undercount, because the lost outcomes
    genuinely are not knowable here, but the run no longer claims to be whole.
    ``expected_shard_count=None`` means the caller did not say, and is
    reported as such rather than assumed to be ``len(shards)``.
    """
    shards = sorted(summaries, key=lambda s: str(s.get("shard", "")))
    total_scored = sum(s.get("scored", 0) for s in shards)
    total_reused = sum(s.get("reused", 0) for s in shards)
    total_unreachable = sum(s.get("unreachable", 0) for s in shards)
    total_mirrored = sum(s.get("mirrored", 0) for s in shards)
    total_cache_hit = sum(s.get("cache_hit", 0) for s in shards)
    total_agencies = total_scored + total_reused + total_unreachable
    unreachable_agencies = sorted(
        {aid for s in shards for aid in s.get("unreachable_agencies", [])}
    )
    fraction_unreachable = (total_unreachable / total_agencies) if total_agencies else 0.0
    missing_shards = (
        max(0, expected_shard_count - len(shards)) if expected_shard_count is not None else 0
    )
    degraded_reasons: list[str] = []
    if missing_shards:
        # "1 of 32 shards", not "1 of 32 shard": the noun agrees with the
        # denominator, which is what a reader is being asked to compare against.
        owned = "it owned" if missing_shards == 1 else "they owned"
        degraded_reasons.append(
            f"{missing_shards} of {expected_shard_count} shards reported no outcomes for "
            f"this run. The feed records {owned} kept their previous scorecard and are not "
            "counted in the totals below."
        )
    if fraction_unreachable > DEGRADED_THRESHOLD:
        degraded_reasons.append(
            f"{total_unreachable} of {total_agencies} attempted feed records could not be "
            f"refreshed, above the {round(DEGRADED_THRESHOLD * 100)}% warning threshold."
        )
    return {
        "generated_at": generated_at.isoformat(),
        "shard_count": len(shards),
        "expected_shard_count": expected_shard_count,
        "missing_shard_count": missing_shards,
        "agency_count": total_agencies,
        "scored": total_scored,
        "reused": total_reused,
        "unreachable": total_unreachable,
        "mirrored": total_mirrored,
        "cache_hit": total_cache_hit,
        "unreachable_agencies": unreachable_agencies,
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
        "degraded_threshold": DEGRADED_THRESHOLD,
        "shards": shards,
    }
