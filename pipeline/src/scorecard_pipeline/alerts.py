"""Expiration and regression alert digest.

The roadmap's first retention tool (docs/roadmap.md): the single most useful
thing this tool can tell a small agency is "your feed expires in N days and
trip planners are about to drop you." This reads the artifacts the pipeline
already publishes and produces a plain-language digest of two things worth
acting on now: feeds whose service window is about to close, and grades that
dropped since the previous run.

The digest is rendered as Markdown and written to stdout or a file. Routing it
to subscribers (email via SES, a Slack post) is a deploy concern handled by the
caller; keeping the build and the send separate is what makes the logic
testable against fixture artifacts with no network.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from .anomaly import detect_anomalies
from .config import artifacts_dir

# A letter-grade drop, or a score fall of at least this many points between the
# two most recent runs, is worth telling someone about. Smaller day-to-day
# wobble from validator nondeterminism is not.
REGRESSION_POINTS = 3.0
GRADE_ORDER = ["F", "D", "C", "B", "A"]
SCORECARD_BASE = "https://gtfsscorecard.org"

# Default lead time for the email digest. Sixty days gives an agency a first,
# calm heads-up while there is plenty of time to re-export, instead of one
# cliff-edge warning the week the feed dies. The digest then groups feeds by
# how soon they expire so the most urgent rise to the top.
DEFAULT_EXPIRY_DAYS = 60

# (upper bound in days, label). A feed is placed in the first tier whose bound
# it falls within; expired feeds come before all of them.
_EXPIRY_TIERS: list[tuple[int, str]] = [
    (7, "Expires within a week"),
    (14, "Expires within two weeks"),
    (30, "Expires within a month"),
    (60, "Expires within two months"),
]
_EXPIRED_LABEL = "Already expired"


def _expiry_tier(days: int | None) -> str:
    """The lead-time bucket label for a feed's days-until-expiry."""
    if days is None:
        return _EXPIRY_TIERS[-1][1]
    if days < 0:
        return _EXPIRED_LABEL
    for bound, label in _EXPIRY_TIERS:
        if days <= bound:
            return label
    return _EXPIRY_TIERS[-1][1]


def _scorecard_url(agency_id: str, anchor: str = "") -> str:
    return f"{SCORECARD_BASE}/agency/{agency_id}/{anchor}"


@dataclass
class AlertItem:
    """One thing worth an agency's attention, framed as a fix."""

    agency_id: str
    agency_name: str
    kind: str  # "expiry" | "regression"
    headline: str
    detail: str
    fix: str
    scorecard_url: str = ""
    days_until_expiry: int | None = None


@dataclass
class Digest:
    as_of: dt.date
    items: list[AlertItem] = field(default_factory=list)


def _load_json(path: Any) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except (FileNotFoundError, ValueError):
        return None


def _grade_dropped(prev: str, curr: str) -> bool:
    try:
        return GRADE_ORDER.index(curr) < GRADE_ORDER.index(prev)
    except ValueError:
        return False


def _expiry_item(latest: dict[str, Any], expiry_days: int) -> AlertItem | None:
    freshness = latest.get("categories", {}).get("freshness", {})
    raw_days = freshness.get("details", {}).get("days_until_expiry")
    if not isinstance(raw_days, (int, float)) or isinstance(raw_days, bool):
        return None
    days = int(raw_days)
    if days > expiry_days:
        return None
    agency = latest["agency"]
    if days < 0:
        headline = "Service data has expired"
        detail = (
            f"The schedule stopped covering service {abs(days)} day(s) ago. "
            "Trip planners may have already dropped this agency."
        )
    else:
        headline = f"Service data expires in {days} day(s)"
        detail = (
            "When the calendar runs out, trip planners stop showing this "
            "agency's service even though buses are still running."
        )
    return AlertItem(
        agency_id=agency["id"],
        agency_name=agency["name"],
        kind="expiry",
        headline=headline,
        detail=detail,
        fix="Re-export the feed with a calendar that extends further out, or "
        "set feed_info end dates past the next service change.",
        # Link straight to the ready-to-send note on the scorecard.
        scorecard_url=_scorecard_url(agency["id"], "#send-note"),
        days_until_expiry=days,
    )


def _regression_item(history: list[dict[str, Any]], name: str, agency_id: str) -> AlertItem | None:
    if len(history) < 2:
        return None
    prev, curr = history[-2], history[-1]
    try:
        grade_drop = _grade_dropped(str(prev["grade"]), str(curr["grade"]))
        score_drop = float(prev["score"]) - float(curr["score"])
    except (KeyError, TypeError, ValueError):
        # A malformed history row should drop this one item, not crash the digest.
        return None
    if not grade_drop and score_drop < REGRESSION_POINTS:
        return None
    if grade_drop:
        headline = f"Grade slipped from {prev['grade']} to {curr['grade']}"
    else:
        headline = f"Score fell {score_drop:.1f} points since {prev['date']}"
    return AlertItem(
        agency_id=agency_id,
        agency_name=name,
        kind="regression",
        headline=headline,
        detail=f"Overall score went from {prev['score']} on {prev['date']} to "
        f"{curr['score']} on {curr['date']}.",
        fix="Open the scorecard and check the top fixes; a recent export change "
        "or an expiring calendar is the usual cause.",
        scorecard_url=_scorecard_url(agency_id),
    )


