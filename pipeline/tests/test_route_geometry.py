"""Tests for per-agency route + stop geometry extraction and dedup (pure)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.route_geometry import (
    _color_name,
    _route_type_family,
    _route_type_label,
    _simplify,
    build_route_geometry,
    route_geometry_from_zip,
)


def _routes(*rows: dict[str, str]) -> list[dict[str, str]]:
    return list(rows)


def _shape_line(shape_id: str, points: list[tuple[float, float]]) -> list[dict[str, str]]:
    return [
        {
            "shape_id": shape_id,
            "shape_pt_lat": str(lat),
            "shape_pt_lon": str(lon),
            "shape_pt_sequence": str(i + 1),
        }
        for i, (lat, lon) in enumerate(points)
    ]


def _features_by_kind(geo: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [f for f in geo["features"] if f["properties"]["kind"] == kind]


def test_one_linestring_per_route_dedups_repeated_trip_shapes() -> None:
    routes = _routes({"route_id": "A", "route_short_name": "A", "route_type": "3"})
    # Three trips, all the same short shape, plus one trip on a longer shape.
    trips = [
        {"route_id": "A", "trip_id": "t1", "shape_id": "short"},
        {"route_id": "A", "trip_id": "t2", "shape_id": "short"},
        {"route_id": "A", "trip_id": "t3", "shape_id": "short"},
        {"route_id": "A", "trip_id": "t4", "shape_id": "long"},
    ]
    shapes = _shape_line("short", [(38.50, -121.70), (38.51, -121.70)]) + _shape_line(
        "long", [(38.50, -121.70), (38.55, -121.70), (38.60, -121.70)]
    )
    result = build_route_geometry(routes, trips, shapes, [])
    assert result.feature_collection is not None
    lines = _features_by_kind(result.feature_collection, "route")
    # Exactly one line for the one route, despite four trips and two shapes.
    assert len(lines) == 1
    # The longer shape wins (dedup keeps the most representative geometry).
    coords = lines[0]["geometry"]["coordinates"]
    assert coords[0] == [-121.7, 38.5]
    assert coords[-1] == [-121.7, 38.6]


def test_route_color_from_feed_wins_over_type_fallback() -> None:
    routes = _routes(
        {"route_id": "A", "route_short_name": "A", "route_type": "3", "route_color": "0E6734"}
    )
    trips = [{"route_id": "A", "trip_id": "t", "shape_id": "s"}]
    shapes = _shape_line("s", [(38.5, -121.7), (38.6, -121.7)])
    result = build_route_geometry(routes, trips, shapes, [])
    assert result.feature_collection is not None
    line = _features_by_kind(result.feature_collection, "route")[0]
    assert line["properties"]["color"] == "#0E6734"
    meta = result.summary["routes"][0]
    assert meta["color"] == "0E6734"
    assert meta["color_name"] == "green"


def test_missing_route_color_falls_back_by_route_type() -> None:
    routes = _routes({"route_id": "F", "route_short_name": "F", "route_type": "4"})
    trips = [{"route_id": "F", "trip_id": "t", "shape_id": "s"}]
    shapes = _shape_line("s", [(38.5, -121.7), (38.6, -121.7)])
    result = build_route_geometry(routes, trips, shapes, [])
    meta = result.summary["routes"][0]
    assert meta["type_label"] == "Ferry"
    # Ferry fallback color, normalized uppercase, no hash in the summary.
    assert meta["color"] == "1B7FA8"


def test_stops_emitted_as_points_and_counted() -> None:
    stops = [
        {"stop_id": "s2", "stop_name": "Second & Main", "stop_lat": "38.55", "stop_lon": "-121.74"},
        {"stop_id": "s1", "stop_name": "First & Elm", "stop_lat": "38.54", "stop_lon": "-121.73"},
        {"stop_id": "bad", "stop_name": "Null Island", "stop_lat": "0", "stop_lon": "0"},
        {"stop_id": "blank", "stop_name": "No coords", "stop_lat": "", "stop_lon": ""},
    ]
    result = build_route_geometry([], [], [], stops)
    assert result.feature_collection is not None
    points = _features_by_kind(result.feature_collection, "stop")
    assert len(points) == 2  # null island and blank dropped
    # Sorted by stop_id for determinism.
    assert [p["properties"]["stop_id"] for p in points] == ["s1", "s2"]
    assert result.summary["stop_count"] == 2
    assert result.summary["has_shapes"] is False


def test_feed_with_neither_routes_nor_stops_yields_no_map() -> None:
    result = build_route_geometry([], [], [], [])
    assert result.feature_collection is None
    assert result.is_empty is True
    assert result.summary["route_count"] == 0
    assert result.summary["stop_count"] == 0


def test_route_without_shape_is_listed_but_not_drawn() -> None:
    # Route exists, but its trips reference no shape -> table row, no line.
    routes = _routes({"route_id": "A", "route_short_name": "A", "route_type": "3"})
    trips = [{"route_id": "A", "trip_id": "t", "shape_id": ""}]
    stops = [{"stop_id": "s1", "stop_name": "Stop", "stop_lat": "38.5", "stop_lon": "-121.7"}]
    result = build_route_geometry(routes, trips, shapes=[], stops=stops)
    assert result.feature_collection is not None
    assert _features_by_kind(result.feature_collection, "route") == []
    meta = result.summary["routes"][0]
    assert meta["has_shape"] is False
    assert result.summary["has_shapes"] is False


def test_geometry_is_deterministic() -> None:
    routes = _routes(
        {"route_id": "B", "route_short_name": "B", "route_type": "3"},
        {"route_id": "A", "route_short_name": "A", "route_type": "3"},
    )
    trips = [
        {"route_id": "A", "trip_id": "t", "shape_id": "sa"},
        {"route_id": "B", "trip_id": "u", "shape_id": "sb"},
    ]
    shapes = _shape_line("sa", [(38.5, -121.7), (38.6, -121.7)]) + _shape_line(
        "sb", [(38.5, -121.6), (38.6, -121.6)]
    )
    a = build_route_geometry(routes, trips, shapes, [])
    b = build_route_geometry(routes, trips, shapes, [])
    assert a.feature_collection == b.feature_collection
    # Routes sorted by id regardless of input order.
    assert [r["id"] for r in a.summary["routes"]] == ["A", "B"]


def test_simplify_drops_collinear_midpoints() -> None:
    line = [(38.50, -121.70), (38.55, -121.70), (38.60, -121.70)]
    simplified = _simplify(line, 0.0001)
    assert simplified == [(38.50, -121.70), (38.60, -121.70)]


def test_coordinates_are_rounded_to_five_decimals() -> None:
    routes = _routes({"route_id": "A", "route_short_name": "A", "route_type": "3"})
    trips = [{"route_id": "A", "trip_id": "t", "shape_id": "s"}]
    shapes = _shape_line("s", [(38.1234567, -121.7654321), (38.2, -121.7)])
    result = build_route_geometry(routes, trips, shapes, [])
    assert result.feature_collection is not None
    coords = _features_by_kind(result.feature_collection, "route")[0]["geometry"]["coordinates"]
    assert coords[0] == [-121.76543, 38.12346]


def test_extended_route_types_fold_to_a_basic_family() -> None:
    assert _route_type_family("700") == 3  # bus
    assert _route_type_label("700") == "Bus"
    assert _route_type_family("109") == 2  # rail
    assert _route_type_label("1200") == "Ferry"
    # Unknown / blank fall through to the generic label.
    assert _route_type_family("9999") is None
    assert _route_type_label("9999") == "Transit line"
    assert _route_type_label("") == "Transit line"


def test_color_name_matches_nearest_word() -> None:
    assert _color_name("CC2222") == "red"
    assert _color_name("0E6734") == "green"
    assert _color_name("2E3092") == "blue"


def test_shape_collapsing_to_one_point_is_not_drawn() -> None:
    # A two-point shape whose endpoints round to the same 5-decimal coordinate
    # (a sub-meter span, or duplicate coordinates from a malformed export) must
    # not be emitted as a 1-coordinate LineString (invalid GeoJSON); the route
    # degrades to no-shape instead.
    routes = _routes({"route_id": "A", "route_short_name": "A", "route_type": "3"})
    trips = [{"route_id": "A", "trip_id": "t", "shape_id": "s"}]
    shapes = _shape_line("s", [(38.500001, -121.700001), (38.500002, -121.700002)])
    result = build_route_geometry(routes, trips, shapes, [])
    # No route LineString is emitted (this feed has no drawable geometry at all).
    if result.feature_collection is not None:
        assert _features_by_kind(result.feature_collection, "route") == []
    meta = result.summary["routes"][0]
    assert meta["id"] == "A"
    assert meta["has_shape"] is False
    assert result.summary["drawn_route_count"] == 0


def test_from_zip_reads_a_real_trimmed_feed(make_gtfs_zip) -> None:  # type: ignore[no-untyped-def]
    files = {
        "routes.txt": (
            "route_id,route_short_name,route_long_name,route_type,route_color\n"
            "A,A,Main Line,3,0E6734\n"
        ),
        "trips.txt": "route_id,trip_id,shape_id\nA,t1,s1\nA,t2,s1\n",
        "shapes.txt": (
            "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
            "s1,38.50,-121.70,1\ns1,38.55,-121.70,2\ns1,38.60,-121.70,3\n"
        ),
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nx,Depot,38.5,-121.7\n",
    }
    zip_path = make_gtfs_zip(files)
    result = route_geometry_from_zip(str(zip_path))
    assert result.feature_collection is not None
    assert result.summary["drawn_route_count"] == 1
    assert result.summary["stop_count"] == 1
