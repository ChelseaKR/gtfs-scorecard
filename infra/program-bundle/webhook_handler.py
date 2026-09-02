"""Stripe webhook for the program tier (docs/program-plan.md).

One endpoint, ``POST /webhook``. Every request is verified against the
endpoint's signing secret before the body is parsed; an unsigned or
mis-signed request is refused with 400 and nothing is read from it.

The webhook is the record of subscription state, not the trigger for a
build. Builds start from the setup form (setup_handler.py) after the buyer
has told us the program's details, and from the weekly refresh
(refresh_handler.py) for active subscriptions. So this handler does little:

- ``checkout.session.completed``: note the session, so a buyer who closes the
  tab before the setup form can be found from the Stripe dashboard and
  helped by hand.
- ``customer.subscription.created`` / ``updated``: upsert the subscription's
  status. A status other than ``active`` or ``trialing`` stops the refresh.
- ``customer.subscription.deleted``: mark it canceled. The row is kept, not
  deleted, so a cancellation is a fact with a date rather than an absence.

Anything else is acknowledged with 200 and ignored; Stripe retries on
non-2xx, and an unknown event type is not a reason to make it retry.
"""

from __future__ import annotations

import json
import os
from typing import Any

from common import json_response, now_iso, table, verify_stripe_signature

ACTIVE_STATUSES = ("active", "trialing")


def _headers(event: dict[str, Any]) -> dict[str, str]:
    return {k.lower(): v for k, v in (event.get("headers") or {}).items()}


def _raw_body(event: dict[str, Any]) -> bytes:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64

        return base64.b64decode(body)
    return body.encode() if isinstance(body, str) else bytes(body)


def apply_event(event_type: str, data: dict[str, Any], *, subscriptions: Any, bundles: Any) -> str:
    """Apply one verified event to the tables. Returns a one-word outcome
    for the response body and the log."""
    obj = data.get("object") or {}
    if event_type == "checkout.session.completed":
        bundles.put_item(
            Item={
                "bundle_id": f"checkout#{obj.get('id', '')}",
                "mode": obj.get("mode", ""),
                "email": (obj.get("customer_details") or {}).get("email", ""),
                "seen_at": now_iso(),
            }
        )
        return "noted"
    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        status = str(obj.get("status") or "")
        subscriptions.update_item(
            Key={"id": str(obj.get("id") or "")},
            UpdateExpression="SET #s = :s, customer = :c, updated_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "active" if status in ACTIVE_STATUSES else status or "unknown",
                ":c": str(obj.get("customer") or ""),
                ":t": now_iso(),
            },
        )
        return "updated"
    if event_type == "customer.subscription.deleted":
        subscriptions.update_item(
            Key={"id": str(obj.get("id") or "")},
            UpdateExpression="SET #s = :s, canceled_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "canceled", ":t": now_iso()},
        )
        return "canceled"
    return "ignored"


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """API Gateway (HTTP API v2 payload) entrypoint."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    if method != "POST":
        return json_response(405, {"ok": False, "error": "POST only."})
    raw = _raw_body(event)
    signature = _headers(event).get("stripe-signature", "")
    if not verify_stripe_signature(raw, signature, os.environ.get("STRIPE_WEBHOOK_SECRET", "")):
        return json_response(400, {"ok": False, "error": "Signature check failed."})
    try:
        payload = json.loads(raw.decode())
    except ValueError:
        return json_response(400, {"ok": False, "error": "Body is not JSON."})
    if not isinstance(payload, dict):
        return json_response(400, {"ok": False, "error": "Body is not an event."})
    outcome = apply_event(
        str(payload.get("type") or ""),
        payload.get("data") or {},
        subscriptions=table("SUBSCRIPTIONS_TABLE"),
        bundles=table("BUNDLES_TABLE"),
    )
    return json_response(200, {"ok": True, "outcome": outcome})
