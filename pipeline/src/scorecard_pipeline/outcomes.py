"""Measure observed finding clearance and recurrence from artifact history.

These are feed-state observations, not proof of an intervention: whether a
published GTFS finding later clears under the same complete producer contract,
how long it stayed visible, and whether it came back. Open episodes are
right-censored and are never described as failures.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable, Mapping
from statistics import median
from typing import Any, cast

from .comparisons import producer_contract
from .effort_calibration import Episode, agency_episodes

OUTCOME_SCHEMA_VERSION = "1.0"


def _days(ep: Episode) -> int:
    cleared = cast(str, ep.cleared)
    return (dt.date.fromisoformat(cleared) - dt.date.fromisoformat(ep.first_seen)).days


def _valid_agency_artifacts(
    agency_id: str, artifacts_iter: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return this agency's well-formed, chronologically sorted artifacts."""
    artifacts: list[dict[str, Any]] = []
    for artifact in artifacts_iter:
        try:
            artifact_id = str(artifact["agency"]["id"])
            date = str(artifact["snapshot_date"])
            parsed_date = dt.date.fromisoformat(date)
        except (KeyError, TypeError, ValueError):
            continue
        if artifact_id == agency_id and parsed_date.isoformat() == date:
            artifacts.append(artifact)
    return sorted(artifacts, key=lambda artifact: str(artifact["snapshot_date"]))


def _contract_scope_by_date(artifacts: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Number each contiguous complete core producer contract."""
    scope_by_date: dict[str, int] = {}
    active_contract: tuple[str, str, str, str, str] | None = None
    scope = 0
    for artifact in artifacts:
        contract = producer_contract(artifact)[:5]
        if not all(contract):
            active_contract = None
            continue
        if contract != active_contract:
            scope += 1
            active_contract = contract
        scope_by_date[str(artifact["snapshot_date"])] = scope
    return scope_by_date


def build_fix_outcomes(
    histories: Mapping[str, Iterable[dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate resolution outcomes by finding code across agency histories.

    Recurrence is agency-scoped within one contiguous complete producer
    contract: an agency contributes once when a code opens in more than one
    episode without a rubric, validator, scoring-profile, or reader-profile
    boundary between them. Resolution rate is closed episodes divided by all
    observed episodes, with still-open episodes reported separately so readers
    can account for right-censoring.
    """
    by_code: dict[str, list[tuple[str, int, Episode]]] = defaultdict(list)
    observation_start: str | None = None
    observation_end: str | None = None
    for agency_id, artifacts_iter in histories.items():
        artifacts = _valid_agency_artifacts(agency_id, artifacts_iter)
        scope_by_date = _contract_scope_by_date(artifacts)
        dates = [str(a.get("snapshot_date", "")) for a in artifacts if a.get("snapshot_date")]
        if dates:
            observation_start = min([observation_start, *dates] if observation_start else dates)
            observation_end = max([observation_end, *dates] if observation_end else dates)
        for episode in agency_episodes(artifacts):
            by_code[episode.code].append((agency_id, scope_by_date[episode.first_seen], episode))

    codes: dict[str, dict[str, Any]] = {}
    total_episodes = total_resolved = 0
    for code in sorted(by_code):
        entries = by_code[code]
        resolved = [ep for _, _, ep in entries if ep.cleared is not None]
        agencies = {agency_id for agency_id, _, _ in entries}
        episodes_by_scope: dict[tuple[str, int], int] = defaultdict(int)
        for agency_id, scope, _ in entries:
            episodes_by_scope[(agency_id, scope)] += 1
        recurring_agencies = {
            agency_id for (agency_id, _), count in episodes_by_scope.items() if count > 1
        }
        recurrence_agencies = len(recurring_agencies)
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
            "A finding opens when its code appears and clears only when it is absent in a later "
            "check under the same complete producer contract where the category was measured. "
            "Recurrence is counted only within a contiguous producer contract; a contract "
            "change resets the recurrence observation. "
            "A clearance does not establish who acted or why. Open episodes are right-censored."
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
            "Clearance rates are descriptive, not causal. They do not show who changed a feed "
            "or why. Still-open episodes include recent findings that have not had enough time "
            "to clear.",
            "",
        ]
    )
    return "\n".join(lines)
