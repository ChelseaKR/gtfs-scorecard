"""Propose agency-registry entries from the Mobility Database catalog.

The roadmap's first Year 1 step (docs/roadmap.md): get a region's worth of
feeds into the registry without hand-editing YAML for each one. This reads the
Mobility Database catalog CSV (mobilitydatabase.org), filters to a country,
state, or list of providers, pairs each GTFS Schedule feed with any realtime
feeds that reference it, and emits reviewable registry blocks.

A human still reviews and merges the output, so the registry stays curated.
The point is to remove the typing, not the judgement: key-gated realtime feeds
become an `rt_note` rather than a broken `rt_urls` entry, key-gated Schedule
feeds are withheld, licenses are carried through, and feeds already present in
the registry are skipped by stable catalog id or normalized URL.

The catalog CSVs are public exports of the Mobility Database; their column
names are used directly so the mapping is auditable against the source. New
registry proposals use the V2 export. Mirror fallback, moved-feed discovery,
and state backfill retain the legacy export until their redirect semantics are
migrated separately.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .config import Agency
from .identity import normalized_mdb_id
from .lint import is_feed_descriptor
from .location import normalize_location
from .net import safe_get

# https://mobilitydatabase.org — V2 is the current proposal corpus. The legacy
# export remains the default for existing consumers that depend on its mirror
# and redirect behavior.
MOBILITY_DATABASE_FEEDS_V2_URL = "https://files.mobilitydatabase.org/feeds_v2.csv"
LEGACY_MOBILITY_DATABASE_CATALOG_URL = (
    "https://storage.googleapis.com/storage/v1/b/mdb-csv/o/sources.csv?alt=media"
)
DEFAULT_PROPOSAL_CATALOG_URL = MOBILITY_DATABASE_FEEDS_V2_URL
DEFAULT_CATALOG_URL = LEGACY_MOBILITY_DATABASE_CATALOG_URL

# Mobility Database gtfs-rt rows carry an entity_type; map it to our rt kinds.
_RT_ENTITY_TO_KIND = {
    "tu": "trip_updates",
    "vp": "vehicle_positions",
    "sa": "service_alerts",
}
_RT_KIND_ORDER = ("trip_updates", "vehicle_positions", "service_alerts")
_RT_KIND_LABEL = {
    "trip_updates": "Trip Updates",
    "vehicle_positions": "Vehicle Positions",
    "service_alerts": "Service Alerts",
}

_OPEN_AUTHENTICATION_TYPES = frozenset({"", "0", "none"})

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

_V2_PROPOSAL_REQUIRED_COLUMNS = frozenset(
    {
        "id",
        "data_type",
        "entity_type",
        "location.country_code",
        "provider",
        "is_official",
        "static_reference",
        "urls.direct_download",
        "urls.authentication_type",
        "status",
    }
)

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
    """A candidate registry block built from one schedule feed plus any
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


def _normalized_data_type(row: dict[str, str]) -> str:
    data_type = _cell(row, "data_type").lower()
    if data_type == "gtfs":
        return "gtfs"
    if data_type in ("gtfs-rt", "gtfs_rt", "gtfs-realtime"):
        return "gtfs-rt"
    return ""


def _catalog_download(row: dict[str, str]) -> str:
    """Usable download field across the V2 and legacy catalog schemas."""
    direct = _cell(row, "urls.direct_download", "urls.direct_download_url")
    if direct:
        return direct
    # V2 separates the provider endpoint from MobilityData's hosted latest
    # archive. The latter is useful only as a reviewed runtime mirror and must
    # not become the canonical URL of a new proposal.
    if "id" in row and "mdb_source_id" not in row:
        return ""
    return _cell(
        row,
        "urls.latest",
        # Retained for compatibility with older hand-trimmed catalog inputs.
        "static_reference",
    )


def _pipe_values(value: str) -> tuple[str, ...]:
    """Trim a V2 pipe-delimited array while preserving source order."""
    return tuple(dict.fromkeys(part.strip() for part in value.split("|") if part.strip()))


def _feed_url_key(url: str) -> str:
    """Treat HTTP/HTTPS variants of one endpoint as the same proposal."""
    from .identity import normalized_feed_url

    return normalized_feed_url(url)


