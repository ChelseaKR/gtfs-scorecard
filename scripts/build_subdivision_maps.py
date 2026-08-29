#!/usr/bin/env python3
"""Generate web/subdivisions/<cc>.json: one simplified SVG path per admin-1
subdivision, for the map drill-down below the world overview.

Selecting a country on the world map drops to a subdivision choropleth, so each
covered country needs its own admin-1 geometry. As with build_world_map.py and
build_us_map.py the pipeline stays hermetic (no geo libraries, no runtime
download), so this is a one-off build tool: it fetches a public-domain admin-1
GeoJSON, projects each country to its own SVG viewBox, and writes a compact
{ISO 3166-2 code: path d} map the web app colors at runtime. Re-run it only to
refresh, re-simplify, or add a country.

Source: https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson
— Natural Earth 1:10m admin-1 states/provinces. Natural Earth data is in the
public domain (no copyright, free for any use), and the nvkelso/natural-earth-
vector repository redistributes it unchanged. Each feature carries iso_a2 (the
country) plus two ISO 3166-2 codes: iso_3166_2 for the mapped unit (a British
county, a German state, a French department, an Italian or Spanish province) and
region_cod for its parent admin-1 region (a French or Italian region, a Spanish
autonomous community; hyphenated for FR/IT like FR-HDF / IT-25, dotted for ES
like ES.CT, normalized to a hyphen here). The 50m file is far too coarse (no
British counties), so 10m is required despite its size.

Keying: the agency registry tags subdivisions at whichever level is meaningful
for that country — county/state level for GB and DE (iso_3166_2), region level
for FR and IT (region_cod), and a mix of both for ES. So per country this picks
the single coherent level (fine iso_3166_2 vs dissolved region_cod) that covers
more registry codes, then supplements any still-missing registry code buildable
from the other level (this is what lets ES carry both its province and its
autonomous-community codes). REGISTRY below is the set of codes the registry
currently uses; it drives that choice and the printed coverage report, and
should be refreshed if the registry's subdivision tags change.

Projection: a cos(lat0)-corrected equirectangular, as in build_world_map.py,
with lat0 the country's centroid latitude so shapes are not sheared. Each
country gets its own viewBox fit to its projected bounding box. Geographic
outliers (French Caribbean and Indian Ocean regions, which would collapse the
metropolitan frame to a speck) are dropped unless they are registry codes, so a
far overseas region such as FR-974 (La Reunion) is simply absent from the
metropolitan-France frame. Rings whose projected area is under ~2 square px are
dropped, except that a subdivision's largest ring is always kept so every unit
renders. Coordinates are rounded to 1 decimal, consecutive duplicates collapse,
and if a country file would exceed ~120 KB a distance-based point thinning
tightens until it fits.

Usage: python scripts/build_subdivision_maps.py [--source URL]
       [--out-dir web/subdivisions] [--countries GB,FR,DE,ES,IT]
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from urllib.request import urlopen

SOURCE = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_10m_admin_1_states_provinces.geojson"
)
COUNTRIES = ["GB", "FR", "DE", "ES", "IT", "CA", "AU", "NZ", "JP", "MY", "BR"]
MARGIN = 8.0  # blank border, in viewBox px, around the fitted country
MAX_DIM = 1000.0  # the longer viewBox axis; the shorter follows the aspect ratio
MIN_RING_AREA_PX = 2.0  # projected square px; drops islet specks
MAX_BYTES = 120_000
IQR_K = 3.0  # centroids past this many IQRs from the median are outliers

ISO_3166_2 = re.compile(r"^[A-Z]{2}-[A-Z0-9]+$")

# ISO 3166-2 codes the agency registry currently tags subdivisions with, per
# country. Used to pick the admin-1 granularity (see the module docstring) and
# to report drill-down coverage. FR-974 (La Reunion) is listed but expected to
# be absent: Natural Earth codes it FR-LRE, and it falls outside a metropolitan
# frame regardless. Refresh this if the registry's subdivision tags change.
REGISTRY = {
    "GB": {
        "GB-BCP",
        "GB-BKM",
        "GB-BNH",
        "GB-BPL",
        "GB-CON",
        "GB-CRF",
        "GB-DND",
        "GB-ERY",
        "GB-ESS",
        "GB-FAL",
        "GB-GAT",
        "GB-HAM",
        "GB-HRT",
        "GB-IOW",
        "GB-IVC",
        "GB-NFK",
        "GB-NGM",
        "GB-NWP",
        "GB-NYK",
        "GB-OXF",
        "GB-PLY",
        "GB-RDG",
        "GB-SCB",
        "GB-STH",
        "GB-SWD",
        "GB-WBK",
        "GB-WIL",
        "GB-WNM",
        "GB-WRT",
        "GB-WSX",
    },
    "FR": {
        "FR-ARA",
        "FR-BFC",
        "FR-BRE",
        "FR-CVL",
        "FR-GES",
        "FR-HDF",
        "FR-IDF",
        "FR-NAQ",
        "FR-NOR",
        "FR-PAC",
        "FR-PDL",
        "FR-974",
    },
    "DE": {"DE-BE", "DE-BW", "DE-NW"},
    "ES": {
        "ES-B",
        "ES-BI",
        "ES-CT",
        "ES-MA",
        "ES-MD",
        "ES-PM",
        "ES-TF",
        "ES-V",
        "ES-VI",
    },
    "IT": {
        "IT-25",
        "IT-32",
        "IT-34",
        "IT-42",
        "IT-52",
        "IT-62",
        "IT-72",
        "IT-75",
        "IT-78",
        "IT-82",
        "IT-88",
    },
    # Canada's provinces and territories are admin-1 (iso_3166_2 CA-ON, CA-QC,
    # ...), so no region-level dissolve is needed. Only two carry feeds today.
    "CA": {"CA-ON", "CA-YT"},
    # Australia's states and territories are admin-1 (iso_3166_2 AU-QLD, AU-VIC,
    # ...), so no region-level dissolve is needed.
    "AU": {"AU-NT", "AU-QLD", "AU-SA", "AU-VIC", "AU-WA"},
    # New Zealand's regions are admin-1 (iso_3166_2 NZ-AUK, NZ-BOP, NZ-OTA, ...),
    # so no region-level dissolve is needed.
    "NZ": {"NZ-AUK", "NZ-BOP", "NZ-OTA"},
    # Japan's prefectures are admin-1 (iso_3166_2 JP-01 ... JP-47), so no
    # region-level dissolve is needed. Forty carry feeds today.
    "JP": {
        "JP-01",
        "JP-02",
        "JP-03",
        "JP-04",
        "JP-05",
        "JP-06",
        "JP-07",
        "JP-08",
        "JP-09",
        "JP-10",
        "JP-11",
        "JP-12",
        "JP-13",
        "JP-14",
        "JP-15",
        "JP-16",
        "JP-17",
        "JP-19",
        "JP-20",
        "JP-21",
        "JP-22",
        "JP-23",
        "JP-24",
        "JP-25",
        "JP-27",
        "JP-28",
        "JP-29",
        "JP-30",
        "JP-32",
        "JP-33",
        "JP-36",
        "JP-37",
        "JP-39",
        "JP-40",
        "JP-41",
        "JP-42",
        "JP-43",
        "JP-44",
        "JP-46",
        "JP-47",
    },
    # Malaysia's states are admin-1 (iso_3166_2 MY-01 ... MY-16), so no
    # region-level dissolve is needed.
    "MY": {"MY-06", "MY-07", "MY-09", "MY-14"},
    # Brazil's states are admin-1 (iso_3166_2 BR-MG, BR-RJ, ...), so no
    # region-level dissolve is needed.
    "BR": {"BR-MG", "BR-RJ"},
}


def _norm(code: str | None) -> str | None:
    """Uppercase an ISO 3166-2 code and accept only well-formed CC-XXX values.
    region_cod is dotted for Spain (ES.CT), so a dot normalizes to a hyphen."""
    if not code:
        return None
    code = code.strip().upper().replace(".", "-")
    return code if ISO_3166_2.match(code) else None


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


def _area(coords: list[tuple[float, float]]) -> float:
    """Unsigned shoelace area of a ring in projected square px."""
    total = 0.0
    # Same ring, rotated by one, so the two are the same length by
    # construction; strict=True records that rather than assuming it.
    for (x1, y1), (x2, y2) in zip(coords, coords[1:] + coords[:1], strict=True):
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


def _centroid(rings: list[list[list[float]]]) -> tuple[float, float]:
    """A subdivision's rough lon/lat centroid, the mean of its largest ring."""
    big = max(rings, key=_area)
    xs = [p[0] for p in big]
    ys = [p[1] for p in big]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _levels(features: list[dict]) -> tuple[dict, dict]:
    """Group a country's features into two admin-1 candidates keyed by ISO
    3166-2 code: fine (iso_3166_2, the mapped unit) and coarse (region_cod, the
    parent region, dissolved by collecting every member ring)."""
    fine: dict[str, list] = {}
    coarse: dict[str, list] = {}
    for feat in features:
        rings = _rings(feat["geometry"])
        code = _norm(feat["properties"].get("iso_3166_2"))
        if code:
            fine.setdefault(code, []).extend(rings)
        parent = _norm(feat["properties"].get("region_cod"))
        if parent:
            coarse.setdefault(parent, []).extend(rings)
    return fine, coarse


