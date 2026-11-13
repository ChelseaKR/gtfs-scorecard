"""The publish must survive a Pages platform blip, and must still be able to fail.

Two scheduled publish cycles were lost in six days to the platform rather than
to anything this repository produced: run 34245244731 (2026-09-08) uploaded the
whole 204 MB artifact and died on `Failed to FinalizeArtifact ... (403)`, and
run 34461157937 (2026-09-10) watched a healthy backend report `updating_pages`
for the action's full 10-minute default and then *canceled its own
deployment*. In both the refreshed data reached S3 and the site kept serving the
previous generation until the next cycle.

The repair is one retry on the upload and a longer wait on the deploy. Both are
the kind of change that quietly turns a gate into a decoration, so the shape is
asserted here: exactly one tolerated failure, tied to a second attempt that can
itself fail, and a wait that stays inside the job that contains it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

# The action's own default, from actions/deploy-pages' action.yml.
DEPLOY_PAGES_DEFAULT_TIMEOUT_MS = 600_000


def test_the_pages_artifact_upload_is_retried_exactly_once() -> None:
    uploads = re.findall(r"uses: actions/upload-pages-artifact@(\S+)", PAGES)
    assert len(uploads) == 2, "the upload is attempted once and retried once"
    assert uploads[0] == uploads[1], "both attempts must run the same pinned action"
    assert PAGES.count("path: _site") == 2, "both attempts must upload the same directory"


def test_only_the_first_upload_attempt_may_tolerate_its_own_failure() -> None:
    """A tolerated failure with nothing after it is a step that cannot fail."""
    tolerated = PAGES.count("continue-on-error: true")
    assert tolerated == 2, (
        "pages.yml tolerates exactly two steps' failures: the first upload attempt "
        "and the first deploy attempt, each of which exists only so a second can run"
    )
    first = PAGES.index("id: upload")
    retry = PAGES.index("name: Upload the Pages artifact (second attempt)")
    assert first < retry
    assert "continue-on-error" not in PAGES[retry : PAGES.index("\n  deploy:\n")], (
        "the second attempt must be able to fail the job; a retry that also "
        "tolerates its own failure publishes nothing and reports success"
    )
    assert "if: ${{ steps.upload.outcome == 'failure' }}" in PAGES, (
        "the retry must be conditioned on the first attempt's outcome, not run "
        "unconditionally or on always()"
    )


def _deploy_job() -> str:
    return PAGES[PAGES.index("\n  deploy:\n") : PAGES.index("\n  production-smoke:\n")]


def test_the_deploy_timeout_is_the_honest_ceiling_and_fits_two_attempts() -> None:
    """The action clamps `timeout` to 600000 ms; a larger value only lies."""
    deploy_job = _deploy_job()
    bounds = [int(m) for m in re.findall(r'timeout: "(\d+)"', deploy_job)]
    assert len(bounds) == 2, "both deploy attempts declare their timeout"
    assert all(b == DEPLOY_PAGES_DEFAULT_TIMEOUT_MS for b in bounds), (
        "deploy-pages clamps `timeout` to 600000 ms (the 2026-11-10 log: 'timeout "
        "set to the maximum of 600000 milliseconds'); any other value is a comment "
        "that is not true"
    )
    wait = re.search(r"sleep (\d+)", deploy_job)
    assert wait, "the retry must wait before starting a fresh deployment"
    worst_case_s = sum(bounds) // 1000 + int(wait.group(1))
    job_bound = re.search(r"^    timeout-minutes: (\d+)$", deploy_job, re.MULTILINE)
    assert job_bound, "the deploy job declares no timeout-minutes"
    assert worst_case_s < int(job_bound.group(1)) * 60, (
        "two attempts plus the wait must fit inside the job, or the job is killed "
        "and concludes `cancelled`, not `failure`"
    )


def test_the_deploy_is_retried_once_after_a_delay_and_can_still_fail() -> None:
    deploy_job = _deploy_job()
    assert deploy_job.count("uses: actions/deploy-pages@") == 2
    pins = re.findall(r"uses: actions/deploy-pages@([0-9a-f]{40})", deploy_job)
    assert len(pins) == 2 and pins[0] == pins[1], "both attempts run the same SHA-pinned action"
    first = deploy_job.index("id: deployment\n")
    wait = deploy_job.index("sleep ")
    retry = deploy_job.index("id: deployment_retry")
    assert first < wait < retry
    assert deploy_job.count("continue-on-error: true") == 1
    assert deploy_job.index("continue-on-error: true") < wait
    assert "continue-on-error" not in deploy_job[retry:], (
        "the second deploy must be able to fail the job: it fails only if both fail"
    )
    assert deploy_job.count("if: ${{ steps.deployment.outcome == 'failure' }}") == 2, (
        "the wait and the retry are conditioned on the first attempt's outcome"
    )
    assert (
        "steps.deployment_retry.outputs.page_url || steps.deployment.outputs.page_url" in deploy_job
    )
