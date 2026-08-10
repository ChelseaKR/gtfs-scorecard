"""Aggregate every agency's route shapes into one national feature collection.

Each agency run emits a per-agency ``geometry.geojson`` (see ``route_geometry``):
one deduplicated ``LineString`` per route plus that feed's stops as points. The
national all-routes map wants all of those route lines on a single canvas, so
this module gathers the route features (not the stops, which would be millions of
points and illegible at national zoom) from every agency's geometry artifact and
tags each line with the things the map needs at national scale:

- ``agency`` and ``agency_name`` so a click can link back to the scorecard,
- ``route`` (the human label) and ``type`` (Bus, Rail, ...) for the popup and
  the route-type colouring,
- ``grade`` (the agency's letter grade, from ``catalog.json``) for the alternate
  grade colouring.

The output is consumed two ways. ``write_geojsonl`` writes newline-delimited
GeoJSON for tippecanoe to turn into zoom-aware vector tiles (then a ``.pmtiles``
archive); ``feature_collection`` returns a plain ``FeatureCollection`` for tests
and for a no-tile fallback. Both are deterministic: features are ordered by
(agency id, route id) and carry no wall-clock input, so a re-run reproduces the
same bytes. The PMTiles archive tippecanoe builds is a separate, non-hermetic
step (see ``scripts/build_national_pmtiles.py``).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import current_agency_ids

# Only the route lines go on the national map. Stops are the accessible
# equivalent per agency (kept on each scorecard's own table); a national point
# cloud of every stop would be both unreadable and enormous.
_ROUTE_KIND = "route"


@dataclass(frozen=True)
class NationalRoutes:
    """The aggregated national route features plus a compact summary.

    ``features`` is the list of enriched route ``LineString`` features, ordered
    deterministically. ``summary`` reports the agency/route counts and the
    grade and route-type breakdowns the page legend and the build log report.
    """

    features: list[dict[str, Any]]
    summary: dict[str, Any]


def load_catalog_grades(catalog_path: Path) -> dict[str, dict[str, str]]:
    """agency id -> {name, grade} from a published ``catalog.json``.

    The catalog is the site's own record of every agency's grade and name, so the
    national map can label and colour a route without re-reading each artifact. A
    missing or malformed catalog degrades to an empty map (every route keeps a
    neutral grade), never an error.
    """
    try:
        payload = json.loads(catalog_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict[str, str]] = {}
    for entry in payload.get("agencies", []):
        aid = entry.get("id")
        if not aid:
            continue
        out[str(aid)] = {
            "name": str(entry.get("name", aid)),
            "grade": str(entry.get("grade", "?")),
        }
    return out


def _read_route_features(geometry_path: Path) -> list[dict[str, Any]]:
    """The route ``LineString`` features from one ``geometry.geojson``, or [].

    Stops (``kind == "stop"``) and any malformed feature are skipped. An
    unreadable file yields no features rather than aborting the aggregation.
    """
    try:
        fc = json.loads(geometry_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    features = fc.get("features")
    if not isinstance(features, list):
        return []
    out: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(props, dict) or not isinstance(geometry, dict):
            continue
        if props.get("kind") != _ROUTE_KIND:
            continue
        if geometry.get("type") != "LineString":
            continue
        out.append(feature)
    return out


def iter_national_route_features(
    artifacts_root: Path,
    grades: dict[str, dict[str, str]],
    *,
    allowed_agency_ids: Collection[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield every agency's route lines, enriched for the national map.

    Agencies are visited in id order, and within an agency the route features
    keep their artifact order (which ``route_geometry`` already sorts by route
    id), so the stream is deterministic. Each yielded feature carries only the
    properties the national map uses, keeping the vector tiles small.
    """
    agency_dirs = sorted(p for p in artifacts_root.iterdir() if p.is_dir())
    current_ids = set(current_agency_ids(agency_dir.name for agency_dir in agency_dirs))
    if allowed_agency_ids is not None:
        current_ids.intersection_update(allowed_agency_ids)
    for agency_dir in agency_dirs:
        # An S3-hydrated tree can retain retired aliases and unlisted artifact
        # directories. A populated registry is authoritative; direct renderers
        # can also pass the ids in their already-scoped public catalog.
        if agency_dir.name not in current_ids:
            continue
        geometry_path = agency_dir / "geometry.geojson"
        if not geometry_path.exists():
            continue
        agency_id = agency_dir.name
        meta = grades.get(agency_id, {})
        agency_name = meta.get("name", agency_id)
        grade = meta.get("grade", "?")
        for feature in _read_route_features(geometry_path):
            props = feature["properties"]
            yield {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {
                    "agency": agency_id,
                    "agency_name": agency_name,
                    "route": props.get("label", props.get("route_id", "")),
                    "type": props.get("type_label", "Transit line"),
                    "grade": grade,
                },
            }


def build_national_routes(
    artifacts_root: Path,
    grades: dict[str, dict[str, str]],
    *,
    allowed_agency_ids: Collection[str] | None = None,
) -> NationalRoutes:
    """Aggregate all agencies' route lines into one national collection."""
    features = list(
        iter_national_route_features(
            artifacts_root,
            grades,
            allowed_agency_ids=allowed_agency_ids,
        )
    )
    agencies = {f["properties"]["agency"] for f in features}
    grade_counts = Counter(f["properties"]["grade"] for f in features)
    type_counts = Counter(f["properties"]["type"] for f in features)
    summary = {
        "agency_count": len(agencies),
        "route_count": len(features),
        "grade_counts": dict(sorted(grade_counts.items())),
        "type_counts": dict(sorted(type_counts.items())),
    }
    return NationalRoutes(features=features, summary=summary)


def feature_collection(routes: NationalRoutes) -> dict[str, Any]:
    """A plain ``FeatureCollection`` of the aggregated routes (for the fallback
    and for tests). The PMTiles path uses ``write_geojsonl`` instead."""
    return {"type": "FeatureCollection", "features": routes.features}


def write_geojsonl(routes: NationalRoutes, out_path: Path) -> int:
    """Write newline-delimited GeoJSON features for tippecanoe; return the count.

    Newline-delimited (one feature per line) is tippecanoe's preferred input and
    streams without loading the whole collection into memory. Keys are sorted so
    the intermediate file is byte-for-byte reproducible.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for feature in routes.features:
            fh.write(json.dumps(feature, sort_keys=True, separators=(",", ":")))
            fh.write("\n")
    return len(routes.features)
