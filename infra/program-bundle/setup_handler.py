"""Post-checkout setup form and the download route (docs/program-plan.md).

Two routes on the program-bundle API, both stateless per request:

``POST /setup``
    The page a buyer lands on after Stripe Checkout posts here with the
    Checkout Session id and the program details (name, accent, logo, agency
    ids). The handler confirms with Stripe that the session is *paid*, mints
    a bundle id, validates the request with the pipeline's own parse_request,
    stores the capability row, records the session so a replayed form cannot
    dispatch twice, dispatches report-bundle.yml, and for a subscription
    stores the request so the weekly refresh can re-dispatch it.

``GET /download/{bundle_id}``
    The link in the delivery email. Looks up the capability row, and if the
    archive exists, answers with a 302 to a presigned S3 URL that lives
    fifteen minutes. The emailed link is stable for thirty days; each click
    mints a fresh short-lived URL, so nothing long-lived is ever written into
    an email. A bundle still being rendered answers 202 with a plain page.

Payment is the only gate. There is no account and no password; the
capability in the email is the credential, the same posture as the alerts
confirm link.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

from common import (
    UpstreamError,
    bundle_row,
    dispatch_bundle_workflow,
    html_response,
    json_response,
    stripe_get,
    table,
    workflow_inputs,
)

from scorecard_pipeline.bundle import BundleError, new_bundle_id, parse_request

PRESIGN_SECONDS = 15 * 60
_SESSION_ID_MAX = 200


def _cadence_for(session: dict[str, Any]) -> str:
    return "monthly" if session.get("mode") == "subscription" else "one_time"


def _session_row(session_id: str, bundle_id: str) -> dict[str, Any]:
    """Marks a Checkout Session as consumed. Shares the bundles table under a
    ``session#`` key so one conditional put is the whole idempotency check."""
    return {"bundle_id": f"session#{session_id}", "consumed_by": bundle_id}


def _claim_session(bundles: Any, session_id: str, bundle_id: str) -> bool:
    """Atomically claim the session; False if it was already used."""
    try:
        bundles.put_item(
            Item=_session_row(session_id, bundle_id),
            ConditionExpression="attribute_not_exists(bundle_id)",
        )
    except Exception as err:  # boto3's ConditionalCheckFailedException, by name
        if "ConditionalCheckFailed" in type(err).__name__ or "ConditionalCheckFailed" in str(err):
            return False
        raise
    return True


def setup(event: dict[str, Any]) -> dict[str, Any]:
    try:
        form = json.loads(event.get("body") or "{}")
    except ValueError:
        return json_response(400, {"ok": False, "error": "Could not read the form."})
    if not isinstance(form, dict):
        return json_response(400, {"ok": False, "error": "Could not read the form."})

    session_id = str(form.get("session_id") or "").strip()
    if not session_id or len(session_id) > _SESSION_ID_MAX or not session_id.startswith("cs_"):
        return json_response(400, {"ok": False, "error": "The checkout reference is missing."})

    try:
        session = stripe_get(f"/v1/checkout/sessions/{urllib.parse.quote(session_id, safe='')}")
    except UpstreamError:
        return json_response(502, {"ok": False, "error": "Could not confirm the payment yet."})
    if session.get("payment_status") != "paid":
        return json_response(402, {"ok": False, "error": "This checkout has not been paid."})

    details = session.get("customer_details") or {}
    raw = {
        "bundle_id": new_bundle_id(),
        "program_name": form.get("program_name", ""),
        "accent": form.get("accent", ""),
        "logo": form.get("logo", ""),
        "agency_ids": form.get("agency_ids", ""),
        "deliver_to": form.get("deliver_to") or details.get("email") or "",
        "cadence": _cadence_for(session),
    }
    try:
        request = parse_request(raw)
    except BundleError as err:
        return json_response(400, {"ok": False, "error": str(err)})

    bundles = table("BUNDLES_TABLE")
    if not _claim_session(bundles, session_id, request.bundle_id):
        return json_response(
            409, {"ok": False, "error": "This checkout already produced a bundle."}
        )
    bundles.put_item(Item=bundle_row(request.as_dict(), source="checkout", session_id=session_id))

    if request.cadence == "monthly" and session.get("subscription"):
        table("SUBSCRIPTIONS_TABLE").put_item(
            Item={
                "id": str(session["subscription"]),
                "status": "active",
                "customer": str(session.get("customer") or ""),
                "deliver_to": request.deliver_to,
                "request": json.dumps(request.as_dict()),
                "created_at": bundle_row(request.as_dict(), source="checkout")["created_at"],
            }
        )

    try:
        dispatch_bundle_workflow(workflow_inputs(request.as_dict()))
    except UpstreamError:
        return json_response(
            502,
            {
                "ok": False,
                "error": "Your order is recorded but the build could not start; "
                "you will hear from us by email.",
                "bundle_id": request.bundle_id,
            },
        )
    return json_response(200, {"ok": True, "bundle_id": request.bundle_id})


def download(bundle_id: str) -> dict[str, Any]:
    if not bundle_id or len(bundle_id) != 32 or not all(c in "0123456789abcdef" for c in bundle_id):
        return html_response(404, "Not found", "That download link is not valid.")
    row = table("BUNDLES_TABLE").get_item(Key={"bundle_id": bundle_id}).get("Item")
    if not row:
        return html_response(
            404, "Link expired", "That download link has expired or was never issued."
        )
    import boto3

    bucket = os.environ["ARTIFACTS_BUCKET"]
    key = f"program-bundles/{bundle_id}/bundle.zip"
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except Exception:  # NoSuchKey / 404 from head_object
        return html_response(
            202,
            "Still being prepared",
            "Your reports are still being generated. Try this link again in a few minutes.",
        )
    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ResponseContentDisposition": (
                f'attachment; filename="board-reports-{bundle_id[:8]}.zip"'
            ),
        },
        ExpiresIn=PRESIGN_SECONDS,
    )
    return {
        "statusCode": 302,
        "headers": {"Location": url, "Cache-Control": "no-store"},
        "body": "",
    }


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """API Gateway (HTTP API v2 payload) entrypoint."""
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = str(event.get("rawPath") or http.get("path") or "/")
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": json_response(204, {})["headers"], "body": ""}
    if method == "POST" and path.rstrip("/").endswith("/setup"):
        return setup(event)
    if method == "GET" and "/download/" in path:
        return download(path.rsplit("/download/", 1)[1].strip("/").lower())
    return json_response(404, {"ok": False, "error": "No such route."})
