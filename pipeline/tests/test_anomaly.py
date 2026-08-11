"""Tests for single-step anomaly detection on an agency's score history."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.anomaly import (
    Anomaly,
    detect_anomalies,
    latest_anomaly,
)


def entry(
    date: str,
    score: float,
    grade: str,
    days_until_expiry: int | None = 120,
) -> dict[str, Any]:
    """A history row in the same shape as index.json's per-agency history."""
    return {
        "date": date,
        "score": score,
        "grade": grade,
        "days_until_expiry": days_until_expiry,
        "categories": {"correctness": score},
    }


def test_steady_history_has_no_anomalies() -> None:
    # A daily feed losing one expiry day per calendar day, scores wobbling within
    # validator noise. Nothing here should be flagged.
    history = [
        entry("2026-06-10", 88.0, "B", days_until_expiry=120),
        entry("2026-06-11", 87.0, "B", days_until_expiry=119),
        entry("2026-06-12", 89.0, "B", days_until_expiry=118),
        entry("2026-06-13", 88.0, "B", days_until_expiry=117),
    ]
    assert detect_anomalies(history) == []
    assert latest_anomaly(history) is None


def test_score_cliff_is_flagged() -> None:
    history = [
        entry("2026-06-10", 88.0, "B", days_until_expiry=120),
        entry("2026-06-11", 60.0, "D", days_until_expiry=119),
        entry("2026-06-12", 58.0, "F", days_until_expiry=118),
    ]
    anomalies = detect_anomalies(history)
    kinds = {a.kind for a in anomalies}
    assert "score_cliff" in kinds
    cliff = next(a for a in anomalies if a.kind == "score_cliff")
    assert cliff.date == "2026-06-11"


def test_small_score_moves_are_not_a_cliff() -> None:
    history = [
        entry("2026-06-10", 88.0, "B"),
        entry("2026-06-11", 71.0, "C"),  # 17-point drop, below the threshold
    ]
    assert [a for a in detect_anomalies(history) if a.kind == "score_cliff"] == []


def test_expiry_regression_is_flagged() -> None:
    # One calendar day passed, but days-until-expiry fell by 45: the service
    # window moved backward, e.g. an older export was republished.
    history = [
        entry("2026-06-10", 88.0, "B", days_until_expiry=60),
        entry("2026-06-11", 88.0, "B", days_until_expiry=15),
    ]
    anomalies = detect_anomalies(history)
    regressions = [a for a in anomalies if a.kind == "expiry_regression"]
    assert len(regressions) == 1
    assert regressions[0].date == "2026-06-11"


def test_normal_expiry_countdown_is_not_a_regression() -> None:
    # Expiry shrinks one day per calendar day; that is exactly expected.
    history = [
        entry("2026-06-10", 88.0, "B", days_until_expiry=30),
        entry("2026-06-11", 88.0, "B", days_until_expiry=29),
        entry("2026-06-12", 88.0, "B", days_until_expiry=28),
    ]
    assert [a for a in detect_anomalies(history) if a.kind == "expiry_regression"] == []


def test_transient_one_day_dip_then_recovery() -> None:
    # The motivating case: a stale export scores F for a day, then recovers to B.
    history = [
        entry("2026-06-10", 85.0, "B", days_until_expiry=120),
        entry("2026-06-11", 40.0, "F", days_until_expiry=119),
        entry("2026-06-12", 84.0, "B", days_until_expiry=118),
    ]
    anomalies = detect_anomalies(history)
    dips = [a for a in anomalies if a.kind == "transient_dip"]
    assert len(dips) == 1
    assert dips[0].date == "2026-06-11"
    # The recovery is the most recent thing of interest; the dip is the anomaly.
    assert latest_anomaly(history) is not None


def test_drop_that_stood_for_weeks_is_not_a_transient_dip() -> None:
    # 8% of published history steps are not consecutive days (1,114 of them are
    # 27-day gaps), so neighbouring rows are not neighbouring days. A feed that
    # scored 40 on 06-11 and was next seen at 90 on 07-08 was broken for nearly
    # a month; calling that a one-day glitch both misstates the evidence and,
    # via alerts._anomaly_alert_items, suppresses the alert the agency needs.
    history = [
        entry("2026-06-10", 85.0, "B", days_until_expiry=120),
        entry("2026-06-11", 40.0, "F", days_until_expiry=119),
        entry("2026-07-08", 84.0, "B", days_until_expiry=92),
    ]
    assert [a for a in detect_anomalies(history) if a.kind == "transient_dip"] == []


