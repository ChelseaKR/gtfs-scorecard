"""A deploy that reads the published corpus must read one generation of it.

`refresh.yml` and `scorecard.yml` publish to the artifacts bucket under the
`artifacts-publish` concurrency group, and they commit in two phases: every
changed agency's `latest.json` first, then `index.json` last as the pointer.
`pages.yml` is in the `pages` group, so nothing serialises a deploy against a
publish in flight, and its bounded sync runs for minutes against a commit
window of seconds.

A sync that straddles that window pairs one generation's `index.json` with
another's `latest.json`. `materialize_current_artifacts.py` compares exactly
those two and refuses the corpus. That refusal is correct and is not what these
tests relax -- `test_activation_hydration.py` pins it, with the two feed
digests move-vendome really carried. What these tests pin is the other half:
the reader has to respond to that refusal by reading the store again, because
the store is consistent at rest and a second read converges. Without that, a
publish landing mid-sync fails the deploy over data the commit never touched.
Run 34768926069 on 2026-09-13 failed this way and left the site serving a
`/bundle/` page whose prices had just been fixed.

The scan reads commands, not prose. Comments are dropped first, so a comment
naming `index.json` cannot satisfy a check for a step that never re-reads it,
and backslash continuations are joined so a wrapped command is read whole.

The rule is scoped to workflows that actually hydrate the corpus from S3.
`a11y.yml` and `e2e.yml` run the same materializer against the corpus committed
to the repository, which is a single self-consistent snapshot no re-read could
improve; a failure there is a real defect in the checkout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"

MATERIALIZER = "materialize_current_artifacts.py"
ARTIFACT_INDEX = "data/artifacts/index.json"


def _commands(text: str) -> list[str]:
    """Logical shell lines: comments dropped, backslash continuations joined."""
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    joined: list[str] = []
    pending = ""
    for line in lines:
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        joined.append(pending + stripped)
        pending = ""
    if pending:
        joined.append(pending)
    return joined


def _steps(workflow: Path) -> list[dict[str, Any]]:
    document = yaml.safe_load(workflow.read_text())
    steps: list[dict[str, Any]] = []
    for job in (document.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                steps.append(step)
    return steps


def _hydrates_from_s3(steps: list[dict[str, Any]]) -> bool:
    for step in steps:
        for command in _commands(str(step.get("run") or "")):
            if "aws s3 sync" in command and "data/artifacts" in command:
                return True
    return False


def _materializing_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        step
        for step in steps
        if any(MATERIALIZER in command for command in _commands(str(step.get("run") or "")))
    ]


def _s3_reading_materializers() -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        steps = _steps(workflow)
        materializing = _materializing_steps(steps)
        if materializing and _hydrates_from_s3(steps):
            found[workflow.name] = materializing
    return found


def test_the_scan_still_sees_the_deploy_it_was_written_for() -> None:
    """Coverage floor, so a scanner that stopped matching cannot report agreement.

    Two numbers: how many workflows run the materializer at all, and how many
    of those read the corpus from S3 and so fall under the rule below. If the
    second is empty the assertions that follow are vacuous.
    """
    running_it = {
        workflow.name
        for workflow in sorted(WORKFLOWS.glob("*.yml"))
        if _materializing_steps(_steps(workflow))
    }
    under_rule = set(_s3_reading_materializers())

    assert running_it >= {"a11y.yml", "e2e.yml", "pages.yml"}, running_it
    assert under_rule == {"pages.yml"}, (under_rule, running_it)


def test_an_s3_read_that_is_refused_is_read_again_before_the_deploy_fails() -> None:
    for name, steps in _s3_reading_materializers().items():
        for step in steps:
            commands = _commands(str(step.get("run") or ""))
            body = "\n".join(commands)

            # Re-invocable: the materializer is reached from a loop rather than
            # run once, so a refusal can be answered with another read.
            assert any(command.strip().startswith(("for ", "while ")) for command in commands), (
                f"{name}: the materializer step runs once and cannot re-read"
            )

            # The re-read has to actually re-fetch the pointer the guard
            # compares against; re-running the guard over the same bytes only
            # reproduces the same refusal.
            assert "aws s3 cp" in body and ARTIFACT_INDEX in body, (
                f"{name}: nothing re-reads {ARTIFACT_INDEX} after a refusal"
            )

            # Escalation: re-reading the pointer resolves the common straddle,
            # but a stale latest.json needs the artifacts re-read too.
            assert "--exact-timestamps" in body, (
                f"{name}: a same-size latest.json would be skipped by the re-read"
            )

            # Still fails closed. A refusal that is never resolved must stop
            # the deploy, not be swallowed into a green build.
            assert step.get("continue-on-error") in (None, False), (
                f"{name}: the guard's refusal is marked non-fatal"
            )
            assert not any(
                MATERIALIZER in command and ("|| true" in command or "|| :" in command)
                for command in commands
            ), f"{name}: the guard's refusal is discarded"
