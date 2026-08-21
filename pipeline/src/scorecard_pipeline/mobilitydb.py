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
registry proposals use the V2 export, as does the supersession check, which
needs the V2 `redirect.id` column to tell which record replaced which. Mirror
fallback, moved-feed discovery, and state backfill retain the legacy export
until their redirect semantics are migrated separately.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from .config import Agency
from .identity import normalized_mdb_id
from .lint import is_feed_descriptor
from .location import normalize_location
from .net import safe_get
from .supersession_review import (
    FLAG_REASONS,
    ReviewedRetirement,
    approved,
    blocking,
    review_entry_yaml,
    review_flags,
)

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
    source_record_number: int = 0
    hosted_url: str = ""  # urls.latest: MobilityData's hosted mirror on GCS
    status: str = ""  # active / deprecated / inactive / development
    is_official: bool | None = None
    # redirect.id: the catalog record(s) that replaced this one. Set on
    # deprecated rows and the catalog's only statement of which feed record
    # supersedes which. Empty on a row the catalog has not redirected.
    redirect_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateDisposition:
    """One auditable decision for one Schedule row in a pinned catalog.

    The exact source bytes and row number are the evidence anchor. Raw endpoint
    URLs, contact fields, and authentication details are deliberately omitted
    from the ledger; a curator can inspect those in the bound source snapshot.
    """

    source_record_number: int
    source_id: str
    normalized_source_id: str
    provider: str
    proposal_eligible: bool
    filter_match: bool
    decision: str
    reason_codes: tuple[str, ...]
    review_flags: tuple[str, ...] = ()
    matched_registry_ids: tuple[str, ...] = ()
    proposal_id: str | None = None
    selected_source_record_number: int | None = None
    selected_source_id: str | None = None

    def as_record(self) -> dict[str, object]:
        """JSON-ready record with stable keys and explicit nullable links."""
        selected_source: dict[str, object] | None = None
        if self.selected_source_record_number is not None:
            selected_source = {
                "record_number": self.selected_source_record_number,
                "id": self.selected_source_id or "",
            }
        return {
            "source_record_number": self.source_record_number,
            "source_id": self.source_id,
            "normalized_source_id": self.normalized_source_id,
            "provider": self.provider,
            "proposal_eligible": self.proposal_eligible,
            "filter_match": self.filter_match,
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "review_flags": list(self.review_flags),
            "matched_registry_ids": list(self.matched_registry_ids),
            "proposal_id": self.proposal_id,
            "selected_source": selected_source,
        }


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


