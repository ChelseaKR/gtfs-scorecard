"""Serverless handler for opt-in feed-health alerts: claim and confirm.

A small Lambda behind an HTTP API. Routes:

  POST /subscribe   {email, all|agencies[], kinds[]}  -> store a pending
                    (unverified) subscriber and email a tokenized confirm link.
  GET  /confirm?email=&token=                          -> a page with one button
  POST /confirm?email=&token=                          -> mark verified.
  GET  /unsubscribe?email=&token=                      -> a page with one button
  POST /unsubscribe?email=&token=                      -> remove the subscriber
                    (also the RFC 8058 one-click POST that mail providers send
                    from the List-Unsubscribe header on each digest).

Why a GET only shows a page: agency and .gov mail often runs a link scanner
(Safe Links, Proofpoint, Mimecast) that opens every link in a message before the
person does. While a GET confirmed or unsubscribed, the scanner used up the
confirm link (the person then saw "Link not valid" although they were
subscribed) and could unsubscribe a reader without their knowing. Scanners do
not press buttons, so the change of state now waits for a POST.

Consent is double opt-in: a row is written unverified, and nothing is ever sent
to it (the daily digest skips unverified subscribers) until the recipient clicks
the confirm link, which only they receive. The store is the DynamoDB table the
pipeline reads (scorecard notify --table); real addresses live there, never in
the repo.

Only the standard library is used at import time; boto3 (present in the Lambda
runtime) is imported lazily inside the handlers, so the pure validation here is
unit-testable without AWS. See docs/decisions/0004-opt-in-alerts.md.

Environment:
  SUBSCRIPTIONS_TABLE      DynamoDB table name
  SES_FROM                 verified sender, e.g. alerts@gtfsscorecard.org
  ALLOW_ORIGIN             CORS origin of the web form (never "*")
  BASE_URL                 site origin used to build the confirm link
  SUBSCRIBE_SHARED_SECRET  if set, requests must send a matching
                           X-Subscribe-Token header (a weak, client-visible bot
                           guard; double opt-in is the real protection)
  AWS_REGION               provided by Lambda
"""

from __future__ import annotations

import datetime as dt
import hmac
import html
import json
import os
import re
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, quote

# Restricted to the characters a real address uses, so a registered address can't
# smuggle URL or query syntax into the confirm/unsubscribe links built from it.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# Must stay identical to notify.ALERT_KINDS. This Lambda cannot import the pipeline package, so
# the two lists are kept in step by a test that imports both and compares them
# (test_infra_handlers.test_handler_alert_kinds_match_the_digest_builder).
#
# They drifted once, and the shape of the bug is worth recording. The form path stores whatever
# this tuple holds when a payload omits `kinds`, so a subscriber who chose nothing was written an
# explicit closed two-item list rather than a "wants everything" marker. subscriptions.yaml
# documents "omit for every kind" and the YAML path honors it; the form path silently inverted it,
# and a form subscriber was permanently opted out of lapse_risk, export_change and anomaly without
# ever being told.
ALERT_KINDS = ("expiry", "lapse_risk", "regression", "export_change", "anomaly")
MAX_AGENCIES = 50
DEFAULT_ORIGIN = "https://gtfsscorecard.org"

# Rate limits (the chosen abuse model: server-side, no third party). A fixed
# per-IP window caps scripted volume; a per-address cooldown caps how often any
# one inbox can be sent a confirm email (the email-bomb vector).
IP_LIMIT = 10
IP_WINDOW = 3600  # seconds
EMAIL_COOLDOWN = 900  # seconds between confirm emails to one address


