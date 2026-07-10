"""Atom 1.0 feeds for feed-quality changes (the static-deploy alert channel).

The roadmap's retention idea is "tell an agency when its feed slips." `alerts.py`
and `notify.py` already do that by email, but email needs an opt-in store and an
SES sender, which a fork or a casual reader does not have. An Atom feed needs
neither: it is one more static file the daily render writes next to the pages, so
anyone — an agency manager, an advocate, a state liaison, a Slack/Zapier webhook —
can subscribe in a reader and hear about a grade drop with no account and no
backend. It complements the email digest rather than replacing it.

Two feeds are produced:

* a site-wide feed of every agency whose grade or score moved on the latest run
  (built from ``render_site.compute_changes``), and
* a per-agency feed of that feed's own history of grade moves, expiry crossings,
  and notable score swings (built from ``timemachine.history_events``).

Everything here is pure and deterministic: the feed ``<updated>`` and each
entry's timestamp are derived from snapshot dates, not wall-clock time, so a
re-run over the same data reproduces byte-identical XML (the publish.py
idempotency contract).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

from .instance import BASE_URL, SITE_NAME

# The tag: URI authority for stable, reproducible entry and feed ids (RFC 4151).
# The date is the scheme's minting year, fixed so ids never churn. Derived from
# the configured base URL's host so a fork mints its own tag authority instead
# of inheriting the upstream domain's; on the upstream instance this resolves
# to the same "gtfsscorecard.org" value it always has, so existing entry ids
# are unchanged.
_TAG_BASE = f"tag:{BASE_URL.split('://', 1)[-1].rstrip('/')},2026:"


@dataclass(frozen=True)
class Entry:
    """One Atom entry: a single change worth hearing about."""

    id: str
    title: str
    updated: dt.datetime
    summary: str
    link: str
    category: str  # machine term, e.g. "grade_drop" | "grade_rise" | "expiry"


def _rfc3339(moment: dt.datetime) -> str:
    """An RFC 3339 / Atom timestamp in UTC with a trailing Z."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_to_dt(date: str) -> dt.datetime:
    """A snapshot date string (YYYY-MM-DD) as a UTC midnight instant. Falls back
    to the epoch on a malformed date so one bad row never breaks the feed."""
    try:
        return dt.datetime.fromisoformat(date).replace(tzinfo=dt.UTC)
    except (TypeError, ValueError):
        return dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


def render_atom(
    *,
    feed_id: str,
    title: str,
    subtitle: str,
    self_url: str,
    alternate_url: str,
    entries: Sequence[Entry],
    updated: dt.datetime | None = None,
) -> str:
    """Serialize an Atom 1.0 feed.

    ``updated`` defaults to the newest entry's timestamp (or the epoch when there
    are no entries) so the document stays a pure function of its data. Entries are
    emitted newest first.
    """
    ordered = sorted(entries, key=lambda e: (e.updated, e.id), reverse=True)
    _epoch = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
    feed_updated = updated or (ordered[0].updated if ordered else _epoch)
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"  <title>{escape(title)}</title>",
        f"  <subtitle>{escape(subtitle)}</subtitle>",
        f"  <id>{escape(feed_id)}</id>",
        f'  <link rel="self" type="application/atom+xml" href="{escape(self_url)}"/>',
        f'  <link rel="alternate" type="text/html" href="{escape(alternate_url)}"/>',
        f"  <updated>{_rfc3339(feed_updated)}</updated>",
        # RFC 4287 4.1.1 requires a feed-level author when entries omit their own;
        # without it the document is not valid Atom and feed validators reject it.
        f"  <author><name>{escape(SITE_NAME)}</name></author>",
        f'  <generator uri="{escape(BASE_URL)}">{escape(SITE_NAME)}</generator>',
    ]
    for entry in ordered:
        parts.extend(
            [
                "  <entry>",
                f"    <title>{escape(entry.title)}</title>",
                f"    <id>{escape(entry.id)}</id>",
                f'    <link rel="alternate" type="text/html" href="{escape(entry.link)}"/>',
                f"    <updated>{_rfc3339(entry.updated)}</updated>",
                f'    <category term="{escape(entry.category)}"/>',
                f"    <summary>{escape(entry.summary)}</summary>",
                "  </entry>",
            ]
        )
    parts.append("</feed>")
    return "\n".join(parts) + "\n"