def _requires_authentication(authentication_type: str) -> bool:
    """Whether a catalog feed requires credentials before it can be fetched."""
    return authentication_type.strip().lower() not in _OPEN_AUTHENTICATION_TYPES


def _catalog_feed(row: dict[str, str]) -> CatalogFeed | None:
    """Map one V2 or legacy CSV row without applying proposal eligibility."""
    normalized_type = _normalized_data_type(row)
    if not normalized_type:
        return None
    return CatalogFeed(
        mdb_id=_cell(row, "mdb_source_id", "id"),
        data_type=normalized_type,
        entity_type="|".join(_pipe_values(_cell(row, "entity_type").lower())),
        country=_cell(row, "location.country_code", "country_code").upper(),
        subdivision_code=_cell(row, "location.subdivision_code", "subdivision_code").upper(),
        subdivision=_cell(row, "location.subdivision_name", "subdivision_name"),
        municipality=_cell(row, "location.municipality", "municipality"),
        provider=_cell(row, "provider", "operator", "name"),
        # Keep the explicit-name signal for duplicate preference. Proposal
        # rendering still falls back to provider when this is empty.
        name=_cell(row, "name"),
        direct_download=_catalog_download(row),
        license_url=_cell(row, "urls.license", "license_url"),
        authentication_type=_cell(row, "urls.authentication_type", "authentication_type"),
        static_reference="|".join(_pipe_values(_cell(row, "static_reference"))),
        hosted_url=_cell(row, "urls.latest"),
        status=_cell(row, "status").lower(),
        is_official=_optional_bool(_cell(row, "is_official")),
    )


def _is_active(feed: CatalogFeed) -> bool:
    """Catalog convention: an omitted status means active."""
    return not feed.status or feed.status == "active"


def _is_proposal_eligible_schedule(feed: CatalogFeed) -> bool:
    return (
        feed.data_type == "gtfs"
        and _is_active(feed)
        and feed.is_official is not False
        and not _requires_authentication(feed.authentication_type)
        and bool(_feed_url_key(feed.direct_download))
    )


def proposal_catalog_schema(csv_text: str) -> str:
    """Validate the minimum safe proposal schema and name the catalog form.

    Proposal eligibility treats omitted status, authentication, and official
    flags permissively for old hand-trimmed legacy inputs. The V2 default must
    therefore prove those columns are present before a missing or non-CSV
    response can silently become an empty, apparently successful intake run.
    """
    reader = csv.reader(io.StringIO(csv_text))
    try:
        columns = next(reader)
    except (csv.Error, StopIteration) as exc:
        raise ValueError("catalog CSV has no readable header") from exc
    fields = {column.strip() for column in columns if column.strip()}
    if "id" in fields and "mdb_source_id" not in fields:
        missing = sorted(_V2_PROPOSAL_REQUIRED_COLUMNS - fields)
        if missing:
            raise ValueError(
                "Mobility Database V2 catalog is missing required column(s): " + ", ".join(missing)
            )
        return "mobilitydatabase-feeds-v2"
    if "mdb_source_id" in fields:
        missing = sorted({"mdb_source_id", "data_type"} - fields)
        has_download = bool(
            fields
            & {
                "urls.direct_download",
                "urls.direct_download_url",
                "urls.latest",
                "static_reference",
            }
        )
        if missing or not has_download:
            details = missing + ([] if has_download else ["a supported download URL column"])
            raise ValueError(
                "legacy Mobility Database catalog is missing required column(s): "
                + ", ".join(details)
            )
        return "mobilitydatabase-legacy"
    raise ValueError(
        "unrecognized proposal catalog header: expected Mobility Database V2 "
        "'id' or legacy 'mdb_source_id'"
    )


def parse_catalog(csv_text: str) -> list[CatalogFeed]:
    """Parse the catalog CSV into feed records, skipping rows without a usable
    download URL or a recognised data type."""
    feeds: list[CatalogFeed] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        feed = _catalog_feed(row)
        if feed is None:
            continue
        if not feed.direct_download:
            continue
        feeds.append(feed)
    return feeds


