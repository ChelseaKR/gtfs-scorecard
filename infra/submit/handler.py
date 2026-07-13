"""Serverless handler for the self-serve agency submission form.

The roadmap's Year 1 onboarding path (docs/roadmap.md). A web form POSTs a
feed; this opens a pull request that adds a registry intake entry, for a human
to review and merge. All validation and block rendering live in the tested
pipeline core (scorecard_pipeline.submissions); this file only does the GitHub
API conversation, so the deployable surface stays small.

Packaging: the deploy bundles the scorecard_pipeline package alongside this
handler (see infra/submit/main.tf). Only the standard library is used here so
the Lambda needs no third-party HTTP client.

Environment:
  GITHUB_TOKEN          fine-scoped token (contents + pull_requests: write)
  GITHUB_REPO           owner/name, e.g. chelseakr/gtfs-scorecard
  BASE_BRANCH           default "main"
  ALLOW_ORIGIN          CORS origin for the form, default the production site
  SUBMIT_SHARED_SECRET  if set, requests must send a matching X-Submit-Token
                        header (the form's only defense against an open,
                        token-backed PR-creating endpoint being driven for spam)
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_ORIGIN = "https://gtfsscorecard.org"

from scorecard_pipeline.agencies import AgencyConfigError
from scorecard_pipeline.submissions import build_submission

API = "https://api.github.com"
INTAKE_PATH = "registry/intake.yaml"
IDS_URL = "https://gtfsscorecard.org/api/v1/ids.json"


def _gh(method: str, path: str, token: str, payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "gtfs-scorecard-submit")
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed api.github.com
        return json.loads(resp.read().decode())


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": os.environ.get("ALLOW_ORIGIN", DEFAULT_ORIGIN),
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }


def _tracked_ids() -> set[str]:
    """Return published ids across the whole registry, best-effort.

    The intake shard alone cannot detect a duplicate already moved into a
    curated shard. The public identity endpoint supplies that complete set;
    human review remains the backstop if the read is unavailable or malformed.
    """
    req = urllib.request.Request(IDS_URL, headers={"User-Agent": "gtfs-scorecard-submit"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed project URL
            payload = json.loads(resp.read().decode())
    except (OSError, UnicodeDecodeError, ValueError):
        return set()
    if not isinstance(payload, dict) or not isinstance(payload.get("agencies"), list):
        return set()
    return {
        agency_id
        for agency in payload["agencies"]
        if isinstance(agency, dict)
        and isinstance((agency_id := agency.get("id")), str)
        and agency_id
    }


def _open_pull_request(form: dict[str, str]) -> str:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPO"]
    base = os.environ.get("BASE_BRANCH", "main")

    current = _gh("GET", f"/repos/{repo}/contents/{INTAKE_PATH}?ref={base}", token)
    if "content" not in current:
        raise RuntimeError("registry intake is too large to read inline from the API")
    existing_yaml = base64.b64decode(current["content"]).decode()

    submission = build_submission(form, existing_yaml, known_ids=_tracked_ids())

    head = _gh("GET", f"/repos/{repo}/git/ref/heads/{base}", token)
    _gh(
        "POST",
        f"/repos/{repo}/git/refs",
        token,
        {"ref": f"refs/heads/{submission.branch}", "sha": head["object"]["sha"]},
    )
    _gh(
        "PUT",
        f"/repos/{repo}/contents/{INTAKE_PATH}",
        token,
        {
            "message": submission.commit_message,
            "content": base64.b64encode(submission.file_content.encode()).decode(),
            "branch": submission.branch,
            "sha": current["sha"],
        },
    )
    pr = _gh(
        "POST",
        f"/repos/{repo}/pulls",
        token,
        {
            "title": submission.pr_title,
            "body": submission.pr_body,
            "head": submission.branch,
            "base": base,
        },
    )
    return str(pr["html_url"])


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda function-URL entrypoint."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    if method == "OPTIONS":
        return _response(204, {})

    # When a shared secret is configured, this token-backed PR-creating endpoint
    # requires it; without it, anyone could drive the function to spam branches.
    secret = os.environ.get("SUBMIT_SHARED_SECRET")
    if secret:
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        provided = headers.get("x-submit-token", "")
        if not hmac.compare_digest(provided, secret):
            return _response(401, {"ok": False, "error": "Unauthorized."})

    try:
        form = json.loads(event.get("body") or "{}")
    except ValueError:
        return _response(400, {"ok": False, "error": "Could not read the submission."})

    try:
        pr_url = _open_pull_request(form)
    except AgencyConfigError as exc:
        return _response(400, {"ok": False, "error": str(exc)})
    except (urllib.error.HTTPError, RuntimeError) as exc:
        return _response(502, {"ok": False, "error": f"Upstream error: {exc}"})
    return _response(200, {"ok": True, "pr_url": pr_url})
