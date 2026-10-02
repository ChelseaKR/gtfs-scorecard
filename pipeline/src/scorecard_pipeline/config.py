"""Agency registry and pipeline paths.

Phase 1 hardcoded the two pilot agencies. Phase 4 replaced that with a
manifest-backed registry so any feed URL can be added without a code change.
Feed URLs and licenses are documented in docs/feeds.md.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal


def utc_today() -> dt.date:
    """Today's date in UTC, never the runner's local zone.

    Every date this pipeline stores or grades against is a UTC date: the
    scheduled build runs on UTC runners, so `snapshot_date`, the dated artifact
    filename, and the "today" that freshness and expiry are measured against
    are all UTC. `dt.date.today()` reads whatever zone the *machine* is in, so
    the same corpus scored from a laptop in America/Los_Angeles after 17:00 PDT
    would be stamped a day behind CI and graded against the wrong day. That
    exact split already shipped once (render_site's Google gate read
    `dt.date.today()` while the rest of the render used a frozen UTC instant),
    so the clock read lives in one place now.

    Callers that already accept an explicit date keep doing so; this is only
    the default when nobody said which day they meant.
    """
    return dt.datetime.now(dt.UTC).date()


@dataclass(frozen=True)
class ReuseEvidence:
    """Curator-reviewed permission and identity evidence for one GTFS feed."""

    decision: str
    source_kind: str
    provider_source_url: str
    terms_url: str
    scope: tuple[str, ...]
    attribution: str
    reviewed_by: str
    reviewed_on: str
    identity_reviewed: bool


#: A fact a license states that may not be known: true, false, or the string
#: ``"unknown"``. Never ``None`` and never a default, so an unmeasured term
#: cannot read as a permissive one (issue #372).
Tri = bool | Literal["unknown"]
TRI_UNKNOWN: Final = "unknown"


@dataclass(frozen=True)
class LicenseBlock:
    """The structured license block of one registry record (issue #372).

    A recorded description of the terms, not a decision about them. It sits
    beside the free-text ``license_note`` and never replaces it. See
    ``license_ledger.py`` for the vocabulary and every validation rule, and
    ``registry/license.schema.json`` for the same shape as a JSON Schema.

    ``share_alike`` records what the license states. Share-alike feeds are
    admitted, with a reuse notice (owner decision, 2026-09-19); see
    ``license_notice.py``.
    """

    id: str
    attribution_required: Tri
    redistribution_allowed: Tri
    share_alike: Tri
    status: str
    name: str = ""
    terms_url: str = ""
    retrieved_on: str = ""
    attribution: str = ""
    reviewed_by: str = ""
    reviewed_on: str = ""
    reviewer_note: str = ""


@dataclass(frozen=True)
class FetchAuth:
    """How to present a credential to a registration-walled feed URL (#371).

    ``secret`` is the *name* of an environment variable, never the credential
    itself; feed_auth.py resolves it at fetch time and fails closed when it is
    missing. ``name`` is the header or query-parameter name the publisher
    expects; it is empty for ``basic``, which always uses ``Authorization``.
    """

    kind: str
    secret: str
    name: str = ""


@dataclass(frozen=True)
class Agency:
    """One transit agency tracked by the scorecard."""

    id: str
    name: str
    static_gtfs_url: str
    # GTFS-Realtime endpoints, by feed kind. Empty dict means the agency
    # does not publish realtime (shown as "Not yet published", never a zero).
    rt_urls: dict[str, str] = field(default_factory=dict)
    # Shown on the scorecard when realtime isn't scored (e.g. key-gated feeds).
    rt_note: str = ""
    license_note: str = ""
    # Set by a curator after manually confirming a feed's operating status,
    # mainly for long-expired feeds: a still-running agency reads as recoverable
    # rather than defunct. Empty means no human check has been recorded.
    operating_note: str = ""
    # Curator-recorded NTD context the feed itself cannot express: a shared
    # regional feed (several agencies, one export), an FTA waiver, or another
    # reporting arrangement. Shown with the NTD readiness box so those agencies
    # are never flagged for identity or coverage they do not own (R15). Empty
    # means no special arrangement is on record.
    ntd_note: str = ""
    # The feed's Mobility Database source id, when known. Lets feed discovery
    # follow the catalog's own record of a feed by id instead of fuzzy name
    # matching, so a moved URL is caught exactly. Empty means not pinned.
    mdb_id: str = ""
    # Canonical identity is separate from a feed endpoint. organization_id joins
    # several modal or regional feeds to one operator; alias_of keeps a retired
    # endpoint reproducible without counting it as another active feed.
    organization_id: str = ""
    alias_of: str = ""
    feed_variant: str = ""
    # Mobility Database source status/provenance. Existing hand-curated records
    # default to active/unknown; sync proposals retain explicit catalog values.
    feed_status: str = "active"
    is_official: bool | None = None
    # The agency's five-digit National Transit Database ID, when known. RY2026
    # submissions must provide a stable agency_id for each represented reporter
    # and crosswalk it to this NTD ID on P-50; the two values do not have to be
    # equal. When this is set, the scorecard shows their optional equality as a
    # neutral, zero-deduction comparison. Empty means no NTD ID on file and that
    # comparison is shown as not-yet-checked. See ntd.assess_id_alignment.
    ntd_id: str = ""
    # Assigned ISO 3166-1 alpha-2 country code. It defaults to US only as a
    # compatibility behavior for registry entries that predate this field. A
    # non-US agency (e.g. "CA") is scored on the same GTFS-quality
    # rubric but skips the US-only surfaces: the FTA National Transit Database
    # GTFS-readiness and NTD-id-alignment views, which have no meaning
    # outside the US. See ADR 0026 (internationalization).
    country: str = "US"
    # Primary catalog jurisdiction, expressed without overloading a US "state"
    # field. The code is ISO 3166-2 (for example US-CA or CA-ON); the name is
    # display text from the curated registry or Mobility Database. A feed may
    # cross boundaries, so these fields locate its primary catalog record and
    # do not claim to describe its complete service area.
    subdivision_code: str = ""
    subdivision_name: str = ""
    # Deprecated US-only compatibility alias used by API v1, program rollups,
    # and the current US map. New code should prefer subdivision_code/name.
    state: str = ""
    # Service shape, so Freshness scores an intermittent feed fairly. "fixed"
    # (the default) is normal year-round service. "seasonal" or "demand_response"
    # service has deliberate calendar gaps, so a recently lapsed calendar is
    # softened rather than scored as a silent expiry. A long-dead feed is still
    # treated seriously regardless, so this is not a way to hide a stale feed.
    service_type: str = "fixed"
    # Set by a curator when the agency runs fare-free by policy. A feed with no
    # fare files is then credited for completeness instead of docked, and the
    # "no fare data" finding becomes a neutral note. Mirrors the neutral
    # treatment of agencies without realtime: a deliberate policy is not a gap.
    fare_free: bool = False
    # Explicit, curator-reviewed evidence that this feed may be reused. Legacy
    # catalog metadata and prose license notes are intentionally not promoted
    # into this record: absence means the reuse decision is still unreviewed.
    reuse_evidence: ReuseEvidence | None = None
    # Opt-in to the large-feed tier: a curator has confirmed this is a real,
    # published feed whose compressed download exceeds 256 MiB or whose largest
    # single table expands past 512 MiB (a national rail-plus-bus export, a whole
    # metro network). It raises the size ceilings to a bounded larger level and
    # streams the download to disk with a bounded memory footprint. The zip-bomb
    # shape guards (entry count, compression ratio, central-directory-only
    # inspection) stay unchanged. Default False keeps every ordinary feed on the
    # tight standard caps. See fetch.LARGE_LIMITS and docs/global-coverage-roadmap.md.
    large_feed: bool = False
    # Give this record a Daily shard to itself. It says nothing about the feed's
    # size or trust, so it does not touch the archive ceilings the way
    # ``large_feed`` does. It is for a source that takes minutes to serve one
    # ordinary-sized feed (a server that builds the archive on each request), so
    # the wait cannot use up the job budget of the ~64 records that would
    # otherwise share its shard. See shards.plan_shards and registry/README.md.
    own_shard: bool = False
    # A credential reference for a feed behind a registration wall (#371). None
    # is every ordinary keyless feed. When set, fetching fails closed without
    # the named environment variable and never falls back to a mirror. See
    # feed_auth.py and registry/README.md.
    fetch_auth: FetchAuth | None = None
    # The structured license block (issue #372), or None when the record has
    # not been given one. None means "no block on file", never "unrestricted";
    # nothing reads it to admit or score a feed, and the only thing it changes in
    # what is published is the share-alike reuse notice. The free-text
    # ``license_note`` above stays the record's prose.
    license_block: LicenseBlock | None = None

    @property
    def organization_key(self) -> str:
        """Stable operator key for portfolio counts and identity joins."""
        return self.organization_id or self.id

    @property
    def is_canonical_feed(self) -> bool:
        return self.feed_status == "active" and not self.alias_of


# Endpoints verified against the Mobility Database and transit.land;
# see docs/feeds.md for sources, licenses, and polling etiquette.
AGENCIES: dict[str, Agency] = {}


def current_agency_ids(agency_ids: Iterable[str]) -> list[str]:
    """Keep ids that belong to active canonical records in the loaded registry.

    Current-corpus jobs use this boundary so retained alias artifacts stay
    available for historical reproduction without being counted, monitored, or
    published beside their live successor. An empty process-global registry is
    the established library/test compatibility mode: callers may operate on a
    synthetic artifact tree without first loading repository configuration.
    """
    ids = list(agency_ids)
    if not AGENCIES:
        return ids
    return [
        agency_id
        for agency_id in ids
        if (agency := AGENCIES.get(agency_id)) is not None and agency.is_canonical_feed
    ]


def register(agency: Agency) -> None:
    """Add an agency to the registry (used by agencies module at import)."""
    AGENCIES[agency.id] = agency


def repo_root() -> Path:
    """Repository root, overridable for tests via SCORECARD_ROOT."""
    env = os.environ.get("SCORECARD_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def raw_dir() -> Path:
    return repo_root() / "data" / "raw"


def artifacts_dir() -> Path:
    return repo_root() / "data" / "artifacts"


def cache_dir() -> Path:
    return repo_root() / "data" / "cache"
