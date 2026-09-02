"""Every merge-blocking job is actually required to merge (ADR 0033).

ADR 0033: "If `infra/compute`, CodeQL, dependency-audit, zizmor, or
container-scan jobs land (P1), their exact job/check names must be appended to
`.github/rulesets/main.json` and the live ruleset updated ... in the same
change that adds the workflow -- not as a follow-up that might not happen."

That follow-up did not happen. container-scan, iac, zizmor and dependency-review
all ran on pull requests while none of them could block a merge. container-scan
caught ten HIGH-severity CVEs in the shipped Lambda images this month; it found
them because it happened to run, not because anything required it to pass.

Nothing compared the workflows to the ruleset, so the omission was invisible.
This test is that comparison: a new pull-request job is either required to
merge or listed in ADVISORY_JOBS with a reason, and there is no third option
where it quietly runs and blocks nothing.

The ruleset file is the reviewable configuration; the live ruleset API is the
enforcement source (ADR 0033). This test can only hold the file. Applying it
still needs `gh api repos/ChelseaKR/gtfs-scorecard/rulesets/{id} -X PUT`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
RULESET = REPO_ROOT / ".github" / "rulesets" / "main.json"

# Pull-request jobs that deliberately do not block a merge. Each entry is a
# decision someone made, not a gap nobody noticed. Keep the reason with it.
#
# "Analyze (javascript)" (issue #288) briefly lived here while its first real
# PR run was unverified — see PR #302, which reported clean (run 32507900709,
# job "Analyze (javascript)": success) — then moved to
# .github/rulesets/main.json's required list (file and live) once confirmed.
ADVISORY_JOBS: dict[str, str] = {
    # links.yml (2026-09-01): lychee over the four money pages. Advisory for
    # its first cycle because the check depends on third-party hosts, several
    # of which in the transit sector refuse unknown user agents, and a false
    # red on every PR would teach people to ignore it. Promote it to the
    # ruleset (file and live) once a week of scheduled runs is clean.
    "money pages have no dead links": "external-host dependency; unverified first cycle",
}

_MATRIX_REF = re.compile(r"\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}")


def _load_yaml(path: Path) -> dict[Any, Any]:
    # Keys are Any, not str: PyYAML parses a workflow's bare `on:` as True.
    return yaml.safe_load(path.read_text())  # type: ignore[no-any-return]


def _triggers(workflow: dict[Any, Any]) -> set[str]:
    # PyYAML parses a bare `on:` key as the boolean True.
    on = workflow.get(True, workflow.get("on"))
    if isinstance(on, str):
        return {on}
    return set(on or ())


def _matrix_rows(job: dict[str, Any]) -> list[dict[str, Any]]:
    """The matrix combinations a job expands into, or one empty row."""
    matrix = (job.get("strategy") or {}).get("matrix")
    if not isinstance(matrix, dict):
        return [{}]
    if isinstance(matrix.get("include"), list):
        return [row for row in matrix["include"] if isinstance(row, dict)]
    rows: list[dict[str, Any]] = [{}]
    for key, values in matrix.items():
        if key in ("include", "exclude") or not isinstance(values, list):
            continue
        rows = [{**row, key: value} for row in rows for value in values]
    return rows


def _check_names(job_id: str, job: dict[str, Any]) -> list[str]:
    """The status-check contexts a job publishes, matrix expanded.

    A matrix job publishes one check per combination, named by substituting the
    matrix values into the job name -- which is exactly why "container-scan" is
    not a context anyone can require.
    """
    template = str(job.get("name") or job_id)
    if not _MATRIX_REF.search(template):
        return [template]

    def expand(row: dict[str, Any]) -> str:
        return _MATRIX_REF.sub(lambda m: str(row.get(m.group(1), m.group(0))), template)

    return [expand(row) for row in _matrix_rows(job)]


def _pull_request_checks() -> dict[str, str]:
    """Every status-check context a pull request produces -> its source."""
    checks: dict[str, str] = {}
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        workflow = _load_yaml(path)
        if "pull_request" not in _triggers(workflow):
            continue
        for job_id, job in (workflow.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for name in _check_names(job_id, job):
                checks[name] = f"{path.name}::{job_id}"
    return checks


def _required_contexts() -> set[str]:
    ruleset = json.loads(RULESET.read_text())
    return {
        check["context"]
        for rule in ruleset["rules"]
        if rule["type"] == "required_status_checks"
        for check in rule["parameters"]["required_status_checks"]
    }


def test_every_pull_request_job_is_required_or_declared_advisory() -> None:
    checks = _pull_request_checks()
    assert checks, "no pull-request jobs found; the workflow parse is wrong"
    required = _required_contexts()
    unenforced = {
        name: source
        for name, source in sorted(checks.items())
        if name not in required and name not in ADVISORY_JOBS
    }
    assert not unenforced, (
        f"{len(unenforced)} pull-request checks cannot block a merge. Add each to "
        f".github/rulesets/main.json (and the live ruleset) per ADR 0033, or to "
        f"ADVISORY_JOBS with a reason:\n"
        + "\n".join(f"  {name!r}  ({source})" for name, source in unenforced.items())
    )


def test_no_required_check_is_unproducible() -> None:
    """A required context no workflow emits blocks every merge forever.

    The mirror of the gap above, and the reason this test cannot be satisfied
    by pasting plausible names into the ruleset: a typo in a matrix-expanded
    context is indistinguishable from a check that never reports.
    """
    produced = set(_pull_request_checks())
    orphans = sorted(_required_contexts() - produced)
    assert not orphans, "required status checks that no pull-request job produces: " + ", ".join(
        repr(o) for o in orphans
    )


@pytest.mark.parametrize(
    "context",
    [
        "Trivy image CVE scan (compute)",
        "Trivy image CVE scan (instant-score)",
        "zizmor (workflow security lint)",
    ],
)
def test_the_security_gates_adr_0033_names_are_required(context: str) -> None:
    """ADR 0033 names zizmor and container-scan explicitly, so pin them.

    The generic test above would go quiet if someone moved one of these into
    ADVISORY_JOBS. These are the ones the ADR decided, and downgrading them is
    an ADR change, not a test edit.
    """
    assert context in _required_contexts()


# Every context required today. The two tests above compare the ruleset to the
# workflows and stay green if a context leaves both at once, so the required set
# could shrink with nothing to see. This list is the ratchet: dropping a gate is
# a deliberate edit here, in the same diff, and not a quiet consequence of
# deleting a job.
PINNED_REQUIRED_CONTEXTS = (
    "pipeline",
    "Secret scan (gitleaks)",
    "SAST (Semgrep)",
    "axe",
    "e2e",
    "Dependency audit (pip-audit + osv-scanner)",
    "Analyze (python)",
    "Analyze (actions)",
    "Analyze (javascript)",
    "standards-pin",
    "Trivy image CVE scan (compute)",
    "Trivy image CVE scan (instant-score)",
    "terraform fmt + validate",
    "zizmor (workflow security lint)",
    "Dependency review (PRs only)",
)

# A job-level `if:` on a required job is the sharpest form of this file's own
# subject. GitHub counts a skipped required check as satisfied, so a required
# job that does not run is a green gate that ran nothing. These conditions are
# true on every pull request, which is the only reason they are allowed.
ALWAYS_TRUE_ON_A_PULL_REQUEST = {
    "github.event_name == 'pull_request'",
}


def _ruleset() -> dict[str, Any]:
    return json.loads(RULESET.read_text())  # type: ignore[no-any-return]


@pytest.mark.parametrize("context", PINNED_REQUIRED_CONTEXTS)
def test_the_required_set_does_not_shrink_unnoticed(context: str) -> None:
    assert context in _required_contexts(), (
        f"{context!r} was a required status check and is not any more. If that is "
        "deliberate, remove it from PINNED_REQUIRED_CONTEXTS in the same change "
        "and say why in the pull request."
    )


def test_the_ruleset_is_actually_switched_on() -> None:
    """`_required_contexts` reads only the list of checks. It never looked at
    `enforcement`, so flipping the ruleset to "disabled" or "evaluate" left
    every test in this file green while nothing blocked anything. A required
    check inside a ruleset that is not enforcing is exactly the shape this file
    exists to catch, one level up from the checks themselves."""
    ruleset = _ruleset()

    assert ruleset["enforcement"] == "active", (
        f"the ruleset is {ruleset['enforcement']!r}; required checks in a ruleset "
        "that is not active block nothing"
    )
    assert ruleset["conditions"]["ref_name"]["include"] == ["refs/heads/main"], (
        "a ruleset that no longer targets main protects nothing"
    )
    rule_types = {rule["type"] for rule in ruleset["rules"]}
    assert "required_status_checks" in rule_types
    assert "pull_request" in rule_types, "review requirements are part of the same gate"


def test_no_required_job_can_skip_itself() -> None:
    """GitHub evaluates a required status check as satisfied when its job is
    skipped, so a job-level `if:` on a required job can turn it into a gate
    that reports success without running. The two live conditions are
    `github.event_name == 'pull_request'`, which is true whenever the check is
    being required at all."""
    required = _required_contexts()
    offenders: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        workflow = _load_yaml(path)
        if "pull_request" not in _triggers(workflow):
            continue
        for job_id, job in (workflow.get("jobs") or {}).items():
            if not isinstance(job, dict) or "if" not in job:
                continue
            if not any(name in required for name in _check_names(job_id, job)):
                continue
            condition = str(job["if"]).strip()
            if condition not in ALWAYS_TRUE_ON_A_PULL_REQUEST:
                offenders.append(f"{path.name}::{job_id} if: {condition!r}")
    assert not offenders, (
        "required jobs carrying a condition that is not known to hold on every "
        "pull request; a skip reads as a pass:\n  " + "\n  ".join(offenders)
    )


def test_no_workflow_producing_a_required_check_filters_on_paths() -> None:
    """Issue #289: `on.pull_request.paths` on a workflow that produces a
    required check leaves that check permanently pending on any pull request
    the filter excludes, which blocks the merge rather than gating it. The
    filters were removed from iac.yml and container-scan.yml and each carries a
    comment saying why. Nothing stopped them coming back."""
    offenders: list[str] = []
    required = _required_contexts()
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        workflow = _load_yaml(path)
        on = workflow.get(True, workflow.get("on"))
        if not isinstance(on, dict):
            continue
        pull_request = on.get("pull_request")
        if not isinstance(pull_request, dict):
            continue
        produces_required = any(
            name in required
            for job_id, job in (workflow.get("jobs") or {}).items()
            if isinstance(job, dict)
            for name in _check_names(job_id, job)
        )
        if not produces_required:
            continue
        for key in ("paths", "paths-ignore"):
            if key in pull_request:
                offenders.append(f"{path.name}: on.pull_request.{key} = {pull_request[key]!r}")
    assert not offenders, (
        "a path filter on a workflow that produces a required check (issue #289):\n  "
        + "\n  ".join(offenders)
    )
