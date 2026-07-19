"""Structural contracts for the bounded production artifact writers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(name: str) -> dict[str, Any]:
    loaded = cast(dict[Any, Any], yaml.safe_load((WORKFLOWS / name).read_text()))
    # PyYAML follows YAML 1.1 and reads GitHub's `on` key as boolean true.
    if True in loaded:
        loaded["on"] = loaded.pop(True)
    return cast(dict[str, Any], loaded)


def test_artifact_writers_share_one_job_level_lock() -> None:
    daily = _workflow("scorecard.yml")
    hourly = _workflow("refresh.yml")
    targeted = _workflow("targeted-score.yml")

    for job in (daily["jobs"]["collect"], hourly["jobs"]["refresh"], targeted["jobs"]["activate"]):
        assert job["concurrency"] == {
            "group": "artifacts-publish",
            "cancel-in-progress": False,
        }

    # Scoring remains parallel; only jobs that can write the public artifact
    # store take the shared lock.
    assert "concurrency" not in daily
    assert "concurrency" not in daily["jobs"]["score"]
    assert "concurrency" not in hourly


def test_targeted_dispatch_is_required_bounded_and_registry_validated() -> None:
    workflow = _workflow("targeted-score.yml")
    input_contract = workflow["on"]["workflow_dispatch"]["inputs"]["agency_ids"]
    assert input_contract["required"] is True
    assert "maximum 25" in input_contract["description"]

    checkout = workflow["jobs"]["activate"]["steps"][0]
    assert checkout["with"]["persist-credentials"] is False

    text = (WORKFLOWS / "targeted-score.yml").read_text()
    assert "ARTIFACTS_BUCKET is required" in text
    assert "TARGET_INPUT: ${{ inputs.agency_ids }}" in text
    assert 'activation-targets --ids "$TARGET_INPUT"' in text
    assert "score selected agencies sequentially" in text.lower()


def test_targeted_hydration_and_etag_guard_cover_authoritative_inputs() -> None:
    text = (WORKFLOWS / "targeted-score.yml").read_text()

    assert "rm -rf data/artifacts" in text
    assert "python -m scorecard_pipeline.cli activation-hydrate" in text
    assert '--targets-file "$RUNNER_TEMP/targets.txt"' in text
    assert '--index-before-out "$RUNNER_TEMP/index.before.json"' in text
    assert '--etag-out "$RUNNER_TEMP/index.etag"' in text
    assert "current_dated" not in text
    assert 'aws s3 sync "$artifact_uri" data/artifacts' not in text
    assert 'cp "$RUNNER_TEMP/index.before.json" ../data/artifacts/index.json' in text
    assert text.count("aws s3api head-object") == 1
    assert 'if [ "$current_etag" != "$expected_etag" ]' in text
    assert '--if-match "$expected_etag"' in text


def test_targeted_publish_is_path_bounded_and_preserves_daily_status() -> None:
    text = (WORKFLOWS / "targeted-score.yml").read_text()

    assert 'aws s3 sync "data/artifacts/${id}" "${artifact_uri}/${id}"' in text
    for output in ("directory.json", "scoring.json", "rollups", "changes"):
        assert f"data/artifacts/{output}" in text
    assert 'cmp -s "$RUNNER_TEMP/index.before.json" data/artifacts/index.json' in text
    assert "put-object-tagging" in text
    assert "artifact-class,Value=dated" in text
    assert "data/artifacts/run" not in text
    assert "perf_gate: advisory" in text

    # No command may upload the entire artifact tree. Deletes are scoped to the
    # private fixlog cache and bounded named-change namespace, so reconciliation
    # can retire stale claims without touching score history.
    assert 'aws s3 sync data/artifacts "' not in text
    assert text.count("\n            --delete ") == 2
    assert '"s3://${ARTIFACTS_BUCKET}/cache/fixlog"' in text
    assert '"${artifact_uri}/changes"' in text


def test_artifact_publishers_regenerate_and_prune_named_change_claims() -> None:
    for name in ("scorecard.yml", "refresh.yml"):
        text = (WORKFLOWS / name).read_text()
        assert "uv run scorecard render-site" in text
        assert "data/artifacts/changes" in text
        assert "--delete --cache-control" in text


def test_hourly_refresh_publishes_only_changed_or_swept_feed_directories() -> None:
    text = (WORKFLOWS / "refresh.yml").read_text()

    assert '--changed-out "$RUNNER_TEMP/swept.txt"' in text
    assert 'sort -u "$RUNNER_TEMP/changed.txt" "$RUNNER_TEMP/swept.txt"' in text
    assert 'aws s3 sync "data/artifacts/${id}" "${artifact_uri}/${id}"' in text
    assert 'done < "$RUNNER_TEMP/refreshed.txt"' in text
    assert 'aws s3 sync data/artifacts "' not in text
    assert 'aws s3 rm "s3://${ARTIFACTS_BUCKET}/data/artifacts" --recursive' not in text


def test_boto3_workflow_commands_use_the_temporary_python_environment() -> None:
    names = ("scorecard.yml", "validator-canary.yml", "targeted-score.yml")
    combined = "\n".join((WORKFLOWS / name).read_text() for name in names)

    assert "uv run --with boto3 scorecard" not in combined
    assert combined.count("uv run --with boto3 python -m scorecard_pipeline.cli") == 5


def test_daily_collect_hydrates_current_before_overlaying_shards() -> None:
    text = (WORKFLOWS / "scorecard.yml").read_text()

    hydrate = text.index("Hydrate the authoritative current corpus and compact history")
    gather = text.index("Gather shard artifacts")
    assert hydrate < gather
    assert '--recursive --exclude "*" --include "*/latest.json"' in text
    assert "index.json proves" in text
