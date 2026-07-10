"""Registry hygiene checks.

The Mobility Database sync can pull in entries whose `name` is the catalog's
feed descriptor ("Flex", "Bus", "Do not use - deprecated") rather than the
transit provider. These checks catch that, plus a non-HTTPS feed URL or a
missing mdb_id, so the registry stays clean as it grows. Reported by
`scorecard lint`; the descriptor set is also used by the sync so future
proposals use the provider name instead.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .config import Agency
from .identity import normalized_feed_url

# Catalog "name" values that describe a feed, not an agency. An agency whose name
# is one of these was synced from the wrong column; its provider name is correct.
FEED_DESCRIPTOR_NAMES = frozenset(
    {
        "do not use - deprecated",
        "flex",
        "flex v2 included",
        "flex v2",
        "static feed for realtime",
        "bus",
        "rail",
        "fixed route",
    }
)


def is_feed_descriptor(name: str) -> bool:
    """True when a name is a feed descriptor, not a real agency name."""
    return name.strip().lower() in FEED_DESCRIPTOR_NAMES


@dataclass(frozen=True)
class RegistryIssue:
    agency_id: str
    kind: str  # feed_descriptor_name | non_https_url | missing_mdb_id
    detail: str


def lint_registry(agencies: Iterable[Agency]) -> list[RegistryIssue]:
    """Hygiene issues across the registry, worst (a wrong name) first."""
    records = list(agencies)
    issues: list[RegistryIssue] = []
    for agency in records:
        if is_feed_descriptor(agency.name):
            issues.append(
                RegistryIssue(
                    agency.id,
                    "feed_descriptor_name",
                    f"name {agency.name!r} is a feed descriptor, not an agency name",
                )
            )
        if not agency.static_gtfs_url.startswith("https://"):
            issues.append(RegistryIssue(agency.id, "non_https_url", agency.static_gtfs_url))
        if not agency.mdb_id:
            issues.append(RegistryIssue(agency.id, "missing_mdb_id", ""))
    canonical = [agency for agency in records if agency.is_canonical_feed]
    for kind, pairs in (
        ("duplicate_mdb_id", ((agency.mdb_id, agency.id) for agency in canonical)),
        (
            "duplicate_feed_url",
            ((normalized_feed_url(agency.static_gtfs_url), agency.id) for agency in canonical),
        ),
    ):
        grouped: dict[str, list[str]] = defaultdict(list)
        for key, agency_id in pairs:
            if key:
                grouped[key].append(agency_id)
        for key, ids in grouped.items():
            if len(ids) < 2:
                continue
            detail = f"{key} is shared by canonical records: {', '.join(sorted(ids))}"
            issues.extend(RegistryIssue(agency_id, kind, detail) for agency_id in ids)
    order = {
        "feed_descriptor_name": 0,
        "duplicate_mdb_id": 1,
        "duplicate_feed_url": 2,
        "non_https_url": 3,
        "missing_mdb_id": 4,
    }
    issues.sort(key=lambda i: (order.get(i.kind, 9), i.agency_id))
    return issues
