"""Expiration and regression alert digest.

The roadmap's first retention tool (docs/roadmap.md): the single most useful
thing this tool can tell a small agency is "your feed expires in N days and
trip planners are about to drop you." This reads the artifacts the pipeline
already publishes and produces a plain-language digest of things worth acting
on now: feeds whose service window is about to close, grades that dropped
since the previous run, and — per EXP-13 (docs/ideation/03-expansions.md) —
feeds whose renewal *behavior* (a history of late renewals, a repeating
lapse-and-recover pattern, a slowing cadence) suggests risk before the calendar
date itself says so. The behavioral read only fires for feeds the deterministic
expiry check hasn't already flagged, so it stays a genuinely earlier warning
rather than a duplicate.

A fourth item, per EXP-18 (docs/ideation/06-sweep-2026-07-12.md), surfaces
when the latest run's export changed structurally — a route dropped, stops
moved, the service span shifted — even when nothing about it was invalid, so
a grade never moved to flag it. Unlike the behavioral lapse-risk read, this
one is not a private-only signal: it mirrors the "What changed inside the
export" block the agency page already renders (`exportdiff.py`, `render_site.py`)
so a subscriber hears the same finding here that a page visitor would see.

The digest is rendered as Markdown and written to stdout or a file. Routing it
to subscribers (email via SES, a Slack post) is a deploy concern handled by the
caller; keeping the build and the send separate is what makes the logic
testable against fixture artifacts with no network. This digest is the private,
opt-in liaison channel (ADR 0004) — the behavioral risk read is never shown on
the public agency page.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from .anomaly import detect_anomalies
from .comparisons import current_producer_contract_suffix
from .config import artifacts_dir, current_agency_ids, utc_today
from .instance import BASE_URL as SCORECARD_BASE
from .lapse_risk import TIER_ELEVATED, TIER_HIGH
from .lapse_risk import assess as assess_lapse_risk

# A letter-grade drop, or a score fall of at least this many points between the
# two most recent runs, is worth telling someone about. Smaller day-to-day
# wobble from validator nondeterminism is not.
REGRESSION_POINTS = 3.0
GRADE_ORDER = ["F", "D", "C", "B", "A"]

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


_SAFE_CONTEXT_VALUE = re.compile(r"^[A-Za-z0-9_-]+$")


def _primary_finding_code(latest: dict[str, Any]) -> str:
    """Choose the first published top-fix code, preferring an expiry finding."""
    fixes = latest.get("top_fixes") or []
    safe_codes = [
        str(fix.get("code"))
        for fix in fixes
        if _SAFE_CONTEXT_VALUE.fullmatch(str(fix.get("code") or ""))
    ]
    if not safe_codes:
        return ""
    freshness_codes = {
        str(finding.get("code"))
        for finding in latest.get("categories", {}).get("freshness", {}).get("findings", [])
    }
    return next((code for code in safe_codes if code in freshness_codes), safe_codes[0])


def _scorecard_url(
    agency_id: str,
    anchor: str = "",
    finding_code: str = "",
) -> str:
    if finding_code and _SAFE_CONTEXT_VALUE.fullmatch(finding_code):
        return (
            f"{SCORECARD_BASE}/agency/{agency_id}/?"
            f"{urlencode({'finding': finding_code})}#finding-handoff"
        )
    return f"{SCORECARD_BASE}/agency/{agency_id}/{anchor}"


def _attach_finding_context(item: AlertItem, latest: dict[str, Any] | None) -> AlertItem:
    code = _primary_finding_code(latest or {})
    if code:
        item.scorecard_url = _scorecard_url(item.agency_id, finding_code=code)
    return item


@dataclass
class AlertItem:
    """One thing worth an agency's attention, framed as a fix."""

    agency_id: str
    agency_name: str
    kind: str  # "expiry" | "lapse_risk" | "regression" | "anomaly" | "export_change"
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
            "agency's service even while service is still running."
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
        scorecard_url=_scorecard_url(
            agency["id"],
            "#send-note",
            _primary_finding_code(latest),
        ),
        days_until_expiry=days,
    )


