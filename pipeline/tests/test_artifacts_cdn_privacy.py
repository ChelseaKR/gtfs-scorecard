"""Regression checks for the public CDN/private bucket boundary."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from scorecard_pipeline.artifact_lifecycle import MUTABLE_PUBLIC_ARTIFACT_NAMES

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


def test_retirement_names_match_the_pages_and_origin_allowlists() -> None:
    assembly = (ROOT / "pipeline" / "scripts" / "assemble_public_artifacts.sh").read_text()
    matched = re.search(
        r"^\s+(latest\.json\|badge\.json\|badge\.svg\|conformance\.json\|mark\.svg"
        r"\|geometry\.geojson)\)$",
        assembly,
        flags=re.MULTILINE,
    )
    assert matched is not None
    assert set(matched.group(1).split("|")) == set(MUTABLE_PUBLIC_ARTIFACT_NAMES)

    origin_policy = (ROOT / "infra" / "artifacts" / "main.tf").read_text()
    for name in MUTABLE_PUBLIC_ARTIFACT_NAMES:
        assert f"/data/artifacts/*/{name}" in origin_policy
    assert not any(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", name) for name in MUTABLE_PUBLIC_ARTIFACT_NAMES
    )


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
    public.extend(
        f"/data/artifacts/demo/{name}"
        for name in MUTABLE_PUBLIC_ARTIFACT_NAMES
        if f"/data/artifacts/demo/{name}" not in public
    )
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
    for workflow in (daily, refresh, targeted):
        assert "--retirement-manifest data/artifacts/.retired-current-artifacts.json" in workflow


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
    retired = source / "retired-demo"
    changes = source / "changes"
    rollups = source / "rollups"
    agency.mkdir(parents=True)
    retired.mkdir()
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
    for name in (*MUTABLE_PUBLIC_ARTIFACT_NAMES, "2026-07-13.json"):
        (retired / name).write_text("retired history")

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
    assert (retired / "2026-07-13.json").exists()
    assert not (destination / "retired-demo").exists()


def _assemble(source: Path, destination: Path) -> set[str]:
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
    return {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }


def _dated_sample(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    (source / "demo").mkdir(parents=True)
    (source / "solo").mkdir()
    (source / "index.json").write_text(
        json.dumps({"agencies": {"demo": {}, "solo": {}, "gap": {}}})
    )
    for name in (
        "2026-06-01.json",  # old: dropped
        "2026-09-20.json",  # inside 90 days of the newest: kept
        "2026-11-10.json",  # newest
        "latest.json",
        "geometry.geojson",
    ):
        (source / "demo" / name).write_text("{}")
    (source / "gap").mkdir()
    for name in ("2026-06-01.json", "2026-08-10.json", "2026-11-10.json", "latest.json"):
        (source / "gap" / name).write_text("{}")  # 08-10 is the previous one, 92 days old
    for name in ("2026-01-01.json", "latest.json"):  # lone old file is also the newest
        (source / "solo" / name).write_text("{}")
    return source, tmp_path / "site"


def test_dated_snapshots_keep_ninety_days_and_the_previous_one(tmp_path: Path) -> None:
    source, destination = _dated_sample(tmp_path)
    published = _assemble(source, destination)

    assert "demo/2026-06-01.json" not in published
    assert "gap/2026-06-01.json" not in published
    assert {
        "demo/2026-09-20.json",
        "gap/2026-08-10.json",
        "gap/2026-11-10.json",
        "demo/2026-11-10.json",
        "demo/latest.json",
        "demo/geometry.geojson",
        "solo/2026-01-01.json",
        "solo/latest.json",
    } <= published
    assert (source / "demo" / "2026-06-01.json").exists(), "only the published copy shrinks"


def test_dated_snapshot_trim_negative_control(tmp_path: Path) -> None:
    """With the trim removed the old file ships, so the test above can fail."""
    script = (ROOT / "pipeline" / "scripts" / "assemble_public_artifacts.sh").read_text()
    assert "timedelta(days=90)" in script
    broken = tmp_path / "assemble.sh"
    broken.write_text(script.replace("timedelta(days=90)", "timedelta(days=9000)"))
    # The script locates its sibling python via BASH_SOURCE, so keep it in place.
    real = ROOT / "pipeline" / "scripts" / "assemble_public_artifacts.sh"
    backup = real.read_text()
    source, destination = _dated_sample(tmp_path)
    try:
        real.write_text(broken.read_text())
        published = _assemble(source, destination)
    finally:
        real.write_text(backup)
    assert "demo/2026-06-01.json" in published


def _is_compact(text: str) -> bool:
    """Exactly what ``json.dumps`` with ``,`` and ``:`` separators gives for its own object."""
    return text == json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=text.isascii())


def _history_point(date: str) -> dict[str, Any]:
    return {
        "categories": {"freshness": 100.0},
        "date": date,
        "days_until_expiry": 40,
        "feed_sha256": "ab" * 32,
        "grade": "B",
        "grade_qualifier": None,
        "reader_archive_profile": "raw-v1",
        "rubric_version": "1.5",
        "score": 80.0,
        "scoring_profile_id": "gtfs-scorecard-1.3",
        "scoring_profile_rubric_version": "1.5",
        "service_horizon_status": "within_review_threshold",
        "validator_version": "7.0.0",
    }


def _pretty_sample(tmp_path: Path) -> tuple[Path, Path]:
    """A store written the way publish.py writes it: indent=2, sorted keys, 130 points."""
    source = tmp_path / "source"
    (source / "demo").mkdir(parents=True)
    (source / "rollups").mkdir()
    dates = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(130)]
    index = {
        "agencies": {
            "demo": {"name": "Demo", "history": [_history_point(d) for d in dates]},
            "few": {"name": "Few", "history": [_history_point(d) for d in dates[:3]]},
        }
    }
    latest = {
        "agency": {"id": "demo", "name": "Demo"},
        "categories": {"freshness": {"details": {"service_horizon_status": "unknown"}}},
        "feed": {"sha256": "ab" * 32, "static_url": "https://pub.example/gtfs.zip"},
        "snapshot_date": "2026-11-10",
    }
    for path, document in (
        (source / "index.json", index),
        (source / "demo" / "latest.json", latest),
        (source / "demo" / "2026-11-10.json", latest),
        (source / "directory.json", {"agencies": [{"id": "demo", "grade": "B"}]}),
        (source / "rollups" / "index.json", {"rollups": [{"id": "california"}]}),
    ):
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    (source / "demo" / "geometry.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    return source, tmp_path / "site"


def test_published_json_is_compact_and_parses_to_the_same_object(tmp_path: Path) -> None:
    source, destination = _pretty_sample(tmp_path)
    published = _assemble(source, destination)
    assert {
        "index.json",
        "directory.json",
        "rollups/index.json",
        "demo/latest.json",
        "demo/2026-11-10.json",
        "demo/geometry.geojson",
    } <= published

    for relative in (
        "directory.json",
        "rollups/index.json",
        "demo/latest.json",
        "demo/2026-11-10.json",
    ):
        pretty = (source / relative).read_text()
        compact = (destination / relative).read_text()
        assert _is_compact(compact), relative
        assert json.loads(compact) == json.loads(pretty), relative
        assert len(compact) < len(pretty), relative
        # Negative control: the pretty-printed source fails the same assertion.
        assert not _is_compact(pretty), relative
    assert _is_compact((destination / "index.json").read_text())
    geometry = destination / "demo" / "geometry.geojson"
    assert geometry.read_text() == (source / "demo" / "geometry.geojson").read_text()
    assert not _is_compact((source / "index.json").read_text()), "the source store stays pretty"


def test_published_index_history_keeps_the_newest_120_points_without_two_fields(
    tmp_path: Path,
) -> None:
    source, destination = _pretty_sample(tmp_path)
    _assemble(source, destination)
    index = json.loads((destination / "index.json").read_text())
    stored = json.loads((source / "index.json").read_text())

    demo = index["agencies"]["demo"]["history"]
    assert len(demo) == 120 and len(stored["agencies"]["demo"]["history"]) == 130
    assert [p["date"] for p in demo] == [p["date"] for p in stored["agencies"]["demo"]["history"]][
        -120:
    ]
    assert len(index["agencies"]["few"]["history"]) == 3
    for entry in index["agencies"].values():
        for point in entry["history"]:
            assert "feed_sha256" not in point and "service_horizon_status" not in point
            assert {
                "date",
                "grade",
                "grade_qualifier",
                "score",
                "categories",
                "days_until_expiry",
            } <= set(point)
            assert {"rubric_version", "scoring_profile_id", "validator_version"} <= set(point)
    assert "feed_sha256" in stored["agencies"]["demo"]["history"][0], "only the published copy"

    latest = json.loads((destination / "demo" / "latest.json").read_text())
    assert latest["feed"]["sha256"] == "ab" * 32
    assert latest["categories"]["freshness"]["details"]["service_horizon_status"] == "unknown"


def test_publish_boundary_pass_negative_control(tmp_path: Path) -> None:
    """With the boundary pass removed, the pretty, unslimmed index ships, so the
    two tests above can fail."""
    real = ROOT / "pipeline" / "scripts" / "assemble_public_artifacts.sh"
    script = real.read_text()
    call = (
        'python3 -I "$script_dir/../src/scorecard_pipeline/publish_boundary.py" '
        '"$dest_root" --write'
    )
    assert call in script
    source, destination = _pretty_sample(tmp_path)
    try:
        real.write_text(script.replace(call, "true"))
        _assemble(source, destination)
    finally:
        real.write_text(script)
    published = (destination / "index.json").read_text()
    assert not _is_compact(published)
    assert len(json.loads(published)["agencies"]["demo"]["history"]) == 130
    assert "feed_sha256" in published
