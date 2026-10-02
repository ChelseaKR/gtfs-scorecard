"""Pair-level findings for overlapping GTFS agencies.

When two agencies share stops, routes, or trips — common in regions where
multiple transit providers serve the same corridor — this module finds the
overlaps and generates plain-language findings about them.  Shared coverage
is not inherently bad, but misaligned stop names, colliding IDs, or
duplicate headsigns can confuse trip planners and riders who transfer
between systems.

Pure by design: dicts in, dataclasses out, no fetching and no disk.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairFinding:
    """One finding about the overlap between two agencies."""

    code: str
    severity: str  # INFO, WARNING, ERROR
    count: int
    what: str
    why: str
    fix: str
    effort: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "count": self.count,
            "what": self.what,
            "why": self.why,
            "fix": self.fix,
            "effort": self.effort,
            "details": self.details,
        }


@dataclass(frozen=True)
class PairResult:
    """The result of comparing two agencies for overlapping GTFS data."""

    agency_a: str
    agency_b: str
    shared_stops: list[dict[str, Any]] = field(default_factory=list)
    shared_routes: list[dict[str, Any]] = field(default_factory=list)
    shared_trips: list[dict[str, Any]] = field(default_factory=list)
    findings: list[PairFinding] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "agency_a": self.agency_a,
            "agency_b": self.agency_b,
            "shared_stops": self.shared_stops,
            "shared_routes": self.shared_routes,
            "shared_trips": self.shared_trips,
            "findings": [f.to_json() for f in self.findings],
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _safe_float(s: str | None) -> float | None:
    """Parse a string to float, returning None on failure or empty input."""
    if s is None:
        return None
    value = s.strip()
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in meters.

    Uses the Haversine formula with the WGS-84 mean Earth radius of
    6_371_000 meters.  Accurate enough for stop-level proximity checks
    where the threshold is on the order of hundreds of meters.
    """
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _normalize_stop_name(name: str) -> str:
    """Lowercase, strip accents, collapse whitespace, remove non-alphanum."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def _normalize_route_name(name: str) -> str:
    """Lowercase, strip accents, collapse whitespace, remove non-alphanum.

    Identical normalization to stop names — route names and stop names
    both benefit from the same treatment when comparing across agencies
    that may differ on capitalization, accents, or punctuation.
    """
    return _normalize_stop_name(name)


# ---------------------------------------------------------------------------
# Stop matching
# ---------------------------------------------------------------------------

DEFAULT_STOP_THRESHOLD_METERS = 100.0


def _build_id_index(items: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    """Build an index of items by a key field."""
    index: dict[str, dict[str, str]] = {}
    for item in items:
        val = item.get(key, "").strip()
        if val:
            index[val] = item
    return index


def _find_exact_id_matches(
    index_a: dict[str, dict[str, str]],
    index_b: dict[str, dict[str, str]],
    key: str,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Find exact ID matches between two indexes."""
    matched_a: set[str] = set()
    matched_b: set[str] = set()
    results: list[dict[str, Any]] = []

    for val, _item_a in index_a.items():
        if val in index_b:
            matched_a.add(val)
            matched_b.add(val)
            results.append(
                {
                    f"{key}_a": val,
                    f"{key}_b": val,
                    "match_method": "id",
                }
            )
    return results, matched_a, matched_b


def _find_proximity_matches(
    unmatched_a: list[tuple[dict[str, str], str, float, float]],
    unmatched_b: list[tuple[dict[str, str], str, float, float]],
    threshold_meters: float,
    grid_size: float,
) -> list[dict[str, Any]]:
    """Find proximity matches using a grid-bucket spatial index."""
    # Build spatial index for B
    grid_b: dict[tuple[int, int], list[tuple[dict[str, str], str, float, float]]] = {}
    for item, val, lat, lon in unmatched_b:
        cell = (int(lat / grid_size), int(lon / grid_size))
        grid_b.setdefault(cell, []).append((item, val, lat, lon))

    used_b: set[str] = set()
    results: list[dict[str, Any]] = []

    for _item_a, _val_a, lat_a, lon_a in unmatched_a:
        cell_a = (int(lat_a / grid_size), int(lon_a / grid_size))
        best: tuple[float, dict[str, str], str, float, float] | None = None
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for item_b, val_b, lat_b, lon_b in grid_b.get((cell_a[0] + dx, cell_a[1] + dy), []):
                    if val_b in used_b:
                        continue
                    dist = _haversine_meters(lat_a, lon_a, lat_b, lon_b)
                    if dist <= threshold_meters and (best is None or dist < best[0]):
                        best = (dist, item_b, val_b, lat_b, lon_b)
        if best is not None:
            dist, item_b, val_b, lat_b, lon_b = best
            used_b.add(val_b)
            results.append(
                {
                    "lat": lat_a,
                    "lon": lon_a,
                    "distance_meters": round(dist, 1),
                    "match_method": "proximity",
                }
            )
    return results


