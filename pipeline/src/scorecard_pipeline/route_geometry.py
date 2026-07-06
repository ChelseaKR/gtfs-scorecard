"""Per-agency route and stop geometry for the scorecard map.

The national map (geo.py) places each agency as a single point; an agency's own
scorecard wants more: the lines its buses actually run and the stops riders wait
at, drawn from that feed's own ``shapes.txt`` and ``stops.txt``.

A GTFS feed describes geometry once per *trip*, so a route that runs hundreds of
trips a day repeats the same handful of shapes hundreds of times. Plotting all of
them is wasteful and illegible. This module deduplicates to **one representative
LineString per route_id**: of the distinct shapes a route's trips use, it keeps
the longest (the shape that traces the most of the route), which is the standard
GTFS-route-shapes reduction. Each line is simplified (Ramer-Douglas-Peucker) and
its coordinates rounded to five decimals (~1 m) so the per-agency artifact stays
a few tens of kilobytes, not megabytes.

Output is one GeoJSON ``FeatureCollection`` mixing route ``LineString`` features
and stop ``Point`` features, distinguished by a ``kind`` property, plus a compact
``summary`` (the route list, with colors and human labels, and the stop count)
that feeds the page's accessible route table without re-parsing the GeoJSON.

Degradation is graceful: a feed with stops but no usable ``shapes.txt`` yields a
stops-only map; a feed with neither yields ``None`` and the page shows no map.
Everything is derived from the feed bytes with no wall-clock input, so a re-run
reproduces the artifact byte-for-byte.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any

from .gtfs import read_tables

# Coordinates are rounded to five decimals (~1.1 m) and lines simplified with a
# tolerance a touch finer than that, so simplification never coarsens a feature
# beyond the rounding floor while still collapsing the dense vertices vendors
# emit along straight runs. Both are degree-space approximations: good enough for
# a city-scale reference map, and they keep the file small at 1,445-agency scale.
_COORD_DECIMALS = 5
_SIMPLIFY_TOLERANCE_DEG = 0.00012

# Stops are the accessible equivalent of the map, but a few feeds carry thousands
# of them; past this cap the GeoJSON keeps a deterministic prefix (stops sorted by
# id) so the artifact and the on-page list stay bounded. summary.stop_count always
# reports the true total.
_STOP_POINT_CAP = 2000

# Basic GTFS route_type values (GTFS Schedule reference). Extended route types are
# folded to these families by range below. route_color in the feed always wins for
# drawing; this label is what the accessible table says in words.
_ROUTE_TYPE_LABEL: dict[int, str] = {
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

# Fallback line color when a route sets no route_color, keyed by the same families.
# Chosen to stay distinguishable from one another; the table never relies on color
# alone, so these only need to be pleasant, not semantically loaded.
_ROUTE_TYPE_COLOR: dict[int, str] = {
    0: "DD3333",
    1: "3344CC",
    2: "8844AA",
    3: "1A7A46",
    4: "1B7FA8",
    5: "9A6A2F",
    6: "9A6A2F",
    7: "9A6A2F",
    11: "1A7A46",
    12: "3344CC",
}
_DEFAULT_COLOR = "4A4A4A"

# Coarse named colors for the text description of each route's color, so the
# table conveys color without relying on the swatch (WCAG 1.4.1). Nearest match
# in sRGB; precision is not the point, a readable word is.
_NAMED_COLORS: list[tuple[str, tuple[int, int, int]]] = [
    ("red", (0xCC, 0x22, 0x22)),
    ("orange", (0xE8, 0x7A, 0x00)),
    ("yellow", (0xE4, 0xC4, 0x00)),
    ("green", (0x1A, 0x7A, 0x46)),
    ("teal", (0x1B, 0x7F, 0xA8)),
    ("blue", (0x33, 0x44, 0xCC)),
    ("purple", (0x88, 0x44, 0xAA)),
    ("pink", (0xD1, 0x50, 0x9D)),
    ("brown", (0x8B, 0x57, 0x2A)),
    ("gray", (0x80, 0x80, 0x80)),
    ("black", (0x10, 0x10, 0x10)),
    ("white", (0xF0, 0xF0, 0xF0)),
]


def _route_type_family(raw: str) -> int | None:  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    """Map a route_type string to a basic family int, folding extended types.

    Extended route types (GTFS spec, the 100-1700 ranges) collapse to the closest
    basic family so the label and fallback color stay meaningful. Returns None for
    a blank or unparseable value.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value in _ROUTE_TYPE_LABEL:
        return value
    # Extended types: fold by documented range to a basic family.
    if 100 <= value <= 117:
        return 2  # rail
    if 200 <= value <= 299:
        return 3  # coach -> bus family
    if 400 <= value <= 405:
        return 1  # urban rail / metro
    if 700 <= value <= 716:
        return 3  # bus
    if value == 800:
        return 11  # trolleybus
    if 900 <= value <= 906:
        return 0  # tram
    if 1000 <= value <= 1021:
        return 4  # water / ferry
    if 1200 <= value <= 1207:
        return 4  # ferry
    if 1300 <= value <= 1307:
        return 6  # aerial lift
    if 1400 <= value <= 1405:
        return 7  # funicular
    return None


