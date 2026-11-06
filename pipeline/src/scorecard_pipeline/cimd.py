"""Canada equity overlay from the Statistics Canada Index of Multiple Deprivation.

ADR 0027. ``tract_equity.py`` holds the country-agnostic geospatial core
(point-in-polygon plus a bounding-box prefilter); this supplies the Canadian
inputs and their own indicator model:

- Per-Dissemination-Area (DA) CIMD deprivation quintiles (StatCan product
  45-20-0001, open CSV).
- DA boundary geometry (2021 Census boundary files).

CIMD's four quintile dimensions do not map onto the US ACS ``EquityIndicators``
(poverty / zero-vehicle / disability), so this carries its own ``CimdIndicators``
type rather than forcing a fit. Per ADR 0026 the tier is a within-Canada quintile
and is not comparable to the US need tier. The transit-relevant dimensions
(economic dependency, situational vulnerability) drive the served-area need
signal; residential instability and ethno-cultural composition are recorded but
deliberately not treated as "need", to avoid conflating demographic composition
with disadvantage.

This module is the pure data-assembly and methodology core (parse, join,
served-area tier), fixture-tested. The gated network fetch (the DA-geometry REST
pull and the CIMD CSV load), the CLI command, and the on-page display are the
wiring step, where the exact StatCan endpoints are confirmed against the live
services (ADR 0027).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tract_equity import Polygon, _in_bbox, _weighted_mean, point_in_polygon

# The four CIMD dimensions, and the two the served-area need tier is built from.
_NEED_DIMENSIONS = ("economic_dependency", "situational_vulnerability")

# Header keywords that identify each dimension's quintile column. CIMD files name
# columns with the dimension words plus a "quintile" marker (the exact wording is
# not published, so match on lowercased keywords to tolerate variations).
_DIMENSION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "residential_instability": ("residential", "instability"),
    "economic_dependency": ("economic", "dependency"),
    "ethno_cultural_composition": ("ethno",),
    "situational_vulnerability": ("situational", "vulnerability"),
}


@dataclass(frozen=True)
class CimdIndicators:
    """A DA's CIMD deprivation quintiles (1 = least deprived, 5 = most).

    Each dimension is a within-Canada population quintile; None when the DA has no
    value for it. Not comparable to the US ACS ``EquityIndicators`` (ADR 0026)."""

    residential_instability: int | None = None
    economic_dependency: int | None = None
    ethno_cultural_composition: int | None = None
    situational_vulnerability: int | None = None


@dataclass(frozen=True)
class DisseminationArea:
    """One DA: its id, boundary, and CIMD quintiles."""

    dauid: str
    polygon: Polygon
    indicators: CimdIndicators

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        lons = [x for ring in self.polygon for x, _ in ring]
        lats = [y for ring in self.polygon for _, y in ring]
        return (min(lons), min(lats), max(lons), max(lats))


# --- pure parsers (unit-tested) ----------------------------------------------


def _quintile(cell: str) -> int | None:
    """A quintile cell as 1-5, or None (blank, suppressed, or out of range)."""
    try:
        q = int(float(cell))
    except (TypeError, ValueError):
        return None
    return q if 1 <= q <= 5 else None


def _quintile_columns(header: list[str]) -> dict[str, int]:
    """Map each dimension to the index of its quintile column, matched by keyword."""
    out: dict[str, int] = {}
    lowered = [h.lower() for h in header]
    for dim, keywords in _DIMENSION_KEYWORDS.items():
        for i, h in enumerate(lowered):
            if "quintile" in h and all(k in h for k in keywords):
                out[dim] = i
                break
    return out


def parse_cimd(rows: list[list[str]]) -> dict[str, CimdIndicators]:
    """Parse CIMD CSV rows into ``{DAUID: CimdIndicators}``.

    Row 0 is the header. The DA id is the exact ``DAUID`` column (not a substring
    match, which would also catch StatCan's ``ADAUID`` aggregate id); each
    dimension's quintile column is matched by keyword. Columns are matched by name,
    so column order and exact header wording do not matter.

    Raises ``ValueError`` when a non-empty header lacks the DAUID column or the two
    need-dimension quintile columns, so a header the matcher does not recognize
    (a different marker, or a French export) fails loudly at fetch time rather than
    silently scoring every DA as unknown (ADR 0027)."""
    if not rows:
        return {}
    header = rows[0]
    lowered = [h.strip().lower() for h in header]
    da_i = next((i for i, h in enumerate(lowered) if h == "dauid"), None)
    cols = _quintile_columns(header)
    missing = [dim for dim in _NEED_DIMENSIONS if dim not in cols]
    if da_i is None or missing:
        raise ValueError(
            "CIMD CSV header not recognized: "
            f"{'no DAUID column; ' if da_i is None else ''}"
            f"{'no quintile column for ' + ', '.join(missing) + '; ' if missing else ''}"
            f"got columns {header}"
        )
    out: dict[str, CimdIndicators] = {}
    for row in rows[1:]:
        if da_i >= len(row) or not row[da_i].strip():
            continue
        vals = {dim: _quintile(row[i]) for dim, i in cols.items() if i < len(row)}
        out[row[da_i].strip()] = CimdIndicators(
            residential_instability=vals.get("residential_instability"),
            economic_dependency=vals.get("economic_dependency"),
            ethno_cultural_composition=vals.get("ethno_cultural_composition"),
            situational_vulnerability=vals.get("situational_vulnerability"),
        )
    return out


def _polygon_from_geometry(geom: dict[str, Any]) -> Polygon | None:
    """A GeoJSON geometry to a single ``Polygon`` (a MultiPolygon reduced to its
    largest part), or None when empty or unusable. Coordinates are expected in
    lon/lat (request ``outSR=4326`` from the StatCan services, which default to
    NAD83 Lambert)."""
    coords = geom.get("coordinates")
    gtype = geom.get("type")
    if not coords:
        return None
    if gtype == "Polygon":
        rings = coords
    elif gtype == "MultiPolygon":
        rings = max(coords, key=lambda part: len(part[0]) if part and part[0] else 0)
    else:
        return None
    polygon: Polygon = [[(float(x), float(y)) for x, y in ring] for ring in rings]
    if not polygon or not polygon[0]:
        return None
    return polygon


def parse_da_geometry(geojson: dict[str, Any]) -> dict[str, Polygon]:
    """Parse a StatCan DA-boundary GeoJSON FeatureCollection into ``{DAUID: polygon}``.

    The DA id is the ``DAUID`` property; empty or unusable geometry is skipped.
    Used when geometry is fetched separately from the CIMD attributes."""
    out: dict[str, Polygon] = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        dauid = props.get("DAUID") or props.get("dauid")
        polygon = _polygon_from_geometry(feature.get("geometry") or {})
        if not dauid or polygon is None:
            continue
        out[str(dauid)] = polygon
    return out


def build_das(
    geometry: dict[str, Polygon], cimd: dict[str, CimdIndicators]
) -> list[DisseminationArea]:
    """Join DA geometry and CIMD quintiles by DAUID. A DA needs both to be useful
    for the served-area test, so one present on only one side is dropped."""
    return [
        DisseminationArea(dauid=dauid, polygon=polygon, indicators=cimd[dauid])
        for dauid, polygon in geometry.items()
        if dauid in cimd
    ]


# --- served-area need tier (the ADR 0027 methodology) ------------------------


def _locate_da(lon: float, lat: float, areas: list[DisseminationArea]) -> DisseminationArea | None:
    """The DA containing a point, or None, with a bounding-box prefilter."""
    for area in areas:
        if _in_bbox(lon, lat, area.bbox) and point_in_polygon(lon, lat, area.polygon):
            return area
    return None


def _tier(quintile: float | None) -> str:
    """A within-Canada served-area quintile to a need tier. A higher mean quintile
    is more deprived, so the top two quintiles read as high need."""
    if quintile is None:
        return "unknown"
    if quintile >= 4.0:
        return "high"
    if quintile >= 3.0:
        return "moderate"
    return "lower"


def served_area_cimd(
    stop_points: list[tuple[float, float]], areas: list[DisseminationArea]
) -> tuple[str, float | None]:
    """The within-Canada need tier and stop-weighted mean quintile for a feed's
    served area, from the transit-relevant CIMD dimensions.

    Each served DA is weighted by how many of the feed's stops land in it; a stop
    in no DA is skipped. Per DA the signal is the mean of its available economic
    dependency and situational vulnerability quintiles (ADR 0027). Returns
    ("unknown", None) when no stop lands in a DA with data."""
    counts: dict[str, int] = {}
    by_id: dict[str, DisseminationArea] = {}
    for lon, lat in stop_points:
        area = _locate_da(lon, lat, areas)
        if area is None:
            continue
        counts[area.dauid] = counts.get(area.dauid, 0) + 1
        by_id[area.dauid] = area

    pairs: list[tuple[float, int]] = []
    for dauid, count in counts.items():
        ind = by_id[dauid].indicators
        dims = [getattr(ind, d) for d in _NEED_DIMENSIONS if getattr(ind, d) is not None]
        if dims:
            pairs.append((sum(dims) / len(dims), count))

    mean_q = _weighted_mean(pairs)
    if mean_q is None:
        return "unknown", None
    # Tier on the rounded value so the tier and the number shown never disagree.
    rounded = round(mean_q, 2)
    return _tier(rounded), rounded


# --- the CIMD MapServer path (geometry + quintiles in one feed) --------------

# StatCan's CIMD ESRI REST service returns each DA as a polygon whose properties
# carry the DAUID and the four dimension quintiles, so geometry and indicators
# arrive together and no separate CSV or join is needed. These are the service's
# exact field names (not the CSV headers), so they are matched exactly.
_CIMD_QUINTILE_FIELDS: dict[str, str] = {
    "residential_instability": "Residential_instability_Q",
    "economic_dependency": "Economic_dependency_Q",
    "ethno_cultural_composition": "Ethno_cultural_composition_Q",
    "situational_vulnerability": "Situational_vulnerability_Q",
}

_CIMD_SERVICE = (
    "https://maps-cartes.services.geo.ca/server2_serveur2/rest/services/"
    "StatCan/multiple_deprivation_2021/MapServer/1/query"
)


def parse_cimd_features(geojson: dict[str, Any]) -> list[DisseminationArea]:
    """Parse the CIMD MapServer's GeoJSON (geometry + quintile attributes in one
    FeatureCollection) into ``DisseminationArea`` objects.

    Each feature's properties carry the DAUID and the four quintile fields, so
    this needs no separate join. A feature with no DAUID or unusable geometry is
    skipped."""
    out: list[DisseminationArea] = []
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        dauid = props.get("DAUID") or props.get("dauid")
        polygon = _polygon_from_geometry(feature.get("geometry") or {})
        if not dauid or polygon is None:
            continue
        vals = {
            dim: _quintile("" if props.get(field) is None else str(props.get(field)))
            for dim, field in _CIMD_QUINTILE_FIELDS.items()
        }
        out.append(
            DisseminationArea(
                dauid=str(dauid),
                polygon=polygon,
                indicators=CimdIndicators(
                    residential_instability=vals["residential_instability"],
                    economic_dependency=vals["economic_dependency"],
                    ethno_cultural_composition=vals["ethno_cultural_composition"],
                    situational_vulnerability=vals["situational_vulnerability"],
                ),
            )
        )
    return out


def stops_bbox(
    stops: list[tuple[float, float]], pad: float = 0.02
) -> tuple[float, float, float, float] | None:
    """A padded lon/lat bounding box around a feed's stops, for a spatial query.

    None when the feed has no stops. The pad (~2 km at Canadian latitudes) pulls
    in DAs a stop sits near the edge of."""
    if not stops:
        return None
    lons = [lon for lon, _ in stops]
    lats = [lat for _, lat in stops]
    return (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad)


# --- gated network fetch (CI only; no key) -----------------------------------


def fetch_cimd_das(bbox: tuple[float, float, float, float]) -> list[DisseminationArea]:
    """Fetch the CIMD DAs intersecting a lon/lat bbox from the StatCan ESRI REST
    service (geometry + quintiles together), paged.

    Returns ``[]`` for a bbox in the territories, which the CIMD excludes, so a
    feed there (e.g. Yukon) reads as no-coverage rather than an error."""
    import json
    import urllib.parse

    from .net import safe_get
    from .robots_policy import shared_checker

    xmin, ymin, xmax, ymax = bbox
    fields = "DAUID," + ",".join(_CIMD_QUINTILE_FIELDS.values())
    das: list[DisseminationArea] = []
    offset = 0
    while True:
        params = urllib.parse.urlencode(
            {
                "where": "1=1",
                "geometry": f"{xmin},{ymin},{xmax},{ymax}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "outSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": fields,
                "returnGeometry": "true",
                "resultOffset": offset,
                "f": "geojson",
            }
        )
        url = f"{_CIMD_SERVICE}?{params}"
        # robots.txt first, as for feeds (ADR 0075). On 2026-11-05 this host's
        # rules said "User-agent: * / Disallow: /", so the refresh stops here.
        shared_checker().require(url)
        body = safe_get(url, timeout=90).decode()
        page = json.loads(body)
        feats = page.get("features") or []
        das.extend(parse_cimd_features(page))
        if not page.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
    return das


def agency_cimd(stops: list[tuple[float, float]]) -> tuple[str, float | None]:
    """The served-area CIMD tier for a feed's stops: bbox, fetch DAs, tier. Gated
    (CI only). ("unknown", None) when the feed has no stops or falls outside CIMD
    coverage (the territories)."""
    bbox = stops_bbox(stops)
    if bbox is None:
        return "unknown", None
    return served_area_cimd(stops, fetch_cimd_das(bbox))