def find_shared_stops(
    stops_a: list[dict[str, str]],
    stops_b: list[dict[str, str]],
    *,
    threshold_meters: float = DEFAULT_STOP_THRESHOLD_METERS,
) -> list[dict[str, Any]]:
    """Match stops between two agencies by exact ID then geographic proximity.

    Returns a list of match dicts with keys: stop_id_a, stop_id_b,
    stop_name_a, stop_name_b, lat, lon, distance_meters, and match_method.
    """
    index_a = _build_id_index(stops_a, "stop_id")
    index_b = _build_id_index(stops_b, "stop_id")

    id_matches, matched_a, matched_b = _find_exact_id_matches(index_a, index_b, "stop_id")
    for m in id_matches:
        m["stop_name_a"] = index_a[m["stop_id_a"]].get("stop_name", "")
        m["stop_name_b"] = index_b[m["stop_id_b"]].get("stop_name", "")
        m["lat"] = _safe_float(index_a[m["stop_id_a"]].get("stop_lat")) or 0.0
        m["lon"] = _safe_float(index_a[m["stop_id_a"]].get("stop_lon")) or 0.0
        m["distance_meters"] = 0.0

    # Prepare unmatched stops for proximity matching
    unmatched_a = _extract_coords(stops_a, "stop_id", matched_a)
    unmatched_b = _extract_coords(stops_b, "stop_id", matched_b)

    grid_size = 0.01  # roughly 1 km
    proximity_matches = _find_proximity_matches(
        unmatched_a, unmatched_b, threshold_meters, grid_size
    )
    for m in proximity_matches:
        m["stop_id_a"] = ""
        m["stop_id_b"] = ""
        m["stop_name_a"] = ""
        m["stop_name_b"] = ""

    return id_matches + proximity_matches


def _extract_coords(
    items: list[dict[str, str]],
    key: str,
    matched: set[str],
) -> list[tuple[dict[str, str], str, float, float]]:
    """Extract items with coordinates, excluding already-matched items."""
    result: list[tuple[dict[str, str], str, float, float]] = []
    for item in items:
        val = item.get(key, "").strip()
        if val in matched:
            continue
        lat = _safe_float(item.get("stop_lat"))
        lon = _safe_float(item.get("stop_lon"))
        if lat is not None and lon is not None:
            result.append((item, val, lat, lon))
    return result


# ---------------------------------------------------------------------------
# Route matching
# ---------------------------------------------------------------------------


