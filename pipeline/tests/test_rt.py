"""Tests for realtime sampling structures, schedule lookup, and scoring."""

from __future__ import annotations

import datetime as dt
import time
import zoneinfo
from collections.abc import Callable
from pathlib import Path

import pytest
from google.transit import gtfs_realtime_pb2

from scorecard_pipeline import rt
from scorecard_pipeline.rt import (
    FRESH_ZERO_SECONDS,
    RtSample,
    RtWindow,
    _active_service_ids,
    _gtfs_time_to_seconds,
    _human_duration,
    _trip_time_spans,
    fetch_sample,
    realtime,
    scheduled_trip_ids_at,
)
from scorecard_pipeline.rt_drift import DriftStats, PlausibilityStats

NOW = 1_770_000_000  # arbitrary unix time used consistently below


def repo_root() -> Path:
    """Find the repository root by marker, not by a fixed parent depth.

    `make mutation` copies pipeline/tests to pipeline/mutants/tests and runs
    pytest from pipeline/mutants, so counting parents from __file__ lands on
    pipeline/ and the registry read fails. Walking up to the directory that
    holds registry/index.yaml gives the same answer from either tree.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "registry" / "index.yaml").is_file():
            return candidate
    raise AssertionError(f"no registry/index.yaml above {Path(__file__).resolve()}")


def sample(
    kind: str,
    ok: bool = True,
    lag: int = 5,
    trip_ids: frozenset[str] = frozenset(),
) -> RtSample:
    return RtSample(
        kind=kind,
        fetched_at=NOW,
        ok=ok,
        header_timestamp=NOW - lag if ok else None,
        entity_count=len(trip_ids),
        trip_ids=trip_ids,
        error=None if ok else "boom",
    )


def healthy_window(trips: frozenset[str] = frozenset({"T1", "T2"})) -> RtWindow:
    return RtWindow(
        samples=[
            sample("trip_updates", trip_ids=trips),
            sample("vehicle_positions"),
            sample("service_alerts"),
        ]
    )


class TestScoring:
    def test_healthy_full_coverage_scores_100(self) -> None:
        result = realtime(healthy_window(), {"T1", "T2"})
        assert result.score == 100.0
        assert result.findings == []
        assert result.details["coverage_pct"] == 100.0

    def test_unreachable_feed_costs_its_share(self) -> None:
        window = RtWindow(
            samples=[
                sample("trip_updates", trip_ids=frozenset({"T1", "T2"})),
                sample("vehicle_positions", ok=False),
                sample("service_alerts"),
            ]
        )
        result = realtime(window, {"T1", "T2"})
        # (25 * 2/3 + 25 + 35) / 85 * 100
        assert result.score == pytest.approx(90.2, abs=0.05)
        finding = next(
            f for f in result.findings if f.code == "scorecard_rt_vehicle_positions_unreachable"
        )
        assert finding.deduction == pytest.approx(100.0 - result.score)

    def test_vehicle_positions_only_scores_configured_capabilities(self) -> None:
        window = RtWindow(samples=[sample("vehicle_positions")])
        plausibility = PlausibilityStats(
            vehicles_checked=39,
            plausible_share=36 / 39,
            worst_meters=900,
        )

        result = realtime(
            window,
            {"T1", "T2"},
            drift=DriftStats(
                observations=5,
                median_seconds=90,
                p90_abs_seconds=120,
                on_time_share=0.8,
            ),
            plausibility=plausibility,
            configured_kinds={"vehicle_positions"},
        )

        # Reachability + freshness + position plausibility are measurable;
        # TripUpdates coverage and unconfigured feed kinds are neutral.
        expected = (25 + 25 + 15 * (36 / 39)) / (25 + 25 + 15) * 100
        assert result.score == pytest.approx(expected)
        assert result.details["configured_kinds"] == ["vehicle_positions"]
        assert result.details["reachable_kinds"] == ["vehicle_positions"]
        assert result.details["kinds_configured"] == 1
        assert result.details["kinds_reachable"] == 1
        assert result.details["coverage_pct"] is None
        assert "scheduled_trips_in_window" not in result.details
        assert "1 of 1 configured feed healthy" in result.summary
        assert "outside service hours" not in result.summary
        codes = {finding.code for finding in result.findings}
        assert "scorecard_rt_trip_updates_unreachable" not in codes
        assert "scorecard_rt_service_alerts_unreachable" not in codes
        assert "scorecard_rt_trip_coverage" not in codes
        assert "drift" not in result.details
        assert "predictions ran" not in result.summary

    def test_vehicle_positions_without_shapes_explains_unmeasured_plausibility(self) -> None:
        result = realtime(
            RtWindow(samples=[sample("vehicle_positions")]),
            None,
            configured_kinds={"vehicle_positions"},
        )

        assert result.score == 100.0
        assert "vehicle position plausibility was not measurable" in result.summary

    def test_vehicle_positions_only_stale_deduction_matches_score_loss(self) -> None:
        result = realtime(
            RtWindow(samples=[sample("vehicle_positions", lag=FRESH_ZERO_SECONDS)]),
            None,
            configured_kinds={"vehicle_positions"},
        )

        finding = next(f for f in result.findings if f.code == "scorecard_rt_stale")
        assert result.score == 50.0
        assert finding.deduction == pytest.approx(100.0 - result.score)
        assert finding.to_json()["points"] == round(100.0 - result.score, 1)

    def test_vehicle_positions_only_implausible_deduction_matches_score_loss(self) -> None:
        result = realtime(
            RtWindow(samples=[sample("vehicle_positions")]),
            None,
            plausibility=PlausibilityStats(
                vehicles_checked=4,
                plausible_share=0.5,
                worst_meters=900,
            ),
            configured_kinds={"vehicle_positions"},
        )

        finding = next(f for f in result.findings if f.code == "scorecard_rt_vehicles_off_route")
        assert finding.deduction == pytest.approx(100.0 - result.score)
        assert finding.to_json()["points"] == round(100.0 - result.score, 1)

    def test_global_basmy_kangar_registry_entry_is_scored_as_vp_only(self) -> None:
        from scorecard_pipeline.agencies import _load_manifest

        root = repo_root()
        registry = _load_manifest(root, root / "registry" / "index.yaml")
        kangar = next(agency for agency in registry if agency.id == "basmy-kangar")
        assert kangar.country == "MY"
        assert set(kangar.rt_urls) == {"vehicle_positions"}

        result = realtime(
            RtWindow(samples=[sample("vehicle_positions")]),
            {"scheduled-but-not-a-trip-update"},
            plausibility=PlausibilityStats(
                vehicles_checked=23,
                plausible_share=1.0,
                worst_meters=20,
            ),
            configured_kinds=kangar.rt_urls,
        )

        assert result.score == 100.0
        assert result.findings == []
        assert result.details["coverage_pct"] is None

    def test_unreachable_configured_vehicle_positions_still_fails(self) -> None:
        window = RtWindow(samples=[sample("vehicle_positions", ok=False)])

        result = realtime(window, {"T1"}, configured_kinds={"vehicle_positions"})

        assert result.score == 0.0
        assert [finding.code for finding in result.findings] == [
            "scorecard_rt_vehicle_positions_unreachable"
        ]
        assert result.findings[0].deduction == 100.0

    def test_trip_updates_only_keeps_coverage_without_other_feed_penalties(self) -> None:
        window = RtWindow(samples=[sample("trip_updates", trip_ids=frozenset({"T1", "T2"}))])

        result = realtime(
            window,
            {"T1", "T2"},
            configured_kinds={"trip_updates"},
        )

        assert result.score == 100.0
        assert result.details["coverage_pct"] == 100.0
        assert result.findings == []
        assert "1 of 1 configured feed healthy" in result.summary

    def test_trip_updates_only_half_coverage_deduction_matches_score_loss(self) -> None:
        result = realtime(
            RtWindow(samples=[sample("trip_updates", trip_ids=frozenset({"T1"}))]),
            {"T1", "T2"},
            configured_kinds={"trip_updates"},
        )

        finding = next(f for f in result.findings if f.code == "scorecard_rt_trip_coverage")
        assert finding.deduction == pytest.approx(100.0 - result.score)
        assert finding.to_json()["points"] == round(100.0 - result.score, 1)

    def test_service_alerts_only_does_not_invent_freshness_or_coverage_gaps(self) -> None:
        result = realtime(
            RtWindow(samples=[sample("service_alerts")]),
            {"T1"},
            configured_kinds={"service_alerts"},
        )

        assert result.score == 100.0
        assert result.findings == []
        assert result.details["rt_freshness"] is None
        assert result.details["coverage_pct"] is None

    def test_service_alerts_only_outage_deduction_matches_score_loss(self) -> None:
        result = realtime(
            RtWindow(samples=[sample("service_alerts", ok=False)]),
            None,
            configured_kinds={"service_alerts"},
        )

        assert result.score == 0.0
        assert [finding.code for finding in result.findings] == [
            "scorecard_rt_service_alerts_unreachable"
        ]
        assert result.findings[0].deduction == 100.0 - result.score

    def test_empty_explicit_configuration_is_rejected(self) -> None:
        # Agencies with no realtime skip this category in the collect path. If
        # a caller bypasses that neutral path, fail rather than invent a score.
        with pytest.raises(ValueError, match="at least one configured"):
            realtime(RtWindow(), None, configured_kinds=set())

    def test_explicit_configuration_marks_an_unsampled_endpoint_unreachable(self) -> None:
        # Configuration, not whichever samples happen to be present, defines
        # the assessment boundary. This stays fail-closed for a configured
        # endpoint if a future sampler ever omits its failure record.
        window = RtWindow(samples=[sample("vehicle_positions")])

        result = realtime(
            window,
            None,
            configured_kinds={"trip_updates", "vehicle_positions"},
        )

        codes = {finding.code for finding in result.findings}
        assert "scorecard_rt_trip_updates_unreachable" in codes
        assert "scorecard_rt_service_alerts_unreachable" not in codes

    def test_stale_feed_loses_freshness_points(self) -> None:
        window = RtWindow(
            samples=[
                sample("trip_updates", lag=600, trip_ids=frozenset({"T1", "T2"})),
                sample("vehicle_positions", lag=600),
                sample("service_alerts"),
            ]
        )
        result = realtime(window, {"T1", "T2"})
        # (25 + 0 + 35) / 85 * 100
        assert result.score == pytest.approx(70.6, abs=0.05)
        assert any(f.code == "scorecard_rt_stale" for f in result.findings)

    def test_lapsed_feed_reads_as_freshness_failure_not_zero(self) -> None:
        # Header two hours behind: the feed has effectively stopped.
        window = RtWindow(
            samples=[
                sample("trip_updates", lag=7200, trip_ids=frozenset({"T1", "T2"})),
                sample("vehicle_positions", lag=7200),
                sample("service_alerts"),
            ]
        )
        result = realtime(window, {"T1", "T2"})
        codes = {f.code for f in result.findings}
        assert "scorecard_rt_feed_lapsed" in codes
        assert "scorecard_rt_stale" not in codes  # the stronger finding replaces it
        assert result.details["rt_freshness"] == "lapsed"
        lapsed = next(f for f in result.findings if f.code == "scorecard_rt_feed_lapsed")
        assert lapsed.severity == "ERROR"
        assert "2 hours" in lapsed.what
        # Freshness zeroes out but reachable + coverage keep it off the floor.
        assert result.score == pytest.approx(70.6, abs=0.05)

    def test_mildly_stale_feed_still_uses_the_gentle_finding(self) -> None:
        window = RtWindow(
            samples=[
                sample("trip_updates", lag=300, trip_ids=frozenset({"T1", "T2"})),
                sample("vehicle_positions", lag=300),
                sample("service_alerts"),
            ]
        )
        result = realtime(window, {"T1", "T2"})
        codes = {f.code for f in result.findings}
        assert "scorecard_rt_stale" in codes
        assert "scorecard_rt_feed_lapsed" not in codes
        assert result.details["rt_freshness"] == "stale"

    def test_partial_coverage_scales_and_explains(self) -> None:
        result = realtime(healthy_window(frozenset({"T1"})), {"T1", "T2"})
        # (25 + 25 + 17.5) / 85 * 100
        assert result.score == pytest.approx(79.4, abs=0.05)
        finding = next(f for f in result.findings if f.code == "scorecard_rt_trip_coverage")
        assert finding.count == 1
        assert "1 of 2" in finding.what

    def test_multiple_scored_findings_sum_to_category_score_loss(self) -> None:
        result = realtime(
            RtWindow(
                samples=[
                    sample(
                        "trip_updates",
                        lag=FRESH_ZERO_SECONDS,
                        trip_ids=frozenset({"T1"}),
                    )
                ]
            ),
            {"T1", "T2"},
            configured_kinds={"trip_updates"},
        )

        scored = [finding for finding in result.findings if finding.deduction > 0]
        assert {finding.code for finding in scored} == {
            "scorecard_rt_stale",
            "scorecard_rt_trip_coverage",
        }
        assert sum(finding.deduction for finding in scored) == pytest.approx(100.0 - result.score)
        assert sum(finding.to_json()["points"] for finding in scored) == round(
            100.0 - result.score, 1
        )

    def test_unreachable_trip_updates_does_not_duplicate_a_coverage_deduction(self) -> None:
        result = realtime(
            RtWindow(samples=[sample("trip_updates", ok=False)]),
            {"T1"},
            configured_kinds={"trip_updates"},
        )

        assert result.score == 0.0
        assert [finding.code for finding in result.findings] == [
            "scorecard_rt_trip_updates_unreachable"
        ]
        assert result.findings[0].deduction == 100.0
        assert result.details["scheduled_trips_in_window"] == 1
        assert result.details["coverage_pct"] is None
        assert result.details["reachable_kinds"] == []
        assert "outside service hours" not in result.summary

    def test_reachable_kinds_identify_only_successful_endpoint_kinds(self) -> None:
        result = realtime(
            RtWindow(
                samples=[
                    sample("trip_updates"),
                    sample("vehicle_positions", ok=False),
                    sample("service_alerts"),
                ]
            ),
            {"T1"},
            configured_kinds={"trip_updates", "vehicle_positions", "service_alerts"},
        )

        assert result.details["reachable_kinds"] == ["trip_updates", "service_alerts"]

    def test_plausibility_folds_into_score(self) -> None:
        good = PlausibilityStats(vehicles_checked=4, plausible_share=1.0, worst_meters=40)
        assert realtime(healthy_window(), {"T1", "T2"}, plausibility=good).score == 100.0
        bad = PlausibilityStats(vehicles_checked=4, plausible_share=0.5, worst_meters=900)
        result = realtime(healthy_window(), {"T1", "T2"}, plausibility=bad)
        # (25 + 25 + 35 + 7.5) / 100 * 100
        assert result.score == pytest.approx(92.5)
        finding = next(f for f in result.findings if f.code == "scorecard_rt_vehicles_off_route")
        assert finding.count == 2
        assert "900 m" in finding.what

    def test_drift_reported_in_summary_and_details(self) -> None:
        drift = DriftStats(
            observations=40, median_seconds=85, p90_abs_seconds=240, on_time_share=0.9
        )
        result = realtime(healthy_window(), {"T1", "T2"}, drift=drift)
        assert result.score == 100.0  # drift informs, it doesn't score
        assert result.details["drift"]["on_time_share_pct"] == 90.0
        assert "median of 85s behind schedule" in result.summary

    def test_implausible_drift_becomes_finding(self) -> None:
        drift = DriftStats(
            observations=12, median_seconds=2400, p90_abs_seconds=3600, on_time_share=0.1
        )
        result = realtime(healthy_window(), {"T1", "T2"}, drift=drift)
        assert any(f.code == "scorecard_rt_predictions_implausible" for f in result.findings)

    def test_no_scheduled_trips_renormalizes_without_coverage(self) -> None:
        result = realtime(healthy_window(frozenset()), None)
        assert result.score == 100.0
        assert result.details["coverage_pct"] is None
        assert "outside service hours" in result.summary

    def test_worst_lag_across_samples(self) -> None:
        window = RtWindow(samples=[sample("trip_updates", lag=5), sample("trip_updates", lag=90)])
        assert window.worst_lag("trip_updates") == 90


class TestScheduleLookup:
    def make_feed(self, make_gtfs_zip: Callable[..., Path]) -> Path:
        return make_gtfs_zip(
            {
                "agency.txt": (
                    "agency_name,agency_url,agency_timezone\n"
                    "Test,https://example.org,America/Los_Angeles\n"
                ),
                "calendar_dates.txt": (
                    "service_id,date,exception_type\nSVC,20260611,1\nNIGHT,20260610,1\n"
                ),
                "trips.txt": (
                    "route_id,service_id,trip_id\nR1,SVC,DAY\nR1,NIGHT,OWL\nR1,OFF,NOPE\n"
                ),
                "stop_times.txt": (
                    "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                    "DAY,10:00:00,10:00:00,S1,1\n"
                    "DAY,11:00:00,11:00:00,S2,2\n"
                    "OWL,24:30:00,24:30:00,S1,1\n"
                    "OWL,25:30:00,25:30:00,S2,2\n"
                    "NOPE,10:00:00,10:00:00,S1,1\n"
                ),
            }
        )

    def moment(self, hour: int, minute: int) -> dt.datetime:
        tz = zoneinfo.ZoneInfo("America/Los_Angeles")
        return dt.datetime(2026, 6, 11, hour, minute, tzinfo=tz)

    def test_daytime_trip_active_within_span(self, make_gtfs_zip: Callable[..., Path]) -> None:
        feed = self.make_feed(make_gtfs_zip)
        assert scheduled_trip_ids_at(str(feed), self.moment(10, 30)) == {"DAY"}
        assert scheduled_trip_ids_at(str(feed), self.moment(12, 0)) == set()

    def test_after_midnight_trip_counts_for_previous_service_day(
        self, make_gtfs_zip: Callable[..., Path]
    ) -> None:
        feed = self.make_feed(make_gtfs_zip)
        # 00:45 on Jun 11 = 24:45 on the Jun 10 NIGHT service
        assert scheduled_trip_ids_at(str(feed), self.moment(0, 45)) == {"OWL"}

    def test_inactive_service_excluded(self, make_gtfs_zip: Callable[..., Path]) -> None:
        feed = self.make_feed(make_gtfs_zip)
        active = scheduled_trip_ids_at(str(feed), self.moment(10, 30))
        assert "NOPE" not in active

    def test_naive_datetime_is_rejected(self) -> None:
        # A naive datetime would be silently coerced to system-local time and skew
        # the service window; the function must refuse it rather than guess a zone.
        with pytest.raises(ValueError):
            scheduled_trip_ids_at("unused.zip", dt.datetime(2026, 6, 11, 10, 0))

    def test_trip_with_no_usable_stop_time_is_skipped(
        self, make_gtfs_zip: Callable[..., Path]
    ) -> None:
        feed = make_gtfs_zip(
            {
                "stop_times.txt": (
                    "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                    "GOOD,08:00:00,08:00:00,S1,1\n"
                    "NOTIME,,,S1,1\n"  # no arrival/departure -> no span
                    ",09:00:00,09:00:00,S1,1\n"  # no trip_id -> skipped
                ),
            }
        )
        spans = _trip_time_spans(str(feed))
        assert "GOOD" in spans
        assert "NOTIME" not in spans
        assert "" not in spans


class TestActiveServiceIds:
    THURSDAY = dt.date(2026, 6, 11)

    def _calendar_row(self, service_id: str, **days: str) -> dict[str, str]:
        row = {
            "service_id": service_id,
            "start_date": "20260101",
            "end_date": "20261231",
            "monday": "0",
            "tuesday": "0",
            "wednesday": "0",
            "thursday": "0",
            "friday": "0",
            "saturday": "0",
            "sunday": "0",
        }
        row.update(days)
        return row

    def test_calendar_weekday_in_range_is_active(self) -> None:
        tables = {
            "calendar.txt": [self._calendar_row("WK", thursday="1")],
            "calendar_dates.txt": [],
        }
        assert _active_service_ids(tables, self.THURSDAY) == {"WK"}

    def test_wrong_weekday_is_inactive(self) -> None:
        tables = {
            "calendar.txt": [self._calendar_row("WKND", saturday="1", sunday="1")],
            "calendar_dates.txt": [],
        }
        assert _active_service_ids(tables, self.THURSDAY) == set()

    def test_out_of_date_range_is_inactive(self) -> None:
        expired = self._calendar_row("OLD", thursday="1")
        expired["end_date"] = "20260101"  # ended before the query date
        tables = {"calendar.txt": [expired], "calendar_dates.txt": []}
        assert _active_service_ids(tables, self.THURSDAY) == set()

    def test_calendar_dates_exception_adds_service(self) -> None:
        # exception_type 1 adds a service for a date even with no calendar.txt row.
        tables = {
            "calendar.txt": [],
            "calendar_dates.txt": [
                {"service_id": "SPECIAL", "date": "20260611", "exception_type": "1"}
            ],
        }
        assert _active_service_ids(tables, self.THURSDAY) == {"SPECIAL"}

    def test_calendar_dates_exception_removes_service(self) -> None:
        # exception_type 2 removes a service the weekly calendar would otherwise run.
        tables = {
            "calendar.txt": [self._calendar_row("WK", thursday="1")],
            "calendar_dates.txt": [{"service_id": "WK", "date": "20260611", "exception_type": "2"}],
        }
        assert _active_service_ids(tables, self.THURSDAY) == set()


class TestHumanDuration:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (45, "45 seconds"),
            (89, "89 seconds"),
            (300, "5 minutes"),
            (7200, "2 hours"),
            (200_000, "2 days"),
        ],
    )
    def test_coarse_readable_age(self, seconds: int, expected: str) -> None:
        assert _human_duration(seconds) == expected


class TestGtfsTimeToSeconds:
    def test_past_midnight_time_parses(self) -> None:
        assert _gtfs_time_to_seconds("25:30:00") == 25 * 3600 + 30 * 60

    def test_midnight_is_zero_not_none(self) -> None:
        assert _gtfs_time_to_seconds("00:00:00") == 0

    def test_wrong_shape_is_none(self) -> None:
        assert _gtfs_time_to_seconds("10:00") is None

    def test_non_numeric_is_none(self) -> None:
        assert _gtfs_time_to_seconds("ab:cd:ef") is None


def _feed_message(timestamp: int | None) -> gtfs_realtime_pb2.FeedMessage:
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    if timestamp is not None:
        msg.header.timestamp = timestamp
    return msg


class TestFetchSample:
    def _serve(self, monkeypatch: pytest.MonkeyPatch, body: bytes) -> None:
        monkeypatch.setattr(rt, "safe_get", lambda *_a, **_k: body)

    def test_parses_trip_updates_with_delay_and_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        msg = _feed_message(NOW - 5)
        ent = msg.entity.add()
        ent.id = "1"
        tu = ent.trip_update
        tu.trip.trip_id = "T1"
        a = tu.stop_time_update.add()
        a.stop_id = "S1"
        a.stop_sequence = 3
        a.arrival.delay = 60
        d = tu.stop_time_update.add()
        d.stop_id = "S2"
        d.departure.time = NOW + 120
        # An entity carrying no trip_update must be skipped, not crash.
        msg.entity.add().id = "noise"

        self._serve(monkeypatch, msg.SerializeToString())
        s = fetch_sample("trip_updates", "https://example.org/tu")

        assert s.ok and s.error is None
        assert s.trip_ids == frozenset({"T1"})
        assert s.header_timestamp == NOW - 5
        # fetched_at is the real wall clock, so lag is just non-negative here.
        assert s.lag_seconds is not None and s.lag_seconds >= 0
        by_stop = {e.stop_id: e for e in s.stop_time_events}
        assert by_stop["S1"].delay_seconds == 60
        assert by_stop["S1"].stop_sequence == 3
        assert by_stop["S1"].predicted_time is None
        assert by_stop["S2"].predicted_time == NOW + 120
        assert by_stop["S2"].delay_seconds is None
        assert by_stop["S2"].stop_sequence is None

    def test_parses_vehicle_positions_and_skips_position_less(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        msg = _feed_message(NOW)
        ent = msg.entity.add()
        ent.id = "v1"
        ent.vehicle.trip.trip_id = "T1"
        ent.vehicle.position.latitude = 38.55
        ent.vehicle.position.longitude = -121.74
        # A vehicle without a position is dropped (no plausible coordinates).
        noise = msg.entity.add()
        noise.id = "v2"
        noise.vehicle.trip.trip_id = "T2"

        self._serve(monkeypatch, msg.SerializeToString())
        s = fetch_sample("vehicle_positions", "https://example.org/vp")

        assert len(s.vehicles) == 1
        assert s.vehicles[0].trip_id == "T1"
        assert s.vehicles[0].lat == pytest.approx(38.55)

    def test_missing_header_timestamp_yields_no_lag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._serve(monkeypatch, _feed_message(None).SerializeToString())
        s = fetch_sample("service_alerts", "https://example.org/sa")
        assert s.ok
        assert s.header_timestamp is None
        assert s.lag_seconds is None

    def test_fetch_failure_is_a_finding_not_a_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: object, **_k: object) -> bytes:
            raise RuntimeError("connection reset")

        monkeypatch.setattr(rt, "safe_get", boom)
        s = fetch_sample("trip_updates", "https://example.org/tu")
        assert not s.ok
        assert s.error is not None and "connection reset" in s.error

    def test_archives_the_raw_protobuf(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        body = _feed_message(NOW).SerializeToString()
        self._serve(monkeypatch, body)
        archive = tmp_path / "nested" / "tu.pb"
        fetch_sample("trip_updates", "https://example.org/tu", archive_to=str(archive))
        assert archive.read_bytes() == body


def test_capture_window_samples_each_kind_and_spaces_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline.config import Agency

    agency = Agency(
        id="demo",
        name="Demo",
        static_gtfs_url="https://example.org/g.zip",
        rt_urls={"trip_updates": "https://example.org/tu", "vehicle_positions": "https://e/vp"},
    )
    fetched: list[tuple[str, str]] = []

    def fake_fetch(kind: str, url: str, archive_to: str | None = None) -> RtSample:
        fetched.append((kind, url))
        return RtSample(kind=kind, fetched_at=NOW, ok=True, header_timestamp=NOW)

    sleeps: list[int] = []
    monkeypatch.setattr(rt, "fetch_sample", fake_fetch)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    window = rt.capture_window(agency, dt.date(2026, 6, 11), samples=2, interval_seconds=30)

    # Two rounds over two endpoints = four samples; one sleep between the rounds.
    assert len(window.samples) == 4
    assert fetched.count(("trip_updates", "https://example.org/tu")) == 2
    assert sleeps == [30]


def test_reachable_feed_without_timestamp_notes_it_without_penalty() -> None:
    # A feed that omits the optional header timestamp shouldn't be scored stale;
    # freshness drops out and a zero-deduction note explains the gap.
    window = RtWindow(
        samples=[
            RtSample(kind="trip_updates", fetched_at=NOW, ok=True, header_timestamp=None),
            RtSample(kind="vehicle_positions", fetched_at=NOW, ok=True, header_timestamp=None),
            RtSample(kind="service_alerts", fetched_at=NOW, ok=True, header_timestamp=None),
        ]
    )
    result = realtime(window, {"T1"})
    note = next(f for f in result.findings if f.code == "scorecard_rt_no_timestamp")
    assert note.severity == "INFO"
    assert note.deduction == 0.0
    assert result.details["rt_freshness"] is None


# ---- service-alert content observations (EXP-19, reported not scored) -------


def _alert(
    header: str = "Detour on Route 5",
    description: str = "Use the F St stop.",
    cause: bool = True,
    effect: bool = True,
    entity: bool = True,
    end: int | None = NOW + 3600,
) -> rt.AlertObs:
    return rt.AlertObs(
        has_header_text=bool(header),
        has_description=bool(description),
        has_cause=cause,
        has_effect=effect,
        has_informed_entity=entity,
        period_end=end,
    )


def alerts_sample(alerts: tuple[rt.AlertObs, ...], fetched_at: int = NOW) -> RtSample:
    return RtSample(
        kind="service_alerts",
        fetched_at=fetched_at,
        ok=True,
        header_timestamp=fetched_at - 5,
        entity_count=len(alerts),
        alerts=alerts,
    )


class TestParseAlerts:
    def _message(self) -> gtfs_realtime_pb2.FeedMessage:
        msg = gtfs_realtime_pb2.FeedMessage()
        msg.header.gtfs_realtime_version = "2.0"
        msg.header.timestamp = NOW
        return msg

    def test_full_alert_observes_every_field(self) -> None:
        msg = self._message()
        alert = msg.entity.add(id="a1").alert
        alert.header_text.translation.add(text="Detour on Route 5")
        alert.description_text.translation.add(text="Use the F St stop instead.")
        alert.cause = gtfs_realtime_pb2.Alert.CONSTRUCTION
        alert.effect = gtfs_realtime_pb2.Alert.DETOUR
        alert.informed_entity.add(route_id="5")
        period = alert.active_period.add()
        period.start = NOW - 3600
        period.end = NOW + 3600

        (obs,) = rt.parse_alerts(msg)
        assert obs == rt.AlertObs(
            has_header_text=True,
            has_description=True,
            has_cause=True,
            has_effect=True,
            has_informed_entity=True,
            period_end=NOW + 3600,
        )

    def test_bare_alert_observes_every_gap(self) -> None:
        msg = self._message()
        msg.entity.add(id="a1").alert.SetInParent()

        (obs,) = rt.parse_alerts(msg)
        assert obs == rt.AlertObs(
            has_header_text=False,
            has_description=False,
            has_cause=False,
            has_effect=False,
            has_informed_entity=False,
            period_end=None,
        )

    def test_blank_translation_text_does_not_count(self) -> None:
        msg = self._message()
        alert = msg.entity.add(id="a1").alert
        alert.header_text.translation.add(text="   ")
        (obs,) = rt.parse_alerts(msg)
        assert obs.has_header_text is False

    def test_any_open_ended_period_means_no_end_date(self) -> None:
        msg = self._message()
        alert = msg.entity.add(id="a1").alert
        alert.active_period.add().end = NOW
        alert.active_period.add().start = NOW  # second phase, no end
        (obs,) = rt.parse_alerts(msg)
        assert obs.period_end is None

    def test_non_alert_entities_are_ignored(self) -> None:
        msg = self._message()
        msg.entity.add(id="t1").trip_update.trip.trip_id = "T1"
        assert rt.parse_alerts(msg) == ()


class TestAlertsContent:
    def test_no_successful_sample_reports_nothing(self) -> None:
        window = RtWindow(samples=[sample("service_alerts", ok=False)])
        assert rt.alerts_content(window) is None

    def test_newest_snapshot_speaks_for_the_window(self) -> None:
        old = alerts_sample((_alert(), _alert()), fetched_at=NOW - 60)
        new = alerts_sample((_alert(),), fetched_at=NOW)
        summary = rt.alerts_content(RtWindow(samples=[old, new]))
        assert summary is not None and summary["alerts"] == 1

    def test_counts_each_content_dimension(self) -> None:
        alerts = (
            _alert(),
            _alert(header="", description="", cause=False, effect=False, entity=False),
            _alert(end=NOW - rt.ALERT_STALE_SECONDS - 1),
        )
        summary = rt.alerts_content(RtWindow(samples=[alerts_sample(alerts)]))
        assert summary == {
            "alerts": 3,
            "with_header_text": 2,
            "with_description": 2,
            "with_cause_and_effect": 2,
            "with_informed_entity": 2,
            "ended_over_30_days_ago": 1,
        }

    def test_recently_ended_and_open_ended_alerts_are_not_stale(self) -> None:
        alerts = (_alert(end=NOW - 86400), _alert(end=None))
        summary = rt.alerts_content(RtWindow(samples=[alerts_sample(alerts)]))
        assert summary is not None and summary["ended_over_30_days_ago"] == 0


class TestAlertsInScoring:
    def _window(self, alerts: tuple[rt.AlertObs, ...]) -> RtWindow:
        return RtWindow(
            samples=[
                sample("trip_updates", trip_ids=frozenset({"T1", "T2"})),
                sample("vehicle_positions"),
                alerts_sample(alerts),
            ]
        )

    def test_observations_land_in_details_with_zero_deductions(self) -> None:
        alerts = (_alert(end=NOW - rt.ALERT_STALE_SECONDS - 1), _alert(header=""))
        result = realtime(self._window(alerts), {"T1", "T2"})
        assert result.details["alerts_content"] == {
            "alerts": 2,
            "with_header_text": 1,
            "with_description": 2,
            "with_cause_and_effect": 2,
            "with_informed_entity": 2,
            "ended_over_30_days_ago": 1,
        }
        codes = {f.code: f for f in result.findings}
        assert codes["scorecard_rt_alerts_ended"].count == 1
        assert codes["scorecard_rt_alerts_ended"].deduction == 0.0
        assert codes["scorecard_rt_alerts_missing_text"].count == 1
        assert codes["scorecard_rt_alerts_missing_text"].deduction == 0.0

    def test_alert_content_never_moves_the_score(self) -> None:
        bad_alerts = (_alert(header="", end=NOW - rt.ALERT_STALE_SECONDS - 1),) * 5
        clean = realtime(self._window(()), {"T1", "T2"})
        messy = realtime(self._window(bad_alerts), {"T1", "T2"})
        assert messy.score == clean.score == 100.0

    def test_healthy_alerts_add_no_findings(self) -> None:
        result = realtime(self._window((_alert(),)), {"T1", "T2"})
        assert result.findings == []
