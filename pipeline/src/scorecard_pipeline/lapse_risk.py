"""Behavioral lapse-risk scoring: flag feeds likely to lapse, ahead of the date.

`alerts.py`'s expiry item is deterministic: it fires once a feed's calendar
falls inside a lead-time window. That is necessary but late — it only speaks up
once the clock has already started ticking loudly. This module looks at the same
dated history the scorecard already keeps (the per-agency "history" list in
index.json, oldest to newest) for *behavioral* patterns that predict a lapse
before the calendar does:

- a feed that has already lapsed and recovered more than once (a repeating
  pattern, not a one-off);
- a feed that has, in the observed window, renewed only after it had already
  gone dark (a late-renewal habit, as opposed to renewing ahead of the
  deadline);
- a feed whose gap between renewals is trending longer (a slowing cadence).

Per the ideation doc (docs/ideation/03-expansions.md, EXP-13) this stays a
transparent heuristic, not a black box: every risk tier comes with the specific,
dated reasons that produced it, so a liaison (never the agency — this is not a
public score) can check the read rather than trust it blindly. It is honest
about its own limits, too: with too little observed history, it says so instead
of guessing.

Wiring this into a digest is a separate concern (see `alerts.py`); here the
logic stays pure and testable against fixture history lists.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

# Fewer than this many dated, readable history entries and there simply isn't
# enough observed behavior to read a pattern from — say so rather than guess.
MIN_HISTORY_ENTRIES = 10

# A day-over-day rise in days-until-expiry, beyond what elapsed calendar time
# alone would explain, counts as a renewal event (the feed's service window
# moved forward) rather than ordinary noise. Mirrors anomaly.py's slack for the
# same signal read in the opposite direction.
RENEWAL_SLACK_DAYS = 3

# A most-recent renewal gap at least this many times the previous gap counts as
# a slowing cadence trend.
CADENCE_SLOWDOWN_RATIO = 1.5

TIER_INSUFFICIENT_HISTORY = "insufficient_history"
TIER_NONE = "none"
TIER_ELEVATED = "elevated"
TIER_HIGH = "high"


@dataclass(frozen=True)
class LapseRiskReason:
    """One dated, inspectable piece of evidence behind a risk tier."""

    code: str
    detail: str


@dataclass(frozen=True)
class LapseRisk:
    """A feed's behavioral lapse-risk read: a tier plus why."""

    tier: str  # insufficient_history | none | elevated | high
    reasons: list[LapseRiskReason] = field(default_factory=list)
    observed_days: int = 0


@dataclass(frozen=True)
class _Point:
    date: dt.date
    days: int


def _points(history: list[dict[str, Any]]) -> list[_Point]:
    """The (date, days_until_expiry) series, oldest to newest, malformed rows dropped."""
    points: list[_Point] = []
    for entry in history:
        raw_days = entry.get("days_until_expiry")
        if isinstance(raw_days, bool) or not isinstance(raw_days, (int, float)):
            continue
        try:
            date = dt.date.fromisoformat(str(entry.get("date")))
        except (ValueError, TypeError):
            continue
        points.append(_Point(date=date, days=int(raw_days)))
    points.sort(key=lambda p: p.date)
    return points


@dataclass(frozen=True)
class _Renewal:
    date: dt.date
    prev_days: int
    new_days: int
    was_late: bool  # renewed after the previous window had already lapsed


def _renewals(points: list[_Point]) -> list[_Renewal]:
    """Detect renewal events: the service window moving forward.

    Ordinary day-to-day movement is days_until_expiry falling by roughly the
    calendar days elapsed. A rise well past that — beyond what elapsed time
    could explain — means a new feed_end_date was published.
    """
    renewals: list[_Renewal] = []
    # Deliberately not strict=True: this pairs each point with its successor,
    # so the second sequence is always exactly one shorter by construction.
    for prev, curr in zip(points, points[1:], strict=False):
        elapsed = (curr.date - prev.date).days
        if elapsed <= 0:
            continue
        # How much the window moved forward, net of the days that simply passed.
        gain = (curr.days - prev.days) + elapsed
        if gain <= RENEWAL_SLACK_DAYS:
            continue
        renewals.append(
            _Renewal(
                date=curr.date,
                prev_days=prev.days,
                new_days=curr.days,
                was_late=prev.days < 0,
            )
        )
    return renewals


def _lapse_episodes(points: list[_Point]) -> int:
    """Count distinct lapse episodes: transitions from current/expiring into lapsed."""
    episodes = 0
    was_lapsed = False
    for point in points:
        is_lapsed = point.days < 0
        if is_lapsed and not was_lapsed:
            episodes += 1
        was_lapsed = is_lapsed
    return episodes


def assess(history: list[dict[str, Any]]) -> LapseRisk:
    """Read a lapse-risk tier and its reasons from one agency's dated history.

    `history` is the per-agency "history" list from index.json, in any order
    (sorted here), where each entry looks like
    {"date", "grade", "score", "days_until_expiry", ...}. Entries missing a
    readable date or days_until_expiry are skipped rather than raising.
    """
    points = _points(history)
    if len(points) < MIN_HISTORY_ENTRIES:
        return LapseRisk(
            tier=TIER_INSUFFICIENT_HISTORY,
            reasons=[
                LapseRiskReason(
                    code="insufficient_history",
                    detail=(
                        f"Only {len(points)} day(s) of readable history observed; "
                        f"{MIN_HISTORY_ENTRIES}+ are needed before a behavioral "
                        "lapse-risk read is trustworthy."
                    ),
                )
            ],
            observed_days=len(points),
        )

    reasons: list[LapseRiskReason] = []
    renewals = _renewals(points)

    late_renewals = [r for r in renewals if r.was_late]
    if late_renewals:
        latest = late_renewals[-1]
        late_by = abs(latest.prev_days)
        reasons.append(
            LapseRiskReason(
                code="late_renewal_history",
                detail=(
                    f"Renewed {late_by} day(s) after the previous service window had "
                    f"already lapsed, most recently on {latest.date.isoformat()}. "
                    "A feed that has renewed late before is more likely to cut it "
                    "close again."
                ),
            )
        )

    episodes = _lapse_episodes(points)
    if episodes >= 2:
        span = (points[-1].date - points[0].date).days
        reasons.append(
            LapseRiskReason(
                code="recurring_lapse",
                detail=(
                    f"The service window lapsed and was renewed {episodes} separate "
                    f"times in the {span} day(s) observed. A repeating lapse-and-"
                    "recover pattern tends to repeat again near the next expiry date."
                ),
            )
        )

    if len(renewals) >= 3:
        gaps = [
            (b.date - a.date).days
            for a, b in zip(renewals, renewals[1:], strict=False)
            if (b.date - a.date).days > 0
        ]
        if len(gaps) >= 2 and gaps[-2] > 0 and gaps[-1] >= gaps[-2] * CADENCE_SLOWDOWN_RATIO:
            reasons.append(
                LapseRiskReason(
                    code="slowing_cadence",
                    detail=(
                        f"The gap between renewals is trending longer: the most recent "
                        f"gap was {gaps[-1]} day(s), versus {gaps[-2]} day(s) before "
                        "that. A stretching renewal cadence is often the first sign of "
                        "a feed about to go quiet."
                    ),
                )
            )

    if not reasons:
        tier = TIER_NONE
    elif len(reasons) == 1:
        tier = TIER_ELEVATED
    else:
        tier = TIER_HIGH

    return LapseRisk(tier=tier, reasons=reasons, observed_days=len(points))
