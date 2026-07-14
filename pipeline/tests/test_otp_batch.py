"""Tests for the weekly OTP routing-QA batch (pure): selection and verdict."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.otp import RoutingQA
from scorecard_pipeline.otp_batch import (
    assess_batch,
    matrix_entries,
    select_best_worst,
)


def _index(scores: dict[str, float | None]) -> dict[str, Any]:
    """A published index with one latest history point per agency."""
    return {
        "agencies": {
            agency_id: {
                "name": agency_id.title(),
                "history": [
                    {
                        "date": "2026-07-01",
                        "grade": "B",
                        "score": score,
                        "days_until_expiry": 30,
                    }
                ],
            }
            for agency_id, score in scores.items()
        }
    }


def _urls(*ids: str) -> dict[str, str]:
    return {agency_id: f"https://feeds.example.org/{agency_id}.zip" for agency_id in ids}


def test_select_best_worst_picks_both_extremes() -> None:
    index = _index({"a": 95.0, "b": 40.0, "c": 72.5, "d": 88.0, "e": 15.0})
    chosen = select_best_worst(index, _urls("a", "b", "c", "d", "e"), count=2)
    assert [(f.feed_id, f.cohort) for f in chosen] == [
        ("a", "best"),
        ("d", "best"),
        ("e", "worst"),
        ("b", "worst"),
    ]
    assert chosen[0].score == 95.0
    assert chosen[2].score == 15.0  # worst cohort leads with the lowest score
    assert chosen[0].feed_url == "https://feeds.example.org/a.zip"


def test_select_is_deterministic_with_tied_scores() -> None:
    index = _index({"zeta": 80.0, "alpha": 80.0, "mid": 50.0, "low": 10.0})
    urls = _urls("zeta", "alpha", "mid", "low")
    chosen = select_best_worst(index, urls, count=1)
    # Ties break by id, so re-running the selection picks the same feeds.
    assert [f.feed_id for f in chosen] == ["alpha", "low"]
    assert [f.feed_id for f in select_best_worst(index, urls, count=1)] == ["alpha", "low"]


def test_select_skips_unscored_and_unfetchable_feeds() -> None:
    index = _index({"scored": 60.0, "unscored": None, "no-url": 99.0})
    index["agencies"]["never-ran"] = {"name": "Never Ran", "history": []}
    chosen = select_best_worst(index, _urls("scored", "unscored", "never-ran"), count=2)
    # Only "scored" both has a score and a URL; it fills the best cohort alone.
    assert [(f.feed_id, f.cohort) for f in chosen] == [("scored", "best")]


def test_select_skips_expired_and_unknown_service_windows() -> None:
    index = _index({"current": 60.0, "expired": 10.0, "unknown": 90.0})
    index["agencies"]["expired"]["history"][0]["days_until_expiry"] = -1
    index["agencies"]["unknown"]["history"][0]["days_until_expiry"] = None
    chosen = select_best_worst(index, _urls("current", "expired", "unknown"), count=2)
    assert [(f.feed_id, f.cohort) for f in chosen] == [("current", "best")]


def test_select_never_queues_a_feed_twice() -> None:
    index = _index({"a": 90.0, "b": 50.0, "c": 20.0})
    chosen = select_best_worst(index, _urls("a", "b", "c"), count=2)
    # Best fills first (a, b); worst takes only the remainder (c).
    assert [(f.feed_id, f.cohort) for f in chosen] == [
        ("a", "best"),
        ("b", "best"),
        ("c", "worst"),
    ]
    assert len({f.feed_id for f in chosen}) == len(chosen)


def test_select_with_no_candidates_is_empty() -> None:
    assert select_best_worst({"agencies": {}}, {}, count=2) == []


def test_matrix_entries_are_json_ready_strings() -> None:
    index = _index({"a": 90.0, "b": 10.0})
    entries = matrix_entries(select_best_worst(index, _urls("a", "b"), count=1))
    assert entries == [
        {"feed_id": "a", "feed_url": "https://feeds.example.org/a.zip", "cohort": "best"},
        {"feed_id": "b", "feed_url": "https://feeds.example.org/b.zip", "cohort": "worst"},
    ]


def test_assess_batch_verdict() -> None:
    verdict = assess_batch(
        [
            ("good", RoutingQA(pairs_tested=5, pairs_routable=5, failures=[])),
            ("bad", RoutingQA(pairs_tested=5, pairs_routable=3, failures=["PATH_NOT_FOUND", "x"])),
        ]
    )
    assert verdict.feeds_tested == 2
    assert verdict.feeds_routable == 1
    assert verdict.all_routable is False
    assert verdict.routable_share == 0.5
    assert verdict.failures == ["bad: PATH_NOT_FOUND", "bad: x"]


def test_assess_batch_all_pass() -> None:
    verdict = assess_batch([("good", RoutingQA(pairs_tested=3, pairs_routable=3, failures=[]))])
    assert verdict.all_routable is True
    assert verdict.failures == []


def test_assess_batch_feed_with_no_pairs_is_a_failure_not_a_pass() -> None:
    verdict = assess_batch([("empty", RoutingQA(pairs_tested=0, pairs_routable=0, failures=[]))])
    assert verdict.all_routable is False
    assert verdict.failures == ["empty: no origin/destination pairs tested"]


def test_assess_batch_empty_is_not_routable() -> None:
    verdict = assess_batch([])
    assert verdict.all_routable is False
    assert verdict.routable_share == 0.0
