"""A feed wrapped in directories is read, not published as a fabricated grade.

Issue #333, measured 2026-09-01. GitLab's archive endpoint wraps whatever it
serves in ``<repo>-<ref>-<path>/<path>/``, two folders deep. Two California
listings are fetched from it:

    gtfs_lax-master-santa_clarita/santa_clarita/stops.txt   364 stops
    gtfs_lax-master-santa_clarita/santa_clarita/trips.txt   898 trips

The reader view only knew how to strip one folder, so both feeds reached the
table readers with every name unresolved. Every count came back 0, and
``santa-clarita-transit`` published **F (26.2)** with ``completeness 0.0``,
``freshness 0.0`` and ``"stops": 0, "trips": 0`` in its details, for a feed that
is healthy. ``catalina-express`` published the same letter from the same
endpoint. Both artifacts are still the live ones on the public site.

That is the "absence rendered as a value" class in its worst direction: a reader
failure printed as a real letter against a named agency, which has nothing to
fix and no way to tell from the page that the tool, not the feed, is at fault.

These tests pin both halves of the rule the issue asks for. The feed that can be
found is read and scored on its real contents. The archive that carries two
feeds is not resolved at all: it stays unreadable and is refused, rather than
having one of its directories picked for it.
"""

from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path

import pytest

from scorecard_pipeline.fetch import prepare_reader_archive
from scorecard_pipeline.gtfs import read_feed_dates, read_tables
from scorecard_pipeline.score import build_scorecard, score_feed_content

TODAY = dt.date(2026, 9, 1)

#: The wrapper GitLab puts around ``?path=santa_clarita``.
GITLAB_PREFIX = "gtfs_lax-master-santa_clarita/santa_clarita/"

#: A feed that is fine: stops, trips, a calendar running well past ``TODAY``.
#: Nothing here should score an F, and nothing here should score 0.0.
HEALTHY_FEED = {
    "agency.txt": (
        "agency_id,agency_name,agency_url,agency_timezone,agency_phone\n"
        "sct,Santa Clarita Transit,https://example.org,America/Los_Angeles,661-295-6300\n"
    ),
    "stops.txt": (
        "stop_id,stop_name,stop_lat,stop_lon,wheelchair_boarding\n"
        "s1,Main Street and 6th,34.39,-118.54,1\n"
        "s2,Soledad Canyon and Bouquet,34.40,-118.55,1\n"
    ),
    "routes.txt": (
        "route_id,agency_id,route_short_name,route_long_name,route_type,"
        "route_color,route_text_color\n"
        "r1,sct,1,Downtown Shuttle,3,0000FF,FFFFFF\n"
    ),
    "trips.txt": (
        "route_id,service_id,trip_id,trip_headsign,wheelchair_accessible\nr1,svc,t1,Downtown,1\n"
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "t1,08:00:00,08:00:00,s1,1\n"
        "t1,08:10:00,08:10:00,s2,2\n"
    ),
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\n"
        "svc,1,1,1,1,1,0,0,20260101,20271231\n"
    ),
    "feed_info.txt": (
        "feed_publisher_name,feed_publisher_url,feed_lang,feed_start_date,"
        "feed_end_date,feed_version\n"
        "Santa Clarita Transit,https://example.org,en,20260101,20271231,v1\n"
    ),
}