def test_dip_survives_one_missed_run() -> None:
    # A skipped daily run (a 2-day step, 857 of those published) still leaves a
    # genuinely transient dip detectable.
    history = [
        entry("2026-06-10", 85.0, "B", days_until_expiry=120),
        entry("2026-06-11", 40.0, "F", days_until_expiry=119),
        entry("2026-06-13", 84.0, "B", days_until_expiry=117),
    ]
    dips = [a for a in detect_anomalies(history) if a.kind == "transient_dip"]
    assert len(dips) == 1


def test_transient_dip_copy_does_not_promise_a_next_day_recovery() -> None:
    history = [
        entry("2026-06-10", 85.0, "B"),
        entry("2026-06-11", 40.0, "F"),
        entry("2026-06-13", 84.0, "B"),
    ]
    dip = next(a for a in detect_anomalies(history) if a.kind == "transient_dip")
    assert "the next day" not in dip.detail


def test_undated_history_rows_are_not_called_transient() -> None:
    # No dates means no way to know how long the dip lasted. Stay quiet about
    # transience rather than suppress a possible real regression.
    history: list[dict[str, Any]] = [
        {"score": 85.0, "grade": "B"},
        {"score": 40.0, "grade": "F"},
        {"score": 84.0, "grade": "B"},
    ]
    assert [a for a in detect_anomalies(history) if a.kind == "transient_dip"] == []


def test_sustained_drop_is_not_a_transient_dip() -> None:
    # Drops and stays down: a real regression, not a one-day glitch.
    history = [
        entry("2026-06-10", 85.0, "B"),
        entry("2026-06-11", 40.0, "F"),
        entry("2026-06-12", 41.0, "F"),
    ]
    assert [a for a in detect_anomalies(history) if a.kind == "transient_dip"] == []


def test_latest_anomaly_returns_most_recent() -> None:
    history = [
        entry("2026-06-10", 88.0, "B"),
        entry("2026-06-11", 60.0, "D"),  # early cliff
        entry("2026-06-12", 61.0, "D"),
        entry("2026-06-13", 30.0, "F"),  # later cliff
        entry("2026-06-14", 62.0, "D"),  # recovery, makes 06-13 a transient dip too
    ]
    latest = latest_anomaly(history)
    assert latest is not None
    assert latest.date == "2026-06-14" or latest.date == "2026-06-13"
    # The most recent anomaly date should not predate a later one.
    anomalies = detect_anomalies(history)
    assert latest.date == anomalies[-1].date


def test_short_histories_return_empty() -> None:
    assert detect_anomalies([]) == []
    assert detect_anomalies([entry("2026-06-10", 88.0, "B")]) == []
    assert latest_anomaly([]) is None
    assert latest_anomaly([entry("2026-06-10", 88.0, "B")]) is None


def test_two_entry_history_can_still_cliff_but_never_dips() -> None:
    history = [
        entry("2026-06-10", 88.0, "B"),
        entry("2026-06-11", 50.0, "F"),
    ]
    anomalies = detect_anomalies(history)
    assert any(a.kind == "score_cliff" for a in anomalies)
    assert all(a.kind != "transient_dip" for a in anomalies)


def test_malformed_entries_do_not_raise() -> None:
    history: list[dict[str, Any]] = [
        {"date": "2026-06-10", "grade": "B"},  # no score, no expiry
        {"date": "2026-06-11", "score": "oops", "grade": "F"},  # non-numeric score
        {"date": "2026-06-12", "score": 88.0, "grade": "B", "days_until_expiry": None},
    ]
    # Should simply skip the checks it cannot run.
    assert detect_anomalies(history) == []


def test_anomaly_is_frozen() -> None:
    a = Anomaly(date="2026-06-11", kind="score_cliff", detail="x")
    try:
        a.date = "2026-06-12"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Anomaly should be frozen")
