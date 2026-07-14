"""A covered-set view of how complete agencies' accessibility data is.

The completeness category already records, per agency, what share of a feed's
stops carry ``wheelchair_boarding`` and what share of its trips carry
``wheelchair_accessible`` (see ``completeness.py`` and the accessibility
sub-score, ADR 0006). That answers the question for one agency. Disability and
accessibility advocates, and the program staff who support them, ask a different
question: across the feeds tracked here, how many let a wheelchair user plan a
trip at all, and where are the gaps?

This module rolls the per-agency coverage up into one picture: a distribution
across coverage bands, portable country/subdivision groups, U.S.-state averages,
the feeds with the most complete data, and how many publish no accessibility
data yet. It is pure over the per-agency artifacts the renderer already reads,
so the artifact is reproducible and adds no per-agency work. It changes no
grade; it is framed as coverage to build on rather than feeds to shame.

Rationale and the field-by-field accessibility mapping live in
[docs/rubric.md](../../../docs/rubric.md) and ADR 0006.
"""

from __future__ import annotations

from typing import Any

from .location_rollups import portable_location_fields, portable_location_rollups

# Coverage bands by the share of a feed's stops that carry wheelchair_boarding.
# "Most" sits at 95% rather than 100% because a feed can legitimately omit a
# handful of stops (e.g. flag stops), and a near-complete feed should read as a
# success, not be docked for the tail.
FULL_THRESHOLD = 95.0


def coverage_record(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """Extract one agency's accessibility-coverage record from its artifact.

    Returns the agency id, name, state, the share of stops with
    ``wheelchair_boarding`` set, the share of trips with ``wheelchair_accessible``
    set, and the accessibility sub-score. Returns None when the feed has no
    measured completeness details (an agency not yet scored, or scored before the
    accessibility fields were recorded), so a missing read is skipped rather than
    counted as zero coverage.
    """
    comp = artifact.get("categories", {}).get("completeness", {})
    if comp.get("status") != "measured":
        return None
    details = comp.get("details") or {}
    if details.get("stops") is None:
        return None
    boarding = details.get("wheelchair_boarding_pct")
    if boarding is None:
        return None
    accessible = details.get("wheelchair_accessible_pct")
    access = details.get("accessibility") or {}
    agency = artifact.get("agency", {})
    location = portable_location_fields(agency)
    return {
        "id": agency.get("id", ""),
        "name": agency.get("name", agency.get("id", "")),
        "state": (agency.get("state", "") or "Unlocated") if location["country"] == "US" else "",
        **location,
        "stops": details.get("stops"),
        "wheelchair_boarding_pct": round(float(boarding), 1),
        "wheelchair_accessible_pct": (
            round(float(accessible), 1) if accessible is not None else None
        ),
        "accessibility_score": access.get("score"),
    }


def band_for(boarding_pct: float) -> str:
    """The coverage band for a stop-level wheelchair_boarding share.

    ``none`` when no stop is marked, ``most`` at or above the full threshold, and
    ``some`` in between. Kept as three plain buckets so the covered-set picture
    reads at a glance without a chart.
    """
    if boarding_pct <= 0:
        return "none"
    if boarding_pct >= FULL_THRESHOLD:
        return "most"
    return "some"


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _location_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Accessibility-data coverage for one country or subdivision."""
    boarding = [float(record["wheelchair_boarding_pct"]) for record in records]
    bands = [band_for(value) for value in boarding]
    return {
        "feed_records": len(records),
        # v1 compatibility alias. These rows count feed records, not distinct
        # operating organizations.
        "agencies": len(records),
        "average_boarding_pct": _avg(boarding),
        "none": bands.count("none"),
        "most": bands.count("most"),
    }


def national_coverage(records: list[dict[str, Any]], *, top: int = 10) -> dict[str, Any]:
    """Roll per-agency coverage records up into the covered-set picture.

    Reports how many agencies are covered, the share in each coverage band
    (none / some / most), average stop- and trip-level coverage, portable
    location groups, a U.S.-state breakdown, the most complete feeds, and a
    sample of feeds publishing no accessibility data yet. Everything is derived
    from ``coverage_record`` output, so it is deterministic and safe to re-run.
    ``top`` caps the encouragement and to-do lists so the artifact stays light.
    """
    count = len(records)
    bands = {"none": 0, "some": 0, "most": 0}
    boarding_values: list[float] = []
    accessible_values: list[float] = []
    by_state: dict[str, dict[str, Any]] = {}
    for r in records:
        boarding = float(r["wheelchair_boarding_pct"])
        bands[band_for(boarding)] += 1
        boarding_values.append(boarding)
        if r.get("wheelchair_accessible_pct") is not None:
            accessible_values.append(float(r["wheelchair_accessible_pct"]))
        if r.get("country") != "US":
            continue
        bucket = by_state.setdefault(
            r["state"], {"state": r["state"], "agencies": 0, "_boarding": [], "none": 0, "most": 0}
        )
        bucket["agencies"] += 1
        bucket["_boarding"].append(boarding)
        band = band_for(boarding)
        if band == "none":
            bucket["none"] += 1
        elif band == "most":
            bucket["most"] += 1

    states = []
    for state in sorted(by_state, key=lambda s: (-by_state[s]["agencies"], s)):
        b = by_state[state]
        states.append(
            {
                "state": state,
                "feed_records": b["agencies"],
                "agencies": b["agencies"],
                "average_boarding_pct": _avg(b["_boarding"]),
                "none": b["none"],
                "most": b["most"],
            }
        )

    ranked = sorted(records, key=lambda r: (-float(r["wheelchair_boarding_pct"]), r["name"]))
    most_complete = [
        {
            "id": r["id"],
            "name": r["name"],
            "state": r["state"],
            "country": r["country"],
            "subdivision_code": r["subdivision_code"],
            "subdivision_name": r["subdivision_name"],
            "pct": r["wheelchair_boarding_pct"],
        }
        for r in ranked
        if float(r["wheelchair_boarding_pct"]) > 0
    ][:top]
    no_data = [r for r in records if float(r["wheelchair_boarding_pct"]) <= 0]
    to_improve = [
        {
            "id": r["id"],
            "name": r["name"],
            "state": r["state"],
            "country": r["country"],
            "subdivision_code": r["subdivision_code"],
            "subdivision_name": r["subdivision_name"],
        }
        for r in sorted(no_data, key=lambda r: r["name"])
    ][:top]

    return {
        "measured_feed_record_count": count,
        # v1 compatibility alias. The metric denominator is feed records.
        "agency_count": count,
        "bands": bands,
        "average_boarding_pct": _avg(boarding_values),
        "average_accessible_pct": _avg(accessible_values),
        "states": states,
        "countries": portable_location_rollups(records, _location_summary),
        "most_complete": most_complete,
        "no_data_count": len(no_data),
        "to_improve_sample": to_improve,
    }
