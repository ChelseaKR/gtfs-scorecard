"""Tests for the sha256-keyed validator-result cache."""

from __future__ import annotations

from pathlib import Path

import pytest

import scorecard_pipeline.vcache as vcache
from scorecard_pipeline.validate import NoticeGroup, ValidationReport

REPORT = ValidationReport(
    validator_version="8.0.1",
    notices=[
        NoticeGroup(
            code="missing_recommended_field", severity="WARNING", total=2, sample_notices=[{"x": 1}]
        ),
        NoticeGroup(code="fast_travel", severity="ERROR", total=5, sample_notices=[]),
    ],
)


def _point_cache_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vcache, "artifacts_dir", lambda: tmp_path)


def test_store_then_load_round_trips_the_report(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)
    vcache.store_cached("demo", "abc123", "8.0.1", REPORT)
    got = vcache.load_cached("demo", "abc123", "8.0.1")
    assert got is not None
    assert got.validator_version == "8.0.1"
    assert [(n.code, n.severity, n.total) for n in got.notices] == [
        ("missing_recommended_field", "WARNING", 2),
        ("fast_travel", "ERROR", 5),
    ]
    assert got.notices[0].sample_notices == [{"x": 1}]


def test_miss_when_feed_bytes_differ(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)
    vcache.store_cached("demo", "abc123", "8.0.1", REPORT)
    # A different feed hash means the feed changed: must re-validate.
    assert vcache.load_cached("demo", "different", "8.0.1") is None


def test_miss_when_validator_version_changed(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)
    vcache.store_cached("demo", "abc123", "8.0.1", REPORT)
    # A new validator may emit different notices, so the old cache is stale.
    assert vcache.load_cached("demo", "abc123", "9.0.0") is None


def test_miss_when_validator_country_changed(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)
    vcache.store_cached("demo", "abc123", "8.0.1", REPORT, country_code="CA")

    assert vcache.load_cached("demo", "abc123", "8.0.1", country_code="CA") is not None
    assert vcache.load_cached("demo", "abc123", "8.0.1", country_code="US") is None


def test_historical_countryless_cache_is_us_only(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)
    path = vcache.cache_path("demo")
    vcache._write_local(
        path,
        {
            "sha256": "abc123",
            "validator_version": "8.0.1",
            "report": vcache._report_to_json(REPORT),
        },
    )

    assert vcache.load_cached("demo", "abc123", "8.0.1", country_code="US") is not None
    assert vcache.load_cached("demo", "abc123", "8.0.1", country_code="GB") is None


def test_miss_when_no_cache_file(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)
    assert vcache.load_cached("never-scored", "abc123", "8.0.1") is None


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3:
    """An in-memory stand-in for the boto3 S3 client used by the cache."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], bytes] = {}
        self.get_calls = 0
        self.put_calls = 0

    def get_object(self, Bucket: str, Key: str):  # type: ignore[no-untyped-def]
        self.get_calls += 1
        try:
            return {"Body": _FakeBody(self.store[(Bucket, Key)])}
        except KeyError as exc:
            raise RuntimeError("NoSuchKey") from exc

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_: object):  # type: ignore[no-untyped-def]
        self.put_calls += 1
        self.store[(Bucket, Key)] = Body


def _use_s3(monkeypatch: pytest.MonkeyPatch, client: _FakeS3, bucket: str = "cache-bkt") -> None:
    monkeypatch.setenv("VALIDATOR_CACHE_BUCKET", bucket)
    monkeypatch.setattr(vcache, "_s3_client", lambda: client)


def test_store_writes_to_both_local_and_s3(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)
    s3 = _FakeS3()
    _use_s3(monkeypatch, s3)
    vcache.store_cached("demo", "abc123", "8.0.1", REPORT)
    assert vcache.cache_path("demo").exists()
    assert ("cache-bkt", vcache._s3_key("demo")) in s3.store
    assert s3.put_calls == 1


def test_load_falls_back_to_s3_and_writes_through(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Populate S3 only, then drop the local file: the next load must hit S3 and
    # rehydrate the local file (the cold-checkout case once artifacts leave git).
    _point_cache_at(tmp_path, monkeypatch)
    s3 = _FakeS3()
    _use_s3(monkeypatch, s3)
    vcache.store_cached("demo", "abc123", "8.0.1", REPORT)
    vcache.cache_path("demo").unlink()

    got = vcache.load_cached("demo", "abc123", "8.0.1")
    assert got is not None
    assert [(n.code, n.total) for n in got.notices] == [
        ("missing_recommended_field", 2),
        ("fast_travel", 5),
    ]
    assert s3.get_calls == 1
    assert vcache.cache_path("demo").exists()  # written through


def test_local_hit_skips_s3(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)
    s3 = _FakeS3()
    _use_s3(monkeypatch, s3)
    vcache.store_cached("demo", "abc123", "8.0.1", REPORT)
    s3.get_calls = 0  # the local file is present; load must not touch S3
    assert vcache.load_cached("demo", "abc123", "8.0.1") is not None
    assert s3.get_calls == 0


def test_s3_errors_never_fail_a_score(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)

    class _Broken(_FakeS3):
        def get_object(self, Bucket, Key):  # type: ignore[no-untyped-def]
            raise RuntimeError("S3 down")

        def put_object(self, Bucket, Key, Body, **_):  # type: ignore[no-untyped-def]
            raise RuntimeError("S3 down")

    _use_s3(monkeypatch, _Broken())
    # Store still writes the local file; load still misses cleanly.
    vcache.store_cached("demo", "abc123", "8.0.1", REPORT)
    assert vcache.cache_path("demo").exists()
    vcache.cache_path("demo").unlink()
    assert vcache.load_cached("demo", "abc123", "8.0.1") is None


def test_no_bucket_keeps_file_only_behaviour(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_cache_at(tmp_path, monkeypatch)
    monkeypatch.delenv("VALIDATOR_CACHE_BUCKET", raising=False)
    monkeypatch.delenv("ARTIFACTS_BUCKET", raising=False)
    # _s3_client must never be called when no bucket is configured.
    monkeypatch.setattr(
        vcache, "_s3_client", lambda: (_ for _ in ()).throw(AssertionError("S3 used"))
    )
    vcache.store_cached("demo", "abc123", "8.0.1", REPORT)
    assert vcache.load_cached("demo", "abc123", "8.0.1") is not None
