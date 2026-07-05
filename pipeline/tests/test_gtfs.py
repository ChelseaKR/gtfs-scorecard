"""Tests for the minimal GTFS readers behind the freshness category."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path

from scorecard_pipeline.gtfs import read_agency_ids, read_feed_dates, read_shapes_coverage

CALENDAR_HEADER = (
    "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
)


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
    # agency_id is optional in single-agency feeds; absence is normal, not error.
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
