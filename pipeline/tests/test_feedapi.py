"""Tests for the Mobility Feed API ingest (pure parsing + guarded reuse)."""

from __future__ import annotations

from typing import Any

import pytest

from scorecard_pipeline.feedapi import (
    ApiDataset,
    ApiValidation,
    feed_id_for,
    parse_dataset,
    parse_feeds,
    report_from_api,
    reuse_reason,
)

_REPORT = {
    "summary": {"validatorVersion": "8.0.1"},
    "notices": [
        {"code": "stop_too_far_from_shape", "severity": "WARNING", "totalNotices": 4},
        {"code": "missing_timepoint_value", "severity": "ERROR", "totalNotices": 1},
    ],
}


def _dataset(
    *, sha: str = "abc123", version: str = "8.0.1", url_json: str = "https://x/report.json"
) -> ApiDataset:
    return ApiDataset(
        dataset_id="mdb-1-202606",
        feed_id="mdb-1",
        hosted_url="https://gcs/mdb-1.zip",
        downloaded_at="2026-06-20",
        sha256=sha,
        validation=ApiValidation(
            validator_version=version,
            total_error=1,
            total_warning=4,
            total_info=0,
            url_json=url_json,
        ),
    )


def test_feed_id_for_normalizes_bare_mdb_ids() -> None:
    assert feed_id_for("1234") == "mdb-1234"
    assert feed_id_for("mdb-1234") == "mdb-1234"
    assert feed_id_for("001234") == "mdb-1234"
    assert feed_id_for("mdb-001234") == "mdb-1234"
    assert feed_id_for("nonlegacy-id") == "nonlegacy-id"
    assert feed_id_for("") == ""


def test_parse_dataset_reads_hash_and_validation() -> None:
    ds = parse_dataset(
        {
            "id": "mdb-1-202606",
            "feed_id": "mdb-1",
            "hosted_url": "https://gcs/mdb-1.zip",
            "downloaded_at": "2026-06-20",
            "hash": "deadbeef",
            "validation_report": {
                "validator_version": "8.0.1",
                "total_error": 2,
                "total_warning": 5,
                "total_info": 1,
                "url_json": "https://x/report.json",
            },
        }
    )
    assert ds.sha256 == "deadbeef"
    assert ds.validation is not None
    assert ds.validation.total_error == 2
    assert ds.validation.url_json.endswith("report.json")


def test_parse_dataset_tolerates_missing_validation() -> None:
    ds = parse_dataset({"id": "d", "feed_id": "mdb-1", "hash": "h"})
    assert ds.validation is None
    assert ds.hosted_url == ""


def test_parse_feeds_reads_producer_url_and_location() -> None:
    feeds = parse_feeds(
        [
            {
                "id": "mdb-1",
                "provider": "Yolobus",
                "data_type": "gtfs",
                "source_info": {"producer_url": "https://agency/gtfs.zip"},
                "locations": [{"country_code": "US", "subdivision_name": "California"}],
            }
        ]
    )
    assert feeds[0].producer_url == "https://agency/gtfs.zip"
    assert feeds[0].subdivision == "California"


def test_reuse_allowed_on_exact_hash_and_version_match() -> None:
    assert reuse_reason(_dataset(), "abc123", "8.0.1") is None
    # Hash comparison is case-insensitive.
    assert reuse_reason(_dataset(sha="ABC123"), "abc123", "8.0.1") is None


def test_reuse_blocked_when_bytes_differ() -> None:
    reason = reuse_reason(_dataset(sha="other"), "abc123", "8.0.1")
    assert reason is not None and "bytes differ" in reason


def test_reuse_blocked_on_validator_version_mismatch() -> None:
    reason = reuse_reason(_dataset(version="7.1.0"), "abc123", "8.0.1")
    assert reason is not None and "validator version differs" in reason


def test_reuse_blocked_without_report_or_link() -> None:
    assert reuse_reason(_dataset(url_json=""), "abc123", "8.0.1") == "no report link"
    bare = ApiDataset("d", "mdb-1", "", "", "abc123", validation=None)
    assert reuse_reason(bare, "abc123", "8.0.1") == "no validation report"


def test_report_from_api_parses_when_reuse_is_safe() -> None:
    calls: list[str] = []

    def fake_fetch(url: str) -> dict[str, Any]:
        calls.append(url)
        return _REPORT

    report = report_from_api(_dataset(), "abc123", "8.0.1", fetch_report=fake_fetch)
    assert report is not None
    assert report.validator_version == "8.0.1"
    assert report.count_by_severity()["ERROR"] == 1
    assert report.count_by_severity()["WARNING"] == 4
    assert calls == ["https://x/report.json"]


def test_report_from_api_returns_none_on_mismatch_without_fetching() -> None:
    def boom(url: str) -> dict[str, Any]:
        raise AssertionError("should not fetch on a hash mismatch")

    assert report_from_api(_dataset(sha="other"), "abc123", "8.0.1", fetch_report=boom) is None


def test_report_from_api_falls_back_when_fetch_fails() -> None:
    def boom(url: str) -> dict[str, Any]:
        raise RuntimeError("network down")

    assert report_from_api(_dataset(), "abc123", "8.0.1", fetch_report=boom) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
