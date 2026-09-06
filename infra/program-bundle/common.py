"""Shared pieces of the program-bundle Lambdas (docs/program-plan.md).

Three handlers share this module: the post-checkout setup form
(setup_handler.py), the Stripe webhook (webhook_handler.py), and the weekly
refresh for subscriptions (refresh_handler.py). Everything here is standard
library at import time; boto3 is imported lazily inside the functions that
touch AWS so the pure logic runs under pytest with no account.

The deploy bundles the scorecard_pipeline package alongside these files
(infra/program-bundle/main.tf), the same packaging as infra/submit, so
request validation is the pipeline's own parse_request and not a second copy.

Environment (set by Terraform):
  GITHUB_TOKEN          fine-scoped token with actions: write on the repo
  GITHUB_REPO           owner/name, e.g. ChelseaKR/gtfs-scorecard
  WORKFLOW_FILE         report-bundle.yml
  WORKFLOW_REF          branch to dispatch on, default main
  STRIPE_SECRET_KEY     restricted key: read checkout sessions only
  STRIPE_WEBHOOK_SECRET signing secret of the one webhook endpoint
  SUBSCRIPTIONS_TABLE   DynamoDB table of subscriptions (hash: id)
  BUNDLES_TABLE         DynamoDB table of bundle capabilities (hash: bundle_id)
  ARTIFACTS_BUCKET      where report-bundle.yml puts program-bundles/<id>/bundle.zip
  ALLOW_ORIGIN          CORS origin of the setup form (never '*')
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_ORIGIN = "https://gtfsscorecard.org"
GITHUB_API = "https://api.github.com"
STRIPE_API = "https://api.stripe.com"
# Kept in step with scorecard_pipeline.bundle.DOWNLOAD_DAYS and the S3
# lifecycle rule for program-bundles/ in infra/artifacts/main.tf.
DOWNLOAD_DAYS = 30
# Stripe's own recommended replay tolerance for the signed timestamp.
SIGNATURE_TOLERANCE_SECONDS = 300


class UpstreamError(RuntimeError):
    """A GitHub or Stripe call failed; the message is safe to log, not to show."""


# ---------------------------------------------------------------------------
# HTTP responses
# ---------------------------------------------------------------------------


def cors_headers(content_type: str = "application/json") -> dict[str, str]:
    return {
        "Content-Type": content_type,
        "Access-Control-Allow-Origin": os.environ.get("ALLOW_ORIGIN", DEFAULT_ORIGIN),
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def json_response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status, "headers": cors_headers(), "body": json.dumps(body)}


def html_response(status: int, title: str, message: str) -> dict[str, Any]:
    page = (
        f"<!doctype html><meta charset=utf-8><title>{title}</title>"
        "<body style='font-family:system-ui;max-width:34rem;margin:4rem auto;padding:0 1rem'>"
        f"<h1>{title}</h1><p>{message}</p>"
        "<p><a href='https://gtfsscorecard.org/'>Back to GTFS Scorecard</a></p>"
    )
    return {"statusCode": status, "headers": cors_headers("text/html"), "body": page}


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def epoch_in(days: int) -> int:
    return int(time.time()) + days * 86400


# ---------------------------------------------------------------------------
# GitHub: dispatch the fulfilment workflow
# ---------------------------------------------------------------------------


def _request(
    method: str, url: str, headers: dict[str, str], payload: dict[str, Any] | None = None
) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - api.github.com / api.stripe.com only
    for key, value in headers.items():
        req.add_header(key, value)
    req.add_header("User-Agent", "gtfs-scorecard-program-bundle")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed hosts only
            raw = resp.read().decode()
    except urllib.error.HTTPError as err:
        raise UpstreamError(f"{method} {url} -> HTTP {err.code}") from err
    except (urllib.error.URLError, OSError) as err:
        raise UpstreamError(f"{method} {url} failed: {err}") from err
    return json.loads(raw) if raw.strip() else {}


def dispatch_bundle_workflow(inputs: dict[str, str]) -> None:
    """POST a workflow_dispatch for report-bundle.yml with the given inputs.

    GitHub returns 204 with no body on success. Inputs are the workflow's
    declared inputs and nothing else; the workflow re-validates every one.
    """
    repo = os.environ["GITHUB_REPO"]
    workflow = os.environ.get("WORKFLOW_FILE", "report-bundle.yml")
    ref = os.environ.get("WORKFLOW_REF", "main")
    _request(
        "POST",
        f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow}/dispatches",
        {
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
        },
        {"ref": ref, "inputs": inputs},
    )


def workflow_inputs(request: dict[str, Any]) -> dict[str, str]:
    """The workflow_dispatch inputs for a stored or validated request dict."""
    agency_ids = request.get("agency_ids") or []
    if isinstance(agency_ids, list | tuple):
        agency_ids = ",".join(str(a) for a in agency_ids)
    return {
        "bundle_id": str(request["bundle_id"]),
        "program_name": str(request["program_name"]),
        "accent": str(request.get("accent") or ""),
        "logo": str(request.get("logo") or ""),
        "agency_ids": str(agency_ids),
        "deliver_to": str(request["deliver_to"]),
        "cadence": str(request.get("cadence") or "one_time"),
    }


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------


def stripe_get(path: str) -> dict[str, Any]:
    """GET one Stripe object with the restricted secret key."""
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        raise UpstreamError("STRIPE_SECRET_KEY is not configured")
    out = _request("GET", f"{STRIPE_API}{path}", {"Authorization": f"Bearer {key}"})
    return out if isinstance(out, dict) else {}


def verify_stripe_signature(
    payload: bytes, header: str, secret: str, *, now: int | None = None
) -> bool:
    """Check a Stripe-Signature header against the raw body.

    Stripe signs ``"{t}.{payload}"`` with HMAC-SHA256 and sends
    ``t=<unix>,v1=<hex>[,v1=<hex>...]``. Any v1 that matches within the
    replay tolerance is accepted; anything else is refused, including a
    header with no timestamp, an unparseable timestamp, or an empty secret.
    """
    if not secret or not header:
        return False
    timestamp = ""
    candidates: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            candidates.append(value)
    if not timestamp.isdigit() or not candidates:
        return False
    current = int(time.time()) if now is None else now
    if abs(current - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in candidates)


# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------


def table(env_name: str) -> Any:
    import boto3

    region = os.environ.get("AWS_REGION", "us-west-2")
    return boto3.resource("dynamodb", region_name=region).Table(os.environ[env_name])


def bundle_row(request: dict[str, Any], *, source: str, session_id: str = "") -> dict[str, Any]:
    """The capability row for one bundle: who it is for, when it expires."""
    return {
        "bundle_id": request["bundle_id"],
        "deliver_to": request["deliver_to"],
        "program_name": request["program_name"],
        "source": source,
        "session_id": session_id,
        "created_at": now_iso(),
        "expires_at": epoch_in(DOWNLOAD_DAYS),
    }
