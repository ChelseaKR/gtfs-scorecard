"""Content-comparison publishing must never skip a real change.

The specific failure this guards is the reason ``aws s3 sync --size-only`` was
rejected: a re-scored artifact whose bytes change without its byte length
changing (a grade moving ``B`` to ``C``, a count going ``19`` to ``20``, a
fixed-width timestamp advancing) must still be published.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import s3_publish
from scorecard_pipeline.artifact_lifecycle import MUTABLE_PUBLIC_ARTIFACT_NAMES
from scorecard_pipeline.s3_publish import (
    LocalFile,
    PublishError,
    RemoteObject,
    content_type,
    is_excluded,
    needs_upload,
    normalize_etag,
    normalize_prefix,
    publish_tree,
)

BUCKET = "artifacts-test"
PREFIX = "data/artifacts"


def _md5(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


class _FakePaginator:
    """Pages the fake bucket two keys at a time so pagination is exercised."""

    def __init__(self, client: _FakeS3) -> None:
        self._client = client

    def paginate(self, *, Bucket: str, Prefix: str) -> Any:
        assert Bucket == BUCKET
        self._client.list_calls += 1
        keys = sorted(k for k in self._client.objects if k.startswith(Prefix))
        for start in range(0, max(len(keys), 1), 2):
            page_keys = keys[start : start + 2]
            yield {
                "Contents": [
                    {
                        "Key": key,
                        "Size": len(self._client.objects[key]),
                        "ETag": f'"{self._client.etag(key)}"',
                    }
                    for key in page_keys
                ]
            }


class _FakeS3:
    """An in-memory stand-in for the boto3 S3 client used by the publisher."""

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects: dict[str, bytes] = dict(objects or {})
        self.puts: list[tuple[str, bytes, dict[str, Any]]] = []
        self.deletes: list[list[str]] = []
        self.etag_overrides: dict[str, str] = {}
        self.fail_keys: set[str] = set()
        self.fail_deletes = False
        self.delete_errors: list[dict[str, str]] = []
        self.list_calls = 0
        self._lock = threading.Lock()

    def etag(self, key: str) -> str:
        return self.etag_overrides.get(key, _md5(self.objects[key]))

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        key = str(kwargs["Key"])
        body = kwargs["Body"].read()
        metadata = {k: v for k, v in kwargs.items() if k not in {"Body", "Bucket", "Key"}}
        with self._lock:
            if key in self.fail_keys:
                raise RuntimeError("AccessDenied")
            self.objects[key] = body
            self.etag_overrides.pop(key, None)
            self.puts.append((key, body, metadata))
        return {}

    def delete_objects(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["Bucket"] == BUCKET
        keys = [str(item["Key"]) for item in kwargs["Delete"]["Objects"]]
        with self._lock:
            if self.fail_deletes:
                raise RuntimeError("AccessDenied")
            self.deletes.append(keys)
            for key in keys:
                self.objects.pop(key, None)
                self.etag_overrides.pop(key, None)
        return {"Errors": list(self.delete_errors)} if self.delete_errors else {}

    def get_paginator(self, operation_name: str) -> _FakePaginator:
        assert operation_name == "list_objects_v2"
        return _FakePaginator(self)

    @property
    def put_keys(self) -> list[str]:
        return [key for key, _, _ in self.puts]


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _publish(client: _FakeS3, root: Path, **kwargs: Any) -> Any:
    return publish_tree(client, root=root, bucket=BUCKET, prefix=PREFIX, **kwargs)


def _minimal_registry(repo: Path) -> None:
    """`main()` loads the registry for every command; give it a valid one."""
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: unitrans\n"
        "    name: Unitrans\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )


def _retirement_manifest(tmp_path: Path, agency_ids: list[str]) -> Path:
    path = tmp_path / "retirements.json"
    path.write_text(json.dumps({"schema_version": 1, "agency_ids": agency_ids}))
    return path


def test_a_same_length_content_change_is_still_published(tmp_path: Path) -> None:
    """The exact case ``--size-only`` would silently drop."""
    published = '{"grade": "B", "notices": 19}'
    rescored = '{"grade": "C", "notices": 20}'
    # Only meaningful while the two payloads really are the same length.
    assert len(published) == len(rescored)
    assert published != rescored

    root = tmp_path / "artifacts"
    key = f"{PREFIX}/unitrans/latest.json"
    client = _FakeS3({key: published.encode()})
    _write(root, "unitrans/latest.json", rescored)

    result = _publish(client, root)

    assert client.put_keys == [key]
    assert client.objects[key].decode() == rescored
    assert (result.uploaded, result.skipped) == (1, 0)


def test_byte_identical_files_are_not_republished(tmp_path: Path) -> None:
    payload = '{"grade": "B"}'
    root = tmp_path / "artifacts"
    key = f"{PREFIX}/unitrans/latest.json"
    client = _FakeS3({key: payload.encode()})
    _write(root, "unitrans/latest.json", payload)

    result = _publish(client, root)

    assert client.puts == []
    assert (result.uploaded, result.skipped) == (0, 1)


def test_a_fresh_checkout_mtime_alone_never_triggers_an_upload(tmp_path: Path) -> None:
    """Every local file is newer than every object, as it is on a CI runner."""
    root = tmp_path / "artifacts"
    objects = {}
    for index in range(6):
        payload = f'{{"agency": {index}}}'
        objects[f"{PREFIX}/agency-{index}/latest.json"] = payload.encode()
        path = _write(root, f"agency-{index}/latest.json", payload)
        path.touch()  # newer than anything the bucket holds
    client = _FakeS3(objects)

    result = _publish(client, root)

    assert client.puts == []
    assert (result.uploaded, result.skipped, result.considered) == (0, 6, 6)


def test_a_new_key_is_published(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    client = _FakeS3()
    _write(root, "unitrans/2026-07-31.json", '{"snapshot_date": "2026-07-31"}')

    result = _publish(client, root)

    assert client.put_keys == [f"{PREFIX}/unitrans/2026-07-31.json"]
    assert result.uploaded == 1


def test_a_length_change_is_published(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    key = f"{PREFIX}/unitrans/latest.json"
    client = _FakeS3({key: b'{"grade": "B"}'})
    _write(root, "unitrans/latest.json", '{"grade": "B", "score": 84}')

    _publish(client, root)

    assert client.put_keys == [key]


def test_a_multipart_etag_cannot_prove_equality_so_it_republishes(tmp_path: Path) -> None:
    """Legacy `aws s3 sync` left multipart ETags; those must fail closed."""
    payload = b'{"agencies": {}}'
    root = tmp_path / "artifacts"
    key = f"{PREFIX}/index.json"
    client = _FakeS3({key: payload})
    client.etag_overrides[key] = f"{_md5(payload)}-3"
    _write(root, "index.json", payload.decode())

    first = _publish(client, root)
    assert first.uploaded == 1

    # The republish is a single PutObject, so the ETag becomes a content MD5
    # and the next run can compare it and skip.
    second = _publish(client, root)
    assert (second.uploaded, second.skipped) == (0, 1)


def test_an_unreadable_etag_fails_closed() -> None:
    local = LocalFile(key="k", path=Path("unused"), size=4)
    assert needs_upload(local, RemoteObject(size=4, etag="")) is True
    assert needs_upload(local, RemoteObject(size=4, etag="not-a-hash")) is True
    assert needs_upload(local, None) is True


def test_excluded_paths_are_never_published(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write(root, "unitrans/latest.json", '{"grade": "B"}')
    for private in ("validator-cache.json", "structure.json", "fixlog.json", "corrected.zip"):
        _write(root, f"unitrans/{private}", "private")
    client = _FakeS3()

    result = _publish(
        client,
        root,
        excludes=[
            "*/validator-cache.json",
            "*/structure.json",
            "*/fixlog.json",
            "*/corrected.zip",
        ],
    )

    assert client.put_keys == [f"{PREFIX}/unitrans/latest.json"]
    assert result.considered == 1


def test_publishing_without_a_retirement_plan_is_additive(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    retired = f"{PREFIX}/unitrans/2026-01-01.json"
    client = _FakeS3({retired: b'{"snapshot_date": "2026-01-01"}'})
    _write(root, "unitrans/latest.json", '{"grade": "B"}')

    _publish(client, root)

    assert retired in client.objects


def test_retirement_manifest_deletes_only_mutable_current_objects(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    agency_id = "retired-demo"
    dated_key = f"{PREFIX}/{agency_id}/2026-01-01.json"
    unrelated_key = f"{PREFIX}/{agency_id}/future-private.json"
    current_keys = {f"{PREFIX}/{agency_id}/{name}" for name in MUTABLE_PUBLIC_ARTIFACT_NAMES}
    objects = {
        **{key: b"stale current" for key in current_keys},
        dated_key: b'{"snapshot_date": "2026-01-01"}',
        unrelated_key: b"not part of retirement",
    }
    client = _FakeS3(objects)
    _write(root, f"{agency_id}/2026-01-01.json", '{"snapshot_date": "2026-01-01"}')
    manifest = _retirement_manifest(tmp_path, [agency_id])

    result = _publish(client, root, retirement_manifest=manifest)

    assert set(client.deletes[0]) == current_keys
    assert current_keys.isdisjoint(client.objects)
    assert dated_key in client.objects
    assert unrelated_key in client.objects
    assert result.retired == len(MUTABLE_PUBLIC_ARTIFACT_NAMES)

    # A second pass sees no current version and creates no redundant delete
    # markers in the versioned bucket.
    client.deletes.clear()
    second = _publish(client, root, retirement_manifest=manifest)
    assert client.deletes == []
    assert second.retired == 0


def test_retirement_permits_a_canonical_id_that_is_currently_withdrawn(tmp_path: Path) -> None:
    """A withdrawn-but-still-canonical id (e.g. ``beloit-transit``) must publish.

    ``_cmd_publish_artifacts`` computes ``protected_agency_ids`` as every
    canonical id minus the currently-withdrawn set (corrections.py), so an
    agency that is both canonical and withdrawn is not protected here: its
    current pointer files are deleted like any other retirement, exactly as
    ``test_retirement_manifest_deletes_only_mutable_current_objects`` proves
    for an unregistered id. ``protected_agency_ids`` still carries an
    unrelated canonical id, so this also proves the exclusion is scoped to
    the withdrawn id and does not just empty the protection set.
    ``test_retirement_rejects_current_canonical_ids`` proves the opposite
    case still holds: an unexplained canonical id with no withdrawal is
    still rejected.
    """
    root = tmp_path / "artifacts"
    agency_id = "beloit-transit"
    dated_key = f"{PREFIX}/{agency_id}/2026-01-01.json"
    current_keys = {f"{PREFIX}/{agency_id}/{name}" for name in MUTABLE_PUBLIC_ARTIFACT_NAMES}
    objects = {
        **{key: b"stale current" for key in current_keys},
        dated_key: b'{"snapshot_date": "2026-01-01"}',
    }
    client = _FakeS3(objects)
    _write(root, f"{agency_id}/2026-01-01.json", '{"snapshot_date": "2026-01-01"}')
    manifest = _retirement_manifest(tmp_path, [agency_id])

    result = _publish(
        client,
        root,
        retirement_manifest=manifest,
        # beloit-transit is canonical but withdrawn, so it is excluded from
        # protection; unitrans is canonical and not withdrawn, so it stays
        # protected (and is not in this manifest, so nothing rejects it).
        protected_agency_ids={"unitrans"},
    )

    assert set(client.deletes[0]) == current_keys
    assert current_keys.isdisjoint(client.objects)
    assert dated_key in client.objects
    assert result.retired == len(MUTABLE_PUBLIC_ARTIFACT_NAMES)


def test_retirement_rejects_a_local_current_pointer_before_deleting(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write(root, "retired-demo/latest.json", '{"grade": "F"}')
    client = _FakeS3({f"{PREFIX}/retired-demo/latest.json": b'{"grade": "F"}'})
    manifest = _retirement_manifest(tmp_path, ["retired-demo"])

    with pytest.raises(PublishError, match="still contains a current artifact"):
        _publish(client, root, retirement_manifest=manifest)

    assert client.deletes == []


def test_retirement_rejects_current_canonical_ids(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    client = _FakeS3()
    manifest = _retirement_manifest(tmp_path, ["unitrans"])

    with pytest.raises(PublishError, match="current canonical agency"):
        _publish(
            client,
            root,
            retirement_manifest=manifest,
            protected_agency_ids={"unitrans"},
        )

    assert client.deletes == []


def test_retirement_manifest_cannot_name_an_arbitrary_path(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    client = _FakeS3()
    manifest = _retirement_manifest(tmp_path, ["../unitrans"])

    with pytest.raises(PublishError, match="unsafe agency id"):
        _publish(client, root, retirement_manifest=manifest)

    assert client.deletes == []


def test_retirement_manifest_cannot_target_a_reserved_namespace(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    client = _FakeS3()
    manifest = _retirement_manifest(tmp_path, ["changes"])

    with pytest.raises(PublishError, match="reserved artifact namespace"):
        _publish(client, root, retirement_manifest=manifest)

    assert client.deletes == []


def test_local_retirement_control_manifest_is_never_uploaded(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    manifest = root / ".retired-current-artifacts.json"
    manifest.write_text(json.dumps({"schema_version": 1, "agency_ids": []}))
    (root / ".retired-current-artifacts.json.tmp").write_text("interrupted write")
    client = _FakeS3()

    result = _publish(client, root, retirement_manifest=manifest)

    assert result.considered == 0
    assert client.puts == []


def test_a_failed_retirement_fails_before_upload(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write(root, "live/latest.json", '{"grade": "B"}')
    client = _FakeS3({f"{PREFIX}/retired-demo/latest.json": b'{"grade": "F"}'})
    client.fail_deletes = True
    manifest = _retirement_manifest(tmp_path, ["retired-demo"])

    with pytest.raises(PublishError, match="could not retire current artifacts"):
        _publish(client, root, retirement_manifest=manifest)

    assert client.puts == []


def test_uploads_carry_the_cache_control_and_content_type(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write(root, "unitrans/latest.json", '{"grade": "B"}')
    _write(root, "unitrans/badge.svg", "<svg/>")
    _write(root, "unitrans/geometry.geojson", '{"type": "FeatureCollection"}')
    _write(root, "rollups/california.csv", "id,grade\n")
    _write(root, "rollups/digest.md", "# digest\n")
    _write(root, "unitrans/opaque.bin", "0")
    client = _FakeS3()

    _publish(client, root, cache_control="max-age=300")

    metadata = {key: meta for key, _, meta in client.puts}
    assert all(meta["CacheControl"] == "max-age=300" for meta in metadata.values())
    assert metadata[f"{PREFIX}/unitrans/latest.json"]["ContentType"] == "application/json"
    assert metadata[f"{PREFIX}/unitrans/badge.svg"]["ContentType"] == "image/svg+xml"
    assert metadata[f"{PREFIX}/unitrans/geometry.geojson"]["ContentType"] == "application/geo+json"
    assert metadata[f"{PREFIX}/rollups/california.csv"]["ContentType"] == "text/csv"
    assert metadata[f"{PREFIX}/rollups/digest.md"]["ContentType"] == "text/markdown"
    # An unrecognized extension leaves S3 to apply its own default.
    assert "ContentType" not in metadata[f"{PREFIX}/unitrans/opaque.bin"]


def test_no_cache_control_leaves_the_header_unset(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write(root, "unitrans/latest.json", '{"grade": "B"}')
    client = _FakeS3()

    _publish(client, root)

    assert "CacheControl" not in client.puts[0][2]


def test_a_failed_upload_fails_the_publish(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write(root, "unitrans/latest.json", '{"grade": "B"}')
    client = _FakeS3()
    client.fail_keys.add(f"{PREFIX}/unitrans/latest.json")

    with pytest.raises(PublishError, match="could not publish"):
        _publish(client, root)


def test_a_missing_publish_root_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(PublishError, match="publish root does not exist"):
        _publish(_FakeS3(), tmp_path / "absent")


def test_an_empty_tree_publishes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    client = _FakeS3()

    result = _publish(client, root)

    assert (result.uploaded, result.skipped, result.listed) == (0, 0, 0)


def test_the_destination_prefix_is_listed_once_per_publish(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    objects = {}
    for index in range(5):
        payload = f'{{"agency": {index}}}'
        objects[f"{PREFIX}/agency-{index}/latest.json"] = payload.encode()
        _write(root, f"agency-{index}/latest.json", payload)
    client = _FakeS3(objects)

    result = _publish(client, root)

    assert client.list_calls == 1
    assert result.listed == 5


def test_listing_skips_entries_without_a_key() -> None:
    class _KeylessPaginator:
        def paginate(self, **kwargs: Any) -> Any:
            yield {"Contents": [{"Key": "", "Size": 0, "ETag": '""'}]}
            yield {}

    class _KeylessClient:
        def get_paginator(self, operation_name: str) -> Any:
            return _KeylessPaginator()

        def put_object(self, **kwargs: Any) -> dict[str, Any]:  # pragma: no cover - unused
            raise AssertionError("no upload expected")

        def delete_objects(self, **kwargs: Any) -> dict[str, Any]:  # pragma: no cover - unused
            raise AssertionError("no deletion expected")

    assert s3_publish.remote_objects(_KeylessClient(), BUCKET, PREFIX) == {}


def test_etag_and_prefix_normalization() -> None:
    assert normalize_etag('"ABC123"') == "abc123"
    assert normalize_etag(None) == ""
    assert normalize_prefix("/data/artifacts/") == "data/artifacts/"
    assert normalize_prefix("/") == ""


def test_exclude_globs_cross_directory_separators() -> None:
    assert is_excluded("unitrans/fixlog.json", ["*/fixlog.json"]) is True
    assert is_excluded("a/b/fixlog.json", ["*/fixlog.json"]) is True
    assert is_excluded("unitrans/latest.json", ["*/fixlog.json"]) is False
    assert is_excluded("unitrans/latest.json", []) is False


def test_content_type_lookup_is_case_insensitive() -> None:
    assert content_type(Path("a/B.JSON")) == "application/json"
    assert content_type(Path("a/b.unknown")) is None


def test_the_cli_publishes_and_reports(
    tmp_path: Path, isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scorecard_pipeline.cli import main

    _minimal_registry(isolated_repo_root)
    root = tmp_path / "artifacts"
    _write(root, "unitrans/latest.json", '{"grade": "B"}')
    client = _FakeS3()
    monkeypatch.setattr(s3_publish, "s3_client", lambda workers: client)

    exit_code = main(
        [
            "publish-artifacts",
            "--root",
            str(root),
            "--bucket",
            BUCKET,
            "--prefix",
            PREFIX,
            "--exclude",
            "*/fixlog.json",
            "--cache-control",
            "max-age=300",
        ]
    )

    assert exit_code == 0
    assert client.put_keys == [f"{PREFIX}/unitrans/latest.json"]


def test_the_cli_fails_when_publishing_fails(
    tmp_path: Path, isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scorecard_pipeline.cli import main

    _minimal_registry(isolated_repo_root)
    client = _FakeS3()
    monkeypatch.setattr(s3_publish, "s3_client", lambda workers: client)

    with pytest.raises(SystemExit):
        main(
            [
                "publish-artifacts",
                "--root",
                str(tmp_path / "absent"),
                "--bucket",
                BUCKET,
                "--prefix",
                PREFIX,
            ]
        )


# --- the Daily scorecard `collect` handoff (2026-09-15 .. 09-17) -------------
#
# Daily scorecard runs 34975445619, 35102283767 and 35227438125 each scored
# every shard and then exited 2 in "Publish artifacts to S3":
#
#   scorecard: error: retirement manifest includes current canonical agency
#   id(s): beloit-transit, massachusetts-area-express-max
#
# `reindex` wrote a withdrawn, still-registered id into the retirement manifest
# (#432 made the withdrawal hold over the same unread bytes re-dated
# 2026-08-10), and `publish-artifacts` then refused its own manifest. #456
# fixed the protection set inside `_cmd_publish_artifacts`, but its test drives
# `publish_tree` with a hand-built set, so reverting the CLI change leaves it
# green. These drive the two commands collect actually runs, in order, through
# `main`, which is where the exit 2 came from.

_WITHDRAWN_SHA = "2f047947b9b64e479c96d384f0d68819294658c727b61ca7e1fc363d2889241c"


def _registry_with_a_withdrawal(repo: Path) -> None:
    """Two registered feeds, one of them withdrawn as ``beloit-transit`` is."""
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: unitrans\n"
        "    name: Unitrans\n"
        "    static_gtfs_url: https://example.org/unitrans.zip\n"
        "  - id: beloit-transit\n"
        "    name: Beloit Transit\n"
        "    static_gtfs_url: https://example.org/beloit.zip\n"
    )
    (repo / "corrections.yaml").write_text(
        "schema_version: 1\n"
        "corrections:\n"
        "  - agency_id: beloit-transit\n"
        "    agency_name: Beloit Transit\n"
        '    snapshot_date: "2026-07-25"\n'
        f"    feed_sha256: {_WITHDRAWN_SHA}\n"
        "    grade: F\n"
        "    score: 37.8\n"
        '    published_from: "2026-06-19"\n'
        '    published_until: "2026-09-05"\n'
        "    cause: no_schedule_tables\n"
        "    outcome: not_measured\n"
        "    evidence: >-\n"
        "      Every table holds a header row and nothing else.\n"
    )


def _empty_feed_artifact(date: str) -> str:
    """A letter over an archive with 0 stops and 0 trips (corrections.py)."""
    return json.dumps(
        {
            "agency": {"id": "beloit-transit", "name": "Beloit Transit"},
            "snapshot_date": date,
            "feed": {"sha256": _WITHDRAWN_SHA},
            "overall": {"grade": "F", "score": 37.8},
            "categories": {
                "completeness": {
                    "status": "measured",
                    "score": 0.0,
                    "details": {"stops": 0, "trips": 0},
                }
            },
        }
    )


def _publish_args(root: Path, manifest: Path) -> list[str]:
    """The flags the Daily scorecard's publish step passes, minus the bucket."""
    return [
        "publish-artifacts",
        "--root",
        str(root),
        "--bucket",
        BUCKET,
        "--prefix",
        PREFIX,
        "--retirement-manifest",
        str(manifest),
        "--exclude",
        "index.json",
        "--exclude",
        "*/fixlog.json",
    ]


