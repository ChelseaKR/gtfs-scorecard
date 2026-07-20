#!/usr/bin/env python3
"""Generate web/world-countries.json: one simplified SVG path per country.

The global overview's choropleth needs country geometry, but the pipeline must
stay hermetic (no geo libraries, no runtime download). So this is a one-off
build tool, a sibling of build_us_map.py: it fetches a public-domain world
countries GeoJSON, projects it to a fixed SVG viewBox, and writes a compact
{ISO 3166-1 alpha-2 code: path d} map the web app colors at runtime. Re-run it
only to refresh or re-simplify the geometry.

Source: https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json
— Natural Earth 1:110m admin-0 boundaries republished as GeoJSON. Natural Earth
data is in the public domain (no copyright, free for any use), and the
johan/world.geo.json repository redistributes it unchanged. Feature ids are
ISO 3166-1 alpha-3 codes; ISO3_TO_ISO2 below covers exactly the codes present.

Projection: a cos(lat0)-corrected equirectangular, as in build_us_map.py. At
world scale the standard parallel is the equator, so the correction is the
identity, and the map is the familiar plate carree. Antarctica is excluded.
Rings whose projected area is under ~3 square px are dropped, except that a
country's largest ring is always kept (Luxembourg and Malta are sub-threshold
whole countries, and the choropleth must be able to fill them). Coordinates are
rounded to 1 decimal, and if the artifact would exceed 250 KB a distance-based
point thinning tightens until it fits.

Usage: python scripts/build_world_map.py [--source URL] [--out web/world-countries.json]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from urllib.request import urlopen

SOURCE = (
    "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json"
)
VIEW_W, VIEW_H = 960.0, 480.0
OMIT = {"AQ"}  # Antarctica: no agencies, and it would dominate the frame
MIN_RING_AREA_PX = 3.0  # projected square px; drops islet specks
MAX_BYTES = 250_000

# ISO 3166-1 alpha-3 -> alpha-2, hand-coded for exactly the ids in SOURCE.
# "CS-KM" is the source's non-standard id for Kosovo; XK is the user-assigned
# alpha-2 code in wide use. Features with id "-99" (Northern Cyprus,
# Somaliland) have no ISO code and are skipped.
ISO3_TO_ISO2 = {
    "AFG": "AF", "AGO": "AO", "ALB": "AL", "ARE": "AE", "ARG": "AR", "ARM": "AM",
    "ATA": "AQ", "ATF": "TF", "AUS": "AU", "AUT": "AT", "AZE": "AZ", "BDI": "BI",
    "BEL": "BE", "BEN": "BJ", "BFA": "BF", "BGD": "BD", "BGR": "BG", "BHS": "BS",
    "BIH": "BA", "BLR": "BY", "BLZ": "BZ", "BMU": "BM", "BOL": "BO", "BRA": "BR",
    "BRN": "BN", "BTN": "BT", "BWA": "BW", "CAF": "CF", "CAN": "CA", "CHE": "CH",
    "CHL": "CL", "CHN": "CN", "CIV": "CI", "CMR": "CM", "COD": "CD", "COG": "CG",
    "COL": "CO", "CRI": "CR", "CS-KM": "XK", "CUB": "CU", "CYP": "CY", "CZE": "CZ",
    "DEU": "DE", "DJI": "DJ", "DNK": "DK", "DOM": "DO", "DZA": "DZ", "ECU": "EC",
    "EGY": "EG", "ERI": "ER", "ESH": "EH", "ESP": "ES", "EST": "EE", "ETH": "ET",
    "FIN": "FI", "FJI": "FJ", "FLK": "FK", "FRA": "FR", "GAB": "GA", "GBR": "GB",
    "GEO": "GE", "GHA": "GH", "GIN": "GN", "GMB": "GM", "GNB": "GW", "GNQ": "GQ",
    "GRC": "GR", "GRL": "GL", "GTM": "GT", "GUF": "GF", "GUY": "GY", "HND": "HN",
    "HRV": "HR", "HTI": "HT", "HUN": "HU", "IDN": "ID", "IND": "IN", "IRL": "IE",
    "IRN": "IR", "IRQ": "IQ", "ISL": "IS", "ISR": "IL", "ITA": "IT", "JAM": "JM",
    "JOR": "JO", "JPN": "JP", "KAZ": "KZ", "KEN": "KE", "KGZ": "KG", "KHM": "KH",
    "KOR": "KR", "KWT": "KW", "LAO": "LA", "LBN": "LB", "LBR": "LR", "LBY": "LY",
    "LKA": "LK", "LSO": "LS", "LTU": "LT", "LUX": "LU", "LVA": "LV", "MAR": "MA",
    "MDA": "MD", "MDG": "MG", "MEX": "MX", "MKD": "MK", "MLI": "ML", "MLT": "MT",
    "MMR": "MM", "MNE": "ME", "MNG": "MN", "MOZ": "MZ", "MRT": "MR", "MWI": "MW",
    "MYS": "MY", "NAM": "NA", "NCL": "NC", "NER": "NE", "NGA": "NG", "NIC": "NI",
    "NLD": "NL", "NOR": "NO", "NPL": "NP", "NZL": "NZ", "OMN": "OM", "PAK": "PK",
    "PAN": "PA", "PER": "PE", "PHL": "PH", "PNG": "PG", "POL": "PL", "PRI": "PR",
    "PRK": "KP", "PRT": "PT", "PRY": "PY", "PSE": "PS", "QAT": "QA", "ROU": "RO",
    "RUS": "RU", "RWA": "RW", "SAU": "SA", "SDN": "SD", "SEN": "SN", "SLB": "SB",
    "SLE": "SL", "SLV": "SV", "SOM": "SO", "SRB": "RS", "SSD": "SS", "SUR": "SR",
    "SVK": "SK", "SVN": "SI", "SWE": "SE", "SWZ": "SZ", "SYR": "SY", "TCD": "TD",
    "TGO": "TG", "THA": "TH", "TJK": "TJ", "TKM": "TM", "TLS": "TL", "TTO": "TT",
    "TUN": "TN", "TUR": "TR", "TWN": "TW", "TZA": "TZ", "UGA": "UG", "UKR": "UA",
    "URY": "UY", "USA": "US", "UZB": "UZ", "VEN": "VE", "VNM": "VN", "VUT": "VU",
    "YEM": "YE", "ZAF": "ZA", "ZMB": "ZM", "ZWE": "ZW",
}


def _rings(geometry: dict) -> list[list[list[float]]]:
    """Flatten a Polygon/MultiPolygon to a list of rings of [lon, lat]."""
    if geometry["type"] == "Polygon":
        return list(geometry["coordinates"])
    rings: list[list[list[float]]] = []
    for poly in geometry["coordinates"]:
        rings.extend(poly)
    return rings


def _project(lon: float, lat: float, lat0: float) -> tuple[float, float]:
    return lon * math.cos(math.radians(lat0)), -lat


def _bbox(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _fit(bbox, box):
    """A function mapping projected (x, y) into a target box, aspect preserved
    and centered. box = (x0, y0, w, h)."""
    minx, miny, maxx, maxy = bbox
    bx, by, bw, bh = box
    spanx = maxx - minx or 1.0
    spany = maxy - miny or 1.0
    scale = min(bw / spanx, bh / spany)
    ox = bx + (bw - spanx * scale) / 2
    oy = by + (bh - spany * scale) / 2

    def fn(x: float, y: float) -> tuple[float, float]:
        return ox + (x - minx) * scale, oy + (y - miny) * scale

    return fn


def _ring_points(features, lat0):
    pts = []
    for feat in features:
        for ring in _rings(feat["geometry"]):
            for lon, lat in ring:
                pts.append(_project(lon, lat, lat0))
    return pts


def _area(coords: list[tuple[float, float]]) -> float:
    """Unsigned shoelace area of a ring in projected square px."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:] + coords[:1]):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _thin(coords: list[tuple[float, float]], min_dist: float) -> list[tuple[float, float]]:
    """Keep points at least min_dist px from the previous kept point."""
    if min_dist <= 0:
        return coords
    kept = [coords[0]]
    for pt in coords[1:]:
        px, py = kept[-1]
        if math.hypot(pt[0] - px, pt[1] - py) >= min_dist:
            kept.append(pt)
    return kept


