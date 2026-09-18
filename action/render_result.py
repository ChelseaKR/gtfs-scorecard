#!/usr/bin/env python3
"""Publish composite-action outputs, summary, and a concise failure annotation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _escape_command(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _facts(artifact: dict[str, Any]) -> tuple[str, str, str]:
    grade = str(artifact.get("overall", {}).get("grade", ""))
    score = str(artifact.get("overall", {}).get("score", ""))
    days = (
        artifact.get("categories", {})
        .get("freshness", {})
        .get("details", {})
        .get("days_until_expiry")
    )
    return grade, score, "" if days is None else str(days)


def build_summary(artifact: dict[str, Any], passed: bool) -> str:
    """A plain-language job summary grounded in the complete result artifact."""
    grade, score, days = _facts(artifact)
    name = str(artifact.get("agency", {}).get("name", "GTFS feed"))
    state = "passed" if passed else "needs attention"
    lines = [
        "## GTFS Scorecard",
        "",
        f"**{name}: grade {grade or '—'} ({score or '—'} / 100) · gate {state}.**",
        "",
        f"Service days remaining: {days or 'not available'}.",
        "",
    ]
    fixes = artifact.get("top_fixes", [])[:3]
    if fixes:
        lines.extend(["### Top things to fix", ""])
        lines.extend(f"{index}. {fix.get('fix', '')}" for index, fix in enumerate(fixes, 1))
        lines.append("")
    lines.append(
        "The complete machine-readable result is available at the action's `result-json` output."
    )
    lines.append("")
    return "\n".join(lines)


#: `scorecard diff` exit codes, mirrored here so the Action can tell the four
#: outcomes apart. cli.DIFF_EXIT_* is the source of truth; action/ is a separate
#: entry point that must not import the pipeline package, so the values are
#: restated and tests/test_action_render_result.py asserts they still agree.
DIFF_OK = 0
DIFF_REGRESSED = 1
DIFF_NOT_COMPARABLE = 2
DIFF_UNREADABLE = 3


def baseline_verdict(diff_rc: int | None, fail_on_regression: bool) -> tuple[bool, str]:
    """Whether the baseline comparison fails the build, and what to say about it.

    Three rules, and the second is the one that is easy to get wrong:

    * A baseline that could not be read fails **always**. It is a broken input,
      not a result, and a gate that shrugs at its own missing baseline is a gate
      that cannot fail.
    * A pair that is not comparable fails when a regression gate was asked for.
      "I cannot tell you whether this regressed" is not a pass. It does not fail
      when no gate was asked for, because then nothing was being gated.
    * A regression fails when a regression gate was asked for.
    """
    if diff_rc is None:
        return False, ""
    if diff_rc == DIFF_UNREADABLE:
        return True, (
            "the baseline could not be read, so no comparison was made. Check the "
            "`baseline` input: it must be a readable file path, an http(s) URL "
            "returning the artifact JSON, or agency@YYYY-MM-DD / agency@latest."
        )
    if diff_rc == DIFF_NOT_COMPARABLE:
        message = (
            "this run and the baseline are different measurements (rubric, scoring "
            "profile, validator, reader archive profile, or measured categories), so "
            "no change is being claimed. The job summary lists which one differs."
        )
        return fail_on_regression, message
    if diff_rc == DIFF_REGRESSED:
        return fail_on_regression, "the feed regressed against the baseline."
    if diff_rc == DIFF_OK:
        return False, "no regression against the baseline."
    return True, f"the baseline comparison exited {diff_rc}, which is not a known verdict."


def _baseline_summary(args: argparse.Namespace, diff_rc: int | None, message: str) -> str:
    """The baseline section of the job summary: the rendered diff plus the verdict.

    When the baseline could not be read there is no diff to show and the section
    says so. It never renders an empty diff, because an empty diff reads as "no
    change" and no comparison happened at all.
    """
    if diff_rc is None:
        return ""
    lines = ["", "### Baseline comparison", "", f"Baseline: `{args.baseline}`", ""]
    body = ""
    if args.diff_markdown:
        try:
            body = Path(args.diff_markdown).read_text()
        except OSError:
            body = ""
    if body.strip():
        lines.extend([body.rstrip(), ""])
    else:
        lines.extend(["No comparison was produced.", ""])
    if message:
        lines.extend([f"**Verdict:** {message}", ""])
    return "\n".join(lines)


#: `scorecard retest` exit codes and the record outcome each one reports,
#: restated for the same reason as the diff codes above: action/ must not
#: import the pipeline package. retest.EXIT_CODES and retest.RECORD_TYPE are
#: the source of truth, and tests/test_action_evidence_packet.py asserts these
#: still agree with them.
RETEST_ALL_CLEARED = 0
RETEST_STILL_PRESENT = 1
RETEST_CANNOT_JUDGE = 2
RETEST_OUTCOMES = {
    RETEST_ALL_CLEARED: "all_cleared",
    RETEST_STILL_PRESENT: "still_present",
    RETEST_CANNOT_JUDGE: "non_comparable",
}
RETEST_RECORD_TYPE = "gtfs-scorecard-retest"
_VERDICTS = ("cleared", "still_present", "non_comparable")


def read_retest_record(path_text: str) -> dict[str, Any] | None:
    """The retest record the step wrote, or ``None`` when there is none to read.

    The step deletes the record path before the retest runs, so a file here
    was written by this run's retest and not left over from an earlier one.
    """
    if not path_text:
        return None
    try:
        record = json.loads(Path(path_text).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict) or record.get("record_type") != RETEST_RECORD_TYPE:
        return None
    return record


def retest_refusal_reasons(log_text: str) -> list[str]:
    """Why `scorecard retest` wrote no record, from the stderr the step captured.

    The CLI logs ``LEVEL logger: message``, and it logs an ERROR line for
    each thing it refuses: a packet it cannot read or will not retest, or an
    artifact it cannot read. Anything else on stderr (uv's own progress, a
    traceback) is left for the step log, where it is printed in full.
    """
    reasons = []
    for line in log_text.splitlines():
        if line.startswith("ERROR "):
            reasons.append(line.partition(": ")[2].strip() or line)
    return reasons


def _tally(findings: list[Any]) -> dict[str, int] | None:
    """Count the record's per-finding verdicts, or ``None`` if one is unreadable."""
    verdicts = [entry.get("verdict") if isinstance(entry, dict) else None for entry in findings]
    if any(verdict not in _VERDICTS for verdict in verdicts):
        return None
    return {verdict: verdicts.count(verdict) for verdict in _VERDICTS}