def catalog_source_counts(csv_text: str) -> dict[str, int]:
    """Source-envelope counts for a reviewable proposal run.

    ``proposal_eligible_schedule_records`` is intentionally pre-user-filter
    and pre-deduplication. It records the source denominator, not permission to
    publish any individual feed.
    """
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    feeds = [feed for row in rows if (feed := _catalog_feed(row)) is not None]
    schedules = [feed for feed in feeds if feed.data_type == "gtfs"]
    realtime = [feed for feed in feeds if feed.data_type == "gtfs-rt"]
    active_schedules = [feed for feed in schedules if _is_active(feed)]
    active_keyless = [
        feed for feed in active_schedules if not _requires_authentication(feed.authentication_type)
    ]
    return {
        "total_records": len(rows),
        "schedule_records": len(schedules),
        "realtime_records": len(realtime),
        "active_schedule_records": len(active_schedules),
        "active_keyless_schedule_records": len(active_keyless),
        "proposal_eligible_schedule_records": sum(
            _is_proposal_eligible_schedule(feed) for feed in schedules
        ),
    }


def _catalog_id_slug(mdb_id: str, *, fallback_material: str = "") -> str:
    """A lowercase registry-safe catalog-id suffix, with a stable fallback."""
    slug = _SLUG_STRIP.sub("-", mdb_id.casefold()).strip("-")
    if slug:
        return slug
    material = mdb_id or fallback_material
    if material:
        digest = hashlib.sha256(material.encode()).hexdigest()[:12]
        return f"catalog-{digest}"
    return "agency"


def slugify(provider: str, mdb_id: str) -> str:
    """A registry id from the provider name, falling back to the catalog id.

    Matches the registry's id rule (lowercase slug). Collisions are the
    caller's to resolve; the proposer disambiguates with the mdb id.
    """
    slug = _SLUG_STRIP.sub("-", provider.lower()).strip("-")
    if not slug or not slug[0].isalnum():
        catalog_slug = _catalog_id_slug(mdb_id, fallback_material=provider)
        slug = catalog_slug if catalog_slug.startswith("mdb-") else f"mdb-{catalog_slug}"
    return slug


def _license_note(feed: CatalogFeed) -> str:
    if feed.license_url:
        return f"License: {feed.license_url}"
    return "No stated data license in the source catalog; verify before publishing."


def _matches(
    feed: CatalogFeed, country: str | None, subdivision: str | None, providers: set[str] | None
) -> bool:
    if country and feed.country != country.upper():
        return False
    if subdivision and feed.subdivision.lower() != subdivision.lower():
        return False
    return not (providers and feed.provider.lower() not in providers)


