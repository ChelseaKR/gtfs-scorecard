"""Exact-key S3 hydration contracts for bounded production activation."""

from __future__ import annotations

import datetime as dt
import io
import json
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.activation import (
    S3_OBJECT_RETRY_BASE_SECONDS,
    ActivationHydrationError,
    HydrationResult,
    _download_one,
    hydrate_activation_corpus,
    materialize_local_current_artifacts,
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
        page_size = self.client.page_size or max(1, len(keys))
        return [
            {"Contents": [{"Key": key} for key in keys[offset : offset + page_size]]}
            for offset in range(0, max(1, len(keys)), page_size)
        ]


class TrackingBody:
    """StreamingBody stand-in that can fail after returning partial content."""

    def __init__(self, data: bytes, *, fail_on_read: int | None = None) -> None:
        self._stream = io.BytesIO(data)
        self.fail_on_read = fail_on_read
        self.read_calls = 0
        self.close_calls = 0

    def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        if self.read_calls == self.fail_on_read:
            raise TimeoutError("transient streaming timeout")
        return self._stream.read(size)

    def close(self) -> None:
        self.close_calls += 1
        self._stream.close()


class FakeS3:
    def __init__(
        self,
        objects: dict[str, bytes],
        *,
        failures: dict[str, str | list[str]] | None = None,
        body_sequences: dict[str, list[object]] | None = None,
        page_size: int | None = None,
    ) -> None:
        self.bucket = "artifacts"
        self.objects = objects
        self.failures = {
            key: list(value) if isinstance(value, list) else value
            for key, value in (failures or {}).items()
        }
        self.body_sequences = {key: list(bodies) for key, bodies in (body_sequences or {}).items()}
        self.page_size = page_size
        self.requested: list[str] = []
        self.listed: list[str] = []
        self._lock = threading.Lock()

    def get_object(self, **kwargs: object) -> dict[str, Any]:
        assert kwargs["Bucket"] == self.bucket
        key = str(kwargs["Key"])
        with self._lock:
            self.requested.append(key)
            bodies = self.body_sequences.get(key)
            body = bodies.pop(0) if bodies else None
            failure = self.failures.get(key)
            failure_code = failure.pop(0) if isinstance(failure, list) and failure else failure
        if isinstance(failure_code, str):
            raise FakeS3Error(failure_code)
        if key not in self.objects:
            raise FakeS3Error("NoSuchKey")
        response: dict[str, Any] = {
            "Body": body or io.BytesIO(self.objects[key]),
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


def _no_sleep(_delay: float) -> None:
    pass


def _hydrate(
    tmp_path: Path,
    client: FakeS3,
    *,
    sleeper: Callable[[float], None] = _no_sleep,
) -> HydrationResult:
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
        sleeper=sleeper,
    )


def test_hydrates_exact_current_corpus_and_only_bounded_prefixes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
    assert "title=noncurrent/unregistered index entries" in capsys.readouterr().err


def test_paginator_consumes_every_page_for_selected_and_aggregate_prefixes(
    tmp_path: Path,
) -> None:
    client = FakeS3(_objects(), page_size=1)

    result = _hydrate(tmp_path, client)

    root = tmp_path / "artifacts"
    assert result.selected_objects == 4
    assert (root / "agency-two/corrected.zip").read_bytes() == b"PK\x03\x04selected-history"
    assert (root / "agency-two/geometry.geojson").exists()
    assert (root / "rollups/index.json").exists()
    assert (root / "changes/latest.json").exists()
    assert (root / "run/latest.json").exists()


def test_transient_stream_failure_retries_the_whole_object_and_closes_each_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "data/artifacts/agency-one/latest.json"
    payload = _objects()[key]
    failed = TrackingBody(payload, fail_on_read=2)
    succeeded = TrackingBody(payload)
    client = FakeS3(_objects(), body_sequences={key: [failed, succeeded]})
    delays: list[float] = []
    temporary_names: list[str] = []
    named_temporary_file = tempfile.NamedTemporaryFile

    def recording_named_temporary_file(*args: Any, **kwargs: Any) -> Any:
        output = named_temporary_file(*args, **kwargs)
        temporary_names.append(output.name)
        return output

    monkeypatch.setattr(
        "scorecard_pipeline.activation.tempfile.NamedTemporaryFile",
        recording_named_temporary_file,
    )

    destination = tmp_path / "agency-one/latest.json"
    assert _download_one(
        client,
        "artifacts",
        key,
        destination,
        optional=False,
        sleeper=delays.append,
    )

    assert destination.read_bytes() == payload
    assert client.requested.count(key) == 2
    assert failed.close_calls == 1
    assert succeeded.close_calls == 1
    assert delays == [S3_OBJECT_RETRY_BASE_SECONDS]
    assert len(temporary_names) == 2
    assert len(set(temporary_names)) == 2
    assert not list(destination.parent.glob(f".{destination.name}.*.tmp"))


def test_transient_get_object_error_retries_from_the_start(tmp_path: Path) -> None:
    key = "data/artifacts/agency-one/latest.json"
    client = FakeS3(_objects(), failures={key: ["SlowDown"]})
    delays: list[float] = []

    assert _download_one(
        client,
        "artifacts",
        key,
        tmp_path / "latest.json",
        optional=False,
        sleeper=delays.append,
    )

    assert client.requested.count(key) == 2
    assert delays == [S3_OBJECT_RETRY_BASE_SECONDS]


def test_transient_index_stream_failure_retries_same_get_capture_and_closes_bodies(
    tmp_path: Path,
) -> None:
    key = "data/artifacts/index.json"
    payload = _objects()[key]
    failed = TrackingBody(payload, fail_on_read=2)
    succeeded = TrackingBody(payload)
    client = FakeS3(_objects(), body_sequences={key: [failed, succeeded]})
    delays: list[float] = []

    _hydrate(tmp_path, client, sleeper=delays.append)

    assert (tmp_path / "index.before.json").read_bytes() == payload
    assert (tmp_path / "index.etag").read_text() == '"index-etag"\n'
    assert client.requested.count(key) == 2
    assert failed.close_calls == 1
    assert succeeded.close_calls == 1
    assert delays == [S3_OBJECT_RETRY_BASE_SECONDS]


def test_transient_stream_failure_exhaustion_aborts_without_partial_destination(
    tmp_path: Path,
) -> None:
    key = "data/artifacts/agency-two/corrected.zip"
    bodies = [TrackingBody(_objects()[key], fail_on_read=2) for _ in range(3)]
    body_sequences: dict[str, list[object]] = {key: list(bodies)}
    client = FakeS3(_objects(), body_sequences=body_sequences)
    delays: list[float] = []

    with pytest.raises(ActivationHydrationError, match=r"after 3 attempts"):
        _hydrate(tmp_path, client, sleeper=delays.append)

    destination = tmp_path / "artifacts/agency-two/corrected.zip"
    assert not destination.exists()
    assert client.requested.count(key) == 3
    assert [body.close_calls for body in bodies] == [1, 1, 1]
    assert delays == [S3_OBJECT_RETRY_BASE_SECONDS, S3_OBJECT_RETRY_BASE_SECONDS * 2]
    assert not list(destination.parent.glob(f".{destination.name}.*.tmp"))


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

    delays: list[float] = []
    with pytest.raises(ActivationHydrationError, match="AccessDenied"):
        _hydrate(tmp_path, client, sleeper=delays.append)

    assert client.requested.count("data/artifacts/agency-one/fixlog.json") == 1
    assert delays == []


def test_local_destination_failure_does_not_retry_remote_object(tmp_path: Path) -> None:
    key = "data/artifacts/agency-one/latest.json"
    body = TrackingBody(_objects()[key])
    client = FakeS3(_objects(), body_sequences={key: [body]})
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("file")
    delays: list[float] = []

    with pytest.raises(ActivationHydrationError, match="could not write"):
        _download_one(
            client,
            "artifacts",
            key,
            blocked_parent / "latest.json",
            optional=False,
            sleeper=delays.append,
        )

    assert client.requested.count(key) == 1
    assert body.close_calls == 1
    assert delays == []


def test_body_validation_failure_does_not_retry(tmp_path: Path) -> None:
    key = "data/artifacts/agency-one/latest.json"

    class NonByteBody:
        close_calls = 0

        def read(self, _size: int) -> str:
            return "not bytes"

        def close(self) -> None:
            self.close_calls += 1

    body = NonByteBody()
    client = FakeS3(_objects(), body_sequences={key: [body]})
    delays: list[float] = []

    with pytest.raises(ActivationHydrationError, match="non-byte content"):
        _download_one(
            client,
            "artifacts",
            key,
            tmp_path / "latest.json",
            optional=False,
            sleeper=delays.append,
        )

    assert client.requested.count(key) == 1
    assert body.close_calls == 1
    assert delays == []


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


def test_local_current_materializer_restores_lifecycle_expired_dated_record(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    agency = root / "agency-one"
    agency.mkdir(parents=True)
    index = {
        "agencies": {
            "agency-one": {
                "history": [{"date": "2026-07-10", "score": 80, "grade": "B"}],
            }
        }
    }
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    latest = _artifact("agency-one", "2026-07-10")
    (agency / "latest.json").write_bytes(latest)

    assert materialize_local_current_artifacts(artifacts_root=root) == 1
    assert (agency / "2026-07-10.json").read_bytes() == latest
    assert materialize_local_current_artifacts(artifacts_root=root) == 0


def test_local_current_materializer_rewrites_stale_dated_record(tmp_path: Path) -> None:
    """A checkout's dated record lagging latest.json is repaired, not fatal.

    snapshot_date names the feed's snapshot, so an agency whose feed has not
    changed keeps one dated filename across many refreshes of its artifact. The
    bounded sync only pulls today's and yesterday's dated objects, so that file
    comes from git and can lag. Aborting here took the daily publish down.
    """
    root = tmp_path / "artifacts"
    agency = root / "agency-one"
    agency.mkdir(parents=True)
    index = {
        "agencies": {
            "agency-one": {
                "history": [{"date": "2026-07-10", "score": 80, "grade": "B"}],
            }
        }
    }
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    latest = _artifact("agency-one", "2026-07-10")
    (agency / "latest.json").write_bytes(latest)
    (agency / "2026-07-10.json").write_text("{}\n", encoding="utf-8")

    assert materialize_local_current_artifacts(artifacts_root=root) == 1
    assert (agency / "2026-07-10.json").read_bytes() == latest
    # Idempotent: a second pass has nothing left to repair.
    assert materialize_local_current_artifacts(artifacts_root=root) == 0


def test_local_current_materializer_still_rejects_index_disagreement(tmp_path: Path) -> None:
    """Repairing a stale dated record must not soften the real corruption gate.

    index.json is refreshed by every sync, so latest.json disagreeing with it
    means the authoritative store is inconsistent. That still fails closed.
    """
    root = tmp_path / "artifacts"
    agency = root / "agency-one"
    agency.mkdir(parents=True)
    index = {
        "agencies": {
            "agency-one": {
                "history": [{"date": "2026-07-11", "score": 80, "grade": "B"}],
            }
        }
    }
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (agency / "latest.json").write_bytes(_artifact("agency-one", "2026-07-10"))
    (agency / "2026-07-10.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ActivationHydrationError, match="latest/index date mismatch"):
        materialize_local_current_artifacts(artifacts_root=root)


def test_local_current_materializer_rejects_unsafe_agency_id(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "index.json").write_text(
        json.dumps(
            {
                "agencies": {
                    "../escape": {"history": [{"date": "2026-07-10", "score": 80, "grade": "B"}]}
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ActivationHydrationError, match="unsafe agency id"):
        materialize_local_current_artifacts(artifacts_root=root)
    assert not (tmp_path / "escape").exists()


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
