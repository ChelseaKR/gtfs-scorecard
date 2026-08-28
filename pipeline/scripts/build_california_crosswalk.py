#!/usr/bin/env python3
"""Rebuild the California registry / Caltrans report-directory crosswalk.

Reads the committed directory snapshot at ``data/caltrans-report-directory.json``
and the California registry records, applies the matching rules described in
``docs/california-reconciliation.md``, layers the curator decisions in
``CURATED`` below, and writes ``data/california-caltrans-crosswalk.yaml``.

The rules run strongest first and stop at the first one that fires:

``feed_url``            the registry feed URL is one of the URLs that agency's
                        own Caltrans report lists. No judgment involved.
``org_name``            the registry name equals the Caltrans organization name
                        once case, punctuation, and parentheses are removed.
``place_name``          a place or brand word shared by both names picks out
                        exactly one organization in their directory.
``source_url_token``    a hostname label shared by the registry feed URL and a
                        feed URL in their report picks out exactly one
                        organization. This is what links a service brand to the
                        body that runs it.
``curated``             a reviewer recorded the decision by hand, with a reason.

Anything left over is ``uncertain`` (a candidate exists but the evidence does
not single one out) or ``absent`` (no candidate at all). Neither is a failure,
and neither is written as a match.

Run from the repository root:

    uv run --project pipeline python pipeline/scripts/build_california_crosswalk.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "data" / "caltrans-report-directory.json"
OUT = REPO_ROOT / "data" / "california-caltrans-crosswalk.yaml"

# Curator decisions, each with the reason it was made. These override the
# mechanical rules. A service brand and the body that runs it rarely share a
# name, so most of these record an operating relationship a string comparison
# cannot see. `null` means "reviewed, and not in their directory".
CURATED: dict[str, tuple[int | None, str]] = {
    "bay-area-rapid-transit-bart": (279, "BART is the district's operating brand"),
    "caltrain": (246, "Caltrain is the Peninsula Corridor Joint Powers Board's service"),
    "golden-gate-transit": (
        127,
        "Golden Gate Transit is the bridge district's bus service",
    ),
    "marin-transit": (194, "Marin Transit is the county transit district's brand"),
    "marin-transit-2937": (194, "second feed record for the same county transit district"),
    "sonoma-marin-area-rail-transit-smart": (315, "SMART is the rail district's brand"),
    "sonoma-county-transit-sct": (314, "Sonoma County Transit is the county's own service"),
    "sacramento-regional-transit-sacrt": (273, "SacRT is the district's brand"),
    "sacramento-regional-transit-sacrt-2137": (273, "second feed record for SacRT"),
    "westcat": (368, "WestCAT is Western Contra Costa Transit Authority's brand"),
    "city-coach": (356, "City Coach is the City of Vacaville's service"),
    "soltrans": (310, "SolTrans is Solano County Transit"),
    "vine-transit": (218, "VINE is the Napa Valley Transportation Authority's brand"),
    "county-connection-cccta": (61, "County Connection is CCCTA's brand"),
    "tri-delta-transit": (336, "Tri Delta Transit is Eastern Contra Costa Transit Authority"),
    "san-francisco-municipal-transportation-agency-sfmta-muni": (
        282,
        "Muni is run by the City and County of San Francisco",
    ),
    "san-francisco-municipal-transportation-agency-sfmta-muni-2886": (
        282,
        "second feed record for Muni",
    ),
    "go-west-shuttle": (366, "Go West is the City of West Covina's shuttle"),
    "altamont-corridor-express": (
        10,
        "ACE is the San Joaquin Regional Rail Commission's service",
    ),
    "commute-org-san-mateo-county-shuttles": (76, "Commute.org runs the shuttles"),
    "samtrans": (290, "second feed record for the San Mateo County Transit District"),
    "santa-ynez-valley-transit": (
        312,
        "their report lists the same syvt feed under the City of Solvang",
    ),
    "south-county-transit-link": (
        81,
        "SCT Link is Sacramento County's service; their report lists the same SCTLink feed",
    ),
    "south-county-transit-link-2203": (81, "second feed record for Sacramento County SCT Link"),
    "city-of-san-luis-obispo-transit": (
        287,
        "SLO Transit is the City of San Luis Obispo's service",
    ),
    "tehama-rural-area-express-trax-susanville-indian-rancheria-public-transportation-program": (
        334,
        "TRAX is Tehama County's service",
    ),
    "humboldt-transit-authority-3032": (
        135,
        "their report lists this Optibus feed for the authority and for two member cities",
    ),
    "gtrans": (118, "GTrans is the City of Gardena's service"),
    "santa-cruz-metro-scmtd": (296, "Santa Cruz METRO is the district's brand"),
    "santa-cruz-metro-scmtd-2425": (296, "second feed record for Santa Cruz METRO"),
    "mountain-transit": (214, "Mountain Transit is Mountain Area Regional Transit Authority"),
    "gold-coast-transit-south-coast-area-transit": (123, "Gold Coast Transit District"),
    "mountain-view-community-shuttle": (
        None,
        "the City of Mountain View is not in their directory",
    ),
    "mountain-view-transportation-management-association-mvgo": (
        None,
        "the Mountain View TMA is not in their directory",
    ),
    "mountain-view-transportation-management-association-mvgo-2025": (
        None,
        "the Mountain View TMA is not in their directory",
    ),
    "mountain-view-transportation-management-association-mvgo-2880": (
        None,
        "the Mountain View TMA is not in their directory",
    ),
    "sierra-madre-gateway-coach": (None, "the City of Sierra Madre is not in their directory"),
    "sierra-madre-gateway-coach-2251": (
        None,
        "the City of Sierra Madre is not in their directory",
    ),
    "sonoma-county-airport-express": (
        None,
        "a private airport shuttle; not in their directory",
    ),
    "airport-valet-express": (None, "a private airport shuttle; not in their directory"),
    "alcatraz-cruises-hornblower-angel-island-tiburon-ferry-blue-gold-fleet": (
        None,
        "bay ferry concessions; not in their directory",
    ),
    "blue-gold-fleet": (None, "a bay ferry operator; not in their directory"),
    "mariposa-grove-shuttle": (None, "a National Park Service shuttle; not in their directory"),
    "playa-vista-shuttle": (None, "a private development shuttle; not in their directory"),
    "spirit-bus": (207, "Spirit Bus is the City of Monterey Park's service"),
    "san-leandro-links": (None, "the City of San Leandro is not in their directory"),
    "morro-bay-transit": (None, "the City of Morro Bay is not in their directory"),
    "morro-bay-transit-2059": (None, "the City of Morro Bay is not in their directory"),
    "mission-bay-transportation-management-association-tma": (
        None,
        "the Mission Bay TMA is not in their directory",
    ),
    "rosemead-explorer": (None, "the City of Rosemead is not in their directory"),
    "rosemead-explorer-3098": (None, "the City of Rosemead is not in their directory"),
    "get-around-town-express": (None, "the operator is not in their directory"),
    "west-berkeley-shuttle": (None, "the West Berkeley Shuttle is not in their directory"),
    "stanford-marguerite-shuttle-sms": (None, "Stanford University is not in their directory"),
    "keep-tahoe-blue": (None, "the Emerald Bay Shuttle operator is not in their directory"),
    "regional-transportation-commission-of-southern-nevada-rtc": (
        None,
        "this is a Nevada operator; it is in the California shard by mistake",
    ),
}

# Reviewed as uncertain: a plausible organization exists but the evidence does
# not single it out, so the crosswalk records the doubt instead of a match.
CURATED_UNCERTAIN: dict[str, str] = {
    "amtrak-san-joaquins": (
        "their directory carries Amtrak with the national feed; whether the "
        "state-supported San Joaquins corridor is meant to sit under it is unclear"
    ),
    "tideline-water-taxi": (
        "a private water-taxi operator; their directory has no matching entry, and "
        "the Water Emergency Transportation Authority is a different operator"
    ),
    "yosemite-valley-shuttle": (
        "the in-park shuttle is run by the National Park Service, not by YARTS, "
        "and their directory has no separate entry for it"
    ),
    "the-santa-cruzer": (
        "the City of Santa Cruz is not listed separately; this may sit under "
        "Santa Cruz Metropolitan Transit District"
    ),
    "modesto-area-express": (
        "Modesto Area Express consolidated into the Stanislaus Regional Transit "
        "Authority; their directory carries the authority but no City of Modesto"
    ),
}

ORG_WORDS = {
    "city",
    "county",
    "of",
    "the",
    "transit",
    "transportation",
    "authority",
    "agency",
    "district",
    "regional",
    "area",
    "system",
    "systems",
    "service",
    "services",
    "bus",
    "lines",
    "joint",
    "powers",
    "board",
    "commission",
    "association",
    "governments",
    "department",
    "public",
    "works",
    "and",
    "municipal",
    "rural",
    "council",
    "inc",
    "valley",
    "line",
    "express",
    "shuttle",
    "trolley",
    "link",
    "connects",
    "connection",
    "metropolitan",
    "corridor",
    "national",
    "monument",
    "california",
    "university",
    "for",
    "local",
    "rapid",
    "coach",
    "center",
    "community",
    "free",
    "weekend",
    "town",
}
URL_NOISE = {
    "gtfs",
    "ca",
    "us",
    "zip",
    "google",
    "transit",
    "data",
    "public",
    "feed",
    "feeds",
    "download",
    "latest",
    "static",
    "com",
    "org",
    "gov",
    "net",
    "www",
    "documentcenter",
    "view",
    "files",
    "resource",
    "utility",
    "rtt",
    "master",
    "main",
    "raw",
    "flex",
    "v1",
    "v2",
    "preview",
    "schedule",
    "realtime",
    "api",
    "current",
    "prod",
    "production",
}
HOST_NOISE = {
    "www",
    "com",
    "org",
    "net",
    "gov",
    "edu",
    "info",
    "app",
    "apps",
    "web",
    "data",
    "gtfs",
    "api",
    "cdn",
    "transit",
    "public",
    "portal",
    "ride",
    "bus",
    "the",
    "and",
    "city",
    "county",
    "http",
    "https",
    "amazonaws",
    "azurewebsites",
    "core",
    "windows",
    "githubusercontent",
    "raw",
    "files",
    "assets",
    "media",
    "documents",
    "site",
    "sites",
    "west",
    "east",
    "north",
    "south",
    "central",
    "area",
    "regional",
    "rider",
    "riders",
    "schedule",
    "shuttle",
    "hosted",
    "feeds",
    "gtfsrealtime",
    "staticgtfs",
    "google",
}
# Landscape words show up in unrelated agency names all over the state, so one
# of them on its own ("mountain", "airport", "sierra") is not an identification.
# A match on this tier needs at least one shared word from outside this set.
GENERIC_PLACE = {
    "mountain",
    "mountains",
    "airport",
    "beach",
    "beaches",
    "bay",
    "lake",
    "tahoe",
    "river",
    "sierra",
    "gold",
    "golden",
    "blue",
    "green",
    "red",
    "reds",
    "park",
    "coast",
    "coastal",
    "harbor",
    "island",
    "hill",
    "hills",
    "springs",
    "creek",
    "grove",
    "ridge",
    "vista",
    "delta",
    "canyon",
    "mesa",
    "point",
    "port",
    "gateway",
    "summit",
    "star",
    "sun",
    "desert",
    "forest",
    "metro",
    "resort",
    "grand",
    "royal",
    "cruz",
    "santa",
    "san",
    "los",
    "county",
    "big",
    "little",
    "upper",
    "lower",
    "downtown",
    "campus",
    "college",
    "school",
    "medical",
    "airporter",
    "ferry",
    "water",
    "yosemite",
    "sequoia",
    "national",
    "state",
    "shuttle",
    "trolley",
}

# Hosts that carry many operators' feeds, so sharing one proves nothing.
SHARED_HOSTS = {
    "api.511.org",
    "data.trilliumtransit.com",
    "gtfs.remix.com",
    "gtfs.calitp.org",
    "gtfs.dds.dot.ca.gov",
    "rapid.nationalrtap.org",
    "s3.amazonaws.com",
    "passio3.com",
    "app.mecatran.com",
    "www.ips-systems.com",
    "ips-systems.com",
    "data.peaktransit.com",
    "api.goswift.ly",
    "gitlab.com",
    "github.com",
    "raw.githubusercontent.com",
    "urldefense.com",
    "api.sparelabs.com",
    "transitfeeds.com",
    "iportal.sacrt.com",
}


def normalized_url(url: str) -> str:
    try:
        parsed = urlsplit((url or "").strip())
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    path = parsed.path.rstrip("/")
    return f"{host}{path}?{parsed.query}" if parsed.query else f"{host}{path}"


def hostname_of(url: str) -> str:
    try:
        return (urlsplit((url or "").strip()).hostname or "").lower()
    except ValueError:
        return ""


def words(text: str) -> list[str]:
    return [
        t
        for t in re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()
        if len(t) > 2 and not t.isdigit()
    ]


def flat_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", " ", (name or "").lower()))


def place_words(name: str) -> set[str]:
    return {t for t in words(re.sub(r"\(.*?\)", " ", name or "")) if t not in ORG_WORDS}


def url_words(url: str) -> set[str]:
    parsed = urlsplit((url or "").strip()) if url else None
    raw = f"{hostname_of(url)} {parsed.path if parsed else ''}"
    return {t for t in words(raw) if t not in URL_NOISE and t not in ORG_WORDS}


def host_labels(host: str) -> set[str]:
    return {
        t
        for t in re.split(r"[.-]+", (host or "").lower())
        if len(t) > 3 and t not in HOST_NOISE and not t.isdigit()
    }


def california_records() -> list[dict[str, Any]]:
    """Every California registry record, plus anything the California page lists.

    The page's cohort is the union of the California shard and the rollup's
    member list, so a record the page counts is reconciled even when it is
    still parked in another shard.
    """
    rollups = yaml.safe_load((REPO_ROOT / "rollups.yaml").read_text())["rollups"]
    members = set(next(r for r in rollups if r["id"] == "california").get("members", []))
    index = yaml.safe_load((REPO_ROOT / "registry" / "index.yaml").read_text())
    out: list[dict[str, Any]] = []
    for shard in index["shards"]:
        loaded = yaml.safe_load((REPO_ROOT / shard).read_text()) or {}
        for entry in loaded.get("agencies") or []:
            californian = entry.get("subdivision_code") == "US-CA"
            if californian or entry["id"] in members:
                out.append({**entry, "shard": shard, "on_california_page": entry["id"] in members})
    return sorted(out, key=lambda e: e["id"])


# (status, method, caltrans_id, evidence) for one registry record.
Decision = tuple[str, str, int | None, str]


def _curated_decision(agency_id: str) -> Decision | None:
    """A hand-reviewed answer, which outranks every derived one."""
    if agency_id in CURATED:
        caltrans_id, reason = CURATED[agency_id]
        status = "matched" if caltrans_id is not None else "absent"
        return status, "curated", caltrans_id, reason
    if agency_id in CURATED_UNCERTAIN:
        return "uncertain", "curated", None, CURATED_UNCERTAIN[agency_id]
    return None


def _feed_url_decision(directory: list[dict[str, Any]], feed_url: str) -> Decision | None:
    """The strongest derived signal: their own report lists this exact feed URL."""
    key = normalized_url(feed_url)
    hits = [a for a in directory if key and key in a["_urls"]]
    if len(hits) == 1:
        return "matched", "feed_url", hits[0]["caltrans_id"], "their report lists this feed URL"
    if len(hits) > 1:
        named = ", ".join(sorted(a["name"] for a in hits))
        return "uncertain", "feed_url", None, f"their reports list this feed URL under {named}"
    return None


def _org_name_decision(directory: list[dict[str, Any]], record: dict[str, Any]) -> Decision | None:
    """Exact organization-name agreement, flattened for punctuation and case."""
    exact = [a for a in directory if flat_name(a["name"]) == flat_name(record["name"])]
    if len(exact) == 1:
        return "matched", "org_name", exact[0]["caltrans_id"], "the organization names agree"
    return None


def _place_name_decision(
    directory: list[dict[str, Any]],
    record_words: set[str],
    org_word_owners: dict[str, set[int]],
) -> Decision | None:
    """A place word only one organization in their directory owns."""
    shared: dict[int, tuple[dict[str, Any], set[str]]] = {}
    for agency in directory:
        common = {w for w in record_words & agency["_words"] if len(org_word_owners[w]) == 1}
        if common and common - GENERIC_PLACE:
            shared[agency["caltrans_id"]] = (agency, common)
    if len(shared) == 1:
        agency, common = next(iter(shared.values()))
        return (
            "matched",
            "place_name",
            agency["caltrans_id"],
            f"shared name: {', '.join(sorted(common))}",
        )
    if len(shared) > 1:
        named = ", ".join(sorted(a["name"] for a, _ in shared.values()))
        return "uncertain", "place_name", None, f"the name fits more than one of them: {named}"
    return None


def _host_decision(
    directory: list[dict[str, Any]],
    record: dict[str, Any],
    feed_url: str,
    host_owners: dict[str, set[int]],
) -> Decision | None:
    """A feed hostname label only one organization publishes under."""
    brand: dict[int, tuple[dict[str, Any], set[str]]] = {}
    host = hostname_of(feed_url)
    labels = place_words(record["name"])
    if host not in SHARED_HOSTS:
        labels |= host_labels(host)
    for agency in directory:
        common = {w for w in labels & agency["_hosts"] if len(host_owners[w]) == 1}
        if common:
            brand[agency["caltrans_id"]] = (agency, common)
    if len(brand) == 1:
        agency, common = next(iter(brand.values()))
        return (
            "matched",
            "source_url_token",
            agency["caltrans_id"],
            f"shared feed hostname: {', '.join(sorted(common))}",
        )
    if len(brand) > 1:
        named = ", ".join(sorted(a["name"] for a, _ in brand.values()))
        return "uncertain", "source_url_token", None, f"the feed host fits {named}"
    return None


def decide(
    record: dict[str, Any],
    directory: list[dict[str, Any]],
    org_word_owners: dict[str, set[int]],
    host_owners: dict[str, set[int]],
) -> Decision:
    """Return (status, method, caltrans_id, evidence) for one registry record.

    The strategies are tried in descending order of evidence strength and the
    first one with an answer wins. Each is its own function so the cascade
    reads as the ordered policy it is; the order and every returned tuple are
    unchanged from when this was one body.
    """
    feed_url = record.get("static_gtfs_url", "")
    record_words = place_words(record["name"]) | url_words(feed_url)
    # Lazily, so a curated answer still costs nothing and no later strategy
    # touches a record the cascade would never have reached.
    strategies: tuple[Callable[[], Decision | None], ...] = (
        lambda: _curated_decision(record["id"]),
        lambda: _feed_url_decision(directory, feed_url),
        lambda: _org_name_decision(directory, record),
        lambda: _place_name_decision(directory, record_words, org_word_owners),
        lambda: _host_decision(directory, record, feed_url, host_owners),
    )
    for strategy in strategies:
        result = strategy()
        if result is not None:
            return result

    loose = [a for a in directory if record_words & a["_words"]]
    if loose:
        named = ", ".join(sorted(a["name"] for a in loose)[:3])
        return "uncertain", "name_overlap", None, f"only a partial name overlap, nearest: {named}"
    return "absent", "no_candidate", None, "no organization in their directory shares a name"


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text())
    directory = snapshot["agencies"]
    for agency in directory:
        agency["_urls"] = {normalized_url(u) for urls in agency["feeds"].values() for u in urls} - {
            ""
        }
        agency["_words"] = place_words(agency["name"])
        agency["_hosts"] = set()
        for urls in agency["feeds"].values():
            for url in urls:
                host = hostname_of(url)
                if host not in SHARED_HOSTS:
                    agency["_hosts"] |= host_labels(host)

    org_word_owners: dict[str, set[int]] = defaultdict(set)
    host_owners: dict[str, set[int]] = defaultdict(set)
    for agency in directory:
        for word in agency["_words"]:
            org_word_owners[word].add(agency["caltrans_id"])
        for label in agency["_hosts"]:
            host_owners[label].add(agency["caltrans_id"])

    by_id = {a["caltrans_id"]: a for a in directory}
    entries = []
    for record in california_records():
        status, method, caltrans_id, evidence = decide(
            record, directory, org_word_owners, host_owners
        )
        entry: dict[str, Any] = {
            "id": record["id"],
            "name": record["name"],
            "status": status,
            "method": method,
            "evidence": evidence,
        }
        if caltrans_id is not None:
            entry["caltrans_id"] = caltrans_id
            entry["caltrans_name"] = by_id[caltrans_id]["name"]
        entries.append(entry)

    matched_orgs = sorted({e["caltrans_id"] for e in entries if "caltrans_id" in e})
    absent_from_registry = [
        {"caltrans_id": a["caltrans_id"], "name": a["name"], "report_url": a["report_url"]}
        for a in directory
        if a["caltrans_id"] not in set(matched_orgs)
    ]
    counts = Counter(e["status"] for e in entries)
    payload = {
        "schema_version": "1.0",
        "directory_source": snapshot["source_url"],
        "directory_month": snapshot["report_month"],
        "directory_retrieved_on": snapshot["retrieved_on"],
        "registry_records": len(entries),
        "matched_records": counts["matched"],
        "uncertain_records": counts["uncertain"],
        "absent_records": counts["absent"],
        "directory_agencies": len(directory),
        "matched_directory_agencies": len(matched_orgs),
        "records": entries,
        "directory_only": absent_from_registry,
    }
    header = (
        "# California registry / Caltrans report-directory crosswalk.\n"
        "#\n"
        "# Generated by pipeline/scripts/build_california_crosswalk.py from the\n"
        "# committed directory snapshot in data/caltrans-report-directory.json.\n"
        "# The method, including how a match is confirmed and when one is left\n"
        "# uncertain, is written up in docs/california-reconciliation.md.\n"
        "#\n"
        "# Do not hand-edit: record a curator decision in the script's CURATED\n"
        "# table, with its reason, and regenerate.\n"
    )
    OUT.write_text(header + yaml.safe_dump(payload, sort_keys=False, width=100))
    print(
        f"{len(entries)} California registry records: "
        f"{counts['matched']} matched, {counts['uncertain']} uncertain, {counts['absent']} absent"
    )
    print(
        f"{len(matched_orgs)} of {len(directory)} organizations in their directory "
        f"are matched to a registry record"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
