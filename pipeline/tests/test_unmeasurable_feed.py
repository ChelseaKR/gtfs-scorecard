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

Withdrawing those two categories is necessary but not sufficient. Correctness
starts at 100 and deducts per distinct notice code, and an empty archive raises
almost none, so with the other two gone correctness alone carries the overall
and the published letter *rises*: 22 committed scorecards would have gone up,
20 across a band, `beloit-transit` F to B and `boxcar` C to A. The F was
fabricated and so is the B. So the scorer refuses instead: no feed-content
category means no scorecard, by the same ValueError path that already refuses a
response body that is not a zip.

The rule these tests pin is narrow on purpose, because the opposite mistake --
excusing a real feed's real 0.0 as "not measurable" -- would hide exactly the
failure this project exists to surface. Only the total absence of the thing
being measured returns None: no table that can carry a service date, or no stops
and no trips at all. One measurable feed-content category is still graded.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from scorecard_pipeline import cli
from scorecard_pipeline.cli import _try_gate
from scorecard_pipeline.completeness import completeness
from scorecard_pipeline.gtfs import read_feed_dates
from scorecard_pipeline.metrics import freshness
from scorecard_pipeline.score import (
    NOTHING_WAS_READ,
    UnreadableFeedError,
    score_feed_content,
)

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


# --- the refusal -------------------------------------------------------------


def test_an_archive_that_describes_no_service_is_refused_not_graded(tmp_path: Path) -> None:
    """The decision. No feed-content category, so no letter at all.

    Correctness would still score this archive -- an empty zip raises only a
    few notices, and correctness starts at 100 and deducts per distinct code --
    so without this refusal the published grade rises from a fabricated F to an
    equally fabricated B or A. "Could not be read" is the only true answer.
    """
    with pytest.raises(UnreadableFeedError, match="no GTFS schedule data"):
        score_feed_content(str(_empty_archive(tmp_path)), today=TODAY)


def test_a_readable_feed_still_returns_its_categories(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    """The narrowness test for the refusal itself."""
    measured = score_feed_content(str(make_gtfs_zip(LAPSED_FEED)), today=TODAY)
    assert {c.name for c in measured} == {"freshness", "completeness"}


def test_one_measurable_feed_category_is_enough_to_still_be_graded(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    """The refusal asks whether anything was read, not whether everything was.

    A feed with stops and trips but no calendar at all cannot be scored for
    freshness, and is still a feed with a real rider experience to grade.
    """
    feed = {k: v for k, v in LAPSED_FEED.items() if k != "calendar.txt"}
    measured = score_feed_content(str(make_gtfs_zip(feed)), today=TODAY)
    assert {c.name for c in measured} == {"completeness"}


def test_the_refusal_reaches_the_cli_by_the_same_path_as_a_non_zip_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One refusal, two causes, not two concepts.

    `fetch_static` already raises ValueError for a response body that is not a
    zip, and `_cmd_try` reports it as "could not score <url>" and exits 1.
    UnreadableFeedError subclasses ValueError and travels that same path, so no
    handling was added for it -- which is the point.
    """
    args = argparse.Namespace(
        url="https://example.org/gtfs.zip",
        name=None,
        date=TODAY,
        country="US",
        html=None,
        comment=None,
        json_out=None,
        min_grade=None,
        min_days_to_expiry=None,
    )
    parser = argparse.ArgumentParser()

    def _refuse(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise UnreadableFeedError(NOTHING_WAS_READ)

    monkeypatch.setattr(cli, "run_adhoc", _refuse)
    assert cli._cmd_try(args, parser) == 1


# --- the gate ----------------------------------------------------------------


def test_the_gate_no_longer_needs_a_case_for_an_unreadable_archive() -> None:
    """ "No thresholds means exit 0" is a statement about thresholds again.

    The reported bug was `scorecard try` exiting 0 with `passed=true` for an
    unreadable archive. That is now fixed upstream of the gate: no scorecard is
    built for such an archive, so nothing unreadable can reach here.
    """
    artifact = {
        "overall": {"grade": "C", "score": 71.5},
        "categories": {
            "correctness": {"status": "measured", "score": 71.5},
            "freshness": {"status": "measured", "details": {"days_until_expiry": 90}},
            "completeness": {"status": "measured"},
        },
    }
    assert _try_gate(artifact, argparse.Namespace(min_grade=None, min_days_to_expiry=None)) == 0


# --- the published corpus -----------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Published scorecards that grade a feed with zero stops and zero trips, as of
#: 2026-09-01. Every one predates the refusal above: they were minted by a
#: scorer that had no way to say "could not be read", and the daily run can no
#: longer produce or refresh them -- ``score_feed_content`` now raises for these
#: feeds, so each run leaves the stale record in place and warns.
#:
#: Verified live, not inferred: `boxcar`'s feed at
#: https://boxcar-gtfs.vercel.app/api/gtfs is a well-formed GTFS archive whose
#: stops.txt and trips.txt contain a header row and nothing else.
#:
#: Withdrawing them is a listing-policy call (docs/listing-policy.md), not a
#: scoring one, so they are named here rather than deleted. The assertion is a
#: subset, not an equality: this set may only shrink.
STALE_GRADED_EMPTY_FEEDS = frozenset(
    {
        "anaheim-resort-transportation-art",
        "anaheim-resort-transportation-art-100",
        "beloit-transit",
        "beloit-transit-392",
        "boxcar",
        "catalina-express",
        "citrus-county-transit-630",
        "cobb-community-transit-cct-354",
        "detroit-people-mover-417",
        "high-desert-point",
        "high-desert-point-636",
        "hut-airport-shuttle",
        "hut-airport-shuttle-635",
        "jaunt-inc-1324",
        "lakexpress-342",
        "massachusetts-area-express-max",
        "massachusetts-area-express-max-431",
        "miami-dade-transit-331",
        "santa-clarita-transit",
        "santa-clarita-transit-812",
        "staten-island-ferry-518",
        "xpress-2355",
    }
)


def _grades_an_empty_feed(artifact: dict[str, object]) -> bool:
    """Whether a published scorecard carries a letter for a feed with nothing in it."""
    categories = artifact.get("categories")
    overall = artifact.get("overall")
    if not isinstance(categories, dict) or not isinstance(overall, dict):
        return False
    completeness_block = categories.get("completeness")
    if not isinstance(completeness_block, dict) or completeness_block.get("status") != "measured":
        return False
    details = completeness_block.get("details")
    if not isinstance(details, dict):
        return False
    return details.get("stops") == 0 and details.get("trips") == 0 and "grade" in overall


def test_no_new_scorecard_grades_a_feed_with_no_stops_and_no_trips() -> None:
    """A ratchet over the committed corpus. It may only improve.

    The refusal stops the scorer minting another of these. This stops one
    arriving by any other route -- a hand-edited artifact, a hydrated snapshot,
    an import -- and keeps the outstanding set counted rather than forgotten.
    """
    artifacts = REPO_ROOT / "data" / "artifacts"
    found = {
        path.parent.name
        for path in sorted(artifacts.glob("*/latest.json"))
        if _grades_an_empty_feed(json.loads(path.read_text()))
    }
    assert found, "no published artifacts were read; the corpus check is not running"
    new = sorted(found - STALE_GRADED_EMPTY_FEEDS)
    assert not new, (
        f"{len(new)} published scorecard(s) grade a feed with no stops and no trips, "
        "which score_feed_content refuses to produce: " + ", ".join(new)
    )
