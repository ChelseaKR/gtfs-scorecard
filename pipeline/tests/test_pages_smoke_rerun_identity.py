"""Production smoke must accept a deploy-only rerun of its own artifact.

Run 42625283585 (2026-11-09) timed out at Pages on attempt 1; `gh run rerun
--failed` reran only the deploy jobs as attempt 2. Production served attempt
1's artifact (deployment_id 42625283585-1), which is this run's data, but smoke
expected `run_id-run_attempt` = 42625283585-2 and failed for its whole budget.

Smoke now expects the id baked into the artifact (the lighthouse job's
`deployment_id` output). These tests run the workflow's own jq filter against
served deployment.json bodies, so a rerun passes and a different run or a
stale copy still fails.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAGES = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

RUN_ID = 42625283585
COMMIT = "a" * 40
MANIFEST = "b" * 64

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="needs jq")


def _smoke_filter() -> str:
    match = re.search(
        r"assert_surface\(\) \{.*?jq -e .*?'(\.schema_version == 3.*?)'",
        PAGES,
        re.S,
    )
    assert match, "could not find the smoke jq filter in pages.yml"
    return match.group(1)


def _served(run_id: int, attempt: int) -> dict[str, object]:
    return {
        "schema_version": 3,
        "commit": COMMIT,
        "source_run_id": run_id,
        "source_run_attempt": attempt,
        "deployment_id": f"{run_id}-{attempt}",
        "release_manifest_sha256": MANIFEST,
    }


def _passes(served: dict[str, object], expected_id: str) -> bool:
    jq = shutil.which("jq")
    assert jq is not None
    result = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [
            jq,
            "-e",
            "--arg",
            "commit",
            COMMIT,
            "--arg",
            "deployment_id",
            expected_id,
            "--argjson",
            "source_run_id",
            str(RUN_ID),
            _smoke_filter(),
        ],
        input=json.dumps(served),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def test_smoke_expects_the_artifacts_own_deployment_id() -> None:
    assert "DEPLOYMENT_ID: ${{ needs.lighthouse.outputs.deployment_id }}" in PAGES
    assert 'echo "deployment_id=$deployment_id" >> "$GITHUB_OUTPUT"' in PAGES
    assert "deployment_id: ${{ steps.assemble.outputs.deployment_id }}" in PAGES


def test_a_deploy_only_rerun_passes_when_its_artifact_is_live() -> None:
    assert _passes(_served(RUN_ID, 1), f"{RUN_ID}-1")


def test_a_different_run_still_fails() -> None:
    assert not _passes(_served(RUN_ID - 1, 1), f"{RUN_ID}-1")


def test_a_stale_attempt_of_this_run_still_fails() -> None:
    assert not _passes(_served(RUN_ID, 1), f"{RUN_ID}-2")


def test_a_self_inconsistent_identity_fails() -> None:
    served = _served(RUN_ID, 1)
    served["source_run_attempt"] = 2
    assert not _passes(served, f"{RUN_ID}-1")
