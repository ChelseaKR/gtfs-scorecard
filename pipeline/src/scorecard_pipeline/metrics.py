"""Phase 1 scorecard metrics: Correctness and Freshness.

Each metric here documents its own scoring rationale; the full methodology
with citations lives in docs/rubric.md and must stay in sync.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from .gtfs import FeedDates
from .notices import translate
from .validate import ValidationReport

# Correctness deductions per distinct notice code, by severity. A code's
# deduction grows gently with instance count (an error appearing 500 times
# is worse than once, but not 500x worse — it is usually one systemic cause).
SEVERITY_BASE_DEDUCTION = {"ERROR": 12.0, "WARNING": 4.0, "INFO": 0.5}


# Per distinct notice code, the base deduction is scaled by how widespread the
# notice is: (instances at or below this count, multiplier). The final tier is
# open-ended. Kept as data so score.methodology() can publish the exact
# thresholds and a skeptic can reproduce the grade.
COUNT_MULTIPLIER_TIERS: tuple[tuple[int, float], ...] = ((5, 1.0), (50, 1.5))
WIDESPREAD_MULTIPLIER = 2.0


def _count_multiplier(total: int) -> float:
    for threshold, multiplier in COUNT_MULTIPLIER_TIERS:
        if total <= threshold:
            return multiplier
    return WIDESPREAD_MULTIPLIER


@dataclass(frozen=True)
class Finding:
    """One notice group, translated for the scorecard UI."""

    code: str
    severity: str
    count: int
    what: str
    why: str
    fix: str
    effort: str
    deduction: float

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "count": self.count,
            "what": self.what,
            "why": self.why,
            "fix": self.fix,
            "effort": self.effort,
            # Roughly the points this finding costs, so a fix can show what it is
            # worth ("about +12 points"). An estimate within the category, not a
            # promise about the overall grade after weighting and renormalization.
            "points": round(self.deduction, 1),
            # Who typically makes this fix, so a manager who does not control the
            # export knows whether to act or to forward it. "" when unclear.
            "owner": _fix_owner(self.effort, self.fix, self.what),
        }


# Survey-style work needs the agency's own knowledge of the world (which stops
# are accessible, what a stop is called); export-setting work is the vendor or
# scheduling tool. Classify conservatively from the fix's own language, and stay
# silent ("") when it is genuinely unclear rather than guess.
_TEAM_TERMS = ("survey", "by hand", "physically", "photograph", "walk the")
_EXPORT_TERMS = ("export setting", "export", "scheduling software", "your export")


def _fix_owner(effort: str, fix: str, what: str) -> str:
    text = f"{effort} {fix} {what}".lower()
    if any(term in text for term in _TEAM_TERMS):
        return "Likely your team"
    if any(term in text for term in _EXPORT_TERMS):
        return "Likely your export tool"
    return ""


@dataclass(frozen=True)
class CategoryResult:
    """A scored rubric category plus the details behind the number."""

    name: str
    score: float  # 0-100
    summary: str
    findings: list[Finding] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": "measured",
            "score": round(self.score, 1),
            "summary": self.summary,
            "findings": [f.to_json() for f in self.findings],
            "details": self.details,
        }


def correctness(report: ValidationReport) -> CategoryResult:
    """Score validator notices, weighted by severity and (gently) by count.

    Rationale (rubric.md "Correctness"): start at 100 and deduct per distinct
    notice code — ERROR 12, WARNING 4, INFO 0.5 points, scaled up to 2x for
    widespread notices. Per-code rather than per-instance deduction keeps one
    systemic export bug from zeroing the score while still ranking feeds with
    many distinct problems below feeds with one.
    """
    findings: list[Finding] = []
    score = 100.0
    for group in report.notices:
        t = translate(group.code)
        base = SEVERITY_BASE_DEDUCTION.get(group.severity, SEVERITY_BASE_DEDUCTION["INFO"])
        deduction = base * _count_multiplier(group.total)
        score -= deduction
        findings.append(
            Finding(
                code=group.code,
                severity=group.severity,
                count=group.total,
                what=t.what,
                why=t.why,
                fix=t.fix,
                effort=t.effort,
                deduction=deduction,
            )
        )
    score = max(0.0, score)

    counts = report.count_by_severity()
    if not findings:
        summary = (
            "The validator found no problems in this feed. That is rare and worth celebrating."
        )
    else:
        n_codes = len(findings)
        total = counts["ERROR"] + counts["WARNING"] + counts["INFO"]
        summary = (
            f"The MobilityData validator flagged {n_codes} "
            f"{'kind' if n_codes == 1 else 'kinds'} of issue across {total} "
            f"{'instance' if total == 1 else 'instances'} "
            f"({counts['ERROR']} error, {counts['WARNING']} warning, "
            f"{counts['INFO']} informational)."
        )
    return CategoryResult(
        name="correctness",
        score=score,
        summary=summary,
        findings=findings,
        details={
            "validator_version": report.validator_version,
            "instances_by_severity": counts,
            "distinct_codes": len(findings),
        },
    )


# A feed that ran out more than a year ago has missed at least one full
# service-update cycle. At that point the silence usually means the agency
# moved to a new feed (a regional aggregator, a new vendor URL) and left this
# one behind, not that a still-current export quietly lapsed last month. We
# treat the two cases differently in the directory: a recently lapsed feed is
# a one-line re-export the agency can fix, while a long-dead URL is a prompt to
# re-check the canonical endpoint in the Mobility Database before trusting the
# grade. One year is the dividing line; it is a judgement call, documented here.
# The web app reads this value from web/src/generated/constants.js, rendered by
# `scorecard render-constants`, so there is no hand-kept mirror to sync.
STALE_FEED_DAYS = 365


def expiry_status(days_until_expiry: int | None) -> str:
    """Bucket a feed by how its validity window relates to today.

    Returns one token used across the catalog, the directory, and the app so
    the "expired" population is split consistently:

    - ``current``        service covers 30+ more days
    - ``expiring_soon``  1-30 days of service left
    - ``lapsed``         expired within the last year (likely still running;
                         a re-export fixes it)
    - ``stale``          expired over a year ago (the feed URL may be abandoned
                         or replaced; verify the canonical endpoint first)
    - ``unknown``        no expiry date could be read from the feed
    """
    if days_until_expiry is None:
        return "unknown"
    if days_until_expiry > 30:
        return "current"
    if days_until_expiry > 0:
        return "expiring_soon"
    if days_until_expiry > -STALE_FEED_DAYS:
        return "lapsed"
    return "stale"


def freshness(dates: FeedDates, today: dt.date, service_type: str = "fixed") -> CategoryResult:
    """Score how far into the future the feed remains usable.

    Rationale (rubric.md "Freshness"): the classic small-agency failure is a
    silently expiring feed. Full credit when service data covers 60+ days
    ahead (Caltrans guidance asks agencies to publish well before expiry);
    credit falls linearly to 0 at expiry day. Missing feed_info dates cost
    15 points because nothing can warn the agency before riders notice.

    ``service_type`` ("fixed", "seasonal", "demand_response") fairly handles a
    feed whose calendar gaps are intentional: a recently lapsed seasonal or
    on-demand calendar is reframed and floored rather than scored as a silent
    expiry. The same softening applies when the feed's own calendars encode
    distinct service periods and expiry lands on one of those boundaries
    (``dates.seasonal_boundary``, detected in gtfs.read_feed_dates) — an
    undeclared academic-term feed gets planned-transition framing under its
    own finding code instead of a lapse alarm. A feed expired over a year
    stays serious regardless, so neither path hides a genuinely abandoned feed.
    """
    findings: list[Finding] = []
    details: dict[str, Any] = {
        "has_feed_info": dates.has_feed_info,
        "feed_version": dates.feed_version,
        "service_type": service_type,
        "feed_start_date": dates.feed_start_date.isoformat() if dates.feed_start_date else None,
        "feed_end_date": dates.feed_end_date.isoformat() if dates.feed_end_date else None,
        "last_service_date": (
            dates.last_service_date.isoformat() if dates.last_service_date else None
        ),
        "seasonal_boundary": dates.seasonal_boundary,
    }
    declared_intermittent = service_type in ("seasonal", "demand_response")
    intermittent = declared_intermittent or dates.seasonal_boundary

    expiry = dates.effective_expiry()
    if expiry is None:
        details["days_until_expiry"] = None
        return CategoryResult(
            name="freshness",
            score=0.0,
            summary="No service end date could be found in this feed, so there is "
            "no way to know when riders will lose trip planning.",
            findings=[
                Finding(
                    code="scorecard_no_expiry_date",
                    severity="ERROR",
                    count=1,
                    what="Neither feed_info.txt nor the calendars state when service ends.",
                    why="Nobody can tell when this feed will go stale.",
                    fix="Add feed_start_date and feed_end_date to feed_info.txt and "
                    "include calendar end dates in your export.",
                    effort="Likely a one-time export setting.",
                    deduction=100.0,
                )
            ],
            details=details,
        )

    days_left = (expiry - today).days
    details["days_until_expiry"] = days_left
    date_score = max(0.0, min(1.0, days_left / 60)) * 100.0

    score = date_score
    if days_left <= 0 and intermittent and days_left > -STALE_FEED_DAYS:
        # Recently lapsed calendar on service known (declared) or detected (from
        # the calendars themselves) to run in distinct periods: the gap may be
        # between service periods, so reframe and floor the score rather than
        # scoring it as a silent expiry. Only recent lapses are softened; a feed
        # dead over a year falls through to the hard case below.
        score = max(score, 50.0)
        if declared_intermittent:
            kind = "seasonal" if service_type == "seasonal" else "on-demand"
            summary = (
                f"This {kind} service's published calendar ended {-days_left} day(s) ago. "
                "If the next service period is running, publish its calendar so riders "
                "can plan it."
            )
            findings.append(
                Finding(
                    code="scorecard_intermittent_calendar_ended",
                    severity="WARNING",
                    count=1,
                    what=f"The published calendar for this {kind} service ended "
                    f"{-days_left} day(s) ago.",
                    why="Between service periods this can be expected, but while service is "
                    "running without a published calendar, trip planners show nothing.",
                    fix="Publish the calendar for the current or next service period and set "
                    "feed_info feed_end_date past it.",
                    effort="One export when the next period's schedule is set.",
                    deduction=round(100.0 - score, 1),
                )
            )
        else:
            # Detected, not declared: the calendars encode distinct service
            # periods (e.g. academic terms) and expiry landed on one of those
            # planned boundaries. Frame as a planned transition under its own
            # code so it never reads as a lapse alarm.
            summary = (
                f"This feed's calendar reached a scheduled service boundary "
                f"{-days_left} day(s) ago. Confirm your next service period is "
                "published so riders can keep planning trips."
            )
            findings.append(
                Finding(
                    code="scorecard_planned_service_boundary",
                    severity="WARNING",
                    count=1,
                    what=f"The published calendar ended {-days_left} day(s) ago at a "
                    "boundary between the feed's own scheduled service periods.",
                    why="The calendar encodes distinct service periods (like academic "
                    "terms), so this looks like a planned transition rather than a "
                    "lapse — but trip planners still show nothing until the next "
                    "period is published.",
                    fix="Confirm your next service period is published: export its "
                    "calendar and set feed_info feed_end_date past it.",
                    effort="One export when the next period's schedule is set.",
                    deduction=round(100.0 - score, 1),
                )
            )
    elif days_left <= 0:
        summary = (
            f"Service data ended {-days_left} day(s) ago. Trip planners have "
            "likely already dropped this feed."
        )
        # An expired feed is the most urgent thing an agency can fix, so it must
        # appear as an actionable finding (and rank first), not just a score of 0.
        findings.append(
            Finding(
                code="scorecard_feed_expired",
                severity="ERROR",
                count=1,
                what=f"Service data ended {-days_left} day(s) ago.",
                why="When the calendar runs out, trip planners stop showing this "
                "agency even though the buses are still running. Riders are told "
                "the service does not exist.",
                fix="Re-export the feed with a calendar that reaches further out, and "
                "set feed_info feed_end_date past your next service change.",
                effort="Usually one export setting; export on a schedule so it never lapses again.",
                deduction=100.0,
            )
        )
    elif days_left < 30:
        summary = (
            f"Service data runs out in {days_left} day(s). Publish an updated "
            "feed soon or riders will lose trip planning."
        )
        findings.append(
            Finding(
                code="scorecard_feed_expiring_soon",
                severity="WARNING",
                count=1,
                what=f"Service data runs out in {days_left} day(s).",
                why="When the calendar runs out, trip planners stop showing this "
                "agency. Fixing it now is calmer than after riders notice.",
                fix="Re-export with a validity window that reaches at least 60 days out.",
                effort="One export setting.",
                # Display-only "points this costs" estimate for the finding card.
                # It is NOT the category delta: the score is `date_score` (set
                # above), so the true loss is `100 - score`, as the sibling
                # findings report. This softened curve understates the impact at
                # very low days_left on purpose (a feed 1 day from expiry still
                # works today), so the card reads calmer than the raw score drop.
                # Keep the two in mind as separate numbers; changing this formula
                # is a governed methodology change (see METHODOLOGY_CHANGELOG).
                deduction=round((1 - days_left / 60) * 60 + 20, 1),
            )
        )
    else:
        summary = f"Service data covers the next {days_left} days."

    if not (dates.feed_start_date and dates.feed_end_date):
        score = max(0.0, score - 15.0)
        findings.append(
            Finding(
                code="scorecard_missing_feed_info_dates",
                severity="WARNING",
                count=1,
                what="feed_info.txt is missing its start/end dates"
                + ("" if dates.has_feed_info else " (the file itself is absent)"),
                why="Apps and this scorecard can't warn anyone before the feed goes "
                "stale without stated validity dates.",
                fix="Add feed_info.txt with feed_start_date and feed_end_date to your export.",
                effort="Two fields, set once in export settings.",
                deduction=15.0,
            )
        )

    return CategoryResult(
        name="freshness",
        score=score,
        summary=summary,
        findings=findings,
        details=details,
    )
