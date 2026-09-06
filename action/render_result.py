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
    args = parser.parse_args()

    result_path = Path(args.json)
    try:
        artifact = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError):
        artifact = {}
    diff_rc = int(args.diff_rc) if args.diff_rc.strip() else None
    fail_on_regression = args.fail_on_regression.casefold() == "true"
    baseline_failed, baseline_message = baseline_verdict(diff_rc, fail_on_regression)
    passed = args.gate_rc == 0 and bool(artifact) and not baseline_failed
    grade, score, days = _facts(artifact)
    comparable = "" if diff_rc is None else str(diff_rc != DIFF_NOT_COMPARABLE).lower()
    regressed = "" if diff_rc not in (DIFF_OK, DIFF_REGRESSED) else str(
        diff_rc == DIFF_REGRESSED
    ).lower()
    _append(
        "GITHUB_OUTPUT",
        "\n".join(
            [
                f"grade={grade}",
                f"score={score}",
                f"days-to-expiry={days}",
                f"passed={str(passed).lower()}",
                f"result-json={result_path}",
                f"comparable={comparable}",
                f"regressed={regressed}",
                f"sarif={args.sarif}",
                "",
            ]
        ),
    )
    if artifact and args.write_summary.casefold() == "true":
        _append("GITHUB_STEP_SUMMARY", build_summary(artifact, passed))
        _append("GITHUB_STEP_SUMMARY", _baseline_summary(args, diff_rc, baseline_message))
    if baseline_failed:
        print(
            "::error title=GTFS Scorecard baseline::"
            + _escape_command(f"Baseline comparison: {baseline_message}")
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
        else:
            message = (
                "GTFS feed could not be scored; inspect the action log for the fetch or "
                "validation error."
            )
        print(f"::error title=GTFS Scorecard gate::{_escape_command(message)}")
    return 1 if baseline_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
