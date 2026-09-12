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
    an email. A bundle still being rendered answers 202 with a plain page. A
    row past its own ``expires_at`` answers "expired" on that fact, not on
    whether the object is there: the S3 lifecycle rule deletes the archive on
    the day and the DynamoDB TTL sweep can lag it by two, and in that window
    "the object is missing" would otherwise read as "still being prepared".

Payment is the only gate. There is no account and no password; the
capability in the email is the credential, the same posture as the alerts
confirm link. The setup route also refuses outright unless PAYMENTS_ENABLED
is "1", the same Terraform gate that decides whether the route exists.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from dataclasses import replace
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


def _session_key(session_id: str) -> str:
    return f"session#{session_id}"


def _session_row(session_id: str, bundle_id: str, plan: str) -> dict[str, Any]:
    """Marks a Checkout Session as consumed. Shares the bundles table under a
    ``session#`` key so one conditional put is the whole idempotency check.
    No ``expires_at``: the claim must outlive the capability row, or a replay
    after 30 days would build a second bundle from one payment.

    ``dispatched`` starts False and is set True only once GitHub has accepted
    the workflow_dispatch. The claim therefore records two different facts --
    "this payment is spoken for" and "a build was actually started" -- so a
    second submission after a failed dispatch can finish the order instead of
    being told a bundle exists that does not.
    """
    return {
        "bundle_id": _session_key(session_id),
        "consumed_by": bundle_id,
        "plan": plan,
        "dispatched": False,
    }


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


def _mark_dispatched(bundles: Any, session_id: str) -> None:
    """Record that the build for this session really started."""
    bundles.update_item(
        Key={"bundle_id": _session_key(session_id)},
        UpdateExpression="SET #d = :d",
        ExpressionAttributeNames={"#d": "dispatched"},
        ExpressionAttributeValues={":d": True},
    )


def _has_expired(expires_at: Any) -> bool:
    """True only when the row carries a readable epoch that has passed.

    An unreadable or absent ``expires_at`` is not evidence of expiry, so it
    reads as "not expired" and the object decides -- the same rule the rest
    of this module follows: a value that could not be read is never turned
    into a fact about the buyer's order.
    """
    if isinstance(expires_at, bool):
        return False
    if isinstance(expires_at, int | float):
        return int(expires_at) <= int(time.time())
    text = str(expires_at or "").strip()
    return text.isdigit() and int(text) <= int(time.time())