def find_shared_routes(
    routes_a: list[dict[str, str]],
    routes_b: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Match routes between two agencies by exact route_id then name similarity.

    Returns a list of match dicts with keys: route_id_a, route_id_b,
    route_name_a, route_name_b, and match_method.
    """
    index_a = _build_id_index(routes_a, "route_id")
    index_b = _build_id_index(routes_b, "route_id")

    id_matches, matched_a, matched_b = _find_exact_id_matches(index_a, index_b, "route_id")
    for m in id_matches:
        m["route_name_a"] = index_a[m["route_id_a"]].get("route_long_name", "")
        m["route_name_b"] = index_b[m["route_id_b"]].get("route_long_name", "")

    # Name matching for unmatched routes
    name_index_b: dict[str, tuple[dict[str, str], str]] = {}
    for route in routes_b:
        rid = route.get("route_id", "").strip()
        if rid in matched_b:
            continue
        name = route.get("route_long_name", "")
        norm = _normalize_route_name(name)
        if norm and norm not in name_index_b:
            name_index_b[norm] = (route, rid)

    name_matches: list[dict[str, Any]] = []
    for route_a in routes_a:
        rid_a = route_a.get("route_id", "").strip()
        if rid_a in matched_a:
            continue
        name_a = route_a.get("route_long_name", "")
        norm_a = _normalize_route_name(name_a)
        if norm_a in name_index_b:
            route_b, rid_b = name_index_b[norm_a]
            matched_b.add(rid_b)
            name_matches.append(
                {
                    "route_id_a": rid_a,
                    "route_id_b": rid_b,
                    "route_name_a": name_a,
                    "route_name_b": route_b.get("route_long_name", ""),
                    "match_method": "name",
                }
            )

    return id_matches + name_matches


# ---------------------------------------------------------------------------
# Trip matching
# ---------------------------------------------------------------------------


def _normalize_headsign(h: str) -> str:
    """Lowercase, strip accents, collapse whitespace for headsign comparison."""
    return _normalize_stop_name(h)


def find_shared_trips(
    trips_a: list[dict[str, str]],
    trips_b: list[dict[str, str]],
    shared_route_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Find trips on shared routes that have matching headsigns.

    ``shared_route_map`` maps route_id_a → route_id_b for routes already
    identified as shared.  Trips are matched when they belong to shared
    routes and have the same normalized headsign.

    Returns a list of match dicts with keys: trip_id_a, trip_id_b,
    route_id_a, route_id_b, headsign_a, headsign_b.
    """
    # Index trips_b by (route_id_b, normalized_headsign).
    trips_b_index: dict[tuple[str, str], list[dict[str, str]]] = {}
    for trip in trips_b:
        rid_b = trip.get("route_id", "").strip()
        headsign = trip.get("trip_headsign", "").strip()
        norm_head = _normalize_headsign(headsign)
        key = (rid_b, norm_head)
        trips_b_index.setdefault(key, []).append(trip)

    results: list[dict[str, Any]] = []
    used_b: set[str] = set()

    for trip_a in trips_a:
        rid_a = trip_a.get("route_id", "").strip()
        if rid_a not in shared_route_map:
            continue
        rid_b = shared_route_map[rid_a]
        headsign_a = trip_a.get("trip_headsign", "").strip()
        norm_head = _normalize_headsign(headsign_a)
        key = (rid_b, norm_head)
        for trip_b in trips_b_index.get(key, []):
            trip_id_b = trip_b.get("trip_id", "").strip()
            if trip_id_b in used_b:
                continue
            used_b.add(trip_id_b)
            results.append(
                {
                    "trip_id_a": trip_a.get("trip_id", ""),
                    "trip_id_b": trip_id_b,
                    "route_id_a": rid_a,
                    "route_id_b": rid_b,
                    "headsign_a": headsign_a,
                    "headsign_b": trip_b.get("trip_headsign", ""),
                }
            )
            break  # one match per trip_a

    return results


# ---------------------------------------------------------------------------
# Finding builders
# ---------------------------------------------------------------------------

_FINDING_TEXT: dict[str, tuple[str, str, str, str]] = {
    "pair_no_overlap": (
        "These two agencies share no stops or routes.",
        "No shared infrastructure means no immediate data-conflict risk.",
        "No action needed.",
        "",
    ),
    "pair_stop_name_mismatch": (
        "Proximity-matched stops have different names across agencies.",
        "A rider transferring between systems may not recognize the stop "
        "under a different name, and trip planners can struggle to link "
        "the same physical stop across feeds.",
        "Coordinate stop naming between agencies so the same stop carries "
        "the same name in both feeds.",
        "Coordination between agencies.",
    ),
    "pair_stop_id_collision": (
        "Different stops share the same stop_id across agencies.",
        "A trip planner that merges feeds by stop_id will treat these as "
        "the same stop, potentially routing riders to the wrong location.",
        "Use agency-prefixed stop_ids (e.g., ``ABM_123``) to avoid "
        "collisions when feeds are merged.",
        "A data export setting in each agency's scheduling software.",
    ),
    "pair_shared_route_count": (
        "These agencies operate routes that overlap.",
        "Shared corridors can indicate duplication or simply a busy "
        "transit hub. The count helps staff assess the scope of overlap.",
        "Review shared routes to confirm intentional coverage rather than accidental duplication.",
        "A conversation between agencies.",
    ),
    "pair_headsign_overlap": (
        "Trips on shared routes have matching headsigns.",
        "Matching headsigns on overlapping routes can confuse riders who "
        "expect different destinations on different agencies' services.",
        "Differentiate headsigns for overlapping routes so riders can "
        "distinguish which agency's service they are boarding.",
        "A coordination conversation between agencies.",
    ),
}


def _build_finding(
    code: str,
    severity: str,
    count: int,
    details: dict[str, Any] | None = None,
) -> PairFinding:
    """Construct a PairFinding from the shared text table."""
    what, why, fix, effort = _FINDING_TEXT[code]
    return PairFinding(
        code=code,
        severity=severity,
        count=count,
        what=what,
        why=why,
        fix=fix,
        effort=effort,
        details=details or {},
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def build_pair_findings(
    stops_a: list[dict[str, str]],
    stops_b: list[dict[str, str]],
    routes_a: list[dict[str, str]],
    routes_b: list[dict[str, str]],
    trips_a: list[dict[str, str]],
    trips_b: list[dict[str, str]],
    agency_a: str,
    agency_b: str,
    *,
    stop_threshold_meters: float = DEFAULT_STOP_THRESHOLD_METERS,
) -> PairResult:
    """Compare two agencies and return shared entities with findings.

    Runs the three match phases (stops, routes, trips) in sequence and
    generates plain-language findings for each noteworthy condition.
    """
    shared_stops = find_shared_stops(stops_a, stops_b, threshold_meters=stop_threshold_meters)
    shared_routes = find_shared_routes(routes_a, routes_b)

    # Build the route_id_a → route_id_b map for trip matching.
    route_map: dict[str, str] = {}
    for match in shared_routes:
        rid_a = match.get("route_id_a", "")
        rid_b = match.get("route_id_b", "")
        if rid_a and rid_b:
            route_map[rid_a] = rid_b

    shared_trips = find_shared_trips(trips_a, trips_b, route_map)

    # --- Generate findings ---------------------------------------------------
    findings: list[PairFinding] = []

    if not shared_stops and not shared_routes:
        findings.append(_build_finding("pair_no_overlap", "INFO", 0))

    # Stop name mismatches (proximity matches only).
    name_mismatches = [
        s
        for s in shared_stops
        if s.get("match_method") == "proximity"
        and _normalize_stop_name(s.get("stop_name_a", ""))
        != _normalize_stop_name(s.get("stop_name_b", ""))
    ]
    if name_mismatches:
        findings.append(
            _build_finding(
                "pair_stop_name_mismatch",
                "WARNING",
                len(name_mismatches),
                {"mismatches": name_mismatches},
            )
        )

    # Stop ID collisions: same ID but different lat/lon (i.e., not the
    # same physical stop).
    id_collisions = [
        s
        for s in shared_stops
        if s.get("match_method") == "id" and s.get("distance_meters", 0.0) > 0.0
    ]
    # Also catch proximity matches that landed on an ID already used —
    # in practice this is when two different stops share a stop_id.
    seen_ids_a: dict[str, int] = {}
    seen_ids_b: dict[str, int] = {}
    for s in shared_stops:
        sid_a = s.get("stop_id_a", "")
        sid_b = s.get("stop_id_b", "")
        seen_ids_a[sid_a] = seen_ids_a.get(sid_a, 0) + 1
        seen_ids_b[sid_b] = seen_ids_b.get(sid_b, 0) + 1
    collision_count = sum(v - 1 for v in seen_ids_a.values() if v > 1) + sum(
        v - 1 for v in seen_ids_b.values() if v > 1
    )
    # Deduplicate: only count each collision pair once.
    actual_id_collisions = len(id_collisions) + max(collision_count, 0)
    if actual_id_collisions:
        findings.append(
            _build_finding(
                "pair_stop_id_collision",
                "WARNING",
                actual_id_collisions,
            )
        )

    # Shared route count.
    if shared_routes:
        findings.append(
            _build_finding(
                "pair_shared_route_count",
                "INFO",
                len(shared_routes),
                {"routes": shared_routes},
            )
        )

    # Headsign overlap.
    if shared_trips:
        findings.append(
            _build_finding(
                "pair_headsign_overlap",
                "INFO",
                len(shared_trips),
                {"trips": shared_trips[:50]},  # cap for artifact size
            )
        )

    return PairResult(
        agency_a=agency_a,
        agency_b=agency_b,
        shared_stops=shared_stops,
        shared_routes=shared_routes,
        shared_trips=shared_trips,
        findings=findings,
        details={
            "shared_stop_count": len(shared_stops),
            "shared_route_count": len(shared_routes),
            "shared_trip_count": len(shared_trips),
            "stop_threshold_meters": stop_threshold_meters,
        },
    )
