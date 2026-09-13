"""Tests for the freshness sweep (pure recompute, plus the command that applies it)."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import pytest

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


def _artifact_over_an_empty_archive() -> dict[str, Any]:
    """A published scorecard shaped like `boxcar`'s on 2026-09-13.

    Its rider-experience category is `measured` over an archive holding 0 stops
    and 0 trips, because it was scored before `score_feed_content` learned to
    refuse such an archive (#331). Freshness carries real dates, so the sweep
    can recompute it and would otherwise re-stamp the whole record.
    """
    art = _artifact(last_service="2027-09-02", fresh_score=100.0, days=365)
    art["agency"] = {"id": "boxcar", "name": "Boxcar Commuter Bus"}
    art["overall"] = {"score": 83.9, "grade": "B"}
    art["categories"]["freshness"]["details"]["feed_end_date"] = "2027-09-02"
    art["categories"]["completeness"]["details"] = {
        "stops": 0,
        "trips": 0,
        "components": {"contact": 15.0, "fares": 0.0},
        "unmeasured_components": ["headsigns", "stop_names"],
    }
    return art


def test_a_grade_over_an_empty_archive_is_not_swept_to_a_new_date() -> None:
    # The defect: the sweep carries correctness, rider experience and realtime
    # forward untouched, so a letter the scorer now refuses to produce was
    # re-published with today's date every cycle. boxcar published B 83.9 this
    # way on 2026-09-13, over an archive its own artifact records as 0 stops
    # and 0 trips.
    art = _artifact_over_an_empty_archive()
    assert can_resweep(art), "freshness is recomputable, so only the new rule can hold it back"
    assert needs_sweep(art, dt.date(2026, 9, 13)) is False


def test_a_real_measurement_is_still_swept() -> None:
    # The rule is narrow: an archive that was actually read still sweeps.
    art = _artifact_over_an_empty_archive()
    art["categories"]["completeness"]["details"] = {"stops": 296, "trips": 1794}
    assert needs_sweep(art, dt.date(2026, 9, 13)) is True


def test_the_sweep_command_names_what_it_held_back_and_leaves_it_undated(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole command, not the predicate: the held-back record keeps its own
    date, a real one beside it is still swept, and the holding back is said out
    loud. A skip nobody is told about is how this ran for days."""
    import argparse

    from scorecard_pipeline import cli, config

    root = tmp_path / "data" / "artifacts"
    empty_dir = root / "boxcar"
    real_dir = root / "unitrans"
    for directory in (empty_dir, real_dir):
        directory.mkdir(parents=True)
    empty = _artifact_over_an_empty_archive()
    real = _artifact_over_an_empty_archive()
    real["agency"] = {"id": "unitrans", "name": "Unitrans"}
    real["categories"]["completeness"]["details"] = {"stops": 296, "trips": 1794}
    (empty_dir / "latest.json").write_text(json.dumps(empty))
    (real_dir / "latest.json").write_text(json.dumps(real))
    monkeypatch.setattr(config, "artifacts_dir", lambda: root)

    changed = tmp_path / "changed.txt"
    args = argparse.Namespace(date=dt.date(2026, 9, 13), apply=False, changed_out=str(changed))
    with caplog.at_level(logging.WARNING):
        assert cli._cmd_freshness_sweep(args, argparse.ArgumentParser()) == 0

    # The record over an empty archive is not among those the sweep would refresh;
    # the feed that was actually read still is.
    assert changed.read_text().split() == ["unitrans"]
    # And the reader of the log is told which record was held back, and why.
    assert "no stops and no trips" in caplog.text
    assert "boxcar" in caplog.text
    assert "corrections.yaml" in caplog.text