def _write_archive(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return path


def _nested(prefix: str, files: dict[str, str]) -> dict[str, str]:
    return {prefix + name: text for name, text in files.items()}


def _reader_view(path: Path) -> Path:
    return prepare_reader_archive(path).path


def test_gitlab_wrapped_feed_is_read_instead_of_reading_as_empty(tmp_path: Path) -> None:
    """The reported archive shape resolves to the feed inside it.

    Before the fix ``prepare_reader_archive`` refused anything more than one
    folder deep, so the readers were handed the raw archive and found no table
    at any name they asked for.
    """
    raw = _write_archive(tmp_path / "gtfs.zip", _nested(GITLAB_PREFIX, HEALTHY_FEED))

    view = _reader_view(raw)

    tables = read_tables(str(view), ["stops.txt", "trips.txt", "routes.txt", "agency.txt"])
    assert {name: len(rows) for name, rows in tables.items()} == {
        "stops.txt": 2,
        "trips.txt": 1,
        "routes.txt": 1,
        "agency.txt": 1,
    }
    dates = read_feed_dates(str(view))
    assert dates.has_date_tables is True
    assert dates.has_service_content is True
    assert dates.feed_end_date == dt.date(2027, 12, 31)


def test_wrapping_a_feed_in_folders_does_not_change_its_grade(tmp_path: Path) -> None:
    """The same feed scores the same whether or not a producer wrapped it.

    This is the published harm stated as an assertion: the nested archive must
    not come back as two measured 0.0s, and must not come back as an F.
    """
    flat = _write_archive(tmp_path / "flat.zip", HEALTHY_FEED)
    nested = _write_archive(tmp_path / "nested.zip", _nested(GITLAB_PREFIX, HEALTHY_FEED))

    flat_card = build_scorecard(score_feed_content(str(_reader_view(flat)), today=TODAY))
    nested_card = build_scorecard(score_feed_content(str(_reader_view(nested)), today=TODAY))

    assert nested_card.grade == flat_card.grade
    assert nested_card.overall_score == pytest.approx(flat_card.overall_score)
    assert nested_card.grade != "F"
    scores = {name: category.score for name, category in nested_card.categories.items()}
    assert scores["freshness"] > 0.0
    assert scores["completeness"] > 0.0


def test_a_feed_wrapped_in_one_folder_still_reads_the_same_way(tmp_path: Path) -> None:
    """One folder deep was already handled and must keep behaving identically."""
    one_deep = _write_archive(tmp_path / "one.zip", _nested("feed/", HEALTHY_FEED))
    two_deep = _write_archive(tmp_path / "two.zip", _nested("export/feed/", HEALTHY_FEED))

    with zipfile.ZipFile(_reader_view(one_deep)) as view:
        one_names = view.namelist()
    with zipfile.ZipFile(_reader_view(two_deep)) as view:
        two_names = view.namelist()

    assert one_names == sorted(HEALTHY_FEED)
    assert two_names == one_names


def test_a_flat_archive_is_read_exactly_as_it_is(tmp_path: Path) -> None:
    """A feed already at the archive root gets no view and no transform.

    The guard the issue asks for alongside the fix: resolving names against the
    members must not change what a conformant archive's bytes read as. This one
    holds on both sides of the fix by design.
    """
    flat = _write_archive(tmp_path / "flat.zip", HEALTHY_FEED)
    before = flat.read_bytes()

    prepared = prepare_reader_archive(flat)

    assert prepared.normalized is False
    assert prepared.path == flat
    assert flat.read_bytes() == before


def test_extras_beside_the_feed_directory_do_not_hide_it(tmp_path: Path) -> None:
    """A licence file at the root is not a GTFS table, so it does not win.

    Root names are still preferred over a directory's, but only when the root
    actually holds the table being asked for. A producer who ships a README
    beside the feed folder is not shipping an empty feed.
    """
    raw = _write_archive(
        tmp_path / "gtfs.zip",
        {"README.md": "producer notes", **_nested("feed/", HEALTHY_FEED)},
    )

    tables = read_tables(str(_reader_view(raw)), ["stops.txt", "trips.txt"])

    assert [len(rows) for rows in tables.values()] == [2, 1]


def test_two_feeds_in_one_archive_stay_unreadable(tmp_path: Path) -> None:
    """An ambiguous bundle is refused for being ambiguous, not for being deep.

    A wrapper holding two agencies' feeds must never be scored as if it were one
    agency's. The message matters as much as the refusal: before the fix this
    archive was rejected for its depth, which is a rule that would have let the
    bundle through as soon as depth was allowed.
    """
    raw = _write_archive(
        tmp_path / "gtfs.zip",
        {
            **_nested("bundle/santa_clarita/", HEALTHY_FEED),
            **_nested("bundle/catalina_express/", HEALTHY_FEED),
        },
    )

    with pytest.raises(ValueError, match="multiple possible root folders carrying GTFS tables"):
        prepare_reader_archive(raw)


def test_an_archive_with_no_feed_in_it_is_still_refused(tmp_path: Path) -> None:
    """Resolving names must not turn "nothing to read" into something to grade.

    The other half of the rule. An archive that carries no GTFS table anywhere
    has no directory to resolve to, so the readers find nothing and the scorer
    refuses, exactly as it did before.
    """
    raw = _write_archive(tmp_path / "gtfs.zip", {"docs/readme.txt": "no feed here"})

    with pytest.raises(ValueError, match="no GTFS schedule data could be read"):
        score_feed_content(str(_reader_view(raw)), today=TODAY)
