"""Tests for the content-addressed raw feed archive (FIX-02)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import scorecard_pipeline.archive as archive

BODY = b"PK\x03\x04fake-zip-bytes"
SHA = hashlib.sha256(BODY).hexdigest()


def _point_archive_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive, "repo_root", lambda: tmp_path)


def _write_source_zip(tmp_path: Path) -> Path:
    src = tmp_path / "source.zip"
    src.write_bytes(BODY)
    return src


def test_local_path_is_sharded_by_hash_prefix(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)
    path = archive.local_path(SHA)
    assert path == tmp_path / "data" / "raw-archive" / SHA[:2] / f"{SHA}.zip"


def test_store_then_fetch_round_trips_locally(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)
    dest = archive.store(SHA, src)
    assert dest.exists()
    assert archive.fetch(SHA) == BODY


def test_fetch_raises_archive_miss_when_absent(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)
    monkeypatch.delenv("RAW_ARCHIVE_BUCKET", raising=False)
    monkeypatch.delenv("ARTIFACTS_BUCKET", raising=False)
    with pytest.raises(archive.ArchiveMiss):
        archive.fetch("b" * 64)


@pytest.mark.parametrize(
    "bad_hash",
    ["../escape", "A" * 64, "a" * 63, "a" * 65, "g" * 64],
)
def test_archive_rejects_invalid_hash_before_path_or_s3_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_hash: str
) -> None:
    _point_archive_at(tmp_path, monkeypatch)
    monkeypatch.setattr(
        archive, "_s3_client", lambda: (_ for _ in ()).throw(AssertionError("S3 used"))
    )

    with pytest.raises(archive.ArchiveIntegrityError, match="64 lowercase hexadecimal"):
        archive.local_path(bad_hash)
    with pytest.raises(archive.ArchiveIntegrityError, match="64 lowercase hexadecimal"):
        archive.fetch(bad_hash)


def test_archive_rejects_a_non_string_hash_cleanly() -> None:
    with pytest.raises(archive.ArchiveIntegrityError, match="64 lowercase hexadecimal"):
        archive.fetch(None)  # type: ignore[arg-type]


def test_store_rejects_source_whose_digest_does_not_match_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)

    with pytest.raises(archive.ArchiveIntegrityError, match="expected"):
        archive.store("a" * 64, src)
    assert not (tmp_path / "data" / "raw-archive").exists()


def test_store_repairs_a_corrupt_same_key_local_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)
    dest = archive.local_path(SHA)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"corrupt")

    assert archive.store(SHA, src) == dest
    assert dest.read_bytes() == BODY


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3:
    """An in-memory stand-in for the boto3 S3 client used by the archive."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], bytes] = {}
        self.get_calls = 0
        self.put_calls = 0
        self.head_calls = 0

    def head_object(self, Bucket: str, Key: str):  # type: ignore[no-untyped-def]
        self.head_calls += 1
        if (Bucket, Key) not in self.store:
            raise RuntimeError("NoSuchKey")

    def get_object(self, Bucket: str, Key: str):  # type: ignore[no-untyped-def]
        self.get_calls += 1
        try:
            return {"Body": _FakeBody(self.store[(Bucket, Key)])}
        except KeyError as exc:
            raise RuntimeError("NoSuchKey") from exc

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_: object):  # type: ignore[no-untyped-def]
        self.put_calls += 1
        self.store[(Bucket, Key)] = Body


def _use_s3(monkeypatch: pytest.MonkeyPatch, client: _FakeS3, bucket: str = "raw-bkt") -> None:
    monkeypatch.setenv("RAW_ARCHIVE_BUCKET", bucket)
    monkeypatch.setattr(archive, "_s3_client", lambda: client)


def test_store_uploads_to_s3_when_bucket_configured(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)
    s3 = _FakeS3()
    _use_s3(monkeypatch, s3)
    archive.store(SHA, src)
    assert ("raw-bkt", archive._s3_key(SHA)) in s3.store
    assert s3.put_calls == 1


