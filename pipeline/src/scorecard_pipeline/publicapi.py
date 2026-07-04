"""A versioned static JSON API over the published data.

The dashboard answers one agency at a time. A state program or an app developer
wants to query across agencies: who ranks where, which feeds improved this week,
how a state compares. The architecture decision tree (docs/expansion.md) says to
serve that from precomputed artifacts before standing up a warehouse, so this
builds a small, versioned, documented API from the same index the site trends
from. Every endpoint is a flat JSON file served from object storage; there is no
query server until interactive multi-tenant queries actually appear (ADR 0013).

All builders are pure over the index dict, so the API is reproducible and safe to
re-run. Per-agency detail already lives at each agency's published artifact, so
the API adds the cross-agency endpoints that do not exist yet: the agency list,
a leaderboard, per-state aggregates, and national stats.
"""

from __future__ import annotations

from typing import Any

from . import DATA_ATTRIBUTION, DATA_LICENSE
from .dataset import build_quality_dataset, national_summary

API_VERSION = "v1"

# How many entries each leaderboard list carries. Enough to be useful on a page,
# small enough to keep the endpoint light.
LEADERBOARD_SIZE = 25
# A score move smaller than this is noise, not a trend; mirrors the movers feed.
MIN_MOVE = 1.0


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def agencies_endpoint(dataset: dict[str, Any]) -> dict[str, Any]:
    """The flat agency list: one compact record per agency, latest check."""
    return {
        "count": len(dataset.get("rows", [])),
        "fields": dataset.get("generated_fields", []),
        "agencies": dataset.get("rows", []),
    }


def leaderboard(index: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    """Cross-agency standings: best and worst by score, and the biggest movers.

    Best and worst rank the latest scores. Movers compare each agency's latest
    score to its previous check, so a feed that just improved or regressed shows
    up, with moves below the noise floor dropped. Names ride along so a consumer
    can render the board without a second lookup.
    """
    scored = [r for r in dataset.get("rows", []) if isinstance(r.get("score"), (int, float))]
    by_score = sorted(scored, key=lambda r: (-float(r["score"]), r["id"]))

    def _entry(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row.get("name"),
            "grade": row.get("grade"),
            "score": row.get("score"),
        }

    movers: list[dict[str, Any]] = []
    for agency_id, entry in (index.get("agencies") or {}).items():
        history = entry.get("history") or []
        if len(history) < 2:
            continue
        last, prev = history[-1], history[-2]
        if not isinstance(last.get("score"), (int, float)) or not isinstance(
            prev.get("score"), (int, float)
        ):
            continue
        delta = round(float(last["score"]) - float(prev["score"]), 1)
        if abs(delta) < MIN_MOVE:
            continue
        movers.append(
            {
                "id": agency_id,
                "name": entry.get("name", agency_id),
                "grade": last.get("grade"),
                "score": last.get("score"),
                "score_delta": delta,
                "date": last.get("date"),
            }
        )
    improved = sorted(movers, key=lambda m: (-m["score_delta"], m["id"]))
    declined = sorted(movers, key=lambda m: (m["score_delta"], m["id"]))
    return {
        "top": [_entry(r) for r in by_score[:LEADERBOARD_SIZE]],
        "bottom": [_entry(r) for r in by_score[-LEADERBOARD_SIZE:][::-1]],
        "most_improved": [m for m in improved if m["score_delta"] > 0][:LEADERBOARD_SIZE],
        "most_declined": [m for m in declined if m["score_delta"] < 0][:LEADERBOARD_SIZE],
    }


def by_state(dataset: dict[str, Any], states: dict[str, str]) -> dict[str, Any]:
    """Per-state aggregates: agency count, median score, and grade distribution.

    State comes from the supplied map (the published catalog), so an agency
    without a known state is grouped under "Unlocated" rather than dropped.
    """
    grades = ("A", "B", "C", "D", "F")
    buckets: dict[str, dict[str, Any]] = {}
    for row in dataset.get("rows", []):
        state = states.get(row["id"]) or "Unlocated"
        b = buckets.setdefault(
            state,
            {
                "state": state,
                "count": 0,
                "scores": [],
                "grade_distribution": dict.fromkeys(grades, 0),
            },
        )
        b["count"] += 1
        if isinstance(row.get("score"), (int, float)):
            b["scores"].append(float(row["score"]))
        if row.get("grade") in b["grade_distribution"]:
            b["grade_distribution"][row["grade"]] += 1
    out = []
    for state in sorted(buckets):
        b = buckets[state]
        median = _median(b["scores"])
        out.append(
            {
                "state": state,
                "count": b["count"],
                "median_score": round(median, 1) if median is not None else None,
                "grade_distribution": b["grade_distribution"],
            }
        )
    return {"states": out}


def stats_endpoint(dataset: dict[str, Any]) -> dict[str, Any]:
    """National headline statistics: count, average and median score, grade mix."""
    summary = national_summary(dataset)
    scores = [
        float(r["score"])
        for r in dataset.get("rows", [])
        if isinstance(r.get("score"), (int, float))
    ]
    median = _median(scores)
    summary["median_score"] = round(median, 1) if median is not None else None
    return summary


def api_index(base_url: str, generated_at: str) -> dict[str, Any]:
    """The API's self-description: version, endpoints, license, and provenance."""
    base = f"{base_url}/api/{API_VERSION}"
    return {
        "version": API_VERSION,
        "generated_at": generated_at,
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "endpoints": {
            "agencies": f"{base}/agencies.json",
            "leaderboard": f"{base}/leaderboard.json",
            "by_state": f"{base}/by-state.json",
            "stats": f"{base}/stats.json",
            "equity": f"{base}/equity.json",
            "canada_equity": f"{base}/canada-equity.json",
            "accessibility": f"{base}/accessibility.json",
            "adoption": f"{base}/adoption.json",
            "realtime": f"{base}/realtime.json",
            "problems": f"{base}/problems.json",
            "trend": f"{base}/trend.json",
            "ntd_readiness": f"{base_url}/ntd.json",
            "agency_detail": f"{base_url}/data/artifacts/{{agency_id}}/latest.json",
        },
        "notes": (
            "Static JSON over precomputed artifacts. Per-agency detail is each "
            "agency's published artifact. CC BY 4.0; cite the attribution."
        ),
    }


def build_api(
    index: dict[str, Any],
    *,
    states: dict[str, str],
    base_url: str,
    generated_at: str,
) -> dict[str, dict[str, Any]]:
    """Build every API endpoint as a {relative_path: payload} map for the writer."""
    dataset = build_quality_dataset(index)
    return {
        "index.json": api_index(base_url, generated_at),
        "agencies.json": agencies_endpoint(dataset),
        "leaderboard.json": leaderboard(index, dataset),
        "by-state.json": by_state(dataset, states),
        "stats.json": stats_endpoint(dataset),
    }
