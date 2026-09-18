"""Google Ads conversion-tracking seam for the program bundle (docs/paid-search-readiness.md).

Not wired to a real account: there is no Google Ads account yet, and this
module is written so that creating one and adding a conversion action is a
one-line config change and nothing else.

``GOOGLE_ADS_CONVERSION_ACTION`` (set by Terraform, ``var.google_ads_conversion_action``
in infra/program-bundle/main.tf, default ``""``) is that one line. While it is
blank -- today, and until Chelsea creates the account -- ``build_conversion_event``
always returns None and ``note_conversion`` is a no-op: webhook_handler's
behavior is unchanged from before this module existed.

This targets Google Ads' "Enhanced conversions for leads" shape: a hashed
customer identifier plus a conversion value and time, matched by Google
against its own signed-in-user graph. Deliberately not a client-side pixel
or tag: web/src/measure.js captures no gclid, because it drops the query
string and runs GA4 with ad storage denied (docs/decisions/0055 and 0056),
and this module adds no script, no cookie, and no gclid capture to the
frontend. The email hashed
below is the same one the webhook already stores in the bundles table
(webhook_handler.py); nothing new is collected, only reused, server-side,
after a sale is already known.

2026-09-15 update: the conversion action above now exists
(``customers/2688527650/conversionActions/7769927171``), and the follow-up
this docstring used to defer -- ``ads_conversion_upload_handler.py``, a
scheduled Lambda that reads what ``emit`` below writes and calls the
Google Ads API's ``ConversionUploadService`` via the ``google-ads`` client
library -- now exists too (docs/google-ads-upload-setup.md). This module's
own job is unchanged: build the payload and hand it to a sink. What changed
is the sink.

``emit`` still prints one structured line to this Lambda's CloudWatch log
group -- that inspection path is untouched. It also now writes the same
event, when ``AD_CONVERSIONS_TABLE`` is configured, to a small DynamoDB
table ``ads_conversion_upload_handler.py`` reads on a schedule. Why a table
and not a CloudWatch Logs Insights query over the printed lines (the shape
this docstring originally sketched, still described in
docs/paid-search-readiness.md §3): Logs Insights has no notion of "already
uploaded," so that plan needed a second small store for the checkpoint
anyway, plus an async, polled query API in front of it. Writing straight to
a table this repo already has idioms for (``common.scan_all``, the
conditional-write pattern in ``webhook_handler._update_subscription``) gets
the same result with one moving part instead of two, and is what the upload
handler's own tests exercise with the existing ``FakeTable`` harness rather
than a mocked Logs Insights client.

``store_pending_upload`` keys each row by the Stripe checkout session id
(carried through as ``conversion_id``) and refuses to overwrite a row that
is already there. That is what keeps a Stripe webhook retry of the same
``checkout.session.completed`` -- which calls ``note_conversion`` again --
from resetting an already-uploaded row back to pending and causing a second
report to Google Ads for one sale.
"""

from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal
from typing import Any

from common import now_iso, table

PENDING = "pending"


def conversion_action() -> str:
    """The Google Ads conversion action resource name, e.g.
    "customers/1234567890/conversionActions/987654321". Empty until Chelsea
    creates the Ads account and a conversion action for the bundle purchase
    -- the one thing this whole seam is waiting on."""
    return os.environ.get("GOOGLE_ADS_CONVERSION_ACTION", "").strip()


