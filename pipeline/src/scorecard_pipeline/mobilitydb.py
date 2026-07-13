"""Propose agencies.yaml entries from the Mobility Database catalog.

The roadmap's first Year 1 step (docs/roadmap.md): get a region's worth of
feeds into the registry without hand-editing YAML for each one. This reads the
Mobility Database catalog CSV (mobilitydatabase.org), filters to a country,
state, or list of providers, pairs each GTFS Schedule feed with any realtime
feeds that reference it, and emits agencies.yaml blocks.

A human still reviews and merges the output, so the registry stays curated.
The point is to remove the typing, not the judgement: key-gated realtime feeds
become an `rt_note` rather than a broken `rt_urls` entry, licenses are carried
through, and ids already present in the registry are skipped.

The catalog CSV is the stable public export of the Mobility Database; its
column names are used directly so the mapping is auditable against the source.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .config import Agency
from .lint import is_feed_descriptor
from .location import normalize_location
from .net import safe_get

# https://mobilitydatabase.org — the catalog is published as a single CSV.
DEFAULT_CATALOG_URL = "https://storage.googleapis.com/storage/v1/b/mdb-csv/o/sources.csv?alt=media"

# Mobility Database gtfs-rt rows carry an entity_type; map it to our rt kinds.
_RT_ENTITY_TO_KIND = {
    "tu": "trip_updates",
    "vp": "vehicle_positions",
    "sa": "service_alerts",
}

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

# Recognized US states/territories. The catalog's subdivision field is mostly
# these names; anything else falls back to unlocated rather than becoming its own
# place. Used by the directory's browse-by-place and the state backfill.
US_STATES = frozenset(
    {
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
        "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
        "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
        "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
        "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
        "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
        "Washington", "West Virginia", "Wisconsin", "Wyoming",
        "District of Columbia", "Puerto Rico", "Guam", "American Samoa",
        "U.S. Virgin Islands", "Northern Mariana Islands",
    }
)  # fmt: skip

# A few catalog rows carry a city or region instead of a state; remap the known
# ones rather than dropping them.
SUBDIVISION_FIXUPS = {
    "Chicago": "Illinois",  # Shawnee Mass Transit District (southern Illinois)
    "Lake Tahoe": "California",  # Emerald Bay Shuttle (Emerald Bay is in CA)
}


def canonical_state(subdivision: str) -> str:
    """A recognized US state/territory name for a catalog subdivision, or "" when
    the value isn't one (after applying the known-quirk fixups)."""
    fixed = SUBDIVISION_FIXUPS.get(subdivision, subdivision)
    return fixed if fixed in US_STATES else ""


@dataclass(frozen=True)
class CatalogFeed:
    """One row of the Mobility Database catalog, narrowed to fields we use."""

    mdb_id: str
    data_type: str  # "gtfs" (schedule) or "gtfs-rt"
    entity_type: str  # realtime only: tu / vp / sa
    country: str
    subdivision_code: str  # ISO 3166-2 code, when the catalog provides one
    subdivision: str  # state or province
    municipality: str
    provider: str
    name: str
    direct_download: str
    license_url: str
    authentication_type: str  # "0"/"" means no key required
    static_reference: str  # realtime -> the schedule feed's mdb_id
    hosted_url: str = ""  # urls.latest: MobilityData's hosted mirror on GCS
    status: str = ""  # active / deprecated / inactive / development
    is_official: bool | None = None


@dataclass
class ProposedAgency:
    """A candidate agencies.yaml block built from one schedule feed plus any
    realtime feeds that reference it."""

    id: str
    name: str
    static_gtfs_url: str
    mdb_id: str = ""
    country: str = ""
    subdivision_code: str = ""
    subdivision_name: str = ""
    rt_urls: dict[str, str] = field(default_factory=dict)
    rt_note: str = ""
    license_note: str = ""
    feed_status: str = "active"
    is_official: bool | None = None


def _cell(row: dict[str, str], *names: str) -> str:
    """First non-empty value among candidate column names, trimmed.

    The catalog has shuffled column names across versions (e.g. provider vs
    operator); accepting a few aliases keeps the sync resilient.
    """
    for name in names:
        value = row.get(name)
        if value and value.strip():
            return value.strip()
    return ""


def _optional_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _feed_url_key(url: str) -> str:
    """Treat HTTP/HTTPS variants of one endpoint as the same proposal."""
    from .identity import normalized_feed_url

    return normalized_feed_url(url)