def retest_verdict(
    requested: bool, retest_rc: int | None, record: dict[str, Any] | None, reasons: list[str]
) -> tuple[bool, str, str]:
    """Whether the evidence-packet retest fails the build, what to say, and its outcome.

    Setting `evidence-packet` is the request for this gate, so every result
    other than "every finding cleared" fails, and "not comparable" fails with
    it: "I cannot tell you whether this was fixed" is not a pass.

    The exit code is a report about the record, not a substitute for it. A
    pass needs a record that exists, lists at least one finding, and whose
    per-finding verdicts add up to the outcome the exit code claims. Anything
    short of that is a retest that did not happen, and it fails with the
    reason named. It is never read as "nothing still present", which is the
    one answer a gate that skipped its own check would give.
    """
    if not requested:
        return False, "", ""
    if retest_rc is None:
        return True, "the retest did not run, so the packet was not checked.", ""
    if record is None:
        why = "; ".join(reasons) or (
            f"`scorecard retest` exited {retest_rc} and wrote no record; its output is in "
            "the step log"
        )
        return True, f"the evidence packet was not retested: {why}.", ""
    findings = record.get("findings")
    if not isinstance(findings, list) or not findings:
        return True, "the retest record lists no finding it checked, so nothing was retested.", ""
    tally = _tally(findings)
    if tally is None:
        return True, (
            "the retest record has a finding with no readable verdict, so no verdict is "
            "taken from it."
        ), ""
    if tally["still_present"]:
        outcome = "still_present"
    elif tally["non_comparable"]:
        outcome = "non_comparable"
    else:
        outcome = "all_cleared"
    if record.get("outcome") != outcome:
        return True, (
            f"the retest record says {record.get('outcome')!r}, which its findings do not "
            "add up to, so no verdict is taken from it."
        ), ""
    if RETEST_OUTCOMES.get(retest_rc) != outcome:
        return True, (
            f"`scorecard retest` exited {retest_rc}, which is not its exit code for "
            f"{outcome!r}, so no verdict is taken from the record."
        ), ""
    total = len(findings)
    if outcome == "all_cleared":
        return False, f"all {total} findings in the packet are cleared.", outcome
    if outcome == "still_present":
        still = tally["still_present"]
        return True, f"{still} of {total} findings in the packet are still present.", outcome
    why = "; ".join(sorted({str(entry["reason"]) for entry in findings if entry.get("reason")}))
    return True, (
        f"{tally['non_comparable']} of {total} findings could not be compared, so none of "
        f"them is claimed cleared{': ' + why if why else ''}."
    ), outcome


