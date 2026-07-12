"""The export diff: what changed in the feed itself between versions (EXP-18).

The classic vendor-export accident is silent. A route drops out of the export
or forty stops shift, the validator finds nothing wrong because nothing is
invalid, and nobody notices until riders do. The grade story (timemachine.py)
narrates grade movement and feeddiff.py diffs the quality findings; this
module reads the layer both sit on top of, the feed content, and says in
plain sentences what an export changed.

Raw zips are not retained across runs (FIX-02's durable tier is still gated),
so the memory is a compact structure fingerprint per agency: route ids and
names, stop positions, trip count, and the service span, a few kilobytes of
derived data persisted beside the artifact as ``structure.json`` the same way
the fix log is. Each run summarizes the fetched zip; when the feed's content
hash moved, the previous fingerprint is diffed against the new one and the
result rides on the artifact as an additive ``export_diff`` block. The tone
stays descriptive, change is normal; this is a notice, never an accusation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .config import artifacts_dir
from .gtfs import read_feed_dates, read_tables

STRUCTURE_SCHEMA = 1

# A stop reported this far from where the previous export placed it has moved
# in the real-world sense (across an intersection, to another block), not
# merely been re-surveyed. Matches the "100 m from its street" framing the
# correctness category already uses for stop placement.
STOP_MOVE_METERS = 100.0

# Sentences name at most this many routes before switching to "and N more",
# so one messy export cannot flood the scorecard.
MAX_NAMED_ROUTES = 5


def _route_label(route: dict[str, str]) -> str:
    short = route.get("route_short_name", "").strip()
    long_ = route.get("route_long_name", "").strip()
    if short and long_:
        return f"{short} ({long_})"
    return short or long_ or route.get("route_id", "").strip()


def summarize_structure(gtfs_zip_path: str, feed_sha256: str) -> dict[str, Any]:
    """A compact structural fingerprint of one export."""
    tables = read_tables(gtfs_zip_path, ["routes.txt", "stops.txt", "trips.txt"])
    routes = {
        row["route_id"].strip(): _route_label(row)
        for row in tables["routes.txt"]
        if row.get("route_id", "").strip()
    }
    stops: dict[str, list[float]] = {}
    for row in tables["stops.txt"]:
        stop_id = row.get("stop_id", "").strip()
        try:
            lat = float(row.get("stop_lat", ""))
            lon = float(row.get("stop_lon", ""))
        except ValueError:
            continue
        if stop_id:
            # 5 decimal places is about a meter; enough to detect a real move
            # while keeping the fingerprint byte-stable across float noise.
            stops[stop_id] = [round(lat, 5), round(lon, 5)]
    dates = read_feed_dates(gtfs_zip_path)
    last_service = dates.last_service_date
    return {
        "structure_schema": STRUCTURE_SCHEMA,
        "feed_sha256": feed_sha256,
        "routes": routes,
        "stops": stops,
        "trip_count": len(tables["trips.txt"]),
        "service_end": last_service.isoformat() if last_service else None,
    }


def _meters_apart(a: list[float], b: list[float]) -> float:
    lat_scale = 111_320.0
    lon_scale = 111_320.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[0] - b[0]) * lat_scale, (a[1] - b[1]) * lon_scale)


def _named(labels: list[str]) -> str:
    labels = sorted(labels)
    if len(labels) <= MAX_NAMED_ROUTES:
        return ", ".join(labels)
    shown = ", ".join(labels[:MAX_NAMED_ROUTES])
    return f"{shown}, and {len(labels) - MAX_NAMED_ROUTES} more"


def diff_structures(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Plain sentences describing what changed between two fingerprints.

    Empty when nothing structural moved (a byte-level change with the same
    routes, stops, trips, and span is normal churn and not worth a notice).
    """
    changes: list[str] = []

    prev_routes: dict[str, str] = previous.get("routes", {})
    curr_routes: dict[str, str] = current.get("routes", {})
    added = [curr_routes[r] for r in curr_routes.keys() - prev_routes.keys()]
    removed = [prev_routes[r] for r in prev_routes.keys() - curr_routes.keys()]
    if removed:
        verb = "is" if len(removed) == 1 else "are"
        changes.append(f"Route {_named(removed)} {verb} no longer in the export.")
    if added:
        verb = "is" if len(added) == 1 else "are"
        changes.append(f"Route {_named(added)} {verb} new in this export.")

    prev_stops: dict[str, list[float]] = previous.get("stops", {})
    curr_stops: dict[str, list[float]] = current.get("stops", {})
    stops_removed = len(prev_stops.keys() - curr_stops.keys())
    stops_added = len(curr_stops.keys() - prev_stops.keys())
    moved = sum(
        1
        for stop_id in prev_stops.keys() & curr_stops.keys()
        if _meters_apart(prev_stops[stop_id], curr_stops[stop_id]) > STOP_MOVE_METERS
    )
    if stops_removed:
        plural = "stop" if stops_removed == 1 else "stops"
        changes.append(f"{stops_removed} {plural} left the export.")
    if stops_added:
        plural = "stop" if stops_added == 1 else "stops"
        changes.append(f"{stops_added} new {plural} appeared.")
    if moved:
        plural = "stop" if moved == 1 else "stops"
        changes.append(f"{moved} {plural} moved more than {int(STOP_MOVE_METERS)} m.")

    prev_trips = int(previous.get("trip_count") or 0)
    curr_trips = int(current.get("trip_count") or 0)
    if prev_trips and curr_trips != prev_trips:
        # A tenth is a service change worth a sentence; smaller drift is the
        # ordinary breathing of a schedule.
        share = abs(curr_trips - prev_trips) / prev_trips
        if share >= 0.10:
            direction = "more" if curr_trips > prev_trips else "fewer"
            changes.append(
                f"The export now has {curr_trips:,} trips, "
                f"{abs(curr_trips - prev_trips):,} {direction} than before."
            )

    if previous.get("service_end") != current.get("service_end") and current.get("service_end"):
        if previous.get("service_end"):
            changes.append(
                f"Service now runs through {current['service_end']} "
                f"(was {previous['service_end']})."
            )
        else:
            changes.append(f"Service now runs through {current['service_end']}.")

    return changes


def _structure_path(agency_id: str) -> Path:
    return artifacts_dir() / agency_id / "structure.json"


def load_structure(agency_id: str) -> dict[str, Any] | None:
    path = _structure_path(agency_id)
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(loaded, dict) or loaded.get("structure_schema") != STRUCTURE_SCHEMA:
        # An older or foreign fingerprint cannot be diffed honestly; start over.
        return None
    return loaded


def save_structure(agency_id: str, structure: dict[str, Any]) -> None:
    path = _structure_path(agency_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(structure, sort_keys=True, separators=(",", ":")) + "\n")


def export_diff(agency_id: str, gtfs_zip_path: str, feed_sha256: str) -> dict[str, Any] | None:
    """The per-run entry point: fingerprint, diff against memory, remember.

    Returns the additive artifact block when this run saw a changed export
    with structural differences, else None. Always advances the stored
    fingerprint so tomorrow diffs against today.
    """
    current = summarize_structure(gtfs_zip_path, feed_sha256)
    previous = load_structure(agency_id)
    save_structure(agency_id, current)
    if previous is None or previous.get("feed_sha256") == feed_sha256:
        return None
    changes = diff_structures(previous, current)
    if not changes:
        return None
    return {
        "from_sha256": previous.get("feed_sha256"),
        "to_sha256": feed_sha256,
        "changes": changes,
    }
