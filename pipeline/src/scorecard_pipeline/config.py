"""Agency registry and pipeline paths.

Phase 1 hardcoded the two pilot agencies. Phase 4 replaced that with a
manifest-backed registry so any feed URL can be added without a code change.
Feed URLs and licenses are documented in docs/feeds.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


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
