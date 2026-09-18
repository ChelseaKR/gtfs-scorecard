"""The Action's `evidence-packet` input: retest the artifact this run already scored (#366).

Most tests here execute action.yml's composite step for real, with bash, the way
a runner does. Only two commands are stood in for, by
tests/fixtures/action_step_stub.py: `uv run ... scorecard try` (the validator is
a Java download) and `scorecard diff`. action/render_result.py and
`scorecard retest` are the shipped code.

Two properties matter most.

* **Unset, nothing moves.** A workflow that does not set `evidence-packet` must
  get the step it got before the input existed, byte for byte: the same
  commands with the same arguments, the same outputs file, job summary,
  annotations, files and exit code. The transcripts in
  tests/fixtures/action_step_without_evidence_packet.json were captured from
  action.yml and action/render_result.py at 9c4a10ef8ae, before the input was
  added, and the new step is compared with them.
* **A retest that did not happen is never a pass.** A packet that cannot be
  read or evaluated, or an artifact that is not there to evaluate, fails the
  step with the reason named. It is never read as "nothing still present".
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scorecard_pipeline.evidence_packet import build_evidence_packet

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
STUB = FIXTURES / "action_step_stub.py"
GOLDEN = FIXTURES / "action_step_without_evidence_packet.json"

HEADSIGN = "missing_trip_headsign"
WHEELCHAIR = "scorecard_wheelchair_boarding_unknown"

_EXPRESSION = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")


def _fix(rank: int, code: str, count: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "code": code,
        "count": count,
        "severity": "WARNING",
        "what": f"{count} instances of {code}.",
        "why": "Riders are affected.",
        "fix": f"Correct {code} in the export.",
        "effort": "One setting.",
    }


def scored_artifact() -> dict[str, Any]:
    """What `scorecard try --json-out` writes, trimmed to what the step reads."""
    return {
        "schema_version": "1.5",
        "snapshot_date": "2026-09-17",
        "generated_at": "2026-09-17T00:00:00+00:00",
        "rubric_version": "1.3",
        "scoring_profile": {"id": "gtfs-scorecard-1.3", "rubric_version": "1.3"},
        "validator_version": "8.0.1",
        "agency": {"id": "_adhoc", "name": "Example Transit"},
        "feed": {"static_url": "https://example.org/gtfs/feed.zip", "sha256": "a" * 64},
        "overall": {"grade": "B", "score": 84.0},
        "categories": {
            "correctness": {
                "status": "measured",
                "score": 80.0,
                "findings": [{"code": HEADSIGN, "count": 12}],
            },
            "freshness": {
                "status": "measured",
                "score": 95.0,
                "details": {"days_until_expiry": 120},
                "findings": [],
            },
            "completeness": {
                "status": "measured",
                "score": 60.0,
                "findings": [{"code": WHEELCHAIR, "count": 40}],
            },
        },
        "top_fixes": [_fix(1, WHEELCHAIR, 40), _fix(2, HEADSIGN, 12)],
    }


def _action() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((ROOT / "action.yml").read_text())
    return loaded


def gate_step() -> dict[str, Any]:
    step: dict[str, Any] = _action()["runs"]["steps"][-1]
    assert step["id"] == "gate"
    return step


def _write_files(tmp_path: Path, workspace: Path, files: dict[str, str]) -> None:
    """Write files into the workspace, or the runner's temporary directory for ``runner/``."""
    for relative, content in files.items():
        target = tmp_path / relative if relative.startswith("runner/") else workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def _write_shims(shims: Path) -> None:
    """`uv` and `python` on PATH, both handing over to the stub."""
    for tool in ("uv", "python"):
        shim = shims / tool
        shim.write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "{STUB}" {tool} "$@"\n')
        shim.chmod(0o755)


