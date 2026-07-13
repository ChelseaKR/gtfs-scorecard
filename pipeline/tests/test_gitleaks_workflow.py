"""Structural contracts for the blocking Gitleaks history-diff gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
SECURITY_WORKFLOW = ROOT / ".github" / "workflows" / "security.yml"
GITLEAKS_VERSION = "8.30.1"
GITLEAKS_LINUX_X64_SHA256 = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
RETIRED_GITLEAKS_ACTION_SHA = "ff98106e4c7b2bc287b24eaf42907196329070c7"


def _secret_scan_job() -> dict[str, Any]:
    workflow = cast(dict[str, Any], yaml.safe_load(SECURITY_WORKFLOW.read_text()))
    return cast(dict[str, Any], workflow["jobs"]["secret-scan"])


def test_gitleaks_cli_release_and_checksum_are_pinned() -> None:
    job = _secret_scan_job()
    scan_step = job["steps"][1]

    assert job["permissions"] == {"contents": "read"}
    assert "uses" not in scan_step
    assert scan_step["env"]["GITLEAKS_VERSION"] == GITLEAKS_VERSION
    assert scan_step["env"]["GITLEAKS_LINUX_X64_SHA256"] == GITLEAKS_LINUX_X64_SHA256

    command = scan_step["run"]
    assert "gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}" in command
    assert "gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" in command
    assert "sha256sum --check --strict" in command
    assert 'actual_version=$("$bin_dir/gitleaks" version)' in command

    workflow_text = SECURITY_WORKFLOW.read_text()
    assert "gitleaks/gitleaks-action" not in workflow_text
    assert RETIRED_GITLEAKS_ACTION_SHA not in workflow_text


def test_gitleaks_scans_trusted_event_commit_ranges_and_fails_closed() -> None:
    scan_step = _secret_scan_job()["steps"][1]
    env = scan_step["env"]
    command = scan_step["run"]

    assert env["EVENT_NAME"] == "${{ github.event_name }}"
    assert env["PR_BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert env["PR_HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert env["PUSH_BEFORE_SHA"] == "${{ github.event.before }}"
    assert env["PUSH_AFTER_SHA"] == "${{ github.event.after }}"

    assert 'before_sha="$PR_BASE_SHA"' in command
    assert 'after_sha="$PR_HEAD_SHA"' in command
    assert 'before_sha="$PUSH_BEFORE_SHA"' in command
    assert 'after_sha="$PUSH_AFTER_SHA"' in command
    assert 'range="${before_sha}..${after_sha}"' in command
    assert 'git cat-file -e "${before_sha}^{commit}"' in command
    assert 'git cat-file -e "${after_sha}^{commit}"' in command
    assert 'gitleaks" git --redact --exit-code 1 --log-opts="$range" .' in command
    assert "GITHUB_STEP_SUMMARY" in command
    assert "continue-on-error" not in command
    assert "|| true" not in command
