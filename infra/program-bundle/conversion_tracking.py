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
or tag: web/src/measure.js already keeps this site cookieless
(docs/decisions/0055-cookieless-site-measurement.md), and this module adds no
script, no cookie, and no gclid capture to the frontend. The email hashed
below is the same one the webhook already stores in the bundles table
(webhook_handler.py); nothing new is collected, only reused, server-side,
after a sale is already known.

What this module does NOT do, on purpose: call the Google Ads API. A real
upload needs OAuth (a developer token, an OAuth client, a refresh token, a
login customer id) -- credentials this repo will never hold, and standing up
that call here would be code nobody could run or test today. So the sink
(``emit``) only writes one structured line to the Lambda's own CloudWatch log
group. The follow-up -- a small scheduled job that reads those lines and
calls the Google Ads API's offline conversion / enhanced-conversions-for-leads
upload via the ``google-ads`` client library -- is deliberately left for
after Chelsea has a conversion action to upload to; seeing real logged events
first is also the easiest way to check the payload shape before that job is
written. See the design doc's "owner steps" for the account-creation order
this waits on.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from common import now_iso


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
    """
    action = conversion_action()
    if not action or not email:
        return None
    return {
        "conversion_action": action,
        # Google Ads wants "yyyy-MM-dd HH:mm:ss+HH:mm"; occurred_at is
        # common.now_iso()'s "yyyy-MM-ddTHH:mm:ss+00:00" and only needs its
        # "T" swapped for a space at upload time, a transform that belongs
        # in the eventual upload job, not baked into the logged event here.
        "conversion_date_time": occurred_at,
        "conversion_value": round((amount_total or 0) / 100, 2),
        "currency_code": (currency or "usd").upper(),
        "plan": plan,
        "user_identifiers": [{"hashed_email": hash_identifier(email)}],
    }


def emit(event: dict[str, Any]) -> None:
    """Write one conversion event as a single structured CloudWatch log line
    (this Lambda's stdout). This is the seam's sink today -- nothing calls
    the Google Ads API yet. A later change points this at the google-ads
    client library instead of, or in addition to, logging."""
    print(json.dumps({"conversion_event": event}, sort_keys=True))


def note_conversion(*, plan: str, obj: dict[str, Any]) -> None:
    """Called once per completed checkout that webhook_handler has already
    confirmed is this product's (a real plan, not "" or "unverified"). Reads
    the same Stripe Checkout Session object the webhook itself reads, builds
    the conversion event, and emits it when configured. A no-op end to end
    while GOOGLE_ADS_CONVERSION_ACTION is unset, which is every deploy today.
    """
    email = str((obj.get("customer_details") or {}).get("email") or "")
    event = build_conversion_event(
        plan=plan,
        email=email,
        amount_total=obj.get("amount_total"),
        currency=str(obj.get("currency") or "usd"),
        occurred_at=now_iso(),
    )
    if event is not None:
        emit(event)
