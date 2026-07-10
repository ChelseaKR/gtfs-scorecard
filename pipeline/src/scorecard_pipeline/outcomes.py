"""Measure observed finding resolution and recurrence from artifact history.

These are product outcomes, not page views: whether a published GTFS finding
later clears under a measured category, how long that took, and whether it came
back. Open episodes are right-censored and are never described as failures.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable, Mapping
from statistics import median
from typing import Any, cast

from .effort_calibration import Episode, agency_episodes

OUTCOME_SCHEMA_VERSION = "1.0"


def _days(ep: Episode) -> int:
    cleared = cast(str, ep.cleared)
    return (dt.date.fromisoformat(cleared) - dt.date.fromisoformat(ep.first_seen)).days


def build_fix_outcomes(
    histories: Mapping[str, Iterable[dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate resolution outcomes by finding code across agency histories.

    Recurrence is agency-scoped: an agency contributes once when a code opens
    in more than one episode. Resolution rate is closed episodes divided by all
    observed episodes, with still-open episodes reported separately so readers
    can account for right-censoring.
    """
    by_code: dict[str, list[tuple[str, Episode]]] = defaultdict(list)
    observation_start: str | None = None
    observation_end: str | None = None
    for agency_id, artifacts_iter in histories.items():
        artifacts = sorted(artifacts_iter, key=lambda a: str(a.get("snapshot_date", "")))
        dates = [str(a.get("snapshot_date", "")) for a in artifacts if a.get("snapshot_date")]
        if dates:
            observation_start = min([observation_start, *dates] if observation_start else dates)
            observation_end = max([observation_end, *dates] if observation_end else dates)
        for episode in agency_episodes(artifacts):
            by_code[episode.code].append((agency_id, episode))

    codes: dict[str, dict[str, Any]] = {}
    total_episodes = total_resolved = 0
    for code in sorted(by_code):
        entries = by_code[code]
        resolved = [ep for _, ep in entries if ep.cleared is not None]
        agencies = {agency_id for agency_id, _ in entries}
        episodes_by_agency: dict[str, int] = defaultdict(int)
        for agency_id, _ in entries:
            episodes_by_agency[agency_id] += 1
        recurrence_agencies = sum(count > 1 for count in episodes_by_agency.values())
        days = sorted(_days(ep) for ep in resolved)
        total_episodes += len(entries)
        total_resolved += len(resolved)
        record: dict[str, Any] = {
            "agencies_observed": len(agencies),
            "episodes": len(entries),
            "resolved_episodes": len(resolved),
            "still_open_episodes": len(entries) - len(resolved),
            "observed_resolution_rate_pct": round(100 * len(resolved) / len(entries), 1),
            "agencies_with_recurrence": recurrence_agencies,
            "observed_recurrence_rate_pct": round(100 * recurrence_agencies / len(agencies), 1),
        }
        if days:
            record.update(
                {
                    "median_days_to_resolution": round(median(days), 1),
                    "fastest_days_to_resolution": days[0],
                    "slowest_days_to_resolution": days[-1],
                }
            )
        codes[code] = record

    return {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "method": (
            "A finding opens when its code appears and resolves only when it is absent in a later "
            "run where the same category was measured. Open episodes are right-censored."
        ),
        "observation_window": {"start": observation_start, "end": observation_end},
        "agencies_with_history": len(histories),
        "overall": {
            "episodes": total_episodes,
            "resolved_episodes": total_resolved,
            "still_open_episodes": total_episodes - total_resolved,
            "observed_resolution_rate_pct": (
                round(100 * total_resolved / total_episodes, 1) if total_episodes else None
            ),
        },
        "codes": codes,
    }


def render_fix_outcomes_markdown(report: dict[str, Any], *, min_episodes: int = 1) -> str:
    """Render a compact internal decision report, most-observed code first."""
    overall = report["overall"]
    window = report["observation_window"]
    lines = [
        "# GTFS finding outcome report",
        "",
        f"Observation window: {window.get('start') or 'none'} to {window.get('end') or 'none'}  ",
        f"Episodes: {overall['episodes']} · resolved: {overall['resolved_episodes']} · "
        f"still open: {overall['still_open_episodes']}",
        "",
        "| Finding code | Agencies | Episodes | Resolved | Still open | Median days | Recurrence |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    rows = [
        (code, stats)
        for code, stats in report["codes"].items()
        if int(stats["episodes"]) >= min_episodes
    ]
    rows.sort(key=lambda row: (-int(row[1]["episodes"]), row[0]))
    for code, stats in rows:
        median_days = stats.get("median_days_to_resolution", "—")
        lines.append(
            f"| {code} | {stats['agencies_observed']} | {stats['episodes']} | "
            f"{stats['resolved_episodes']} | {stats['still_open_episodes']} | {median_days} | "
            f"{stats['observed_recurrence_rate_pct']}% |"
        )
    lines.extend(
        [
            "",
            "Resolution rates are descriptive, not causal. Still-open episodes include recent "
            "findings that have not had enough time to clear.",
            "",
        ]
    )
    return "\n".join(lines)