def _step_env(step: dict[str, Any], inputs: dict[str, str], runner_temp: Path) -> dict[str, str]:
    """The step's `env:` block resolved as a runner resolves it.

    An input the workflow did not set takes the default action.yml declares
    for it, so a test that omits `evidence-packet` exercises the real default.
    """
    declared = _action()["inputs"]

    def one(match: re.Match[str]) -> str:
        expression = match.group(1)
        if expression == "runner.temp":
            return str(runner_temp)
        name = expression.removeprefix("inputs.")
        assert name != expression, f"the harness cannot resolve {expression}"
        return inputs.get(name, str(declared[name].get("default", "")))

    return {
        _EXPRESSION.sub(one, str(key)): _EXPRESSION.sub(one, str(value))
        for key, value in step["env"].items()
    }


def _listing(folder: Path) -> list[str]:
    return sorted(str(path.relative_to(folder)) for path in folder.rglob("*"))


def run_step(
    tmp_path: Path,
    inputs: dict[str, str],
    *,
    artifact: dict[str, Any] | None = None,
    try_rc: int = 0,
    try_writes: bool = True,
    diff_rc: int = 0,
    script: str | None = None,
    render_result: str | None = None,
    before: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run the gate step once and return everything it did, with paths normalised.

    ``inputs`` are the workflow's `with:` values. ``before`` writes files into
    the workspace (relative paths) or the runner's temporary directory (paths
    starting ``runner/``) before the step starts. ``script`` replaces the
    step's `run:` text and ``render_result`` the source of
    action/render_result.py, for the controls that sabotage them.
    """
    workspace = tmp_path / "workspace"
    runner_temp = tmp_path / "runner"
    shims = tmp_path / "shims"
    for folder in (workspace, runner_temp, shims):
        folder.mkdir()
    action_path = ROOT
    if render_result is not None:
        action_path = tmp_path / "action-copy"
        _write_files(tmp_path, action_path, {"action/render_result.py": render_result})
    _write_files(tmp_path, workspace, before or {})
    _write_shims(shims)
    artifact_file = tmp_path / "stub-artifact.json"
    artifact_file.write_text(json.dumps(scored_artifact() if artifact is None else artifact))
    calls = tmp_path / "calls.jsonl"
    outputs = tmp_path / "github-output"
    summary = tmp_path / "step-summary"
    step = gate_step()
    env = os.environ | _step_env(step, inputs, runner_temp)
    env |= {
        "PATH": f"{shims}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_ACTION_PATH": str(action_path),
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_OUTPUT": str(outputs),
        "GITHUB_STEP_SUMMARY": str(summary),
        "STUB_CALLS": str(calls),
        "STUB_ARTIFACT_FILE": str(artifact_file),
        "STUB_TRY_RC": str(try_rc),
        "STUB_TRY_WRITES": "1" if try_writes else "0",
        "STUB_DIFF_RC": str(diff_rc),
    }
    step_file = tmp_path / "step.sh"
    step_file.write_text(step["run"] if script is None else script)
    run = subprocess.run(  # noqa: S603 - bash over this repository's own action.yml
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(step_file)],  # noqa: S607
        cwd=workspace,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    def clean(text: str) -> str:
        for real, label in (
            (str(action_path.resolve()), "<action>"),
            (str(action_path), "<action>"),
            (str(tmp_path.resolve()), "<tmp>"),
            (str(tmp_path), "<tmp>"),
            (str(ROOT), "<action>"),
        ):
            text = text.replace(real, label)
        return text

    def read(path: Path) -> str | None:
        return clean(path.read_text()) if path.exists() else None

    return {
        "exit_code": run.returncode,
        "stdout": clean(run.stdout),
        "stderr": clean(run.stderr),
        "calls": [json.loads(line) for line in (read(calls) or "").splitlines()],
        "github_output": read(outputs),
        "step_summary": read(summary),
        "workspace_files": _listing(workspace),
        "runner_temp_files": _listing(runner_temp),
    }


#: Configurations of the step with `evidence-packet` unset, covering every
#: branch it had before the input existed: the default run, a threshold failure,
#: a feed that could not be scored, a gated regression against a baseline, and
#: every other input set at once.
UNSET_SCENARIOS: dict[str, dict[str, Any]] = {
    "defaults, a passing feed": {
        "inputs": {"feed-url": "https://example.org/gtfs/feed.zip"},
    },
    "a threshold failure": {
        "inputs": {
            "feed-url": "https://example.org/gtfs/feed.zip",
            "min-grade": "A",
            "min-days-to-expiry": "30",
        },
        "try_rc": 1,
    },
    "a feed that could not be scored": {
        "inputs": {
            "feed-url": "https://example.org/gtfs/feed.zip",
            "min-grade": "C",
            "sarif": "out/gtfs.sarif",
        },
        "try_rc": 1,
        "try_writes": False,
    },
    "a gated regression against a baseline": {
        "inputs": {
            "feed-url": "https://example.org/gtfs/feed.zip",
            "baseline": "example-transit@latest",
            "fail-on-regression": "true",
        },
        "diff_rc": 1,
    },
    "every other input set": {
        "inputs": {
            "feed-url": "https://example.org/gtfs/feed.zip",
            "min-grade": "C",
            "min-days-to-expiry": "14",
            "name": "Example Transit",
            "country": "CA",
            "html": "out/scorecard.html",
            "json": "out/scorecard.json",
            "summary": "false",
            "baseline": "old.json",
            "fail-on-regression": "false",
            "sarif": "out/gtfs.sarif",
            "sarif-base": "gtfs/",
            "history-path": "history",
            "ref": "v1",
        },
        "diff_rc": 2,
    },
}


def run_unset_scenario(tmp_path: Path, name: str, *, script: str | None = None) -> dict[str, Any]:
    scenario = UNSET_SCENARIOS[name]
    return run_step(
        tmp_path,
        scenario["inputs"],
        try_rc=scenario.get("try_rc", 0),
        try_writes=scenario.get("try_writes", True),
        diff_rc=scenario.get("diff_rc", 0),
        script=script,
    )


def _golden() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(GOLDEN.read_text())
    return loaded


def _verbs(transcript: dict[str, Any]) -> list[str]:
    """Each call the step made, as `scorecard <verb>` or `render_result.py`."""
    named = []
    for call in transcript["calls"]:
        if call[0] == "uv":
            named.append(f"scorecard {call[call.index('scorecard') + 1]}")
        else:
            named.append(Path(call[1]).name)
    return named


# --- the input and its documentation ---------------------------------------------------


def test_the_input_is_opt_in_and_retests_the_scored_result() -> None:
    action = _action()
    assert action["inputs"]["evidence-packet"]["default"] == ""
    assert action["inputs"]["evidence-packet"]["required"] is False
    step = gate_step()
    assert step["env"]["EVIDENCE_PACKET"] == "${{ inputs.evidence-packet }}"
    run = step["run"]
    retest = run.index("scorecard retest")
    # Reads the result scored above; never a second `scorecard try`.
    assert run.count("scorecard try") == 1
    assert run.index("gate_rc=$?") < retest
    assert 'scorecard retest "$EVIDENCE_PACKET" --artifact "$result_json"' in run
    assert '--country "$FEED_COUNTRY"' in run[retest:]
    # render_result.py hears about the retest only when the input is set.
    assert '${retest_args[@]+"${retest_args[@]}"}' in run


def test_the_docs_never_present_evidence_packet_as_released() -> None:
    docs = (ROOT / "docs" / "ci-action.md").read_text()
    gap = docs[docs.index("**What `v1.4.0` does not yet include.**") :]
    gap = gap[: gap.index("\n## ")]
    assert "`evidence-packet`" in gap
    row = next(line for line in docs.splitlines() if line.startswith("| `evidence-packet` |"))
    assert "Not in `v1.4.0`" in row
    section = docs[docs.index("## Retesting against an evidence packet") :]
    section = section[: section.index("\n## ")]
    assert "**Not in `v1.4.0`.**" in section
    # No recipe that a reader could paste as a released `uses:` step.
    assert "uses:" not in section


# --- unset, the step is byte-identical to before the input existed -----------------------


def test_the_golden_transcripts_cover_every_scenario_and_each_one_ran_the_step() -> None:
    """A golden that recorded a step which never ran would match anything that also did not."""
    golden = _golden()
    assert "9c4a10ef8ae" in golden["captured_from"]
    assert set(golden["scenarios"]) == set(UNSET_SCENARIOS)
    for transcript in golden["scenarios"].values():
        verbs = _verbs(transcript)
        assert verbs[0] == "scorecard try"
        assert verbs[-1] == "render_result.py"
        assert "scorecard retest" not in verbs
        assert transcript["github_output"].startswith("grade=")


@pytest.mark.parametrize("name", list(UNSET_SCENARIOS))
def test_without_evidence_packet_the_step_is_byte_identical(tmp_path: Path, name: str) -> None:
    assert run_unset_scenario(tmp_path, name) == _golden()["scenarios"][name]


def _sabotage(text: str, target: str, replacement: str) -> str:
    """Apply one sabotage and prove it landed: a control that silently no-ops passes."""
    assert text.count(target) == 1, f"the control's target is not unique: {target!r}"
    sabotaged = text.replace(target, replacement)
    assert sabotaged != text
    assert replacement in sabotaged
    return sabotaged


@pytest.mark.parametrize(
    ("where", "target", "replacement", "field"),
    [
        pytest.param(
            "script",
            'if [[ -n "$EVIDENCE_PACKET" ]]; then\n  retest_json=',
            "if true; then\n  retest_json=",
            "calls",
            id="the retest runs with no packet",
        ),
        pytest.param(
            "script",
            '${retest_args[@]+"${retest_args[@]}"}',
            '--evidence-packet "$EVIDENCE_PACKET"',
            "calls",
            id="render_result.py is always told about a packet",
        ),
        pytest.param(
            "render_result",
            "    if args.evidence_packet:\n        outputs.append(",
            "    if True:\n        outputs.append(",
            "github_output",
            id="the retest outputs are always written",
        ),
    ],
)
def test_the_byte_identity_check_catches_a_change_to_the_unset_path(
    tmp_path: Path, where: str, target: str, replacement: str, field: str
) -> None:
    """Negative controls for the test above, each asserting its sabotage landed.

    Script targets are written as the parsed `run:` text has them, without the
    indentation the block carries inside action.yml.
    """
    script = gate_step()["run"]
    render = (ROOT / "action" / "render_result.py").read_text()
    if where == "script":
        script = _sabotage(script, target, replacement)
        transcript = run_unset_scenario(tmp_path, "defaults, a passing feed", script=script)
    else:
        render = _sabotage(render, target, replacement)
        scenario = UNSET_SCENARIOS["defaults, a passing feed"]
        transcript = run_step(tmp_path, scenario["inputs"], render_result=render)
    golden = _golden()["scenarios"]["defaults, a passing feed"]
    assert transcript != golden
    assert transcript[field] != golden[field]


# --- set, the step retests the result it scored ----------------------------------------


def _packet(artifact: dict[str, Any] | None = None) -> str:
    return json.dumps(build_evidence_packet(scored_artifact() if artifact is None else artifact))


def corrected_artifact() -> dict[str, Any]:
    """The republished export: new bytes, the same contract, both notices gone."""
    artifact = scored_artifact()
    artifact["feed"]["sha256"] = "b" * 64
    for category in artifact["categories"].values():
        category["findings"] = []
    artifact["top_fixes"] = []
    return artifact


def _with_packet(**extra: str) -> dict[str, str]:
    return {
        "feed-url": "https://example.org/gtfs/feed.zip",
        "evidence-packet": "packet.json",
        **extra,
    }


def _annotation(transcript: dict[str, Any]) -> str:
    """The one evidence-packet annotation the step printed, without its command prefix."""
    stdout = str(transcript["stdout"])
    prefix = "::error title=GTFS Scorecard evidence packet::"
    lines = [line for line in stdout.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1, stdout
    return lines[0].removeprefix(prefix)


def test_the_same_bytes_are_still_present_and_the_validator_runs_once(tmp_path: Path) -> None:
    transcript = run_step(tmp_path, _with_packet(), before={"packet.json": _packet()})

    assert _verbs(transcript) == ["scorecard try", "scorecard retest", "render_result.py"]
    retest_call = transcript["calls"][1]
    assert retest_call[retest_call.index("--artifact") + 1] == (
        "<tmp>/runner/gtfs-scorecard-result.json"
    )
    assert retest_call[retest_call.index("--country") + 1] == "US"
    assert transcript["exit_code"] == 1
    outputs = transcript["github_output"]
    assert "passed=false" in outputs
    assert "retest-outcome=still_present\n" in outputs
    assert "retest-json=<tmp>/runner/gtfs-scorecard-retest.json\n" in outputs
    assert _annotation(transcript) == (
        "Evidence packet retest: 2 of 2 findings in the packet are still present."
    )
    summary = transcript["step_summary"]
    assert "### Evidence packet retest" in summary
    assert "#### GTFS retest: Example Transit" in summary
    assert "same bytes" in summary


def test_a_corrected_export_passes(tmp_path: Path) -> None:
    transcript = run_step(
        tmp_path,
        _with_packet(),
        artifact=corrected_artifact(),
        before={"packet.json": _packet()},
    )

    assert transcript["exit_code"] == 0
    assert "passed=true" in transcript["github_output"]
    assert "retest-outcome=all_cleared\n" in transcript["github_output"]
    assert "::error" not in transcript["stdout"]
    assert "**Verdict:** all 2 findings in the packet are cleared." in transcript["step_summary"]


def test_a_retest_under_another_validator_fails_as_not_comparable(tmp_path: Path) -> None:
    """Corrected bytes, so a comparison would clear both. It is not a comparison."""
    other = corrected_artifact()
    other["validator_version"] = "8.1.0"
    transcript = run_step(
        tmp_path, _with_packet(), artifact=other, before={"packet.json": _packet()}
    )

    assert transcript["exit_code"] == 1
    assert "retest-outcome=non_comparable\n" in transcript["github_output"]
    assert "all_cleared" not in transcript["github_output"]
    annotation = _annotation(transcript)
    assert "2 of 2 findings could not be compared" in annotation
    assert "validator_version 8.0.1 in the packet, 8.1.0 in the retest" in annotation


@pytest.mark.parametrize(
    ("packet", "reason"),
    [
        pytest.param(None, "No such file or directory", id="the packet file is missing"),
        pytest.param("{", "Expecting property name", id="the packet is not JSON"),
        pytest.param(
            '["not", "a", "packet"]', "the packet is not a JSON object", id="not a packet"
        ),
        pytest.param(
            json.dumps(build_evidence_packet(scored_artifact()) | {"work_items": []}),
            "the packet requests no work, so there is nothing to retest",
            id="the packet requests no work",
        ),
    ],
)
def test_a_packet_that_cannot_be_retested_fails_with_its_reason(
    tmp_path: Path, packet: str | None, reason: str
) -> None:
    """The corrected export would pass a retest, so a refusal read as "no findings" passes."""
    transcript = run_step(
        tmp_path,
        _with_packet(),
        artifact=corrected_artifact(),
        before={} if packet is None else {"packet.json": packet},
    )

    assert transcript["exit_code"] == 1
    outputs = transcript["github_output"]
    assert "passed=false" in outputs
    assert "retest-outcome=\n" in outputs
    assert "retest-json=\n" in outputs
    annotation = _annotation(transcript)
    assert annotation.startswith(
        "Evidence packet retest: the evidence packet was not retested: refusing packet.json "
        "before reading the scored artifact: "
    )
    assert reason in annotation
    assert "gtfs-scorecard-retest.json" not in transcript["runner_temp_files"]
    assert "No retest record was produced." in transcript["step_summary"]


def test_a_feed_that_could_not_be_scored_is_not_retested_against_an_earlier_result(
    tmp_path: Path,
) -> None:
    """An earlier step's result at the same `json` path would clear the packet here."""
    transcript = run_step(
        tmp_path,
        _with_packet(json="out/scorecard.json"),
        try_rc=1,
        try_writes=False,
        before={
            "packet.json": _packet(),
            "out/scorecard.json": json.dumps(corrected_artifact()),
        },
    )

    assert transcript["exit_code"] == 1
    assert "retest-outcome=\n" in transcript["github_output"]
    assert "all_cleared" not in transcript["github_output"]
    annotation = _annotation(transcript)
    assert "the scored artifact out/scorecard.json could not be read" in annotation
    assert "GTFS feed could not be scored" in transcript["stdout"]