def _path_for(feature, lat0, fit, min_dist: float) -> str:
    rings = [[fit(*_project(lon, lat, lat0)) for lon, lat in ring] for ring in _rings(feature["geometry"])]
    largest = max(rings, key=_area) if rings else None
    parts: list[str] = []
    for coords in rings:
        # Drop islet specks, but never a country's only visible ring.
        if _area(coords) < MIN_RING_AREA_PX and coords is not largest:
            continue
        coords = _thin(coords, min_dist)
        rounded: list[str] = []
        for x, y in coords:
            pt = f"{x:.1f},{y:.1f}"
            if not rounded or rounded[-1] != pt:
                rounded.append(pt)
        if len(rounded) >= 3:
            parts.append("M" + "L".join(rounded) + "Z")
    return "".join(parts)


def build(geojson: dict, min_dist: float) -> dict[str, str]:
    lat0 = 0.0
    feats = []
    for feat in geojson["features"]:
        code = ISO3_TO_ISO2.get(feat.get("id", ""))
        if code is None or code in OMIT:
            continue  # no ISO code (Northern Cyprus, Somaliland) or Antarctica
        feats.append((code, feat))

    fit = _fit(_bbox(_ring_points([f for _, f in feats], lat0)), (10, 10, VIEW_W - 20, VIEW_H - 20))
    out: dict[str, str] = {}
    for code, feat in feats:
        path = _path_for(feat, lat0, fit, min_dist)
        if path:
            out[code] = path
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=SOURCE)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "web" / "world-countries.json"))
    args = ap.parse_args()

    with urlopen(args.source, timeout=30) as resp:  # noqa: S310 - fixed https source
        geojson = json.loads(resp.read().decode("utf-8"))

    # Round-to-1-decimal alone usually fits; thin progressively if it does not.
    min_dist = 0.0
    while True:
        paths = build(geojson, min_dist)
        payload = {"viewBox": f"0 0 {int(VIEW_W)} {int(VIEW_H)}", "countries": paths}
        body = json.dumps(payload, separators=(",", ":")) + "\n"
        if len(body) <= MAX_BYTES:
            break
        min_dist = 0.8 if min_dist == 0.0 else min_dist * 1.25
    Path(args.out).write_text(body)
    print(f"wrote {args.out}: {len(paths)} countries, {len(body)} bytes (thinning {min_dist}px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
