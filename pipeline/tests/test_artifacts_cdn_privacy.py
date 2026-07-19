"""Regression checks for the public CDN/private bucket boundary."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_viewer_request_function_is_an_allowlist() -> None:
    code = (ROOT / "infra" / "artifacts" / "public-artifacts-only.js").read_text()

    assert "var isRootArtifact = /^\\/data\\/artifacts\\/" in code
    assert "var isChangeArtifact = /^\\/data\\/artifacts\\/changes\\/" in code
    assert "var isRollupArtifact = /^\\/data\\/artifacts\\/rollups\\/" in code
    assert "var isReservedNamespace" in code
    assert "isAgencyArtifact = !isReservedNamespace" in code
    assert "corrected" not in code
    assert "validator-cache" not in code
    assert "structure.json" not in code
    assert "fixlog.json" not in code
    assert 'uri === "/data/liveness.json"' in code
    assert "statusCode: 404" in code


def test_viewer_request_function_behavior() -> None:
    function_path = ROOT / "infra" / "artifacts" / "public-artifacts-only.js"
    public = [
        "/data/artifacts/index.json",
        "/data/artifacts/changes/latest.json",
        "/data/artifacts/rollups/california.json",
        "/data/artifacts/demo/latest.json",
        "/data/artifacts/demo/2026-07-14.json",
        "/data/artifacts/demo/badge.svg",
        "/data/liveness.json",
    ]
    private = [
        "/data/artifacts/run/latest.json",
        "/data/artifacts/changes/badge.svg",
        "/data/artifacts/rollups/badge.svg",
        "/data/artifacts/demo/validator-cache.json",
        "/data/artifacts/demo/structure.json",
        "/data/artifacts/demo/fixlog.json",
        "/data/artifacts/demo/corrected.zip",
        "/cache/validator/demo.json",
        "/feeds/hash.zip",
    ]
    harness = """
