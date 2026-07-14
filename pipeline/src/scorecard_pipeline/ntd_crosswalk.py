"""Populate agency NTD IDs from the Transitland Atlas crosswalk.

ADR 0016 added an `ntd_id` to the registry so the scorecard can compare optional
equality with the required feed `agency_id`. That comparison can only run where
we know the NTD ID, and we curated it only for the two pilots. Required
agency_id presence is checked separately. The Transitland Atlas
(github.com/transitland/transitland-atlas, CC-BY) records `us_ntd_id` on its US
operators and links each operator to its feeds, so it is an open join from a
feed to its five-digit NTD ID. This turns that into a one-time, reviewable
population of `ntd_id` across the registry.

The join key is the feed's static URL: each Atlas feed carries a
`urls.static_current`, and each operator carries `us_ntd_id` plus the Onestop IDs
of its feeds. We map every feed URL to its operator's NTD ID, then match our
registry's `static_gtfs_url` against it. A URL that the Atlas links to more than
one NTD ID (a shared regional feed) is dropped rather than guessed, so we never
assign one agency the NTD ID of a feed it shares. The matching functions are pure
over parsed Atlas documents and the registry, so they are testable without the
network; only `fetch_atlas` reaches out.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

ATLAS_API = "https://api.github.com/repos/transitland/transitland-atlas/contents/feeds?ref=main"
ATLAS_RAW = "https://raw.githubusercontent.com/transitland/transitland-atlas/main/feeds/"

# A single NTD ID: four or five digits. The Atlas sometimes records a
# comma-joined list on one operator (it reports for several NTD agencies); that is
# ambiguous for a single feed, so it is rejected rather than written as one value.
_NTD_ID = re.compile(r"^\d{4,5}$")


def normalize_url(url: str) -> str:
    """A comparable form of a feed URL: scheme-insensitive, host lowercased, no
    trailing slash. Query strings are kept, because some feeds (e.g. a 511-style
    endpoint with an operator_id parameter) distinguish operators only there."""
    u = url.strip()
    for prefix in ("https://", "http://"):
        if u.lower().startswith(prefix):
            u = u[len(prefix) :]
            break
    if u.lower().startswith("www."):
        u = u[4:]
    # Lowercase only the host (up to the first slash); paths/queries can be
    # case-sensitive on some servers.
    slash = u.find("/")
    if slash == -1:
        return u.rstrip("/").lower()
    host, rest = u[:slash], u[slash:]
    return (host.lower() + rest).rstrip("/")


def build_index(docs: list[dict[str, Any]]) -> dict[str, str]:
    """Map each feed's normalized static URL to its operator's NTD ID.

    Built across all documents at once, because an operator's `associated_feeds`
    can reference a feed defined in a different file. A URL linked to more than one
    distinct NTD ID is dropped (a shared regional feed should not stamp one
    agency's ID onto another), so the returned index is unambiguous.
    """
    # Onestop feed id -> normalized static URL, across every document.
    feed_url: dict[str, str] = {}
    for doc in docs:
        for feed in doc.get("feeds", []) or []:
            osid = feed.get("id")
            static = (feed.get("urls") or {}).get("static_current")
            if osid and static:
                feed_url[osid] = normalize_url(static)

    # Normalized URL -> set of NTD IDs seen for it.
    url_ntds: dict[str, set[str]] = {}
    for doc in docs:
        for op in doc.get("operators", []) or []:
            ntd = str((op.get("tags") or {}).get("us_ntd_id") or "").strip()
            # Reject blanks and multi-value tags (a comma-joined list of IDs is
            # ambiguous for a single feed); only a clean single NTD ID is usable.
            if not _NTD_ID.match(ntd):
                continue
            for assoc in op.get("associated_feeds", []) or []:
                osid = assoc.get("feed_onestop_id")
                url = feed_url.get(osid) if osid else None
                if url:
                    url_ntds.setdefault(url, set()).add(str(ntd))

    return {url: next(iter(ntds)) for url, ntds in url_ntds.items() if len(ntds) == 1}


@dataclass(frozen=True)
class Proposal:
    """A proposed NTD ID for one registry agency, matched by feed URL."""

    agency_id: str
    ntd_id: str


def match_agencies(
    agencies: list[dict[str, Any]], index: dict[str, str], *, skip_ids: set[str] | None = None
) -> list[Proposal]:
    """Propose an NTD ID for each agency whose feed URL is in the index.

    ``agencies`` is the parsed registry list (each with ``id`` and
    ``static_gtfs_url``). Agencies already carrying an ``ntd_id`` are skipped (pass
    their ids in ``skip_ids``) so a curated value is never overwritten. Sorted by
    id for a deterministic, clean diff.
    """
    skip = skip_ids or set()
    out: list[Proposal] = []
    for a in agencies:
        aid = a.get("id")
        url = a.get("static_gtfs_url")
        if not aid or not url or aid in skip:
            continue
        ntd = index.get(normalize_url(str(url)))
        if ntd:
            out.append(Proposal(str(aid), ntd))
    return sorted(out, key=lambda p: p.agency_id)


# --- Name fallback ---------------------------------------------------------
#
# The feed-URL match is exact but misses agencies whose published URL is not the
# one the Atlas lists. A second, conservative pass matches by operator name. The
# precision driver is global name uniqueness (a normalized name that maps to one
# NTD ID across the whole Atlas); a geographic guardrail then rejects a name match
# that lands implausibly far from where we know the agency runs, to catch the rare
# same-name-different-place coincidence. A wrong NTD ID is worse than none, so an
# ambiguous or geographically-impossible match is dropped, not guessed.

_GEOHASH_32 = "0123456789bcdefghjkmnpqrstuvwxyz"

# A name match more than this far from the agency's own geometry is treated as a
# coincidence and dropped. Generous, because an Atlas onestop_id geohash is coarse
# (a few characters), but tight enough to separate agencies in different regions.
MAX_NAME_MATCH_KM = 400.0

# Generic words dropped from a name before comparison, so "Foo Transit Authority"
# and "Foo Transportation District" are not forced to differ on boilerplate. Kept
# small; over-stripping would collapse distinct agencies together.
_NAME_STOPWORDS = frozenset(
    {
        "transit",
        "transportation",
        "authority",
        "district",
        "agency",
        "system",
        "systems",
        "regional",
        "metropolitan",
        "area",
        "public",
        "the",
        "of",
        "county",
        "city",
        "inc",
    }
)


def normalize_name(name: str) -> str:
    """A comparable form of an operator name: lowercased, parentheticals and
    punctuation removed, generic transit boilerplate words dropped, remaining
    tokens sorted and joined. Returns "" when nothing distinctive is left, so a
    name that is only boilerplate never matches."""
    s = name.lower()
    out_chars = []
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out_chars.append(ch if ch.isalnum() else " ")
    tokens = [t for t in "".join(out_chars).split() if t and t not in _NAME_STOPWORDS]
    return " ".join(sorted(tokens))


def _geohash_decode(geohash: str) -> tuple[float, float] | None:
    """Decode a geohash to the centroid (lat, lon) of its cell, or None if empty
    or malformed. Standard base-32 geohash; only as precise as the hash is long."""
    if not geohash:
        return None
    lat_lo, lat_hi = -90.0, 90.0
    lon_lo, lon_hi = -180.0, 180.0
    even = True
    for ch in geohash:
        idx = _GEOHASH_32.find(ch)
        if idx < 0:
            return None
        for bit in (16, 8, 4, 2, 1):
            if even:
                mid = (lon_lo + lon_hi) / 2
                if idx & bit:
                    lon_lo = mid
                else:
                    lon_hi = mid
            else:
                mid = (lat_lo + lat_hi) / 2
                if idx & bit:
                    lat_lo = mid
                else:
                    lat_hi = mid
            even = not even
    return (lat_lo + lat_hi) / 2, (lon_lo + lon_hi) / 2


def operator_centroid(onestop_id: str) -> tuple[float, float] | None:
    """The approximate (lat, lon) of an Atlas operator from its onestop_id, whose
    second dash-segment is a geohash (``o-9q8-samtrans`` -> geohash ``9q8``)."""
    parts = onestop_id.split("-")
    if len(parts) < 2:
        return None
    return _geohash_decode(parts[1])


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt

    lat1, lon1, lat2, lon2 = map(radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def build_name_index(docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map each globally-unique normalized operator name to its NTD ID and centroid.

    Indexes both the operator name and its short name. A normalized name linked to
    more than one distinct NTD ID anywhere in the Atlas is dropped, so only names
    that identify a single reporter nationally survive. The centroid (from the
    operator onestop_id geohash) rides along for the geographic guardrail.
    """
    name_ntds: dict[str, set[str]] = {}
    name_centroid: dict[str, tuple[float, float] | None] = {}
    for doc in docs:
        for op in doc.get("operators", []) or []:
            ntd = str((op.get("tags") or {}).get("us_ntd_id") or "").strip()
            # Same guard as build_index: reject blanks, comma-joined lists (a
            # parent operating several subsidiaries), and non-numeric tags; only a
            # clean single NTD ID is usable.
            if not _NTD_ID.match(ntd):
                continue
            centroid = operator_centroid(str(op.get("onestop_id", "")))
            for raw in (op.get("name"), op.get("short_name")):
                norm = normalize_name(str(raw or ""))
                if not norm:
                    continue
                name_ntds.setdefault(norm, set()).add(str(ntd))
                # Keep the first centroid seen for the name.
                name_centroid.setdefault(norm, centroid)
    return {
        norm: {"ntd_id": next(iter(ntds)), "centroid": name_centroid.get(norm)}
        for norm, ntds in name_ntds.items()
        if len(ntds) == 1
    }


def match_agencies_by_name(
    agencies: list[dict[str, Any]],
    name_index: dict[str, dict[str, Any]],
    *,
    skip_ids: set[str] | None = None,
    max_km: float = MAX_NAME_MATCH_KM,
) -> list[Proposal]:
    """Propose an NTD ID for each agency whose name uniquely matches the Atlas.

    ``agencies`` carry ``id``, ``name``, and optionally ``lat``/``lon`` (the
    agency's geometry). A match requires the agency's normalized name to be a
    globally-unique Atlas name. When both the agency and the matched operator have
    a location, a distance beyond ``max_km`` rejects the match as a coincidence;
    when either location is unknown, the global-uniqueness of the name carries it.
    Agencies in ``skip_ids`` (already matched or curated) are left alone.
    """
    skip = skip_ids or set()
    out: list[Proposal] = []
    for a in agencies:
        aid = a.get("id")
        if not aid or aid in skip:
            continue
        norm = normalize_name(str(a.get("name") or ""))
        hit = name_index.get(norm)
        if not norm or not hit:
            continue
        a_lat, a_lon = a.get("lat"), a.get("lon")
        centroid = hit.get("centroid")
        if (
            centroid is not None
            and a_lat is not None
            and a_lon is not None
            and _haversine_km((float(a_lat), float(a_lon)), centroid) > max_km
        ):
            continue  # name coincided but the locations do not; drop it
        out.append(Proposal(str(aid), str(hit["ntd_id"])))
    return sorted(out, key=lambda p: p.agency_id)


def agencies_with_ntd_id(yaml_text: str) -> set[str]:
    """Ids of agencies that already declare an `ntd_id`, read structurally so an
    existing curated value is preserved. Reads the registry as the loader does."""
    import yaml

    raw = yaml.safe_load(yaml_text) or {}
    out: set[str] = set()
    for a in raw.get("agencies", []) or []:
        if isinstance(a, dict) and a.get("id") and a.get("ntd_id"):
            out.add(str(a["id"]))
    return out


def apply_to_yaml(yaml_text: str, proposals: list[Proposal]) -> tuple[str, int]:
    """Insert `ntd_id` lines into the registry text for each proposal.

    Works on the raw text rather than round-tripping through a YAML dumper, so the
    345 KB hand-maintained file keeps its formatting, comments, and order and the
    diff is one added line per agency. The `ntd_id` is inserted right after the
    agency's `- id:` line, matching the file's two-space list indentation. An
    agency that already has an `ntd_id` (per ``agencies_with_ntd_id``) is left
    untouched. Returns the new text and how many lines were inserted.
    """
    have = agencies_with_ntd_id(yaml_text)
    want = {p.agency_id: p.ntd_id for p in proposals if p.agency_id not in have}
    if not want:
        return yaml_text, 0

    lines = yaml_text.split("\n")
    out: list[str] = []
    inserted = 0
    for line in lines:
        out.append(line)
        stripped = line.strip()
        if stripped.startswith("- id:"):
            # The id value, with optional quotes, after "- id:".
            value = stripped[len("- id:") :].strip().strip("'\"")
            if value in want:
                indent = line[: len(line) - len(line.lstrip())]
                # Sibling keys sit one list-indent deeper than the "- " marker.
                key_indent = indent + "  "
                out.append(f'{key_indent}ntd_id: "{want[value]}"')
                inserted += 1
    return "\n".join(out), inserted


def fetch_atlas(fetch: Any = None) -> list[dict[str, Any]]:
    """Download and parse every Atlas DMFR feed document.

    ``fetch`` is an optional callable taking a URL and returning text (defaults to
    the pipeline's HTTP helper), so tests can inject a stub. Files that fail to
    download or parse are skipped with no effect on the rest.
    """
    if fetch is None:
        from .net import safe_get

        def fetch(url: str) -> str:
            return safe_get(url, timeout=30, retries=2).decode("utf-8")

    listing = json.loads(fetch(ATLAS_API))
    if not isinstance(listing, list):
        return []
    # The GitHub Contents API caps directory listings at 1000 items; if the Atlas
    # feeds/ directory ever nears that, we'd silently miss later files. Log a warning
    # so it gets noticed before becoming a silent miss.
    if len(listing) >= 500:
        import logging

        logging.getLogger(__name__).warning(
            "fetch_atlas: Atlas feeds/ listing has %d entries; approaching the "
            "1000-item GitHub Contents API cap — switch to the tree API if this grows.",
            len(listing),
        )
    docs: list[dict[str, Any]] = []
    for entry in listing:
        name = entry.get("name", "")
        if not name.endswith(".dmfr.json"):
            continue
        try:
            docs.append(json.loads(fetch(ATLAS_RAW + name)))
        except (ValueError, OSError):
            continue
    return docs
