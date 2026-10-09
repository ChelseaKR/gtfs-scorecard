"""Behavioral tests for draft-only dataset release promotion."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.dataset_release_promotion import (
    EXPECTED_ASSETS,
    EXPECTED_PAYLOAD_ASSETS,
    LISTING_LAG_ATTEMPTS,
    LISTING_LAG_DELAY_SECONDS,
    DatasetReleasePromotionError,
    DesiredRelease,
    promote_release,
    stage_release,
)


class FakeReleaseClient:
    """In-memory GitHub release model that records every external mutation.

    Reads are counted separately from `events`, which holds mutations and
    verification downloads only, so "nothing was mutated" assertions keep
    their meaning. `listing_lag` is how many `find_release` calls still answer
    None although the release exists (GitHub's listing trailing a create);
    `id_read_misses` is the same for reads by id.
    """

    def __init__(self, release: dict[str, Any] | None = None) -> None:
        self.release = release
        self.ref: dict[str, Any] | None = None
        self.contents: dict[int, bytes] = {}
        self.events: list[str] = []
        self.next_asset_id = 100
        self.immutable_enabled = True
        self.listing_lag = 0
        self.id_read_misses = 0
        self.list_calls = 0
        self.id_reads: list[int] = []

    def find_release(self, tag: str) -> dict[str, Any] | None:
        assert self.release is None or self.release["tag_name"] == tag
        self.list_calls += 1
        if self.release is not None and self.listing_lag > 0:
            self.listing_lag -= 1
            return None
        return self.release

    def get_release(self, release_id: int) -> dict[str, Any] | None:
        self.id_reads.append(release_id)
        if self.id_read_misses > 0:
            self.id_read_misses -= 1
            return None
        if self.release is None or self.release["id"] != release_id:
            return None
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


def _uploads(client: FakeReleaseClient) -> list[str]:
    return [event for event in client.events if event.startswith("upload:")]


def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    return sleeps


def test_a_draft_the_listing_has_not_caught_up_with_is_read_by_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runs 37547342002 and 37559300763 created the draft, listed releases about
    two seconds later, got nothing, and raised. The create response carries the
    id, so reconciliation reads by id; only the final listing-based check waits,
    and it waits inside its existing bound."""
    desired = _desired(tmp_path)
    client = FakeReleaseClient()
    client.ref = {"object": {"type": "commit", "sha": desired.target}}
    client.listing_lag = 3
    sleeps = _no_sleep(monkeypatch)

    assert stage_release(client, desired) == "staged"

    assert client.events.count("create-draft") == 1
    assert client.id_reads == [42]
    assert _uploads(client) == [f"upload:{name}" for name in EXPECTED_ASSETS]
    assert sleeps == [2, 4, 6]
    assert client.release is not None and client.release["draft"] is True


def test_an_id_read_miss_falls_back_to_bounded_listing_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desired = _desired(tmp_path)
    client = FakeReleaseClient()
    client.ref = {"object": {"type": "commit", "sha": desired.target}}
    client.id_read_misses = 1
    client.listing_lag = 2
    sleeps = _no_sleep(monkeypatch)

    assert stage_release(client, desired) == "staged"

    assert client.id_reads == [42]
    assert sleeps == [LISTING_LAG_DELAY_SECONDS, LISTING_LAG_DELAY_SECONDS]
    assert _uploads(client) == [f"upload:{name}" for name in EXPECTED_ASSETS]


def test_a_draft_truly_absent_after_the_bound_raises_without_uploading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desired = _desired(tmp_path)
    client = FakeReleaseClient()
    client.ref = {"object": {"type": "commit", "sha": desired.target}}
    client.id_read_misses = 10**6
    client.listing_lag = 10**6
    sleeps = _no_sleep(monkeypatch)

    with pytest.raises(DatasetReleasePromotionError, match="disappeared during reconciliation"):
        stage_release(client, desired)

    # One listing read before the create, then exactly the bounded fallback.
    assert client.list_calls == 1 + LISTING_LAG_ATTEMPTS
    assert sleeps == [LISTING_LAG_DELAY_SECONDS] * (LISTING_LAG_ATTEMPTS - 1)
    assert _uploads(client) == []


def test_a_release_never_listed_fails_after_the_verification_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desired = _desired(tmp_path)
    client = FakeReleaseClient()
    client.ref = {"object": {"type": "commit", "sha": desired.target}}
    client.listing_lag = 10**6
    sleeps = _no_sleep(monkeypatch)

    with pytest.raises(DatasetReleasePromotionError, match="draft state: release is not listed"):
        stage_release(client, desired)

    assert sleeps == [attempt * 2 for attempt in range(1, 10)]
    assert "publish" not in client.events


def test_an_empty_draft_left_by_a_failed_run_is_filled_not_refused(tmp_path: Path) -> None:
    """Run 37559300763 left dataset-2026-10 as a draft with zero assets beside
    its signed tag. The retry must fill that draft, not create a second one and
    not treat the empty one as foreign."""
    desired = _desired(tmp_path)
    client = FakeReleaseClient(_release(desired, draft=True))
    client.ref = {"object": {"type": "commit", "sha": desired.target}}

    assert stage_release(client, desired) == "staged"

    assert "create-draft" not in client.events
    assert not any(event.startswith("delete:") for event in client.events)
    assert _uploads(client) == [f"upload:{name}" for name in EXPECTED_ASSETS]
    assert client.release is not None
    assert {asset["name"] for asset in client.release["assets"]} == set(EXPECTED_ASSETS)
    assert client.release["draft"] is True


def test_a_draft_with_different_notes_is_refused_and_names_the_field(tmp_path: Path) -> None:
    desired = _desired(tmp_path)
    release = _release(desired, draft=True)
    release["body"] = "Other notes.\n"
    client = FakeReleaseClient(release)
    client.ref = {"object": {"type": "commit", "sha": desired.target}}

    with pytest.raises(DatasetReleasePromotionError, match="metadata conflicts on body"):
        stage_release(client, desired)

    assert client.events == []
