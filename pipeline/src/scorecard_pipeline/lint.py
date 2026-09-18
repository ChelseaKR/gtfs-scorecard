"""Registry hygiene checks.

The Mobility Database sync can pull in entries whose `name` is the catalog's
feed descriptor ("Flex", "Bus", "Do not use - deprecated") rather than the
transit provider. These checks catch that, plus a non-HTTPS feed URL or a
missing mdb_id, so the registry stays clean as it grows. Reported by
`scorecard lint`; the descriptor set is also used by the sync so future
proposals use the provider name instead.

``literal_credential`` (issue #371) is the one check about secrets: a record
must name a credential by environment variable, never carry one. It covers the
``fetch_auth.secret`` field itself, a credentialed record whose URL already
carries the credential parameter, and user-info (``https://user:pass@host``) in
any feed URL. Its detail never repeats the offending value, because this
report is printed to CI logs.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from .config import Agency
from .feed_auth import reference_problem
from .identity import normalized_feed_url, normalized_mdb_id

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
    kind: str  # feed_descriptor_name | literal_credential | non_https_url | missing_mdb_id
    detail: str


def _has_userinfo(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.username is not None or parts.password is not None


def credential_problems(agency: Agency) -> list[str]:
    """Every way ``agency`` carries a literal credential, as plain sentences.

    Publisher-published keys that some open feeds put in their public URL (a
    Mecatran ``apiKey``, for example) are not flagged: they are printed on the
    publisher's own open-data page and the registry has always carried them.
    What is flagged is a credential issued to an account, which is exactly what
    ``fetch_auth`` exists to keep out of the record.
    """
    problems: list[str] = []
    auth = agency.fetch_auth
    if auth is not None:
        problem = reference_problem(auth.secret)
        if problem is not None:
            problems.append(problem)
        if auth.kind == "query" and auth.name:
            try:
                present = {key for key, _ in parse_qsl(urlsplit(agency.static_gtfs_url).query)}
            except ValueError:
                present = set()
            if auth.name in present:
                problems.append(
                    f"static_gtfs_url already carries the {auth.name!r} parameter that "
                    "fetch_auth supplies; remove it from the URL (the value is not printed)"
                )
    urls = {"static_gtfs_url": agency.static_gtfs_url}
    urls.update({f"rt_urls.{kind}": url for kind, url in agency.rt_urls.items()})
    for field, url in urls.items():
        if _has_userinfo(url):
            problems.append(
                f"{field} carries a user name or password before the host; use fetch_auth "
                "with kind basic instead (the value is not printed)"
            )
    return problems


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
        issues.extend(
            RegistryIssue(agency.id, "literal_credential", problem)
            for problem in credential_problems(agency)
        )
        if not agency.static_gtfs_url.startswith("https://"):
            # A URL with user-info is already reported, without its value, as
            # literal_credential; echoing it here would print the password.
            detail = "" if _has_userinfo(agency.static_gtfs_url) else agency.static_gtfs_url
            issues.append(RegistryIssue(agency.id, "non_https_url", detail))
        if not agency.mdb_id:
            issues.append(RegistryIssue(agency.id, "missing_mdb_id", ""))
    canonical = [agency for agency in records if agency.is_canonical_feed]
    for kind, pairs in (
        (
            "duplicate_mdb_id",
            ((normalized_mdb_id(agency.mdb_id), agency.id) for agency in canonical),
        ),
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
        "literal_credential": 0,
        "feed_descriptor_name": 1,
        "duplicate_mdb_id": 2,
        "duplicate_feed_url": 3,
        "non_https_url": 4,
        "missing_mdb_id": 5,
    }
    issues.sort(key=lambda i: (order.get(i.kind, 9), i.agency_id))
    return issues
