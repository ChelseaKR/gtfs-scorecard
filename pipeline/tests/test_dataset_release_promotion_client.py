"""HTTP, CLI, and fail-closed edge coverage for dataset release promotion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import requests

import scorecard_pipeline.dataset_release_promotion as promotion
from scorecard_pipeline.dataset_release_promotion import (
    EXPECTED_PAYLOAD_ASSETS,
    DatasetReleasePromotionError,
    DesiredRelease,
    GitHubReleaseClient,
)


def _response(
    value: Any = None, *, status: int = 200, raw: bytes | None = None
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.url = "https://api.github.test/resource"
    response._content = raw if raw is not None else json.dumps(value).encode()
    return response


class QueueClient(GitHubReleaseClient):
    """GitHub client whose HTTP boundary is a deterministic response queue."""

    def __init__(self, *responses: requests.Response) -> None:
        super().__init__("ChelseaKR/gtfs-scorecard", "test-token")
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.uploaded = b""

    def _request(
        self,
        method: str,
        url: str,
        *,
        allow_missing: bool = False,
        **kwargs: Any,
    ) -> requests.Response:
        self.calls.append((method, url, {"allow_missing": allow_missing, **kwargs}))
        data = kwargs.get("data")
        if data is not None and hasattr(data, "read"):
            self.uploaded = data.read()
        return self.responses.pop(0)


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
        value = (
            json.dumps(provenance, sort_keys=True).encode()
            if name == "PROVENANCE.json"
            else f"bytes for {name}\n".encode()
        )
        (bundle / name).write_bytes(value)
    (bundle / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}\n"
            for name in EXPECTED_PAYLOAD_ASSETS
        )
    )
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


def test_http_request_headers_missing_transport_and_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GitHubReleaseClient("owner/repo", "secret-token")
    assert client.session.headers["Authorization"] == "Bearer secret-token"
    assert client.session.headers["X-GitHub-Api-Version"] == "2026-03-10"

    responses: list[requests.Response | Exception] = [
        _response(status=404),
        requests.ConnectionError("offline"),
        _response(status=503),
    ]

    def request(method: str, url: str, **kwargs: Any) -> requests.Response:
        assert method == "GET"
        assert kwargs["timeout"] == (10, 120)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(client.session, "request", request)
    assert (
        client._request("GET", "https://example.test/missing", allow_missing=True).status_code
        == 404
    )
    with pytest.raises(DatasetReleasePromotionError, match="GitHub request failed: offline"):
        client._request("GET", "https://example.test/offline")
    with pytest.raises(DatasetReleasePromotionError, match="GitHub GET failed with HTTP 503"):
        client._request("GET", "https://example.test/error")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_response(raw=b"{"), "invalid JSON"),
        (_response(["not", "an", "object"]), "non-object"),
    ],
)
def test_object_rejects_invalid_payloads(response: requests.Response, message: str) -> None:
    with pytest.raises(DatasetReleasePromotionError, match=message):
        GitHubReleaseClient._object(response, "test object")


def test_find_release_paginates_and_rejects_duplicate_or_invalid_results() -> None:
    first_page: list[Any] = [{"tag_name": "other"} for _ in range(99)]
    expected = {"id": 7, "tag_name": "dataset-2026-08"}
    first_page.append(expected)
    client = QueueClient(_response(first_page), _response([]))

    assert client.find_release("dataset-2026-08") == expected
    assert [call[2]["params"]["page"] for call in client.calls] == [1, 2]

    duplicate = QueueClient(_response([expected, expected]))
    with pytest.raises(DatasetReleasePromotionError, match="multiple releases"):
        duplicate.find_release("dataset-2026-08")

    invalid_json = QueueClient(_response(raw=b"{"))
    with pytest.raises(DatasetReleasePromotionError, match="invalid releases JSON"):
        invalid_json.find_release("dataset-2026-08")

    non_list = QueueClient(_response({"tag_name": "dataset-2026-08"}))
    with pytest.raises(DatasetReleasePromotionError, match="non-list releases"):
        non_list.find_release("dataset-2026-08")


def test_tag_ref_resolves_annotated_tag_and_rejects_invalid_shapes() -> None:
    tag_sha = "b" * 40
    target = "a" * 40
    success = QueueClient(
        _response({"object": {"type": "tag", "sha": tag_sha}}),
        _response({"object": {"type": "commit", "sha": target}}),
    )
    assert success.tag_ref("dataset-2026-08") == {
        "object": {"type": "commit", "sha": target},
        "tag_object_sha": tag_sha,
    }

    assert QueueClient(_response(status=404)).tag_ref("missing") is None
    for client, message in (
        (QueueClient(_response({"object": {"type": "commit", "sha": target}})), "not annotated"),
        (QueueClient(_response({"object": {"type": "tag", "sha": "bad"}})), "invalid SHA"),
        (
            QueueClient(
                _response({"object": {"type": "tag", "sha": tag_sha}}),
                _response({"object": {"type": "tree", "sha": target}}),
            ),
            "does not target a commit",
        ),
    ):
        with pytest.raises(DatasetReleasePromotionError, match=message):
            client.tag_ref("dataset-2026-08")


def test_github_client_draft_asset_setting_and_publish_operations(tmp_path: Path) -> None:
    desired = _desired(tmp_path)
    created = {"id": 42, "draft": True}
    published = {"id": 42, "draft": False, "immutable": True}
    client = QueueClient(
        _response(created),
        _response({}),
        _response({}),
        _response(raw=b"downloaded bytes"),
        _response({"enabled": True}),
        _response(published),
    )

    assert client.create_draft(desired) == created
    client.delete_asset(9)
    upload = tmp_path / "catalog.csv"
    upload.write_bytes(b"csv bytes")
    client.upload_asset({"upload_url": "https://uploads.test/assets{?name,label}"}, upload)
    assert client.uploaded == b"csv bytes"
    assert client.download_asset(11) == b"downloaded bytes"
    assert client.immutable_releases_enabled() is True
    assert client.publish(42) == published

    assert [call[0] for call in client.calls] == ["POST", "DELETE", "POST", "GET", "GET", "PATCH"]
    assert client.calls[0][2]["json"] == {
        "tag_name": desired.tag,
        "target_commitish": desired.target,
        "name": desired.title,
        "body": desired.body,
        "draft": True,
        "prerelease": False,
    }
    assert client.calls[2][1] == "https://uploads.test/assets"
    assert client.calls[2][2]["headers"] == {"Content-Type": "text/csv"}
    assert client.calls[3][2]["headers"] == {"Accept": "application/octet-stream"}
    assert client.calls[5][2]["json"] == {"draft": False}

    with pytest.raises(DatasetReleasePromotionError, match="no upload URL"):
        QueueClient().upload_asset({}, upload)
    assert QueueClient(_response({"enabled": False})).immutable_releases_enabled() is False


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda desired: desired.bundle.rename(desired.bundle.with_name("gone")),
            "directory is missing",
        ),
        (lambda desired: (desired.bundle / "extra.txt").write_text("extra"), "exact asset set"),
        (lambda desired: (desired.bundle / "catalog.csv").write_bytes(b""), "empty asset"),
        (lambda desired: (desired.bundle / "SHA256SUMS").write_text("malformed\n"), "malformed"),
    ],
)
def test_local_bundle_validation_fails_closed(tmp_path: Path, mutate: Any, message: str) -> None:
    desired = _desired(tmp_path)
    mutate(desired)
    with pytest.raises(DatasetReleasePromotionError, match=message):
        promotion._local_bytes(desired)


@pytest.mark.parametrize(
    ("provenance", "message"),
    [(b"not-json", "PROVENANCE.json is invalid"), (b"{}", "does not exactly bind")],
)
def test_provenance_validation_fails_after_checksum_verification(
    tmp_path: Path, provenance: bytes, message: str
) -> None:
    desired = _desired(tmp_path)
    (desired.bundle / "PROVENANCE.json").write_bytes(provenance)
    (desired.bundle / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((desired.bundle / name).read_bytes()).hexdigest()}  {name}\n"
            for name in EXPECTED_PAYLOAD_ASSETS
        )
    )

    with pytest.raises(DatasetReleasePromotionError, match=message):
        promotion._local_bytes(desired)


def _main_args(desired: DesiredRelease, *, stage_only: bool) -> list[str]:
    args = [
        "--repository",
        desired.repository,
        "--tag",
        desired.tag,
        "--target",
        desired.target,
        "--title",
        desired.title,
        "--notes",
        str(desired.bundle.parent / "notes.md"),
        "--bundle",
        str(desired.bundle),
        "--source-mode",
        desired.source_mode,
        "--source-run-id",
        str(desired.source_run_id),
        "--source-run-attempt",
        str(desired.source_run_attempt),
    ]
    if stage_only:
        args.append("--stage-only")
    return args


@pytest.mark.parametrize(("stage_only", "result"), [(True, "staged"), (False, "published")])
def test_main_routes_stage_and_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stage_only: bool,
    result: str,
) -> None:
    desired = _desired(tmp_path)
    (tmp_path / "notes.md").write_text(desired.body)
    sentinel = QueueClient()
    captured: list[DesiredRelease] = []

    def client_factory(repository: str, token: str) -> QueueClient:
        assert (repository, token) == (desired.repository, "token")
        return sentinel

    def route(client: promotion.ReleaseClient, value: DesiredRelease) -> str:
        assert client is sentinel
        captured.append(value)
        return result

    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(promotion, "GitHubReleaseClient", client_factory)
    monkeypatch.setattr(promotion, "stage_release" if stage_only else "promote_release", route)

    assert promotion.main(_main_args(desired, stage_only=stage_only)) == 0
    assert captured == [desired]
    assert capsys.readouterr().out == f"Dataset release {desired.tag}: {result}.\n"


def test_main_requires_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    desired = _desired(tmp_path)
    (tmp_path / "notes.md").write_text(desired.body)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    with pytest.raises(DatasetReleasePromotionError, match="GH_TOKEN is required"):
        promotion.main(_main_args(desired, stage_only=True))


def test_release_and_tag_validation_error_helpers(tmp_path: Path) -> None:
    desired = _desired(tmp_path)
    with pytest.raises(DatasetReleasePromotionError, match="numeric id"):
        promotion._release_id({"id": True})
    with pytest.raises(DatasetReleasePromotionError, match="tag conflicts"):
        promotion._require_ref_value(
            {"object": {"type": "commit", "sha": "b" * 40}}, desired.target
        )
    with pytest.raises(DatasetReleasePromotionError, match="assets are not a list"):
        promotion._assets_by_name({"assets": None})
    with pytest.raises(DatasetReleasePromotionError, match="malformed asset"):
        promotion._assets_by_name({"assets": [None]})
    with pytest.raises(DatasetReleasePromotionError, match="duplicate asset"):
        promotion._assets_by_name({"assets": [{"name": "catalog.csv"}, {"name": "catalog.csv"}]})


def test_stage_requires_existing_trusted_tag(tmp_path: Path) -> None:
    desired = _desired(tmp_path)
    client = QueueClient()
    client.find_release = lambda tag: None  # type: ignore[method-assign]
    client.tag_ref = lambda tag: None  # type: ignore[method-assign]

    with pytest.raises(DatasetReleasePromotionError, match="trusted annotated release tag"):
        promotion.stage_release(client, desired)
