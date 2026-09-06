"""Tests for the minimal GTFS readers behind the freshness category."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path

import pytest

from scorecard_pipeline.gtfs import (
    TableTooLargeError,
    iter_table_rows,
    read_agency_ids,
    read_feed_dates,
    read_shapes_coverage,
)

CALENDAR_HEADER = (
    "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
)


def test_iter_table_rows_streams_and_respects_a_task_cap(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    path = make_gtfs_zip({"stop_times.txt": ("trip_id,stop_id,stop_sequence\nT1,S1,1\nT1,S2,2\n")})

    rows = list(iter_table_rows(str(path), "stop_times.txt"))
    assert [row["stop_id"] for row in rows] == ["S1", "S2"]
    assert list(iter_table_rows(str(path), "missing.txt")) == []

    with pytest.raises(TableTooLargeError, match="analysis cap"):
        list(iter_table_rows(str(path), "stop_times.txt", max_member_bytes=1))

    # None means no size check at all. A streamed table's memory cost is set by
    # what the caller keeps, not by the table, so a caller folding it into a
    # bounded aggregate has nothing to protect and every reason to measure the
    # feed it was handed.
    rows = list(iter_table_rows(str(path), "stop_times.txt", max_member_bytes=None))
    assert [row["stop_id"] for row in rows] == ["S1", "S2"]


def test_reads_feed_info_and_calendar(make_gtfs_zip: Callable[..., Path]) -> None:
    path = make_gtfs_zip(
        {
            "feed_info.txt": (
                "feed_publisher_name,feed_publisher_url,feed_lang,"
                "feed_start_date,feed_end_date,feed_version\n"
                "Unitrans,https://unitrans.ucdavis.edu,en,20260601,20260915,SU26\n"
            ),
            "calendar.txt": CALENDAR_HEADER + "WK,1,1,1,1,1,0,0,20260601,20260820\n",
            "calendar_dates.txt": "service_id,date,exception_type\nWK,20260904,1\n",
        }
    )
    dates = read_feed_dates(str(path))
    assert dates.has_feed_info
    assert dates.feed_publisher_name == "Unitrans"
    assert dates.feed_version == "SU26"
    assert dates.feed_end_date == dt.date(2026, 9, 15)
    # added service on 9/4 extends past the calendar end of 8/20
    assert dates.last_service_date == dt.date(2026, 9, 4)
    # expiry is the earlier of feed_info end and last service date
    assert dates.effective_expiry() == dt.date(2026, 9, 4)


def test_missing_feed_info_and_calendar_dates(make_gtfs_zip: Callable[..., Path]) -> None:
    path = make_gtfs_zip({"calendar.txt": CALENDAR_HEADER + "WK,1,1,1,1,1,0,0,20260601,20260820\n"})
    dates = read_feed_dates(str(path))
    assert not dates.has_feed_info
    assert dates.feed_end_date is None
    assert dates.effective_expiry() == dt.date(2026, 8, 20)


def test_removed_service_exceptions_do_not_extend_expiry(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    path = make_gtfs_zip(
        {
            "calendar.txt": CALENDAR_HEADER + "WK,1,1,1,1,1,0,0,20260601,20260820\n",
            "calendar_dates.txt": "service_id,date,exception_type\nWK,20261225,2\n",
        }
    )
    assert read_feed_dates(str(path)).last_service_date == dt.date(2026, 8, 20)


def test_empty_feed_has_no_expiry(make_gtfs_zip: Callable[..., Path]) -> None:
    path = make_gtfs_zip({"stops.txt": "stop_id,stop_name\n"})
    dates = read_feed_dates(str(path))
    assert dates.effective_expiry() is None


def test_malformed_dates_are_ignored(make_gtfs_zip: Callable[..., Path]) -> None:
    path = make_gtfs_zip(
        {"calendar.txt": CALENDAR_HEADER + "WK,1,1,1,1,1,0,0,2026-06-01,not_a_date\n"}
    )
    assert read_feed_dates(str(path)).effective_expiry() is None


class TestSeasonalBoundary:
    def test_two_disjoint_terms_set_boundary(self, make_gtfs_zip: Callable[..., Path]) -> None:
        # Fall and spring terms separated by a month-long break: the feed
        # encodes distinct service periods and expiry is the spring term's end.
        path = make_gtfs_zip(
            {
                "calendar.txt": CALENDAR_HEADER
                + "FALL,1,1,1,1,1,0,0,20250922,20251212\n"
                + "SPRING,1,1,1,1,1,0,0,20260112,20260605\n",
            }
        )
        dates = read_feed_dates(str(path))
        assert dates.seasonal_boundary
        assert dates.effective_expiry() == dt.date(2026, 6, 5)

    def test_single_continuous_span_never_triggers(
        self, make_gtfs_zip: Callable[..., Path]
    ) -> None:
        path = make_gtfs_zip(
            {"calendar.txt": CALENDAR_HEADER + "WK,1,1,1,1,1,0,0,20260101,20261231\n"}
        )
        assert not read_feed_dates(str(path)).seasonal_boundary

    def test_overlapping_calendars_merge_to_one_span(
        self, make_gtfs_zip: Callable[..., Path]
    ) -> None:
        # Weekday and weekend calendars overlap; merged they are one continuous
        # period, so no boundary is detected.
        path = make_gtfs_zip(
            {
                "calendar.txt": CALENDAR_HEADER
                + "WK,1,1,1,1,1,0,0,20260101,20260630\n"
                + "WE,0,0,0,0,0,1,1,20260101,20260630\n",
            }
        )
        assert not read_feed_dates(str(path)).seasonal_boundary

    def test_short_gap_reads_as_continuous(self, make_gtfs_zip: Callable[..., Path]) -> None:
        # A one-week holiday closure between calendars is under the 14-day
        # seasonal threshold and must not soften anything.
        path = make_gtfs_zip(
            {
                "calendar.txt": CALENDAR_HEADER
                + "A,1,1,1,1,1,0,0,20260101,20260320\n"
                + "B,1,1,1,1,1,0,0,20260328,20260630\n",
            }
        )
        assert not read_feed_dates(str(path)).seasonal_boundary

    def test_feed_info_end_inside_a_term_is_not_a_boundary(
        self, make_gtfs_zip: Callable[..., Path]
    ) -> None:
        # Distinct terms exist, but feed_info expires the feed mid-term, so the
        # expiry does not coincide with a planned boundary.
        path = make_gtfs_zip(
            {
                "feed_info.txt": (
                    "feed_publisher_name,feed_publisher_url,feed_lang,"
                    "feed_start_date,feed_end_date\n"
                    "Test,https://ex.org,en,20250922,20260401\n"
                ),
                "calendar.txt": CALENDAR_HEADER
                + "FALL,1,1,1,1,1,0,0,20250922,20251212\n"
                + "SPRING,1,1,1,1,1,0,0,20260112,20260605\n",
            }
        )
        dates = read_feed_dates(str(path))
        assert dates.effective_expiry() == dt.date(2026, 4, 1)
        assert not dates.seasonal_boundary

    def test_added_service_bridging_the_gap_defeats_detection(
        self, make_gtfs_zip: Callable[..., Path]
    ) -> None:
        # calendar_dates additions inside the break shrink the service-free gap
        # below the threshold, so the terms read as one period with pauses.
        added = "".join(f"HOLIDAY,202512{day:02d},1\n" for day in range(13, 32)) + "".join(
            f"HOLIDAY,202601{day:02d},1\n" for day in range(1, 12)
        )
        path = make_gtfs_zip(
            {
                "calendar.txt": CALENDAR_HEADER
                + "FALL,1,1,1,1,1,0,0,20250922,20251212\n"
                + "SPRING,1,1,1,1,1,0,0,20260112,20260605\n",
                "calendar_dates.txt": "service_id,date,exception_type\n" + added,
            }
        )
        assert not read_feed_dates(str(path)).seasonal_boundary

    def test_malformed_active_row_disables_detection(
        self, make_gtfs_zip: Callable[..., Path]
    ) -> None:
        # An active calendar without a parseable start date makes the span
        # picture untrustworthy; stay conservative rather than invent a gap.
        path = make_gtfs_zip(
            {
                "calendar.txt": CALENDAR_HEADER
                + "FALL,1,1,1,1,1,0,0,not_a_date,20251212\n"
                + "SPRING,1,1,1,1,1,0,0,20260112,20260605\n",
            }
        )
        assert not read_feed_dates(str(path)).seasonal_boundary


def test_read_agency_ids_distinct_and_ordered(make_gtfs_zip: Callable[..., Path]) -> None:
    path = make_gtfs_zip(
        {
            "agency.txt": (
                "agency_id,agency_name,agency_url,agency_timezone\n"
                "90142,Unitrans,https://ex.org,America/Los_Angeles\n"
                "90142,Unitrans Dup,https://ex.org,America/Los_Angeles\n"
                " ,Blank,https://ex.org,America/Los_Angeles\n"
                "OTHER,Other,https://ex.org,America/Los_Angeles\n"
            )
        }
    )
    assert read_agency_ids(str(path)) == ["90142", "OTHER"]


def test_read_agency_ids_empty_when_unset(make_gtfs_zip: Callable[..., Path]) -> None:
    # The parser reports absence without raising. The RY2026 NTD assessment,
    # rather than the GTFS reader, turns this into a required-presence finding.
    path = make_gtfs_zip(
        {"agency.txt": "agency_name,agency_url,agency_timezone\nUnitrans,https://ex.org,UTC\n"}
    )
    assert read_agency_ids(str(path)) == []


def test_read_shapes_coverage_counts_trips_with_a_real_shape(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    path = make_gtfs_zip(
        {
            "shapes.txt": (
                "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
                "S1,38.5,-121.7,0\nS1,38.6,-121.8,1\n"
            ),
            "trips.txt": (
                "route_id,service_id,trip_id,shape_id\n"
                "R1,WK,T1,S1\nR1,WK,T2,S1\nR1,WK,T3,\nR1,WK,T4,DANGLING\n"
            ),
        }
    )
    coverage = read_shapes_coverage(str(path))
    assert coverage.total_trips == 4
    # T3 has no shape_id and T4 references a shape not present in shapes.txt.
    assert coverage.trips_with_shape == 2


def test_read_shapes_coverage_empty_when_no_shapes_file(make_gtfs_zip: Callable[..., Path]) -> None:
    path = make_gtfs_zip({"trips.txt": "route_id,service_id,trip_id\nR1,WK,T1\nR1,WK,T2\n"})
    coverage = read_shapes_coverage(str(path))
    assert coverage.total_trips == 2
    assert coverage.trips_with_shape == 0


def test_read_shapes_coverage_no_trips(make_gtfs_zip: Callable[..., Path]) -> None:
    path = make_gtfs_zip({"stops.txt": "stop_id,stop_name\nS1,Main St\n"})
    coverage = read_shapes_coverage(str(path))
    assert coverage.total_trips == 0
    assert coverage.trips_with_shape == 0


# Byte sequences a producer can put in front of, or between, the rows of a
# GTFS table. _has_data_row decides has_service_content, so a table it cannot
# split into rows is published as a feed that describes no service -- an
# absence written where a measurement goes.
UTF8_BOM = b"\xef\xbb\xbf"


@pytest.mark.parametrize(
    ("stops", "trips"),
    [
        pytest.param(
            b"stop_id,stop_name\rS1,Main St\r",
            b"route_id,service_id,trip_id\r",
            id="carriage-return line endings",
        ),
        pytest.param(
            UTF8_BOM + b"stop_id,stop_name\rS1,Main St\r",
            UTF8_BOM + b"route_id,service_id,trip_id\r",
            id="a UTF-8 BOM in front of carriage-return line endings",
        ),
    ],
)
def test_a_readable_stops_table_is_service_content_whatever_ends_its_lines(
    make_gtfs_zip: Callable[..., Path], stops: bytes, trips: bytes
) -> None:
    """A stop is a stop however the producer terminated the line it sits on.

    Read as bytes, a table whose rows end in a bare CR is one long line, so the
    header consumes the whole file and nothing is left to be a data row. The
    feed then publishes has_service_content=False -- "this archive describes no
    service" -- for an archive that describes a stop. Decoding through
    TextIOWrapper with newline="" splits on CR, LF and CRLF alike, so the
    question the reader answers stops depending on the producer's line endings.
    """
    path = make_gtfs_zip({"stops.txt": stops, "trips.txt": trips})
    assert read_feed_dates(str(path)).has_service_content


@pytest.mark.parametrize(
    ("stops", "trips"),
    [
        pytest.param(
            b"stop_id,stop_name\nS1,Main St\n",
            b"route_id,service_id,trip_id\n",
            id="no BOM",
        ),
        pytest.param(
            UTF8_BOM + b"stop_id,stop_name\nS1,Main St\n",
            UTF8_BOM + b"route_id,service_id,trip_id\n",
            id="a UTF-8 BOM",
        ),
    ],
)
def test_a_utf8_bom_does_not_change_what_the_reader_sees(
    make_gtfs_zip: Callable[..., Path], stops: bytes, trips: bytes
) -> None:
    """Narrowness, not evidence: this one passes either side of the fix.

    _has_data_row reads the BOM as part of the header line it discards, so a
    BOM never decided this answer. It is pinned anyway because utf-8-sig is now
    what strips it, and a reader that stopped stripping it would corrupt the
    first column name for every consumer that does parse the header.
    """
    path = make_gtfs_zip({"stops.txt": stops, "trips.txt": trips})
    assert read_feed_dates(str(path)).has_service_content


def test_a_header_only_table_is_not_service_content_with_or_without_a_bom(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    """The other direction: nothing here may start reading a header as a row.

    A BOM-only file is the sharp case. Read as bytes its three BOM bytes strip
    to a non-empty line; decoded as utf-8-sig they strip to nothing at all.
    Both must answer "no rows", because a stops.txt holding a BOM and a column
    header describes exactly as many stops as an absent one.
    """
    for stops in (b"stop_id,stop_name\n", UTF8_BOM + b"stop_id,stop_name\n", UTF8_BOM, b""):
        path = make_gtfs_zip(
            {"stops.txt": stops, "trips.txt": b"route_id,service_id,trip_id\n"},
            name=f"gtfs-{len(stops)}.zip",
        )
        assert not read_feed_dates(str(path)).has_service_content
