#!/usr/bin/env python3
"""Build the national all-routes vector tiles and package them as PMTiles.

This is a separate, non-hermetic build step: it shells out to **tippecanoe**,
which is not part of the daily render image. Keep it off the daily build (see
``.github/workflows/tiles.yml`` for the dedicated, on-demand workflow) and run it
when the route geometry changes:

    python3 pipeline/scripts/build_national_pmtiles.py

Steps:
  1. Aggregate every agency's ``geometry.geojson`` route lines into one
     newline-delimited GeoJSON (``national_routes.aggregate``), tagging each line
     with agency, route name, route type, and the agency's grade.
  2. Run tippecanoe to build zoom-aware, aggressively simplified vector tiles and
     write them straight to a single ``.pmtiles`` archive.
  3. Report the archive size so the hosting decision (commit to ``web/`` vs.
     S3+CloudFront, see docs/decisions/0023) can be made against the threshold.

The aggregated GeoJSONL is deterministic; the PMTiles bytes are **not**
guaranteed reproducible (tippecanoe embeds build metadata and may parallelise
feature ordering), so the archive is treated as a generated asset, not a
checked-invariant.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from scorecard_pipeline.agencies import read_agencies
from scorecard_pipeline.config import artifacts_dir, repo_root
from scorecard_pipeline.national_routes import (
    build_national_routes,
    load_catalog_grades,
    write_geojsonl,
)

# Aggressive low-zoom simplification keeps the national view legible and the
# archive small; detail returns as you zoom in. --drop-densest-as-needed sheds
# features where lines pile up rather than letting a metro's bundle blow the tile
# size budget. -zg lets tippecanoe choose the max zoom from the data.
_TIPPECANOE_ARGS = [
    "--layer=routes",
    "--name=National transit routes",
    "--attribution=GTFS Scorecard, CC BY 4.0",
    "-zg",
    "--minimum-zoom=2",
    "--simplification=10",
    "--drop-densest-as-needed",
    "--extend-zooms-if-still-dropping",
    "--no-tile-size-limit",
    "--force",
]


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = repo_root()
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=artifacts_dir(),
        help="artifacts root holding per-agency geometry.geojson (default: data/artifacts)",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=root / "web" / "catalog.json",
        help="catalog.json for agency names and grades (default: web/catalog.json)",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=root / "build" / "tiles",
        help="scratch dir for the intermediate GeoJSONL (default: build/tiles)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "web" / "tiles" / "national-routes.pmtiles",
        help="output .pmtiles path (default: web/tiles/national-routes.pmtiles)",
    )
    parser.add_argument(
        "--geojsonl-only",
        action="store_true",
        help="only write the aggregated GeoJSONL; skip tippecanoe (no tile tool needed)",
    )
    args = parser.parse_args(argv)

    grades = load_catalog_grades(args.catalog)
    # Catalog grade metadata is optional, but current-corpus membership is not.
    # Derive the allowlist from the validated registry so a missing or malformed
    # catalog merely produces neutral ``?`` grades instead of reviving retained
    # alias/unregistered geometry in the national tiles.
    canonical_ids = {agency.id for agency in read_agencies() if agency.is_canonical_feed}
    routes = build_national_routes(
        args.artifacts,
        grades,
        allowed_agency_ids=canonical_ids,
    )
    geojsonl_path = args.build_dir / "national_routes.geojsonl"
    count = write_geojsonl(routes, geojsonl_path)

    summary = routes.summary
    print(
        f"Aggregated {count} route lines from {summary['agency_count']} agencies "
        f"-> {geojsonl_path}",
        file=sys.stderr,
    )
    print(f"  by grade: {summary['grade_counts']}", file=sys.stderr)
    print(f"  by type:  {summary['type_counts']}", file=sys.stderr)

    if count == 0:
        print(
            "No route geometry found. Run agency scoring first so each agency "
            "emits data/artifacts/<id>/geometry.geojson.",
            file=sys.stderr,
        )
        return 1

    if args.geojsonl_only:
        print("--geojsonl-only set; skipping tippecanoe.", file=sys.stderr)
        return 0

    tippecanoe = shutil.which("tippecanoe")
    if tippecanoe is None:
        print(
            "tippecanoe not found on PATH. Install it (brew install tippecanoe) or "
            "run the tiles workflow, then re-run. The aggregated GeoJSONL is ready "
            f"at {geojsonl_path}.",
            file=sys.stderr,
        )
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [tippecanoe, "-o", str(args.out), *_TIPPECANOE_ARGS, str(geojsonl_path)]
    print("Running:", " ".join(cmd), file=sys.stderr)
    # argv list, no shell=True; tippecanoe is resolved from PATH above and
    # every remaining element is a module constant or an argparse path.
    result = subprocess.run(cmd, check=False)  # noqa: S603
    if result.returncode != 0:
        print("tippecanoe failed.", file=sys.stderr)
        return result.returncode

    size = args.out.stat().st_size
    print(f"\nWrote {args.out} ({_human_size(size)}, {size} bytes)", file=sys.stderr)
    print(
        "Hosting threshold (docs/decisions/0023): commit to web/ if <= 25 MB, "
        "else publish to S3+CloudFront.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