def test_collect_publishes_the_manifest_reindex_wrote_for_a_withdrawn_agency(
    isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scorecard_pipeline.artifact_lifecycle import retirement_manifest_path
    from scorecard_pipeline.cli import main
    from scorecard_pipeline.config import artifacts_dir

    _registry_with_a_withdrawal(isolated_repo_root)
    root = artifacts_dir()
    # The checkout carries the withdrawn record; collect's hydrate adds what
    # S3 still serves: the same unread bytes re-dated, as the current pointer.
    _write(root, "beloit-transit/2026-07-25.json", _empty_feed_artifact("2026-07-25"))
    _write(root, "beloit-transit/2026-08-10.json", _empty_feed_artifact("2026-08-10"))
    _write(root, "beloit-transit/latest.json", _empty_feed_artifact("2026-08-10"))

    assert main(["reindex"]) == 0
    manifest = retirement_manifest_path(root)
    assert json.loads(manifest.read_text())["agency_ids"] == ["beloit-transit"]
    assert not (root / "beloit-transit" / "latest.json").exists()

    current = {f"{PREFIX}/beloit-transit/{name}" for name in MUTABLE_PUBLIC_ARTIFACT_NAMES}
    dated = f"{PREFIX}/beloit-transit/2026-08-10.json"
    client = _FakeS3({**{key: b"withdrawn F" for key in current}, dated: b"evidence"})
    monkeypatch.setattr(s3_publish, "s3_client", lambda workers: client)

    assert main(_publish_args(root, manifest)) == 0

    # The withdrawn grade's current pointers are gone from the store; the
    # dated evidence it was withdrawn over is not.
    assert not current & set(client.objects)
    assert dated in client.objects


def test_collect_still_refuses_to_retire_a_registered_agency_nothing_withdrew(
    tmp_path: Path,
    isolated_repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The exemption is the withdrawal, not every id that shows up in a manifest."""
    from scorecard_pipeline.cli import main
    from scorecard_pipeline.config import artifacts_dir

    _registry_with_a_withdrawal(isolated_repo_root)
    root = artifacts_dir()
    _write(root, "beloit-transit/2026-07-25.json", _empty_feed_artifact("2026-07-25"))
    _write(root, "unitrans/2026-09-17.json", '{"snapshot_date": "2026-09-17"}')
    manifest = _retirement_manifest(tmp_path, ["unitrans"])
    client = _FakeS3({f"{PREFIX}/unitrans/latest.json": b"current B"})
    monkeypatch.setattr(s3_publish, "s3_client", lambda workers: client)

    with pytest.raises(SystemExit) as exited:
        main(_publish_args(root, manifest))

    assert exited.value.code == 2
    assert (
        "retirement manifest includes current canonical agency id(s): unitrans"
        in capsys.readouterr().err
    )
    assert client.deletes == []
    assert f"{PREFIX}/unitrans/latest.json" in client.objects


def test_a_staged_publish_root_still_honors_the_withdrawal_reindex_recorded(
    tmp_path: Path, isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Intraday refresh and targeted score publish a stage, not the corpus.

    `refresh.yml` stages only the feeds it changed or swept and passes that
    directory as ``--root``, with the manifest reindex wrote under
    ``data/artifacts``. A withdrawn agency is rarely in the stage, so the
    withdrawal has to be read from the tree the manifest came from. Reading it
    from ``--root`` is how Intraday refresh 35299487909 still exited 2 on the
    commit that fixed the Daily scorecard.
    """
    from scorecard_pipeline.artifact_lifecycle import retirement_manifest_path
    from scorecard_pipeline.cli import main
    from scorecard_pipeline.config import artifacts_dir

    _registry_with_a_withdrawal(isolated_repo_root)
    corpus = artifacts_dir()
    _write(corpus, "beloit-transit/2026-07-25.json", _empty_feed_artifact("2026-07-25"))
    _write(corpus, "beloit-transit/latest.json", _empty_feed_artifact("2026-08-10"))
    _write(corpus, "unitrans/2026-09-18.json", '{"snapshot_date": "2026-09-18"}')
    assert main(["reindex"]) == 0
    manifest = retirement_manifest_path(corpus)
    assert json.loads(manifest.read_text())["agency_ids"] == ["beloit-transit"]

    # The refresh stage: only the feed this cycle touched.
    stage = tmp_path / "public-artifacts"
    _write(stage, "unitrans/2026-09-18.json", '{"snapshot_date": "2026-09-18"}')
    current = {f"{PREFIX}/beloit-transit/{name}" for name in MUTABLE_PUBLIC_ARTIFACT_NAMES}
    client = _FakeS3({key: b"withdrawn F" for key in current})
    monkeypatch.setattr(s3_publish, "s3_client", lambda workers: client)

    assert main(_publish_args(stage, manifest)) == 0

    assert not current & set(client.objects)
    assert client.put_keys == [f"{PREFIX}/unitrans/2026-09-18.json"]