def _anomaly_alert_items(
    history: list[dict[str, Any]], agency_id: str, agency_name: str
) -> list[AlertItem]:
    """Convert non-transient anomalies in the score history to AlertItems.

    Transient dips (one-day recoveries) are suppressed: a feed that glitched
    and bounced back the next day is noise, not a thing to act on. The dip
    date and the recovery date (the step that brought the score back up) are
    both suppressed, because the recovery cliff is equally meaningless on its
    own. Score cliffs that sustained and expiry regressions are surfaced
    because both require a human to check whether a real change happened.
    """
    all_anomalies = detect_anomalies(history)

    # Dates that are part of a transient-dip pattern. The dip date itself is
    # flagged transient_dip; the recovery date is the next entry in the
    # history (whose score_cliff is equally noise — the score simply bounced
    # back).
    suppressed_dates: set[str] = set()
    history_dates = [str(e.get("date", "")) for e in history]
    for anomaly in all_anomalies:
        if anomaly.kind == "transient_dip":
            suppressed_dates.add(anomaly.date)
            try:
                idx = history_dates.index(anomaly.date)
                if idx + 1 < len(history_dates):
                    suppressed_dates.add(history_dates[idx + 1])
            except ValueError:
                pass

    items: list[AlertItem] = []
    for anomaly in all_anomalies:
        if anomaly.kind == "transient_dip":
            continue
        if anomaly.date in suppressed_dates:
            continue
        if anomaly.kind == "score_cliff":
            headline = f"Score changed sharply on {anomaly.date}"
            fix = (
                "Check for feed changes or a new validator notice around this date. "
                "If the score stayed down, look at the top fixes on the scorecard."
            )
        else:  # expiry_regression
            headline = f"Service window shortened unexpectedly on {anomaly.date}"
            fix = (
                "Confirm the latest export is the one being served. An older export "
                "may have been republished, which moves the calendar backward."
            )
        items.append(
            AlertItem(
                agency_id=agency_id,
                agency_name=agency_name,
                kind="anomaly",
                headline=headline,
                detail=anomaly.detail,
                fix=fix,
                scorecard_url=_scorecard_url(agency_id),
            )
        )
    return items


def build_digest(
    today: dt.date | None = None,
    expiry_days: int = DEFAULT_EXPIRY_DAYS,
) -> Digest:
    """Scan published artifacts for expiry and regression alerts.

    Reads each agency's latest.json for the expiry window and index.json for
    score history. Returns items sorted with the most urgent first (expired
    feeds, then soonest-to-expire, then regressions).
    """
    as_of = today or dt.date.today()
    root = artifacts_dir()
    items: list[AlertItem] = []

    index = _load_json(root / "index.json") or {"agencies": {}}
    for agency_id, entry in sorted(index.get("agencies", {}).items()):
        latest = _load_json(root / agency_id / "latest.json")
        if latest:
            expiry = _expiry_item(latest, expiry_days)
            if expiry:
                items.append(expiry)
        regression = _regression_item(
            entry.get("history", []), entry.get("name", agency_id), agency_id
        )
        if regression:
            items.append(regression)
        items.extend(
            _anomaly_alert_items(entry.get("history", []), agency_id, entry.get("name", agency_id))
        )

    def _urgency(item: AlertItem) -> tuple[int, int, str]:
        # Expiry before regression/anomaly; within expiry, soonest (or most overdue) first.
        if item.kind == "expiry":
            days = item.days_until_expiry
            return (0, days if days is not None else 9999, item.agency_id)
        if item.kind == "anomaly":
            return (2, 0, item.agency_id)
        return (1, 0, item.agency_id)

    items.sort(key=_urgency)
    return Digest(as_of=as_of, items=items)


def render_digest(digest: Digest) -> str:  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    """Render the digest as Markdown.

    Empty is a valid, good outcome: a digest with nothing in it says so plainly
    rather than sending an alarming blank.
    """
    lines = [f"# Feed health digest — {digest.as_of.isoformat()}", ""]
    if not digest.items:
        lines.append(
            "No feeds need attention today. Nothing is expiring soon and no grades dropped."
        )
        lines.append("")
        return "\n".join(lines)

    expiring = [i for i in digest.items if i.kind == "expiry"]
    regressions = [i for i in digest.items if i.kind == "regression"]
    anomalies = [i for i in digest.items if i.kind == "anomaly"]
    lines.append(f"{len(digest.items)} item(s) need attention.")
    lines.append("")

    def _emit(item: AlertItem, heading: str = "###") -> None:
        lines.append(f"{heading} {item.agency_name}")
        lines.append(f"**{item.headline}.** {item.detail}")
        lines.append("")
        lines.append(f"Fix: {item.fix}")
        if item.scorecard_url:
            # Expiry items deep-link to the ready-to-send note; others to the page.
            label = (
                "Copy a note to send the agency" if item.kind == "expiry" else "Open the scorecard"
            )
            lines.append("")
            lines.append(f"[{label}]({item.scorecard_url})")
        lines.append("")

    if expiring:
        lines.append("## Feeds expiring soon")
        lines.append("")
        # Group by lead-time tier so the ramp is visible: expired, then a week
        # out, two weeks, a month, two months. Items are already soonest-first.
        tier_order = [_EXPIRED_LABEL] + [label for _, label in _EXPIRY_TIERS]
        for tier in tier_order:
            members = [i for i in expiring if _expiry_tier(i.days_until_expiry) == tier]
            if not members:
                continue
            lines.append(f"### {tier}")
            lines.append("")
            for item in members:
                _emit(item, "####")
    if regressions:
        lines.append("## Grade changes")
        lines.append("")
        for item in regressions:
            _emit(item)
    if anomalies:
        lines.append("## Unusual score changes")
        lines.append("")
        for item in anomalies:
            _emit(item)
    return "\n".join(lines)