def test_a_threshold_failure_is_still_retested(tmp_path: Path) -> None:
    transcript = run_step(
        tmp_path, _with_packet(**{"min-grade": "A"}), try_rc=1, before={"packet.json": _packet()}
    )

    assert _verbs(transcript) == ["scorecard try", "scorecard retest", "render_result.py"]
    assert transcript["exit_code"] == 1
    assert "retest-outcome=still_present\n" in transcript["github_output"]
    gate = next(line for line in transcript["stdout"].splitlines() if "GTFS gate did not" in line)
    assert "Evidence packet: 2 of 2 findings in the packet are still present." in gate


def test_a_result_scored_under_another_country_is_refused(tmp_path: Path) -> None:
    transcript = run_step(tmp_path, _with_packet(country="CA"), before={"packet.json": _packet()})

    assert transcript["exit_code"] == 1
    assert "retest-outcome=\n" in transcript["github_output"]
    assert "was scored with validator country US, not CA" in _annotation(transcript)


# --- render_result.py's retest verdict, unit by unit -------------------------------------


def _render_module() -> Any:
    """action/render_result.py, imported by path: action/ is not a package."""
    spec = importlib.util.spec_from_file_location(
        "action_render_result", ROOT / "action" / "render_result.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(*verdicts: str, outcome: str) -> dict[str, Any]:
    return {
        "record_type": "gtfs-scorecard-retest",
        "outcome": outcome,
        "findings": [
            {"notice_code": f"code_{index}", "verdict": verdict, "reason": None}
            for index, verdict in enumerate(verdicts)
        ],
    }


def test_the_action_and_the_cli_agree_on_the_retest_contract() -> None:
    """action/ cannot import the pipeline package, so the contract is restated there."""
    from scorecard_pipeline import retest

    render = _render_module()
    assert {
        render.RETEST_ALL_CLEARED: render.RETEST_OUTCOMES[render.RETEST_ALL_CLEARED],
        render.RETEST_STILL_PRESENT: render.RETEST_OUTCOMES[render.RETEST_STILL_PRESENT],
        render.RETEST_CANNOT_JUDGE: render.RETEST_OUTCOMES[render.RETEST_CANNOT_JUDGE],
    } == {code: outcome for outcome, code in retest.EXIT_CODES.items()}
    assert render.RETEST_RECORD_TYPE == retest.RECORD_TYPE
    assert set(render._VERDICTS) == {retest.CLEARED, retest.STILL_PRESENT, retest.NON_COMPARABLE}


def test_no_packet_means_no_retest_verdict() -> None:
    assert _render_module().retest_verdict(False, None, None, []) == (False, "", "")


@pytest.mark.parametrize(
    ("rc", "record", "reasons", "message"),
    [
        pytest.param(None, None, [], "the retest did not run", id="asked for, never run"),
        pytest.param(
            2,
            None,
            ["refusing p.json: no work"],
            "not retested: refusing p.json: no work.",
            id="refused, with the logged reason",
        ),
        pytest.param(
            1,
            None,
            [],
            "`scorecard retest` exited 1 and wrote no record",
            id="a crash exits 1 and is not read as still present",
        ),
        pytest.param(
            0,
            _record(outcome="all_cleared"),
            [],
            "lists no finding it checked",
            id="all cleared over no findings",
        ),
        pytest.param(
            0,
            _record("cleared", "fixed", outcome="all_cleared"),
            [],
            "a finding with no readable verdict",
            id="a verdict that is not one",
        ),
        pytest.param(
            0,
            _record("cleared", "still_present", outcome="all_cleared"),
            [],
            "which its findings do not add up to",
            id="a record that contradicts itself",
        ),
        pytest.param(
            0,
            _record("still_present", outcome="still_present"),
            [],
            "exited 0, which is not its exit code for 'still_present'",
            id="an exit code the record denies",
        ),
        pytest.param(
            3,
            _record("cleared", outcome="all_cleared"),
            [],
            "exited 3, which is not its exit code for 'all_cleared'",
            id="an exit code that is not a verdict",
        ),
    ],
)
def test_a_retest_that_did_not_happen_fails_with_a_named_reason(
    rc: int | None, record: dict[str, Any] | None, reasons: list[str], message: str
) -> None:
    failed, text, outcome = _render_module().retest_verdict(True, rc, record, reasons)
    assert failed is True
    assert message in text
    assert outcome == ""


def test_each_real_outcome_is_reported_and_only_all_cleared_passes() -> None:
    verdict = _render_module().retest_verdict
    assert verdict(True, 0, _record("cleared", "cleared", outcome="all_cleared"), []) == (
        False,
        "all 2 findings in the packet are cleared.",
        "all_cleared",
    )
    assert verdict(
        True, 1, _record("still_present", "non_comparable", outcome="still_present"), []
    ) == (True, "1 of 2 findings in the packet are still present.", "still_present")
    unexplained = verdict(True, 2, _record("non_comparable", outcome="non_comparable"), [])
    assert unexplained == (
        True,
        "1 of 1 findings could not be compared, so none of them is claimed cleared.",
        "non_comparable",
    )


def test_only_error_lines_are_read_as_refusal_reasons() -> None:
    log = (
        "Resolved 40 packages\n"
        "INFO scorecard_pipeline.cli: something routine\n"
        "ERROR scorecard_pipeline.cli: refusing p.json before reading the scored artifact: "
        "the packet names no agency\n"
        "ERROR \n"
    )
    assert _render_module().retest_refusal_reasons(log) == [
        "refusing p.json before reading the scored artifact: the packet names no agency",
        "ERROR ",
    ]


def test_a_record_is_read_only_when_it_is_a_retest_record(tmp_path: Path) -> None:
    read = _render_module().read_retest_record
    assert read("") is None
    assert read(str(tmp_path / "missing.json")) is None
    for text in ("{", "[]", json.dumps({"record_type": "gtfs-scorecard-diff"})):
        (tmp_path / "record.json").write_text(text)
        assert read(str(tmp_path / "record.json")) is None
    record = _record("cleared", outcome="all_cleared")
    (tmp_path / "record.json").write_text(json.dumps(record))
    assert read(str(tmp_path / "record.json")) == record


def test_an_exit_code_that_is_not_a_number_is_no_exit_code() -> None:
    render = _render_module()
    assert render._int_or_none("") is None
    assert render._int_or_none("two") is None
    assert render._int_or_none("1") == 1
