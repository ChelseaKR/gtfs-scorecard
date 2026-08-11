"""Catch implausible single-step shifts in an agency's score history.

A feed pipeline occasionally publishes one bad snapshot: a stale export served
for a single day scores an F, then the next day's run recovers to a B. That is
not a real regression, it is a transient glitch, and treating it as a genuine
slide would send a misleading alert to the agency. This module looks at the
dated history the scorecard already keeps (the per-agency "history" list in
index.json, oldest to newest) and points out steps that are too large or too
abrupt to be a normal day-to-day change.

This is a heads-up layer, not a verdict: every finding names what looks off and
leaves the judgement to the person reading it. Wiring it into the digest or the
site is a separate pass; here the logic stays pure and testable.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

# A one-step move of this many points or more is bigger than ordinary validator
# wobble or a routine export change, so it is worth a second look.
SCORE_CLIFF_POINTS = 20.0

# How much further days-until-expiry may fall in one step than the calendar days
# that actually passed. A little slack absorbs rounding and a feed that updates
# slightly off the daily cadence; a drop well past this means the service window
# itself moved backward rather than time simply elapsing.
EXPIRY_SLACK_DAYS = 3
EXPIRY_REGRESSION_POINTS = 10

# A single date counts as a transient dip when both the day before and the day
# after score at least this many points higher: a one-day hole that recovered.
TRANSIENT_DIP_POINTS = 20.0

# History rows are not always consecutive days: a feed on the standard cadence,
# a paused pipeline, or a newly added agency all leave gaps, and roughly one
# published step in twelve spans more than a day. A dip is only "transient" if
# the neighbouring rows sit that close in time; across a longer gap the low
# score stood for however long the gap lasted, which is a regression to alert on
# rather than a glitch to suppress. Two days allows one missed daily run.
TRANSIENT_DIP_MAX_STEP_DAYS = 2


@dataclass(frozen=True)
class Anomaly:
    """One history step or point that looks off, framed as a heads-up.

    `kind` is a stable machine tag ("score_cliff", "expiry_regression",
    "transient_dip"); `detail` is the plain-language note for a reader.
    """

    date: str
    kind: str
    detail: str


def _score(entry: dict[str, Any]) -> float | None:
    raw = entry.get("score")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def _expiry(entry: dict[str, Any]) -> int | None:
    raw = entry.get("days_until_expiry")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return int(raw)


def _days_between(earlier: str, later: str) -> int | None:
    """Calendar days from one ISO date to the next, or None if either is unparseable."""
    try:
        start = dt.date.fromisoformat(earlier)
        end = dt.date.fromisoformat(later)
    except (ValueError, TypeError):
        return None
    return (end - start).days


def _score_cliff(prev: dict[str, Any], curr: dict[str, Any]) -> Anomaly | None:
    prev_score, curr_score = _score(prev), _score(curr)
    if prev_score is None or curr_score is None:
        return None
    delta = curr_score - prev_score
    if abs(delta) < SCORE_CLIFF_POINTS:
        return None
    direction = "fell" if delta < 0 else "rose"
    return Anomaly(
        date=str(curr.get("date", "")),
        kind="score_cliff",
        detail=(
            f"The score {direction} {abs(delta):.0f} points in one step, from "
            f"{prev_score:.0f} on {prev.get('date')} to {curr_score:.0f} on "
            f"{curr.get('date')}. A jump this size usually means the export "
            "changed rather than the service. Worth checking the run on this date."
        ),
    )


def _expiry_regression(prev: dict[str, Any], curr: dict[str, Any]) -> Anomaly | None:
    prev_days, curr_days = _expiry(prev), _expiry(curr)
    if prev_days is None or curr_days is None:
        return None
    elapsed = _days_between(str(prev.get("date")), str(curr.get("date")))
    if elapsed is None:
        return None
    # As time passes, days-until-expiry should shrink by about the days elapsed.
    # A drop well past that means the feed's service window moved backward.
    expected_drop = elapsed
    actual_drop = prev_days - curr_days
    overshoot = actual_drop - expected_drop
    if overshoot <= EXPIRY_SLACK_DAYS + EXPIRY_REGRESSION_POINTS:
        return None
    return Anomaly(
        date=str(curr.get("date", "")),
        kind="expiry_regression",
        detail=(
            f"Days until the service window ends dropped by {actual_drop} between "
            f"{prev.get('date')} and {curr.get('date')}, but only {elapsed} day(s) "
            "passed. The feed's calendar appears to have moved backward, which can "
            "happen when an older export is republished. Worth confirming the latest "
            "export is the one being served."
        ),
    )


def _transient_dip(
    prev: dict[str, Any], curr: dict[str, Any], nxt: dict[str, Any]
) -> Anomaly | None:
    prev_score, curr_score, next_score = _score(prev), _score(curr), _score(nxt)
    if prev_score is None or curr_score is None or next_score is None:
        return None
    # Only a dip bracketed by nearby checks is evidence of a glitch. Unreadable
    # or distant dates mean the low score may have stood for weeks, so stay
    # quiet: a suppressed alert about a real regression costs the agency more
    # than an extra alert about a glitch.
    before = _days_between(str(prev.get("date")), str(curr.get("date")))
    after = _days_between(str(curr.get("date")), str(nxt.get("date")))
    if before is None or after is None:
        return None
    if not (0 < before <= TRANSIENT_DIP_MAX_STEP_DAYS and 0 < after <= TRANSIENT_DIP_MAX_STEP_DAYS):
        return None
    if (
        prev_score - curr_score >= TRANSIENT_DIP_POINTS
        and next_score - curr_score >= TRANSIENT_DIP_POINTS
    ):
        return Anomaly(
            date=str(curr.get("date", "")),
            kind="transient_dip",
            detail=(
                f"The score dropped to {curr_score:.0f} on {curr.get('date')} and was "
                f"back to {next_score:.0f} at the next check on {nxt.get('date')} "
                f"(it was {prev_score:.0f} on {prev.get('date')}). A dip that bounced "
                "straight back is usually a stale export served briefly, not a real "
                "change in the feed."
            ),
        )
    return None


def detect_anomalies(history: list[dict[str, Any]]) -> list[Anomaly]:
    """Find implausible single-step shifts in one agency's dated score history.

    `history` is the per-agency "history" list from index.json, sorted oldest to
    newest, where each entry looks like
    {"date", "grade", "score", "days_until_expiry", "categories": {...}}.

    Returns the anomalies in date order. Histories with fewer than two entries
    have no step to compare and return an empty list. Malformed or missing fields
    on a given entry skip the checks that need them rather than raising.
    """
    anomalies: list[Anomaly] = []
    if len(history) < 2:
        return anomalies

    for i in range(1, len(history)):
        prev, curr = history[i - 1], history[i]
        cliff = _score_cliff(prev, curr)
        if cliff is not None:
            anomalies.append(cliff)
        expiry = _expiry_regression(prev, curr)
        if expiry is not None:
            anomalies.append(expiry)

    # A transient dip needs a date and both of its neighbours, so it starts at the
    # second entry and stops before the last.
    for i in range(1, len(history) - 1):
        dip = _transient_dip(history[i - 1], history[i], history[i + 1])
        if dip is not None:
            anomalies.append(dip)

    # Date order keeps the report readable; the per-date checks above already run
    # oldest to newest, so a stable sort on date preserves their relative order.
    anomalies.sort(key=lambda a: a.date)
    return anomalies


def latest_anomaly(history: list[dict[str, Any]]) -> Anomaly | None:
    """The most recent anomaly in the history, or None if there are none."""
    anomalies = detect_anomalies(history)
    if not anomalies:
        return None
    return anomalies[-1]
