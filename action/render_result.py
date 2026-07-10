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
    args = parser.parse_args()

    result_path = Path(args.json)
    try:
        artifact = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError):
        artifact = {}
    passed = args.gate_rc == 0 and bool(artifact)
    grade, score, days = _facts(artifact)
    _append(
        "GITHUB_OUTPUT",
        "\n".join(
            [
                f"grade={grade}",
                f"score={score}",
                f"days-to-expiry={days}",
                f"passed={str(passed).lower()}",
                f"result-json={result_path}",
                "",
            ]
        ),
    )
    if artifact and args.write_summary.casefold() == "true":
        _append("GITHUB_STEP_SUMMARY", build_summary(artifact, passed))
    if not passed:
        if artifact:
            requirements = []
            if args.min_grade:
                requirements.append(f"minimum grade {args.min_grade}")
            if args.min_days:
                requirements.append(f"minimum {args.min_days} service days")
            suffix = f" Required: {', '.join(requirements)}." if requirements else ""
            message = f"GTFS gate did not pass: grade {grade}, score {score}.{suffix}"
        else:
            message = (
                "GTFS feed could not be scored; inspect the action log for the fetch or "
                "validation error."
            )
        print(f"::error title=GTFS Scorecard gate::{_escape_command(message)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
