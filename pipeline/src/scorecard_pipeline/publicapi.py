"""A versioned static JSON API over the published data.

The dashboard answers one agency at a time. A state program or an app developer
wants to query across scorecards: which feeds changed this week and how a
location's covered feeds are doing. The architecture decision tree
(docs/expansion.md) says to
serve that from precomputed artifacts before standing up a warehouse, so this
builds a small, versioned, documented API from the same index the site trends
from. Every endpoint is a flat JSON file served from object storage; there is no
query server until interactive multi-tenant queries actually appear (ADR 0013).

All builders are pure over the index dict, so the API is reproducible and safe to
re-run. Per-agency detail already lives at each agency's published artifact, so
the API adds the cross-feed endpoints that do not exist yet: the scorecard list,
named changes, per-state aggregates, and covered-corpus stats. The historical
``leaderboard.json`` path remains for v1 compatibility but publishes no
absolute rankings.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import DATA_ATTRIBUTION, DATA_LICENSE
from .comparisons import (
    MIN_PUBLIC_COMPARISON_COHORT,
    build_comparison_cohort,
    same_producer_contract,
)
from .config import Agency
from .dataset import build_quality_dataset, national_summary
from .identity import build_identity_ledger
from .location import country_name

API_VERSION = "v1"

# How many entries each named change list carries. Enough to be useful on a
# page, small enough to keep the endpoint light.
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
    """The flat feed list plus the contract behind per-row eligibility."""
    return {
        "count": len(dataset.get("rows", [])),
        "fields": dataset.get("generated_fields", []),
        "comparison": dataset.get("comparison", {}),
        "agencies": dataset.get("rows", []),
    }


def _eligible_movers(
    index: dict[str, Any],
    eligible_ids: set[str],
    required_rubric: str,
    trips_map: dict[str, int],
) -> list[dict[str, Any]]:
    """Named same-feed changes that cannot be explained by producer drift."""
    movers: list[dict[str, Any]] = []
    for agency_id, entry in (index.get("agencies") or {}).items():
        history = entry.get("history") or []
        if agency_id not in eligible_ids or len(history) < 2:
            continue
        last, prev = history[-1], history[-2]
        if (
            str(last.get("rubric_version") or "") != required_rubric
            or str(prev.get("rubric_version") or "") != required_rubric
            or not same_producer_contract(prev, last)
        ):
            continue
        if not isinstance(last.get("score"), (int, float)) or not isinstance(
            prev.get("score"), (int, float)
        ):
            continue
        delta = round(float(last["score"]) - float(prev["score"]), 1)
        if abs(delta) < MIN_MOVE:
            continue
        mover: dict[str, Any] = {
            "id": agency_id,
            "name": entry.get("name", agency_id),
            "grade": last.get("grade"),
            "score": last.get("score"),
            "score_delta": delta,
            "date": last.get("date"),
        }
        trips = trips_map.get(agency_id)
        if trips is not None:
            mover["annual_trips"] = trips
        movers.append(mover)
    return movers


def leaderboard(
    index: dict[str, Any],
    dataset: dict[str, Any],
    annual_trips: dict[str, int] | None = None,
    *,
    agencies: Iterable[Agency] | None = None,
    min_cohort: int = MIN_PUBLIC_COMPARISON_COHORT,
) -> dict[str, Any]:
    """V1-compatible change endpoint with absolute standings retired.

    ``top`` and ``bottom`` are always empty. Named movers remain because they
    describe a change in one feed, not its rank against another. They are
    emitted only for current-rubric, fully measured, canonical records whose
    current identity is unambiguous, and only when the two compared history
    points use the same current rubric.

    When ``annual_trips`` is provided, matched change rows carry it as context;
    it does not change which records qualify.
    """
    trips_map = annual_trips or {}

    def _trips(agency_id: str) -> int:
        return trips_map.get(agency_id) or 0

    rows = dataset.get("rows", [])
    scored, comparison = build_comparison_cohort(rows, agencies=agencies)
    comparison.update(
        {
            # Retained so v1 consumers that read the former guardrail metadata
            # do not fail on a missing key. Policy, not cohort size, now keeps
            # the absolute lists empty.
            "minimum_cohort": min_cohort,
            "suppressed": True,
            "suppression_reason": "policy_no_absolute_rankings",
        }
    )
    eligible_ids = {str(row["id"]) for row in scored}
    required_rubric = str(comparison["required_rubric_version"])

    movers = _eligible_movers(index, eligible_ids, required_rubric, trips_map)
    improved = sorted(movers, key=lambda m: (-m["score_delta"], m["id"]))
    if annual_trips:
        declined = sorted(movers, key=lambda m: (m["score_delta"], -_trips(m["id"]), m["id"]))
    else:
        declined = sorted(movers, key=lambda m: (m["score_delta"], m["id"]))
    return {
        "comparison": comparison,
        "top": [],
        "bottom": [],
        "most_improved": [m for m in improved if m["score_delta"] > 0][:LEADERBOARD_SIZE],
        "most_declined": [m for m in declined if m["score_delta"] < 0][:LEADERBOARD_SIZE],
    }


def by_state(
    dataset: dict[str, Any],
    states: dict[str, str],
    locations: dict[str, dict[str, str]] | None = None,
    comparable_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Legacy U.S.-state aggregates: count, median score, and grade distribution.

    State comes from the supplied map (the published catalog). Explicitly
    non-U.S. records are excluded; a U.S. agency without a known state is
    grouped under ``Unlocated``. A missing location record retains the historical
    U.S. interpretation for backwards-compatible direct callers.
    """
    grades = ("A", "B", "C", "D", "F")
    buckets: dict[str, dict[str, Any]] = {}
    location_map = locations or {}
    for row in dataset.get("rows", []):
        agency_id = str(row["id"])
        location = location_map.get(agency_id) or {}
        if str(location.get("country") or "US").strip().upper() != "US":
            continue
        state = states.get(agency_id) or "Unlocated"
        b = buckets.setdefault(
            state,
            {
                "state": state,
                "count": 0,
                "comparison_eligible_count": 0,
                "scores": [],
                "grade_distribution": dict.fromkeys(grades, 0),
            },
        )
        b["count"] += 1
        comparable = comparable_ids is None or agency_id in comparable_ids
        if comparable:
            b["comparison_eligible_count"] += 1
        if comparable and isinstance(row.get("score"), (int, float)):
            b["scores"].append(float(row["score"]))
        if comparable and row.get("grade") in b["grade_distribution"]:
            b["grade_distribution"][row["grade"]] += 1
    out = []
    for state in sorted(buckets):
        b = buckets[state]
        median = _median(b["scores"])
        out.append(
            {
                "state": state,
                "count": b["count"],
                "comparison_eligible_count": b["comparison_eligible_count"],
                "median_score": round(median, 1) if median is not None else None,
                "grade_distribution": b["grade_distribution"],
            }
        )
    return {"states": out}


