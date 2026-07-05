"""Feed time-machine: a plain-language timeline of what changed across an agency's
score history.

The trend chart shows the shape; this narrates it. From the dated history the
pipeline already keeps, it derives a text event for each snapshot where something
changed: a grade move, the feed crossing into or out of the expiry window, or a
notable score swing, naming the category that drove it. A reader, including one
using a screen reader, gets the story without reading a chart.

True GTFS-file diffing (which routes or stops changed) needs the raw feed, which
is not archived; this works from the artifacts on hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import expiry_status

# Friendly category names; "completeness" shows as "rider experience" in the UI.
_CAT_LABELS = {
    "correctness": "correctness",
    "freshness": "freshness",
    "completeness": "rider experience",
    "realtime": "realtime",
}

MIN_SCORE_MOVE = 3.0


@dataclass(frozen=True)
class Event:
    date: str
    kind: str  # grade_change | expiry | score_move | findings
    detail: str


def finding_codes(artifact: dict[str, Any]) -> dict[str, str]:
    """Map each finding code in an artifact to its 'what' text, across measured
    categories. Used to diff one dated run against the next. (render_site imports
    this so the finding-diff logic lives in one place.)"""
    out: dict[str, str] = {}
    for cat in artifact.get("categories", {}).values():
        if cat.get("status") == "measured":
            for f in cat.get("findings", []):
                code = f.get("code")
                if code:
                    out.setdefault(str(code), str(f.get("what", "")))
    return out


def _artifact_date(artifact: dict[str, Any]) -> str:
    return str(artifact.get("snapshot_date") or artifact.get("date") or "")


def _driver(prev_cats: dict[str, Any], curr_cats: dict[str, Any]) -> str | None:
    """The category that moved most between two snapshots, as a phrase, or None
    when nothing moved meaningfully."""
    best_label: str | None = None
    best_delta = 0.0
    for key, label in _CAT_LABELS.items():
        if key in prev_cats and key in curr_cats:
            delta = float(curr_cats[key]) - float(prev_cats[key])
            if abs(delta) > abs(best_delta):
                best_delta = delta
                best_label = label
    if best_label is None or abs(best_delta) < MIN_SCORE_MOVE:
        return None
    verb = "rose" if best_delta > 0 else "fell"
    return f"{best_label} {verb} {abs(round(best_delta))} points"


def _expiry_phrase(prev_status: str, curr_status: str, days: Any) -> str:
    if curr_status in ("lapsed", "stale"):
        return "Feed expired."
    if curr_status == "expiring_soon":
        tail = f" ({int(days)} days of service left)" if isinstance(days, (int, float)) else ""
        return f"Feed entered the expiry window{tail}."
    if curr_status == "current" and prev_status in ("expiring_soon", "lapsed", "stale"):
        return "Feed renewed to a current calendar."
    return f"Feed status changed to {curr_status}."


def history_events(
    history: list[dict[str, Any]], *, min_score_move: float = MIN_SCORE_MOVE
) -> list[Event]:
    """A plain-language event per snapshot where something changed, newest first.

    One event per transition, choosing the most salient change: a grade move wins,
    then an expiry-window crossing, then a notable score swing. A steady feed
    produces nothing."""
    events: list[Event] = []
    for prev, curr in zip(history, history[1:], strict=False):
        date = str(curr.get("date", ""))
        prev_grade, curr_grade = prev.get("grade"), curr.get("grade")
        prev_score, curr_score = prev.get("score"), curr.get("score")
        prev_exp = expiry_status(prev.get("days_until_expiry"))
        curr_exp = expiry_status(curr.get("days_until_expiry"))
        driver = _driver(prev.get("categories", {}), curr.get("categories", {}))

        if curr_grade != prev_grade and curr_grade is not None and prev_grade is not None:
            detail = f"Grade went {prev_grade} to {curr_grade}"
            events.append(Event(date, "grade_change", detail + (f", {driver}." if driver else ".")))
        elif curr_exp != prev_exp:
            phrase = _expiry_phrase(prev_exp, curr_exp, curr.get("days_until_expiry"))
            events.append(Event(date, "expiry", phrase))
        elif (
            isinstance(prev_score, (int, float))
            and isinstance(curr_score, (int, float))
            and abs(curr_score - prev_score) >= min_score_move
        ):
            verb = "rose" if curr_score > prev_score else "fell"
            detail = f"Score {verb} {abs(round(curr_score - prev_score))} points"
            events.append(Event(date, "score_move", detail + (f", {driver}." if driver else ".")))

    return list(reversed(events))


# How many story sentences to spend on transitions between the opening and closing
# grade sentence; keeps ``grade_story`` within its 3-5 sentence bound.
_STORY_MIDDLE_BUDGET = 3


def grade_story(
    history: list[dict[str, Any]], artifacts: list[dict[str, Any]] | None = None
) -> list[str]:
    """A short, deterministic 'grade story': 3-5 dated plain sentences tracing how
    this feed reached its current grade, composed from the same events the timeline
    uses. No LLM.

    The first sentence states the starting grade and its date; the middle sentences
    are the most significant transitions in priority order — grade-band moves first,
    then expiry-window crossings, then cleared findings — and the last sentence
    states the current grade. Every sentence keeps its ISO date so a reader can trace
    it to a specific run. Returns ``[]`` for a single-run (or empty) history. The
    language is correlational, never causal."""
    if len(history) < 2:
        return []

    first, last = history[0], history[-1]
    start_date = str(first.get("date", ""))
    end_date = str(last.get("date", ""))

    story: list[str] = [f"On {start_date} this feed started at grade {first.get('grade')}."]

    middle: list[str] = []
    # 1) Grade-band moves (a changed letter grade), oldest first.
    for prev, curr in zip(history, history[1:], strict=False):
        prev_grade, curr_grade = prev.get("grade"), curr.get("grade")
        if prev_grade is not None and curr_grade is not None and prev_grade != curr_grade:
            date = str(curr.get("date", ""))
            middle.append(f"On {date} the grade moved from {prev_grade} to {curr_grade}.")
    # 2) Expiry-window crossings, oldest first (history_events is newest first).
    for event in reversed(history_events(history)):
        if event.kind == "expiry":
            clause = event.detail[0].lower() + event.detail[1:]
            middle.append(f"On {event.date} {clause}")
    # 3) Cleared findings, oldest first.
    for prev, curr in zip(artifacts or [], (artifacts or [])[1:], strict=False):
        prev_codes = finding_codes(prev)
        cleared = sorted(c for c in prev_codes if c not in finding_codes(curr))
        if cleared:
            middle.append(f"On {_artifact_date(curr)} it cleared {', '.join(cleared)}.")

    if not middle:
        # No band move, expiry crossing, or cleared finding. The grade held, but
        # the score may still have drifted within the band. Say so, using the
        # same whole-point rounding the timeline uses for its "Score rose N
        # points" note, so the story never reads as "held steady" next to a
        # timeline that shows the score moving.
        first_score, last_score = first.get("score"), last.get("score")
        if (
            isinstance(first_score, (int, float))
            and isinstance(last_score, (int, float))
            and round(first_score) != round(last_score)
        ):
            verb = "rose" if last_score > first_score else "fell"
            middle.append(
                f"On {end_date} the grade held, though the score {verb} "
                f"from {round(first_score)} to {round(last_score)}."
            )
        else:
            middle.append(f"On {end_date} the grade held steady.")
    story.extend(middle[:_STORY_MIDDLE_BUDGET])

    story.append(f"As of {end_date} it holds grade {last.get('grade')}.")
    return story