def parse_catalog(csv_text: str) -> list[CatalogFeed]:
    """Parse the catalog CSV into feed records, skipping rows without a usable
    download URL or a recognised data type."""
    feeds: list[CatalogFeed] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        data_type = _cell(row, "data_type").lower()
        if data_type not in ("gtfs", "gtfs-rt", "gtfs_rt", "gtfs-realtime"):
            continue
        normalized_type = "gtfs" if data_type == "gtfs" else "gtfs-rt"
        download = _cell(row, "urls.direct_download", "urls.latest", "static_reference")
        if normalized_type == "gtfs" and not download:
            continue
        feeds.append(
            CatalogFeed(
                mdb_id=_cell(row, "mdb_source_id", "id"),
                data_type=normalized_type,
                entity_type=_cell(row, "entity_type").lower(),
                country=_cell(row, "location.country_code", "country_code").upper(),
                subdivision_code=_cell(
                    row, "location.subdivision_code", "subdivision_code"
                ).upper(),
                subdivision=_cell(row, "location.subdivision_name", "subdivision_name"),
                municipality=_cell(row, "location.municipality", "municipality"),
                provider=_cell(row, "provider", "operator", "name"),
                name=_cell(row, "name", "provider"),
                direct_download=download,
                license_url=_cell(row, "urls.license", "license_url"),
                authentication_type=_cell(row, "urls.authentication_type", "authentication_type"),
                static_reference=_cell(row, "static_reference"),
                hosted_url=_cell(row, "urls.latest"),
                status=_cell(row, "status").lower(),
                is_official=_optional_bool(_cell(row, "is_official")),
            )
        )
    return feeds


def slugify(provider: str, mdb_id: str) -> str:
    """A registry id from the provider name, falling back to the catalog id.

    Matches the registry's id rule (lowercase slug). Collisions are the
    caller's to resolve; the proposer disambiguates with the mdb id.
    """
    slug = _SLUG_STRIP.sub("-", provider.lower()).strip("-")
    if not slug or not slug[0].isalnum():
        slug = f"mdb-{mdb_id}" if mdb_id else "agency"
    return slug


def _license_note(feed: CatalogFeed) -> str:
    if feed.license_url:
        return f"License: {feed.license_url}"
    return "No stated data license in the Mobility Database; verify before publishing."


def _matches(
    feed: CatalogFeed, country: str | None, subdivision: str | None, providers: set[str] | None
) -> bool:
    if country and feed.country != country.upper():
        return False
    if subdivision and feed.subdivision.lower() != subdivision.lower():
        return False
    return not (providers and feed.provider.lower() not in providers)


