"""Canonical organization/feed identity reporting.

The registry historically used one ``Agency`` per URL. This module makes the
coverage denominator explicit while the curated alias and organization fields
are backfilled. It never deletes or merges a feed automatically.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from urllib.parse import urlsplit

from .config import Agency


def normalized_feed_url(url: str) -> str:
    """Scheme-insensitive endpoint key for HTTP/HTTPS alias detection."""
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
    path = parsed.path.rstrip("/") or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{port}{path}{query}"


def _duplicate_groups(values: Iterable[tuple[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for key, agency_id in values:
        if key:
            grouped[key].append(agency_id)
    return [
        {"key": key, "ids": sorted(ids)} for key, ids in sorted(grouped.items()) if len(ids) > 1
    ]


def build_identity_ledger(agencies: Iterable[Agency]) -> dict[str, object]:
    """Coverage counts and unresolved duplicate groups for public denominators."""
    records = list(agencies)
    active = [agency for agency in records if agency.feed_status == "active"]
    canonical = [agency for agency in active if agency.is_canonical_feed]
    aliases = [agency for agency in records if agency.alias_of]
    organizations = {agency.organization_key for agency in canonical}
    return {
        "configured_feed_records": len(records),
        "active_feed_records": len(active),
        "canonical_feed_records": len(canonical),
        "distinct_organizations": len(organizations),
        "alias_records": len(aliases),
        "official_sources": sum(agency.is_official is True for agency in records),
        "official_status_unknown": sum(agency.is_official is None for agency in records),
        "status_counts": {
            status: sum(agency.feed_status == status for agency in records)
            for status in ("active", "development", "deprecated", "inactive")
        },
        "unresolved_duplicate_mdb_ids": _duplicate_groups(
            (agency.mdb_id, agency.id) for agency in canonical
        ),
        "unresolved_duplicate_feed_urls": _duplicate_groups(
            (normalized_feed_url(agency.static_gtfs_url), agency.id) for agency in canonical
        ),
    }
