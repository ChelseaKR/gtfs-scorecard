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
    assert tolerated == 1, (
        "pages.yml tolerates exactly one step's failure: the first upload attempt, "
        "which exists only so the second can run"
    )
    first = PAGES.index("id: upload")
    retry = PAGES.index("name: Upload the Pages artifact (second attempt)")
    assert first < retry
    assert "continue-on-error" not in PAGES[retry:], (
        "the second attempt must be able to fail the job; a retry that also "
        "tolerates its own failure publishes nothing and reports success"
    )
    assert "if: ${{ steps.upload.outcome == 'failure' }}" in PAGES, (
        "the retry must be conditioned on the first attempt's outcome, not run "
        "unconditionally or on always()"
    )


def test_the_deploy_waits_longer_than_the_actions_default_and_less_than_its_job() -> None:
    deploy_job = PAGES[PAGES.index("\n  deploy:\n") : PAGES.index("\n  production-smoke:\n")]
    bound = re.search(r'timeout: "(\d+)"', deploy_job)
    assert bound, "the deploy step declares no timeout, so it keeps the 10-minute default"
    timeout_ms = int(bound.group(1))
    assert timeout_ms > DEPLOY_PAGES_DEFAULT_TIMEOUT_MS, (
        "at the default the action cancels its own deployment after 10 minutes; "
        "run 34461157937 was canceled that way while the backend was still working"
    )
    job_bound = re.search(r"^    timeout-minutes: (\d+)$", deploy_job, re.MULTILINE)
    assert job_bound, "the deploy job declares no timeout-minutes"
    assert timeout_ms < int(job_bound.group(1)) * 60_000, (
        "a wait longer than the job that contains it is never reached: the job is "
        "killed first, and a killed job concludes `cancelled`, not `failure`"
    )
