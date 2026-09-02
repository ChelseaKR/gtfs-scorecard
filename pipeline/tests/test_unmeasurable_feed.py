"""An archive nobody could read must not be scored as if it had been.

Found downstream on 2026-09-01, against the published `gtfs-scorecard@v1.4.0`
Action. A well-formed zip containing no GTFS files at all was scored, and
published:

    Overall grade: F  (31.3/100)
    Correctness       71.5
    Freshness          0.0
    Rider experience   0.0
    Realtime            --  not yet measured

Two of those categories measured nothing and printed a floor for it. The third
printed the correct thing -- "not yet measured" -- from the same table, so the
renderer already had the vocabulary; freshness and rider experience simply were
not using it. A 0.0 is a measurement. It says a real feed was read and found to
have nothing riders can use, and a reader cannot tell it apart from the archive
that had nothing to read.

The rule these tests pin is narrow on purpose, because the opposite mistake --
excusing a real feed's real 0.0 as "not measurable" -- would hide exactly the
failure this project exists to surface. Only the total absence of the thing
being measured returns None: no table that can carry a service date, or no stops
and no trips at all.
"""

from __future__ import annotations

import argparse
import datetime as dt
import zipfile
from collections.abc import Callable
from pathlib import Path

from scorecard_pipeline.cli import _try_gate
from scorecard_pipeline.completeness import completeness
from scorecard_pipeline.gtfs import read_feed_dates
from scorecard_pipeline.metrics import freshness

TODAY = dt.date(2026, 9, 1)

# A feed that really does describe service. Its calendar has already lapsed, so
# freshness legitimately scores badly -- that is the case that must keep scoring.
LAPSED_FEED = {
    "agency.txt": (
        "agency_id,agency_name,agency_url,agency_timezone\n"
        "a,A Transit,https://example.org,America/Los_Angeles\n"
    ),
    "stops.txt": "stop_id,stop_name\ns1,Main St\ns2,Second St\n",
    "routes.txt": "route_id,agency_id,route_short_name,route_type\nr1,a,1,3\n",
    "trips.txt": "route_id,service_id,trip_id\nr1,svc,t1\n",
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\nsvc,1,1,1,1,1,0,0,20240101,20240201\n"
    ),
}


def _empty_archive(tmp_path: Path) -> Path:
    """A well-formed zip with no GTFS member at all -- the reported input."""
    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", "this archive contains no GTFS files at all\n")
    return path


# --- freshness ---------------------------------------------------------------


def test_an_archive_with_no_date_tables_does_not_measure_freshness(tmp_path: Path) -> None:
    dates = read_feed_dates(str(_empty_archive(tmp_path)))
    assert dates.has_date_tables is False
    assert freshness(dates, TODAY) is None


def test_a_real_lapsed_feed_still_scores_freshness(make_gtfs_zip: Callable[..., Path]) -> None:
    """The narrowness test. A feed whose calendar ran out is measured and bad.

    If the guard ever widened to "no usable end date", this would return None and
    a genuinely expired feed would stop being reported as expired.
    """
    dates = read_feed_dates(str(make_gtfs_zip(LAPSED_FEED)))
    assert dates.has_date_tables is True
    result = freshness(dates, TODAY)
    assert result is not None
    assert result.score == 0.0
    assert result.findings


def test_an_empty_calendar_file_is_still_a_measurement(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    """Present-but-empty is a claim the feed made. Absent is no claim at all."""
    feed = dict(LAPSED_FEED)
    feed["calendar.txt"] = (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
    )
    dates = read_feed_dates(str(make_gtfs_zip(feed)))
    assert dates.has_date_tables is True
    assert freshness(dates, TODAY) is not None


# --- rider experience --------------------------------------------------------


def test_an_archive_with_no_stops_or_trips_does_not_measure_completeness(
    tmp_path: Path,
) -> None:
    assert completeness(str(_empty_archive(tmp_path))) is None


def test_a_feed_with_stops_and_trips_still_scores_completeness(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    result = completeness(str(make_gtfs_zip(LAPSED_FEED)))
    assert result is not None
    assert result.score is not None


def test_the_zero_came_from_presence_checks_with_nothing_present(
    tmp_path: Path,
) -> None:
    """Why the category, not just its components, had to become unmeasurable.

    Four of the six components already returned None for this archive (#286).
    The 0.0 that reached the page was contact and fares, both presence checks,
    both reporting "absent" about a feed that described nothing to begin with.
    """
    assert completeness(str(_empty_archive(tmp_path))) is None


# --- the gate ----------------------------------------------------------------


def _artifact(freshness_status: str, completeness_status: str) -> dict[str, object]:
    return {
        "overall": {"grade": "C", "score": 71.5},
        "categories": {
            "correctness": {"status": "measured", "score": 71.5},
            "freshness": {"status": freshness_status, "details": {"days_until_expiry": 90}},
            "completeness": {"status": completeness_status},
        },
    }


def _no_thresholds() -> argparse.Namespace:
    return argparse.Namespace(min_grade=None, min_days_to_expiry=None)


def test_the_gate_fails_when_nothing_could_be_read_even_with_no_thresholds() -> None:
    """The reported bug: exit 0 and `passed=true` for an unreadable archive.

    The Action derives `passed` straight from this exit code, so a consumer who
    configured no thresholds -- the default -- was told an unreadable feed
    passed.
    """
    artifact = _artifact("not_yet_measured", "not_yet_measured")
    assert _try_gate(artifact, _no_thresholds()) == 1


def test_the_gate_still_passes_a_readable_feed_with_no_thresholds() -> None:
    """ "No thresholds means exit 0" survives for every input that was read."""
    artifact = _artifact("measured", "measured")
    assert _try_gate(artifact, _no_thresholds()) == 0


def test_one_readable_category_is_enough_to_keep_the_no_threshold_pass() -> None:
    """The gate asks whether anything was read, not whether everything was."""
    assert _try_gate(_artifact("measured", "not_yet_measured"), _no_thresholds()) == 0
    assert _try_gate(_artifact("not_yet_measured", "measured"), _no_thresholds()) == 0
