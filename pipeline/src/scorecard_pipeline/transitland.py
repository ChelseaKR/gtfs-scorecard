"""Discover feeds from the Transitland Atlas, a second source alongside the
Mobility Database.

The Mobility Database catalog is heavily weighted toward Europe and North
America; the coverage roadmap names a second discovery source as what actually
raises non-Western coverage (docs/global-coverage-roadmap.md). The Transitland
Atlas (github.com/transitland/transitland-atlas, CC-BY) is an independently
curated, keyless registry of feeds expressed as DMFR (Distributed Mobility Feed
Registry) JSON, strongest exactly where the Mobility Database is thin. The REST
v2 API needs an account key and so is unusable in CI; the Atlas DMFR files are
public and openly licensed, which is why this module reads them (the same source
ntd_crosswalk.py already ingests).

The design contract is deliberately simple: :func:`parse_dmfr` emits
``mobilitydb.CatalogFeed`` objects, the exact shape ``propose_agencies``,
``find_replacements``, and the rest of the discovery pipeline already consume. A
Transitland-sourced feed therefore flows through the same proposer, the same
deduplication (by stable id and normalized URL), and the same
curator-review-before-registry workflow as a Mobility Database feed.

One honest limitation: DMFR does not carry an ISO country or subdivision on a
feed — only a geohash inside the Onestop ID. This module leaves the location
fields empty, which ``propose_agencies`` preserves as an unassigned location for
a curator to fill during the same source, reuse, and identity review every feed
already gets. It never guesses a country. The parse function is pure over parsed
DMFR documents, so it is testable without the network; only the fetch reaches
out, and it reuses ntd_crosswalk's Atlas fetch.
"""

from __future__ import annotations

import re
from typing import Any

from .mobilitydb import CatalogFeed

# DMFR realtime URL keys, and the CatalogFeed entity_type each maps to. Mirrors
# mobilitydb._RT_ENTITY_TO_KIND, in the other direction: DMFR expresses realtime
# as URLs on the schedule feed rather than as separate rows, so each present URL
# becomes its own gtfs-rt CatalogFeed that references the schedule feed's id.
_DMFR_RT_URLS = {
    "realtime_trip_updates": "tu",
    "realtime_vehicle_positions": "vp",
    "realtime_alerts": "sa",
}

# DMFR authorization.type is empty/absent for an open feed; any other value
# ("query_param", "header", "basic_auth", "oauth2") means a key is required.
# Map to the CatalogFeed authentication_type convention where "" is open and a
# non-open value is flagged so _requires_authentication treats it as key-gated.
_OPEN_AUTH_TYPES = frozenset({"", "none"})

_ONESTOP_PREFIX = re.compile(r"^[a-z]-[0-9bcdefghjkmnpqrstuvwxyz]+-")


def _provider_from_onestop(onestop_id: str) -> str:
    """A readable fallback provider from a Onestop feed id.

    A Onestop id is ``<spec-letter>-<geohash>-<slug>`` (e.g.
    ``f-r1f-adelaidemetrocomau``). Strip the type and geohash prefix and return
    the slug; the curator gives it a proper display name during review. Ids that
    do not match the shape are returned unchanged.
    """
    stripped = _ONESTOP_PREFIX.sub("", onestop_id)
    return stripped or onestop_id


def _auth_type(authorization: dict[str, Any]) -> str:
    raw = str(authorization.get("type") or "").strip().lower()
    return "" if raw in _OPEN_AUTH_TYPES else "1"


def _operator_names_by_feed(doc: dict[str, Any]) -> dict[str, str]:
    """Map a feed's Onestop id to the first top-level operator that lists it.

    DMFR operators can be defined at the document top level and reference their
    feeds via ``associated_feeds``; using that operator's name gives a better
    provider than the id slug when a feed has no embedded operators.
    """
    names: dict[str, str] = {}
    for operator in doc.get("operators", []) or []:
        name = str(operator.get("name") or "").strip()
        if not name:
            continue
        for assoc in operator.get("associated_feeds", []) or []:
            feed_id = assoc.get("feed_onestop_id")
            if feed_id:
                names.setdefault(feed_id, name)
    return names


def _feed_provider(feed: dict[str, Any], top_level: dict[str, str]) -> str:
    """The best available provider name for a feed: an embedded operator, then a
    top-level operator that references it, then the id slug."""
    embedded = feed.get("operators") or []
    for operator in embedded:
        name = str(operator.get("name") or "").strip()
        if name:
            return name
    feed_id = str(feed.get("id") or "")
    if feed_id in top_level:
        return top_level[feed_id]
    return _provider_from_onestop(feed_id)


def parse_dmfr(docs: list[dict[str, Any]]) -> list[CatalogFeed]:
    """Turn parsed Transitland Atlas DMFR documents into CatalogFeed rows.

    Each GTFS Schedule feed becomes one ``gtfs`` CatalogFeed. Each realtime URL
    on that feed becomes a separate ``gtfs-rt`` CatalogFeed whose
    ``static_reference`` is the schedule feed's id, so the proposer wires
    realtime to its schedule feed exactly as it does for the Mobility Database.
    Location fields are left empty (DMFR carries no ISO country); everything else
    — the download URL, the license URL, whether a key is required, and a
    provider name — comes straight from the DMFR record.
    """
    feeds: list[CatalogFeed] = []
    for doc in docs:
        top_level = _operator_names_by_feed(doc)
        for feed in doc.get("feeds", []) or []:
            spec = str(feed.get("spec") or "").strip().lower()
            feed_id = str(feed.get("id") or "").strip()
            if not feed_id:
                continue
            urls = feed.get("urls") or {}
            license_url = str((feed.get("license") or {}).get("url") or "").strip()
            auth = _auth_type(feed.get("authorization") or {})
            provider = _feed_provider(feed, top_level)

            if spec == "gtfs":
                static = str(urls.get("static_current") or "").strip()
                if static:
                    feeds.append(
                        CatalogFeed(
                            mdb_id=feed_id,
                            data_type="gtfs",
                            entity_type="",
                            country="",
                            subdivision_code="",
                            subdivision="",
                            municipality="",
                            provider=provider,
                            name=provider,
                            direct_download=static,
                            license_url=license_url,
                            authentication_type=auth,
                            static_reference="",
                            status="active",
                        )
                    )
                for url_key, entity in _DMFR_RT_URLS.items():
                    rt_url = str(urls.get(url_key) or "").strip()
                    if rt_url:
                        feeds.append(
                            CatalogFeed(
                                mdb_id=f"{feed_id}~{entity}",
                                data_type="gtfs-rt",
                                entity_type=entity,
                                country="",
                                subdivision_code="",
                                subdivision="",
                                municipality="",
                                provider=provider,
                                name=provider,
                                direct_download=rt_url,
                                license_url=license_url,
                                authentication_type=auth,
                                static_reference=feed_id,
                                status="active",
                            )
                        )
    return feeds


def fetch_feeds(fetch: Any = None) -> list[CatalogFeed]:
    """Fetch every Atlas DMFR document and parse them into CatalogFeed rows.

    Reuses ntd_crosswalk's Atlas fetch (the same keyless, CC-BY source), so the
    GitHub Contents listing and per-file download behavior stay in one place.
    ``fetch`` is an optional URL-to-text callable for tests.
    """
    from .ntd_crosswalk import fetch_atlas

    return parse_dmfr(fetch_atlas(fetch))
