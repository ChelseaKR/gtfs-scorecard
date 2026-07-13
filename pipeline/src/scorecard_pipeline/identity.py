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
    try:
        # ``urlsplit`` itself rejects malformed IPv6 brackets and netloc
        # characters whose NFKC form would change URL delimiters.  Catalog
        # input is advisory, so both parse-time and port-time failures become
        # an unusable key instead of aborting the whole sync.
        parsed = urlsplit(url.strip())
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        parsed_port = parsed.port
    except ValueError:
        # External catalog rows are advisory input. A malformed netloc or port
        # must not crash the whole identity-ledger build or be collapsed into
        # a valid endpoint; an empty key makes duplicate grouping skip this row.
        return ""
    if scheme not in {"http", "https"} or not host:
        return ""
    # Credentials have no place in a public feed identity. Besides leaking into
    # catalog data, accepting them would let a userinfo URL collapse onto the
    # same mirror key as the credential-free endpoint.
    if parsed.username is not None or parsed.password is not None:
        return ""
    default_port = (scheme == "http" and parsed_port == 80) or (
        scheme == "https" and parsed_port == 443
    )
    port = "" if parsed_port is None or default_port else f":{parsed_port}"
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
    provisional_organization_keys = [agency for agency in canonical if not agency.organization_id]
    return {
        "configured_feed_records": len(records),
        "active_feed_records": len(active),
        "canonical_feed_records": len(canonical),
        "active_canonical_feed_records": len(canonical),
        "distinct_organizations": len(organizations),
        "distinct_organization_keys": len(organizations),
        "provisional_organization_keys": len(provisional_organization_keys),
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