def test_store_skips_upload_when_hash_already_in_s3(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Most calls are the same feed as yesterday: the second store() for an
    # unchanged hash must not re-upload.
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)
    s3 = _FakeS3()
    _use_s3(monkeypatch, s3)
    archive.store(SHA, src)
    assert s3.put_calls == 1
    archive.store(SHA, src)
    assert s3.put_calls == 1  # unchanged


def test_fetch_falls_back_to_s3_and_writes_through(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)
    s3 = _FakeS3()
    _use_s3(monkeypatch, s3)
    archive.store(SHA, src)
    archive.local_path(SHA).unlink()  # simulate a cold checkout

    got = archive.fetch(SHA)
    assert got == BODY
    assert s3.get_calls == 1
    assert archive.local_path(SHA).exists()  # written through


def test_fetch_rejects_a_corrupt_local_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_archive_at(tmp_path, monkeypatch)
    monkeypatch.delenv("RAW_ARCHIVE_BUCKET", raising=False)
    monkeypatch.delenv("ARTIFACTS_BUCKET", raising=False)
    dest = archive.local_path(SHA)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"corrupt")

    with pytest.raises(archive.ArchiveIntegrityError, match="integrity failure"):
        archive.fetch(SHA)


def test_fetch_recovers_a_corrupt_local_copy_from_valid_s3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_archive_at(tmp_path, monkeypatch)
    dest = archive.local_path(SHA)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"corrupt")
    s3 = _FakeS3()
    _use_s3(monkeypatch, s3)
    s3.store[("raw-bkt", archive._s3_key(SHA))] = BODY

    assert archive.fetch(SHA) == BODY
    assert dest.read_bytes() == BODY
    assert s3.get_calls == 1


def test_fetch_rejects_corrupt_s3_bytes_without_writing_them_locally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_archive_at(tmp_path, monkeypatch)
    s3 = _FakeS3()
    _use_s3(monkeypatch, s3)
    s3.store[("raw-bkt", archive._s3_key(SHA))] = b"corrupt"

    with pytest.raises(archive.ArchiveIntegrityError, match="s3://raw-bkt"):
        archive.fetch(SHA)
    assert not archive.local_path(SHA).exists()


def test_local_hit_skips_s3(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)
    s3 = _FakeS3()
    _use_s3(monkeypatch, s3)
    archive.store(SHA, src)
    s3.get_calls = 0
    assert archive.fetch(SHA) == BODY
    assert s3.get_calls == 0


def test_s3_write_errors_never_fail_a_store(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)

    class _Broken(_FakeS3):
        def head_object(self, Bucket, Key):  # type: ignore[no-untyped-def]
            raise RuntimeError("S3 down")

        def put_object(self, Bucket, Key, Body, **_):  # type: ignore[no-untyped-def]
            raise RuntimeError("S3 down")

    _use_s3(monkeypatch, _Broken())
    dest = archive.store(SHA, src)
    assert dest.exists()  # local copy still landed


def test_fetch_raises_when_s3_read_fails(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)

    class _Broken(_FakeS3):
        def get_object(self, Bucket, Key):  # type: ignore[no-untyped-def]
            raise RuntimeError("S3 down")

    _use_s3(monkeypatch, _Broken())
    with pytest.raises(archive.ArchiveMiss):
        archive.fetch("c" * 64)


def test_no_bucket_keeps_local_only_behaviour(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)
    monkeypatch.delenv("RAW_ARCHIVE_BUCKET", raising=False)
    monkeypatch.delenv("ARTIFACTS_BUCKET", raising=False)
    monkeypatch.setattr(
        archive, "_s3_client", lambda: (_ for _ in ()).throw(AssertionError("S3 used"))
    )
    archive.store(SHA, src)
    assert archive.fetch(SHA) == BODY


def test_artifacts_bucket_env_var_is_a_fallback(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _point_archive_at(tmp_path, monkeypatch)
    src = _write_source_zip(tmp_path)
    monkeypatch.delenv("RAW_ARCHIVE_BUCKET", raising=False)
    monkeypatch.setenv("ARTIFACTS_BUCKET", "shared-bkt")
    s3 = _FakeS3()
    monkeypatch.setattr(archive, "_s3_client", lambda: s3)
    archive.store(SHA, src)
    assert ("shared-bkt", archive._s3_key(SHA)) in s3.store