def _change_entry(change: dict[str, object], base_url: str) -> Entry:
    """Map one ``compute_changes`` record to an Atom entry."""
    agency_id = str(change.get("id", ""))
    name = str(change.get("name", agency_id))
    date = str(change.get("date", ""))
    from_grade = change.get("from_grade")
    to_grade = change.get("to_grade")
    delta = change.get("score_delta")
    regressed = bool(change.get("regressed"))
    grade_moved = from_grade != to_grade
    if grade_moved:
        verb = "dropped" if regressed else "improved"
        title = f"{name}: grade {verb} {from_grade} to {to_grade}"
        category = "grade_drop" if regressed else "grade_rise"
    else:
        verb = "fell" if regressed else "rose"
        shown = abs(float(delta)) if isinstance(delta, (int, float)) else delta
        title = f"{name}: score {verb} {shown} points"
        category = "score_drop" if regressed else "score_rise"
    summary = (
        f"On {date}, {name}'s GTFS data quality went from "
        f"{change.get('from_score')} ({from_grade}) to "
        f"{change.get('to_score')} ({to_grade}). "
        + (
            "Trip planners read the same feed, so a drop is worth a look."
            if regressed
            else "A step in the right direction."
        )
    )
    return Entry(
        id=f"{_TAG_BASE}agency/{agency_id}/{date}",
        title=title,
        updated=_date_to_dt(date),
        summary=summary,
        link=f"{base_url}/agency/{agency_id}/",
        category=category,
    )


def site_change_feed(
    changes: list[dict[str, object]], *, base_url: str, max_entries: int = 60
) -> str:
    """The site-wide Atom feed: every agency that moved on the latest run.

    ``changes`` is the output of ``render_site.compute_changes`` (regressions
    first). The feed caps at ``max_entries`` so a big swing day does not produce
    an unbounded document.
    """
    entries = [_change_entry(c, base_url) for c in changes[:max_entries]]
    return render_atom(
        feed_id=f"{_TAG_BASE}changes",
        title="GTFS Scorecard: feed quality changes",
        subtitle=(
            "Transit agencies whose GTFS data quality grade or score moved since their last check."
        ),
        self_url=f"{base_url}/changes/feed.xml",
        alternate_url=f"{base_url}/pulse/#changes",
        entries=entries,
    )


def agency_change_feed(
    agency_id: str,
    agency_name: str,
    events: Sequence[Any],
    *,
    base_url: str,
    max_entries: int = 50,
) -> str:
    """A single agency's Atom feed of dated change events.

    ``events`` is the output of ``timemachine.history_events`` (newest first):
    each has ``date``, ``kind``, and ``detail``. A grade-drop event is tagged
    ``grade_drop`` so a reader or webhook can filter for the alert that matters.
    """
    entries: list[Entry] = []
    for ev in events[:max_entries]:
        date = str(getattr(ev, "date", ""))
        kind = str(getattr(ev, "kind", "change"))
        detail = str(getattr(ev, "detail", ""))
        category = kind
        if kind == "grade_change":
            category = "grade_drop" if " to " in detail and _is_drop(detail) else "grade_change"
        entries.append(
            Entry(
                id=f"{_TAG_BASE}agency/{agency_id}/{date}/{kind}",
                title=f"{agency_name}: {detail}",
                updated=_date_to_dt(date),
                summary=detail,
                link=f"{base_url}/agency/{agency_id}/",
                category=category,
            )
        )
    return render_atom(
        feed_id=f"{_TAG_BASE}agency/{agency_id}/changes",
        title=f"GTFS Scorecard: {agency_name} feed quality changes",
        subtitle=f"Grade moves, expiry warnings, and score swings for {agency_name}'s GTFS feed.",
        self_url=f"{base_url}/agency/{agency_id}/feed.xml",
        alternate_url=f"{base_url}/agency/{agency_id}/",
        entries=entries,
    )


# Letter grades worst-to-best; a "went X to Y" detail is a drop when Y ranks below X.
_GRADE_ORDER = ["F", "D", "C", "B", "A"]


def _is_drop(detail: str) -> bool:
    """Whether a grade_change detail string ('Grade went B to C, ...') describes a
    drop. Defaults to False when the grades can't be read, so an ambiguous detail
    is not labelled an alert."""
    try:
        # The detail is "Grade went B to C" with an optional ", <driver>." tail,
        # and ends in a period when there is no driver ("Grade went C to D.").
        head = detail.split(",")[0]  # "Grade went B to C" or "Grade went C to D."
        tokens = head.replace("Grade went", "").split(" to ")
        prev = tokens[0].strip().rstrip(".")
        curr = tokens[1].strip().rstrip(".")
        return _GRADE_ORDER.index(curr) < _GRADE_ORDER.index(prev)
    except (IndexError, ValueError):
        return False
