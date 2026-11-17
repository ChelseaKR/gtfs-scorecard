"""Serverless handler for the self-serve agency submission form.

The roadmap's Year 1 onboarding path (docs/roadmap.md). A web form POSTs a
feed; this opens a pull request that adds a registry intake entry, for a human
to review and merge. All validation and block rendering live in the tested
pipeline core (scorecard_pipeline.submissions); this file only does the GitHub
API conversation, so the deployable surface stays small.

Packaging: the deploy bundles the scorecard_pipeline package alongside this
handler (see infra/submit/main.tf). Only the standard library is used here so
the Lambda needs no third-party HTTP client.

Order of checks, cheapest and most local first (ADR 0079): body size, JSON
shape, every field against the form's rules, the daily limits, and only then
any call that uses the GitHub token. A request that fails an earlier check
never reaches a later one.

Environment:
  GITHUB_TOKEN          fine-scoped token (contents + pull_requests: write)
  GITHUB_REPO           owner/name, e.g. chelseakr/gtfs-scorecard
  BASE_BRANCH           default "main"
  ALLOW_ORIGIN          CORS origin for the form, default the production site
  SUBMIT_SHARED_SECRET  if set, requests must send a matching X-Submit-Token
                        header
  RATELIMIT_TABLE       DynamoDB table for the daily limits (shared with
                        infra/alerts and infra/instant-score; this endpoint
                        uses its own "submit#" key prefix). Required: with no
                        table, or a table that cannot be reached, submissions
                        are refused rather than accepted uncounted.
  SUBMIT_CLIENT_DAILY_CAP  submissions one client may make per UTC day (default 3)
  SUBMIT_GLOBAL_DAILY_CAP  submissions accepted from everyone per UTC day (default 20)
  AWS_REGION            provided by Lambda
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_ORIGIN = "https://gtfsscorecard.org"

from scorecard_pipeline.agencies import AgencyConfigError
from scorecard_pipeline.submissions import build_submission, checked_entry

log = logging.getLogger(__name__)

# The largest request body read. A complete submission with every field at its
# length limit, in a script that takes several bytes per character, is under
# 7 KB; anything larger is not a form post.
MAX_BODY_BYTES = 8 * 1024
# Daily limits, counted per UTC day in the rate-limit table. Each accepted
# request opens a pull request under the maintainer's account and starts the
# repository's pull-request checks, so the numbers are sized for a form that
# sees a few real submissions a week, not for throughput.
DEFAULT_CLIENT_DAILY_CAP = 3
DEFAULT_GLOBAL_DAILY_CAP = 20
_DAY_SECONDS = 86400
MANUAL_PATH = "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/add-your-agency.md"

API = "https://api.github.com"
INTAKE_PATH = "registry/intake.yaml"
IDS_URL = "https://gtfsscorecard.org/api/v1/ids.json"
# Names the scorecard and links to the fetcher page (ADR 0075).
SUBMIT_USER_AGENT = "gtfs-scorecard submit (+https://gtfsscorecard.org/fetcher/)"


def _gh(method: str, path: str, token: str, payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", SUBMIT_USER_AGENT)
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
    req = urllib.request.Request(IDS_URL, headers={"User-Agent": SUBMIT_USER_AGENT})
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


class _TooLarge(Exception):
    """The request body is larger than any real submission."""


class SubmissionsPaused(RuntimeError):
    """The daily limits could not be checked, so nothing was opened."""


class LimitReached(RuntimeError):
    """A daily limit is used up; the message says which and what to do instead."""


def _cap(name: str, default: int) -> int:
    """A positive whole number from the environment, or the default."""
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _limits_table() -> Any:
    """The shared rate-limit table. Raises SubmissionsPaused when unconfigured."""
    name = os.environ.get("RATELIMIT_TABLE")
    if not name:
        raise SubmissionsPaused("no rate-limit table is configured")
    import boto3  # noqa: PLC0415 - lazy; provided by the Lambda runtime

    region = os.environ.get("AWS_REGION", "us-west-2")
    return boto3.resource("dynamodb", region_name=region).Table(name)


def _take(table: Any, key: str, cap: int, expires_at: int) -> bool:
    """Count one request against ``key`` unless it is already at ``cap``.

    One conditional write, so two requests arriving together cannot both take
    the last place. Returns False when the cap was already reached; any other
    failure propagates and the caller refuses the request.
    """
    try:
        table.update_item(
            Key={"key": key},
            UpdateExpression="ADD #c :one SET expires_at = if_not_exists(expires_at, :exp)",
            ConditionExpression="attribute_not_exists(#c) OR #c < :cap",
            ExpressionAttributeNames={"#c": "count"},
            ExpressionAttributeValues={":one": 1, ":cap": cap, ":exp": expires_at},
        )
    except Exception as exc:
        error = getattr(exc, "response", None)
        code = error.get("Error", {}).get("Code") if isinstance(error, dict) else None
        if code == "ConditionalCheckFailedException":
            return False
        raise
    return True


def _client_key(event: dict[str, Any], day: str) -> str:
    """A per-day key for the calling client that does not store its address.

    The address is hashed together with the day, so the stored key cannot be
    matched to the same client on another day, and it expires with the row.
    A request with no source address shares one key with every other such
    request, so leaving the address out is not a way around the limit.
    """
    ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")
    source = ip if isinstance(ip, str) and ip else "unknown"
    digest = hashlib.sha256(f"{day}|{source}".encode()).hexdigest()[:32]
    return f"submit#client#{day}#{digest}"


def _claim_daily_quota(event: dict[str, Any], now: float | None = None) -> None:
    """Count this request against the per-client and the global daily limit.

    Raises LimitReached when either is used up, and SubmissionsPaused when the
    limits cannot be checked at all. The client limit is taken first, so one
    client that has used its own allowance does not also use up everyone's.
    """
    moment = time.time() if now is None else now
    day = time.strftime("%Y-%m-%d", time.gmtime(moment))
    # Rows outlive their day by one more, then DynamoDB's TTL removes them.
    expires_at = (int(moment) // _DAY_SECONDS + 2) * _DAY_SECONDS
    try:
        table = _limits_table()
        client_ok = _take(
            table,
            _client_key(event, day),
            _cap("SUBMIT_CLIENT_DAILY_CAP", DEFAULT_CLIENT_DAILY_CAP),
            expires_at,
        )
        if not client_ok:
            raise LimitReached(
                "This form accepts a few submissions a day from one place, and that limit "
                f"is used up. Try again tomorrow, or add the agency yourself: {MANUAL_PATH}"
            )
        global_ok = _take(
            table,
            f"submit#all#{day}",
            _cap("SUBMIT_GLOBAL_DAILY_CAP", DEFAULT_GLOBAL_DAILY_CAP),
            expires_at,
        )
    except (LimitReached, SubmissionsPaused):
        raise
    except Exception as exc:
        # The type is logged, never the message: a client error can quote the request.
        log.error("submission limits could not be checked: %s", type(exc).__name__)
        raise SubmissionsPaused("the rate-limit table could not be reached") from exc
    if not global_ok:
        raise LimitReached(
            "The form has taken as many submissions as it accepts in one day. "
            f"Try again tomorrow, or add the agency yourself: {MANUAL_PATH}"
        )


def _read_form(event: dict[str, Any]) -> dict[str, str]:
    """The request body as validated form fields.

    Raises ``_TooLarge`` for an oversized body and AgencyConfigError (one plain
    sentence) for anything that is not a well-formed submission.
    """
    body = event.get("body") or ""
    if not isinstance(body, str):
        raise AgencyConfigError("Could not read the submission.")
    # Base64 grows a body by a third; compare the encoded form against the
    # matching ceiling before decoding anything.
    encoded = bool(event.get("isBase64Encoded"))
    ceiling = (MAX_BODY_BYTES * 4) // 3 + 4 if encoded else MAX_BODY_BYTES
    if len(body) > ceiling or len(body.encode("utf-8", "surrogatepass")) > ceiling:
        raise _TooLarge
    if encoded:
        try:
            raw = base64.b64decode(body, validate=True)
        except (binascii.Error, ValueError):
            raise AgencyConfigError("Could not read the submission.") from None
        if len(raw) > MAX_BODY_BYTES:
            raise _TooLarge
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise AgencyConfigError("Could not read the submission.") from None
    try:
        form = json.loads(body or "{}")
    except (ValueError, RecursionError):
        raise AgencyConfigError("Could not read the submission.") from None
    fields, _entry = checked_entry(form)
    return fields


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
        form = _read_form(event)
    except _TooLarge:
        return _response(413, {"ok": False, "error": "That submission is too large."})
    except AgencyConfigError as exc:
        return _response(400, {"ok": False, "error": str(exc)})

    # Only a well-formed submission is counted, and it is counted before the
    # GitHub token is used for anything.
    try:
        _claim_daily_quota(event)
    except LimitReached as exc:
        return _response(429, {"ok": False, "error": str(exc)})
    except SubmissionsPaused:
        return _response(
            503,
            {
                "ok": False,
                "error": "Online submission is paused right now. You can add the agency "
                f"yourself: {MANUAL_PATH}",
            },
        )

    try:
        pr_url = _open_pull_request(form)
    except AgencyConfigError as exc:
        return _response(400, {"ok": False, "error": str(exc)})
    except (urllib.error.HTTPError, RuntimeError) as exc:
        return _response(502, {"ok": False, "error": f"Upstream error: {exc}"})
    return _response(200, {"ok": True, "pr_url": pr_url})