def _location_summary(
    members: list[dict[str, Any]],
    *,
    comparable_ids: set[str] | None,
    code_key: str,
    code: str | None,
    name_key: str,
    name: str,
) -> dict[str, Any]:
    grades = ("A", "B", "C", "D", "F")
    comparable = [
        member
        for member in members
        if comparable_ids is None or str(member.get("id")) in comparable_ids
    ]
    scores = [
        float(member["score"])
        for member in comparable
        if isinstance(member.get("score"), (int, float))
        and not isinstance(member.get("score"), bool)
    ]
    median = _median(scores)
    distribution = dict.fromkeys(grades, 0)
    for member in comparable:
        if member.get("grade") in distribution:
            distribution[member["grade"]] += 1
    return {
        code_key: code,
        name_key: name,
        "count": len(members),
        "comparison_eligible_count": len(comparable),
        "median_score": round(median, 1) if median is not None else None,
        "grade_distribution": distribution,
    }


def by_location(
    dataset: dict[str, Any],
    locations: dict[str, dict[str, str]],
    comparable_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Country aggregates with nested ISO 3166-2 subdivision aggregates."""
    by_country: dict[str, list[dict[str, Any]]] = {}
    for row in dataset.get("rows", []):
        # The v1 location fields were added after the original U.S. corpus.
        # Omitted historical country values therefore mean US, matching the
        # artifact, directory, MCP, and aggregate compatibility contracts.
        country_code = str((locations.get(str(row["id"])) or {}).get("country") or "US")
        by_country.setdefault(country_code, []).append(row)

    countries: list[dict[str, Any]] = []
    for country_code, members in by_country.items():
        country_summary = _location_summary(
            members,
            comparable_ids=comparable_ids,
            code_key="country_code",
            code=country_code or None,
            name_key="country_name",
            name=country_name(country_code),
        )
        subdivisions: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for member in members:
            location = locations.get(str(member["id"])) or {}
            key = (
                str(location.get("subdivision_code") or ""),
                str(location.get("subdivision_name") or ""),
            )
            subdivisions.setdefault(key, []).append(member)
        country_summary["subdivisions"] = [
            _location_summary(
                subdivision_members,
                comparable_ids=comparable_ids,
                code_key="subdivision_code",
                code=code or None,
                name_key="subdivision_name",
                name=name or "Unlocated",
            )
            for (code, name), subdivision_members in sorted(subdivisions.items())
        ]
        countries.append(country_summary)
    countries.sort(key=lambda row: (row["country_code"] is None, row["country_code"] or ""))
    return {"countries": countries}


def stats_endpoint(
    dataset: dict[str, Any], comparable_ids: set[str] | None = None
) -> dict[str, Any]:
    """Coverage counts plus guarded score statistics."""
    summary = national_summary(dataset)
    comparable_rows = [
        row
        for row in dataset.get("rows", [])
        if comparable_ids is None or str(row.get("id")) in comparable_ids
    ]
    comparable_summary = national_summary({**dataset, "rows": comparable_rows})
    summary["average_score"] = comparable_summary["average_score"]
    summary["grade_distribution"] = comparable_summary["grade_distribution"]
    summary["comparison_eligible_count"] = len(comparable_rows)
    scores = [
        float(r["score"]) for r in comparable_rows if isinstance(r.get("score"), (int, float))
    ]
    median = _median(scores)
    summary["median_score"] = round(median, 1) if median is not None else None
    return summary


def coverage_endpoint(
    index: dict[str, Any], dataset: dict[str, Any], agencies: Iterable[Agency]
) -> dict[str, Any]:
    """Explicit registry and publication denominators.

    Feed records, organization keys, rendered scorecards, and scored rows are
    different populations. Keeping them in one named endpoint prevents a
    consumer from treating the backwards-compatible ``stats.agency_count`` as
    all four. Organization keys that fall back to a feed id remain explicitly
    provisional until a curator supplies ``organization_id``.
    """
    identity = build_identity_ledger(agencies)
    rows = dataset.get("rows", [])
    return {
        "configured_feed_records": identity["configured_feed_records"],
        "active_canonical_feed_records": identity["active_canonical_feed_records"],
        "distinct_organization_keys": identity["distinct_organization_keys"],
        "provisional_organization_keys": identity["provisional_organization_keys"],
        "published_scorecard_pages": len(index.get("agencies") or {}),
        "scored_latest_rows": sum(
            isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool)
            for row in rows
        ),
        "definitions": {
            "configured_feed_records": (
                "Entries in the curated feed registry, including inactive records and aliases."
            ),
            "active_canonical_feed_records": (
                "Active registry entries that are not aliases of another feed record."
            ),
            "distinct_organization_keys": (
                "Distinct explicit organization IDs or provisional feed-ID fallbacks "
                "among active canonical feeds."
            ),
            "provisional_organization_keys": (
                "Active canonical feeds still using their feed ID because no curated "
                "organization ID is recorded."
            ),
            "published_scorecard_pages": (
                "Feed scorecard entries present in the published artifact index, including "
                "retained pages for records no longer configured."
            ),
            "scored_latest_rows": "Published latest rows whose overall score is numeric.",
        },
    }


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
            "changes": f"{base_url}/data/artifacts/changes/latest.json",
            "by_state": f"{base}/by-state.json",
            "by_location": f"{base}/by-location.json",
            "stats": f"{base}/stats.json",
            "coverage": f"{base}/coverage.json",
            "equity": f"{base}/equity.json",
            "canada_equity": f"{base}/canada-equity.json",
            "accessibility": f"{base}/accessibility.json",
            "adoption": f"{base}/adoption.json",
            "realtime": f"{base}/realtime.json",
            "problems": f"{base}/problems.json",
            "trend": f"{base}/trend.json",
            "status": f"{base}/status.json",
            "ntd_readiness": f"{base_url}/ntd.json",
            "agency_detail": f"{base_url}/data/artifacts/{{agency_id}}/latest.json",
        },
        "notes": (
            "Static JSON over precomputed artifacts. Per-agency detail is each "
            "feed record's published artifact. Absolute rankings and individual "
            "percentiles are not published. Named changes and score aggregates apply "
            "documented rubric and identity guardrails. CC BY 4.0; cite the attribution."
        ),
    }


def build_api(
    index: dict[str, Any],
    *,
    agencies: Iterable[Agency],
    states: dict[str, str],
    locations: dict[str, dict[str, str]],
    base_url: str,
    generated_at: str,
) -> dict[str, dict[str, Any]]:
    """Build every API endpoint as a {relative_path: payload} map for the writer."""
    agency_list = list(agencies)
    dataset = build_quality_dataset(index, agencies=agency_list)
    comparable_rows = [
        row for row in dataset.get("rows", []) if row.get("comparison_eligible") is True
    ]
    comparison = dataset["comparison"]
    comparable_ids = {str(row["id"]) for row in comparable_rows}
    state_payload = by_state(dataset, states, locations, comparable_ids)
    state_payload["comparison"] = comparison
    location_payload = by_location(dataset, locations, comparable_ids)
    location_payload["comparison"] = comparison
    stats_payload = stats_endpoint(dataset, comparable_ids)
    stats_payload["comparison"] = comparison
    return {
        "index.json": api_index(base_url, generated_at),
        "agencies.json": agencies_endpoint(dataset),
        "leaderboard.json": leaderboard(index, dataset, agencies=agency_list),
        "by-state.json": state_payload,
        "by-location.json": location_payload,
        "stats.json": stats_payload,
        "coverage.json": coverage_endpoint(index, dataset, agency_list),
    }