def propose_agencies(  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    feeds: list[CatalogFeed],
    *,
    country: str | None = None,
    subdivision: str | None = None,
    providers: list[str] | None = None,
    existing_ids: set[str] | None = None,
) -> list[ProposedAgency]:
    """Build candidate registry entries from catalog feeds.

    Schedule feeds matching the filter become agencies; realtime feeds are
    attached to the schedule feed they reference (static_reference). Key-gated
    realtime feeds are recorded as a note, not a broken URL, so they show
    neutrally rather than scoring zero. Ids already in `existing_ids` are
    skipped so re-running the sync never re-proposes a tracked agency.
    """
    existing = existing_ids or set()
    provider_filter = {p.lower() for p in providers} if providers else None

    rt_by_reference: dict[str, list[CatalogFeed]] = {}
    for feed in feeds:
        active = not feed.status or feed.status == "active"
        if (
            feed.data_type == "gtfs-rt"
            and feed.static_reference
            and active
            and feed.is_official is not False
        ):
            rt_by_reference.setdefault(feed.static_reference, []).append(feed)

    proposals: list[ProposedAgency] = []
    used_ids = set(existing)
    proposed_sources: set[str] = set()
    proposed_urls: set[str] = set()
    for feed in feeds:
        if feed.data_type != "gtfs":
            continue
        if feed.status and feed.status != "active":
            continue
        if feed.is_official is False:
            continue
        if not _matches(feed, country, subdivision, provider_filter):
            continue
        url_key = _feed_url_key(feed.direct_download)
        # A malformed catalog URL has no safe identity key. Do not emit an
        # unusable proposal or add the empty sentinel to the dedup set, where
        # it would make later malformed rows look like the same endpoint.
        if not url_key:
            continue
        if (feed.mdb_id and feed.mdb_id in proposed_sources) or url_key in proposed_urls:
            continue
        if feed.mdb_id:
            proposed_sources.add(feed.mdb_id)
        proposed_urls.add(url_key)

        base_id = slugify(feed.provider, feed.mdb_id)
        agency_id = base_id
        if agency_id in used_ids:
            agency_id = f"{base_id}-{feed.mdb_id}" if feed.mdb_id else base_id
        if agency_id in existing or agency_id in used_ids:
            continue
        used_ids.add(agency_id)

        rt_urls: dict[str, str] = {}
        key_gated = False
        for rt in rt_by_reference.get(feed.mdb_id, []):
            kind = _RT_ENTITY_TO_KIND.get(rt.entity_type)
            if not kind:
                continue
            if rt.authentication_type and rt.authentication_type.lower() not in ("0", "none"):
                key_gated = True
                continue
            rt_urls[kind] = rt.direct_download

        rt_note = ""
        if key_gated and not rt_urls:
            rt_note = (
                "This agency publishes realtime, but the feed needs an access key "
                "we don't have yet. Nothing here counts against the grade."
            )

        # The catalog's feed name is usually the agency's brand ("Yolobus"), but
        # sometimes a feed descriptor ("Flex", "Bus", "Do not use - deprecated").
        # In that case the provider is the real agency name (lint.py).
        name = feed.provider if is_feed_descriptor(feed.name) else (feed.name or feed.provider)
        location = normalize_location(
            feed.country,
            subdivision_code=feed.subdivision_code,
            subdivision_name=feed.subdivision,
        )
        proposals.append(
            ProposedAgency(
                id=agency_id,
                name=name,
                static_gtfs_url=feed.direct_download,
                mdb_id=feed.mdb_id,
                # Preserve an unassigned or malformed catalog country so the
                # registry rejects it explicitly instead of a proposal silently
                # falling back to the legacy US default.
                country=location.country_code or feed.country.strip().upper(),
                subdivision_code=location.subdivision_code,
                # Keep catalog context even when it is not a recognized ISO
                # subdivision. An unknown name is useful to a curator; it must
                # not be promoted to a guessed code.
                subdivision_name=location.subdivision_name or feed.subdivision,
                rt_urls=rt_urls,
                rt_note=rt_note,
                license_note=_license_note(feed),
                feed_status=feed.status or "active",
                is_official=feed.is_official,
            )
        )
    return proposals


def _scalar(value: str) -> str:
    """Quote a YAML scalar only when a plain one would misparse.

    A value containing ": " (e.g. "License: https://...") or other indicator
    characters has to be quoted or YAML reads it as a nested mapping. Plain
    values pass through so the output keeps the registry's unquoted style.
    """
    risky = (
        ": " in value
        or " #" in value
        or "\n" in value
        or value != value.strip()
        or (value and value[0] in "!&*?{}[],#|>@`\"'%:-")
    )
    if not risky:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_location(proposal: ProposedAgency) -> list[str]:
    """Registry location lines, omitting the default US country."""
    fields = (
        ("country", proposal.country if proposal.country != "US" else ""),
        ("subdivision_code", proposal.subdivision_code),
        ("subdivision_name", proposal.subdivision_name),
    )
    return [f"    {key}: {_scalar(value)}" for key, value in fields if value]


def render_yaml(proposals: list[ProposedAgency]) -> str:
    """Render proposals as agencies.yaml blocks, ready to review and merge.

    Hand-rolled rather than yaml.dump so the output matches the registry's
    existing hand-written style (block order, comment-free, two-space indent)
    and stays diff-friendly when pasted into agencies.yaml.
    """
    lines: list[str] = []
    for p in proposals:
        lines.append(f"  - id: {p.id}")
        lines.append(f"    name: {_scalar(p.name)}")
        lines.append(f"    static_gtfs_url: {_scalar(p.static_gtfs_url)}")
        lines.extend(_render_location(p))
        if p.mdb_id:
            lines.append(f"    mdb_id: {_scalar(p.mdb_id)}")
        lines.append(f"    feed_status: {_scalar(p.feed_status)}")
        if p.is_official is not None:
            lines.append(f"    is_official: {'true' if p.is_official else 'false'}")
        if p.rt_urls:
            lines.append("    rt_urls:")
            for kind in ("trip_updates", "vehicle_positions", "service_alerts"):
                if kind in p.rt_urls:
                    lines.append(f"      {kind}: {_scalar(p.rt_urls[kind])}")
        if p.rt_note:
            lines.append(f"    rt_note: {_scalar(p.rt_note)}")
        if p.license_note:
            lines.append(f"    license_note: {_scalar(p.license_note)}")
        lines.append("")
    return "\n".join(lines)


