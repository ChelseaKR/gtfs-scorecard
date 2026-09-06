"""Contract tests for the richer GitHub Action result surface."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
from io import BytesIO
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_marketplace_metadata_and_documented_refs_match_release_version() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    project = tomllib.loads((ROOT / "pipeline/pyproject.toml").read_text())
    version = project["project"]["version"]
    major = version.split(".", maxsplit=1)[0]
    docs = (ROOT / "docs/ci-action.md").read_text()

    assert action["name"] == "GTFS Scorecard gate"
    assert action["description"]
    assert action["author"]
    assert action["branding"] == {"icon": "check-circle", "color": "green"}
    assert set(re.findall(r"ChelseaKR/gtfs-scorecard@(v\d+)", docs)) == {f"v{major}"}
    assert f"@v{version}" in docs


def test_release_sign_validates_the_actual_tag_before_release_operations() -> None:
    workflow = (ROOT / ".github/workflows/release-sign.yml").read_text()
    validate_start = workflow.index("- name: Validate release tag")
    cosign_start = workflow.index("- name: Install cosign")
    sign_start = workflow.index("- name: Sign the manifest (keyless)")
    attest_start = workflow.index("- name: Attest release provenance")
    validate_step = workflow[validate_start:cosign_start]
    attach_step = workflow.split("Wait for the release and attach verification assets", 1)[1]

    assert validate_start < cosign_start < sign_start < attest_start
    assert "RESOLVED_TAG: ${{ inputs.tag || github.ref_name }}" in validate_step
    assert "^v[0-9]+\\.[0-9]+\\.[0-9]+$" in validate_step
    assert 'git show-ref --verify --quiet "refs/tags/$RESOLVED_TAG"' in validate_step
    assert 'git rev-parse "refs/tags/${RESOLVED_TAG}^{commit}"' in validate_step
    assert 'gpg.ssh.allowedSignersFile "$GITHUB_WORKSPACE/.github/release-signers"' in validate_step
    assert 'git tag -v "$RESOLVED_TAG"' in validate_step
    assert 'printf \'tag=%s\\n\' "$RESOLVED_TAG" >> "$GITHUB_OUTPUT"' in validate_step
    assert "RELEASE_TAG: ${{ steps.release_tag.outputs.tag }}" in attach_step
    assert 'tag="$RELEASE_TAG"' in attach_step
    assert 'tag="${{ steps.release_tag.outputs.tag }}"' not in attach_step


def test_action_declares_stable_outputs_and_json_input() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    assert set(action["outputs"]) == {
        "grade",
        "score",
        "days-to-expiry",
        "passed",
        "result-json",
    }
    assert action["inputs"]["json"]["required"] is False
    assert action["inputs"]["summary"]["default"] == "true"
    assert action["inputs"]["country"]["default"] == "US"
    run = action["runs"]["steps"][-1]["run"]
    assert '--country "$FEED_COUNTRY"' in run
    assert '--json-out "$result_json"' in run
    assert 'uv run --project "${GITHUB_ACTION_PATH}/pipeline" --locked --no-dev' in run
    assert "git+https://" not in run
    assert "uvx" not in run
    assert 'exit "$gate_rc"' in run

    uv_setup = action["runs"]["steps"][-2]
    assert uv_setup["with"] == {
        "version": "0.11.29",
        "enable-cache": False,
        "ignore-empty-workdir": True,
    }


def test_action_source_archive_is_runtime_bounded() -> None:
    git = shutil.which("git")
    assert git is not None
    archive = subprocess.run(  # noqa: S603 - resolved git binary over this checkout
        [git, "archive", "--worktree-attributes", "--format=tar", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as bundle:
        names = set(bundle.getnames())

    assert "action.yml" in names
    assert "action/render_result.py" in names
    assert "pipeline/pyproject.toml" in names
    assert "pipeline/src/scorecard_pipeline/cli.py" in names
    assert "pipeline/uv.lock" in names
    assert not any(name.startswith("data/") for name in names)
    assert not any(name.startswith("web/") for name in names)
    assert not any(name.startswith("pipeline/tests/") for name in names)
    assert len(names) < 600


def test_result_script_writes_outputs_summary_and_annotation(tmp_path: Path) -> None:
    artifact = {
        "agency": {"name": "Example Transit"},
        "overall": {"grade": "C", "score": 72.5},
        "categories": {"freshness": {"details": {"days_until_expiry": 12}}},
        "top_fixes": [{"fix": "Extend the service calendar."}],
    }
    result = tmp_path / "result.json"
    output = tmp_path / "output.txt"
    summary = tmp_path / "summary.md"
    result.write_text(json.dumps(artifact))
    env = os.environ | {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)}

    run = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        [
            sys.executable,
            str(ROOT / "action/render_result.py"),
            "--json",
            str(result),
            "--gate-rc",
            "1",
            "--min-grade",
            "B",
            "--write-summary",
            "true",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    outputs = output.read_text()
    assert "grade=C" in outputs
    assert "days-to-expiry=12" in outputs
    assert "passed=false" in outputs
    assert "Example Transit: grade C" in summary.read_text()
    assert "::error title=GTFS Scorecard gate::" in run.stdout


@pytest.mark.parametrize(
    "gate_rc",
    [
        pytest.param(1, id="the scorer reported the refusal"),
        pytest.param(0, id="the refusal did not reach the exit code"),
    ],
)
def test_a_refused_feed_never_reports_a_passing_gate_or_a_grade(
    tmp_path: Path, gate_rc: int
) -> None:
    """The downstream shape: the scorer refused, so there is no result file.

    `score_feed_content` raises for an archive that describes no service, and
    `_cmd_try` reports it and exits 1 before `--json-out` is written
    (tests/test_unmeasurable_feed.py). The action still runs this script, with a
    `--json` path that does not exist, and what it prints is what a caller acts
    on. Three things have to hold and each one was reported wrong against
    `gtfs-scorecard@v1.4.0`:

    * `passed` is false. Someone pointing the action at a broken export must not
      be told the gate passed.
    * `grade` and `score` are empty rather than defaulted. A blank is the only
      honest output for a feed nobody read; a letter here would be the same
      fabrication one layer further out.
    * no job summary is written. The summary renders "grade —" for an empty
      artifact, which reads as a scorecard with a missing field rather than as
      no scorecard at all.

    The script itself still exits 0: the action's own exit code is the scorer's
    `$gate_rc`, so a crash here would replace a clean gate failure with a broken
    step.

    Run for a refusal the scorer reported and for one it did not. `passed` is
    two conditions, `gate_rc == 0 and bool(artifact)`, and only the second case
    exercises the second half: an absent result must be a failed gate even if
    the exit code says otherwise, because the artifact is the evidence and the
    exit code is only a report about it.
    """
    missing = tmp_path / "never-written.json"
    output = tmp_path / "output.txt"
    summary = tmp_path / "summary.md"
    env = os.environ | {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)}

    run = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        [
            sys.executable,
            str(ROOT / "action/render_result.py"),
            "--json",
            str(missing),
            "--gate-rc",
            str(gate_rc),
            "--min-grade",
            "B",
            "--write-summary",
            "true",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    outputs = output.read_text()
    assert "passed=false" in outputs
    assert "grade=\n" in outputs, "a refused feed must not be given a letter"
    assert "score=\n" in outputs
    assert "days-to-expiry=\n" in outputs
    assert not summary.exists(), "nothing was scored, so there is nothing to summarize"
    assert "::error title=GTFS Scorecard gate::GTFS feed could not be scored" in run.stdout
    assert "did not pass: grade" not in run.stdout, (
        "a refusal is not a threshold failure and must not be reported as one"
    )


def test_cli_json_output_is_written_before_gate_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse

    from scorecard_pipeline import cli

    artifact = {
        "agency": {"name": "Example Transit"},
        "feed": {"static_url": "https://example.org/gtfs.zip"},
        "overall": {"grade": "C", "score": 72.5},
        "categories": {
            "correctness": {"status": "measured", "score": 70},
            "freshness": {
                "status": "measured",
                "score": 80,
                "details": {"days_until_expiry": 12},
            },
        },
        "top_fixes": [],
    }
    monkeypatch.setattr(cli, "run_adhoc", lambda *_args, **_kwargs: artifact)
    monkeypatch.setattr(
        "scorecard_pipeline.render_site._render_agency",
        lambda *_args, **_kwargs: '<link href="/app.css">',
    )
    monkeypatch.setattr(
        "scorecard_pipeline.onboard.render_comment",
        lambda *_args, **_kwargs: "Scorecard comment\n",
    )
    output = tmp_path / "nested/result.json"
    html_output = tmp_path / "nested/report/scorecard.html"
    comment_output = tmp_path / "nested/comment/scorecard.md"
    args = argparse.Namespace(
        url="https://example.org/gtfs.zip",
        name=None,
        date=None,
        html=str(html_output),
        comment=str(comment_output),
        page_url=None,
        json_out=str(output),
        min_grade="B",
        min_days_to_expiry=None,
    )
    assert cli._cmd_try(args, argparse.ArgumentParser()) == 1
    assert json.loads(output.read_text())["overall"]["grade"] == "C"
    assert html_output.read_text().startswith('<link href="https://gtfsscorecard.org/')
    assert comment_output.read_text() == "Scorecard comment\n"


def test_installed_action_command_does_not_require_an_agency_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import cli

    def registry_must_not_load() -> None:
        raise AssertionError("scorecard try must be registry-free")

    monkeypatch.setattr(cli, "load_agencies", registry_must_not_load)
    monkeypatch.setattr(cli, "_cmd_try", lambda _args, _parser: 0)
    assert cli.main(["try", "https://example.org/gtfs.zip"]) == 0
