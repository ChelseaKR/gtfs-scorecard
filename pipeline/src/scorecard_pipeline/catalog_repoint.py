"""Follow a catalog retirement to a successor feed we do not track yet.

`find_supersessions` handles a retired record whose successor we already
publish: the retired record becomes an alias. It leaves the other case on a
list, "the successor record is not published here", and that list is where a
tracked agency's feed quietly went stale. The catalog has said where the
agency publishes now; the registry still requests the URL it retired.

This module reads the same redirect and proposes the other edit: keep the
tracked record (its id, its page, its history) and move its
``static_gtfs_url`` and ``mdb_id`` to the one current successor. It adds no
record and no page. It is the "URL rot repair" half of the coverage work in
ADR 0069.

A proposal is only made when all of these hold, and each refusal is reported
with its reason so a curator can act on it by hand:

- the redirect chain reaches exactly one current Schedule record;
- that record is open (no key), not marked unofficial, and has a usable URL;
- no registry record already tracks that catalog id or that endpoint, which
  would make the edit a duplicate rather than a repair;
- the successor reads as the same agency (same country and subdivision, a
  name that reads as a rename), using the review flags the supersession
  check already uses;
- no curator note on the record names the current host, which is a recorded
  decision to track that host;
- the successor host's robots.txt permits the request under the project's
  policy (``robots_policy``, ADR 0070), the same policy the daily fetch applies.

Like the other catalog checks, this proposes; ``--apply`` writes the edit into
the registry shard on a branch and a person merges it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from .config import Agency
from .identity import normalized_mdb_id
from .location import normalize_location
from .mobilitydb import (
    CatalogFeed,
    _feed_url_key,
    _is_active,
    _license_note,
    _reachable_catalog_ids,
    _scalar,
    _schedule_exclusion_reasons,
    pinning_note,
)
from .robots_policy import (
    DISALLOWED_BY_ROBOTS,
    INVALID_URL,
    ROBOTS_NOT_A_RULES_FILE,
    ROBOTS_REDIRECTED_OFF,
    ROBOTS_UNREACHABLE,
    RobotsVerdict,
)
from .supersession_review import FLAG_REASONS, blocking, review_flags

# Hold reasons. Stable strings: they are written into the weekly report.
SUCCESSOR_AMBIGUOUS = "successor_ambiguous"
SUCCESSOR_NOT_OPEN = "successor_not_open"
SUCCESSOR_ALREADY_TRACKED = "successor_already_tracked"
NOTE_PINS_CURRENT_HOST = "note_pins_current_host"

_HOLD_TEXT = {
    SUCCESSOR_AMBIGUOUS: "the catalog's redirects reach more than one current record",
    SUCCESSOR_NOT_OPEN: "the successor needs a key, is marked unofficial, or has no usable URL",
    SUCCESSOR_ALREADY_TRACKED: "another registry record already tracks the successor",
    NOTE_PINS_CURRENT_HOST: "a curator note names the host this record is tracked on",
}

# Robots holds carry the policy's reason code (ADR 0070). A person reading the
# report needs the sentence, so these map the codes to one.
_ROBOTS_HOLD_TEXT = {
    DISALLOWED_BY_ROBOTS: "not fetched: the successor host's robots.txt disallows this path",
    ROBOTS_REDIRECTED_OFF: "the successor host's /robots.txt redirects somewhere else",
    ROBOTS_NOT_A_RULES_FILE: "the successor host serves a web page, not rules, at /robots.txt",
    ROBOTS_UNREACHABLE: "the successor host's /robots.txt could not be read",
    INVALID_URL: "the successor URL is not an http or https address",
}


def _hold_text(code: str) -> str | None:
    """The sentence for a robots hold code, or None for any other code."""
    if code.startswith("robots_status_"):
        status = code.removeprefix("robots_status_")
        return (
            f"the successor host's /robots.txt answered {status}, "
            "which the robots policy treats as off-limits"
        )
    return _ROBOTS_HOLD_TEXT.get(code)


# Notes in these shapes were written by the catalog sync, not by a curator.
_CATALOG_NOTE_PREFIXES = ("License: http", "No stated data license")


@dataclass(frozen=True)
class _CatalogIdentity:
    """The three fields ``review_flags`` reads, for a catalog row."""

    country: str
    subdivision_code: str
    name: str


@dataclass(frozen=True)
class Repoint:
    """A tracked record whose catalog record retired into one we do not track.

    ``hold`` is empty when the edit is ready to apply. Otherwise it names why a
    person has to look first: a hold reason from this module, a blocking review
    flag from ``supersession_review``, or a robots verdict.
    """

    agency_id: str
    agency_name: str
    mdb_id: str
    current_url: str
    successor_mdb_id: str
    successor_name: str
    successor_url: str
    successor_license_note: str = ""
    hold: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.hold


def _current_successors(feed: CatalogFeed, by_mdb: dict[str, CatalogFeed]) -> list[CatalogFeed]:
    """The current Schedule records a retired record's redirects lead to."""
    found: list[CatalogFeed] = []
    for key in _reachable_catalog_ids(feed, by_mdb):
        record = by_mdb.get(key)
        if record is not None and record.data_type == "gtfs" and _is_active(record):
            found.append(record)
    return found


