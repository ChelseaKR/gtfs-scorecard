"""Post-checkout setup form and the download route (docs/program-plan.md).

Two routes on the program-bundle API, both stateless per request:

``POST /setup``
    The page a buyer lands on after Stripe Checkout posts here with the
    Checkout Session id and the program details (name, accent, logo, agency
    ids). The handler confirms with Stripe that the session is *paid* and
    that its one line item is one of this product's four prices (a paid
    checkout for anything else on the same Stripe account builds nothing),
    mints a bundle id, validates the request with the pipeline's own
    parse_request held to the agency cap of the price that was bought,
    records the session so a replayed form cannot dispatch twice, stores the
    capability row, dispatches report-bundle.yml, and for a subscription
    stores the request so the weekly refresh can re-dispatch it.

``GET /download/{bundle_id}``
    The link in the delivery email. Looks up the capability row, and if the
    archive exists, answers with a 302 to a presigned S3 URL that lives
    fifteen minutes. The emailed link is stable for thirty days; each click
    mints a fresh short-lived URL, so nothing long-lived is ever written into
    an email. A bundle still being rendered answers 202 with a plain page.

Payment is the only gate. There is no account and no password; the
capability in the email is the credential, the same posture as the alerts
confirm link. The setup route also refuses outright unless PAYMENTS_ENABLED
is "1", the same Terraform gate that decides whether the route exists.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

from common import (
    PLAN_AGENCY_CAPS,
    SUBSCRIPTION_PLANS,
    UpstreamError,
    bundle_row,
    checkout_plan,
    dispatch_bundle_workflow,
    html_response,
    json_response,
    payments_enabled,
    stripe_get,
    table,
    workflow_inputs,
)

from scorecard_pipeline.bundle import BundleError, new_bundle_id, parse_request

PRESIGN_SECONDS = 15 * 60
_SESSION_ID_MAX = 200


def _session_row(session_id: str, bundle_id: str, plan: str) -> dict[str, Any]:
    """Marks a Checkout Session as consumed. Shares the bundles table under a
    ``session#`` key so one conditional put is the whole idempotency check.
    No ``expires_at``: the claim must outlive the capability row, or a replay
    after 30 days would build a second bundle from one payment."""
    return {"bundle_id": f"session#{session_id}", "consumed_by": bundle_id, "plan": plan}


def _claim_session(bundles: Any, session_id: str, bundle_id: str, plan: str) -> bool:
    """Atomically claim the session; False if it was already used."""
    try:
        bundles.put_item(
            Item=_session_row(session_id, bundle_id, plan),
            ConditionExpression="attribute_not_exists(bundle_id)",
        )
    except Exception as err:  # boto3's ConditionalCheckFailedException, by name
        if "ConditionalCheckFailed" in type(err).__name__ or "ConditionalCheckFailed" in str(err):
            return False
        raise
    return True


class _Refused(Exception):
    """Carries the response to send instead of building anything.

    The checks in ``_paid_purchase`` each have their own status and their own
    sentence for the buyer, and every one of them means "nothing was built".
    Raising them keeps ``setup`` a list of steps rather than a ladder.
    """

    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__(str(response.get("statusCode")))
        self.response = response


def _paid_purchase(session_id: str) -> tuple[dict[str, Any], str, str]:
    """The Checkout Session, the price it was for, and the plan that price
    sells. Raises ``_Refused`` when the session was not a paid purchase of one
    of this product's four prices.

    Two reads, not one. That the session is *paid* says only that money moved
    on this Stripe account; what was *bought* is in the line items, and it is
    what decides both whether to build at all and how many agencies the buyer
    is entitled to.
    """
    try:
        session = stripe_get(f"/v1/checkout/sessions/{urllib.parse.quote(session_id, safe='')}")
    except UpstreamError as err:
        raise _Refused(
            json_response(502, {"ok": False, "error": "Could not confirm the payment yet."})
        ) from err
    if session.get("payment_status") != "paid":
        raise _Refused(
            json_response(402, {"ok": False, "error": "This checkout has not been paid."})
        )

    try:
        bought = checkout_plan(session_id)
    except UpstreamError as err:
        # Stripe is unreachable, or the restricted key cannot read line items.
        # Either way this is "not yet", never "build it anyway".
        raise _Refused(
            json_response(502, {"ok": False, "error": "Could not confirm the payment yet."})
        ) from err
    if bought is None:
        raise _Refused(
            json_response(
                403,
                {
                    "ok": False,
                    "error": "This checkout was not for a GTFS Scorecard report bundle, "
                    "so nothing was built.",
                },
            )
        )
    price, plan = bought
    return session, price, plan


def setup(event: dict[str, Any]) -> dict[str, Any]:
    if not payments_enabled():
        return json_response(
            503,
            {
                "ok": False,
                "error": "Setup is closed right now, so nothing was built. "
                "Your checkout has not been used; try again later.",
            },
        )
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
        session, price, plan = _paid_purchase(session_id)
    except _Refused as refused:
        return refused.response

    details = session.get("customer_details") or {}
    raw = {
        "bundle_id": new_bundle_id(),
        "program_name": form.get("program_name", ""),
        "accent": form.get("accent", ""),
        "logo": form.get("logo", ""),
        "agency_ids": form.get("agency_ids", ""),
        "deliver_to": form.get("deliver_to") or details.get("email") or "",
        "cadence": "monthly" if plan in SUBSCRIPTION_PLANS else "one_time",
    }
    try:
        # Validated before the session is claimed, so a list over the plan's
        # cap can be trimmed and sent again with the same checkout.
        request = parse_request(raw, max_agencies=PLAN_AGENCY_CAPS[plan])
    except BundleError as err:
        return json_response(400, {"ok": False, "error": str(err)})

    bundles = table("BUNDLES_TABLE")
    if not _claim_session(bundles, session_id, request.bundle_id, plan):
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
                # The refresh re-checks this against the configured prices, so
                # a row left over from test mode never builds in live mode.
                "price": price,
                "plan": plan,
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
