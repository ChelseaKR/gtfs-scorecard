"""Exact-key S3 hydration contracts for bounded production activation."""

from __future__ import annotations

import datetime as dt
import io
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.activation import (
    ActivationHydrationError,
    hydrate_activation_corpus,
)

LAST_MODIFIED = dt.datetime(2026, 7, 1, 12, 0, tzinfo=dt.UTC)


class FakeS3Error(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakePaginator:
    def __init__(self, client: FakeS3) -> None:
        self.client = client

    def paginate(self, *, Bucket: str, Prefix: str):  # type: ignore[no-untyped-def]
        assert Bucket == self.client.bucket
        self.client.listed.append(Prefix)
        keys = sorted(key for key in self.client.objects if key.startswith(Prefix))
        return [{"Contents": [{"Key": key} for key in keys]}]


class FakeS3:
    def __init__(
        self,
        objects: dict[str, bytes],
        *,
        failures: dict[str, str] | None = None,
    ) -> None:
        self.bucket = "artifacts"
        self.objects = objects
        self.failures = failures or {}
        self.requested: list[str] = []
        self.listed: list[str] = []
        self._lock = threading.Lock()

    def get_object(self, **kwargs: object) -> dict[str, Any]:
        assert kwargs["Bucket"] == self.bucket
        key = str(kwargs["Key"])
        with self._lock:
            self.requested.append(key)
        if key in self.failures:
            raise FakeS3Error(self.failures[key])
        if key not in self.objects:
            raise FakeS3Error("NoSuchKey")
        response: dict[str, Any] = {
            "Body": io.BytesIO(self.objects[key]),
            "LastModified": LAST_MODIFIED,
        }
        if key == "data/artifacts/index.json":
            response["ETag"] = '"index-etag"'
        return response

    def get_paginator(self, operation_name: str) -> FakePaginator:
        assert operation_name == "list_objects_v2"
        return FakePaginator(self)


def _artifact(
    agency_id: str,
    date: str,
    *,
    score: int | None = None,
    grade: str | None = None,
) -> bytes:
    default_score, default_grade = (80, "B") if agency_id == "agency-one" else (70, "C")
    return (
        json.dumps(
            {
                "agency": {"id": agency_id},
                "snapshot_date": date,
                "overall": {
                    "score": default_score if score is None else score,
                    "grade": default_grade if grade is None else grade,
                },
                "categories": {},
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _index() -> bytes:
    return (
        json.dumps(
            {
                "schema_version": "1.8",
                "agencies": {
                    "agency-one": {
                        "name": "One",
                        "history": [{"date": "2026-07-10", "score": 80, "grade": "B"}],
                    },
                    "agency-two": {
                        "name": "Two",
                        "history": [{"date": "2026-07-09", "score": 70, "grade": "C"}],
                    },
                    "old-orphan": {
                        "name": "Old",
                        "history": [{"date": "2026-01-01", "score": 60, "grade": "D"}],
                    },
                },
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _objects() -> dict[str, bytes]:
    return {
        "data/artifacts/index.json": _index(),
        "data/artifacts/agency-one/latest.json": _artifact("agency-one", "2026-07-10"),
        "data/artifacts/agency-one/fixlog.json": b'{"receipts": []}\n',
        "data/artifacts/agency-two/latest.json": _artifact("agency-two", "2026-07-09"),
        # The selected current dated object has expired. Its full directory is
        # still hydrated, but the hydrator must not recreate that remote object.
        "data/artifacts/agency-two/2026-07-01.json": _artifact("agency-two", "2026-07-01"),
        "data/artifacts/agency-two/corrected.zip": b"PK\x03\x04selected-history",
        "data/artifacts/agency-two/geometry.geojson": b'{"type":"FeatureCollection"}\n',
        "data/artifacts/rollups/index.json": b'{"rollups": []}\n',
        "data/artifacts/changes/latest.json": b'{"changes": []}\n',
        "data/artifacts/run/latest.json": b'{"status": "daily"}\n',
    }


def _hydrate(tmp_path: Path, client: FakeS3, **kwargs: object):  # type: ignore[no-untyped-def]
    return hydrate_activation_corpus(
        bucket="artifacts",
        targets=["agency-two"],
        known_ids={"agency-one", "agency-two"},
        artifacts_root=tmp_path / "artifacts",
        index_before=tmp_path / "index.before.json",
        etag_out=tmp_path / "index.etag",
        liveness_out=tmp_path / "liveness.json",
        workers=4,
        client=client,
        **kwargs,
    )


def test_hydrates_exact_current_corpus_and_only_bounded_prefixes(tmp_path: Path) -> None:
    client = FakeS3(_objects())

    result = _hydrate(tmp_path, client)

    root = tmp_path / "artifacts"
    assert (root / "index.json").read_bytes() == _index()
    assert (tmp_path / "index.before.json").read_bytes() == _index()
    assert (tmp_path / "index.etag").read_text() == '"index-etag"\n'
    assert (root / "agency-one/latest.json").read_bytes() == _artifact("agency-one", "2026-07-10")
    assert (root / "agency-one/2026-07-10.json").read_bytes() == (
        root / "agency-one/latest.json"
    ).read_bytes()
    assert (root / "agency-one/latest.json").stat().st_mtime == LAST_MODIFIED.timestamp()
    assert not (root / "agency-two/2026-07-09.json").exists()
    assert (root / "agency-two/2026-07-01.json").exists()
    assert (root / "agency-two/corrected.zip").read_bytes().startswith(b"PK")
    assert (root / "agency-two/geometry.geojson").exists()
    assert (root / "rollups/index.json").exists()
    assert (root / "changes/latest.json").exists()
    assert (root / "run/latest.json").read_text() == '{"status": "daily"}\n'
    assert not (root / "old-orphan").exists()
    assert "data/artifacts/old-orphan/latest.json" not in client.requested
    assert {
        "data/artifacts/rollups/",
        "data/artifacts/changes/",
        "data/artifacts/run/",
        "data/artifacts/agency-two/",
    } == set(client.listed)
    assert result.agencies == 2
    assert result.selected_objects == 4
    # agency-two fixlog, agency-one's lifecycle-expired dated object, and liveness.
    assert result.optional_misses == 3
    assert result.skipped_unregistered == 1


def test_missing_required_latest_aborts(tmp_path: Path) -> None:
    objects = _objects()
    del objects["data/artifacts/agency-one/latest.json"]

    with pytest.raises(ActivationHydrationError, match=r"agency-one/latest\.json"):
        _hydrate(tmp_path, FakeS3(objects))


def test_non_missing_optional_error_aborts(tmp_path: Path) -> None:
    client = FakeS3(
        _objects(),
        failures={"data/artifacts/agency-one/fixlog.json": "AccessDenied"},
    )

    with pytest.raises(ActivationHydrationError, match="AccessDenied"):
        _hydrate(tmp_path, client)


def test_latest_must_match_captured_index_date(tmp_path: Path) -> None:
    objects = _objects()
    objects["data/artifacts/agency-one/latest.json"] = _artifact("agency-one", "2026-07-11")

    with pytest.raises(ActivationHydrationError, match="latest/index date mismatch"):
        _hydrate(tmp_path, FakeS3(objects))


def test_latest_must_match_captured_index_summary(tmp_path: Path) -> None:
    objects = _objects()
    objects["data/artifacts/agency-one/latest.json"] = _artifact(
        "agency-one", "2026-07-10", score=79
    )

    with pytest.raises(ActivationHydrationError, match="latest/index summary mismatch"):
        _hydrate(tmp_path, FakeS3(objects))


def test_present_current_dated_object_must_equal_latest(tmp_path: Path) -> None:
    objects = _objects()
    current_key = "data/artifacts/agency-one/2026-07-10.json"
    objects[current_key] = objects["data/artifacts/agency-one/latest.json"]

    client = FakeS3(objects)
    result = _hydrate(tmp_path, client)

    assert current_key in client.requested
    assert result.optional_misses == 2  # agency-two fixlog and liveness only


def test_divergent_current_dated_object_aborts(tmp_path: Path) -> None:
    objects = _objects()
    objects["data/artifacts/agency-one/2026-07-10.json"] = (
        objects["data/artifacts/agency-one/latest.json"] + b" "
    )

    with pytest.raises(ActivationHydrationError, match="latest/dated payload mismatch"):
        _hydrate(tmp_path, FakeS3(objects))


@pytest.mark.parametrize("unsafe_date", ["../../escape", "20260710", "2026-7-10", "2026-02-30"])
def test_snapshot_date_must_be_canonical_and_cannot_escape_root(
    tmp_path: Path, unsafe_date: str
) -> None:
    objects = _objects()
    index = json.loads(objects["data/artifacts/index.json"])
    index["agencies"]["agency-one"]["history"][-1]["date"] = unsafe_date
    objects["data/artifacts/index.json"] = (json.dumps(index) + "\n").encode()
    objects["data/artifacts/agency-one/latest.json"] = _artifact("agency-one", unsafe_date)

    with pytest.raises(ActivationHydrationError, match="snapshot date"):
        _hydrate(tmp_path, FakeS3(objects))

    assert not (tmp_path / "escape.json").exists()


@pytest.mark.parametrize(
    "unsafe_key",
    [
        "data/artifacts/agency-two/./alias.json",
        "data/artifacts/agency-two//alias.json",
        "data/artifacts/agency-two/../alias.json",
    ],
)
def test_listed_keys_cannot_alias_local_paths(tmp_path: Path, unsafe_key: str) -> None:
    objects = _objects()
    objects[unsafe_key] = b"unsafe"

    with pytest.raises(ActivationHydrationError, match="unsafe artifact key"):
        _hydrate(tmp_path, FakeS3(objects))


def test_casefolded_destination_collision_aborts(tmp_path: Path) -> None:
    objects = _objects()
    objects["data/artifacts/agency-two/Alias.json"] = b"one"
    objects["data/artifacts/agency-two/alias.json"] = b"two"

    with pytest.raises(ActivationHydrationError, match="same local path"):
        _hydrate(tmp_path, FakeS3(objects))


def test_s3_key_cannot_collide_with_atomic_temporary_name(tmp_path: Path) -> None:
    objects = _objects()
    key = "data/artifacts/agency-two/.latest.json.tmp"
    objects[key] = b"listed object"

    _hydrate(tmp_path, FakeS3(objects))

    root = tmp_path / "artifacts/agency-two"
    assert (root / ".latest.json.tmp").read_bytes() == b"listed object"
    assert (root / "latest.json").read_bytes() == _artifact("agency-two", "2026-07-09")


@pytest.mark.parametrize("workers", [0, 33])
def test_concurrency_is_bounded(tmp_path: Path, workers: int) -> None:
    with pytest.raises(ActivationHydrationError, match="workers must be between"):
        hydrate_activation_corpus(
            bucket="artifacts",
            targets=["agency-two"],
            known_ids={"agency-one", "agency-two"},
            artifacts_root=tmp_path / "artifacts",
            index_before=tmp_path / "index.before.json",
            etag_out=tmp_path / "index.etag",
            liveness_out=tmp_path / "liveness.json",
            workers=workers,
            client=FakeS3(_objects()),
        )