class BadRequest(ValueError):
    """Input the form should never send; surfaced as a 400.

    `code` names the field the refusal is about (email, agency, kinds), so the
    form can show its own sentence and mark that field rather than print the
    API's terse text to a reader."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def validate_subscribe(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate a subscribe payload. Pure; raises BadRequest."""
    email = body.get("email")
    if not isinstance(email, str) or not EMAIL_RE.match(email.strip()):
        raise BadRequest("a valid email is required", "email")
    email = email.strip().lower()

    follows_all = body.get("all") is True
    agencies: list[str] = []
    if not follows_all:
        raw = body.get("agencies")
        if not isinstance(raw, list) or not raw:
            raise BadRequest("choose at least one agency, or all", "agency")
        if len(raw) > MAX_AGENCIES:
            raise BadRequest("too many agencies", "agency")
        for a in raw:
            if not isinstance(a, str) or not SLUG_RE.match(a):
                raise BadRequest(f"invalid agency id: {a!r}", "agency")
            agencies.append(a)

    kinds_raw = body.get("kinds")
    if kinds_raw is None:
        kinds = list(ALERT_KINDS)
    elif isinstance(kinds_raw, list) and kinds_raw:
        bad = [k for k in kinds_raw if k not in ALERT_KINDS]
        if bad:
            raise BadRequest(f"unknown alert kind(s): {bad}", "kinds")
        kinds = list(dict.fromkeys(kinds_raw))  # de-dupe, keep order
    else:
        raise BadRequest("kinds must be a non-empty list if present", "kinds")

    out: dict[str, Any] = {"email": email, "kinds": kinds}
    if follows_all:
        out["all"] = True
    else:
        out["agencies"] = agencies
    return out


def _cors_headers(content_type: str = "application/json") -> dict[str, str]:
    return {
        "Content-Type": content_type,
        "Access-Control-Allow-Origin": os.environ.get("ALLOW_ORIGIN", DEFAULT_ORIGIN),
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Subscribe-Token",
    }


def _json(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps(body)}


def _html(status: int, title: str, message: str, button: str = "") -> dict[str, Any]:
    """A small page for a link opened from an email.

    With `button`, the page carries one form that POSTs back to the address it
    was opened at (no action attribute), so the token in the link travels with
    the press and nowhere else. `title`, `message` and `button` are this file's
    own wording; anything taken from a request is escaped before it gets here.
    These pages carry a token in their address, so they are never cached and
    never sent as a referrer."""
    form = (
        "<form method=post>"
        "<button type=submit style='font:inherit;font-weight:600;min-height:44px;"
        "padding:0.6rem 1.2rem;cursor:pointer'>"
        f"{button}</button></form>"
        if button
        else ""
    )
    page = (
        # lang, a viewport and a main landmark, as on every page of the site:
        # people open this from an email link, often on a phone (WCAG 3.1.1,
        # 1.4.10, 1.3.1; docs/vpat.md).
        "<!doctype html><html lang=en><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title>"
        "<body style='font-family:system-ui;max-width:34rem;margin:4rem auto;padding:0 1rem'>"
        f"<main><h1>{title}</h1><p>{message}</p>{form}"
        "<p><a href='https://gtfsscorecard.org/'>Back to GTFS Scorecard</a></p></main>"
    )
    headers = _cors_headers("text/html; charset=utf-8")
    headers["Cache-Control"] = "no-store"
    headers["Referrer-Policy"] = "no-referrer"
    return {"statusCode": status, "headers": headers, "body": page}


def _secret_ok(event: dict[str, Any]) -> bool:
    secret = os.environ.get("SUBSCRIBE_SHARED_SECRET", "")
    if not secret:
        return True
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    return hmac.compare_digest(headers.get("x-subscribe-token", ""), secret)


def _table() -> Any:
    import boto3  # noqa: PLC0415 - lazy; provided by the Lambda runtime

    region = os.environ.get("AWS_REGION", "us-west-2")
    return boto3.resource("dynamodb", region_name=region).Table(os.environ["SUBSCRIPTIONS_TABLE"])


def _request_base(event: dict[str, Any]) -> str:
    """The public base URL of this API, taken from the request itself. The
    confirm/unsubscribe routes live on this API (not the static site), so links
    must point here, and reading the host avoids hard-coding the endpoint."""
    domain = event.get("requestContext", {}).get("domainName")
    return f"https://{domain}" if domain else DEFAULT_ORIGIN


