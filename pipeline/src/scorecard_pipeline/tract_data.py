"""Load Census tract geometry and ACS indicators into ``Tract`` objects.

This is the data step ADR 0015 named as the tract-level escalation of the
state-level equity overlay. ``tract_equity.py`` already holds the geospatial core
(point-in-polygon, stop-weighted aggregation, ``need_tier``); this supplies the
two inputs it needs:

- **Geometry** from the Census TIGERweb REST service (GeoJSON, filterable by
  state FIPS, no API key), fetched a state at a time and paged.
- **ACS indicators** from the same Census ACS 5-year API the state overlay uses
  (``equity.py``), queried at tract geography and keyed by 11-digit GEOID. Like
  the state overlay, this needs a free ``CENSUS_API_KEY`` and only runs in the
  dedicated workflow, never the daily scoring path.

Fetching per state means a run pulls only the states that have tracked agencies,
and the heavy tract geometry is never committed: a workflow computes each feed's
served-area need from stops we already have and publishes only the small result.
The pure parsers and the join are unit-tested; the network fetch mirrors the
state overlay's gated, CI-only pattern.
"""

from __future__ import annotations

import json
from typing import Any

from .equity import (
    _DISABILITY_VAR,
    _POVERTY_VAR,
    _ZV_NONE,
    _ZV_TOTAL,
    ACS_YEAR,
    EquityIndicators,
    _to_float,
)
from .tract_equity import Polygon, Tract, served_area_need

# TIGERweb current-vintage tracts layer. Returns GeoJSON when f=geojson; STATE is
# the two-digit state FIPS. outSR=4326 keeps coordinates in lon/lat.
_TIGERWEB_TRACTS = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/0/query"
)
_TIGERWEB_PAGE = 2000  # records per page; the service is paged with resultOffset


# --- pure parsers (unit-tested) ----------------------------------------------


def parse_tract_geometry(geojson: dict[str, Any]) -> dict[str, Polygon]:
    """Parse a TIGERweb tracts GeoJSON FeatureCollection into ``{GEOID: polygon}``.

    Each feature carries a ``GEOID`` property and Polygon or MultiPolygon
    geometry. A MultiPolygon is reduced to its largest part (the tract's main
    body); ``tract_equity``'s ``Polygon`` is a single outer ring plus holes, which
    is enough for the point-in-polygon served-area test. Features without a GEOID
    or usable geometry are skipped.
    """
    out: dict[str, Polygon] = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        geoid = props.get("GEOID")
        geom = feature.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if not geoid or not coords:
            continue
        if gtype == "Polygon":
            rings = coords
        elif gtype == "MultiPolygon":
            rings = max(coords, key=lambda part: len(part[0]) if part and part[0] else 0)
        else:
            continue
        polygon: Polygon = [[(float(x), float(y)) for x, y in ring] for ring in rings]
        # A degenerate part (empty outer ring) would later raise in Tract.bbox;
        # real TIGERweb geometry never has one, but skip it defensively.
        if not polygon or not polygon[0]:
            continue
        out[str(geoid)] = polygon
    return out


def _geoid(header: list[str], row: list[str]) -> str:
    """The 11-digit tract GEOID (state + county + tract) from an ACS row."""
    return row[header.index("state")] + row[header.index("county")] + row[header.index("tract")]


def parse_tract_acs(
    subject_rows: list[list[str]], detail_rows: list[list[str]]
) -> dict[str, EquityIndicators]:
    """Combine ACS subject and detailed-table tract responses into
    ``{GEOID: EquityIndicators}``.

    Mirrors ``equity.parse_acs`` but keys by the 11-digit GEOID rather than the
    state name, and computes the zero-vehicle share from the no-vehicle and total
    household counts. Columns are matched by name, so response order does not
    matter.
    """
    poverty: dict[str, float | None] = {}
    disability: dict[str, float | None] = {}
    if subject_rows:
        header = subject_rows[0]
        pov_i = header.index(_POVERTY_VAR) if _POVERTY_VAR in header else None
        dis_i = header.index(_DISABILITY_VAR) if _DISABILITY_VAR in header else None
        for row in subject_rows[1:]:
            g = _geoid(header, row)
            if pov_i is not None:
                poverty[g] = _to_float(row[pov_i])
            if dis_i is not None:
                disability[g] = _to_float(row[dis_i])

    zero_vehicle: dict[str, float | None] = {}
    if detail_rows:
        header = detail_rows[0]
        total_i = header.index(_ZV_TOTAL) if _ZV_TOTAL in header else None
        none_i = header.index(_ZV_NONE) if _ZV_NONE in header else None
        for row in detail_rows[1:]:
            if total_i is None or none_i is None:
                continue
            g = _geoid(header, row)
            total = _to_float(row[total_i])
            none = _to_float(row[none_i])
            if total and none is not None and total > 0:
                zero_vehicle[g] = round(none / total * 100, 1)

    geoids = set(poverty) | set(disability) | set(zero_vehicle)
    return {
        g: EquityIndicators(
            poverty_pct=poverty.get(g),
            zero_vehicle_pct=zero_vehicle.get(g),
            disability_pct=disability.get(g),
        )
        for g in geoids
    }


def build_tracts(geometry: dict[str, Polygon], acs: dict[str, EquityIndicators]) -> list[Tract]:
    """Join tract geometry and ACS indicators by GEOID into ``Tract`` objects.

    A tract needs both a polygon and an indicator set to be useful for the
    served-area test, so a tract present on only one side is dropped.
    """
    return [
        Tract(geoid=geoid, polygon=polygon, indicators=acs[geoid])
        for geoid, polygon in geometry.items()
        if geoid in acs
    ]


