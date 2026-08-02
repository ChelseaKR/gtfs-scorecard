"""Raw-archive versus reader-view routing at the daily pipeline boundary."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Collection
from pathlib import Path
from typing import Any

import pytest

import scorecard_pipeline.archive as archive
import scorecard_pipeline.cli as cli
import scorecard_pipeline.conformance as conformance
import scorecard_pipeline.exportdiff as exportdiff
import scorecard_pipeline.ferry_profile as ferry_profile
import scorecard_pipeline.geo as geo
import scorecard_pipeline.gtfs as gtfs
import scorecard_pipeline.mode_language as mode_language
import scorecard_pipeline.modes as modes
import scorecard_pipeline.recommend as recommend
import scorecard_pipeline.routability as routability
import scorecard_pipeline.route_geometry as route_geometry
import scorecard_pipeline.vcache as vcache
from scorecard_pipeline.config import AGENCIES, Agency
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.rt import RtSample, RtWindow
from scorecard_pipeline.rt_drift import DriftStats, PlausibilityStats
from scorecard_pipeline.validate import VALIDATOR_VERSION, ValidationReport


def _category(name: str) -> CategoryResult:
    details = {"validator_version": VALIDATOR_VERSION} if name == "correctness" else {}
    return CategoryResult(name=name, score=100.0, summary="Measured.", details=details)


def test_run_agency_routes_raw_archive_and_reader_view_to_their_owners(  # noqa: C901
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External integrity boundaries use raw bytes; owned readers use the view."""
    run_date = dt.date(2026, 7, 16)
    raw_path = tmp_path / "gtfs.zip"
    reader_path = tmp_path / "gtfs.reader.zip"
    raw_path.write_bytes(b"raw producer bytes")
    reader_path.write_bytes(b"deterministic reader view")
    digest = "ab" * 32
    agency = Agency(
        id="reader-routing-demo",
        name="Reader routing demo",
        static_gtfs_url="https://example.test/raw.zip",
        rt_urls={
            "trip_updates": "https://example.test/trip-updates.pb",
            "vehicle_positions": "https://example.test/vehicle-positions.pb",
        },
        ntd_id="12345",
        fare_free=True,
    )
    fetched = FetchResult(
        agency_id=agency.id,
        path=raw_path,
        url=agency.static_gtfs_url,
        fetched_date=run_date,
        sha256=digest,
        size_bytes=raw_path.stat().st_size,
        reused=False,
        source="origin",
        final_url="https://cdn.example.test/raw.zip",
        reader_path=reader_path,
        reader_archive_normalized=True,
    )
    monkeypatch.setitem(AGENCIES, agency.id, agency)
    monkeypatch.setenv("SCORECARD_ROOT", str(tmp_path))

    raw_calls: list[tuple[str, object, object]] = []
    reader_calls: list[str] = []
    published: dict[str, Any] = {}
    report = ValidationReport(validator_version=VALIDATOR_VERSION, notices=[])

    def fetch(
        configured_agency: Agency,
        date: dt.date,
        *,
        force: bool,
    ) -> FetchResult:
        assert configured_agency is agency
        assert date == run_date
        assert force is False
        return fetched

    def store_raw(sha256: str, path: Path) -> Path:
        raw_calls.append(("archive", sha256, path))
        return tmp_path / "archive" / f"{sha256}.zip"

    def load_report(
        agency_id: str,
        sha256: str,
        validator_version: str,
        country_code: str = "US",
    ) -> ValidationReport | None:
        raw_calls.append(("vcache_load", sha256, (agency_id, validator_version, country_code)))
        return None

    def api_report(
        configured_agency: Agency,
        sha256: str,
        validator_version: str,
    ) -> ValidationReport | None:
        assert configured_agency is agency
        raw_calls.append(("feed_api", sha256, validator_version))
        return None

    def validate_raw(
        path: Path,
        output_dir: Path,
        *,
        country_code: str,
        large_feed: bool = False,
    ) -> Path:
        raw_calls.append(("validator", path, country_code))
        return output_dir / "report.json"

    def store_report(
        agency_id: str,
        sha256: str,
        validator_version: str,
        cached_report: ValidationReport,
        country_code: str = "US",
    ) -> Path:
        assert cached_report is report
        raw_calls.append(("vcache_store", sha256, (agency_id, validator_version, country_code)))
        return tmp_path / "cache" / f"{agency_id}.json"

    def expect_reader(label: str, path: str | Path) -> None:
        assert Path(path) == reader_path
        reader_calls.append(label)

    feed_dates = object()

    def read_dates(path: str) -> object:
        expect_reader("freshness", path)
        return feed_dates

    def score_freshness(
        dates: object,
        *,
        today: dt.date,
        service_type: str,
    ) -> CategoryResult:
        assert dates is feed_dates
        assert today == run_date
        assert service_type == agency.service_type
        return _category("freshness")

    def score_completeness(path: str, *, fare_free: bool) -> CategoryResult:
        expect_reader("completeness", path)
        assert fare_free is True
        return _category("completeness")

    def score_realtime(
        configured_agency: Agency,
        static_path: Path,
        date: dt.date,
        *,
        rt_samples: int,
        rt_interval: int,
    ) -> CategoryResult:
        assert configured_agency is agency
        expect_reader("realtime", static_path)
        assert date == run_date
        assert (rt_samples, rt_interval) == (2, 7)
        return _category("realtime")

    def read_modes(path: str) -> dict[str, Any]:
        expect_reader("modes", path)
        return {"primary_mode": "bus", "modes": ["bus"]}

    def read_ferry(
        path: str,
        *,
        fare_free: bool,
        configured_realtime_kinds: Collection[str],
    ) -> dict[str, Any] | None:
        expect_reader("ferry_profile", path)
        assert fare_free is True
        assert set(configured_realtime_kinds) == set(agency.rt_urls)
        return None

    def read_recommendations(path: str) -> list[dict[str, object]]:
        expect_reader("recommendations", path)
        return []

    def read_geo(path: str) -> dict[str, Any] | None:
        expect_reader("geo", path)
        return None

    def read_geometry(path: str) -> route_geometry.RouteGeometry:
        expect_reader("geometry", path)
        return route_geometry.RouteGeometry(feature_collection=None, summary={})

    def read_export_diff(agency_id: str, path: str, sha256: str) -> dict[str, Any] | None:
        assert agency_id == agency.id
        expect_reader("export_diff", path)
        assert sha256 == digest
        return None

    def read_routability(path: str) -> routability.RoutabilityProfile:
        expect_reader("routability", path)
        return routability.RoutabilityProfile(0, 0, 0, 0, [])

    def read_agency_ids(path: str) -> list[str]:
        expect_reader("ntd_id", path)
        return [agency.ntd_id]

    def read_shapes(path: str) -> gtfs.ShapesCoverage:
        expect_reader("shapes", path)
        return gtfs.ShapesCoverage(total_trips=1, trips_with_shape=1)

    def save_artifact(artifact: dict[str, Any]) -> Path:
        published.update(artifact)
        return tmp_path / "published.json"

    monkeypatch.setattr(cli, "fetch_static", fetch)
    monkeypatch.setattr(archive, "store", store_raw)
    monkeypatch.setattr(vcache, "load_cached", load_report)
    monkeypatch.setattr(cli, "_maybe_api_report", api_report)
    monkeypatch.setattr(cli, "run_validator", validate_raw)
    monkeypatch.setattr(cli, "parse_report", lambda _path: report)
    monkeypatch.setattr(vcache, "store_cached", store_report)
    monkeypatch.setattr(cli, "correctness", lambda checked: _category("correctness"))
    monkeypatch.setattr(cli, "read_feed_dates", read_dates)
    monkeypatch.setattr(cli, "freshness", score_freshness)
    monkeypatch.setattr(cli, "completeness", score_completeness)
    monkeypatch.setattr(cli, "_realtime_category", score_realtime)
    monkeypatch.setattr(modes, "mode_profile_from_zip", read_modes)
    monkeypatch.setattr(ferry_profile, "ferry_profile_from_zip", read_ferry)
    monkeypatch.setattr(recommend, "gather_recommendations", read_recommendations)
    monkeypatch.setattr(
        conformance,
        "assess",
        lambda _artifact: conformance.Conformance(False, [], "Not yet."),
    )
    monkeypatch.setattr(geo, "agency_geo_from_zip", read_geo)
    monkeypatch.setattr(route_geometry, "route_geometry_from_zip", read_geometry)
    monkeypatch.setattr(exportdiff, "export_diff", read_export_diff)
    monkeypatch.setattr(routability, "assess_routability", read_routability)
    monkeypatch.setattr(gtfs, "read_agency_ids", read_agency_ids)
    monkeypatch.setattr(gtfs, "read_shapes_coverage", read_shapes)
    monkeypatch.setattr(mode_language, "adapt_artifact_language", lambda artifact: artifact)
    monkeypatch.setattr(cli, "publish", save_artifact)

    outcome = cli.run_agency(
        agency.id,
        run_date,
        rt_samples=2,
        rt_interval=7,
    )

    assert outcome.path == str(tmp_path / "published.json")
    assert outcome.cache_hit is False
    assert raw_calls == [
        ("archive", digest, raw_path),
        ("vcache_load", digest, (agency.id, VALIDATOR_VERSION, "US")),
        ("feed_api", digest, VALIDATOR_VERSION),
        ("validator", raw_path, "US"),
        ("vcache_store", digest, (agency.id, VALIDATOR_VERSION, "US")),
    ]
    assert Counter(reader_calls) == Counter(
        {
            "freshness": 1,
            "completeness": 1,
            "realtime": 1,
            "modes": 1,
            "ferry_profile": 1,
            "recommendations": 1,
            "geo": 1,
            "geometry": 1,
            "export_diff": 1,
            "routability": 1,
            "ntd_id": 1,
            "shapes": 1,
        }
    )
    assert published["feed"]["sha256"] == digest
    assert published["feed"]["static_url"] == agency.static_gtfs_url
    assert published["fetch"]["final_url"] == fetched.final_url
    assert published["fetch"]["reader_archive_normalized"] is True
    assert published["fetch"]["reader_archive_profile"] == "flat-single-root-v1"


