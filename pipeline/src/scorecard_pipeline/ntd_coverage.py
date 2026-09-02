"""Invert the NTD join: start from the reporter roster, not from a feed.

`ntd_crosswalk` populates an `ntd_id` outward from a feed we already track, so
the population it can describe is closed by construction. A reporter with no
feed in any catalogue can never enter that crosswalk, and therefore can never be
counted. The question a Caltrans district liaison or an FTA reviewer actually
asks -- which reporters obligated to publish GTFS have nothing discoverable at
all -- is unreachable from that direction.

This module runs the join the other way. The left side is FTA's own reporter
roster (NTD Annual Database, Agency Information). The right side is every open
feed registry we can read: this project's registry, the Transitland Atlas, and
the Mobility Database. Each reporter is placed in exactly one match tier, and
the tiers are ordered by how much the evidence is worth, so a reader can draw
the line wherever they trust it and read a different number.

Three things this deliberately does not do.

It does not grade anyone. A reporter with no discoverable feed is reported as a
gap in what open catalogues can see, never as a zero and never as a finding
about the agency. The fix may belong to FTA's own crosswalk, to a catalogue, or
to us.

It does not guess. Where the evidence is a name that merely shares a token, the
tier says so and the number is reported twice: once counting weak matches as
matches, once not. The distance between those two numbers is the honest width of
the measurement, and it is wide.

It does not mix units. Every count here is a count of NTD reporters. The
registry counts feed records, which is a different unit -- regional feeds, modal
variants, and retired aliases are separate records for one operator -- and the
two must never be added or compared as though they were the same thing.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ntd_crosswalk import normalize_name

# NTD mode codes that describe scheduled, route-based service. The RY2023 D-10
# requirement applies to reporters operating fixed-route or deviated-fixed-route
# service, so these are the modes that put a reporter in scope.
#
# Deviated fixed route has no distinct NTD mode code -- agencies report it under
# Bus (MB) or, when the deviation dominates, under Demand Response (DR). DR and
# Vanpool (VP) are therefore excluded, which makes the in-scope population a
# lower bound rather than an exact census. Say so wherever the count is used.
FIXED_ROUTE_MODES = frozenset(
    {
        "AR",  # Alaska Railroad
        "CB",  # Commuter Bus
        "CC",  # Cable Car
        "CR",  # Commuter Rail
        "FB",  # Ferryboat
        "HR",  # Heavy Rail
        "IP",  # Inclined Plane
        "LR",  # Light Rail
        "MB",  # Bus
        "MG",  # Monorail / Automated Guideway
        "PB",  # Publico
        "RB",  # Bus Rapid Transit
        "SR",  # Streetcar Rail
        "TB",  # Trolleybus
        "TR",  # Aerial Tramway
        "YR",  # Hybrid Rail
    }
)

# NTD reports Puerto Rico and the territories as states. Registry records for
# them carry their own ISO country code, so a join scoped to country == "US"
# silently drops every territorial reporter.
US_AND_TERRITORY_CODES = frozenset({"US", "PR", "VI", "GU", "AS", "MP"})

# Match tiers, strongest first. `strong` tiers rest on an identifier or an exact
# name within one state; the rest are heuristics that a human should confirm.
TIER_ORDER = (
    "registry_ntd_id",
    "registry_name_exact",
    "registry_domain",
    "registry_name_fuzzy",
    "atlas_ntd_id",
    "catalog_name_exact",
    "catalog_domain",
    "catalog_name_fuzzy",
    "weak_shared_token",
    "no_candidate",
)
STRONG_TIERS = frozenset(
    {
        "registry_ntd_id",
        "registry_name_exact",
        "registry_domain",
        "registry_name_fuzzy",
        "atlas_ntd_id",
        "catalog_name_exact",
        "catalog_domain",
        "catalog_name_fuzzy",
    }
)
TRACKED_BY_US_TIERS = frozenset(
    {
        "registry_ntd_id",
        "registry_name_exact",
        "registry_domain",
        "registry_name_fuzzy",
    }
)

# Two names match loosely when this much of their combined distinctive
# vocabulary is shared. 0.6 keeps "Spokane Transit Authority" against "Spokane
# Transit" and rejects "Valley Transit" against "Antelope Valley Transit".
FUZZY_NAME_THRESHOLD = 0.6

# A host serving feeds for more than this many records is a vendor or archive,
# not an agency's own domain, so a domain match through it proves nothing.
SHARED_HOST_RECORDS = 3

# A token has to be at least this long, and rare enough in one state, before a
# bare token overlap is worth surfacing even as weak evidence.
MIN_TOKEN_LENGTH = 4
MAX_TOKEN_RECORDS = 3

_URL_HOST = re.compile(r"^[a-z][a-z0-9+.-]*://([^/]+)")


def registrable_host(url: str) -> str:
    """The last two labels of a URL's host, lowercased, or "" if there is none.

    Deliberately naive about public suffixes: a two-label reduction folds
    `gtfs.muni.org` and `www.muni.org` together, which is the point, and the
    shared-host filter removes the cases where that folding would over-match.
    """
    match = _URL_HOST.match(url.strip().lower())
    if match is None:
        return ""
    host = match.group(1).split(":")[0].strip(".")
    labels = [label for label in host.split(".") if label]
    if not labels:
        return ""
    return ".".join(labels[-2:]) if len(labels) >= 2 else labels[0]


def name_tokens(name: str) -> frozenset[str]:
    """Distinctive tokens of an operator name, boilerplate already dropped."""
    normalized = normalize_name(name)
    return frozenset(normalized.split()) if normalized else frozenset()


@dataclass(frozen=True)
class FeedRecord:
    """One catalogue entry, reduced to what the join can actually use."""

    key: str
    state: str  # two-letter US state or territory code, "" when unknown
    name: str
    urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class Reporter:
    """One NTD reporter from the Agency Information roster."""

    ntd_id: str
    name: str
    dba: str
    state: str
    reporter_type: str
    organization_type: str
    url: str

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(n for n in (self.name, self.dba) if n)


@dataclass(frozen=True)
class Match:
    """Where a reporter was found, and on what evidence."""

    tier: str
    evidence: str


class CatalogIndex:
    """Name, domain, and token views of one catalogue, built once and reused."""

    def __init__(self, records: list[FeedRecord], *, label: str) -> None:
        self.label = label
        self._exact: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._tokens: dict[str, list[tuple[str, frozenset[str]]]] = defaultdict(list)
        self._token_counts: dict[str, Counter[str]] = defaultdict(Counter)
        self._domains: dict[str, set[str]] = defaultdict(set)
        for record in records:
            normalized = normalize_name(record.name)
            if normalized:
                self._exact[(record.state, normalized)].append(record.key)
            tokens = name_tokens(record.name)
            if tokens:
                self._tokens[record.state].append((record.key, tokens))
                self._token_counts[record.state].update(tokens)
            for url in record.urls:
                host = registrable_host(url)
                if host:
                    self._domains[host].add(record.key)
        self._shared_hosts = {
            host for host, keys in self._domains.items() if len(keys) > SHARED_HOST_RECORDS
        }

    @property
    def shared_hosts(self) -> frozenset[str]:
        """Hosts serving too many records to identify any one of them."""
        return frozenset(self._shared_hosts)

    def exact_name(self, reporter: Reporter) -> str | None:
        for name in reporter.names:
            normalized = normalize_name(name)
            if normalized:
                keys = self._exact.get((reporter.state, normalized))
                if keys:
                    return ",".join(sorted(keys))
        return None

    def domain(self, reporter: Reporter) -> str | None:
        host = registrable_host(reporter.url)
        if not host or host in self._shared_hosts:
            return None
        keys = self._domains.get(host)
        return ",".join(sorted(keys)) if keys else None

    def fuzzy_name(self, reporter: Reporter) -> str | None:
        wanted: set[str] = set()
        for name in reporter.names:
            wanted |= name_tokens(name)
        if not wanted:
            return None
        best: tuple[str, float] | None = None
        for key, tokens in self._tokens.get(reporter.state, ()):
            union = wanted | tokens
            score = len(wanted & tokens) / len(union) if union else 0.0
            if score >= FUZZY_NAME_THRESHOLD and (best is None or score > best[1]):
                best = (key, score)
        return f"{best[0]} (jaccard {best[1]:.2f})" if best else None

    def shared_token(self, reporter: Reporter) -> str | None:
        """Weak evidence: a long, locally rare token both names carry.

        This is where "Sitka Tribe of Alaska" finds "RIDE Sitka". It is also
        where a placename shared by two unrelated operators produces a wrong
        candidate, which is why it is reported as its own tier and never folded
        into the strong count.
        """
        wanted: set[str] = set()
        for name in reporter.names:
            wanted |= name_tokens(name)
        counts = self._token_counts.get(reporter.state, Counter())
        rare = {
            token
            for token in wanted
            if len(token) >= MIN_TOKEN_LENGTH and 1 <= counts.get(token, 0) <= MAX_TOKEN_RECORDS
        }
        if not rare:
            return None
        keys = sorted(
            {key for key, tokens in self._tokens.get(reporter.state, ()) if tokens & rare}
        )
        return ",".join(keys) if keys else None


def obligated_reporters(
    roster: list[dict[str, str]],
    service_by_mode: list[dict[str, str]],
    *,
    report_year: str,
) -> list[Reporter]:
    """Roster rows for reporters running at least one fixed-route mode.

    `roster` is the Agency Information table and `service_by_mode` is the
    Service (by Mode) table; both are keyed by the five-character NTD ID, which
    is a zero-padded string and sometimes alphanumeric ("A0015", "03R06"). It is
    never an integer. A roster carrying several rows for one ID (division and
    department rows) contributes the first row only.
    """
    in_scope = {
        row.get("NTD ID", "").strip()
        for row in service_by_mode
        if row.get("Report Year", "").strip() == report_year
        and row.get("Mode", "").strip() in FIXED_ROUTE_MODES
    }
    in_scope.discard("")
    seen: set[str] = set()
    out: list[Reporter] = []
    for row in roster:
        ntd_id = row.get("NTD ID", "").strip()
        if ntd_id not in in_scope or ntd_id in seen:
            continue
        seen.add(ntd_id)
        out.append(
            Reporter(
                ntd_id=ntd_id,
                name=row.get("Agency Name", "").strip(),
                dba=row.get("Doing Business As", "").strip(),
                state=row.get("State", "").strip().upper(),
                reporter_type=row.get("Reporter Type", "").strip(),
                organization_type=row.get("Organization Type", "").strip(),
                url=row.get("URL", "").strip(),
            )
        )
    return sorted(out, key=lambda r: r.ntd_id)


def classify(
    reporter: Reporter,
    *,
    registry_by_ntd_id: dict[str, list[str]],
    registry: CatalogIndex,
    atlas_ntd_ids: frozenset[str],
    catalog: CatalogIndex,
) -> Match:
    """Place one reporter in the strongest tier its evidence supports."""
    keys = registry_by_ntd_id.get(reporter.ntd_id)
    if keys:
        return Match("registry_ntd_id", "registry:" + ",".join(sorted(keys)))
    for tier, found in (
        ("registry_name_exact", registry.exact_name(reporter)),
        ("registry_domain", registry.domain(reporter)),
        ("registry_name_fuzzy", registry.fuzzy_name(reporter)),
    ):
        if found:
            return Match(tier, "registry:" + found)
    if reporter.ntd_id in atlas_ntd_ids:
        return Match("atlas_ntd_id", "transitland-atlas")
    for tier, found in (
        ("catalog_name_exact", catalog.exact_name(reporter)),
        ("catalog_domain", catalog.domain(reporter)),
        ("catalog_name_fuzzy", catalog.fuzzy_name(reporter)),
    ):
        if found:
            return Match(tier, f"{catalog.label}:{found}")
    for source in (registry, catalog):
        found = source.shared_token(reporter)
        if found:
            return Match("weak_shared_token", f"{source.label}:{found}")
    return Match("no_candidate", "")


def atlas_ntd_ids_with_a_feed(docs: list[dict[str, Any]]) -> frozenset[str]:
    """NTD IDs the Transitland Atlas ties to an operator that has a static feed.

    Unlike `ntd_crosswalk.build_index`, a comma-joined `us_ntd_id` tag is split
    rather than dropped. Dropping it is right when stamping one ID onto one feed
    record; here the question is only whether SOME feed exists for a reporter,
    and every ID in a joint tag has one.
    """
    feed_urls: dict[str, str] = {}
    for doc in docs:
        for feed in doc.get("feeds", []) or []:
            osid = feed.get("id")
            static = (feed.get("urls") or {}).get("static_current")
            if osid and static:
                feed_urls[str(osid)] = str(static)
    found: set[str] = set()
    for doc in docs:
        for operator in doc.get("operators", []) or []:
            raw = str((operator.get("tags") or {}).get("us_ntd_id") or "").strip()
            if not raw:
                continue
            associated = operator.get("associated_feeds", []) or []
            if not any(feed_urls.get(str(a.get("feed_onestop_id"))) for a in associated):
                continue
            for piece in raw.replace(";", ",").split(","):
                if piece.strip():
                    found.add(piece.strip())
    return frozenset(found)


@dataclass(frozen=True)
class Coverage:
    """The counts, with the weak tier kept separable on purpose."""

    report_year: str
    obligated: int
    by_tier: dict[str, int] = field(default_factory=dict)

    @property
    def tracked_by_registry(self) -> int:
        return sum(self.by_tier.get(tier, 0) for tier in TRACKED_BY_US_TIERS)

    @property
    def discoverable_elsewhere(self) -> int:
        return sum(self.by_tier.get(tier, 0) for tier in STRONG_TIERS - TRACKED_BY_US_TIERS)

    @property
    def no_candidate_strict(self) -> int:
        """Counting only strong evidence as a match: the upper bound."""
        return self.obligated - sum(self.by_tier.get(tier, 0) for tier in STRONG_TIERS)

    @property
    def no_candidate_lenient(self) -> int:
        """Counting weak name overlap as a match too: the lower bound."""
        return self.by_tier.get("no_candidate", 0)


def summarize(matches: list[Match], *, report_year: str, obligated: int) -> Coverage:
    counts = Counter(match.tier for match in matches)
    return Coverage(
        report_year=report_year,
        obligated=obligated,
        by_tier={tier: counts.get(tier, 0) for tier in TIER_ORDER},
    )


# --- publishing the committed snapshot ---------------------------------------

#: Where the committed reporter-coverage snapshot lives, and the unit it must
#: declare. `data/ntd/PROVENANCE.md` records the sources, their retrieval date
#: and their terms.
SNAPSHOT_NAME = "reporter-coverage-ry2024.json"

#: The only unit these counts may carry. The registry counts feed records, which
#: is a different unit, and the two must never be added or compared as though
#: they were the same thing.
REPORTER_UNIT = "ntd_reporters"


def snapshot_path() -> Path:
    """The committed snapshot's path under the repository root."""
    from .config import repo_root

    return repo_root() / "data" / "ntd" / SNAPSHOT_NAME


