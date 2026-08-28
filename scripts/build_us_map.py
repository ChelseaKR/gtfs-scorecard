#!/usr/bin/env python3
"""Generate web/us-states.json: one simplified SVG path per US state.

The national overview's choropleth needs state geometry, but the pipeline must
stay hermetic (no geo libraries, no runtime download). So this is a one-off
build tool: it fetches a public-domain US states GeoJSON, projects it to a fixed
SVG viewBox, and writes a compact {state name: path d} map the web app colors at
runtime. Re-run it only to refresh or re-simplify the geometry.

Projection: a cos(lat0)-corrected equirectangular for the lower 48 plus DC,
which is faithful enough at this size, with Alaska and Hawaii drawn as the
conventional insets at the lower left (Alaska's Aleutian longitudes are unwrapped
so the state stays contiguous). Puerto Rico and other non-contiguous areas are
left to the directory's state list rather than crowding the map.

Usage: python scripts/build_us_map.py [--source URL] [--out web/us-states.json]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from urllib.request import urlopen

SOURCE = (
    "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"
)
VIEW_W, VIEW_H = 960.0, 600.0
INSETS = {"Alaska", "Hawaii"}
OMIT = {"Puerto Rico"}  # shown in the state list, not on the contiguous map


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


def _ring_points(features, lat0, unwrap=False):
    pts = []
    for feat in features:
        for ring in _rings(feat["geometry"]):
            for lon, lat in ring:
                if unwrap and lon > 0:
                    lon -= 360
                pts.append(_project(lon, lat, lat0))
    return pts


def _path_for(feature, lat0, fit, unwrap=False) -> str:
    parts: list[str] = []
    for ring in _rings(feature["geometry"]):
        coords = []
        for lon, lat in ring:
            if unwrap and lon > 0:
                lon -= 360
            x, y = fit(*_project(lon, lat, lat0))
            coords.append(f"{x:.1f},{y:.1f}")
        if coords:
            parts.append("M" + "L".join(coords) + "Z")
    return "".join(parts)


def build(geojson: dict) -> dict[str, str]:
    feats = {f["properties"]["name"]: f for f in geojson["features"]}
    main = [f for n, f in feats.items() if n not in INSETS and n not in OMIT]

    out: dict[str, str] = {}
    # Lower 48 + DC into the main area (leaving room at the bottom for insets).
    lat0 = 39.0
    fit_main = _fit(_bbox(_ring_points(main, lat0)), (15, 10, VIEW_W - 30, VIEW_H - 130))
    for feat in main:
        out[feat["properties"]["name"]] = _path_for(feat, lat0, fit_main)

    # Alaska inset, lower left (Aleutians unwrapped so the state is contiguous).
    if "Alaska" in feats:
        ak = feats["Alaska"]
        fit_ak = _fit(_bbox(_ring_points([ak], 60.0, unwrap=True)), (10, VIEW_H - 175, 215, 165))
        out["Alaska"] = _path_for(ak, 60.0, fit_ak, unwrap=True)
    # Hawaii inset, to the right of Alaska.
    if "Hawaii" in feats:
        hi = feats["Hawaii"]
        fit_hi = _fit(_bbox(_ring_points([hi], 20.0)), (240, VIEW_H - 110, 120, 95))
        out["Hawaii"] = _path_for(hi, 20.0, fit_hi)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=SOURCE)
    ap.add_argument(
        "--out", default=str(Path(__file__).resolve().parents[1] / "web" / "us-states.json")
    )
    args = ap.parse_args()

    with urlopen(args.source, timeout=30) as resp:  # noqa: S310 - fixed https source
        geojson = json.loads(resp.read().decode("utf-8"))
    paths = build(geojson)
    payload = {"viewBox": f"0 0 {int(VIEW_W)} {int(VIEW_H)}", "states": paths}
    Path(args.out).write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    print(f"wrote {args.out}: {len(paths)} states")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
