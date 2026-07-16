"""Tests for the descriptive, zero-deduction ferry capability profile."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scorecard_pipeline.ferry_profile import build_ferry_profile, ferry_profile_from_zip


def _profile() -> dict[str, object]:
    result = build_ferry_profile(
        [
            {"route_id": "f", "route_type": "4"},
            {"route_id": "b", "route_type": "3"},
        ],
        [
            {
                "route_id": "f",
                "trip_id": "f1",
                "wheelchair_accessible": "1",
                "bikes_allowed": "1",
                "cars_allowed": "",
            },
            {
                "route_id": "f",
                "trip_id": "f2",
                "wheelchair_accessible": "",
                "bikes_allowed": "2",
                "cars_allowed": "2",
            },
            {
                "route_id": "b",
                "trip_id": "b1",
                "wheelchair_accessible": "2",
                "bikes_allowed": "2",
                "cars_allowed": "1",
            },
        ],
        [
            {"trip_id": "f1", "stop_id": "p1"},
            {"trip_id": "f2", "stop_id": "p2"},
            {"trip_id": "b1", "stop_id": "bus"},
        ],
        [
            {
                "stop_id": "p1",
                "location_type": "0",
                "parent_station": "terminal",
                "stop_access": "1",
                "wheelchair_boarding": "1",
            },
            {
                "stop_id": "p2",
                "location_type": "",
                "parent_station": "terminal",
                "stop_access": "",
                "wheelchair_boarding": "2",
            },
            {"stop_id": "terminal", "location_type": "1"},
            {
                "stop_id": "bus",
                "location_type": "0",
                "wheelchair_boarding": "1",
            },
        ],
        fare_profile={"model": "v2", "applied": True},
        configured_realtime_kinds={"service_alerts", "trip_updates"},
    )
    assert result is not None
    return result


def test_profile_scopes_measurements_to_ferry_routes_and_trips() -> None:
    profile = _profile()

    assert profile["measured"] is True
    assert profile["graded"] is False
    assert profile["route_count"] == 1
    assert profile["trip_count"] == 2
    assert profile["terminal_hierarchy"] == {
        "boarding_location_count": 2,
        "parented_boarding_location_count": 2,
        "parented_boarding_location_pct": 100.0,
        "referenced_station_count": 1,
    }


def test_profile_preserves_unknown_enum_values() -> None:
    profile = _profile()

    assert profile["stop_access"] == {
        "eligible_terminal_count": 2,
        "stated_count": 1,
        "stated_pct": 50.0,
        "direct_count": 1,
        "through_station_count": 0,
    }
    assert profile["accessibility"]["trips"]["stated_pct"] == 50.0  # type: ignore[index]
    assert profile["bikes"]["stated_pct"] == 100.0  # type: ignore[index]
    assert profile["cars"]["stated_pct"] == 50.0  # type: ignore[index]
    assert profile["cars"]["allowed_count"] == 0  # type: ignore[index]
    assert profile["cars"]["not_allowed_count"] == 1  # type: ignore[index]


def test_feed_level_facts_are_labelled_and_ordered() -> None:
    profile = _profile()

    assert profile["fares"] == {
        "scope": "whole_feed",
        "fare_free": False,
        "model": "v2",
        "applied": True,
    }
    assert profile["realtime"] == {
        "scope": "whole_feed",
        "configured_kinds": ["trip_updates", "service_alerts"],
        "kinds_configured": 2,
    }


def test_non_ferry_feed_has_no_profile() -> None:
    result = build_ferry_profile(
        [{"route_id": "b", "route_type": "3"}],
        [{"route_id": "b", "trip_id": "b1"}],
        [],
        [],
        fare_profile={"model": "none", "applied": False},
    )

    assert result is None


def test_profile_reads_zip_and_fare_model(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    path = make_gtfs_zip(
        {
            "routes.txt": "route_id,route_type\nf,4\n",
            "trips.txt": (
                "route_id,service_id,trip_id,wheelchair_accessible,bikes_allowed,cars_allowed\n"
                "f,s,t,1,1,1\n"
            ),
            "stop_times.txt": "trip_id,stop_id,stop_sequence\nt,p,1\n",
            "stops.txt": (
                "stop_id,stop_name,location_type,parent_station,stop_access,wheelchair_boarding\n"
                "p,Pier,0,terminal,0,1\n"
                "terminal,Terminal,1,,,1\n"
            ),
            "fare_attributes.txt": (
                "fare_id,price,currency_type,payment_method,transfers\nf,5,USD,0,0\n"
            ),
        }
    )

    profile = ferry_profile_from_zip(str(path), configured_realtime_kinds={"vehicle_positions"})

    assert profile is not None
    assert profile["fares"]["model"] == "legacy"
    assert profile["fares"]["applied"] is True
    assert profile["stop_access"]["through_station_count"] == 1
    assert profile["realtime"]["configured_kinds"] == ["vehicle_positions"]