def _send_confirmation(email: str, token: str, base: str) -> None:
    import boto3  # noqa: PLC0415 - lazy; provided by the Lambda runtime

    link = (
        f"{base.rstrip('/')}/confirm"
        f"?email={quote(email, safe='')}&token={quote(token, safe='')}"
    )
    # Kept in sync with notify.verification_email; the two live in separate deploy
    # units (this standalone Lambda does not bundle the pipeline package).
    body = (
        "You (or someone using this address) asked for GTFS Scorecard feed-health "
        "alerts.\n\n"
        f"Confirm to start receiving them:\n  {link}\n\n"
        "If you did not request this, ignore this email and nothing will be sent.\n"
    )
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    ses.send_email(
        Source=os.environ["SES_FROM"],
        Destination={"ToAddresses": [email]},
        Message={
            "Subject": {"Data": "Confirm your GTFS Scorecard alerts"},
            "Body": {"Text": {"Data": body}},
        },
    )


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _ip_rate_limited(event: dict[str, Any]) -> bool:
    """Fixed-window per-IP counter in the rate-limit table (TTL auto-expires each
    window). Returns True once an IP exceeds IP_LIMIT requests in a window."""
    ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")
    if not ip:
        return False
    import boto3  # noqa: PLC0415 - lazy; provided by the Lambda runtime

    region = os.environ.get("AWS_REGION", "us-west-2")
    table = boto3.resource("dynamodb", region_name=region).Table(os.environ["RATELIMIT_TABLE"])
    now = int(time.time())
    bucket = now // IP_WINDOW
    resp = table.update_item(
        Key={"key": f"ip#{ip}#{bucket}"},
        UpdateExpression="ADD #c :one SET expires_at = if_not_exists(expires_at, :exp)",
        ExpressionAttributeNames={"#c": "count"},
        ExpressionAttributeValues={":one": 1, ":exp": (bucket + 1) * IP_WINDOW + 60},
        ReturnValues="ALL_NEW",
    )
    return int(resp["Attributes"]["count"]) > IP_LIMIT


def _email_on_cooldown(existing: dict[str, Any] | None) -> bool:
    """True if a pending row for this address got a confirm email within the
    cooldown. Caps how often one inbox can be sent a 'confirm?' email."""
    if not existing or existing.get("verified"):
        return False
    ts = existing.get("requested_ts")
    return bool(ts) and (int(time.time()) - int(ts)) < EMAIL_COOLDOWN


def _subscribe(event: dict[str, Any]) -> dict[str, Any]:
    if not _secret_ok(event):
        return _json(403, {"error": "forbidden"})
    if _ip_rate_limited(event):
        return _json(429, {"error": "Too many requests. Try again later.", "code": "rate"})
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON", "code": "request"})
    if not isinstance(payload, dict):
        return _json(400, {"error": "invalid JSON", "code": "request"})
    try:
        sub = validate_subscribe(payload)
    except BadRequest as exc:
        return _json(400, {"error": str(exc), "code": exc.code})

    table = _table()
    existing = table.get_item(Key={"email": sub["email"]}).get("Item")
    if existing and existing.get("verified"):
        return _json(200, {"status": "subscribed", "message": "This address is already subscribed."})
    if _email_on_cooldown(existing):
        return _json(
            429,
            {"error": "A confirmation email was just sent. Check your inbox.", "code": "cooldown"},
        )

    token = secrets.token_urlsafe(24)
    # A stable unsubscribe token, kept across confirm so every alert email can
    # carry a working one-click unsubscribe link (preserved if re-subscribing).
    unsub = (existing or {}).get("unsub_token") or secrets.token_urlsafe(24)
    item: dict[str, Any] = {
        "email": sub["email"],
        "verified": False,
        "token": token,
        "unsub_token": unsub,
        "kinds": set(sub["kinds"]),
        "created_at": _now(),
        "requested_ts": int(time.time()),
    }
    if sub.get("all"):
        item["all"] = True
    else:
        item["agencies"] = set(sub["agencies"])
    # Upsert: re-subscribing overwrites the pending row, so repeated requests for
    # one address do not pile up. A still-pending address simply gets a fresh link.
    table.put_item(Item=item)
    _send_confirmation(sub["email"], token, _request_base(event))
    return _json(200, {"status": "pending", "message": "Check your email to confirm."})


def _link_params(event: dict[str, Any]) -> tuple[str, str]:
    """The address and token a confirm or unsubscribe link carries."""
    qs = parse_qs((event.get("rawQueryString") or "").lstrip("?"))
    email = (qs.get("email") or [""])[0].strip().lower()
    token = (qs.get("token") or [""])[0]
    return email, token


def _matches(row: dict[str, Any] | None, field: str, token: str) -> bool:
    value = (row or {}).get(field)
    return bool(value) and hmac.compare_digest(str(value), token)


