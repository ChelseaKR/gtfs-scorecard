"""Portable country and subdivision grouping for cross-agency rollups.

The adoption, accessibility, and realtime APIs publish different metrics, but
their geographic contract is the same: an additive ``countries`` array with
nested ISO 3166-2 subdivisions. Legacy artifacts that omit ``country`` are US
records by the public API contract. Unknown subdivisions stay visible under an
``Unlocated`` row instead of being dropped or guessed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .location import country_name, normalize_subdivision

LocationSummary = Callable[[list[dict[str, Any]]], dict[str, Any]]


def portable_location_fields(source: dict[str, Any]) -> dict[str, str]:
    """Canonical portable location fields copied from a record-like mapping."""
    country = str(source.get("country") or "US").strip().upper()
    subdivision_code = str(source.get("subdivision_code") or "").strip().upper()
    subdivision_name = str(source.get("subdivision_name") or "").strip()
    if country == "US" and not subdivision_code and not subdivision_name:
        # Most historical U.S. artifacts predate ISO subdivision fields but do
        # carry the resolved full state name (and some callers carry the postal
        # abbreviation). Preserve that useful geography in the additive
        # country rollups instead of collapsing the original corpus under one
        # Unlocated row.
        legacy_state = str(source.get("state") or "").strip()
        subdivision_code, subdivision_name = normalize_subdivision("US", legacy_state)
        if not subdivision_code and len(legacy_state) == 2 and legacy_state.isalpha():
            subdivision_code, subdivision_name = normalize_subdivision(
                "US", f"US-{legacy_state.upper()}"
            )
    return {
        "country": country,
        "subdivision_code": subdivision_code,
        "subdivision_name": subdivision_name,
    }


def portable_location_rollups(
    records: list[dict[str, Any]], summarize: LocationSummary
) -> list[dict[str, Any]]:
    """Group records by country and subdivision using a metric-specific summary.

    ``summarize`` receives the members at one geographic level and returns that
    metric's fields. This helper owns only the shared location keys, unknown-row
    policy, and deterministic ordering.
    """
    by_country: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        country = portable_location_fields(record)["country"]
        by_country.setdefault(country, []).append(record)

    countries: list[dict[str, Any]] = []
    for country_code in sorted(by_country):
        members = by_country[country_code]
        row: dict[str, Any] = {
            "country_code": country_code,
            "country_name": country_name(country_code, country_code),
            **summarize(members),
        }
        by_subdivision: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for member in members:
            location = portable_location_fields(member)
            key = (location["subdivision_code"], location["subdivision_name"])
            by_subdivision.setdefault(key, []).append(member)
        subdivisions: list[dict[str, Any]] = []
        for (code, name), subdivision_members in sorted(
            by_subdivision.items(),
            key=lambda item: (not item[0][0], item[0][0], item[0][1]),
        ):
            subdivisions.append(
                {
                    "subdivision_code": code or None,
                    "subdivision_name": name or code or "Unlocated",
                    **summarize(subdivision_members),
                }
            )
        row["subdivisions"] = subdivisions
        countries.append(row)
    return countries