def fetch_catalog(url: str = DEFAULT_CATALOG_URL) -> str:
    """Download the catalog CSV. Split out so tests use a local fixture.

    Routed through safe_get so an operator-supplied --catalog URL gets the same
    SSRF and size guards as every other fetch, rather than a raw urlopen.
    """
    data = safe_get(url, timeout=60, max_bytes=128 * 1024 * 1024)
    return data.decode("utf-8", errors="replace")


_catalog_cache: list[CatalogFeed] | None = None


def load_catalog(*, force: bool = False) -> list[CatalogFeed]:
    """The parsed Mobility Database catalog, fetched once and memoised.

    Used by the fetch fallback, which only consults it when an agency's origin
    feed is unreachable, so the catalog download happens for the blocked
    minority of feeds rather than on every run.
    """
    global _catalog_cache
    if _catalog_cache is None or force:
        _catalog_cache = parse_catalog(fetch_catalog())
    return _catalog_cache


def hosted_mirror_url(
    agency_id: str, agency_name: str, current_url: str, mdb_id: str = ""
) -> str | None:
    """MobilityData's hosted mirror (``urls.latest``) for an agency, if any.

    The mirror lives on Google Cloud Storage, reachable even when the agency's
    own server firewalls datacenter IPs or sits behind a bot filter. Because
    these bytes are scored and published as the agency's feed, the match is
    deliberately stricter than discovery: only a pinned exact ``mdb_id`` or an
    exact normalized current download URL may select a mirror. Names are never
    an identity boundary.
    """
    try:
        feeds = load_catalog()
    except Exception:
        return None
    schedule = [feed for feed in feeds if feed.data_type == "gtfs" and feed.hosted_url]
    if mdb_id:
        for feed in schedule:
            if feed.mdb_id == mdb_id:
                return feed.hosted_url

    current_key = _feed_url_key(current_url)
    if current_key:
        for feed in schedule:
            if _feed_url_key(feed.direct_download) == current_key:
                return feed.hosted_url
    return None


# --- feed discovery: is a tracked feed's URL still the canonical one? ----------

# Words that say nothing about *which* agency a feed belongs to. Dropped before
# token-matching a registry name against a catalog provider, so "City of Davis
# Transit" and "Davis Community Transit" still share the distinctive "davis".
_NAME_STOPWORDS = frozenset(
    {
        "transit",
        "transportation",
        "authority",
        "agency",
        "district",
        "city",
        "county",
        "area",
        "regional",
        "rural",
        "public",
        "system",
        "systems",
        "service",
        "services",
        "bus",
        "buses",
        "lines",
        "line",
        "shuttle",
        "express",
        "commission",
        "department",
        "dept",
        "municipal",
        "metro",
        "metropolitan",
        "joint",
        "powers",
        "inc",
    }
)


def _name_tokens(text: str) -> frozenset[str]:
    """Distinctive lowercase word tokens from an agency or provider name."""
    words = re.split(r"[^a-z0-9]+", text.lower())
    return frozenset(w for w in words if w and w not in _NAME_STOPWORDS and len(w) > 2)


def _url_slug(url: str) -> str:
    """A comparable key for a GTFS download URL: host plus path, lowercased,
    with the scheme, querystring, www., and trailing .zip stripped.

    Many small CA agencies are hosted on shared services (Trillium, S3) where
    the agency identity lives in the path (``/gtfs/alhambra-ca-us/...``), so the
    path matters as much as the host for deciding whether two URLs are the same
    feed.
    """
    u = re.sub(r"^https?://", "", url.strip().lower())
    u = u.split("?", 1)[0].split("#", 1)[0]
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/").removesuffix(".zip")


@dataclass
class FeedMatch:
    """How a tracked agency's feed URL relates to the Mobility Database."""

    agency_id: str
    agency_name: str
    current_url: str
    # "tracked"     the exact current URL is still in the catalog (canonical)
    # "replaced"    the catalog has this agency on a different download URL
    # "missing"     no catalog feed matches this agency at all
    status: str
    candidates: list[CatalogFeed] = field(default_factory=list)


def _same_feed(current_slug: str, feed: CatalogFeed) -> bool:
    """Whether a catalog feed is the same download as the current URL."""
    return _url_slug(feed.direct_download) == current_slug


