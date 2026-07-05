"""Tests for empirical fix-effort calibration: runs-to-clear episodes and bands."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.effort_calibration import (
    MIN_SAMPLES,
    Episode,
    agency_episodes,
    band_text,
    build_clear_stats,
    stats_from_episodes,
)


def _artifact(date: str, *codes: str, measured: bool = True) -> dict[str, Any]:
    """One dated artifact with the given correctness codes present, or an
    unmeasured correctness category when ``measured`` is False."""
    return {
        "snapshot_date": date,
        "categories": {
            "correctness": {
                "status": "measured" if measured else "skipped",
                "findings": [{"code": c, "what": f"{c} finding"} for c in codes],
            }
        },
    }


def test_code_clears_after_three_runs_yields_one_sample_with_day_count() -> None:
    # Present on three consecutive daily runs, then verified gone on the fourth.
    # first-seen is the first run; the sample is (cleared - first_seen).days.
    artifacts = [
        _artifact("2026-06-01", "expired_calendar"),
        _artifact("2026-06-02", "expired_calendar"),
        _artifact("2026-06-03", "expired_calendar"),
        _artifact("2026-06-04"),  # cleared, category still measured
    ]
    episodes = agency_episodes(artifacts)
    assert episodes == [Episode("expired_calendar", "2026-06-01", "2026-06-04")]
    stats = stats_from_episodes(episodes)
    assert stats["expired_calendar"]["samples"] == 1
    assert stats["expired_calendar"]["median_days"] == 3
    assert stats["expired_calendar"]["still_open"] == 0


def test_unmeasured_category_does_not_count_as_cleared() -> None:
    # The code disappears only because the category went unmeasured (failed
    # fetch). That is invisible, not fixed: no sample, still counted open.
    artifacts = [
        _artifact("2026-06-01", "stop_too_far_from_shape"),
        _artifact("2026-06-02", measured=False),
        _artifact("2026-06-03", measured=False),
    ]
    episodes = agency_episodes(artifacts)
    assert episodes == [Episode("stop_too_far_from_shape", "2026-06-01", None)]
    stats = stats_from_episodes(episodes)
    assert stats["stop_too_far_from_shape"]["samples"] == 0
    assert stats["stop_too_far_from_shape"]["still_open"] == 1
    assert "median_days" not in stats["stop_too_far_from_shape"]


def test_recurrence_yields_two_episodes() -> None:
    # Clears, comes back, clears again: two distinct episodes with their own
    # first-seen dates and day counts.
    artifacts = [
        _artifact("2026-06-01", "missing_timepoint"),
        _artifact("2026-06-03"),  # first clear (2 days)
        _artifact("2026-06-10", "missing_timepoint"),  # recurs
        _artifact("2026-06-15"),  # second clear (5 days)
    ]
    episodes = agency_episodes(artifacts)
    assert episodes == [
        Episode("missing_timepoint", "2026-06-01", "2026-06-03"),
        Episode("missing_timepoint", "2026-06-10", "2026-06-15"),
    ]
    stats = stats_from_episodes(episodes)
    assert stats["missing_timepoint"]["samples"] == 2
    assert stats["missing_timepoint"]["median_days"] == 4  # median of [2, 5] = 3.5 -> 4


def test_build_clear_stats_pools_multiple_agencies() -> None:
    # Two agencies, each contributing one episode for the same code.
    agency_a = [_artifact("2026-06-01", "x"), _artifact("2026-06-05")]  # 4 days
    agency_b = [_artifact("2026-06-01", "x"), _artifact("2026-06-09")]  # 8 days
    stats = build_clear_stats([agency_a, agency_b])
    assert stats["x"]["samples"] == 2
    assert stats["x"]["median_days"] == 6  # median of [4, 8]


def test_below_min_samples_yields_no_band() -> None:
    # Four closed episodes is under the floor of five, so no band is quoted.
    stats = {"samples": MIN_SAMPLES - 1, "median_days": 14, "p25": 10, "p75": 20}
    assert band_text(stats) is None


def test_band_wording_is_stable() -> None:
    # At or above the floor the band reads in week-rounded plain language and
    # names the sample size.
    stats = {"samples": 12, "median_days": 14, "p25": 9, "p75": 21}
    assert band_text(stats) == (
        "Agencies here usually clear this within about 2 weeks (based on 12 observed fixes)."
    )


def test_band_wording_singular_week() -> None:
    stats = {"samples": 6, "median_days": 5, "p25": 3, "p75": 8}
    assert band_text(stats) == (
        "Agencies here usually clear this within about 1 week (based on 6 observed fixes)."
    )