def _unfinished_bundle_id(bundles: Any, session_id: str) -> str:
    """The bundle id of a claim whose build never started, else "".

    Only an explicit ``dispatched: False`` counts. A claim written before this
    field existed, or one whose Lambda died after calling GitHub, has no such
    record, and re-dispatching on a guess would build a second time from one
    payment. Absence of the flag is not evidence of a failed dispatch.
    """
    row = bundles.get_item(Key={"bundle_id": _session_key(session_id)}).get("Item") or {}
    if row.get("dispatched") is not False:
        return ""
    return str(row.get("consumed_by") or "")


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
        # 404 is not an outage. Stripe is telling us this reference does not
        # exist on this account and never will -- a mistyped or truncated
        # address, or a test-mode id read with the live key. "Could not
        # confirm yet" would invite a buyer to retry that forever.
        if err.status == 404:
            raise _Refused(
                json_response(
                    404,
                    {
                        "ok": False,
                        "error": "That checkout reference is not one Stripe recognises. Open the "
                        "page Stripe sent you to after paying, address and all. If you have lost "
                        "it, reply to the receipt Stripe emailed you rather than paying again.",
                    },
                )
            ) from err
        raise _Refused(
            json_response(502, {"ok": False, "error": "Could not confirm the payment yet."})
        ) from err
    if session.get("payment_status") != "paid":
        # Not always "you did not pay". A payment method that settles later
        # (a bank debit, say) leaves the session unpaid at the moment Stripe
        # redirects here, and the buyer is looking at a completed checkout.
        # The message has to fit both readers, and must not send anyone back
        # to pay a second time.
        raise _Refused(
            json_response(
                402,
                {
                    "ok": False,
                    "error": "Stripe has not settled this checkout yet, so nothing was built. "
                    "If you paid by a method that clears over a day or two, keep this page's "
                    "web address and open it again once the receipt arrives. Do not pay again.",
                },
            )
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


def _record_subscription(session: dict[str, Any], request: Any, *, price: str, plan: str) -> None:
    """Store what the weekly refresh needs, for a subscription purchase."""
    if request.cadence != "monthly" or not session.get("subscription"):
        return
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
        # The session is spoken for. Whether a build actually started decides
        # what to say: answering "this checkout already produced a bundle" to
        # someone whose first attempt died before the dispatch is both false
        # and a dead end, because the form is the only way they can reach us.
        unfinished = _unfinished_bundle_id(bundles, session_id)
        if not unfinished:
            return json_response(
                409, {"ok": False, "error": "This checkout already produced a bundle."}
            )
        # Finish the earlier order under its own bundle id, so one payment
        # still yields exactly one bundle and one download link.
        request = replace(request, bundle_id=unfinished)
    bundles.put_item(Item=bundle_row(request.as_dict(), source="checkout", session_id=session_id))

    _record_subscription(session, request, price=price, plan=plan)

    try:
        dispatch_bundle_workflow(workflow_inputs(request.as_dict()))
    except UpstreamError as err:
        # A paid order that never started a build is the one failure nobody
        # else can see: the workflow leaves no run, and the buyer is told to
        # wait. Print it so CloudWatch holds the session and bundle ids, and
        # leave the claim's `dispatched` False so a second submission of the
        # same form finishes the order instead of being refused.
        print(
            json.dumps(
                {
                    "event": "dispatch_failed",
                    "session_id": session_id,
                    "bundle_id": request.bundle_id,
                    "plan": plan,
                    "deliver_to": request.deliver_to,
                    "error": str(err),
                }
            )
        )
        return json_response(
            502,
            {
                "ok": False,
                "error": "Your order is recorded but the build could not start. "
                "Nothing was charged twice. Send this form again in a few minutes and it "
                "will pick up the same order; if it keeps failing, reply to the receipt "
                "Stripe emailed you.",
                "bundle_id": request.bundle_id,
            },
        )
    _mark_dispatched(bundles, session_id)
    return json_response(200, {"ok": True, "bundle_id": request.bundle_id})


def download(bundle_id: str) -> dict[str, Any]:
    if not bundle_id or len(bundle_id) != 32 or not all(c in "0123456789abcdef" for c in bundle_id):
        return html_response(404, "Not found", "That download link is not valid.")
    row = table("BUNDLES_TABLE").get_item(Key={"bundle_id": bundle_id}).get("Item")
    if not row:
        return html_response(
            404, "Link expired", "That download link has expired or was never issued."
        )
    # DynamoDB's TTL sweep is best-effort and can lag its deadline by up to two
    # days, while the S3 lifecycle rule deletes the archive on the day. Between
    # the two, an expired bundle has a row and no object -- which looks exactly
    # like one still being rendered. Read the row's own expiry rather than
    # inferring the state from the missing object, or a buyer past thirty days
    # is told to keep waiting for a file that was deleted.
    if _has_expired(row.get("expires_at")):
        return html_response(
            404,
            "Link expired",
            "That download link has expired. Bundles are kept for 30 days; "
            "reply to the email it came in and it can be rebuilt.",
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
            "Your reports are still being generated. Try this link again in a few minutes. "
            "If this page still says the same thing an hour from now, the build did not "
            "finish: reply to the receipt Stripe emailed you and quote "
            f"{bundle_id[:8]}, and it will be rebuilt or refunded.",
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
