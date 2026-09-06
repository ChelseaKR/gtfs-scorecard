"""Producing-tool profiles: who actually makes a GTFS fix.

The scorecard's fixes say what to change. For a small agency the harder question
is often who changes it, because most small agencies do not run their own export.
This module answers that with a short profile of how a fix lands at each tool the
registry sees at scale, so fix surfaces can name the actual next step ("send this
to your Trillium contact") instead of the generic "check your export settings"
(docs/RESEARCH-ROADMAP.md R5).

Hosting is not producing. An earlier version of this module read the producing
tool off the host serving the zip, which credited every feed on a vendor's
delivery host to that vendor. That is wrong for real feeds in this registry:
``data.trilliumtransit.com`` serves feeds whose own ``feed_info.txt`` names GMV
Syncromatics as publisher, and every ``rapid.nationalrtap.org`` feed URL sits
under ``/GTFSFileManagement/UserUploadFiles/``, a file-upload path that carries
whatever an agency uploaded, including a feed published by Connexionz. Handing
those agencies a fix request addressed to Trillium or to National RTAP's GTFS
Builder sends the one email a manager sends to a company that cannot act on it.

So the producer comes from the feed's own declaration first. ``feed_info.txt``
carries ``feed_publisher_name`` and ``feed_publisher_url``, which is the
publisher's statement about itself, written by whatever wrote the feed. Those
declarations are read into ``data/feed-publishers.json`` by
``pipeline/scripts/fetch_feed_publishers.py`` and consulted here. The host is
used only where the URL is a tool's own generated-export endpoint, and never
where it is a hosting or upload service.

Detection stays deliberately conservative in both directions. When the evidence
names a producer this module has no documented fix path for, it returns None
rather than falling back to the host, and the fix surfaces keep their generic
"whoever runs your scheduling software export" wording. An honest unknown is
better than a confident wrong name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from .config import repo_root

# How a fix reaches the published feed, per tool.
#   hosted    — a service produces and hosts the feed; the agency asks them.
#   self_edit — the agency's own staff edit in the tool and re-export.
#   repo      — the feed is regenerated and committed by a repo maintainer.
#   archive   — the URL serves an unmaintained archive copy; fixing any single
#               finding matters less than publishing from a live URL.
KINDS = ("hosted", "self_edit", "repo", "archive")

# What a host match is evidence of.
#   produces — the URL is the tool's own generated-export endpoint, so serving a
#              feed from it means the tool wrote those bytes.
#   serves   — the URL is a hosting or file-upload service. It carries feeds the
#              host did not build, so it is no evidence of a producing tool.
#   route    — the URL describes how the feed is published (a repository, an
#              archive) and names no organization as its producer.
HOST_EVIDENCE = ("produces", "serves", "route")


@dataclass(frozen=True)
class ToolProfile:
    """One producing tool the registry sees at scale, or a publishing route."""

    key: str
    name: str
    kind: str
    # One or two plain sentences for the agency page: who makes the change and
    # where. Written to the agency reader, never as blame.
    fix_path: str
    # The lede for the forwardable fix-request block, replacing the generic
    # "whoever runs your scheduling software export" copy.
    request_lede: str


_TRILLIUM = ToolProfile(
    key="trillium",
    name="Trillium",
    kind="hosted",
    fix_path=(
        "Trillium produces and hosts this feed as a service. These changes are "
        "made on their side: send the fix list to your Trillium contact and they "
        "apply it and republish."
    ),
    request_lede=(
        "This feed is produced and hosted by Trillium. Copy this and send it to "
        "your Trillium contact; they make the change and republish the feed."
    ),
)

_GTFS_BUILDER = ToolProfile(
    key="gtfs_builder",
    name="National RTAP GTFS Builder",
    kind="self_edit",
    fix_path=(
        "This feed is built with National RTAP's GTFS Builder. Your staff can "
        "usually make these changes in the GTFS Builder spreadsheets and "
        "republish, and National RTAP's help desk supports that at no cost."
    ),
    request_lede=(
        "This feed comes from National RTAP's GTFS Builder, so your own staff can "
        "usually make these changes in the GTFS Builder spreadsheets and "
        "republish. If a consultant maintains it for you, forward this to them."
    ),
)

_REMIX = ToolProfile(
    key="remix",
    name="Remix",
    kind="self_edit",
    fix_path=(
        "This feed is exported from Remix. The change happens in your Remix "
        "workspace; once your planners update the data there, the published "
        "export picks it up."
    ),
    request_lede=(
        "This feed is exported from Remix. If your planners work in Remix, the "
        "change happens in your own workspace; otherwise forward this to whoever "
        "maintains your Remix data."
    ),
)

_PASSIO = ToolProfile(
    key="passio",
    name="Passio",
    kind="hosted",
    fix_path=(
        "This feed is generated by your Passio system from the route and stop "
        "data they maintain. Send the fix list to your Passio contact."
    ),
    request_lede=(
        "This feed is generated by your Passio system. Copy this and send it to "
        "your Passio contact; the fixes apply to the route and stop data behind "
        "your AVL setup."
    ),
)

_REPO = ToolProfile(
    key="repo",
    name="a code repository",
    kind="repo",
    fix_path=(
        "This feed is published from a code repository, so whoever maintains "
        "that repository regenerates the zip — often planning staff or a "
        "consultant. The fix happens in the source data, then a fresh export is "
        "committed."
    ),
    request_lede=(
        "This feed is published from a code repository. Forward this to whoever "
        "maintains that repository; the fix happens in the source data, then a "
        "fresh export is committed."
    ),
)

_ARCHIVE = ToolProfile(
    key="archive",
    name="the TransitFeeds archive",
    kind="archive",
    fix_path=(
        "This feed URL points at the TransitFeeds archive, which is no longer "
        "maintained. Before any single fix, publish the feed from a live URL "
        "you control and update the listings that still point here."
    ),
    request_lede=(
        "This feed is served from the TransitFeeds archive, which is no longer "
        "maintained. The most useful request is publishing the current feed from "
        "a live URL, then these fixes."
    ),
)


@dataclass(frozen=True)
class _HostRule:
    """A host suffix, the profile it points at, and what the match proves."""

    profile: ToolProfile
    evidence: str


# Host suffix -> rule. Matching is suffix-based so vendor subdomains
# (oregon-gtfs.trilliumtransit.com) resolve without listing each one.
#
# trilliumtransit.com and rapid.nationalrtap.org are "serves", not "produces":
# both demonstrably carry feeds built by someone else, so the host alone must
# not name them. Their feeds are still attributed whenever the feed's own
# declaration names them, which in this registry is the common case.
_HOST_RULES: dict[str, _HostRule] = {
    "trilliumtransit.com": _HostRule(_TRILLIUM, "serves"),
    "rapid.nationalrtap.org": _HostRule(_GTFS_BUILDER, "serves"),
    "gtfs.remix.com": _HostRule(_REMIX, "produces"),
    "passio3.com": _HostRule(_PASSIO, "produces"),
    "github.com": _HostRule(_REPO, "route"),
    "githubusercontent.com": _HostRule(_REPO, "route"),
    "gitlab.com": _HostRule(_REPO, "route"),
    "transitfeeds.com": _HostRule(_ARCHIVE, "route"),
}


@dataclass(frozen=True)
class _Producer:
    """A producer this project can recognize in a feed's own declaration.

    ``profile`` is None for a producer with no documented fix path here. That is
    still useful evidence: it rules the host out, so the copy stays generic
    instead of naming a company that did not build the feed.
    """

    key: str
    profile: ToolProfile | None


_PRODUCERS: dict[str, _Producer] = {
    "trillium": _Producer("trillium", _TRILLIUM),
    "national_rtap": _Producer("national_rtap", _GTFS_BUILDER),
    "remix": _Producer("remix", _REMIX),
    "passio": _Producer("passio", _PASSIO),
    # Recognized in feed declarations in this registry, with no documented fix
    # path of their own. Naming them would be a guess; crediting the host that
    # serves their feeds would be wrong. Both resolve to generic copy.
    "gmv_syncromatics": _Producer("gmv_syncromatics", None),
    "connexionz": _Producer("connexionz", None),
    "optibus": _Producer("optibus", None),
    "mti_umd": _Producer("mti_umd", None),
}

# The host of a declared feed_publisher_url, matched by suffix. A publisher URL
# is the least ambiguous half of the declaration: it is a domain, not prose.
_PUBLISHER_URL_HOSTS: dict[str, str] = {
    "trilliumtransit.com": "trillium",
    "nationalrtap.org": "national_rtap",
    "remix.com": "remix",
    "passiotech.com": "passio",
    "passio3.com": "passio",
    "gmvsyncromatics.com": "gmv_syncromatics",
    "connexionz.com": "connexionz",
    "connexionz.co.nz": "connexionz",
    "optibus.com": "optibus",
    "mti.umd.edu": "mti_umd",
}

# A declared feed_publisher_name, lowercased and stripped of trailing company
# suffixes, matched exactly. Exact matching on purpose: an agency named after
# its region must never collide with a vendor by substring.
_PUBLISHER_NAMES: dict[str, str] = {
    "trillium solutions": "trillium",
    "trillium transit": "trillium",
    "trillium": "trillium",
    "national rtap": "national_rtap",
    "remix": "remix",
    "remix software": "remix",
    "passio technologies": "passio",
    "passio": "passio",
    "gmv syncromatics": "gmv_syncromatics",
    "syncromatics": "gmv_syncromatics",
    "connexionz": "connexionz",
    "optibus": "optibus",
    "mti umd": "mti_umd",
}

_NAME_SUFFIXES = (
    " inc",
    " inc.",
    " llc",
    " llc.",
    " ltd",
    " ltd.",
    " limited",
    " corp",
    " corp.",
    " co",
    " co.",
)

_SNAPSHOT = Path("data") / "feed-publishers.json"


#: Every producing-tool profile, by its key. ``detect_tool`` answers from a feed
#: URL; a caller who already knows which tool an agency uses (the MCP server's
#: ``explain_finding``, say) needs the same guidance without one. An unknown key
#: returns None rather than the nearest match: naming the wrong vendor in a fix
#: path is worse than being generic.
PROFILES_BY_KEY: dict[str, ToolProfile] = {
    profile.key: profile for profile in (_TRILLIUM, _GTFS_BUILDER, _REMIX, _PASSIO, _REPO, _ARCHIVE)
}


def profile_for_key(key: str) -> ToolProfile | None:
    """The tool profile for a key, or None when the key is not one we profile."""
    return PROFILES_BY_KEY.get(str(key).strip().casefold())


def _host(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    netloc = netloc.split("@")[-1].split(":")[0]
    return netloc.removeprefix("www.")


def _suffix_match(host: str, table: dict[str, str]) -> str | None:
    for suffix, key in table.items():
        if host == suffix or host.endswith("." + suffix):
            return key
    return None


def _normalized_publisher_name(name: str) -> str:
    text = " ".join(name.lower().replace(",", " ").split())
    changed = True
    while changed:
        changed = False
        for suffix in _NAME_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                changed = True
    return text


def _declared_producer(publisher_name: str | None, publisher_url: str | None) -> _Producer | None:
    """The producer a feed's own feed_info.txt declaration names, if recognized.

    Both halves are read. When each resolves to a different producer the
    declaration contradicts itself and no producer is returned, so the copy
    stays generic rather than picking a side. A declaration naming the agency
    itself resolves to nothing, which is correct: most tools write the agency
    into feed_publisher_name, so that is not evidence about the tool.
    """
    from_url = _suffix_match(_host(publisher_url), _PUBLISHER_URL_HOSTS) if publisher_url else None
    from_name = (
        _PUBLISHER_NAMES.get(_normalized_publisher_name(publisher_name)) if publisher_name else None
    )
    if from_url and from_name and from_url != from_name:
        return None
    key = from_url or from_name
    return _PRODUCERS.get(key) if key else None


@lru_cache(maxsize=4)
def _load_snapshot(path: Path) -> dict[str, tuple[str, str]]:
    """Declared publisher fields from a snapshot file, keyed by feed URL.

    Keyed by URL rather than by agency id so a moved feed simply has no
    evidence: the entry recorded against the old URL never speaks for the new
    one. A missing or unreadable snapshot is an empty index, and every feed
    falls back to what its host alone can prove.

    Cached on the path, not globally: a fork or a test can point
    ``SCORECARD_ROOT`` at another tree mid-process, and a single cached index
    would answer for whichever tree happened to be read first.
    """
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    index: dict[str, tuple[str, str]] = {}
    for record in (payload.get("feeds") or {}).values():
        url = str(record.get("url") or "")
        if not url:
            continue
        index[url] = (
            str(record.get("publisher_name") or ""),
            str(record.get("publisher_url") or ""),
        )
    return index


def _publisher_snapshot() -> dict[str, tuple[str, str]]:
    return _load_snapshot(repo_root() / _SNAPSHOT)


def _recorded_declaration(static_url: str) -> tuple[str, str] | None:
    index = _publisher_snapshot()
    if static_url in index:
        return index[static_url]
    # Registries and catalogs move a feed between http and https without the
    # bytes changing; the declaration read from one still describes the other.
    other = (
        static_url.replace("https://", "http://", 1)
        if static_url.startswith("https://")
        else static_url.replace("http://", "https://", 1)
    )
    return index.get(other)


def _host_rule(host: str) -> _HostRule | None:
    for suffix, rule in _HOST_RULES.items():
        if host == suffix or host.endswith("." + suffix):
            return rule
    return None


def _feed_declaration(
    url: str, publisher_name: str | None, publisher_url: str | None
) -> tuple[str, str] | None:
    """The declaration to judge this feed by: the caller's, else the snapshot's."""
    if publisher_name or publisher_url:
        return (publisher_name or "", publisher_url or "")
    return _recorded_declaration(url)


def detect_tool(
    static_url: str | None,
    *,
    publisher_name: str | None = None,
    publisher_url: str | None = None,
) -> ToolProfile | None:
    """The producing-tool profile for a feed, or None to keep copy generic.

    Evidence is read in this order:

    1. An archive URL is answered first. "Publish from a live URL you control"
       is a fact about the URL and stays true whoever built the bytes.
    2. The feed's own ``feed_info.txt`` publisher declaration, passed in or read
       from the committed snapshot. A producer with a documented fix path wins
       over the host.
    3. A publishing route (a code repository). It names no organization, so a
       producer this project has no profile for does not contradict it.
    4. A declaration naming somebody else rules the host out: no name at all
       beats the host's name on a feed the host did not build.
    5. The host, and only where the URL is a tool's own generated-export
       endpoint. A hosting or upload service proves nothing about the producer.

    Anything unresolved returns None and the fix surfaces keep their existing
    generic wording.
    """
    if not static_url:
        return None
    url = str(static_url)
    host = _host(url)
    if not host:
        return None
    rule = _host_rule(host)

    if rule is not None and rule.profile.kind == "archive":
        return rule.profile

    declaration = _feed_declaration(url, publisher_name, publisher_url)
    producer = _declared_producer(*declaration) if declaration is not None else None

    if producer is not None and producer.profile is not None:
        return producer.profile
    if rule is None:
        return None
    if rule.evidence == "route":
        return rule.profile
    if producer is not None:
        return None
    return rule.profile if rule.evidence == "produces" else None
