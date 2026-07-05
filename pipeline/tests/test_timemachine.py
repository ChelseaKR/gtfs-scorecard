"""Tests for the feed time-machine history narrative (pure)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.timemachine import (
    grade_story,
    history_events,
)


def _pt(date: str, score: float, grade: str, days: int | None, **cats: float) -> dict[str, Any]:
    return {
        "date": date,
        "score": score,
        "grade": grade,
        "days_until_expiry": days,
        "categories": cats,
    }


def test_grade_change_names_the_driving_category_and_sorts_newest_first() -> None:
    history = [
        _pt("2026-06-10", 84.0, "B", 80, correctness=90.0, freshness=85.0),
        _pt("2026-06-14", 70.0, "C", 78, correctness=90.0, freshness=40.0),
        _pt("2026-06-16", 84.0, "B", 76, correctness=90.0, freshness=85.0),
    ]
    events = history_events(history)
    # Newest first: the recovery, then the dip.
    assert [e.date for e in events] == ["2026-06-16", "2026-06-14"]
    assert events[1].kind == "grade_change"
    assert "Grade went B to C" in events[1].detail
    assert "freshness fell 45 points" in events[1].detail


def test_expiry_window_crossing_is_reported() -> None:
    history = [
        _pt("2026-06-10", 80.0, "B", 60),  # current
        _pt("2026-06-12", 79.0, "B", 20),  # expiring_soon
    ]
    events = history_events(history)
    assert len(events) == 1
    assert events[0].kind == "expiry"
    assert "expiry window" in events[0].detail and "20 days" in events[0].detail


def test_feed_expired_phrasing_when_grade_holds() -> None:
    # Same grade but the calendar lapsed, so the expiry branch fires.
    events = history_events([_pt("a", 60, "C", 5), _pt("b", 58, "C", -2)])
    assert events[0].kind == "expiry"
    assert events[0].detail == "Feed expired."


def test_grade_change_wins_over_expiry_when_both_move() -> None:
    renewed = history_events(
        [_pt("a", 0, "F", -5, freshness=0.0), _pt("b", 80, "B", 90, freshness=85.0)]
    )
    assert renewed[0].kind == "grade_change"


def test_score_move_without_grade_change() -> None:
    history = [
        _pt("2026-06-10", 84.0, "B", 80, completeness=60.0),
        _pt("2026-06-12", 88.0, "B", 79, completeness=70.0),
    ]
    events = history_events(history)
    assert events[0].kind == "score_move"
    assert "Score rose 4 points" in events[0].detail
    assert "rider experience rose 10 points" in events[0].detail


def test_steady_history_and_short_history_produce_no_events() -> None:
    steady = [_pt("a", 84.0, "B", 80), _pt("b", 84.5, "B", 79), _pt("c", 84.0, "B", 78)]
    assert history_events(steady) == []
    assert history_events([_pt("a", 84.0, "B", 80)]) == []
    assert history_events([]) == []


def _artifact(date: str, *codes: str) -> dict[str, Any]:
    """A minimal dated artifact carrying finding codes under a measured category."""
    return {
        "snapshot_date": date,
        "categories": {
            "correctness": {
                "status": "measured",
                "findings": [{"code": c, "what": f"{c} detail"} for c in codes],
            }
        },
    }


def test_grade_story_is_stable_dated_and_within_bound() -> None:
    history = [
        _pt("2026-06-10", 84.0, "B", 80, freshness=85.0),
        _pt("2026-06-14", 70.0, "C", 78, freshness=40.0),
        _pt("2026-06-18", 88.0, "A", 30, freshness=90.0),
    ]
    artifacts = [
        _artifact("2026-06-10", "missing_feed_contact"),
        _artifact("2026-06-14", "missing_feed_contact"),
        _artifact("2026-06-18"),
    ]
    story = grade_story(history, artifacts)
    # Deterministic, byte-for-byte stable composition.
    assert story == [
        "On 2026-06-10 this feed started at grade B.",
        "On 2026-06-14 the grade moved from B to C.",
        "On 2026-06-18 the grade moved from C to A.",
        "On 2026-06-18 it cleared missing_feed_contact.",
        "As of 2026-06-18 it holds grade A.",
    ]
    assert 3 <= len(story) <= 5
    # Every sentence stays traceable to a run via its ISO date.
    assert all("202" in s for s in story)


def test_grade_story_fills_a_steady_middle_when_no_transitions() -> None:
    history = [_pt("2026-06-10", 84.0, "B", 80), _pt("2026-06-14", 84.2, "B", 79)]
    story = grade_story(history)
    assert story == [
        "On 2026-06-10 this feed started at grade B.",
        "On 2026-06-14 the grade held steady.",
        "As of 2026-06-14 it holds grade B.",
    ]


def test_grade_story_caps_middle_and_reports_expiry_transitions() -> None:
    history = [
        _pt("2026-06-10", 84.0, "B", 80),
        _pt("2026-06-12", 79.0, "B", 20),  # enters expiry window
        _pt("2026-06-14", 60.0, "C", 10),  # grade move
        _pt("2026-06-16", 90.0, "A", 90),  # grade move + renewed
    ]
    story = grade_story(history)
    assert story[0] == "On 2026-06-10 this feed started at grade B."
    assert story[-1] == "As of 2026-06-16 it holds grade A."
    assert len(story) == 5  # capped at start + 3 transitions + end
    # Grade-band moves are listed before expiry crossings.
    assert "moved from B to C" in story[1]
    assert "expiry window" in " ".join(story)


def test_grade_story_empty_for_single_run_history() -> None:
    assert grade_story([_pt("2026-06-10", 84.0, "B", 80)]) == []
    assert grade_story([]) == []
