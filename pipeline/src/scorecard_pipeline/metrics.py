"""Phase 1 scorecard metrics: Correctness and Freshness.

Each metric here documents its own scoring rationale; the full methodology
with citations lives in docs/rubric.md and must stay in sync.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
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

# A date more than ten calendar years beyond the check is far outside ordinary
# schedule publishing, but GTFS does not forbid it. Treat it as a review signal,
# not a validity error or a score deduction. Ten years deliberately leaves room
# for legitimate multi-year planning while catching sentinel-like dates such as
# 2100. Calendar years (rather than a fixed day count) keep leap years from
# moving the boundary.
SERVICE_HORIZON_REVIEW_YEARS = 10


def _years_after(value: dt.date, years: int) -> dt.date:
    """Return the same calendar date ``years`` later, clamping leap day."""
    if value.year > dt.date.max.year - years:
        return dt.date.max
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        # The only valid date that cannot be replaced this way is February 29
        # in a target year without a leap day.
        return value.replace(year=value.year + years, day=28)


def service_horizon_status(expiry: dt.date | None, today: dt.date) -> str:
    """Classify an end date without turning a review threshold into a rule.

    ``unusually_distant`` means strictly more than ten calendar years after the
    check date. The boundary itself remains ``within_review_threshold``. An
    unknown expiry stays ``unknown`` rather than being treated as normal.
    """
    if expiry is None:
        return "unknown"
    if expiry > _years_after(today, SERVICE_HORIZON_REVIEW_YEARS):
        return "unusually_distant"
    return "within_review_threshold"


def _published_date(value: Any) -> dt.date | None:
    """Read a published ISO date without making a wall-clock assumption."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        return None


def resolve_service_horizon_status(
    values: Mapping[str, Any], snapshot_date: dt.date | str | None = None
) -> str:
    """Return the explicit horizon status or derive it for legacy records.

    Artifacts and index/catalog rows published before schema 1.10 have no
    ``service_horizon_status``. Derive the same strict calendar-year threshold
    from their immutable snapshot plus either ``effective_expiry_date`` or
    ``days_until_expiry`` so the first deploy does not expose a sentinel-like
    countdown. Records with no usable dates stay ``unknown``.
    """
    explicit = values.get("service_horizon_status")
    if explicit in ("within_review_threshold", "unusually_distant", "unknown"):
        return str(explicit)

    checked = _published_date(
        snapshot_date if snapshot_date is not None else values.get("snapshot_date")
    )
    if checked is None:
        checked = _published_date(values.get("date"))
    if checked is None:
        return "unknown"

    expiry = _published_date(values.get("effective_expiry_date"))
    if expiry is None:
        days = values.get("days_until_expiry")
        if isinstance(days, bool) or not isinstance(days, (int, float)):
            return "unknown"
        if isinstance(days, float) and (not days.is_integer() or not math.isfinite(days)):
            return "unknown"
        try:
            expiry = checked + dt.timedelta(days=int(days))
        except OverflowError:
            return "unknown"
    return service_horizon_status(expiry, checked)


def presented_freshness_summary(
    category: Mapping[str, Any], snapshot_date: dt.date | str | None = None
) -> str:
    """Return freshness summary copy that is safe for legacy artifacts.

    Pre-1.10 artifacts embedded the raw countdown in ``summary``. Presentation
    and assistant surfaces use this adapter so an old sentinel-like horizon is
    disclosed as a trust advisory without rewriting immutable artifacts.
    """
    summary = str(category.get("summary") or "")
    details = category.get("details")
    if not isinstance(details, Mapping):
        return summary
    if resolve_service_horizon_status(details, snapshot_date) != "unusually_distant":
        return summary
    end = _published_date(details.get("effective_expiry_date"))
    through = f" through {end.isoformat()}" if end else " to an unusually distant date"
    return (
        f"Service is published{through}. It may be intentional, but confirm the end date "
        "before treating the feed as maintained."
    )


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


# 30 consecutive failed liveness checks (liveness.py) is long enough that "the
# server had a bad day" stops being the likely explanation, while staying clear
# of an ordinary blip -- an outage, a lapsed certificate -- that recovers within
# a few checks. Deliberately a check *count*, not a calendar duration: a stale
# feed is "standard" cadence tier (cadence.py), checked a few times a day, not
# once, so "30 failures" is roughly a week, not a month -- and the exact
# elapsed time depends on cadence.py's tiering, which this module does not
# import and should not assume. Callers should describe this as a streak of
# checks, not translate it into a specific number of days.
UNREACHABLE_STREAK_CHECKS = 30


def operating_signal(status: str, consecutive_failures: int) -> str:
    """Whether an expired feed's URL is itself still being served, a neutral
    read that stops short of guessing at the agency's operating status.

    Only meaningful once a feed has already expired (``status`` "lapsed" or
    "stale", from `expiry_status`); returns "" for a current or expiring-soon
    feed, since there is nothing to classify yet. The distinction this adds is
    not "is the agency running" -- that is exactly the guess this stays
    neutral about -- but a narrower, automatic, already-observed fact:

    - ``"reachable"``   the feed's URL still answers; only the calendar went
                        stale, not the hosting behind it.
    - ``"unreachable"`` the URL itself has failed every check for at least
                        `UNREACHABLE_STREAK_CHECKS` running: a stronger and
                        separate signal from an old calendar, worth reading
                        differently in a caseload view. Still not proof the
                        agency stopped -- a moved feed URL or a dropped
                        Mobility Database listing look the same from here.
    """
    if status not in ("lapsed", "stale"):
        return ""
    return "unreachable" if consecutive_failures >= UNREACHABLE_STREAK_CHECKS else "reachable"


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
    horizon_status = service_horizon_status(expiry, today)
    details["effective_expiry_date"] = expiry.isoformat() if expiry else None
    details["service_horizon_status"] = horizon_status
    details["service_horizon_review_years"] = SERVICE_HORIZON_REVIEW_YEARS
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
                    what=f"This {kind} service has no published calendar. The last "
                    f"one ended {-days_left} day(s) ago.",
                    why="Between service periods this is normal. But if buses are "
                    "running with no published calendar, trip planners show nothing.",
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
                    what=f"The published calendar ended {-days_left} day(s) ago, "
                    "right where one of the feed's own service periods ends.",
                    why="The calendar sets out separate service periods, such as "
                    "school terms. So this reads as a planned change, not a lapse. "
                    "Trip planners still show nothing until you publish the next "
                    "period.",
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
                fix="Re-export the feed with a calendar that reaches further out. "
                "Set feed_end_date in feed_info.txt past your next service change.",
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
    elif horizon_status == "unusually_distant":
        # GTFS permits this date. Keep the existing full-credit score while
        # making clear that a distant end date alone is not evidence that the
        # feed is actively maintained. This is summary/detail metadata, not a
        # category finding, so finding prevalence, diffs, and Top 3 stay stable.
        summary = (
            f"Service is published through {expiry.isoformat()}, an unusually distant "
            "end date. It may be intentional, but confirm it before treating the feed "
            "as maintained."
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