_SUBSCRIBED = (
    "You are subscribed",
    "Your address is confirmed. You will hear from us only when a feed you follow needs attention.",
)


def _confirm(event: dict[str, Any]) -> dict[str, Any]:
    """POST /confirm: the person pressed the button, so mark the row verified.

    The used token is kept as `confirmed_token`, so the same link opened again
    (by the person, or by a scanner after them) says the address is subscribed
    instead of calling a good link invalid. Only the holder of the link can get
    that answer: any other token gets "Link not valid", whatever the row says."""
    email, token = _link_params(event)
    if not email or not token:
        return _html(400, "Link incomplete", "That confirmation link is missing information.")
    table = _table()
    row = table.get_item(Key={"email": email}).get("Item")
    if row and row.get("verified") and _matches(row, "confirmed_token", token):
        return _html(200, *_SUBSCRIBED)
    if not _matches(row, "token", token):
        return _html(400, "Link not valid", "That confirmation link is expired or already used.")
    table.update_item(
        Key={"email": email},
        UpdateExpression="SET verified = :t, confirmed_token = :tok REMOVE #tok",
        ExpressionAttributeNames={"#tok": "token"},
        ExpressionAttributeValues={":t": True, ":tok": token},
    )
    return _html(200, *_SUBSCRIBED)


def _confirm_page(event: dict[str, Any]) -> dict[str, Any]:
    """GET /confirm: what opening the emailed link shows. It changes nothing."""
    email, token = _link_params(event)
    if not email or not token:
        return _html(400, "Link incomplete", "That confirmation link is missing information.")
    row = _table().get_item(Key={"email": email}).get("Item")
    if row and row.get("verified") and _matches(row, "confirmed_token", token):
        return _html(200, *_SUBSCRIBED)
    if not _matches(row, "token", token):
        return _html(400, "Link not valid", "That confirmation link is expired or already used.")
    return _html(
        200,
        "Confirm your feed-health alerts",
        f"Press the button to start alerts for {html.escape(email)}.",
        button="Confirm my alerts",
    )


def _unsubscribe(event: dict[str, Any]) -> dict[str, Any]:
    """POST /unsubscribe: the button on the page, or a mail provider's RFC 8058
    one-click request (body ``List-Unsubscribe=One-Click``). The token in the
    address is what authorizes it, so the body is not read."""
    email, token = _link_params(event)
    if not email or not token:
        return _html(400, "Link incomplete", "That unsubscribe link is missing information.")
    table = _table()
    row = table.get_item(Key={"email": email}).get("Item")
    # Idempotent: a missing row (already removed) is a success, not an error.
    if _matches(row, "unsub_token", token):
        table.delete_item(Key={"email": email})
    elif row:
        return _html(400, "Link not valid", "That unsubscribe link is not valid.")
    return _html(
        200, "Unsubscribed", "You will not receive any more feed-health alerts at this address."
    )


def _unsubscribe_page(event: dict[str, Any]) -> dict[str, Any]:
    """GET /unsubscribe: what the link in a digest opens. It changes nothing."""
    email, token = _link_params(event)
    if not email or not token:
        return _html(400, "Link incomplete", "That unsubscribe link is missing information.")
    row = _table().get_item(Key={"email": email}).get("Item")
    if not row:
        return _html(
            200, "Unsubscribed", "You will not receive any more feed-health alerts at this address."
        )
    if not _matches(row, "unsub_token", token):
        return _html(400, "Link not valid", "That unsubscribe link is not valid.")
    return _html(
        200,
        "Stop feed-health alerts",
        f"Press the button to stop all feed-health alerts to {html.escape(email)}.",
        button="Unsubscribe",
    )


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """API entrypoint. Routes by method and path."""
    ctx = event.get("requestContext", {}).get("http", {})
    method = ctx.get("method", "GET").upper()
    path = ctx.get("path", "/")
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": _cors_headers(), "body": ""}
    if path.endswith("/unsubscribe"):
        if method == "GET":
            return _unsubscribe_page(event)
        if method == "POST":
            return _unsubscribe(event)
    if method == "POST" and path.endswith("/subscribe"):
        return _subscribe(event)
    if path.endswith("/confirm"):
        if method == "GET":
            return _confirm_page(event)
        if method == "POST":
            return _confirm(event)
    return _json(404, {"error": "not found"})
