"""Behavioral tests for draft-only dataset release promotion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.dataset_release_promotion import (
    EXPECTED_ASSETS,
    EXPECTED_PAYLOAD_ASSETS,
    DatasetReleasePromotionError,
    DesiredRelease,
    promote_release,
    stage_release,
)


class FakeReleaseClient:
    """In-memory GitHub release model that records every external mutation."""

    def __init__(self, release: dict[str, Any] | None = None) -> None:
        self.release = release
        self.ref: dict[str, Any] | None = None
        self.contents: dict[int, bytes] = {}
        self.events: list[str] = []
        self.next_asset_id = 100
        self.immutable_enabled = True

    def find_release(self, tag: str) -> dict[str, Any] | None:
        assert self.release is None or self.release["tag_name"] == tag
        return self.release

    def tag_ref(self, tag: str) -> dict[str, Any] | None:
        return self.ref

    def create_draft(self, desired: DesiredRelease) -> dict[str, Any]:
        self.events.append("create-draft")
        self.ref = {"object": {"type": "commit", "sha": desired.target}}
        self.release = _release(desired, draft=True)
        return self.release

    def delete_asset(self, asset_id: int) -> None:
        self.events.append(f"delete:{asset_id}")
        assert self.release is not None
        self.release["assets"] = [
            asset for asset in self.release["assets"] if asset["id"] != asset_id
        ]
        self.contents.pop(asset_id, None)

    def upload_asset(self, release: Mapping[str, Any], path: Path) -> None:
        assert release is self.release
        assert self.release is not None
        content = path.read_bytes()
        asset_id = self.next_asset_id
        self.next_asset_id += 1
        self.events.append(f"upload:{path.name}")
        self.release["assets"].append(_asset(asset_id, path.name, content))
        self.contents[asset_id] = content

    def download_asset(self, asset_id: int) -> bytes:
        self.events.append(f"download:{asset_id}")
        return self.contents[asset_id]

    def immutable_releases_enabled(self) -> bool:
        self.events.append("check-immutable-releases")
        return self.immutable_enabled

    def publish(self, release_id: int) -> dict[str, Any]:
        assert self.release is not None and self.release["id"] == release_id
        assert self.release["draft"] is True
        self.events.append("publish")
        self.release["draft"] = False
        self.release["immutable"] = True
        return self.release


def _asset(asset_id: int, name: str, content: bytes) -> dict[str, Any]:
    return {
        "id": asset_id,
        "name": name,
        "state": "uploaded",
        "size": len(content),
        "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
    }


def _release(desired: DesiredRelease, *, draft: bool) -> dict[str, Any]:
    return {
        "id": 42,
        "tag_name": desired.tag,
        "target_commitish": desired.target,
        "name": desired.title,
        "body": desired.body,
        "draft": draft,
        "prerelease": False,
        "immutable": not draft,
        "upload_url": "https://uploads.example/releases/42/assets{?name,label}",
        "assets": [],
    }


def _desired(tmp_path: Path) -> DesiredRelease:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    provenance = {
        "schema_version": 1,
        "source_mode": "scheduled-daily",
        "head_sha": "a" * 40,
        "source_run_id": 123,
        "source_run_attempt": 2,
    }
    for name in EXPECTED_PAYLOAD_ASSETS:
        content = (
            json.dumps(provenance, sort_keys=True).encode()
            if name == "PROVENANCE.json"
            else f"exact bytes for {name}\n".encode()
        )
        (bundle / name).write_bytes(content)
    checksums = "".join(
        f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}\n"
        for name in EXPECTED_PAYLOAD_ASSETS
    )
    (bundle / "SHA256SUMS").write_text(checksums)
    return DesiredRelease(
        repository="ChelseaKR/gtfs-scorecard",
        tag="dataset-2026-08",
        target="a" * 40,
        title="Dataset 2026-08",
        body="Exact notes.\n",
        bundle=bundle,
        source_mode="scheduled-daily",
        source_run_id=123,
        source_run_attempt=2,
    )


def _put_asset(
    client: FakeReleaseClient, desired: DesiredRelease, name: str, content: bytes
) -> None:
    assert client.release is not None
    asset_id = client.next_asset_id
    client.next_asset_id += 1
    client.release["assets"].append(_asset(asset_id, name, content))
    client.contents[asset_id] = content


def test_interrupted_exact_draft_is_reconciled_and_verified_before_publish(
    tmp_path: Path,
) -> None:
    desired = _desired(tmp_path)
    client = FakeReleaseClient(_release(desired, draft=True))
    client.ref = {"object": {"type": "commit", "sha": desired.target}}
    _put_asset(client, desired, "CITATION.cff", (desired.bundle / "CITATION.cff").read_bytes())
    _put_asset(client, desired, "catalog.csv", b"interrupted upload")

    assert promote_release(client, desired) == "published"

    assert client.release is not None and client.release["draft"] is False
    assert {asset["name"] for asset in client.release["assets"]} == set(EXPECTED_ASSETS)
    assert any(event.startswith("delete:") for event in client.events)
    assert "upload:catalog.csv" in client.events
    publish_index = client.events.index("publish")
    assert all(
        any(event == f"download:{asset['id']}" for event in client.events[:publish_index])
        for asset in client.release["assets"]
    )


def test_new_release_is_created_as_draft_and_published_only_after_all_uploads(
    tmp_path: Path,
) -> None:
    desired = _desired(tmp_path)
    client = FakeReleaseClient()
    client.ref = {"object": {"type": "commit", "sha": desired.target}}

    assert promote_release(client, desired) == "published"

    assert client.events[0] == "create-draft"
    publish_index = client.events.index("publish")
    assert all(client.events.index(f"upload:{name}") < publish_index for name in EXPECTED_ASSETS)
    assert client.events.index("check-immutable-releases") < publish_index


def test_stage_only_verifies_exact_bytes_without_checking_or_publishing(tmp_path: Path) -> None:
    desired = _desired(tmp_path)
    client = FakeReleaseClient()
    client.ref = {"object": {"type": "commit", "sha": desired.target}}

    assert stage_release(client, desired) == "staged"

    assert client.release is not None and client.release["draft"] is True
    downloads = [event for event in client.events if event.startswith("download:")]
    assert len(downloads) == len(EXPECTED_ASSETS)
    assert "check-immutable-releases" not in client.events
    assert "publish" not in client.events


def test_partial_public_release_fails_closed_without_mutation(tmp_path: Path) -> None:
    desired = _desired(tmp_path)
    client = FakeReleaseClient(_release(desired, draft=False))
    client.ref = {"object": {"type": "commit", "sha": desired.target}}
    _put_asset(client, desired, "CITATION.cff", (desired.bundle / "CITATION.cff").read_bytes())
    client.events.clear()

    with pytest.raises(DatasetReleasePromotionError, match="exact asset set"):
        promote_release(client, desired)

    assert client.events == []


def test_disabled_immutable_releases_keeps_verified_draft_unpublished(tmp_path: Path) -> None:
    desired = _desired(tmp_path)
    client = FakeReleaseClient()
    client.ref = {"object": {"type": "commit", "sha": desired.target}}
    client.immutable_enabled = False

    with pytest.raises(DatasetReleasePromotionError, match="keeping exact draft unpublished"):
        promote_release(client, desired)

    assert client.release is not None and client.release["draft"] is True
    assert "check-immutable-releases" in client.events
    assert "publish" not in client.events


def test_conflicting_draft_asset_fails_closed_without_deleting_it(tmp_path: Path) -> None:
    desired = _desired(tmp_path)
    client = FakeReleaseClient(_release(desired, draft=True))
    client.ref = {"object": {"type": "commit", "sha": desired.target}}
    _put_asset(client, desired, "unreviewed.txt", b"do not delete")
    client.events.clear()

    with pytest.raises(DatasetReleasePromotionError, match="unexpected asset"):
        promote_release(client, desired)

    assert client.events == []
