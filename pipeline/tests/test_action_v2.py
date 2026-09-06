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
        "comparable",
        "regressed",
    }
    assert action["inputs"]["json"]["required"] is False
    assert action["inputs"]["summary"]["default"] == "true"
    assert action["inputs"]["country"]["default"] == "US"
    # The baseline comparison is opt-in and its gate is opt-in separately: a
    # workflow that only wants the comparison reported must not start failing.
    assert action["inputs"]["baseline"]["default"] == ""
    assert action["inputs"]["fail-on-regression"]["default"] == "false"
    run = action["runs"]["steps"][-1]["run"]
    assert '--country "$FEED_COUNTRY"' in run
    assert '--json-out "$result_json"' in run
    assert 'uv run --project "${GITHUB_ACTION_PATH}/pipeline" --locked --no-dev' in run
    assert "git+https://" not in run
    assert "uvx" not in run
    assert 'exit "$gate_rc"' in run
    # The comparison only runs over a result that exists. Diffing against a
    # scorer that refused would compare a baseline with nothing.
    assert '[[ -n "$BASELINE" && "$gate_rc" -eq 0 ]]' in run
    assert 'scorecard diff "$BASELINE" "$result_json"' in run
    # render_result.py's exit code has to survive `set -e` to be readable at all.
    assert "render_rc=$?" in run
    assert 'exit "$render_rc"' in run

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


def _run_render(
    tmp_path: Path, *, artifact: dict[str, object] | None = None, **flags: str
) -> tuple[int, str, str]:
    """Run action/render_result.py and return (exit code, GITHUB_OUTPUT, annotations)."""
    result = tmp_path / "result.json"
    output = tmp_path / "output.txt"
    summary = tmp_path / "summary.md"
    result.write_text(
        json.dumps(
            artifact
            if artifact is not None
            else {
                "agency": {"name": "Example Transit"},
                "overall": {"grade": "B", "score": 84.0},
                "categories": {"freshness": {"details": {"days_until_expiry": 120}}},
            }
        )
    )
    argv = [
        sys.executable,
        str(ROOT / "action/render_result.py"),
        "--json",
        str(result),
        "--gate-rc",
        "0",
        "--write-summary",
        "true",
    ]
    for key, value in flags.items():
        argv.extend([f"--{key.replace('_', '-')}", value])
    run = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        argv,
        env=os.environ | {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)},
        check=False,
        capture_output=True,
        text=True,
    )
    return run.returncode, output.read_text(), run.stdout + summary.read_text()


def test_no_baseline_leaves_the_comparison_outputs_blank(tmp_path: Path) -> None:
    code, outputs, _ = _run_render(tmp_path)
    assert code == 0
    assert "passed=true" in outputs
    assert "comparable=\n" in outputs
    assert "regressed=\n" in outputs


def test_an_unreadable_baseline_fails_even_without_the_regression_gate(tmp_path: Path) -> None:
    """The gate that cannot fail, closed.

    `fail-on-regression: false` means "report, do not gate". It does not mean
    "accept a baseline I never read". A misconfigured `baseline` input that
    passed silently would leave a workflow believing it had a comparison.
    """
    code, outputs, text = _run_render(
        tmp_path, baseline="s3://nope", diff_rc="3", fail_on_regression="false"
    )
    assert code == 1
    assert "passed=false" in outputs
    assert "the baseline could not be read" in text
    # No comparison happened, so the summary must not render an empty diff as
    # though it were a clean one.
    assert "No comparison was produced." in text


def test_a_non_comparable_baseline_fails_the_regression_gate(tmp_path: Path) -> None:
    """ "I cannot tell you whether this regressed" is not a pass."""
    code, outputs, text = _run_render(
        tmp_path, baseline="old.json", diff_rc="2", fail_on_regression="true"
    )
    assert code == 1
    assert "passed=false" in outputs
    assert "comparable=false" in outputs
    assert "regressed=\n" in outputs
    assert "different measurements" in text


def test_a_non_comparable_baseline_is_reported_but_not_gated_when_no_gate_was_asked_for(
    tmp_path: Path,
) -> None:
    code, outputs, text = _run_render(
        tmp_path, baseline="old.json", diff_rc="2", fail_on_regression="false"
    )
    assert code == 0
    assert "passed=true" in outputs
    assert "comparable=false" in outputs
    assert "different measurements" in text


def test_a_regression_fails_only_when_the_gate_was_asked_for(tmp_path: Path) -> None:
    gated, gated_outputs, gated_text = _run_render(
        tmp_path, baseline="old.json", diff_rc="1", fail_on_regression="true"
    )
    assert gated == 1
    assert "regressed=true" in gated_outputs
    assert "the feed regressed against the baseline" in gated_text

    ungated, ungated_outputs, _ = _run_render(
        tmp_path, baseline="old.json", diff_rc="1", fail_on_regression="false"
    )
    assert ungated == 0
    assert "regressed=true" in ungated_outputs
    assert "passed=true" in ungated_outputs


def test_a_clean_comparison_passes_and_reports_both_outputs(tmp_path: Path) -> None:
    code, outputs, _ = _run_render(
        tmp_path, baseline="old.json", diff_rc="0", fail_on_regression="true"
    )
    assert code == 0
    assert "comparable=true" in outputs
    assert "regressed=false" in outputs


def test_the_action_and_the_cli_agree_on_the_diff_exit_codes() -> None:
    """action/ cannot import the pipeline package, so the codes are restated there."""
    from scorecard_pipeline import cli

    action_source = (ROOT / "action/render_result.py").read_text()
    for name, value in (
        ("DIFF_OK", cli.DIFF_EXIT_OK),
        ("DIFF_REGRESSED", cli.DIFF_EXIT_REGRESSED),
        ("DIFF_NOT_COMPARABLE", cli.DIFF_EXIT_NOT_COMPARABLE),
        ("DIFF_UNREADABLE", cli.DIFF_EXIT_UNREADABLE),
    ):
        assert f"{name} = {value}" in action_source