def _lapse_risk_item(history: list[dict[str, Any]], name: str, agency_id: str) -> AlertItem | None:
    """A behavioral early-warning item, or None if the tier doesn't warrant one.

    Only called for agencies the deterministic expiry check hasn't already
    flagged (see build_digest), so this is always a genuinely earlier signal,
    never a second copy of the same warning. `insufficient_history` and `none`
    tiers produce nothing — a quiet, honest read, not a forced item.
    """
    risk = assess_lapse_risk(history)
    if risk.tier not in (TIER_ELEVATED, TIER_HIGH):
        return None
    label = "High" if risk.tier == TIER_HIGH else "Elevated"
    headline = f"{label} behavioral lapse risk"
    detail = " ".join(reason.detail for reason in risk.reasons)
    return AlertItem(
        agency_id=agency_id,
        agency_name=name,
        kind="lapse_risk",
        headline=headline,
        detail=detail,
        fix="This is a behavioral read from renewal history, not a certainty — "
        "confirm with the agency whether the next export is already prepared. "
        "A proactive check now can prevent a repeat of this pattern.",
        scorecard_url=_scorecard_url(agency_id),
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


def _export_change_item(
    latest: dict[str, Any] | None, name: str, agency_id: str
) -> AlertItem | None:
    """An item when the latest run's export changed structurally (EXP-18):
    routes added or removed, stops that moved, the service span, or trip
    count. None when there is no ``export_diff`` block or it carries no
    changes — most runs, since most exports are byte-identical or change only
    in ways that don't move the structure fingerprint.

    Descriptive only, matching the agency-page rendering of the same block:
    the digest never claims the change was a mistake, only that it happened.
    """
    if not latest:
        return None
    export = latest.get("export_diff")
    changes = (export or {}).get("changes") or []
    if not changes:
        return None
    return AlertItem(
        agency_id=agency_id,
        agency_name=name,
        kind="export_change",
        headline="The export's structure changed",
        detail=" ".join(str(c) for c in changes),
        fix="Confirm this was intentional. If not, check your scheduling "
        "software's export settings for what changed.",
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


def build_digest(  # noqa: C901
    today: dt.date | None = None,
    expiry_days: int = DEFAULT_EXPIRY_DAYS,
) -> Digest:
    """Scan published artifacts for expiry, regression, and export-change alerts.

    Reads each agency's latest.json for the expiry window, the export-diff
    block, and index.json for score history. Returns items sorted with the
    most urgent first (expired feeds, then soonest-to-expire, then
    regressions, then structural export changes, then anomalies).
    """
    as_of = today or utc_today()
    root = artifacts_dir()
    items: list[AlertItem] = []

    index = _load_json(root / "index.json") or {"agencies": {}}
    indexed = index.get("agencies", {})
    current_ids = set(current_agency_ids(indexed))
    for agency_id, entry in sorted(indexed.items()):
        # A stale committed/hydrated index may predate the retirement. Keep its
        # history on disk, but do not send a new alert for the alias.
        if agency_id not in current_ids:
            continue
        history = entry.get("history", [])
        comparable_history = current_producer_contract_suffix(history)
        latest = _load_json(root / agency_id / "latest.json")
        expiry = None
        if latest:
            expiry = _expiry_item(latest, expiry_days)
            if expiry:
                items.append(expiry)
        if not expiry:
            # Behavioral risk is only worth surfacing when the deterministic
            # check hasn't already flagged this feed — otherwise it is a
            # slower-to-fire duplicate of the same warning.
            lapse_risk = _lapse_risk_item(
                comparable_history, entry.get("name", agency_id), agency_id
            )
            if lapse_risk:
                items.append(_attach_finding_context(lapse_risk, latest))
        regression = _regression_item(comparable_history, entry.get("name", agency_id), agency_id)
        if regression:
            items.append(_attach_finding_context(regression, latest))
        # Not routed through _attach_finding_context: an export-structure
        # change is not one of the validator's named findings, so there is no
        # finding code to link. The plain scorecard URL is the honest link.
        export_change = _export_change_item(latest, entry.get("name", agency_id), agency_id)
        if export_change:
            items.append(export_change)
        items.extend(
            _attach_finding_context(item, latest)
            for item in _anomaly_alert_items(
                comparable_history,
                agency_id,
                entry.get("name", agency_id),
            )
        )

    def _urgency(item: AlertItem) -> tuple[int, int, str]:
        # Expiry first (soonest/most overdue first), then behavioral lapse
        # risk (the early warning), then regressions, then structural export
        # changes (a concrete, dated event but not yet known to have moved
        # the grade), then anomalies.
        if item.kind == "expiry":
            days = item.days_until_expiry
            return (0, days if days is not None else 9999, item.agency_id)
        if item.kind == "lapse_risk":
            return (1, 0, item.agency_id)
        if item.kind == "anomaly":
            return (4, 0, item.agency_id)
        if item.kind == "export_change":
            return (3, 0, item.agency_id)
        return (2, 0, item.agency_id)

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
    lapse_risks = [i for i in digest.items if i.kind == "lapse_risk"]
    regressions = [i for i in digest.items if i.kind == "regression"]
    export_changes = [i for i in digest.items if i.kind == "export_change"]
    anomalies = [i for i in digest.items if i.kind == "anomaly"]
    lines.append(f"{len(digest.items)} item(s) need attention.")
    lines.append("")

    def _emit(item: AlertItem, heading: str = "###") -> None:
        lines.append(f"{heading} {item.agency_name}")
        lines.append(f"**{item.headline}.** {item.detail}")
        lines.append("")
        lines.append(f"Fix: {item.fix}")
        if item.scorecard_url:
            if "?finding=" in item.scorecard_url:
                label = "Open the finding handoff"
            else:
                # Older artifacts without a safe finding code retain the
                # ready-to-send note link.
                label = (
                    "Copy a note to send the agency"
                    if item.kind == "expiry"
                    else "Open the scorecard"
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
    if lapse_risks:
        lines.append("## Feeds showing early lapse-risk signals")
        lines.append("")
        lines.append(
            "Not yet close to expiring, but their renewal history suggests risk "
            "worth a proactive check — see the reasons below each one."
        )
        lines.append("")
        for item in lapse_risks:
            _emit(item)
    if regressions:
        lines.append("## Grade changes")
        lines.append("")
        for item in regressions:
            _emit(item)
    if export_changes:
        lines.append("## What changed inside the export")
        lines.append("")
        # Deliberately does not say "without moving the grade": an export can
        # change structurally on the same run a grade drops, and this section
        # renders alongside the regression section when it does. Claiming the
        # grade held would be false in exactly that case.
        lines.append(
            "The feed file changed shape since the last check. A structural "
            "change does not have to move the grade, so it can pass unnoticed. "
            "Worth confirming it was intended."
        )
        lines.append("")
        for item in export_changes:
            _emit(item)
    if anomalies:
        lines.append("## Unusual score changes")
        lines.append("")
        for item in anomalies:
            _emit(item)
    return "\n".join(lines)