def hash_identifier(value: str) -> str:
    """SHA-256 hex digest of a trimmed, lowercased identifier, the exact
    normalization Google Ads' enhanced conversions require before hashing."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def build_conversion_event(
    *,
    plan: str,
    email: str,
    amount_total: int | None,
    currency: str,
    occurred_at: str,
    conversion_id: str = "",
) -> dict[str, Any] | None:
    """The payload for one purchase, in the shape a later Google Ads upload
    would send, or None when there is nothing to send: no conversion action
    configured (true of every deploy today), or no email to hash (a checkout
    session with no ``customer_details.email``, which the webhook's own
    ``bundles`` row would also show as blank).

    ``amount_total`` is cents, exactly as Stripe sends it on the Checkout
    Session object in the ``checkout.session.completed`` event payload
    (no second Stripe read); it is converted to a decimal currency amount
    here because that is the unit Google Ads' conversion value expects.

    ``conversion_id`` is the Stripe checkout session id (``note_conversion``
    passes ``obj["id"]``). It travels on the event only so
    ``store_pending_upload`` has a stable key to write the pending row
    under; ``ads_conversion_upload_handler.py`` never sends it to Google
    Ads. Blank by default so every existing caller of this function keeps
    working unchanged.
    """
    action = conversion_action()
    if not action or not email:
        return None
    return {
        "conversion_action": action,
        # Google Ads wants "yyyy-MM-dd HH:mm:ss+HH:mm"; occurred_at is
        # common.now_iso()'s "yyyy-MM-ddTHH:mm:ss+00:00" and only needs its
        # "T" swapped for a space at upload time, a transform
        # ads_conversion_upload_handler.py makes, not baked into the logged
        # event here.
        "conversion_date_time": occurred_at,
        "conversion_value": round((amount_total or 0) / 100, 2),
        "currency_code": (currency or "usd").upper(),
        "plan": plan,
        "user_identifiers": [{"hashed_email": hash_identifier(email)}],
        "conversion_id": conversion_id,
    }


def emit(event: dict[str, Any]) -> None:
    """Write one conversion event as a single structured CloudWatch log line
    (this Lambda's stdout), then hand it to ``store_pending_upload`` -- see
    the module docstring for why a small table and not a Logs Insights
    query. Printing happens unconditionally and first: it is cheap,
    unaffected by whether the table is configured, and is what every
    existing test that spies on this function has always observed."""
    print(json.dumps({"conversion_event": event}, sort_keys=True))
    store_pending_upload(event)


def store_pending_upload(event: dict[str, Any]) -> None:
    """Persist one conversion event as a ``status: "pending"`` row
    ``ads_conversion_upload_handler.py`` can find, when
    ``AD_CONVERSIONS_TABLE`` is configured. Blank (every deploy before
    main.tf's table is applied) makes this a no-op, the same posture as
    ``conversion_action()`` above.

    Keyed by ``event["conversion_id"]`` with a condition that refuses to
    overwrite an existing row -- see the module docstring: a Stripe webhook
    retry must not be able to reset an already-uploaded row back to
    pending. A blank ``conversion_id`` cannot be keyed at all; that row is
    logged (the printed CloudWatch line above already carries the full
    event) and not written, rather than written under a made-up key nothing
    else would ever look for.

    Not wrapped in a broader try/except: a genuine DynamoDB outage here
    raises, the same as an outage in the ``bundles.put_item`` call the
    webhook already makes right before this runs. Stripe retries the
    webhook on a non-2xx response, and the write is safe to retry (the
    condition below is exactly what makes it so).
    """
    table_name = os.environ.get("AD_CONVERSIONS_TABLE", "").strip()
    if not table_name:
        return
    conversion_id = str(event.get("conversion_id") or "")
    if not conversion_id:
        print(json.dumps({"conversion_event_error": "no conversion_id; not queued for upload"}))
        return
    row = {
        "conversion_id": conversion_id,
        "status": PENDING,
        "event": _for_dynamodb(event),
        "created_at": now_iso(),
    }
    conversions = table("AD_CONVERSIONS_TABLE")
    try:
        conversions.put_item(Item=row, ConditionExpression="attribute_not_exists(conversion_id)")
    except Exception as err:  # boto3's ConditionalCheckFailedException, by name -- see common.py
        if "ConditionalCheckFailed" in type(err).__name__ or "ConditionalCheckFailed" in str(err):
            return
        raise


def _for_dynamodb(event: dict[str, Any]) -> dict[str, Any]:
    """boto3's Table resource refuses a Python ``float`` ("Float types are
    not supported. Use Decimal types instead."); ``conversion_value`` is the
    only float ``build_conversion_event`` produces."""
    out = dict(event)
    if "conversion_value" in out:
        out["conversion_value"] = Decimal(str(out["conversion_value"]))
    return out


def note_conversion(*, plan: str, obj: dict[str, Any]) -> None:
    """Called once per completed checkout that webhook_handler has already
    confirmed is this product's (a real plan, not "" or "unverified"). Reads
    the same Stripe Checkout Session object the webhook itself reads, builds
    the conversion event, and emits it when configured. A no-op end to end
    while GOOGLE_ADS_CONVERSION_ACTION is unset.
    """
    email = str((obj.get("customer_details") or {}).get("email") or "")
    event = build_conversion_event(
        plan=plan,
        email=email,
        amount_total=obj.get("amount_total"),
        currency=str(obj.get("currency") or "usd"),
        occurred_at=now_iso(),
        conversion_id=str(obj.get("id") or ""),
    )
    if event is not None:
        emit(event)