# --- network fetch (CI only; ACS needs CENSUS_API_KEY) -----------------------


def fetch_tract_geometry(state_fips: str) -> dict[str, Polygon]:
    """Fetch all tract polygons for a state from TIGERweb, paged. No key needed."""
    from .net import safe_get
    from .robots_policy import shared_checker

    merged: dict[str, Any] = {"features": []}
    offset = 0
    while True:
        url = (
            f"{_TIGERWEB_TRACTS}?where=STATE%3D%27{state_fips}%27&outFields=GEOID"
            f"&returnGeometry=true&outSR=4326&f=geojson"
            f"&resultRecordCount={_TIGERWEB_PAGE}&resultOffset={offset}"
        )
        shared_checker().require(url)  # robots.txt first (ADR 0075)
        body = safe_get(url, timeout=90).decode()
        page = json.loads(body)
        feats = page.get("features") or []
        merged["features"].extend(feats)
        # The service echoes exceededTransferLimit while more pages remain.
        if not page.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
    return parse_tract_geometry(merged)


def fetch_tract_acs(state_fips: str, year: str = ACS_YEAR) -> dict[str, EquityIndicators]:
    """Fetch tract-level ACS indicators for a state. Needs ``CENSUS_API_KEY``."""
    import os

    from .equity import _fetch_acs_rows

    base = f"https://api.census.gov/data/{year}/acs/acs5"
    geo = f"&for=tract:*&in=state:{state_fips}&in=county:*"
    subject_url = f"{base}/subject?get=NAME,{_POVERTY_VAR},{_DISABILITY_VAR}{geo}"
    detail_url = f"{base}?get=NAME,{_ZV_TOTAL},{_ZV_NONE}{geo}"
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if key:
        subject_url += f"&key={key}"
        detail_url += f"&key={key}"
    return parse_tract_acs(_fetch_acs_rows(subject_url), _fetch_acs_rows(detail_url))


def load_state_tracts(state_fips: str, year: str = ACS_YEAR) -> list[Tract]:
    """Fetch geometry + ACS for a state and join them into ``Tract`` objects."""
    return build_tracts(fetch_tract_geometry(state_fips), fetch_tract_acs(state_fips, year))


# --- per-agency served-area need (pure over pre-fetched tracts) --------------

# Two-letter USPS abbreviation to two-digit Census state FIPS. Agencies carry the
# abbreviation; TIGERweb and the ACS are queried by FIPS.
STATE_FIPS: dict[str, str] = {
    "AL": "01",
    "AK": "02",
    "AZ": "04",
    "AR": "05",
    "CA": "06",
    "CO": "08",
    "CT": "09",
    "DE": "10",
    "DC": "11",
    "FL": "12",
    "GA": "13",
    "HI": "15",
    "ID": "16",
    "IL": "17",
    "IN": "18",
    "IA": "19",
    "KS": "20",
    "KY": "21",
    "LA": "22",
    "ME": "23",
    "MD": "24",
    "MA": "25",
    "MI": "26",
    "MN": "27",
    "MS": "28",
    "MO": "29",
    "MT": "30",
    "NE": "31",
    "NV": "32",
    "NH": "33",
    "NJ": "34",
    "NM": "35",
    "NY": "36",
    "NC": "37",
    "ND": "38",
    "OH": "39",
    "OK": "40",
    "OR": "41",
    "PA": "42",
    "RI": "44",
    "SC": "45",
    "SD": "46",
    "TN": "47",
    "TX": "48",
    "UT": "49",
    "VT": "50",
    "VA": "51",
    "WA": "53",
    "WV": "54",
    "WI": "55",
    "WY": "56",
    "PR": "72",
}


def stops_from_geometry(geojson: dict[str, Any]) -> list[tuple[float, float]]:
    """Extract (lon, lat) for every stop point in an agency ``geometry.geojson``.

    The per-agency geometry artifact already carries ``kind: "stop"`` Point
    features (route_geometry.py), so the served-area test reuses them without
    re-reading the feed."""
    out: list[tuple[float, float]] = []
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        if props.get("kind") != "stop" or geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            out.append((float(coords[0]), float(coords[1])))
    return out


def agency_tiers(
    agencies: list[dict[str, Any]], tracts_by_fips: dict[str, list[Tract]]
) -> list[dict[str, Any]]:
    """Per-agency served-area need tier from stops and pre-fetched tracts.

    Each agency dict carries ``id``, ``name``, ``state`` (USPS), and ``stops`` (a
    list of (lon, lat)). Tracts are supplied per state FIPS so fetching stays in
    the caller (and is done once per state). An agency whose state has no tract
    data, or whose stops fall in no tract, comes back ``unknown`` rather than
    being dropped, so the roster stays complete."""
    results: list[dict[str, Any]] = []
    for a in agencies:
        fips = STATE_FIPS.get(str(a.get("state", "")).upper(), "")
        tracts = tracts_by_fips.get(fips, [])
        tier, ind = served_area_need(a.get("stops") or [], tracts)
        results.append(
            {
                "id": a.get("id", ""),
                "name": a.get("name", a.get("id", "")),
                "state": a.get("state", "") or "Unlocated",
                "need_tier": tier,
                "poverty_pct": ind.poverty_pct,
                "zero_vehicle_pct": ind.zero_vehicle_pct,
                "disability_pct": ind.disability_pct,
            }
        )
    return results
