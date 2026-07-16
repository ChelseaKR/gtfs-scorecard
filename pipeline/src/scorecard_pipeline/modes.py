"""Ungraded GTFS service-mode measurements.

``route_type`` is a descriptive GTFS field, not a quality signal.  This module
turns it into one shared contract for artifacts, public APIs, maps, and later
mode-aware presentation.  Unknown values stay visible as ``other`` rather than
being guessed or silently counted as bus service.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .gtfs import read_tables

ROUTE_TYPE_LABEL: dict[int, str] = {
    0: "Tram / light rail",
    1: "Subway / metro",
    2: "Rail",
    3: "Bus",
    4: "Ferry",
    5: "Cable tram",
    6: "Aerial lift",
    7: "Funicular",
    11: "Trolleybus",
    12: "Monorail",
}

_MODE_KEY: dict[int, str] = {
    0: "tram",
    1: "subway",
    2: "rail",
    3: "bus",
    4: "ferry",
    5: "cable_tram",
    6: "aerial_lift",
    7: "funicular",
    11: "trolleybus",
    12: "monorail",
}

_MODE_ORDER = (*_MODE_KEY.values(), "other")
_MODE_LABEL = {key: ROUTE_TYPE_LABEL[family] for family, key in _MODE_KEY.items()} | {
    "other": "Other / unclassified"
}


def route_type_family(raw: str) -> int | None:  # noqa: C901 - explicit spec range mapping
    """Fold a basic or extended GTFS ``route_type`` into a basic family."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value in ROUTE_TYPE_LABEL:
        return value
    if 100 <= value <= 117:
        return 2
    if 200 <= value <= 299:
        return 3
    if 400 <= value <= 405:
        return 1
    if 700 <= value <= 716:
        return 3
    if value == 800:
        return 11
    if 900 <= value <= 906:
        return 0
    if 1000 <= value <= 1021 or 1200 <= value <= 1207:
        return 4
    if 1300 <= value <= 1307:
        return 6
    if 1400 <= value <= 1405:
        return 7
    return None


def route_type_label(raw: str) -> str:
    """Human label for a GTFS route type, with a truthful generic fallback."""
    family = route_type_family(raw)
    return ROUTE_TYPE_LABEL[family] if family is not None else "Transit line"


def route_type_mode(raw: str) -> str:
    """Stable public mode key for a GTFS route type."""
    family = route_type_family(raw)
    return _MODE_KEY[family] if family is not None else "other"


def build_mode_profile(routes: list[dict[str, str]], trips: list[dict[str, str]]) -> dict[str, Any]:
    """Build the deterministic, zero-deduction mode profile for one feed."""
    route_modes: dict[str, str] = {}
    for row in routes:
        route_id = (row.get("route_id") or "").strip()
        if route_id and route_id not in route_modes:
            route_modes[route_id] = route_type_mode(row.get("route_type") or "")

    route_counts = Counter(route_modes.values())
    trip_counts: Counter[str] = Counter()
    for row in trips:
        route_id = (row.get("route_id") or "").strip()
        if route_id in route_modes:
            trip_counts[route_modes[route_id]] += 1

    keys = [key for key in _MODE_ORDER if route_counts[key] > 0]
    total_trips = sum(trip_counts.values())
    modes = [
        {
            "key": key,
            "label": _MODE_LABEL[key],
            "route_count": route_counts[key],
            "trip_count": trip_counts[key],
            "trip_share_pct": (
                round(trip_counts[key] * 100 / total_trips, 1) if total_trips else None
            ),
        }
        for key in keys
    ]
    primary = max(
        keys,
        key=lambda key: (trip_counts[key], route_counts[key], -_MODE_ORDER.index(key)),
        default=None,
    )
    return {
        "measured": True,
        "graded": False,
        "primary_mode": primary,
        "primary_mode_label": _MODE_LABEL.get(primary) if primary else None,
        "modes": modes,
        "route_count": sum(route_counts.values()),
        "trip_count": total_trips,
        "is_multimodal": len(keys) > 1,
        "has_ferry": "ferry" in keys,
        "ferry_only": keys == ["ferry"],
    }


def mode_profile_from_zip(gtfs_zip_path: str) -> dict[str, Any]:
    """Read the mode-relevant tables from a feed zip."""
    tables = read_tables(gtfs_zip_path, ["routes.txt", "trips.txt"])
    return build_mode_profile(tables["routes.txt"], tables["trips.txt"])