def _identity(feed: CatalogFeed) -> _CatalogIdentity:
    location = normalize_location(
        feed.country, subdivision_code=feed.subdivision_code, subdivision_name=feed.subdivision
    )
    return _CatalogIdentity(
        country=location.country_code,
        subdivision_code=location.subdivision_code,
        name=feed.name or feed.provider,
    )


class _Tracking:
    """Who tracks each catalog id and each endpoint in the registry.

    A retired alias of the record being repaired does not count as another
    tracker: the 2026-07-11 dedupe sometimes kept the twin on the dead URL
    canonical and retired the twin on the live one, and that alias is exactly
    the evidence the repair should follow.
    """

    def __init__(self, agencies: list[Agency]) -> None:
        self._by_id: dict[str, set[str]] = {}
        self._by_url: dict[str, set[str]] = {}
        self._aliases: dict[str, set[str]] = {}
        for a in agencies:
            if a.mdb_id:
                self._by_id.setdefault(normalized_mdb_id(a.mdb_id), set()).add(a.id)
            if key := _feed_url_key(a.static_gtfs_url):
                self._by_url.setdefault(key, set()).add(a.id)
            if a.alias_of:
                self._aliases.setdefault(a.alias_of, set()).add(a.id)

    def tracked_by_another(self, agency: Agency, feed: CatalogFeed) -> bool:
        owners = self._by_id.get(normalized_mdb_id(feed.mdb_id), set()) | self._by_url.get(
            _feed_url_key(feed.direct_download), set()
        )
        return bool(owners - self._aliases.get(agency.id, set()) - {agency.id})


def _holds(agency: Agency, successors: list[CatalogFeed]) -> tuple[str, ...]:
    successor = successors[0]
    hold: list[str] = []
    if len(successors) > 1:
        hold.append(SUCCESSOR_AMBIGUOUS)
    if _schedule_exclusion_reasons(successor):
        hold.append(SUCCESSOR_NOT_OPEN)
    hold.extend(blocking(review_flags(agency, _identity(successor))))  # type: ignore[arg-type]
    if pinning_note(agency, agency.static_gtfs_url):
        hold.append(NOTE_PINS_CURRENT_HOST)
    return tuple(dict.fromkeys(hold))


def find_repoints(feeds: list[CatalogFeed], agencies: Iterable[Agency]) -> list[Repoint]:
    """Every tracked record the catalog retired into a successor we do not track.

    Pure over the catalog and the registry: no network. Robots verdicts are
    added afterwards by :func:`check_successor_robots`.
    """
    agency_list = list(agencies)
    by_mdb = {normalized_mdb_id(f.mdb_id): f for f in feeds if f.mdb_id}
    tracking = _Tracking(agency_list)

    found: list[Repoint] = []
    for agency in sorted(agency_list, key=lambda a: a.id):
        if not agency.is_canonical_feed or not agency.mdb_id:
            continue
        retired = by_mdb.get(normalized_mdb_id(agency.mdb_id))
        if retired is None or retired.status != "deprecated":
            continue
        successors = _current_successors(retired, by_mdb)
        if not successors:
            continue  # nothing current to follow; the supersession report names it
        successor = successors[0]
        if tracking.tracked_by_another(agency, successor):
            # Another live record tracks the successor: the supersession check
            # retires this record into it, or the two are duplicates for a
            # curator. Either way it is not a URL repair.
            continue
        found.append(
            Repoint(
                agency_id=agency.id,
                agency_name=agency.name,
                mdb_id=agency.mdb_id,
                current_url=agency.static_gtfs_url,
                successor_mdb_id=successor.mdb_id,
                successor_name=successor.name or successor.provider,
                successor_url=successor.direct_download,
                successor_license_note=_license_note(successor),
                hold=_holds(agency, successors),
            )
        )
    return found


def check_successor_robots(
    repoints: Iterable[Repoint], check: Callable[[str], RobotsVerdict]
) -> list[Repoint]:
    """Add a robots hold to each ready repoint whose successor host refuses us.

    Only ready proposals are checked, so a held one costs no request.
    """
    out: list[Repoint] = []
    for item in repoints:
        if item.ready:
            verdict = check(item.successor_url)
            if not verdict.allowed:
                item = replace(item, hold=(*item.hold, verdict.reason))
        out.append(item)
    return out


def _mdb_id_in_style(existing: str, successor: str) -> str:
    """Write the successor id in the shard's own style for a legacy numeric id."""
    normalized = normalized_mdb_id(successor)
    if normalized.startswith("mdb-") and not existing.strip().strip("'\"").startswith("mdb-"):
        return normalized.removeprefix("mdb-")
    return successor


def _id_blocks(lines: list[str]) -> list[tuple[int, int, str]]:
    """``(first line, end line, agency id)`` for each ``- id:`` block."""
    starts = [
        (index, match.group(1))
        for index, line in enumerate(lines)
        if (match := re.match(r"\s*-\s*id:\s*(\S+)", line))
    ]
    ends = [index for index, _ in starts[1:]] + [len(lines)]
    return [(begin, end, agency_id) for (begin, agency_id), end in zip(starts, ends, strict=True)]


