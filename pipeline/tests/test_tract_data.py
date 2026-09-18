"""Tests for the Census tract data-assembly layer (tract_data.py).

The network fetch (TIGERweb geometry, Census ACS) is gated + CI-only like the
state overlay, so these cover the pure parsers and the join against fixtures
shaped exactly like the real responses, plus the round-trip through the
geospatial core in tract_equity.py.
"""

from __future__ import annotations

import json

import pytest

from scorecard_pipeline.tract_data import (
    STATE_FIPS,
    agency_tiers,
    build_tracts,
    parse_tract_acs,
    parse_tract_geometry,
    stops_from_geometry,
)
from scorecard_pipeline.tract_equity import served_area_need

# A TIGERweb-shaped FeatureCollection: one Polygon, one MultiPolygon (whose
# larger part should win), and one unusable feature (skipped).
_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"GEOID": "10003014908"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [0, 2], [2, 2], [2, 0], [0, 0]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"GEOID": "10003014909"},
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[10, 10], [10, 11], [11, 10], [10, 10]]],  # tiny (3 pts)
                    [[[5, 5], [5, 7], [7, 7], [7, 5], [5, 5]]],  # larger (5 pts) -> wins
                ],
            },
        },
        {"type": "Feature", "properties": {}, "geometry": None},  # skipped
    ],
}

# ACS array-of-arrays, keyed to the same tracts (state+county+tract -> GEOID).
_SUBJECT = [
    ["NAME", "S1701_C03_001E", "S1810_C03_001E", "state", "county", "tract"],
    ["Tract 149.08", "22.0", "16.0", "10", "003", "014908"],  # high poverty + disability
    ["Tract 149.09", "5.0", "3.0", "10", "003", "014909"],  # lower
]
_DETAIL = [
    ["NAME", "B08201_001E", "B08201_002E", "state", "county", "tract"],
    ["Tract 149.08", "1000", "200", "10", "003", "014908"],  # 20% zero-vehicle (high)
    ["Tract 149.09", "1000", "-666666666", "10", "003", "014909"],  # suppressed -> None
]


def test_parse_geometry_polygon_and_multipolygon() -> None:
    geo = parse_tract_geometry(_GEOJSON)
    assert set(geo) == {"10003014908", "10003014909"}  # bad feature skipped
    # MultiPolygon reduced to its larger part (the 5-point ring starting at (5,5)).
    assert geo["10003014909"][0][0] == (5.0, 5.0)
    assert all(isinstance(x, float) and isinstance(y, float) for x, y in geo["10003014908"][0])


def test_parse_acs_geoid_zero_vehicle_and_suppressed() -> None:
    acs = parse_tract_acs(_SUBJECT, _DETAIL)
    a = acs["10003014908"]
    assert a.poverty_pct == 22.0 and a.disability_pct == 16.0 and a.zero_vehicle_pct == 20.0
    b = acs["10003014909"]
    assert b.poverty_pct == 5.0 and b.zero_vehicle_pct is None  # Census sentinel dropped


def test_build_tracts_joins_and_drops_one_sided() -> None:
    geo = parse_tract_geometry(_GEOJSON)
    acs = parse_tract_acs(_SUBJECT, _DETAIL)
    acs["99999999999"] = acs["10003014908"]  # ACS with no geometry -> dropped
    tracts = build_tracts(geo, acs)
    assert {t.geoid for t in tracts} == {"10003014908", "10003014909"}
    assert all(t.polygon and t.indicators is not None for t in tracts)


def test_served_area_need_over_built_tracts() -> None:
    tracts = build_tracts(parse_tract_geometry(_GEOJSON), parse_tract_acs(_SUBJECT, _DETAIL))
    # A stop inside the high-need tract (polygon around 0..2) -> HIGH tier.
    tier, ind = served_area_need([(1.0, 1.0)], tracts)
    assert tier == "high"
    assert ind.poverty_pct == 22.0 and ind.zero_vehicle_pct == 20.0
    # A stop in no tract -> unknown.
    tier2, _ = served_area_need([(50.0, 50.0)], tracts)
    assert tier2 == "unknown"


def test_stops_from_geometry_extracts_only_stops() -> None:
    gj = {
        "features": [
            {
                "properties": {"kind": "stop"},
                "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
            },
            {
                "properties": {"kind": "route"},
                "geometry": {"type": "LineString", "coordinates": [[0, 0]]},
            },
            {
                "properties": {"kind": "stop"},
                "geometry": {"type": "Point", "coordinates": [3.0, 4.0]},
            },
        ]
    }
    assert stops_from_geometry(gj) == [(1.0, 2.0), (3.0, 4.0)]


def test_agency_tiers_maps_state_and_handles_missing() -> None:
    tracts = build_tracts(parse_tract_geometry(_GEOJSON), parse_tract_acs(_SUBJECT, _DETAIL))
    agencies = [
        {"id": "a", "name": "A", "state": "DE", "stops": [(1.0, 1.0)]},  # inside high-need tract
        {"id": "b", "name": "B", "state": "CA", "stops": [(1.0, 1.0)]},  # no CA tracts -> unknown
        {"id": "c", "name": "C", "state": "DE", "stops": [(50.0, 50.0)]},  # in no tract -> unknown
    ]
    res = {r["id"]: r for r in agency_tiers(agencies, {"10": tracts})}
    assert STATE_FIPS["DE"] == "10"
    assert res["a"]["need_tier"] == "high" and res["a"]["poverty_pct"] == 22.0
    assert res["b"]["need_tier"] == "unknown"
    assert res["c"]["need_tier"] == "unknown"
    assert len(res) == 3  # roster stays complete


def test_fetch_tract_geometry_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """The TIGERweb fetch follows resultOffset paging until the service stops
    signaling exceededTransferLimit, merging every page."""
    import scorecard_pipeline.net as net

    pages = [
        {
            "features": [
                {
                    "properties": {"GEOID": "10001000100"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]],
                    },
                }
            ],
            "exceededTransferLimit": True,  # more to come
        },
        {
            "features": [
                {
                    "properties": {"GEOID": "10001000200"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[2, 2], [2, 3], [3, 3], [2, 2]]],
                    },
                }
            ],
            "exceededTransferLimit": False,  # last page
        },
    ]
    calls: list[str] = []

    def fake_safe_get(url: str, **kwargs: object) -> bytes:
        calls.append(url)
        return json.dumps(pages[len(calls) - 1]).encode()

    monkeypatch.setattr(net, "safe_get", fake_safe_get)
    from scorecard_pipeline.tract_data import fetch_tract_geometry

    geo = fetch_tract_geometry("10")
    assert set(geo) == {"10001000100", "10001000200"}  # both pages merged
    assert len(calls) == 2  # paged exactly twice, then stopped
    assert "resultOffset=1" in calls[1]  # advanced by the first page's count
