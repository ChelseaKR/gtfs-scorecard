"""Tests for the shared, ungraded GTFS mode contract."""

from __future__ import annotations

import zipfile
from pathlib import Path

from scorecard_pipeline.modes import (
    build_mode_profile,
    mode_profile_from_zip,
    route_type_family,
    route_type_mode,
)


def test_mixed_profile_uses_trip_share_for_primary_mode() -> None:
    routes = [
        {"route_id": "bus-a", "route_type": "3"},
        {"route_id": "bus-b", "route_type": "700"},
        {"route_id": "boat", "route_type": "4"},
    ]
    trips = [
        {"trip_id": "1", "route_id": "bus-a"},
        {"trip_id": "2", "route_id": "boat"},
        {"trip_id": "3", "route_id": "boat"},
        {"trip_id": "4", "route_id": "boat"},
    ]

    profile = build_mode_profile(routes, trips)

    assert profile["graded"] is False
    assert profile["primary_mode"] == "ferry"
    assert profile["is_multimodal"] is True
    assert profile["has_ferry"] is True
    assert profile["ferry_only"] is False
    assert profile["route_count"] == 3
    assert profile["trip_count"] == 4
    ferry = next(mode for mode in profile["modes"] if mode["key"] == "ferry")
    assert ferry == {
        "key": "ferry",
        "label": "Ferry",
        "route_count": 1,
        "trip_count": 3,
        "trip_share_pct": 75.0,
    }


def test_unknown_types_are_not_guessed_as_bus() -> None:
    profile = build_mode_profile(
        [{"route_id": "mystery", "route_type": "9999"}],
        [{"trip_id": "1", "route_id": "mystery"}],
    )

    assert route_type_family("9999") is None
    assert route_type_mode("9999") == "other"
    assert profile["primary_mode"] == "other"
    assert profile["has_ferry"] is False
    assert profile["ferry_only"] is False


def test_ferry_only_requires_at_least_one_published_route() -> None:
    empty = build_mode_profile([], [])
    ferry = build_mode_profile(
        [{"route_id": "f", "route_type": "1200"}],
        [{"trip_id": "1", "route_id": "f"}],
    )

    assert empty["measured"] is True
    assert empty["primary_mode"] is None
    assert empty["ferry_only"] is False
    assert ferry["ferry_only"] is True


def test_profile_reads_gtfs_zip(tmp_path: Path) -> None:
    path = tmp_path / "feed.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("routes.txt", "route_id,route_type\nf,4\n")
        zf.writestr("trips.txt", "route_id,service_id,trip_id\nf,s,t\n")

    profile = mode_profile_from_zip(str(path))

    assert profile["primary_mode"] == "ferry"
    assert profile["ferry_only"] is True