def _catalog_feed(row: dict[str, str], *, source_record_number: int = 0) -> CatalogFeed | None:
    """Map one V2 or legacy CSV row without applying proposal eligibility."""
    normalized_type = _normalized_data_type(row)
    if not normalized_type:
        return None
    return CatalogFeed(
        source_record_number=source_record_number,
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
        redirect_ids=_pipe_values(_cell(row, "redirect.id")),
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


def parse_catalog_records(csv_text: str) -> list[CatalogFeed]:
    """Parse every recognized Schedule and Realtime row.

    Unlike :func:`parse_catalog`, this preserves Schedule rows without a usable
    direct-download URL so a disposition ledger can account for them instead
    of silently shrinking its denominator.
    """
    feeds: list[CatalogFeed] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for source_record_number, row in enumerate(reader, start=1):
        feed = _catalog_feed(row, source_record_number=source_record_number)
        if feed is not None:
            feeds.append(feed)
    return feeds


def parse_catalog(csv_text: str) -> list[CatalogFeed]:
    """Parse the catalog CSV into feed records, skipping rows without a usable
    download URL or a recognised data type."""
    return [feed for feed in parse_catalog_records(csv_text) if feed.direct_download]


def catalog_source_counts(csv_text: str) -> dict[str, int]:
    """Source-envelope counts for a reviewable proposal run.

    ``proposal_eligible_schedule_records`` is intentionally pre-user-filter
    and pre-deduplication. It records the source denominator, not permission to
    publish any individual feed.
    """
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    feeds = [
        feed
        for source_record_number, row in enumerate(rows, start=1)
        if (feed := _catalog_feed(row, source_record_number=source_record_number)) is not None
    ]
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


def _select_realtime_with_flags(
    feeds: Iterable[CatalogFeed],
) -> tuple[dict[str, str], str, tuple[str, ...]]:
    """Attach only one access-consistent URL per realtime kind.

    Exact duplicate catalog rows collapse into sets. Distinct keyless URLs or
    mixed keyless/key-gated evidence are not safe to resolve mechanically, so
    that kind stays unattached and the proposal explains why. Stable review
    flags let the disposition ledger preserve the same decision without
    parsing human-readable prose.
    """
    open_urls, gated_urls, has_unmapped_gated_feed = _realtime_urls_by_access(feeds)

    selected: dict[str, str] = {}
    notes: list[str] = []
    flags: set[str] = set()
    gated_only: list[str] = []
    for kind in _RT_KIND_ORDER:
        keyless = open_urls[kind]
        gated = gated_urls[kind]
        label = _RT_KIND_LABEL[kind]
        if keyless and gated:
            flags.add(f"realtime_{kind}_access_conflict")
            notes.append(
                f"The source catalog lists both keyless and access-key {label} "
                f"references. No {label} endpoint was attached because the access "
                "requirements conflict."
            )
        elif len(keyless) > 1:
            flags.add(f"realtime_{kind}_ambiguous")
            notes.append(
                f"The source catalog lists multiple keyless {label} endpoints. "
                f"No {label} endpoint was attached because the canonical URL is ambiguous."
            )
        elif len(keyless) == 1:
            selected[kind] = next(iter(keyless))
        elif gated:
            gated_only.append(label)
            flags.add(f"realtime_{kind}_authentication_required")

    if gated_only:
        labels = ", ".join(gated_only)
        notes.append(
            f"This agency publishes {labels}, but those feeds need an access key we don't have yet."
        )
    if has_unmapped_gated_feed:
        flags.add("realtime_unrecognized_kind_authentication_required")
        notes.append(
            "The source catalog also lists a realtime feed with an unrecognized kind "
            "that needs an access key, so it was not attached."
        )
    if notes:
        notes.append("Nothing here counts against the grade.")
    return selected, " ".join(notes), tuple(sorted(flags))


def _select_realtime(feeds: Iterable[CatalogFeed]) -> tuple[dict[str, str], str]:
    """Compatibility wrapper for callers that do not need review flags."""
    selected, note, _flags = _select_realtime_with_flags(feeds)
    return selected, note


def _schedule_exclusion_reasons(feed: CatalogFeed) -> tuple[str, ...]:
    reasons: list[str] = []
    if not _is_active(feed):
        reasons.append("non_active_status")
    if feed.is_official is False:
        reasons.append("explicitly_unofficial")
    if _requires_authentication(feed.authentication_type):
        reasons.append("schedule_authentication_required")
    if not feed.direct_download:
        reasons.append("missing_direct_download")
    elif not _feed_url_key(feed.direct_download):
        reasons.append("invalid_direct_download")
    return tuple(reasons)


def _filter_reasons(
    feed: CatalogFeed,
    *,
    country: str | None,
    subdivision: str | None,
    providers: set[str] | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if country and feed.country != country.upper():
        reasons.append("country_filter_mismatch")
    if subdivision and feed.subdivision.lower() != subdivision.lower():
        reasons.append("subdivision_filter_mismatch")
    if providers and feed.provider.lower() not in providers:
        reasons.append("provider_filter_mismatch")
    return tuple(reasons)


def _review_flags(feed: CatalogFeed, realtime_flags: tuple[str, ...]) -> tuple[str, ...]:
    flags = set(realtime_flags)
    if not feed.license_url:
        flags.add("license_not_stated")
    if feed.is_official is None:
        flags.add("official_status_unspecified")
    return tuple(sorted(flags))


def _disposition(
    feed: CatalogFeed,
    *,
    position: int,
    decision: str,
    reason_codes: tuple[str, ...],
    proposal_eligible: bool = True,
    filter_match: bool = True,
    review_flags: tuple[str, ...] = (),
    matched_registry_ids: tuple[str, ...] = (),
    proposal_id: str | None = None,
    selected: CatalogFeed | None = None,
    selected_position: int | None = None,
) -> CandidateDisposition:
    source_record_number = feed.source_record_number or position + 1
    selected_record_number = None
    selected_id = None
    if selected is not None and selected_position is not None:
        selected_record_number = selected.source_record_number or selected_position + 1
        selected_id = selected.mdb_id
    return CandidateDisposition(
        source_record_number=source_record_number,
        source_id=feed.mdb_id,
        normalized_source_id=normalized_mdb_id(feed.mdb_id),
        provider=feed.provider,
        proposal_eligible=proposal_eligible,
        filter_match=filter_match,
        decision=decision,
        reason_codes=reason_codes,
        review_flags=review_flags,
        matched_registry_ids=matched_registry_ids,
        proposal_id=proposal_id,
        selected_source_record_number=selected_record_number,
        selected_source_id=selected_id,
    )


def propose_agencies_with_dispositions(  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    feeds: list[CatalogFeed],
    *,
    country: str | None = None,
    subdivision: str | None = None,
    providers: list[str] | None = None,
    existing_ids: set[str] | None = None,
    existing_mdb_ids: set[str] | None = None,
    existing_feed_urls: set[str] | None = None,
    existing_mdb_id_matches: dict[str, set[str]] | None = None,
    existing_feed_url_matches: dict[str, set[str]] | None = None,
) -> tuple[list[ProposedAgency], list[CandidateDisposition]]:
    """Build proposals plus one decision for every Schedule catalog row.

    Schedule feeds matching the filter become agencies; realtime feeds are
    attached to the schedule feed they reference (static_reference). Key-gated
    realtime feeds are recorded as a note, not a broken URL, so they show
    neutrally rather than scoring zero. Key-gated Schedule feeds cannot produce
    a registry-ready entry and are omitted. Existing agency ids, catalog ids,
    and normalized feed URLs are skipped so a rerun never re-proposes a tracked
    feed even when its display name or URL spelling differs.
    """
    existing = existing_ids or set()
    mdb_id_matches: dict[str, set[str]] = {}
    for raw_id, agency_ids in (existing_mdb_id_matches or {}).items():
        normalized = normalized_mdb_id(raw_id)
        if normalized:
            mdb_id_matches.setdefault(normalized, set()).update(agency_ids)
    feed_url_matches: dict[str, set[str]] = {}
    for raw_url, agency_ids in (existing_feed_url_matches or {}).items():
        normalized = _feed_url_key(raw_url)
        if normalized:
            feed_url_matches.setdefault(normalized, set()).update(agency_ids)

    tracked_mdb_ids = {
        normalized_mdb_id(mdb_id) for mdb_id in (existing_mdb_ids or set()) if mdb_id
    } | set(mdb_id_matches)
    tracked_feed_urls = {
        key for url in (existing_feed_urls or set()) if (key := _feed_url_key(url))
    } | set(feed_url_matches)
    provider_filter = {p.lower() for p in providers} if providers else None

    rt_by_reference: dict[str, list[CatalogFeed]] = {}
    for feed in feeds:
        if (
            feed.data_type == "gtfs-rt"
            and feed.static_reference
            and _is_active(feed)
            and feed.is_official is not False
            and bool(_feed_url_key(feed.direct_download))
        ):
            for reference in _pipe_values(feed.static_reference):
                rt_by_reference.setdefault(normalized_mdb_id(reference), []).append(feed)

    # A catalog id is a global identity boundary. Detect conflicts across the
    # complete Schedule snapshot before eligibility or user filters can hide
    # one of its endpoints.
    source_endpoints: dict[str, set[str]] = {}
    for feed in feeds:
        if feed.data_type != "gtfs":
            continue
        source_id = normalized_mdb_id(feed.mdb_id)
        url_key = _feed_url_key(feed.direct_download)
        if source_id and url_key:
            source_endpoints.setdefault(source_id, set()).add(url_key)
    ambiguous_source_ids = {
        source_id for source_id, endpoints in source_endpoints.items() if len(endpoints) > 1
    }

    # Group mechanically eligible, filter-matched catalog records by endpoint.
    # Selecting the richest row from the complete group makes the result
    # independent of source order while retaining the selected V2 row id.
    schedule_groups: dict[str, list[tuple[int, CatalogFeed]]] = {}
    dispositions: dict[int, CandidateDisposition] = {}
    for position, feed in enumerate(feeds):
        if feed.data_type != "gtfs":
            continue
        exclusion_reasons = _schedule_exclusion_reasons(feed)
        filter_reasons = _filter_reasons(
            feed,
            country=country,
            subdivision=subdivision,
            providers=provider_filter,
        )
        if normalized_mdb_id(feed.mdb_id) in ambiguous_source_ids:
            dispositions[position] = _disposition(
                feed,
                position=position,
                decision="blocked_conflict",
                reason_codes=("catalog_id_maps_to_multiple_endpoints",),
                proposal_eligible=not bool(exclusion_reasons),
                filter_match=not bool(filter_reasons),
            )
            continue
        if exclusion_reasons:
            dispositions[position] = _disposition(
                feed,
                position=position,
                decision="excluded",
                reason_codes=exclusion_reasons + filter_reasons,
                proposal_eligible=False,
                filter_match=not bool(filter_reasons),
            )
            continue
        if filter_reasons:
            dispositions[position] = _disposition(
                feed,
                position=position,
                decision="filtered_out",
                reason_codes=filter_reasons,
                filter_match=False,
            )
            continue
        url_key = _feed_url_key(feed.direct_download)
        schedule_groups.setdefault(url_key, []).append((position, feed))

    proposals: list[ProposedAgency] = []
    used_ids = set(existing)
    proposed_sources: set[str] = set()
    proposed_urls: set[str] = set()
    for url_key in sorted(schedule_groups):
        indexed_duplicates = schedule_groups[url_key]
        duplicates = [feed for _position, feed in indexed_duplicates]
        duplicate_ids = {
            normalized_mdb_id(candidate.mdb_id) for candidate in duplicates if candidate.mdb_id
        }
        tracked_reasons: list[str] = []
        if duplicate_ids & tracked_mdb_ids:
            tracked_reasons.append("catalog_id_already_tracked")
        if url_key in tracked_feed_urls:
            tracked_reasons.append("endpoint_already_tracked")
        if tracked_reasons:
            matched_registry_ids: set[str] = set()
            for source_id in duplicate_ids:
                matched_registry_ids.update(mdb_id_matches.get(source_id, set()))
            matched_registry_ids.update(feed_url_matches.get(url_key, set()))
            for position, candidate in indexed_duplicates:
                dispositions[position] = _disposition(
                    candidate,
                    position=position,
                    decision="already_tracked",
                    reason_codes=tuple(tracked_reasons),
                    matched_registry_ids=tuple(sorted(matched_registry_ids)),
                )
            continue
        selected_position, feed = max(
            indexed_duplicates,
            key=lambda item: (
                _schedule_metadata_richness(item[1]),
                -(item[1].source_record_number or item[0] + 1),
            ),
        )
        proposal_url = _preferred_schedule_url(duplicates)
        conflicting_source_ids = duplicate_ids & proposed_sources
        if conflicting_source_ids or url_key in proposed_urls:
            reasons: list[str] = []
            if conflicting_source_ids:
                reasons.append("catalog_id_maps_to_multiple_endpoints")
            if url_key in proposed_urls:
                reasons.append("endpoint_repeated_across_groups")
            for position, candidate in indexed_duplicates:
                dispositions[position] = _disposition(
                    candidate,
                    position=position,
                    decision="blocked_conflict",
                    reason_codes=tuple(reasons),
                )
            continue

        base_id = slugify(feed.provider, feed.mdb_id)
        agency_id = base_id
        if agency_id in used_ids:
            suffix = _catalog_id_slug(feed.mdb_id, fallback_material=feed.direct_download)
            agency_id = f"{base_id}-{suffix}"
        if agency_id in existing or agency_id in used_ids:
            for position, candidate in indexed_duplicates:
                dispositions[position] = _disposition(
                    candidate,
                    position=position,
                    decision="blocked_conflict",
                    reason_codes=("proposal_id_collision",),
                )
            continue
        used_ids.add(agency_id)

        # Any duplicate row can be the id referenced by a realtime source, so
        # attach RT from the complete endpoint group to the selected proposal.
        realtime_feeds: list[CatalogFeed] = []
        for duplicate_id in sorted(duplicate_ids):
            realtime_feeds.extend(rt_by_reference.get(duplicate_id, []))
        rt_urls, rt_note, realtime_flags = _select_realtime_with_flags(realtime_feeds)

        # The catalog's feed name is usually the agency's brand ("Yolobus"), but
        # sometimes a feed descriptor ("Flex", "Bus", "Do not use - deprecated").
        # In that case the provider is the real agency name (lint.py).
        name = feed.provider if is_feed_descriptor(feed.name) else (feed.name or feed.provider)
        location = normalize_location(
            feed.country,
            subdivision_code=feed.subdivision_code,
            subdivision_name=feed.subdivision,
        )
        proposal = ProposedAgency(
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
        proposals.append(proposal)
        proposed_sources.update(duplicate_ids)
        proposed_urls.add(url_key)
        flags = _review_flags(feed, realtime_flags)
        for position, candidate in indexed_duplicates:
            if position == selected_position:
                dispositions[position] = _disposition(
                    candidate,
                    position=position,
                    decision="proposed_for_review",
                    reason_codes=("selected_group_representative",),
                    review_flags=flags,
                    proposal_id=agency_id,
                    selected=feed,
                    selected_position=selected_position,
                )
            else:
                dispositions[position] = _disposition(
                    candidate,
                    position=position,
                    decision="collapsed_duplicate",
                    reason_codes=("same_normalized_endpoint",),
                    review_flags=flags,
                    proposal_id=agency_id,
                    selected=feed,
                    selected_position=selected_position,
                )

    ordered_dispositions = [
        dispositions[position]
        for position, feed in enumerate(feeds)
        if feed.data_type == "gtfs" and position in dispositions
    ]
    return proposals, ordered_dispositions


def propose_agencies(
    feeds: list[CatalogFeed],
    *,
    country: str | None = None,
    subdivision: str | None = None,
    providers: list[str] | None = None,
    existing_ids: set[str] | None = None,
    existing_mdb_ids: set[str] | None = None,
    existing_feed_urls: set[str] | None = None,
    existing_mdb_id_matches: dict[str, set[str]] | None = None,
    existing_feed_url_matches: dict[str, set[str]] | None = None,
) -> list[ProposedAgency]:
    """Compatibility wrapper returning only reviewable registry proposals."""
    proposals, _dispositions = propose_agencies_with_dispositions(
        feeds,
        country=country,
        subdivision=subdivision,
        providers=providers,
        existing_ids=existing_ids,
        existing_mdb_ids=existing_mdb_ids,
        existing_feed_urls=existing_feed_urls,
        existing_mdb_id_matches=existing_mdb_id_matches,
        existing_feed_url_matches=existing_feed_url_matches,
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

    The current mirror lives at ``files.mobilitydatabase.org``, reachable even
    when the agency's own server firewalls datacenter IPs or sits behind a bot filter. Because
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

    def current_mirror_url(feed: CatalogFeed) -> str:
        """Upgrade legacy numeric mirror records to the current V2 endpoint."""
        normalized = normalized_mdb_id(feed.mdb_id)
        if re.fullmatch(r"mdb-[0-9]+", normalized):
            return f"https://files.mobilitydatabase.org/{normalized}/latest.zip"
        return feed.hosted_url

    if mdb_id:
        mdb_key = normalized_mdb_id(mdb_id)
        for feed in schedule:
            if normalized_mdb_id(feed.mdb_id) == mdb_key:
                return current_mirror_url(feed)

    current_key = _feed_url_key(current_url)
    if current_key:
        for feed in schedule:
            if _feed_url_key(feed.direct_download) == current_key:
                return current_mirror_url(feed)
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
        "national",
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


@dataclass(frozen=True)
class Supersession:
    """A tracked record the catalog has replaced, and the record that replaced it.

    ``review_flags`` names the ways the two records look like different agencies
    rather than one agency renamed (see ``supersession_review``). A flagged
    retirement is reported and held for a decision instead of being applied, so
    a redirect that crosses a state line cannot be recorded silently.
    """

    agency_id: str
    agency_name: str
    mdb_id: str
    successor_agency_id: str
    successor_agency_name: str
    successor_mdb_id: str
    review_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnresolvedSupersession:
    """A tracked record the catalog deprecated without a successor we publish.

    Named rather than dropped: "the catalog retired this feed record and we
    cannot say what replaced it" is a different fact from "this record is
    current", and only the first one is true here.
    """

    agency_id: str
    agency_name: str
    mdb_id: str
    redirect_ids: tuple[str, ...]
    # ambiguous_redirect | no_current_successor | successor_not_in_catalog |
    # successor_not_published | redirect_cycle
    reason: str


_REDIRECT_CHAIN_LIMIT = 8


def _reachable_catalog_ids(feed: CatalogFeed, by_mdb: dict[str, CatalogFeed]) -> list[str]:
    """Every catalog record this one's redirects lead to, directly or in turn.

    Breadth-first and cycle-safe: the catalog chains retirements, and a record
    that names two successors has to be followed down both branches before the
    chain can say which one is still current.
    """
    seen = {normalized_mdb_id(feed.mdb_id)}
    frontier = [feed]
    reached: list[str] = []
    for _ in range(_REDIRECT_CHAIN_LIMIT):
        following: list[CatalogFeed] = []
        for current in frontier:
            for target in current.redirect_ids:
                key = normalized_mdb_id(target)
                if key in seen:
                    continue
                seen.add(key)
                reached.append(key)
                onward = by_mdb.get(key)
                if onward is not None:
                    following.append(onward)
        if not following:
            break
        frontier = following
    return reached


def _resolve_successor(
    agency: Agency,
    feed: CatalogFeed,
    by_mdb: dict[str, CatalogFeed],
    registry_by_mdb: dict[str, Agency],
) -> tuple[Agency | None, str]:
    """The one record we publish that this retired record's redirects lead to.

    Among the records the redirects reach, only the ones this registry publishes
    can be a destination, and a record the catalog has itself replaced by another
    of those is not the current one. Exactly one survivor is the successor. More
    than one is a real fork, which is a curator's call, not a mechanical one.
    """
    reached = _reachable_catalog_ids(feed, by_mdb)
    if not reached:
        return None, "no_current_successor"
    if not any(key in by_mdb for key in reached):
        return None, "successor_not_in_catalog"
    candidates = {
        key: record
        for key in reached
        if (record := registry_by_mdb.get(key)) is not None
        and record.is_canonical_feed
        and record.id != agency.id
    }
    if not candidates:
        return None, "successor_not_published"
    live = [
        record
        for key, record in candidates.items()
        if not _replaced_by_another_candidate(key, candidates, by_mdb)
    ]
    if len(live) == 1:
        return live[0], ""
    return None, "redirect_cycle" if not live else "ambiguous_redirect"


def _replaced_by_another_candidate(
    key: str, candidates: dict[str, Agency], by_mdb: dict[str, CatalogFeed]
) -> bool:
    """Whether the catalog has replaced this candidate with one of the others."""
    feed = by_mdb.get(key)
    if feed is None or feed.status != "deprecated":
        return False
    return any(reached in candidates for reached in _reachable_catalog_ids(feed, by_mdb))


def _looping_retirements(retirements: dict[str, str]) -> set[str]:
    """Ids whose retirement would leave the registry pointing in a circle.

    Two records that each name the other as their successor cannot both be
    retired: the registry would have no live record to resolve either one to.
    """
    looped: set[str] = set()
    for start, first in retirements.items():
        seen = {start}
        node = first
        while node in retirements:
            if node in seen:
                looped.add(start)
                break
            seen.add(node)
            node = retirements[node]
    return looped


def find_supersessions(
    feeds: list[CatalogFeed], agencies: Iterable[Agency]
) -> tuple[list[Supersession], list[UnresolvedSupersession]]:
    """Which tracked feed records the catalog has retired, and what replaced them.

    The Mobility Database marks a replaced feed record ``deprecated`` and points
    ``redirect.id`` at the record that took its place. Both records are often
    tracked here, so without reading the redirect the same agency publishes two
    current scorecards with two different grades and neither page mentions the
    other. Nothing else in the catalog identifies that pair: the retired record
    and its successor share no id, no URL and no feed hash, which is why the
    existing duplicate detector cannot see them.

    Returns the retirements that resolve to a record we already publish, and the
    ones that do not, each with the reason. This proposes; it never rewrites the
    registry, and it never invents a successor from a similar name.
    """
    by_mdb = {normalized_mdb_id(f.mdb_id): f for f in feeds if f.mdb_id}
    registry_by_mdb: dict[str, Agency] = {
        normalized_mdb_id(a.mdb_id): a for a in agencies if a.mdb_id
    }
    resolved: list[Supersession] = []
    unresolved: list[UnresolvedSupersession] = []
    for key, agency in sorted(registry_by_mdb.items()):
        if not agency.is_canonical_feed:
            continue  # already retired, or already an alias of something else
        feed = by_mdb.get(key)
        if feed is None or feed.status != "deprecated":
            continue
        successor, reason = _resolve_successor(agency, feed, by_mdb, registry_by_mdb)
        if successor is None:
            unresolved.append(
                UnresolvedSupersession(
                    agency.id, agency.name, agency.mdb_id, feed.redirect_ids, reason
                )
            )
            continue
        resolved.append(
            Supersession(
                agency.id,
                agency.name,
                agency.mdb_id,
                successor.id,
                successor.name,
                successor.mdb_id,
                review_flags(agency, successor),
            )
        )
    looped = _looping_retirements({s.agency_id: s.successor_agency_id for s in resolved})
    unresolved.extend(
        UnresolvedSupersession(
            s.agency_id,
            s.agency_name,
            s.mdb_id,
            by_mdb[normalized_mdb_id(s.mdb_id)].redirect_ids,
            "redirect_cycle",
        )
        for s in resolved
        if s.agency_id in looped
    )
    return [s for s in resolved if s.agency_id not in looped], unresolved


def hold_for_review(
    superseded: Sequence[Supersession], reviewed: Mapping[str, ReviewedRetirement]
) -> tuple[list[Supersession], list[Supersession]]:
    """Split retirements into the ones a recorded decision covers, and the rest.

    A retirement with no review flags needs no decision and applies as before.
    A flagged one applies only when ``supersession-review.yaml`` approves that
    exact pairing for those exact reasons, so a redirect that crosses a state
    line, or that renames an agency into an unrelated one, waits for a person
    instead of being written into the registry by the weekly job.
    """
    ready: list[Supersession] = []
    held: list[Supersession] = []
    for item in superseded:
        entry = reviewed.get(item.agency_id)
        target = ready if approved(entry, item.successor_agency_id, item.review_flags) else held
        target.append(item)
    return ready, held


def apply_supersessions(yaml_text: str, supersessions: list[Supersession]) -> tuple[str, list[str]]:
    """Retire each superseded record in one registry shard, in place.

    Writes the two fields the registry already defines for this
    (``alias_of`` and ``feed_status: deprecated``) plus a comment naming the
    catalog evidence, so the reason survives in the file a curator reads. A
    targeted line insertion rather than a YAML round-trip, mirroring
    apply_replacements, so comments and hand-written formatting are untouched.
    Returns the new text and the ids changed.
    """
    wanted = {s.agency_id: s for s in supersessions}
    if not wanted:
        return yaml_text, []
    out: list[str] = []
    changed: list[str] = []
    pending: Supersession | None = None
    indent = ""
    for line in yaml_text.splitlines():
        id_match = re.match(r"(\s*)-\s*id:\s*(\S+)", line)
        if id_match:
            if pending is not None:  # a block with no name line; keep the fields anyway
                out.extend(_supersession_fields(indent, pending))
            indent = id_match.group(1)
            pending = wanted.pop(id_match.group(2), None)
            if pending is not None:
                retired_id = normalized_mdb_id(pending.mdb_id)
                successor_id = normalized_mdb_id(pending.successor_mdb_id)
                out.append(
                    f"{indent}# Mobility Database {retired_id} is deprecated "
                    f"and redirects to {successor_id}."
                )
                changed.append(pending.agency_id)
            out.append(line)
            continue
        out.append(line)
        if pending is not None and re.match(r"\s*name:\s*\S", line):
            out.extend(_supersession_fields(indent, pending))
            pending = None
    if pending is not None:
        out.extend(_supersession_fields(indent, pending))
    trailing = "\n" if yaml_text.endswith("\n") else ""
    return "\n".join(out) + trailing, changed


def _supersession_fields(indent: str, superseded: Supersession) -> list[str]:
    """The two registry fields that retire one record to its successor."""
    return [
        f"{indent}  alias_of: {superseded.successor_agency_id}",
        f"{indent}  feed_status: deprecated",
    ]


_UNRESOLVED_REASON_TEXT = {
    "ambiguous_redirect": "the catalog lists more than one successor record",
    "no_current_successor": "the catalog names no successor it still calls current",
    "successor_not_in_catalog": "the successor record is not in this catalog export",
    "successor_not_published": "the successor record is not published here",
    "redirect_cycle": "the catalog's redirects loop",
}


def render_supersessions_md(
    superseded: list[Supersession],
    unresolved: list[UnresolvedSupersession],
    *,
    today: str,
    held: Sequence[Supersession] = (),
) -> str:
    """A reviewable Markdown report of catalog-recorded feed retirements."""
    out: list[str] = [
        "# Superseded feed records in the Mobility Database",
        "",
        f"Run {today}. Source: mobilitydatabase.org catalog CSV.",
        "",
        "The Mobility Database marks a replaced feed record `deprecated` and names "
        "the record that replaced it. Where both records are tracked here, the "
        "retired one is set to `feed_status: deprecated` with `alias_of` pointing "
        "at its successor: its dated artifacts stay available for reproducibility "
        "and its scorecard URL redirects, but it stops publishing a second current "
        "grade under the same agency's name.",
        "",
        f"- **{len(superseded)}** retired records resolve to a successor published here.",
        f"- **{len(unresolved)}** retired records do not, and keep their own page.",
        "",
    ]
    if held:
        out += [
            f"- **{len(held)}** of those retirements are **held for review**: the "
            "successor is in a different state, or carries a name that does not read "
            "as this agency renamed. They are not recorded until a decision for each "
            "is in `supersession-review.yaml`.",
            "",
        ]
    if superseded:
        out += [
            "## Retired, with the successor we publish",
            "",
            "| Retired record | Successor | Catalog redirect |",
            "| --- | --- | --- |",
        ]
        for s in sorted(superseded, key=lambda item: item.agency_name.lower()):
            redirect = f"{normalized_mdb_id(s.mdb_id)} to {normalized_mdb_id(s.successor_mdb_id)}"
            out.append(
                f"| {s.agency_name} (`{s.agency_id}`) | {s.successor_agency_name} "
                f"(`{s.successor_agency_id}`) | {redirect} |"
            )
        out.append("")
    if held:
        out += [
            "## Held for review",
            "",
            "Each of these is a retirement the catalog asks for where the two records "
            "do not look like one agency. Read the pair, then record the decision in "
            "`supersession-review.yaml` at the repository root: `retire` if it is the "
            "same agency or a real merger, `keep_separate` if it is not. Until then "
            "the retirement is not written, and the build fails if one is written "
            "without a decision.",
            "",
        ]
        for s in sorted(held, key=lambda item: item.agency_name.lower()):
            reasons = "; ".join(FLAG_REASONS[flag] for flag in blocking(s.review_flags))
            out += [
                f"### {s.agency_name} (`{s.agency_id}`) to {s.successor_agency_name} "
                f"(`{s.successor_agency_id}`)",
                "",
                f"- Catalog redirect: {normalized_mdb_id(s.mdb_id)} to "
                f"{normalized_mdb_id(s.successor_mdb_id)}",
                f"- Held because {reasons}.",
                "",
                "```yaml",
                review_entry_yaml(s.agency_id, s.successor_agency_id, s.review_flags).rstrip("\n"),
                "```",
                "",
            ]
    renamed = [s for s in superseded if s.agency_name.strip() != s.successor_agency_name.strip()]
    if renamed:
        out += [
            "### Read these ones closely",
            "",
            "The successor publishes under a different name, so the redirect sends a "
            "reader from one agency's name to another. That is what the catalog "
            "records, and it is right often enough to follow, but it is the case "
            "worth checking by hand before merging.",
            "",
        ]
        for s in sorted(renamed, key=lambda item: item.agency_name.lower()):
            out.append(
                f"- {s.agency_name} (`{s.agency_id}`) to {s.successor_agency_name} "
                f"(`{s.successor_agency_id}`)"
            )
        out.append("")
    if unresolved:
        out += [
            "## Retired, with no successor we publish",
            "",
            "These stay published on their own record. The catalog has retired the "
            "feed source, so the grade describes a feed the agency may no longer "
            "publish; deciding what to say on those pages is a curator call, not a "
            "mechanical one.",
            "",
        ]
        for u in sorted(unresolved, key=lambda item: item.agency_name.lower()):
            reason = _UNRESOLVED_REASON_TEXT.get(u.reason, u.reason)
            catalog_id = normalized_mdb_id(u.mdb_id)
            named = ", ".join(normalized_mdb_id(target) for target in u.redirect_ids)
            points_at = f" It points at {named}." if named else ""
            out.append(f"- {u.agency_name} (`{u.agency_id}`, {catalog_id}): {reason}.{points_at}")
        out.append("")
    return "\n".join(out)


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