const fs = require("fs");
const vm = require("vm");
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
const uris = JSON.parse(process.argv[2]);
const results = uris.map((uri) => handler({request: {uri}}));
process.stdout.write(JSON.stringify(results));
"""
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [node, "-e", harness, str(function_path), json.dumps(public + private)],
        check=True,
        capture_output=True,
        text=True,
    )
    results = json.loads(completed.stdout)

    assert [result.get("uri") for result in results[: len(public)]] == public
    assert all(result.get("statusCode") == 404 for result in results[len(public) :])


def test_origin_policy_cannot_read_private_prefixes() -> None:
    terraform = (ROOT / "infra" / "artifacts" / "main.tf").read_text()

    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/latest.json" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/????-??-??.json" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/liveness.json" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/*" not in terraform
    assert "${aws_s3_bucket.artifacts.arn}/feeds/*" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/cache/*" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/run/*" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/validator-cache.json" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/structure.json" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/fixlog.json" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/corrected.zip" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/rollups/*.state.json" in terraform
    assert 'aws_cloudfront_function" "public_artifacts_only' in terraform


def test_publishers_retire_legacy_validator_cache_objects() -> None:
    daily = (ROOT / ".github" / "workflows" / "scorecard.yml").read_text()
    refresh = (ROOT / ".github" / "workflows" / "refresh.yml").read_text()
    targeted = (ROOT / ".github" / "workflows" / "targeted-score.yml").read_text()
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text()

    for workflow in (daily,):
        assert '--exclude "*/validator-cache.json"' in workflow
        assert '--include "*/validator-cache.json"' in workflow
        assert '--exclude "*/structure.json"' in workflow
        assert '--include "*/structure.json"' in workflow
        assert '--exclude "*/fixlog.json"' in workflow
        assert '--include "*/fixlog.json"' in workflow
        assert '--exclude "*/corrected.zip"' in workflow
        assert '--include "*/corrected.zip"' in workflow
        assert "data/cache/structure" in workflow
        assert "cache/structure" in workflow
    for internal in ("validator-cache.json", "structure.json", "fixlog.json", "corrected.zip"):
        assert f'--exclude "{internal}"' in refresh
    assert "data/cache/structure/${id}.json" in refresh
    assert '--exclude "validator-cache.json"' in targeted
    assert '--exclude "structure.json"' in targeted
    assert '--exclude "fixlog.json"' in targeted
    assert '--exclude "corrected.zip"' in targeted
    assert "data/cache/structure/${id}.json" in targeted
    assert "${artifact_uri}/${id}/${internal}" in targeted
    assert "structures-${{ strategy.job-index }}" not in daily
    assert "cache/structure-staging/${GITHUB_RUN_ID}/${GITHUB_RUN_ATTEMPT}/${id}.json" in daily
    assert 'rm -f "$stage/$id/validator-cache.json"' in daily
    assert '"$stage/$id/structure.json" "$stage/$id/fixlog.json"' in daily
    assert "assemble_public_artifacts.sh" in pages
    assert 'cp -r "data/artifacts/$id"' not in pages
    assert 'include "*/fixlog.json"' not in pages
    assert 'include "*/corrected.zip"' not in pages
    assert '--include "canada-equity.json"' in pages
    assert '--include "*/conformance.json" --include "*/mark.svg"' in pages


def test_terraform_exports_no_unsafe_whole_tree_sync_command() -> None:
    outputs = (ROOT / "infra" / "artifacts" / "outputs.tf").read_text()

    assert "sync_command" not in outputs
    assert "aws s3 sync data/artifacts" not in outputs


def test_pages_role_cannot_read_the_whole_mixed_use_bucket() -> None:
    terraform = (ROOT / "infra" / "artifacts" / "github_oidc.tf").read_text()
    pages_policy = terraform.split('data "aws_iam_policy_document" "pages_read_s3"', 1)[1]

    assert 'resources = ["${aws_s3_bucket.artifacts.arn}/*"]' not in pages_policy
    assert "${aws_s3_bucket.artifacts.arn}/cache/fixlog/*" in pages_policy
    assert "${aws_s3_bucket.artifacts.arn}/cache/validator/*" not in pages_policy
    assert "${aws_s3_bucket.artifacts.arn}/cache/structure/*" not in pages_policy


def test_no_legacy_validator_cache_remains_in_public_artifacts() -> None:
    legacy = list((ROOT / "data" / "artifacts").glob("*/validator-cache.json"))

    assert legacy == []


def test_public_artifact_assembly_is_a_positive_allowlist(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "public"
    agency = source / "demo"
    changes = source / "changes"
    rollups = source / "rollups"
    agency.mkdir(parents=True)
    changes.mkdir()
    rollups.mkdir()
    (source / "index.json").write_text(json.dumps({"agencies": {"demo": {}}}))
    (source / "directory.json").write_text("{}")
    for name in (
        "latest.json",
        "2026-07-14.json",
        "badge.svg",
        "validator-cache.json",
        "structure.json",
        "fixlog.json",
        "corrected.zip",
        "future-private.json",
    ):
        public_names = {"latest.json", "2026-07-14.json", "badge.svg"}
        (agency / name).write_text("public" if name in public_names else "private")
    (changes / "latest.json").write_text("{}")
    (changes / "draft.json").write_text("private")
    (rollups / "california.json").write_text("{}")
    (rollups / "california.state.json").write_text("private")
    (rollups / "digest.md").write_text("private")

    bash = shutil.which("bash")
    assert bash is not None
    subprocess.run(  # noqa: S603 - fixed executable and test-owned paths
        [
            bash,
            str(ROOT / "pipeline" / "scripts" / "assemble_public_artifacts.sh"),
            str(source),
            str(destination),
        ],
        check=True,
    )

    relative = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert relative == {
        "changes/latest.json",
        "demo/2026-07-14.json",
        "demo/badge.svg",
        "demo/latest.json",
        "directory.json",
        "index.json",
        "rollups/california.json",
    }
