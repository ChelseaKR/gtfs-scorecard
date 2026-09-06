"""Ungraded ferry capability measurements for producer and consumer decisions.

The profile follows the adopted GTFS Schedule field semantics documented at
https://gtfs.org/documentation/schedule/reference/. In particular, blank or
``0`` values for ``wheelchair_*``, ``bikes_allowed``, and ``cars_allowed`` mean
unknown, never "not allowed". ``stop_access`` is measured only where the
specification permits it: a boardable child location with ``parent_station``.

These measurements never change a category score or grade. They describe the
ferry subset of a feed; fare and realtime publication remain feed-level facts
and are labelled that way in the public contract.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable
from contextlib import closing
from typing import Any

from .fares import detect_fares
from .gtfs import TableTooLargeError, iter_table_rows, read_tables
from .modes import route_type_mode

log = logging.getLogger(__name__)

_BOARDABLE_LOCATION_TYPES = {"", "0"}
_STATED_ENUM_VALUES = {"1", "2"}
_REALTIME_KIND_ORDER = ("trip_updates", "vehicle_positions", "service_alerts")


def _pct(count: int, total: int) -> float | None:
    return round(count * 100 / total, 1) if total else None


def _enum_coverage(rows: list[dict[str, str]], field: str) -> dict[str, Any]:
    """Measure a GTFS yes/no/unknown enum without collapsing unknown into no."""
    values = [(row.get(field) or "").strip() for row in rows]
    stated = sum(value in _STATED_ENUM_VALUES for value in values)
    allowed = sum(value == "1" for value in values)
    not_allowed = sum(value == "2" for value in values)
    total = len(rows)
    return {
        "total_count": total,
        "stated_count": stated,
        "stated_pct": _pct(stated, total),
        "allowed_count": allowed,
        "allowed_pct": _pct(allowed, total),
        "not_allowed_count": not_allowed,
        "not_allowed_pct": _pct(not_allowed, total),
    }


def _realtime_kinds(configured: Collection[str]) -> list[str]:
    values = {str(kind).strip() for kind in configured if str(kind).strip()}
    return [kind for kind in _REALTIME_KIND_ORDER if kind in values] + sorted(
        values.difference(_REALTIME_KIND_ORDER)
    )


def build_ferry_profile(
    routes: list[dict[str, str]],
    trips: list[dict[str, str]],
    stop_times: Iterable[dict[str, str]],
    stops: list[dict[str, str]],
    *,
    fare_profile: dict[str, Any],
    fare_free: bool = False,
    configured_realtime_kinds: Collection[str] = (),
) -> dict[str, Any] | None:
    """Build a zero-deduction profile for the ferry subset of a GTFS feed.

    ``stop_times`` is read once and only for the ferry trips' stop ids, so it
    may be any iterable of rows -- a list in tests, a streamed reader in the
    pipeline. It is also read last: a feed with no ferry routes returns before
    touching it, which is what keeps a lazy reader from opening the largest
    table in the archive for the feeds that have no ferry to describe.
    """
    ferry_route_ids = {
        (row.get("route_id") or "").strip()
        for row in routes
        if route_type_mode(row.get("route_type") or "") == "ferry"
        and (row.get("route_id") or "").strip()
    }
    if not ferry_route_ids:
        return None

    ferry_trips = [row for row in trips if (row.get("route_id") or "").strip() in ferry_route_ids]
    ferry_trip_ids = {
        (row.get("trip_id") or "").strip()
        for row in ferry_trips
        if (row.get("trip_id") or "").strip()
    }
    served_stop_ids = {
        (row.get("stop_id") or "").strip()
        for row in stop_times
        if (row.get("trip_id") or "").strip() in ferry_trip_ids
        and (row.get("stop_id") or "").strip()
    }
    boarding_locations = [
        row
        for row in stops
        if (row.get("stop_id") or "").strip() in served_stop_ids
        and (row.get("location_type") or "").strip() in _BOARDABLE_LOCATION_TYPES
    ]
    parented_locations = [
        row for row in boarding_locations if (row.get("parent_station") or "").strip()
    ]
    parent_ids = {
        (row.get("parent_station") or "").strip()
        for row in parented_locations
        if (row.get("parent_station") or "").strip()
    }
    station_ids = {
        (row.get("stop_id") or "").strip()
        for row in stops
        if (row.get("location_type") or "").strip() == "1"
        and (row.get("stop_id") or "").strip() in parent_ids
    }

    stop_access_values = [(row.get("stop_access") or "").strip() for row in parented_locations]
    stop_access_stated = sum(value in {"0", "1"} for value in stop_access_values)
    stop_access_direct = sum(value == "1" for value in stop_access_values)
    stop_access_station = sum(value == "0" for value in stop_access_values)
    configured_kinds = _realtime_kinds(configured_realtime_kinds)

    return {
        "measured": True,
        "graded": False,
        "scope": "ferry_routes_and_trips",
        "route_count": len(ferry_route_ids),
        "trip_count": len(ferry_trips),
        "terminal_hierarchy": {
            "boarding_location_count": len(boarding_locations),
            "parented_boarding_location_count": len(parented_locations),
            "parented_boarding_location_pct": _pct(
                len(parented_locations), len(boarding_locations)
            ),
            "referenced_station_count": len(station_ids),
        },
        "stop_access": {
            "eligible_terminal_count": len(parented_locations),
            "stated_count": stop_access_stated,
            "stated_pct": _pct(stop_access_stated, len(parented_locations)),
            "direct_count": stop_access_direct,
            "through_station_count": stop_access_station,
        },
        "accessibility": {
            "terminals": _enum_coverage(boarding_locations, "wheelchair_boarding"),
            "trips": _enum_coverage(ferry_trips, "wheelchair_accessible"),
            "measures": "published_values_not_physical_usability",
        },
        "bikes": _enum_coverage(ferry_trips, "bikes_allowed"),
        "cars": _enum_coverage(ferry_trips, "cars_allowed"),
        "fares": {
            "scope": "whole_feed",
            "fare_free": fare_free,
            "model": str(fare_profile.get("model") or "none"),
            "applied": bool(fare_profile.get("applied")),
        },
        "realtime": {
            "scope": "whole_feed",
            "configured_kinds": configured_kinds,
            "kinds_configured": len(configured_kinds),
        },
    }


def ferry_profile_from_zip(
    gtfs_zip_path: str,
    *,
    fare_free: bool = False,
    configured_realtime_kinds: Collection[str] = (),
) -> dict[str, Any] | None:
    """Read the ferry-relevant GTFS tables and return the ungraded profile.

    Returns None when there is no ferry profile to report, including the case
    where one of the small tables is too large to read: the ferry profile is a
    descriptive add-on, so it is skipped rather than failing the whole score.

    stop_times.txt is streamed rather than read whole, and with no byte cap.
    The only thing this profile takes from it is the set of stop ids the ferry
    trips call at, so the memory cost is the size of that set. Reading it whole
    cost about 750 bytes a row, which is how a 1.01 GB stop_times.txt -- 62 MB
    *under* the whole-table cap -- became roughly 13 GB of dicts and killed the
    Dutch national aggregate's shard for three weeks.
    """
    try:
        tables = read_tables(gtfs_zip_path, ["routes.txt", "trips.txt", "stops.txt"])
    except TableTooLargeError as exc:
        log.warning("ferry profile skipped: %s", exc)
        return None
    fares = detect_fares(gtfs_zip_path).to_details()
    stop_times = iter_table_rows(gtfs_zip_path, "stop_times.txt", max_member_bytes=None)
    # closing() because build_ferry_profile returns before reading a row when
    # the feed has no ferry routes, and an abandoned generator should release
    # its open archive at a point this function chooses.
    with closing(stop_times):
        return build_ferry_profile(
            tables["routes.txt"],
            tables["trips.txt"],
            stop_times,
            tables["stops.txt"],
            fare_profile=fares,
            fare_free=fare_free,
            configured_realtime_kinds=configured_realtime_kinds,
        )
