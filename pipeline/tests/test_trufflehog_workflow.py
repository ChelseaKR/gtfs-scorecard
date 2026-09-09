"""Structural contracts for the weekly full-history TruffleHog sweep.

Five properties of `.github/workflows/trufflehog.yml` decide whether that workflow is a
gate or a decoration, and none of them shows up as a red build when it breaks.

1. **Some lane reports the `unverified` tier.** TruffleHog sorts a finding into
   `verified` (it authenticated the credential against the live service), `unknown`
   (verification errored) and `unverified` (it asked, and the service said no). A
   credential that leaked and was later *revoked* -- the normal end state of a real
   incident, and the exact case a weekly history sweep exists to catch -- answers "no"
   and is therefore `unverified`. This job ran `--results=verified` until 2026-09-06,
   which could not fail on it. Measured on a throwaway clone with a real-shaped AWS key
   planted in one commit and deleted in the next: `--results=verified` and
   `--results=verified,unknown` both exited 0 reporting nothing; adding `unverified`
   exited 183.

2. **No lane spells its selection `--only-verified`.** Same hole, different name.

3. **Every detector the widened lane switches off stays armed in another lane**, Lob
   aside. Lob matches this repository's own pytest function names under every tier
   (ADR 0044) and no lane can usefully run it. The other four exclusions exist only
   because the widened tier surfaces committed third-party artefacts and synthetic test
   DSNs, and they are only safe while the verified-results lane still runs them.

4. **The action ref and the `version:` input name the same release.** The input selects
   the scanning image (`ghcr.io/trufflesecurity/trufflehog:${VERSION}`) and defaults to
   `latest`, so the SHA on `uses:` pins only the wrapper. This gate was pinned at v3.95.8
   and running whatever upstream had published most recently.

5. **`fetch-depth: 0` and the scan root survive.** Without the first the checkout is one
   commit deep and a "full-history" sweep becomes a one-commit scan reporting success;
   without the second the action can exit on its own "BASE and HEAD commits are the same"
   guard having scanned nothing.

The pin comment is a YAML comment and so is invisible to a YAML parser, so assertion 4
reads the file as text. See docs/decisions/0053-secret-scan-reports-every-result-tier.md.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "trufflehog.yml"

#: The tier a revoked credential lands in. Its absence is the defect.
REQUIRED_RESULT_TIER = "unverified"

#: Excluded from every lane on purpose (ADR 0044), so it needs no covering lane.
DETECTOR_WITH_NO_LANE = "Lob"


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), (
        f"{WORKFLOW} is missing. If the sweep was deliberately removed or replaced, update "
        "this test with the replacement rather than deleting it: an absent scan must be a "
        "decision, not a silence."
    )
    return WORKFLOW.read_text(encoding="utf-8")


def _scan_job() -> dict[str, Any]:
    workflow = cast(dict[str, Any], yaml.safe_load(_workflow_text()))
    return cast(dict[str, Any], workflow["jobs"]["trufflehog"])


def _lanes() -> list[str]:
    lanes = [
        str(step["with"]["extra_args"])
        for step in _scan_job()["steps"]
        if isinstance(step, dict) and "trufflesecurity/trufflehog@" in str(step.get("uses", ""))
    ]
    assert lanes, "no trufflehog step with `extra_args:`; this guard can no longer see the tiers"
    return lanes


def _result_tiers(lane: str) -> set[str]:
    match = re.search(r"--results=([\w,]+)", lane)
    return set(match.group(1).split(",")) if match else set()


def _excluded_detectors(lane: str) -> set[str]:
    match = re.search(r"--exclude-detectors=([\w,]+)", lane)
    return set(match.group(1).split(",")) if match else set()


def test_no_lane_restricts_itself_to_verified_findings_alone() -> None:
    for lane in _lanes():
        assert "--only-verified" not in lane, (
            "`--only-verified` cannot fail on a credential the provider has already revoked, "
            f"which is the case this sweep exists for. Offending args: {lane!r}"
        )
        assert re.search(r"--results=[\w,]+", lane), (
            f"expected an explicit `--results=` tier list, got {lane!r}"
        )


def test_some_lane_reports_the_unverified_tier() -> None:
    tiers = [sorted(_result_tiers(lane)) for lane in _lanes()]
    assert any(REQUIRED_RESULT_TIER in lane for lane in tiers), (
        f"no lane of this sweep reports `{REQUIRED_RESULT_TIER}` results (found {tiers}), so "
        "nothing here can fail on a credential that leaked and was then revoked"
    )


def test_every_detector_the_widened_lane_excludes_stays_armed_elsewhere() -> None:
    lanes = _lanes()
    widened = [lane for lane in lanes if REQUIRED_RESULT_TIER in _result_tiers(lane)]
    others = [lane for lane in lanes if REQUIRED_RESULT_TIER not in _result_tiers(lane)]

    needing_cover: set[str] = set()
    for lane in widened:
        needing_cover |= _excluded_detectors(lane)
    needing_cover.discard(DETECTOR_WITH_NO_LANE)

    for detector in sorted(needing_cover):
        assert any(detector not in _excluded_detectors(lane) for lane in others), (
            f"{detector} is excluded from the widened lane and from every other lane too, so "
            "nothing in this job can catch it any more. Keep the verified-results lane that "
            "leaves it armed."
        )


def test_the_verified_results_lane_still_runs_after_the_widened_lane_fails() -> None:
    steps = [
        step
        for step in _scan_job()["steps"]
        if isinstance(step, dict) and "trufflesecurity/trufflehog@" in str(step.get("uses", ""))
    ]
    assert len(steps) >= 2, (
        "the widened lane's detector exclusions are only safe while a second lane keeps them "
        "armed; that lane is gone"
    )
    covering = [
        step for step in steps if REQUIRED_RESULT_TIER not in str(step["with"]["extra_args"])
    ]
    assert covering, "no verified-results lane left to cover the widened lane's exclusions"
    for step in covering:
        assert "cancelled()" in str(step.get("if", "")), (
            "the covering lane must run under `if: ${{ !cancelled() }}`; without it a failure "
            "in the widened lane skips it and its verdict is never reported"
        )


def test_the_action_ref_and_the_version_input_name_the_same_release() -> None:
    text = _workflow_text()
    pinned = re.findall(r"trufflesecurity/trufflehog@[0-9a-f]{40}\s*#\s*v(\d+(?:\.\d+)*)", text)
    selected = re.findall(r"^\s*version:\s*\"?(\d+(?:\.\d+)*)\"?\s*$", text, flags=re.MULTILINE)

    assert pinned, "no SHA-pinned trufflehog ref carrying a `# vX.Y.Z` comment"
    assert selected, (
        "no `version:` input on any trufflehog step. The action then downloads `latest`, so the "
        "SHA pin above it pins only the wrapper and not the binary that actually scans."
    )
    assert len(pinned) == len(selected), (
        f"{len(pinned)} pinned trufflehog ref(s) but {len(selected)} `version:` input(s); every "
        "step needs its own pinned version"
    )
    for ref_version, input_version in zip(pinned, selected, strict=True):
        assert ref_version == input_version, (
            f"the action is pinned to v{ref_version} but `version: {input_version}` is what "
            f"downloads the scanner, so the bump to v{ref_version} changed nothing"
        )


def test_the_sweep_checks_out_the_whole_history_and_scans_the_whole_tree() -> None:
    steps = _scan_job()["steps"]
    checkout = next(
        step for step in steps if "actions/checkout@" in str(cast(Any, step).get("uses", ""))
    )
    assert checkout["with"]["fetch-depth"] == 0, (
        "`fetch-depth: 0` is missing from the checkout. actions/checkout then fetches a single "
        "commit and this full-history sweep silently becomes a one-commit scan that still "
        "reports success."
    )
    for step in steps:
        if "trufflesecurity/trufflehog@" in str(cast(Any, step).get("uses", "")):
            assert cast(dict[str, Any], step["with"]).get("path") == "./", (
                "the scan root is not `./`; with path, base and head all unset the action can "
                'exit on its own "BASE and HEAD commits are the same" guard having scanned '
                "nothing and still go green"
            )
