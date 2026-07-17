"""Tests for router-free trip-plannability checks."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scorecard_pipeline.routability import assess_routability

_TRIPS = "route_id,service_id,trip_id\nr,s,t1\nr,s,t2\n"
_STOPS = "stop_id,stop_name,location_type\nA,Alpha,0\nB,Beta,0\nC,Gamma,0\n"


def _zip(
    make: Callable[..., Path], stop_times: str, trips: str = _TRIPS, stops: str = _STOPS
) -> Path:
    return make({"trips.txt": trips, "stops.txt": stops, "stop_times.txt": stop_times})


def test_clean_feed_has_no_findings(make_gtfs_zip: Callable[..., Path]) -> None:
    st = (
        "trip_id,stop_id,stop_sequence\n"
        "t1,A,1\nt1,B,2\n"
        "t2,B,1\nt2,C,2\n"  # every trip has 2 stops; A, B, C all served
    )
    p = assess_routability(str(_zip(make_gtfs_zip, st)))
    assert p.single_stop_trips == 0
    assert p.orphan_stops == 0
    assert p.findings == []


def test_single_stop_trip_is_flagged(make_gtfs_zip: Callable[..., Path]) -> None:
    st = "trip_id,stop_id,stop_sequence\nt1,A,1\nt1,B,2\nt2,C,1\n"  # t2 has one stop
    p = assess_routability(str(_zip(make_gtfs_zip, st)))
    assert p.single_stop_trips == 1
    codes = {f.code for f in p.findings}
    assert "scorecard_single_stop_trips" in codes


def test_trip_with_no_stop_times_counts_as_single(make_gtfs_zip: Callable[..., Path]) -> None:
    st = "trip_id,stop_id,stop_sequence\nt1,A,1\nt1,B,2\n"  # t2 absent entirely
    p = assess_routability(str(_zip(make_gtfs_zip, st)))
    assert p.single_stop_trips == 1  # t2 has zero stop_times


def test_orphan_stop_is_flagged(make_gtfs_zip: Callable[..., Path]) -> None:
    st = "trip_id,stop_id,stop_sequence\nt1,A,1\nt1,B,2\nt2,A,1\nt2,B,2\n"  # C never served
    p = assess_routability(str(_zip(make_gtfs_zip, st)))
    assert p.orphan_stops == 1
    assert any(f.code == "scorecard_orphan_stops" for f in p.findings)


def test_station_rows_are_not_orphans(make_gtfs_zip: Callable[..., Path]) -> None:
    stops = "stop_id,stop_name,location_type\nA,Alpha,0\nB,Beta,0\nSTA,Station,1\n"
    st = "trip_id,stop_id,stop_sequence\nt1,A,1\nt1,B,2\nt2,A,1\nt2,B,2\n"
    p = assess_routability(str(_zip(make_gtfs_zip, st, stops=stops)))
    # STA is location_type 1 (station), legitimately absent from stop_times.
    assert p.orphan_stops == 0
    assert p.boardable_stops == 2


def test_stops_served_through_a_location_group_are_not_orphans(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {
        "trips.txt": "route_id,service_id,trip_id\nr,s,t1\n",
        "stops.txt": "stop_id,stop_name,location_type\nA,Alpha,0\nB,Beta,0\n",
        "stop_times.txt": (
            "trip_id,location_group_id,stop_sequence,start_pickup_drop_off_window,"
            "end_pickup_drop_off_window\n"
            "t1,g,1,07:00:00,10:00:00\n"
            "t1,g,2,07:00:00,10:00:00\n"
        ),
        "location_groups.txt": "location_group_id,location_group_name\ng,Service area\n",
        "location_group_stops.txt": "location_group_id,stop_id\ng,A\ng,B\n",
    }

    p = assess_routability(str(make_gtfs_zip(feed)))

    assert p.single_stop_trips == 0
    assert p.boardable_stops == 2
    assert p.orphan_stops == 0


def test_geojson_location_header_whitespace_does_not_hide_trip_locations(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {
        "trips.txt": "route_id,service_id,trip_id\nr,s,t1\n",
        "stops.txt": "stop_id,stop_name,location_type\n",
        "stop_times.txt": (
            "trip_id, location_id,stop_sequence,start_pickup_drop_off_window,"
            "end_pickup_drop_off_window\n"
            "t1,z,1,07:00:00,10:00:00\n"
            "t1,z,2,07:00:00,10:00:00\n"
        ),
        "locations.geojson": (
            '{"type":"FeatureCollection","features":[{"type":"Feature","id":"z",'
            '"properties":{},"geometry":{"type":"Polygon","coordinates":[]}}]}'
        ),
    }

    p = assess_routability(str(make_gtfs_zip(feed)))

    assert p.single_stop_trips == 0
    assert p.boardable_stops == 0
    assert p.orphan_stops == 0


def test_geojson_location_does_not_mark_an_unrelated_stop_as_served(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {
        "trips.txt": "route_id,service_id,trip_id\nr,s,t1\n",
        "stops.txt": "stop_id,stop_name,location_type\nA,Alpha,0\n",
        "stop_times.txt": (
            "trip_id,location_id,stop_sequence,start_pickup_drop_off_window,"
            "end_pickup_drop_off_window\n"
            "t1,z,1,07:00:00,10:00:00\n"
            "t1,z,2,07:00:00,10:00:00\n"
        ),
        "locations.geojson": (
            '{"type":"FeatureCollection","features":[{"type":"Feature","id":"z",'
            '"properties":{},"geometry":{"type":"Polygon","coordinates":[]}}]}'
        ),
    }

    p = assess_routability(str(make_gtfs_zip(feed)))

    assert p.single_stop_trips == 0
    assert p.orphan_stops == 1


def test_to_details_shape(make_gtfs_zip: Callable[..., Path]) -> None:
    st = "trip_id,stop_id,stop_sequence\nt1,A,1\nt1,B,2\nt2,C,1\n"
    d = assess_routability(str(_zip(make_gtfs_zip, st))).to_details()
    assert d == {
        "trips_total": 2,
        "single_stop_trips": 1,
        "boardable_stops": 3,
        "orphan_stops": 0,
    }