def _retest_summary(args: argparse.Namespace, record: dict[str, Any] | None, message: str) -> str:
    """The evidence-packet section of the job summary: the retest record, then the verdict.

    The record's own Markdown is written to be pasted into a ticket and opens
    with a top-level heading, so its headings are moved under this section's.
    """
    if not args.evidence_packet:
        return ""
    lines = ["", "### Evidence packet retest", "", f"Packet: `{args.evidence_packet}`", ""]
    body = ""
    if record is not None and args.retest_markdown:
        try:
            body = Path(args.retest_markdown).read_text()
        except OSError:
            body = ""
    if body.strip():
        demoted = ("###" + line if line.startswith("#") else line for line in body.splitlines())
        lines.extend(["\n".join(demoted).rstrip(), ""])
    else:
        lines.extend(["No retest record was produced.", ""])
    lines.extend([f"**Verdict:** {message}", ""])
    return "\n".join(lines)


def _int_or_none(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


def _append(path_var: str, content: str) -> None:
    path = os.environ.get(path_var)
    if path:
        with Path(path).open("a") as handle:
            handle.write(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--gate-rc", required=True, type=int)
    parser.add_argument("--min-grade", default="")
    parser.add_argument("--min-days", default="")
    parser.add_argument("--write-summary", default="true")
    parser.add_argument("--baseline", default="")
    parser.add_argument("--diff-rc", default="")
    parser.add_argument("--diff-markdown", default="")
    parser.add_argument("--fail-on-regression", default="false")
    parser.add_argument("--sarif", default="")
    # The evidence-packet retest. Passed only when the `evidence-packet` input
    # is set, so a run without it gets the outputs, summary and annotations it
    # always did.
    parser.add_argument("--evidence-packet", default="")
    parser.add_argument("--retest-rc", default="")
    parser.add_argument("--retest-json", default="")
    parser.add_argument("--retest-markdown", default="")
    parser.add_argument("--retest-log", default="")
    args = parser.parse_args()

    result_path = Path(args.json)
    try:
        artifact = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError):
        artifact = {}
    diff_rc = int(args.diff_rc) if args.diff_rc.strip() else None
    fail_on_regression = args.fail_on_regression.casefold() == "true"
    baseline_failed, baseline_message = baseline_verdict(diff_rc, fail_on_regression)
    retest_record = read_retest_record(args.retest_json)
    try:
        retest_log = Path(args.retest_log).read_text() if args.retest_log else ""
    except OSError:
        retest_log = ""
    retest_failed, retest_message, retest_outcome = retest_verdict(
        bool(args.evidence_packet),
        _int_or_none(args.retest_rc),
        retest_record,
        retest_refusal_reasons(retest_log),
    )
    passed = args.gate_rc == 0 and bool(artifact) and not baseline_failed and not retest_failed
    grade, score, days = _facts(artifact)
    comparable = "" if diff_rc is None else str(diff_rc != DIFF_NOT_COMPARABLE).lower()
    regressed = "" if diff_rc not in (DIFF_OK, DIFF_REGRESSED) else str(
        diff_rc == DIFF_REGRESSED
    ).lower()
    outputs = [
        f"grade={grade}",
        f"score={score}",
        f"days-to-expiry={days}",
        f"passed={str(passed).lower()}",
        f"result-json={result_path}",
        f"comparable={comparable}",
        f"regressed={regressed}",
        f"sarif={args.sarif}",
    ]
    if args.evidence_packet:
        outputs.append(f"retest-outcome={retest_outcome}")
        outputs.append(f"retest-json={args.retest_json if retest_record is not None else ''}")
    _append("GITHUB_OUTPUT", "\n".join([*outputs, ""]))
    if artifact and args.write_summary.casefold() == "true":
        _append("GITHUB_STEP_SUMMARY", build_summary(artifact, passed))
        _append("GITHUB_STEP_SUMMARY", _baseline_summary(args, diff_rc, baseline_message))
        _append("GITHUB_STEP_SUMMARY", _retest_summary(args, retest_record, retest_message))
    if baseline_failed:
        print(
            "::error title=GTFS Scorecard baseline::"
            + _escape_command(f"Baseline comparison: {baseline_message}")
        )
    if retest_failed:
        print(
            "::error title=GTFS Scorecard evidence packet::"
            + _escape_command(f"Evidence packet retest: {retest_message}")
        )
    if not passed:
        if artifact:
            requirements = []
            if args.min_grade:
                requirements.append(f"minimum grade {args.min_grade}")
            if args.min_days:
                requirements.append(f"minimum {args.min_days} service days")
            suffix = f" Required: {', '.join(requirements)}." if requirements else ""
            message = f"GTFS gate did not pass: grade {grade}, score {score}.{suffix}"
            if baseline_failed:
                message = f"{message} Baseline: {baseline_message}"
            if retest_failed:
                message = f"{message} Evidence packet: {retest_message}"
        else:
            message = (
                "GTFS feed could not be scored; inspect the action log for the fetch or "
                "validation error."
            )
        print(f"::error title=GTFS Scorecard gate::{_escape_command(message)}")
    return 1 if baseline_failed or retest_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
