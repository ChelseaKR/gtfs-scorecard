"""Tests for the freshness sweep (pure recompute, no file I/O)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from scorecard_pipeline.sweep import can_resweep, needs_sweep, resweep


def _artifact(*, last_service: str | None, fresh_score: float, days: int | None) -> dict[str, Any]:
    """A minimal scored artifact with one finding per measured category, shaped
    like a real published latest.json."""
    return {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "snapshot_date": "2026-06-10",
        "overall": {"score": 80.0, "grade": "B"},
        "top_fixes": [],
        "categories": {
            "correctness": {
                "name": "correctness",
                "status": "measured",
                "score": 90.0,
                "summary": "",
                "weight": 0.35,
                "findings": [
                    {
                        "code": "missing_recommended_field",
                        "severity": "WARNING",
                        "count": 2,
                        "what": "x",
                        "why": "y",
                        "fix": "z",
                        "effort": "",
                        "points": 4.0,
                    }
                ],
                "details": {},
            },
            "freshness": {
                "name": "freshness",
                "status": "measured",
                "score": fresh_score,
                "summary": "",
                "weight": 0.20,
                "findings": [],
                "details": {
                    "has_feed_info": False,
                    "feed_version": None,
                    "service_type": "fixed",
                    "feed_start_date": None,
                    "feed_end_date": None,
                    "last_service_date": last_service,
                    "days_until_expiry": days,
                },
            },
            "completeness": {
                "name": "completeness",
                "status": "measured",
                "score": 60.0,
                "summary": "",
                "weight": 0.25,
                "findings": [],
                "details": {},
            },
            "realtime": {
                "name": "realtime",
                "status": "not_yet_measured",
                "weight": 0.20,
                "summary": "This agency does not publish realtime.",
            },
        },
    }


def test_can_resweep_requires_dated_measured_freshness() -> None:
    assert can_resweep(_artifact(last_service="2026-09-01", fresh_score=85.0, days=83))
    # No expiry date stored: nothing to recompute against.
    assert not can_resweep(_artifact(last_service=None, fresh_score=0.0, days=None))


def test_needs_sweep_skips_feeds_already_scored_on_the_sweep_date() -> None:
    art = _artifact(last_service="2026-09-01", fresh_score=85.0, days=83)  # snapshot 2026-06-10
    # Stale: last full score predates the sweep date, so refresh it.
    assert needs_sweep(art, dt.date(2026, 6, 20)) is True
    # Already current: scored on (or after) the sweep date, so skip — never
    # restamp a same-day full score as a freshness recompute.
    assert needs_sweep(art, dt.date(2026, 6, 10)) is False
    assert needs_sweep(art, dt.date(2026, 6, 5)) is False
    # No dates to recompute against: nothing to sweep.
    assert (
        needs_sweep(_artifact(last_service=None, fresh_score=0.0, days=None), dt.date(2026, 6, 20))
        is False
    )


def test_resweep_drops_grade_when_feed_has_since_expired() -> None:
    # Scored 2026-06-10 with service through 2026-09-01 (current); sweeping months
    # later, after service has ended, must recompute freshness to 0 and re-grade.
    art = _artifact(last_service="2026-02-01", fresh_score=85.0, days=83)
    new, summary = resweep(art, dt.date(2026, 6, 20))

    assert new["categories"]["freshness"]["score"] == 0.0
    assert new["categories"]["freshness"]["details"]["days_until_expiry"] == -139
    assert summary["grade_changed"] is True
    assert summary["new_grade"] != "B"
    # The expired feed becomes the leading fix, ahead of the correctness warning.
    assert new["top_fixes"][0]["code"] == "scorecard_feed_expired"


def test_resweep_overall_is_weighted_average_of_measured_categories() -> None:
    # correctness 90 (0.35), freshness 0 (0.20), completeness 60 (0.25); realtime
    # is not measured, so weights renormalize over 0.80.
    art = _artifact(last_service="2026-02-01", fresh_score=85.0, days=83)
    new, _ = resweep(art, dt.date(2026, 6, 20))
    expected = (90 * 0.35 + 0 * 0.20 + 60 * 0.25) / (0.35 + 0.20 + 0.25)
    assert new["overall"]["score"] == round(expected, 1)


def test_resweep_marks_partial_and_keeps_feed_fetched_date() -> None:
    art = _artifact(last_service="2026-09-01", fresh_score=85.0, days=83)
    new, _ = resweep(art, dt.date(2026, 6, 20))
    assert new["snapshot_date"] == "2026-06-20"
    assert new["recompute"] == {
        "kind": "freshness",
        "as_of": "2026-06-20",
        "feed_fetched_date": "2026-06-10",
    }
    # Not-yet-measured realtime is preserved untouched, not regenerated.
    assert new["categories"]["realtime"]["status"] == "not_yet_measured"
    assert "does not publish realtime" in new["categories"]["realtime"]["summary"]


def test_resweep_keeps_current_feed_current() -> None:
    # Still 70+ days of service left as of the sweep date: the date component is
    # full (100), less the standing 15-point penalty for absent feed_info dates.
    art = _artifact(last_service="2026-09-01", fresh_score=85.0, days=83)
    new, summary = resweep(art, dt.date(2026, 6, 20))
    assert new["categories"]["freshness"]["score"] == 85.0
    assert summary["new_days"] == (dt.date(2026, 9, 1) - dt.date(2026, 6, 20)).days


def test_a_chain_of_sweeps_keeps_naming_the_day_the_feed_was_fetched() -> None:
    """The defect: each sweep took the previous sweep's stamp as a fetch date.

    Sweeps run every cycle, so the published claim became "fetched yesterday"
    for feeds nobody had downloaded in weeks. On 2026-09-13, 468 of the 472
    published recomputes claimed a fetch on 2026-09-12 while carrying the same
    feed_sha256 they had held since 2026-08-10.
    """
    art = _artifact(last_service="2027-09-02", fresh_score=85.0, days=365)
    art["snapshot_date"] = "2026-08-10"  # the day the feed was really downloaded

    first, _ = resweep(art, dt.date(2026, 9, 12))
    assert first["recompute"]["feed_fetched_date"] == "2026-08-10"

    # Sweeping the swept artifact, as the next cycle does.
    second, _ = resweep(first, dt.date(2026, 9, 13))
    assert second["snapshot_date"] == "2026-09-13"
    assert second["recompute"]["as_of"] == "2026-09-13"
    assert second["recompute"]["feed_fetched_date"] == "2026-08-10"

    # And a thirtieth sweep still says the same thing.
    latest = second
    for day in range(14, 30):
        latest, _ = resweep(latest, dt.date(2026, 9, day))
    assert latest["recompute"]["feed_fetched_date"] == "2026-08-10"


def test_a_full_score_after_a_sweep_resets_the_fetch_date() -> None:
    """The rule must not freeze the date: a real fetch is a real fetch.

    A full re-score writes an artifact with no recompute block, so the next
    sweep reads its snapshot_date, which is the day it was downloaded.
    """
    from scorecard_pipeline.sweep import last_fetched_date

    swept = _artifact(last_service="2027-09-02", fresh_score=85.0, days=365)
    swept["snapshot_date"] = "2026-08-10"
    swept, _ = resweep(swept, dt.date(2026, 9, 12))
    assert last_fetched_date(swept) == "2026-08-10"

    rescored = _artifact(last_service="2027-09-02", fresh_score=85.0, days=365)
    rescored["snapshot_date"] = "2026-09-13"
    assert last_fetched_date(rescored) == "2026-09-13"
    swept_again, _ = resweep(rescored, dt.date(2026, 9, 14))
    assert swept_again["recompute"]["feed_fetched_date"] == "2026-09-13"