def test_realtime_category_routes_the_reader_view_to_schedule_analyses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "gtfs.zip"
    reader_path = tmp_path / "gtfs.reader.zip"
    agency = Agency(
        id="reader-rt-demo",
        name="Reader RT demo",
        static_gtfs_url="https://example.test/raw.zip",
        rt_urls={
            "trip_updates": "https://example.test/trip-updates.pb",
            "vehicle_positions": "https://example.test/vehicle-positions.pb",
        },
    )
    window = RtWindow(
        samples=[
            RtSample(kind="trip_updates", fetched_at=1, ok=True, header_timestamp=1),
            RtSample(kind="vehicle_positions", fetched_at=1, ok=True, header_timestamp=1),
        ]
    )
    drift_result = DriftStats(1, 0, 0, 1.0)
    plausibility_result = PlausibilityStats(1, 1.0, 0)
    paths: list[Path] = []

    def schedule(path: str, moment: dt.datetime) -> set[str]:
        assert moment.tzinfo is not None
        paths.append(Path(path))
        return {"T1"}

    def drift(samples: list[RtSample], path: str) -> DriftStats:
        assert samples is window.samples
        paths.append(Path(path))
        return drift_result

    def plausibility(samples: list[RtSample], path: str) -> PlausibilityStats:
        assert samples is window.samples
        paths.append(Path(path))
        return plausibility_result

    def score(
        scored_window: RtWindow,
        scheduled: set[str] | None,
        drift: DriftStats | None = None,
        plausibility: PlausibilityStats | None = None,
        configured_kinds: Collection[str] | None = None,
    ) -> CategoryResult:
        assert scored_window is window
        assert scheduled == {"T1"}
        assert drift is drift_result
        assert plausibility is plausibility_result
        assert set(configured_kinds or ()) == set(agency.rt_urls)
        return _category("realtime")

    monkeypatch.setattr(cli, "capture_window", lambda *_args, **_kwargs: window)
    monkeypatch.setattr(cli, "scheduled_trip_ids_at", schedule)
    monkeypatch.setattr(cli, "compute_drift", drift)
    monkeypatch.setattr(cli, "vehicle_plausibility", plausibility)
    monkeypatch.setattr(cli, "realtime", score)

    result = cli._realtime_category(
        agency,
        reader_path,
        dt.date(2026, 7, 16),
        rt_samples=2,
        rt_interval=0,
    )

    assert result.name == "realtime"
    assert paths == [reader_path, reader_path, reader_path]
    assert raw_path not in paths


def test_oversized_routability_table_is_reported_as_unmeasured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    reader_path = tmp_path / "national.reader.zip"

    def oversized(_path: str) -> routability.RoutabilityProfile:
        raise gtfs.TableTooLargeError("stop_times.txt exceeds the safety cap")

    monkeypatch.setattr(routability, "assess_routability", oversized)

    block = cli._routability_block(reader_path)

    assert block == {
        "measured": False,
        "reason": "table_too_large",
        "findings": [],
    }
    assert "routability not measured" in caplog.text