def _route_type_label(raw: str) -> str:
    family = _route_type_family(raw)
    if family is None:
        return "Transit line"
    return _ROUTE_TYPE_LABEL[family]


def _normalize_color(raw: str) -> str | None:
    """A six-hex-digit color without the hash, or None if unusable."""
    value = raw.strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value.upper()


def _color_name(hex_color: str) -> str:
    """The nearest coarse color word for a six-hex color, for the text label."""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    best = min(
        _NAMED_COLORS,
        key=lambda nc: (r - nc[1][0]) ** 2 + (g - nc[1][1]) ** 2 + (b - nc[1][2]) ** 2,
    )
    return best[0]


def _coord(row: dict[str, str], field: str) -> float | None:
    raw = row.get(field, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _valid_lonlat(lon: float | None, lat: float | None) -> bool:
    if lon is None or lat is None:
        return False
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return False
    # null island (0, 0) is almost always a stand-in for a missing coordinate.
    return not (lon == 0.0 and lat == 0.0)


def _shape_length(points: list[tuple[float, float]]) -> float:
    """Cumulative length of a (lat, lon) polyline in a flat degree metric.

    Longitude is scaled by cos(latitude) so east-west spans are not overstated at
    higher latitudes; this is only used to rank shapes against each other, so an
    approximate metric is enough.
    """
    total = 0.0
    for (lat1, lon1), (lat2, lon2) in itertools.pairwise(points):
        scale = math.cos(math.radians((lat1 + lat2) / 2))
        total += math.hypot(lat2 - lat1, (lon2 - lon1) * scale)
    return total


def _perp_distance(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Perpendicular distance from point p to segment a-b, in degree space."""
    (ay, ax), (by, bx), (py, px) = a, b, p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    proj_x, proj_y = ax + t * dx, ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _simplify(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker line simplification, iterative to bound recursion.

    Keeps the endpoints and any vertex more than ``tolerance`` from the running
    chord. ``points`` are (lat, lon); the metric is plain degree distance, which
    is fine for thinning the dense vertices vendors emit along straight runs.
    """
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        max_dist, max_idx = -1.0, start
        for i in range(start + 1, end):
            d = _perp_distance(points[i], points[start], points[end])
            if d > max_dist:
                max_dist, max_idx = d, i
        if max_dist > tolerance:
            keep[max_idx] = True
            stack.append((start, max_idx))
            stack.append((max_idx, end))
    return [p for p, k in zip(points, keep, strict=True) if k]


def _ordered_shapes(shape_rows: list[dict[str, str]]) -> dict[str, list[tuple[float, float]]]:
    """shape_id -> ordered (lat, lon) points, sorted by shape_pt_sequence."""
    raw: dict[str, list[tuple[int, float, float]]] = {}
    for row in shape_rows:
        shape_id = (row.get("shape_id") or "").strip()
        if not shape_id:
            continue
        lat = _coord(row, "shape_pt_lat")
        lon = _coord(row, "shape_pt_lon")
        if not _valid_lonlat(lon, lat):
            continue
        try:
            seq = int((row.get("shape_pt_sequence") or "0").strip())
        except ValueError:
            continue
        if lat is None or lon is None:  # guaranteed by _valid_lonlat(); not assert (-O strips it)
            raise AssertionError("lat/lon None despite _valid_lonlat() passing")
        raw.setdefault(shape_id, []).append((seq, lat, lon))
    return {
        shape_id: [(lat, lon) for _, lat, lon in sorted(pts)]
        for shape_id, pts in raw.items()
        if len(pts) >= 2
    }


def _route_shape_ids(trip_rows: list[dict[str, str]]) -> dict[str, list[str]]:
    """route_id -> the distinct shape_ids its trips reference, order preserved."""
    out: dict[str, list[str]] = {}
    for row in trip_rows:
        route_id = (row.get("route_id") or "").strip()
        shape_id = (row.get("shape_id") or "").strip()
        if not route_id or not shape_id:
            continue
        seen = out.setdefault(route_id, [])
        if shape_id not in seen:
            seen.append(shape_id)
    return out


@dataclass(frozen=True)
class RouteGeometry:
    """The map payload plus a compact, page-ready summary.

    ``feature_collection`` is None when the feed has neither drawable routes nor
    locatable stops (no map at all). ``summary`` always describes the routes and
    stop count for the accessible table, even when ``feature_collection`` is None.
    """

    feature_collection: dict[str, Any] | None
    summary: dict[str, Any]

    @property
    def is_empty(self) -> bool:
        return self.feature_collection is None


def _round_line(points: list[tuple[float, float]]) -> list[list[float]]:
    """(lat, lon) points -> rounded [lon, lat] GeoJSON coordinate pairs.

    Consecutive duplicates created by rounding are dropped so a thinned line never
    carries a zero-length segment.
    """
    out: list[list[float]] = []
    for lat, lon in points:
        pair = [round(lon, _COORD_DECIMALS), round(lat, _COORD_DECIMALS)]
        if not out or out[-1] != pair:
            out.append(pair)
    return out


def build_route_geometry(
    routes: list[dict[str, str]],
    trips: list[dict[str, str]],
    shapes: list[dict[str, str]],
    stops: list[dict[str, str]],
) -> RouteGeometry:
    """Build the dedup'd route + stop geometry from already-parsed GTFS tables."""
    ordered_shapes = _ordered_shapes(shapes)
    route_shapes = _route_shape_ids(trips)

    route_meta: list[dict[str, Any]] = []
    route_features: list[dict[str, Any]] = []
    for row in sorted(routes, key=lambda r: r.get("route_id") or ""):
        route_id = (row.get("route_id") or "").strip()
        if not route_id:
            continue
        short = (row.get("route_short_name") or "").strip()
        long = (row.get("route_long_name") or "").strip()
        type_label = _route_type_label(row.get("route_type") or "")
        family = _route_type_family(row.get("route_type") or "")
        color = _normalize_color(row.get("route_color") or "") or _ROUTE_TYPE_COLOR.get(
            family if family is not None else -1, _DEFAULT_COLOR
        )
        text_color = _normalize_color(row.get("route_text_color") or "") or "FFFFFF"

        # Dedup: of the shapes this route's trips use, keep the longest as the one
        # representative line. Hundreds of per-trip repeats collapse to one feature.
        candidate_ids = [s for s in route_shapes.get(route_id, []) if s in ordered_shapes]
        coords: list[list[float]] = []
        if candidate_ids:
            best_id = max(candidate_ids, key=lambda s: _shape_length(ordered_shapes[s]))
            coords = _round_line(_simplify(ordered_shapes[best_id], _SIMPLIFY_TOLERANCE_DEG))
        # A LineString needs at least two distinct positions. A shape that collapses
        # to a single point after simplification and 5-decimal rounding (a sub-metre
        # span, or duplicate coordinates from a malformed export) is not drawable, so
        # treat the route as having no shape rather than emitting invalid GeoJSON.
        has_shape = len(coords) >= 2

        label = short or long or route_id
        color_name = _color_name(color)
        route_meta.append(
            {
                "id": route_id,
                "short": short,
                "long": long,
                "label": label,
                "type_label": type_label,
                "color": color,
                "text_color": text_color,
                "color_name": color_name,
                "has_shape": has_shape,
            }
        )
        if has_shape:
            route_features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "kind": "route",
                        "route_id": route_id,
                        "label": label,
                        "long": long,
                        "type_label": type_label,
                        "color": f"#{color}",
                        "text_color": f"#{text_color}",
                        "color_name": color_name,
                    },
                }
            )

    # Stops as points, reusing the same coordinate validation as the route shapes.
    located: list[tuple[str, str, float, float]] = []
    for row in stops:
        lon = _coord(row, "stop_lon")
        lat = _coord(row, "stop_lat")
        if not _valid_lonlat(lon, lat):
            continue
        if lon is None or lat is None:  # guaranteed by _valid_lonlat(); not assert (-O strips it)
            raise AssertionError("lon/lat None despite _valid_lonlat() passing")
        stop_id = (row.get("stop_id") or "").strip()
        name = (row.get("stop_name") or "").strip() or stop_id or "Unnamed stop"
        located.append((stop_id, name, lat, lon))
    located.sort(key=lambda s: s[0])
    stop_count = len(located)

    stop_features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(lon, _COORD_DECIMALS), round(lat, _COORD_DECIMALS)],
            },
            "properties": {"kind": "stop", "stop_id": stop_id, "name": name},
        }
        for stop_id, name, lat, lon in located[:_STOP_POINT_CAP]
    ]

    has_shapes = bool(route_features)
    summary = {
        "routes": route_meta,
        "route_count": len(route_meta),
        "drawn_route_count": len(route_features),
        "stop_count": stop_count,
        "has_shapes": has_shapes,
        "stop_points_capped": stop_count > _STOP_POINT_CAP,
    }

    if not route_features and not stop_features:
        return RouteGeometry(feature_collection=None, summary=summary)

    fc = {
        "type": "FeatureCollection",
        "features": route_features + stop_features,
    }
    return RouteGeometry(feature_collection=fc, summary=summary)


def route_geometry_from_zip(gtfs_zip_path: str) -> RouteGeometry:
    """Read the geometry-relevant tables from a feed zip and build the payload."""
    tables = read_tables(gtfs_zip_path, ["routes.txt", "trips.txt", "shapes.txt", "stops.txt"])
    return build_route_geometry(
        tables.get("routes.txt", []),
        tables.get("trips.txt", []),
        tables.get("shapes.txt", []),
        tables.get("stops.txt", []),
    )
