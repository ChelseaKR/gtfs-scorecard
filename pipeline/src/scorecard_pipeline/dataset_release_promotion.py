"""Stage, verify, and publish a dataset release without a public partial state."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import requests

EXPECTED_PAYLOAD_ASSETS = (
    "CITATION.cff",
    "DATA-DICTIONARY.md",
    "PROVENANCE.json",
    "agencies.parquet",
    "catalog.csv",
    "catalog.json",
    "dataset.csv",
    "dataset.json",
    "ntd.json",
)
EXPECTED_ASSETS = (*EXPECTED_PAYLOAD_ASSETS, "SHA256SUMS")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class DatasetReleasePromotionError(RuntimeError):
    """The release cannot be promoted without weakening its exact-byte contract."""


@dataclass(frozen=True)
class DesiredRelease:
    """The immutable metadata and local bytes a release must carry."""

    repository: str
    tag: str
    target: str
    title: str
    body: str
    bundle: Path
    source_mode: str
    source_run_id: int
    source_run_attempt: int


class ReleaseClient(Protocol):
    """GitHub operations used by the fail-closed promotion state machine."""

    def find_release(self, tag: str) -> dict[str, Any] | None: ...

    def tag_ref(self, tag: str) -> dict[str, Any] | None: ...

    def create_draft(self, desired: DesiredRelease) -> dict[str, Any]: ...

    def delete_asset(self, asset_id: int) -> None: ...

    def upload_asset(self, release: Mapping[str, Any], path: Path) -> None: ...

    def download_asset(self, asset_id: int) -> bytes: ...

    def immutable_releases_enabled(self) -> bool: ...

    def publish(self, release_id: int) -> dict[str, Any]: ...


class GitHubReleaseClient:
    """Small, bounded GitHub REST client used by the Actions workflow."""

    def __init__(self, repository: str, token: str) -> None:
        self.repository = repository
        self.api = f"https://api.github.com/repos/{repository}"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "gtfs-scorecard-dataset-release",
            }
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        allow_missing: bool = False,
        **kwargs: Any,
    ) -> requests.Response:
        try:
            response = self.session.request(method, url, timeout=(10, 120), **kwargs)
        except requests.RequestException as exc:
            raise DatasetReleasePromotionError(f"GitHub request failed: {exc}") from exc
        if allow_missing and response.status_code == 404:
            return response
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise DatasetReleasePromotionError(
                f"GitHub {method} failed with HTTP {response.status_code}"
            ) from exc
        return response

    @staticmethod
    def _object(response: requests.Response, label: str) -> dict[str, Any]:
        try:
            value = response.json()
        except requests.JSONDecodeError as exc:
            raise DatasetReleasePromotionError(f"GitHub returned invalid JSON for {label}") from exc
        if not isinstance(value, dict):
            raise DatasetReleasePromotionError(f"GitHub returned a non-object for {label}")
        return cast(dict[str, Any], value)

    def find_release(self, tag: str) -> dict[str, Any] | None:
        matches: list[dict[str, Any]] = []
        page = 1
        while True:
            response = self._request(
                "GET", f"{self.api}/releases", params={"per_page": 100, "page": page}
            )
            try:
                releases = response.json()
            except requests.JSONDecodeError as exc:
                raise DatasetReleasePromotionError("GitHub returned invalid releases JSON") from exc
            if not isinstance(releases, list):
                raise DatasetReleasePromotionError("GitHub returned a non-list releases payload")
            for raw in releases:
                if isinstance(raw, dict) and raw.get("tag_name") == tag:
                    matches.append(cast(dict[str, Any], raw))
            if len(releases) < 100:
                break
            page += 1
        if len(matches) > 1:
            raise DatasetReleasePromotionError(f"multiple releases use tag {tag}")
        return matches[0] if matches else None

    def tag_ref(self, tag: str) -> dict[str, Any] | None:
        response = self._request("GET", f"{self.api}/git/ref/tags/{tag}", allow_missing=True)
        if response.status_code == 404:
            return None
        ref = self._object(response, "tag ref")
        ref_object = ref.get("object")
        if not isinstance(ref_object, dict) or ref_object.get("type") != "tag":
            raise DatasetReleasePromotionError("release tag is not annotated")
        tag_sha = ref_object.get("sha")
        if not isinstance(tag_sha, str) or not _GIT_SHA.fullmatch(tag_sha):
            raise DatasetReleasePromotionError("release tag object has an invalid SHA")
        tag_response = self._request("GET", f"{self.api}/git/tags/{tag_sha}")
        tag_object = self._object(tag_response, "annotated tag object").get("object")
        if not isinstance(tag_object, dict) or tag_object.get("type") != "commit":
            raise DatasetReleasePromotionError("annotated release tag does not target a commit")
        return {"object": tag_object, "tag_object_sha": tag_sha}

    def create_draft(self, desired: DesiredRelease) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"{self.api}/releases",
            json={
                "tag_name": desired.tag,
                "target_commitish": desired.target,
                "name": desired.title,
                "body": desired.body,
                "draft": True,
                "prerelease": False,
            },
        )
        return self._object(response, "created draft")

    def delete_asset(self, asset_id: int) -> None:
        self._request("DELETE", f"{self.api}/releases/assets/{asset_id}")

    def upload_asset(self, release: Mapping[str, Any], path: Path) -> None:
        upload_url = release.get("upload_url")
        if not isinstance(upload_url, str):
            raise DatasetReleasePromotionError("draft release has no upload URL")
        upload_url = upload_url.split("{", 1)[0]
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as handle:
            self._request(
                "POST",
                upload_url,
                params={"name": path.name},
                headers={"Content-Type": content_type},
                data=handle,
            )

    def download_asset(self, asset_id: int) -> bytes:
        response = self._request(
            "GET",
            f"{self.api}/releases/assets/{asset_id}",
            headers={"Accept": "application/octet-stream"},
        )
        return response.content

    def immutable_releases_enabled(self) -> bool:
        response = self._request("GET", f"{self.api}/immutable-releases")
        return self._object(response, "immutable release setting").get("enabled") is True

    def publish(self, release_id: int) -> dict[str, Any]:
        response = self._request(
            "PATCH", f"{self.api}/releases/{release_id}", json={"draft": False}
        )
        return self._object(response, "published release")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _local_bytes(desired: DesiredRelease) -> dict[str, bytes]:
    if not desired.bundle.is_dir():
        raise DatasetReleasePromotionError("release bundle directory is missing")
    actual_names = sorted(path.name for path in desired.bundle.iterdir() if path.is_file())
    if actual_names != sorted(EXPECTED_ASSETS):
        raise DatasetReleasePromotionError("release bundle does not contain the exact asset set")
    payload = {name: (desired.bundle / name).read_bytes() for name in EXPECTED_ASSETS}
    if any(not value for value in payload.values()):
        raise DatasetReleasePromotionError("release bundle contains an empty asset")

    checksum_lines = payload["SHA256SUMS"].decode("utf-8").splitlines()
    expected_checksums = {name: _sha256_bytes(payload[name]) for name in EXPECTED_PAYLOAD_ASSETS}
    parsed: dict[str, str] = {}
    for line in checksum_lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        if match is None or match.group(2) in parsed:
            raise DatasetReleasePromotionError("SHA256SUMS is malformed")
        parsed[match.group(2)] = match.group(1)
    if parsed != expected_checksums:
        raise DatasetReleasePromotionError("SHA256SUMS does not bind the exact payload bytes")

    try:
        provenance = json.loads(payload["PROVENANCE.json"])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatasetReleasePromotionError("PROVENANCE.json is invalid") from exc
    expected_provenance = {
        "schema_version": 1,
        "source_mode": desired.source_mode,
        "head_sha": desired.target,
        "source_run_id": desired.source_run_id,
        "source_run_attempt": desired.source_run_attempt,
    }
    if provenance != expected_provenance:
        raise DatasetReleasePromotionError("PROVENANCE.json does not exactly bind the source")
    return payload


def _release_id(release: Mapping[str, Any]) -> int:
    release_id = release.get("id")
    if not isinstance(release_id, int) or isinstance(release_id, bool):
        raise DatasetReleasePromotionError("release has no numeric id")
    return release_id


def _require_metadata(release: Mapping[str, Any], desired: DesiredRelease, *, draft: bool) -> None:
    expected = {
        "tag_name": desired.tag,
        "target_commitish": desired.target,
        "name": desired.title,
        "body": desired.body,
        "draft": draft,
        "prerelease": False,
    }
    if not draft:
        expected["immutable"] = True
    if any(release.get(key) != value for key, value in expected.items()):
        state = "draft" if draft else "public"
        raise DatasetReleasePromotionError(f"existing {state} release metadata conflicts")


def _require_tag_target(client: ReleaseClient, desired: DesiredRelease) -> None:
    ref = client.tag_ref(desired.tag)
    if ref is None:
        raise DatasetReleasePromotionError("release tag was not created")
    obj = ref.get("object")
    if not isinstance(obj, dict) or obj.get("type") != "commit" or obj.get("sha") != desired.target:
        raise DatasetReleasePromotionError("release tag does not target the exact source commit")


def _require_ref_value(ref: Mapping[str, Any], target: str) -> None:
    obj = ref.get("object")
    if not isinstance(obj, dict) or obj.get("type") != "commit" or obj.get("sha") != target:
        raise DatasetReleasePromotionError("existing release tag conflicts with source")


def _assets_by_name(release: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_assets = release.get("assets")
    if not isinstance(raw_assets, list):
        raise DatasetReleasePromotionError("release assets are not a list")
    result: dict[str, dict[str, Any]] = {}
    for raw in raw_assets:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise DatasetReleasePromotionError("release contains a malformed asset")
        name = cast(str, raw["name"])
        if name in result:
            raise DatasetReleasePromotionError(f"release contains duplicate asset {name}")
        result[name] = cast(dict[str, Any], raw)
    unexpected = sorted(set(result) - set(EXPECTED_ASSETS))
    if unexpected:
        raise DatasetReleasePromotionError(f"release contains unexpected asset {unexpected[0]}")
    return result


def _asset_matches(asset: Mapping[str, Any], content: bytes) -> bool:
    return (
        asset.get("state") == "uploaded"
        and asset.get("size") == len(content)
        and asset.get("digest") == f"sha256:{_sha256_bytes(content)}"
        and isinstance(asset.get("id"), int)
        and not isinstance(asset.get("id"), bool)
    )


def _verify_assets(
    client: ReleaseClient, release: Mapping[str, Any], local: Mapping[str, bytes]
) -> None:
    assets = _assets_by_name(release)
    if set(assets) != set(EXPECTED_ASSETS):
        raise DatasetReleasePromotionError("release does not contain the exact asset set")
    for name in EXPECTED_ASSETS:
        asset = assets[name]
        expected = local[name]
        if not _asset_matches(asset, expected):
            raise DatasetReleasePromotionError(
                f"release metadata does not bind exact bytes for {name}"
            )
        downloaded = client.download_asset(cast(int, asset["id"]))
        if downloaded != expected:
            raise DatasetReleasePromotionError(f"downloaded release bytes differ for {name}")


def _refresh_until_exact(
    client: ReleaseClient,
    desired: DesiredRelease,
    local: Mapping[str, bytes],
    *,
    draft: bool,
    attempts: int = 10,
) -> dict[str, Any]:
    last_error: DatasetReleasePromotionError | None = None
    for attempt in range(1, attempts + 1):
        release = client.find_release(desired.tag)
        if release is None:
            raise DatasetReleasePromotionError("release disappeared during promotion")
        try:
            _require_metadata(release, desired, draft=draft)
            _require_tag_target(client, desired)
            _verify_assets(client, release, local)
            return release
        except DatasetReleasePromotionError as exc:
            last_error = exc
        if attempt < attempts:
            time.sleep(attempt * 2)
    raise DatasetReleasePromotionError(
        f"release did not reach an exact {'draft' if draft else 'public'} state: {last_error}"
    )


def _reconcile_draft(
    client: ReleaseClient,
    desired: DesiredRelease,
    local: Mapping[str, bytes],
    release: dict[str, Any],
) -> None:
    """Replace only known mismatched draft assets, then fill exact missing assets."""
    _require_metadata(release, desired, draft=True)
    _require_tag_target(client, desired)
    # At most one deletion per expected filename is needed. Bound the loop so
    # stale API reads cannot turn a safe retry into an unbounded workflow run.
    for _attempt in range(len(EXPECTED_ASSETS) + 1):
        current = client.find_release(desired.tag)
        if current is None:
            raise DatasetReleasePromotionError("draft disappeared during reconciliation")
        release = current
        _require_metadata(current, desired, draft=True)
        assets = _assets_by_name(current)
        mismatched = next(
            (name for name, asset in assets.items() if not _asset_matches(asset, local[name])),
            None,
        )
        if mismatched is None:
            break
        asset_id = assets[mismatched].get("id")
        if not isinstance(asset_id, int) or isinstance(asset_id, bool):
            raise DatasetReleasePromotionError(f"draft asset {mismatched} has no numeric id")
        client.delete_asset(asset_id)
    else:
        raise DatasetReleasePromotionError("draft assets did not reconcile after bounded retries")

    for name in EXPECTED_ASSETS:
        if name not in assets:
            client.upload_asset(release, desired.bundle / name)


def stage_release(client: ReleaseClient, desired: DesiredRelease) -> str:
    """Create or reconcile an exact draft without making it public."""
    local = _local_bytes(desired)
    release = client.find_release(desired.tag)
    if release is not None and release.get("draft") is False:
        _require_metadata(release, desired, draft=False)
        _require_tag_target(client, desired)
        _verify_assets(client, release, local)
        return "already-published"

    if release is None:
        existing_ref = client.tag_ref(desired.tag)
        if existing_ref is None:
            raise DatasetReleasePromotionError("trusted annotated release tag does not exist")
        _require_ref_value(existing_ref, desired.target)
        release = client.create_draft(desired)

    _reconcile_draft(client, desired, local, release)
    _refresh_until_exact(client, desired, local, draft=True)
    return "staged"


def promote_release(client: ReleaseClient, desired: DesiredRelease) -> str:
    """Verify the draft, require immutable hosting, publish once, and verify again."""
    stage_result = stage_release(client, desired)
    if stage_result == "already-published":
        return stage_result

    local = _local_bytes(desired)
    verified_draft = _refresh_until_exact(client, desired, local, draft=True)
    if not client.immutable_releases_enabled():
        raise DatasetReleasePromotionError(
            "repository-level immutable releases are not enabled; keeping exact draft unpublished"
        )
    published = client.publish(_release_id(verified_draft))
    _require_metadata(published, desired, draft=False)
    _refresh_until_exact(client, desired, local, draft=False)
    return "published"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--notes", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--source-mode", choices=("scheduled-daily", "manual-latest"), required=True
    )
    parser.add_argument("--source-run-id", type=int, required=True)
    parser.add_argument("--source-run-attempt", type=int, required=True)
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="create/reconcile and verify the draft, but require owner-local promotion",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise DatasetReleasePromotionError("GH_TOKEN is required")
    desired = DesiredRelease(
        repository=args.repository,
        tag=args.tag,
        target=args.target,
        title=args.title,
        body=args.notes.read_text(encoding="utf-8"),
        bundle=args.bundle,
        source_mode=args.source_mode,
        source_run_id=args.source_run_id,
        source_run_attempt=args.source_run_attempt,
    )
    client = GitHubReleaseClient(args.repository, token)
    result = stage_release(client, desired) if args.stage_only else promote_release(client, desired)
    print(f"Dataset release {args.tag}: {result}.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
