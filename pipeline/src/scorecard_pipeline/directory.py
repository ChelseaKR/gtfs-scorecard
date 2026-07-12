"""Build the directory dataset the web app's national view reads.

At ~1,200 agencies the front door can't be a flat alphabetical list. This
turns the per-agency artifacts into one slim document the app loads once:

- a national **summary** (grade distribution, how many feeds are expiring or
  expired, the median score) so the landing screen leads with the picture,
- a **by-state** rollup so a manager can browse to their own state and a
  liaison can treat a state as a portfolio,
- per-agency **size tier** and **percentile**, so a lone letter grade reads in
  context ("better than 70% of agencies its size").

It is built at collect time from the artifacts already on disk, so it adds no
per-agency or per-shard work. State comes from each agency's Mobility Database
subdivision (resolved by the caller); size comes from the feed's stop count,
which the completeness metric already records.
"""

from __future__ import annotations

from typing import Any

from . import DATA_ATTRIBUTION, DATA_LICENSE, SCHEMA_VERSION
from ._stats import _percentile
from .location import country_name

# Size tiers by number of stops in the feed. The breakpoints sort the long tail
# of small and rural systems (the audience) away from the big-city feeds, so a
# percentile is computed against true peers rather than against agencies of a
# completely different scale. Stops, not routes, because a feed can be one route
# with hundreds of stops; stop count tracks the data-entry burden a grade
# reflects more closely.
SIZE_TIERS: tuple[tuple[str, str, int], ...] = (
    ("small", "Small (under 100 stops)", 100),
    ("medium", "Medium (100–999 stops)", 1000),
    ("large", "Large (1,000+ stops)", 2**31),
)


def size_tier(stops: int | None) -> str:
    """The size-tier key for a feed's stop count, or "unknown" when unmeasured."""
    if stops is None:
        return "unknown"
    for key, _label, ceiling in SIZE_TIERS:
        if stops < ceiling:
            return key
    return "large"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 1)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 1)


_GRADES = ("A", "B", "C", "D", "F")


def _grade_distribution(records: list[dict[str, Any]]) -> dict[str, int]:
    dist = dict.fromkeys(_GRADES, 0)
    for r in records:
        g = str(r.get("grade", ""))
        if g in dist:
            dist[g] += 1
    return dist


def _state_rollup(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per state: agency count, average score, grade mix, expired count.

    Sorted by agency count so the states a liaison is most likely to want sit at
    the top of the browse grid. Agencies with no resolved state collect under an
    "Unlocated" bucket rather than vanishing.
    """
    by_state: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        # A non-US agency has no legacy US state; keep it findable under its
        # configured country name instead of mixing it into Unlocated. Existing
        # Canadian rows still publish under the exact same "Canada" label.
        country_code = str(r.get("country") or "")
        non_us_country = country_name(country_code) if country_code not in ("", "US") else ""
        place = r.get("state") or non_us_country or "Unlocated"
        by_state.setdefault(place, []).append(r)

    rows: list[dict[str, Any]] = []
    for state, members in by_state.items():
        scores = [float(m["score"]) for m in members if m.get("score") is not None]
        expired = sum(1 for m in members if m.get("expiry_status") in ("lapsed", "stale"))
        rows.append(
            {
                "state": state,
                "agencies": len(members),
                "average_score": round(sum(scores) / len(scores), 1) if scores else None,
                "grade_distribution": _grade_distribution(members),
                "expired": expired,
            }
        )
    rows.sort(key=lambda row: (-row["agencies"], row["state"]))
    return rows


def _rollup_row(
    members: list[dict[str, Any]],
    *,
    code_key: str,
    code: str | None,
    name_key: str,
    name: str,
) -> dict[str, Any]:
    scores = [float(member["score"]) for member in members if member.get("score") is not None]
    return {
        code_key: code,
        name_key: name,
        "agencies": len(members),
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "grade_distribution": _grade_distribution(members),
        "expired": sum(
            1 for member in members if member.get("expiry_status") in ("lapsed", "stale")
        ),
    }


def _country_rollup(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Portable country rows with nested first-level subdivision rows."""
    by_country: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_country.setdefault(str(record.get("country") or ""), []).append(record)

    countries: list[dict[str, Any]] = []
    for country_code, members in by_country.items():
        country = _rollup_row(
            members,
            code_key="country_code",
            code=country_code or None,
            name_key="country_name",
            name=country_name(country_code),
        )
        by_subdivision: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for member in members:
            code = str(member.get("subdivision_code") or "")
            name = str(member.get("subdivision_name") or "")
            by_subdivision.setdefault((code, name), []).append(member)
        subdivisions = [
            _rollup_row(
                subdivision_members,
                code_key="subdivision_code",
                code=code or None,
                name_key="subdivision_name",
                name=name or "Unlocated",
            )
            for (code, name), subdivision_members in by_subdivision.items()
        ]
        subdivisions.sort(
            key=lambda row: (
                -row["agencies"],
                row["subdivision_name"],
                row["subdivision_code"] or "",
            )
        )
        country["subdivisions"] = subdivisions
        countries.append(country)
    countries.sort(
        key=lambda row: (-row["agencies"], row["country_name"], row["country_code"] or "")
    )
    return countries


def build_directory(records: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    """Assemble directory.json from per-agency records.

    Each input record carries at least id, name, grade, score, state,
    expiry_status, days_until_expiry, stops, top_fix, and scorecard_url. This
    fills in each record's size_tier and percentiles (national, and within its
    size tier) and prepends the national and per-state summary. Input order is
    preserved for the agency list; callers sort in the UI.
    """
    national_scores = [float(r["score"]) for r in records if r.get("score") is not None]

    # Peer scores grouped by size tier, so a small agency is ranked against
    # other small agencies and not against a statewide rail operator.
    tier_scores: dict[str, list[float]] = {}
    for r in records:
        r["size_tier"] = size_tier(r.get("stops"))
        if r.get("score") is not None:
            tier_scores.setdefault(r["size_tier"], []).append(float(r["score"]))

    for r in records:
        if r.get("score") is None:
            r["national_percentile"] = None
            r["peer_percentile"] = None
            continue
        score = float(r["score"])
        r["national_percentile"] = _percentile(score, national_scores)
        r["peer_percentile"] = _percentile(score, tier_scores.get(r["size_tier"], []))

    expiring_soon = sum(
        1
        for r in records
        if isinstance(r.get("days_until_expiry"), int | float)
        and not isinstance(r.get("days_until_expiry"), bool)
        and 0 < float(r["days_until_expiry"]) <= 30
    )
    lapsed = sum(1 for r in records if r.get("expiry_status") == "lapsed")
    stale = sum(1 for r in records if r.get("expiry_status") == "stale")

    summary = {
        "agencies": len(records),
        "average_score": round(sum(national_scores) / len(national_scores), 1)
        if national_scores
        else None,
        "median_score": _median(national_scores),
        "grade_distribution": _grade_distribution(records),
        "expiring_soon": expiring_soon,
        "expired": {"lapsed": lapsed, "stale": stale, "total": lapsed + stale},
        "states": _state_rollup(records),
        "countries": _country_rollup(records),
        "size_tiers": [
            {
                "key": key,
                "label": label,
                "agencies": sum(1 for r in records if r["size_tier"] == key),
            }
            for key, label, _ceiling in SIZE_TIERS
        ],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": generated_at,
        "summary": summary,
        "agencies": records,
    }
