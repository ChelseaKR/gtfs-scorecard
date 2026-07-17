"""Country identity across the daily pipeline's validator boundary."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

import scorecard_pipeline.archive as archive
import scorecard_pipeline.cli as cli
import scorecard_pipeline.feedapi as feedapi
from scorecard_pipeline.config import AGENCIES, Agency
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.validate import VALIDATOR_VERSION, ValidationReport
from scorecard_pipeline.vcache import load_cached


class _StopAfterValidation(RuntimeError):
    """End the large daily pipeline once validator/cache behavior is observed."""


def test_daily_run_passes_country_and_country_scopes_reusable_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agency = Agency(
        id="canadian-demo",
        name="Canadian Demo",
        static_gtfs_url="https://example.test/gtfs.zip",
        country="CA",
    )
    AGENCIES[agency.id] = agency
    feed = tmp_path / "gtfs.zip"
    feed.write_bytes(b"PK")
    fetched = FetchResult(
        agency_id=agency.id,
        path=feed,
        url=agency.static_gtfs_url,
        fetched_date=dt.date(2026, 7, 12),
        sha256="ab" * 32,
        size_bytes=2,
        reused=False,
    )
    validator_calls: list[tuple[str, str]] = []
    report = ValidationReport(validator_version=VALIDATOR_VERSION, notices=[])

    monkeypatch.delenv("MOBILITY_FEED_API_TOKEN", raising=False)
    monkeypatch.setattr(cli, "fetch_static", lambda *_args, **_kwargs: fetched)
    monkeypatch.setattr(archive, "store", lambda *_args, **_kwargs: None)

    def validate(
        _feed: Path,
        output_dir: Path,
        *,
        country_code: str,
    ) -> Path:
        validator_calls.append((country_code, output_dir.name))
        return output_dir / "report.json"

    def stop_after_validation(_report: ValidationReport) -> None:
        raise _StopAfterValidation

    monkeypatch.setattr(cli, "run_validator", validate)
    monkeypatch.setattr(cli, "parse_report", lambda _path: report)
    monkeypatch.setattr(cli, "correctness", stop_after_validation)

    with pytest.raises(_StopAfterValidation):
        cli.run_agency(agency.id, dt.date(2026, 7, 12), force_fetch=True, skip_rt=True)

    assert validator_calls == [("CA", "validator-ca")]
    assert (
        load_cached(
            agency.id,
            fetched.sha256,
            VALIDATOR_VERSION,
            country_code="CA",
        )
        is not None
    )
    assert (
        load_cached(
            agency.id,
            fetched.sha256,
            VALIDATOR_VERSION,
            country_code="US",
        )
        is None
    )


def test_non_us_feed_does_not_reuse_country_unproven_feed_api_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agency = Agency(
        id="japanese-demo",
        name="Japanese Demo",
        static_gtfs_url="https://example.test/gtfs.zip",
        country="JP",
        mdb_id="mdb-jp",
    )
    monkeypatch.setenv("MOBILITY_FEED_API_TOKEN", "token")

    def unexpected_reuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("non-US validation must run locally with an explicit country")

    monkeypatch.setattr(feedapi, "try_cached_report", unexpected_reuse)

    assert cli._maybe_api_report(agency, "ab" * 32, VALIDATOR_VERSION) is None