def published_reporter_coverage(path: Path | None = None) -> dict[str, Any] | None:
    """The committed reporter counts, or None when they cannot be trusted.

    Fails closed on every disagreement rather than publishing a number that
    does not reconcile:

    * a missing or unreadable snapshot publishes nothing;
    * a snapshot that does not declare `unit: ntd_reporters` publishes nothing,
      so a feed-record count can never be rendered under a reporter label;
    * tier counts that do not sum to the stated obligated population publish
      nothing, because then no denominator on the page would be the real one.

    Returning None is the honest outcome: the page keeps its existing
    tracked-feed measurement and says nothing about reporters at all.
    """
    source = path if path is not None else snapshot_path()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("unit") != REPORTER_UNIT:
        return None

    obligated = payload.get("obligated_reporters")
    by_tier = payload.get("by_tier")
    if not _is_count(obligated) or not isinstance(by_tier, dict):
        return None
    if sorted(by_tier) != sorted(TIER_ORDER):
        return None
    if not all(_is_count(count) for count in by_tier.values()):
        return None
    if sum(by_tier.values()) != obligated:
        return None

    # The section dates its own denominator -- "Report Year {year}, retrieved
    # {date}" -- and that sentence is what lets a reader judge how old the 1,253
    # is. Rendered from an absent field it reads "Report Year , retrieved ",
    # which is a provenance claim with nothing behind it sitting beside real
    # counts. Same rule as the tiers: if the snapshot cannot say when it is
    # from, the section does not render.
    report_year = str(payload.get("report_year") or "").strip()
    retrieved_utc = str(payload.get("retrieved_utc") or "").strip()
    if not report_year or len(retrieved_utc) < len("YYYY-MM-DD"):
        return None

    tracked = sum(by_tier[tier] for tier in TRACKED_BY_US_TIERS)
    elsewhere = sum(by_tier[tier] for tier in STRONG_TIERS - TRACKED_BY_US_TIERS)
    return {
        "unit": REPORTER_UNIT,
        "report_year": report_year,
        "retrieved_utc": retrieved_utc,
        "obligated_reporters": obligated,
        "tracked_by_registry": tracked,
        "discoverable_elsewhere": elsewhere,
        # The two ends of the same honest range: the low end counts a shared
        # rare word as a match, the high end does not. The distance between them
        # is the width of a name-based join, and it is wide.
        "no_discoverable_feed_low": by_tier["no_candidate"],
        "no_discoverable_feed_high": obligated - sum(by_tier[tier] for tier in STRONG_TIERS),
        "needs_human_review": by_tier["weak_shared_token"],
        "by_tier": dict(by_tier),
    }


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