def _schedule_metadata_richness(
    feed: CatalogFeed,
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Preference for duplicate schedule rows that share one endpoint.

    The final string fields make exact ties deterministic without changing the
    public identity: the selected proposal still carries the raw catalog id.
    """
    location_fields = sum(
        bool(value) for value in (feed.country, feed.subdivision_code, feed.subdivision)
    )
    return (
        (
            int(feed.is_official is True),
            int(bool(feed.license_url)),
            location_fields,
            int(bool(feed.municipality)),
            int(bool(feed.hosted_url)),
            int(bool(feed.name)),
            int(bool(feed.provider)),
            len(feed.name),
            len(feed.provider),
        ),
        (
            feed.name.casefold(),
            feed.provider.casefold(),
            feed.country.casefold(),
            feed.subdivision_code.casefold(),
            feed.subdivision.casefold(),
            feed.municipality.casefold(),
            feed.license_url,
            feed.hosted_url,
            normalized_mdb_id(feed.mdb_id),
            feed.mdb_id,
            feed.direct_download,
        ),
    )


def _preferred_schedule_url(feeds: list[CatalogFeed]) -> str:
    """Choose a stable HTTPS spelling without discarding richer metadata.

    Duplicate rows in one normalized endpoint group can differ in URL spelling.
    Metadata still comes from the richest row, while the rendered canonical
    endpoint uses HTTPS whenever the catalog supplies it.
    """
    urls = sorted({feed.direct_download for feed in feeds})
    secure = [url for url in urls if url.casefold().startswith("https://")]
    return (secure or urls)[0]


def _realtime_urls_by_access(
    feeds: Iterable[CatalogFeed],
) -> tuple[dict[str, set[str]], dict[str, set[str]], bool]:
    """Distinct URLs per kind/access class, plus gated rows of unknown kind."""
    open_urls: dict[str, set[str]] = {kind: set() for kind in _RT_KIND_ORDER}
    gated_urls: dict[str, set[str]] = {kind: set() for kind in _RT_KIND_ORDER}
    has_unmapped_gated_feed = False
    for feed in feeds:
        gated = _requires_authentication(feed.authentication_type)
        mapped = False
        for entity_type in _pipe_values(feed.entity_type):
            kind = _RT_ENTITY_TO_KIND.get(entity_type)
            if not kind:
                continue
            mapped = True
            (gated_urls if gated else open_urls)[kind].add(feed.direct_download)
        if gated and not mapped:
            has_unmapped_gated_feed = True
    return open_urls, gated_urls, has_unmapped_gated_feed


def _select_realtime(feeds: Iterable[CatalogFeed]) -> tuple[dict[str, str], str]:
    """Attach only one access-consistent URL per realtime kind.

    Exact duplicate catalog rows collapse into sets. Distinct keyless URLs or
    mixed keyless/key-gated evidence are not safe to resolve mechanically, so
    that kind stays unattached and the proposal explains why.
    """
    open_urls, gated_urls, has_unmapped_gated_feed = _realtime_urls_by_access(feeds)

    selected: dict[str, str] = {}
    notes: list[str] = []
    gated_only: list[str] = []
    for kind in _RT_KIND_ORDER:
        keyless = open_urls[kind]
        gated = gated_urls[kind]
        label = _RT_KIND_LABEL[kind]
        if keyless and gated:
            notes.append(
                f"The source catalog lists both keyless and access-key {label} "
                f"references. No {label} endpoint was attached because the access "
                "requirements conflict."
            )
        elif len(keyless) > 1:
            notes.append(
                f"The source catalog lists multiple keyless {label} endpoints. "
                f"No {label} endpoint was attached because the canonical URL is ambiguous."
            )
        elif len(keyless) == 1:
            selected[kind] = next(iter(keyless))
        elif gated:
            gated_only.append(label)

    if gated_only:
        labels = ", ".join(gated_only)
        notes.append(
            f"This agency publishes {labels}, but those feeds need an access key we don't have yet."
        )
    if has_unmapped_gated_feed:
        notes.append(
            "The source catalog also lists a realtime feed with an unrecognized kind "
            "that needs an access key, so it was not attached."
        )
    if notes:
        notes.append("Nothing here counts against the grade.")
    return selected, " ".join(notes)


def propose_agencies(  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    feeds: list[CatalogFeed],
    *,
    country: str | None = None,
    subdivision: str | None = None,
    providers: list[str] | None = None,
    existing_ids: set[str] | None = None,
    existing_mdb_ids: set[str] | None = None,
    existing_feed_urls: set[str] | None = None,
) -> list[ProposedAgency]:
    """Build candidate registry entries from catalog feeds.

    Schedule feeds matching the filter become agencies; realtime feeds are
    attached to the schedule feed they reference (static_reference). Key-gated
    realtime feeds are recorded as a note, not a broken URL, so they show
    neutrally rather than scoring zero. Key-gated Schedule feeds cannot produce
    a registry-ready entry and are omitted. Existing agency ids, catalog ids,
    and normalized feed URLs are skipped so a rerun never re-proposes a tracked
    feed even when its display name or URL spelling differs.
    """
    existing = existing_ids or set()
    tracked_mdb_ids = {
        normalized_mdb_id(mdb_id) for mdb_id in (existing_mdb_ids or set()) if mdb_id
    }
    tracked_feed_urls = {
        key for url in (existing_feed_urls or set()) if (key := _feed_url_key(url))
    }
    provider_filter = {p.lower() for p in providers} if providers else None

    rt_by_reference: dict[str, list[CatalogFeed]] = {}
    for feed in feeds:
        if (
            feed.data_type == "gtfs-rt"
            and feed.static_reference
            and _is_active(feed)
            and feed.is_official is not False
        ):
            for reference in _pipe_values(feed.static_reference):
                rt_by_reference.setdefault(normalized_mdb_id(reference), []).append(feed)

    # Filter first, then group duplicate catalog records by endpoint. Selecting
    # the richest row from the complete group makes the result independent of
    # source order while retaining the raw id of the selected V2 row.
    schedule_groups: dict[str, list[CatalogFeed]] = {}
    for feed in feeds:
        if not _is_proposal_eligible_schedule(feed):
            continue
        if not _matches(feed, country, subdivision, provider_filter):
            continue
        url_key = _feed_url_key(feed.direct_download)
        schedule_groups.setdefault(url_key, []).append(feed)

    proposals: list[ProposedAgency] = []
    used_ids = set(existing)
    proposed_sources: set[str] = set()
    proposed_urls: set[str] = set()
    for url_key, duplicates in schedule_groups.items():
        duplicate_ids = {
            normalized_mdb_id(candidate.mdb_id) for candidate in duplicates if candidate.mdb_id
        }
        if duplicate_ids & tracked_mdb_ids or url_key in tracked_feed_urls:
            continue
        feed = max(duplicates, key=_schedule_metadata_richness)
        proposal_url = _preferred_schedule_url(duplicates)
        source_key = normalized_mdb_id(feed.mdb_id)
        if (source_key and source_key in proposed_sources) or url_key in proposed_urls:
            continue
        if source_key:
            proposed_sources.add(source_key)
        proposed_urls.add(url_key)

        base_id = slugify(feed.provider, feed.mdb_id)
        agency_id = base_id
        if agency_id in used_ids:
            suffix = _catalog_id_slug(feed.mdb_id, fallback_material=feed.direct_download)
            agency_id = f"{base_id}-{suffix}"
        if agency_id in existing or agency_id in used_ids:
            continue
        used_ids.add(agency_id)

        # Any duplicate row can be the id referenced by a realtime source, so
        # attach RT from the complete endpoint group to the selected proposal.
        realtime_feeds: list[CatalogFeed] = []
        for duplicate_id in sorted(duplicate_ids):
            realtime_feeds.extend(rt_by_reference.get(duplicate_id, []))
        rt_urls, rt_note = _select_realtime(realtime_feeds)

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
                static_gtfs_url=proposal_url,
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
    """Render proposals as registry blocks, ready to review and merge.

    Hand-rolled rather than yaml.dump so the output matches the registry's
    existing hand-written style (block order, comment-free, two-space indent)
    and stays diff-friendly when pasted into the intake shard.
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


def fetch_catalog_bytes(url: str = DEFAULT_CATALOG_URL) -> bytes:
    """Download the exact catalog bytes for parsing and provenance hashing.

    Routed through safe_get so an operator-supplied --catalog URL gets the same
    SSRF and size guards as every other fetch, rather than a raw urlopen.
    """
    return safe_get(url, timeout=60, max_bytes=128 * 1024 * 1024)


def fetch_catalog(url: str = DEFAULT_CATALOG_URL) -> str:
    """Download and decode the catalog CSV. Tests use a local fixture."""
    return fetch_catalog_bytes(url).decode("utf-8", errors="replace")


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
        mdb_key = normalized_mdb_id(mdb_id)
        for feed in schedule:
            if normalized_mdb_id(feed.mdb_id) == mdb_key:
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
    confirm the canonical endpoint before editing the registry. This proposes;
    it never rewrites the registry.
    """
    pinned = mdb_ids or {}
    schedule = [f for f in feeds if f.data_type == "gtfs" and f.direct_download]
    by_slug: dict[str, list[CatalogFeed]] = {}
    by_mdb: dict[str, CatalogFeed] = {}
    for f in schedule:
        by_slug.setdefault(_url_slug(f.direct_download), []).append(f)
        if f.mdb_id:
            by_mdb[normalized_mdb_id(f.mdb_id)] = f

    matches: list[FeedMatch] = []
    for agency_id, agency_name, current_url in registry:
        current_slug = _url_slug(current_url)

        # Pinned id wins: match the exact catalog row, name changes and all.
        pinned_feed = by_mdb.get(normalized_mdb_id(pinned.get(agency_id, "")))
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
    """Rewrite the static URL of each ``replaced`` agency in one registry shard.

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
    by_mdb = {
        normalized_mdb_id(f.mdb_id): f.subdivision for f in catalog if f.mdb_id and f.subdivision
    }
    resolved: dict[str, str] = {}
    for agency in agencies:
        if agency.state or not agency.mdb_id:
            continue
        state = canonical_state(by_mdb.get(normalized_mdb_id(agency.mdb_id), ""))
        if state:
            resolved[agency.id] = state
    return resolved


def apply_state_backfill(yaml_text: str, resolved: dict[str, str]) -> tuple[str, list[str]]:
    """Insert a ``state:`` line into each resolved agency block in one shard.

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
        out += ["## Likely replaced — verify and update the registry", ""]
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
