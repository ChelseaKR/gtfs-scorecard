"""Tests for schedule-vs-RT drift and vehicle position plausibility."""

from __future__ import annotations

import datetime as dt
import zoneinfo
from collections.abc import Callable
from pathlib import Path

import pytest

from scorecard_pipeline.rt import RtSample, StopTimeEvent, VehicleObs
from scorecard_pipeline.rt_drift import compute_drift, vehicle_plausibility

TZ = zoneinfo.ZoneInfo("America/Los_Angeles")
# 10:00 local on 2026-06-11
FETCH_AT = int(dt.datetime(2026, 6, 11, 10, 0, tzinfo=TZ).timestamp())


def feed(make_gtfs_zip: Callable[..., Path]) -> Path:
    return make_gtfs_zip(
        {
            "agency.txt": (
                "agency_name,agency_url,agency_timezone\n"
                "Test,https://example.org,America/Los_Angeles\n"
            ),
            "stop_times.txt": (
                "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                "T1,10:00:00,10:00:00,S1,1\n"
                "T1,10:10:00,10:10:00,S2,2\n"
            ),
            "trips.txt": "route_id,service_id,trip_id,shape_id\nR1,SVC,T1,SH1\n",
            # A straight north-south line near Davis, CA
            "shapes.txt": (
                "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
                "SH1,38.5400,-121.7400,1\n"
                "SH1,38.5500,-121.7400,2\n"
            ),
        }
    )


def tu_sample(events: list[StopTimeEvent]) -> RtSample:
    return RtSample(
        kind="trip_updates",
        fetched_at=FETCH_AT,
        ok=True,
        header_timestamp=FETCH_AT,
        stop_time_events=tuple(events),
    )


def vp_sample(vehicles: list[VehicleObs]) -> RtSample:
    return RtSample(
        kind="vehicle_positions",
        fetched_at=FETCH_AT,
        ok=True,
        header_timestamp=FETCH_AT,
        vehicles=tuple(vehicles),
    )


class TestDrift:
    def test_direct_delay_fields(self, make_gtfs_zip: Callable[..., Path]) -> None:
        samples = [
            tu_sample(
                [
                    StopTimeEvent("T1", "S1", 1, delay_seconds=120, predicted_time=None),
                    StopTimeEvent("T1", "S2", 2, delay_seconds=-30, predicted_time=None),
                ]
            )
        ]
        stats = compute_drift(samples, str(feed(make_gtfs_zip)))
        assert stats is not None
        assert stats.observations == 2
        assert stats.median_seconds == 45
        assert stats.on_time_share == 1.0

    def test_predicted_times_resolved_against_schedule(
        self, make_gtfs_zip: Callable[..., Path]
    ) -> None:
        # scheduled S1 at 10:00; predicted 10:03 -> 180s late
        predicted = FETCH_AT + 180
        samples = [
            tu_sample([StopTimeEvent("T1", "S1", 1, delay_seconds=None, predicted_time=predicted)])
        ]
        stats = compute_drift(samples, str(feed(make_gtfs_zip)))
        assert stats is not None
        assert stats.median_seconds == 180

    def test_later_sample_wins_per_stop(self, make_gtfs_zip: Callable[..., Path]) -> None:
        samples = [
            tu_sample([StopTimeEvent("T1", "S1", 1, delay_seconds=600, predicted_time=None)]),
            tu_sample([StopTimeEvent("T1", "S1", 1, delay_seconds=60, predicted_time=None)]),
        ]
        stats = compute_drift(samples, str(feed(make_gtfs_zip)))
        assert stats is not None
        assert stats.observations == 1
        assert stats.median_seconds == 60

    def test_unmatchable_predictions_discarded(self, make_gtfs_zip: Callable[..., Path]) -> None:
        # 8 hours off: beyond the sanity bound, likely mis-keyed
        samples = [
            tu_sample(
                [
                    StopTimeEvent(
                        "T1", "S1", 1, delay_seconds=None, predicted_time=FETCH_AT + 8 * 3600
                    )
                ]
            )
        ]
        assert compute_drift(samples, str(feed(make_gtfs_zip))) is None

    def test_no_trip_updates_returns_none(self, make_gtfs_zip: Callable[..., Path]) -> None:
        assert compute_drift([vp_sample([])], str(feed(make_gtfs_zip))) is None

    # GTFS times are measured from "noon minus 12 hours" of the service day, not
    # from local midnight. The two are the same on 363 days a year and an hour
    # apart on the two DST transition days, so a midnight reference reports every
    # on-time bus as an hour off on exactly those days.
    @pytest.mark.parametrize(
        ("service_date", "label"),
        [(dt.date(2026, 11, 1), "fall back"), (dt.date(2026, 3, 8), "spring forward")],
    )
    def test_on_time_bus_reads_as_on_time_across_dst(
        self, make_gtfs_zip: Callable[..., Path], service_date: dt.date, label: str
    ) -> None:
        # A bus arriving at exactly its scheduled 10:00 local, sampled at 10:00
        # local on a DST transition day.
        moment = int(dt.datetime.combine(service_date, dt.time(10), TZ).timestamp())
        sample = RtSample(
            kind="trip_updates",
            fetched_at=moment,
            ok=True,
            header_timestamp=moment,
            stop_time_events=(
                StopTimeEvent("T1", "S1", 1, delay_seconds=None, predicted_time=moment),
            ),
        )
        stats = compute_drift([sample], str(feed(make_gtfs_zip)))
        assert stats is not None
        assert stats.median_seconds == 0, f"{label}: on-time bus reported as drifting"
        assert stats.on_time_share == 1.0


class TestPlausibility:
    def test_vehicle_on_route_is_plausible(self, make_gtfs_zip: Callable[..., Path]) -> None:
        samples = [vp_sample([VehicleObs("T1", 38.5450, -121.7400)])]
        stats = vehicle_plausibility(samples, str(feed(make_gtfs_zip)))
        assert stats is not None
        assert stats.vehicles_checked == 1
        assert stats.plausible_share == 1.0
        assert stats.worst_meters < 50

    def test_vehicle_far_from_route_is_flagged(self, make_gtfs_zip: Callable[..., Path]) -> None:
        # ~0.01 deg of longitude ~ 870m at this latitude
        samples = [vp_sample([VehicleObs("T1", 38.5450, -121.7300)])]
        stats = vehicle_plausibility(samples, str(feed(make_gtfs_zip)))
        assert stats is not None
        assert stats.plausible_share == 0.0
        assert stats.worst_meters == pytest.approx(870, abs=30)

    def test_unknown_trip_or_no_vehicles_not_applicable(
        self, make_gtfs_zip: Callable[..., Path]
    ) -> None:
        path = str(feed(make_gtfs_zip))
        assert vehicle_plausibility([vp_sample([])], path) is None
        assert vehicle_plausibility([vp_sample([VehicleObs("??", 38.54, -121.74)])], path) is None