def find_replacements(
    feeds: list[CatalogFeed],
    registry: list[tuple[str, str, str]],
    mdb_ids: dict[str, str] | None = None,
) -> list[FeedMatch]:
    """For each tracked agency, decide whether its feed URL is still canonical.

    `registry` is (agency_id, agency_name, current_static_url) tuples. When an
    agency has a pinned Mobility Database id in `mdb_ids`, it is matched against
    that exact catalog row, which is unambiguous and survives a name change.
    Otherwise the agency is matched two looser ways: by exact download URL (same
    host+path), then by distinctive name tokens. The result classifies the
    agency as ``tracked`` (URL still in the catalog), ``replaced`` (catalog
    lists a different URL for what looks like the same agency), or ``missing``
    (no catalog match), and carries the candidate catalog feeds so a human can
    confirm the canonical endpoint before editing agencies.yaml. This proposes;
    it never rewrites the registry.
    """
    pinned = mdb_ids or {}
    schedule = [f for f in feeds if f.data_type == "gtfs" and f.direct_download]
    by_slug: dict[str, list[CatalogFeed]] = {}
    by_mdb: dict[str, CatalogFeed] = {}
    for f in schedule:
        by_slug.setdefault(_url_slug(f.direct_download), []).append(f)
        if f.mdb_id:
            by_mdb[f.mdb_id] = f

    matches: list[FeedMatch] = []
    for agency_id, agency_name, current_url in registry:
        current_slug = _url_slug(current_url)

        # Pinned id wins: match the exact catalog row, name changes and all.
        pinned_feed = by_mdb.get(pinned.get(agency_id, ""))
        if pinned_feed is not None:
            status = "tracked" if _same_feed(current_slug, pinned_feed) else "replaced"
            matches.append(FeedMatch(agency_id, agency_name, current_url, status, [pinned_feed]))
            continue

        if current_slug in by_slug:
            matches.append(
                FeedMatch(
                    agency_id, agency_name, current_url, "tracked", list(by_slug[current_slug])
                )
            )
            continue

        wanted = _name_tokens(agency_name) | _name_tokens(agency_id.replace("-", " "))
        scored: list[tuple[int, CatalogFeed]] = []
        for f in schedule:
            shared = wanted & (_name_tokens(f.provider) | _name_tokens(f.name))
            if shared:
                scored.append((len(shared), f))
        scored.sort(key=lambda t: t[0], reverse=True)
        candidates = [f for _, f in scored[:5]]
        # A name candidate is only a *replacement* if its URL differs from the
        # one we already have; an identical URL just means the catalog agrees.
        replaced = any(not _same_feed(current_slug, f) for f in candidates)
        status = "replaced" if replaced else "missing"
        matches.append(FeedMatch(agency_id, agency_name, current_url, status, candidates))
    return matches


def replacement_url(match: FeedMatch) -> str | None:
    """The catalog download URL to move a ``replaced`` agency onto, if any.

    The first candidate whose URL actually differs from the current one. Returns
    None for any other status, so callers can treat "has a replacement" as a
    single truthy check.
    """
    if match.status != "replaced":
        return None
    current_slug = _url_slug(match.current_url)
    for f in match.candidates:
        if _url_slug(f.direct_download) != current_slug:
            return f.direct_download
    return None


def apply_replacements(yaml_text: str, matches: list[FeedMatch]) -> tuple[str, list[str]]:
    """Rewrite the static_gtfs_url of each ``replaced`` agency in agencies.yaml.

    A targeted line replacement, not a YAML round-trip, so the registry's
    comments and hand-written formatting survive untouched. Each agency's
    ``static_gtfs_url:`` is matched within its own ``- id:`` block and only the
    first occurrence is changed. Returns the new text and the ids that changed,
    so a CI job can decide whether there is anything to open a pull request for.
    """
    new_urls = {m.agency_id: url for m in matches if (url := replacement_url(m)) is not None}
    if not new_urls:
        return yaml_text, []

    out: list[str] = []
    changed: list[str] = []
    current_id: str | None = None
    for line in yaml_text.splitlines():
        id_match = re.match(r"\s*-\s*id:\s*(\S+)", line)
        if id_match:
            current_id = id_match.group(1)
        url_match = re.match(r"(\s*)static_gtfs_url:\s*\S", line)
        if url_match and current_id in new_urls:
            out.append(f"{url_match.group(1)}static_gtfs_url: {new_urls.pop(current_id)}")
            changed.append(current_id)
            continue
        out.append(line)
    trailing = "\n" if yaml_text.endswith("\n") else ""
    return "\n".join(out) + trailing, changed