def _first_line(lines: list[str], begin: int, end: int, pattern: str) -> re.Match[str] | None:
    for index in range(begin, end):
        if match := re.match(pattern, lines[index]):
            return match
    return None


def _block_edits(lines: list[str], begin: int, end: int, item: Repoint) -> dict[int, str] | None:
    """The replacement lines for one block, or None when a needed line is missing."""
    url = _first_line(lines, begin, end, r"(\s*)static_gtfs_url:\s*\S")
    mdb = _first_line(lines, begin, end, r"(\s*)mdb_id:\s*(\S.*)$")
    if url is None or mdb is None:
        return None
    url_index = lines.index(url.string, begin, end)
    mdb_index = lines.index(mdb.string, begin, end)
    existing = mdb.group(2)
    quote = "'" if existing.strip().startswith("'") else ""
    new_id = _mdb_id_in_style(existing, item.successor_mdb_id)
    edits = {
        url_index: f"{url.group(1)}static_gtfs_url: {item.successor_url}",
        mdb_index: f"{mdb.group(1)}mdb_id: {quote}{new_id}{quote}",
    }
    # A note the catalog wrote describes the retired record's terms. Follow it
    # to the successor's. A note a curator wrote is theirs and stays.
    note = _first_line(lines, begin, end, r"(\s*)license_note:\s*(\S.*)$")
    if note is not None and item.successor_license_note:
        value = note.group(2).strip().strip("'\"")
        both_unstated = value.startswith("No stated") and item.successor_license_note.startswith(
            "No stated"
        )
        if value.startswith(_CATALOG_NOTE_PREFIXES) and not both_unstated:
            edits[lines.index(note.string, begin, end)] = (
                f"{note.group(1)}license_note: {_scalar(item.successor_license_note)}"
            )
    return edits


def apply_repoints(yaml_text: str, repoints: Iterable[Repoint]) -> tuple[str, list[str]]:
    """Move each ready record's URL and catalog id to its successor, in place.

    A targeted line edit within each ``- id:`` block, like
    ``apply_replacements``, so comments and formatting survive. A comment
    above the block names the catalog evidence. A block missing either line is
    left untouched rather than half-edited.
    """
    wanted = {r.agency_id: r for r in repoints if r.ready}
    if not wanted:
        return yaml_text, []
    lines = yaml_text.splitlines()
    edits: dict[int, str] = {}
    comments: dict[int, str] = {}
    changed: list[str] = []
    for begin, end, agency_id in _id_blocks(lines):
        item = wanted.get(agency_id)
        block = _block_edits(lines, begin, end, item) if item is not None else None
        if item is None or block is None:
            continue
        edits.update(block)
        indent = lines[begin][: len(lines[begin]) - len(lines[begin].lstrip())]
        comments[begin] = (
            f"{indent}# Mobility Database {normalized_mdb_id(item.mdb_id)} is deprecated "
            f"and redirects to {normalized_mdb_id(item.successor_mdb_id)}; "
            "the feed URL follows it (ADR 0069)."
        )
        changed.append(agency_id)

    out: list[str] = []
    for index, line in enumerate(lines):
        if index in comments:
            out.append(comments[index])
        out.append(edits.get(index, line))
    trailing = "\n" if yaml_text.endswith("\n") else ""
    return "\n".join(out) + trailing, changed


def render_repoints_md(repoints: Iterable[Repoint]) -> str:
    """The report section for the supersession run's Markdown output."""
    items = sorted(repoints, key=lambda r: r.agency_name.lower())
    ready = [r for r in items if r.ready]
    held = [r for r in items if not r.ready]
    out = [
        "## Retired, with a successor we do not track yet",
        "",
        "The catalog retired the record each of these is tracked on and names one "
        "current record that replaced it. The edit keeps the scorecard and its "
        "history and moves `static_gtfs_url` and `mdb_id` to the successor "
        "(ADR 0069). Nothing is added and no page is created.",
        "",
        f"- **{len(ready)}** are ready: open, the same agency by the review rules, "
        "and allowed by the successor host's robots.txt.",
        f"- **{len(held)}** are held for a person, with the reason.",
        "",
    ]
    for r in ready:
        out.append(
            f"- {r.agency_name} (`{r.agency_id}`): {normalized_mdb_id(r.mdb_id)} to "
            f"{normalized_mdb_id(r.successor_mdb_id)}, now {r.successor_url}"
        )
    if ready:
        out.append("")
    if held:
        out += ["### Held", ""]
        for r in held:
            reasons = "; ".join(
                _HOLD_TEXT.get(code) or _hold_text(code) or FLAG_REASONS.get(code) or code
                for code in r.hold
            )
            out.append(
                f"- {r.agency_name} (`{r.agency_id}`): {normalized_mdb_id(r.mdb_id)} to "
                f"{normalized_mdb_id(r.successor_mdb_id)} ({r.successor_url}). Held: {reasons}."
            )
        out.append("")
    return "\n".join(out)