def _select(fine: dict, coarse: dict, registry: set[str]) -> dict[str, list]:
    """Pick the coherent admin-1 level covering more registry codes, then add
    any still-missing registry code buildable from the other level."""
    base, other = (fine, coarse)
    if len(registry & coarse.keys()) > len(registry & fine.keys()):
        base, other = coarse, fine
    subs = dict(base)
    for code in registry:
        if code not in subs and code in other:
            subs[code] = other[code]
    return subs


def _drop_outliers(subs: dict, registry: set[str]) -> dict[str, list]:
    """Drop far-flung subdivisions (French overseas regions would shrink the
    metropolitan frame to a speck) by an interquartile fence on centroids.
    Registry codes are never dropped."""
    if len(subs) < 4:
        return subs
    cents = {code: _centroid(rings) for code, rings in subs.items()}

    def fence(values: list[float]) -> tuple[float, float]:
        s = sorted(values)
        q1, q3 = s[len(s) // 4], s[(3 * len(s)) // 4]
        iqr = (q3 - q1) or 1.0
        return q1 - IQR_K * iqr, q3 + IQR_K * iqr

    lo_lon, hi_lon = fence([c[0] for c in cents.values()])
    lo_lat, hi_lat = fence([c[1] for c in cents.values()])
    kept: dict[str, list] = {}
    for code, rings in subs.items():
        clon, clat = cents[code]
        inside = lo_lon <= clon <= hi_lon and lo_lat <= clat <= hi_lat
        if code in registry or inside:
            kept[code] = rings
    return kept


def _path_for(rings, lat0, fit, min_dist: float) -> str:
    projected = [[fit(*_project(lon, lat, lat0)) for lon, lat in ring] for ring in rings]
    largest = max(projected, key=_area) if projected else None
    parts: list[str] = []
    for coords in projected:
        # Drop islet specks, but never a subdivision's largest ring.
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


def build(features: list[dict], country: str, min_dist: float) -> tuple[dict, str, int, int]:
    """Build one country's payload: pick a level, drop outliers, project into a
    country-specific viewBox, and simplify each subdivision to an SVG path."""
    registry = REGISTRY.get(country, set())
    subs = _drop_outliers(_select(*_levels(features), registry), registry)

    lonlat = [(lon, lat) for rings in subs.values() for ring in rings for lon, lat in ring]
    lats = [lat for _lon, lat in lonlat]
    lat0 = (min(lats) + max(lats)) / 2.0  # standard parallel: the country's centroid latitude
    proj_pts = [_project(lon, lat, lat0) for lon, lat in lonlat]
    minx, miny, maxx, maxy = _bbox(proj_pts)
    spanx, spany = (maxx - minx) or 1.0, (maxy - miny) or 1.0
    scale = (MAX_DIM - 2 * MARGIN) / max(spanx, spany)
    w = round(spanx * scale + 2 * MARGIN)
    h = round(spany * scale + 2 * MARGIN)
    fit = _fit((minx, miny, maxx, maxy), (MARGIN, MARGIN, w - 2 * MARGIN, h - 2 * MARGIN))

    paths: dict[str, str] = {}
    for code, rings in subs.items():
        path = _path_for(rings, lat0, fit, min_dist)
        if path:
            paths[code] = path
    # Sort by subdivision code so the output is byte-deterministic regardless of
    # the set-iteration order upstream; otherwise a regeneration (e.g. the
    # geometry-refresh workflow) produces spurious key-reordering diffs.
    ordered = dict(sorted(paths.items()))
    payload = {"viewBox": f"0 0 {w} {h}", "country": country, "subdivisions": ordered}
    body = json.dumps(payload, separators=(",", ":")) + "\n"
    return ordered, body, w, h


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=SOURCE)
    ap.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parents[1] / "web" / "subdivisions"),
    )
    ap.add_argument("--countries", default=",".join(COUNTRIES))
    args = ap.parse_args()

    with urlopen(args.source, timeout=120) as resp:  # noqa: S310 - fixed https source
        geojson = json.loads(resp.read().decode("utf-8"))

    by_country: dict[str, list[dict]] = {}
    for feat in geojson["features"]:
        by_country.setdefault(feat["properties"].get("iso_a2"), []).append(feat)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for country in [c.strip().upper() for c in args.countries.split(",") if c.strip()]:
        features = by_country.get(country, [])
        if not features:
            print(f"{country}: no features in source, skipped")
            continue
        # Round-to-1-decimal alone usually fits; thin progressively if it does not.
        min_dist = 0.0
        while True:
            paths, body, _w, _h = build(features, country, min_dist)
            if len(body) <= MAX_BYTES:
                break
            min_dist = 0.8 if min_dist == 0.0 else min_dist * 1.25
        out_path = out_dir / f"{country.lower()}.json"
        out_path.write_text(body)

        registry = REGISTRY.get(country, set())
        present = sorted(c for c in registry if c in paths)
        missing = sorted(c for c in registry if c not in paths)
        print(
            f"wrote {out_path}: {len(paths)} subdivisions, {len(body)} bytes "
            f"(thinning {min_dist}px) — registry coverage {len(present)}/{len(registry)}"
            + (f", missing {missing}" if missing else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