def resolve_states(agencies: Iterable[Agency], catalog: list[CatalogFeed]) -> dict[str, str]:
    """State for each agency that lacks one but pins an mdb_id, from the catalog's
    subdivision. Only newly resolved agencies are returned: a curator's state is
    left alone, and an mdb_id absent from the catalog or a non-state subdivision
    (a stray city) is skipped rather than guessed."""
    by_mdb = {f.mdb_id: f.subdivision for f in catalog if f.mdb_id and f.subdivision}
    resolved: dict[str, str] = {}
    for agency in agencies:
        if agency.state or not agency.mdb_id:
            continue
        state = canonical_state(by_mdb.get(agency.mdb_id, ""))
        if state:
            resolved[agency.id] = state
    return resolved


def apply_state_backfill(yaml_text: str, resolved: dict[str, str]) -> tuple[str, list[str]]:
    """Insert a ``state:`` line into each resolved agency's block in agencies.yaml.

    Targeted line insertion (not a YAML round-trip) so comments and formatting
    survive, mirroring apply_replacements. The line is added right after the
    agency's ``- id:`` line, indented as a sibling of name. Returns the new text
    and the ids changed."""
    if not resolved:
        return yaml_text, []
    out: list[str] = []
    changed: list[str] = []
    for line in yaml_text.splitlines():
        out.append(line)
        id_match = re.match(r"(\s*)-\s*id:\s*(\S+)", line)
        if id_match and (state := resolved.get(id_match.group(2))):
            out.append(f"{id_match.group(1)}  state: {state}")
            changed.append(id_match.group(2))
    trailing = "\n" if yaml_text.endswith("\n") else ""
    return "\n".join(out) + trailing, changed


def render_replacements_md(matches: list[FeedMatch], *, today: str) -> str:
    """A reviewable Markdown report of how tracked feed URLs relate to the catalog.

    ``replaced`` and ``missing`` rows come first, worst first, since they may
    need a registry edit. A closing count records the ``tracked`` feeds: a feed
    that is still the catalog's listed URL needs no link change, even if the data
    behind it has gone stale. This is the key result for the expired cohort, so
    it is stated, not left as an empty report.
    """
    replaced = [m for m in matches if m.status == "replaced"]
    missing = [m for m in matches if m.status == "missing"]
    tracked = [m for m in matches if m.status == "tracked"]
    out: list[str] = [
        "# Feed-discovery check against the Mobility Database",
        "",
        f"Run {today}. Source: mobilitydatabase.org catalog CSV.",
        "",
        "This checks whether the feed URL each agency is tracked on still appears "
        "in the Mobility Database, and where it doesn't, proposes the catalog feed "
        "that looks like the same agency. Candidates are suggestions to verify by "
        "hand, not automatic edits.",
        "",
        f"- **{len(replaced)}** agencies look **replaced**: the catalog lists a "
        "different download URL for the same agency.",
        f"- **{len(missing)}** agencies have **no catalog match** on name or URL.",
        f"- **{len(tracked)}** agencies are still on their **listed URL**: the link is "
        "canonical, so any staleness is at the source, not a wrong URL here.",
        "",
    ]
    if replaced:
        out += ["## Likely replaced — verify and update agencies.yaml", ""]
        for m in replaced:
            out.append(f"### {m.agency_name} (`{m.agency_id}`)")
            out.append(f"- Tracked URL (not in catalog): {m.current_url}")
            for f in m.candidates:
                if _url_slug(f.direct_download) == _url_slug(m.current_url):
                    continue
                lic = f" — license {f.license_url}" if f.license_url else ""
                out.append(f"- Candidate (mdb {f.mdb_id}, {f.provider}): {f.direct_download}{lic}")
            out.append("")
    if missing:
        out += ["## No catalog match — confirm the agency still publishes GTFS", ""]
        for m in missing:
            out.append(f"- {m.agency_name} (`{m.agency_id}`): {m.current_url}")
        out.append("")
    if tracked:
        out += [
            "## Still on the listed URL — staleness is at the source",
            "",
            "The Mobility Database lists the same download URL we already track, so "
            "there is no newer canonical feed to switch to. A feed here that is also "
            "expired means the agency or its vendor stopped refreshing the export, "
            "not that the link moved.",
            "",
        ]
        for m in sorted(tracked, key=lambda x: x.agency_name.lower()):
            out.append(f"- {m.agency_name} (`{m.agency_id}`): {m.current_url}")
        out.append("")
    return "\n".join(out)
