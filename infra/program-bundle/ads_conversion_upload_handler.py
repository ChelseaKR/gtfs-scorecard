"""Scheduled Google Ads conversion upload for the program bundle
(docs/paid-search-readiness.md, docs/google-ads-upload-setup.md).

EventBridge invokes this daily (state gated on ``var.google_ads_upload_ready``
in main.tf -- the same "Terraform cannot check this for itself" posture as
the daily reconciler's ``reconciler_reporting_ready``). It reads every row
``conversion_tracking.emit`` wrote to ``AD_CONVERSIONS_TABLE`` with
``status: "pending"``, uploads each as a Google Ads "Enhanced Conversions
for Leads" click conversion (``ConversionUploadService.upload_click_conversions``,
the ``google-ads`` client library) against ``GOOGLE_ADS_CONVERSION_ACTION``,
and writes each row's own outcome back individually.

Why a DynamoDB table and not the CloudWatch Logs Insights query
docs/paid-search-readiness.md §3 originally sketched: see
conversion_tracking.py's module docstring. In short, that plan still needed
some persisted checkpoint of "already uploaded" to stay idempotent across
runs -- Logs Insights has no notion of "processed" -- so it would have paired
an async, polled query API with a second small store anyway. Writing
straight to a table this handler can scan, claim and re-read gives the same
result with one moving part instead of two, using the scan-with-pagination
and conditional-write idioms this Lambda set already has
(``common.scan_all``, ``webhook_handler._update_subscription``).
``conversion_tracking.emit`` still prints its structured CloudWatch line
too; nothing here removes an existing inspection path.

Credentials -- a developer token, an OAuth client id and secret, a refresh
token, and the login customer id -- are five more sensitive Terraform
variables wired into ``local.common_env`` (main.tf), the same shape as
``STRIPE_SECRET_KEY`` and ``GITHUB_TOKEN`` elsewhere in this Lambda set:
blank by default, never a value this repo commits, read from the
environment at call time. Any one of them blank makes a real run refuse
with ``ConfigurationError`` rather than silently uploading nothing -- the
same posture as ``refresh_handler.ConfigurationError``. See
docs/google-ads-upload-setup.md for where each value comes from and how an
owner puts it in Terraform.

Idempotent two ways:
  - ``conversion_tracking.store_pending_upload`` writes one row per Stripe
    checkout session id and refuses to overwrite an existing one, so a
    Stripe webhook retry can never re-queue an already-handled purchase.
  - This handler only ever claims a row with a conditional update
    (``status = "pending"`` -> ``"uploaded"``/``"failed"``), so two
    overlapping invocations (a slow run plus the next day's schedule)
    cannot both report the same conversion: whichever gets there first wins
    the row, and the other's write is refused and counted
    ``claimed_elsewhere``, not retried into a duplicate upload.

Partial failures: the upload request is sent with ``partial_failure=True``,
so one malformed or refused conversion in a batch cannot sink the rest.
Each row's own result -- success or Google Ads' own error message -- is
written back to its row, and nothing is silently dropped: a row that fails
stays at ``status: "failed"`` with the error attached, for a human to read,
never retried automatically here (retrying blind into an API that already
recorded a partial failure risks a duplicate on the rows that DID succeed).

A row whose stored ``event`` cannot be read as a valid conversion payload
(missing a required field, no hashed-email identifier) is marked ``failed``
with that reason and the batch continues; one bad row must not crash the
whole run -- the same "found orders, could not vouch for all of them"
posture as ``reconcile_handler.artifact_state``'s ``unreadable`` case.

Dry run: ``DRY_RUN=1`` in the environment, or ``{"dry_run": true}`` as the
invoke payload, reads and logs what it would upload and changes nothing: no
Google Ads call, no row update, and no credentials are required (so a
dry run is useful before docs/google-ads-upload-setup.md is finished).
"""

from __future__ import annotations

import json
import os
from typing import Any

from common import now_iso, scan_all, table

PENDING = "pending"
UPLOADED = "uploaded"
FAILED = "failed"

# What conversion_tracking.build_conversion_event always puts on the event
# when a conversion action is configured -- a row missing any of these was
# either written before that function's contract, or hand-edited.
REQUIRED_EVENT_FIELDS = (
    "conversion_action",
    "conversion_date_time",
    "conversion_value",
    "currency_code",
)

# GOOGLE_ADS_DEVELOPER_TOKEN is read (see _client_from_env) but deliberately
# not required below: Google sunset the developer token as the
# access-control mechanism 2026-09-09 -- access levels now attach to the
# Google Cloud project behind the OAuth client instead -- and the google-ads
# client library itself lists this field as optional. See
# docs/google-ads-upload-setup.md.
_REQUIRED_CREDENTIAL_ENV_VARS = (
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
)
_CREDENTIAL_ENV_VARS = ("GOOGLE_ADS_DEVELOPER_TOKEN", *_REQUIRED_CREDENTIAL_ENV_VARS)


class ConfigurationError(RuntimeError):
    """One or more required Google Ads credentials are blank while there is
    real work to do. Raised rather than reported per row, the same reasoning
    as refresh_handler.ConfigurationError: a blank credential is a
    configuration fact, not something every pending row should be
    individually blamed for."""


def _credentials() -> dict[str, str] | None:
    """The Google Ads values this handler needs, keyed by the plain names
    ``_client_from_env`` uses, or None when a required one is blank -- the
    default in every deploy until an owner has completed
    docs/google-ads-upload-setup.md. ``developer_token`` may be blank (see
    the comment above _CREDENTIAL_ENV_VARS) and is still included in the
    returned dict either way, so _client_from_env always has the key."""
    values = {
        name.removeprefix("GOOGLE_ADS_").lower(): os.environ.get(name, "").strip()
        for name in _CREDENTIAL_ENV_VARS
    }
    required_keys = [
        name.removeprefix("GOOGLE_ADS_").lower() for name in _REQUIRED_CREDENTIAL_ENV_VARS
    ]
    missing_required = any(not values[key] for key in required_keys)
    return None if missing_required else values


def _client_from_env(credentials: dict[str, str]) -> Any:
    """Build a real GoogleAdsClient. Imported here, not at module load, so
    every other function in this module -- everything pytest exercises --
    runs without the ``google-ads`` package installed, the same "pure logic
    needs no account" posture as common.table()'s lazy boto3 import."""
    from google.ads.googleads.client import GoogleAdsClient

    return GoogleAdsClient.load_from_dict(
        {
            "developer_token": credentials["developer_token"],
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "refresh_token": credentials["refresh_token"],
            "login_customer_id": credentials["login_customer_id"],
            # proto-plus messages, not raw protobuf: every current Google Ads
            # client example uses attribute assignment
            # (click_conversion.conversion_value = 1.0), which is a
            # proto-plus behavior and the default (use_proto_plus=False)
            # does not support it the same way.
            "use_proto_plus": True,
        }
    )


def pending_rows(conversions: Any) -> list[dict[str, Any]]:
    """Every row still waiting to be uploaded. Scan order is not defined,
    and does not need to be: each row is claimed individually by its own
    conditional update in mark_row, so processing order cannot cause a
    double report."""
    return scan_all(
        conversions,
        FilterExpression="#s = :pending",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":pending": PENDING},
    )


def _google_ads_datetime(occurred_at: str) -> str:
    """Google Ads wants "yyyy-MM-dd HH:mm:ss+HH:mm"; conversion_tracking
    stores common.now_iso()'s "yyyy-MM-ddTHH:mm:ss+00:00" verbatim -- that
    module's own docstring already named this transform as the one thing
    left for this job."""
    return occurred_at.replace("T", " ", 1)


def parse_event(row: dict[str, Any]) -> dict[str, Any] | None:
    """The stored ``event`` map as a plain conversion payload ready for
    build_click_conversion, or None when the row is malformed: missing a
    required field, or not exactly one hashed-email user identifier. None
    is what keeps one bad row from crashing the batch (see the module
    docstring); the caller logs it and marks the row ``failed`` rather than
    raising."""
    event = row.get("event")
    if not isinstance(event, dict):
        return None
    for field in REQUIRED_EVENT_FIELDS:
        if not event.get(field):
            return None
    identifiers = event.get("user_identifiers")
    one_identifier = isinstance(identifiers, list) and len(identifiers) == 1
    if not one_identifier or not isinstance(identifiers[0], dict):
        return None
    hashed_email = str(identifiers[0].get("hashed_email") or "")
    if not hashed_email:
        return None
    return {
        "conversion_action": str(event["conversion_action"]),
        "conversion_date_time": _google_ads_datetime(str(event["conversion_date_time"])),
        "conversion_value": float(event["conversion_value"]),
        "currency_code": str(event["currency_code"]),
        "hashed_email": hashed_email,
    }


def build_click_conversion(client: Any, event: dict[str, Any]) -> Any:
    """One ClickConversion proto for the Google Ads upload request. No
    ``gclid`` is ever set: this site captures none (its measurement drops the
    query string and runs GA4 with ad storage denied -- docs/decisions/0055
    and 0056), and Enhanced
    Conversions for Leads matches on the hashed email identifier alone."""
    click_conversion = client.get_type("ClickConversion")
    click_conversion.conversion_action = event["conversion_action"]
    click_conversion.conversion_date_time = event["conversion_date_time"]
    click_conversion.conversion_value = event["conversion_value"]
    click_conversion.currency_code = event["currency_code"]
    identifier = client.get_type("UserIdentifier")
    identifier.hashed_email = event["hashed_email"]
    identifier.user_identifier_source = client.enums.UserIdentifierSourceEnum.FIRST_PARTY
    click_conversion.user_identifiers.append(identifier)
    return click_conversion


def _partial_failures(client: Any, response: Any) -> dict[int, str]:
    """{index into the request's ``conversions`` list: Google Ads' own error
    message}, empty when the whole batch succeeded.

    ``partial_failure_error`` is a raw ``google.rpc.Status`` -- unlike every
    other field this module reads, which is proto-plus, because it comes
    from ``google.rpc`` and not the Ads API itself -- carrying one
    ``GoogleAdsFailure`` packed into ``.details`` per failing conversion.
    Each failure's location names which element of ``conversions`` it
    belongs to; verified against the installed ``google-ads`` client
    (API v25) rather than assumed.
    """
    status = getattr(response, "partial_failure_error", None)
    if status is None or not getattr(status, "code", 0):
        return {}
    failure_type = type(client.get_type("GoogleAdsFailure"))
    failures: dict[int, str] = {}
    for detail in status.details:
        failure = failure_type.deserialize(detail.value)
        for error in failure.errors:
            index = 0
            for element in error.location.field_path_elements:
                if element.field_name == "conversions":
                    index = element.index
            failures[index] = str(error.message)
    return failures


def upload_batch(
    client: Any, *, login_customer_id: str, rows: list[tuple[str, dict[str, Any]]]
) -> dict[str, tuple[str, str]]:
    """Upload one batch. ``rows`` is (conversion_id, parsed event) pairs, in
    the same order the request lists them -- a partial-failure error names
    conversions by index into that list, so the order here and the order
    appended to the request must match. Returns
    ``{conversion_id: (status, detail)}`` for every row: UPLOADED with an
    empty detail, or FAILED with Google Ads' own error message.
    """
    service = client.get_service("ConversionUploadService")
    request = client.get_type("UploadClickConversionsRequest")
    request.customer_id = login_customer_id
    request.partial_failure = True
    for _conversion_id, event in rows:
        request.conversions.append(build_click_conversion(client, event))

    response = service.upload_click_conversions(request=request)
    failures = _partial_failures(client, response)

    outcome: dict[str, tuple[str, str]] = {}
    for index, (conversion_id, _event) in enumerate(rows):
        outcome[conversion_id] = (FAILED, failures[index]) if index in failures else (UPLOADED, "")
    return outcome


def mark_row(conversions: Any, conversion_id: str, *, status: str, detail: str) -> bool:
    """Claim one row for this outcome. The condition is the second half of
    this handler's idempotency (see the module docstring): only a row still
    ``pending`` can be moved, so two overlapping runs cannot both report the
    same conversion. Returns False, without raising, when another run
    already claimed this row -- the caller counts that, it does not retry
    it."""
    try:
        conversions.update_item(
            Key={"conversion_id": conversion_id},
            UpdateExpression="SET #s = :status, detail = :detail, updated_at = :t",
            ConditionExpression="#s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": status,
                ":detail": detail,
                ":t": now_iso(),
                ":pending": PENDING,
            },
        )
    except Exception as err:  # boto3's ConditionalCheckFailedException, by name -- see common.py
        if "ConditionalCheckFailed" in type(err).__name__ or "ConditionalCheckFailed" in str(err):
            return False
        raise
    return True


def run(
    *,
    conversions: Any,
    credentials: dict[str, str] | None,
    client_factory: Any = _client_from_env,
    dry_run: bool = False,
) -> dict[str, int]:
    """Upload every pending row once. Returns counts: scanned, malformed,
    uploaded, failed, claimed_elsewhere, would_upload."""
    counts = {
        "scanned": 0,
        "malformed": 0,
        "uploaded": 0,
        "failed": 0,
        "claimed_elsewhere": 0,
        "would_upload": 0,
    }
    rows = pending_rows(conversions)
    counts["scanned"] = len(rows)
    if not rows:
        return counts

    parsed: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        conversion_id = str(row.get("conversion_id") or "")
        event = parse_event(row)
        if not conversion_id or event is None:
            print(
                json.dumps(
                    {
                        "ads_conversion_upload": "malformed row skipped",
                        "conversion_id": conversion_id or "(missing)",
                    }
                )
            )
            counts["malformed"] += 1
            if conversion_id:
                mark_row(conversions, conversion_id, status=FAILED, detail="malformed stored event")
            continue
        parsed.append((conversion_id, event))

    if not parsed:
        return counts

    if dry_run:
        for conversion_id, _event in parsed:
            preview = {
                "ads_conversion_upload": "dry run: would upload",
                "conversion_id": conversion_id,
            }
            print(json.dumps(preview))
        counts["would_upload"] = len(parsed)
        return counts

    if credentials is None:
        raise ConfigurationError(
            "one or more of " + ", ".join(_REQUIRED_CREDENTIAL_ENV_VARS) + " is blank; "
            f"{len(parsed)} pending conversion(s) were found and none could be uploaded. "
            "See docs/google-ads-upload-setup.md."
        )

    client = client_factory(credentials)
    outcomes = upload_batch(client, login_customer_id=credentials["login_customer_id"], rows=parsed)
    for conversion_id, (status, detail) in outcomes.items():
        if mark_row(conversions, conversion_id, status=status, detail=detail):
            counts[status] += 1
        else:
            counts["claimed_elsewhere"] += 1
    return counts


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """EventBridge entrypoint. The scheduled event carries nothing this
    handler reads; a hand invoke may pass ``{"dry_run": true}``."""
    dry_run = os.environ.get("DRY_RUN", "0") == "1" or (
        isinstance(event, dict) and event.get("dry_run") is True
    )
    table_name = os.environ.get("AD_CONVERSIONS_TABLE", "").strip()
    if not table_name:
        # The default in every deploy until main.tf's table is applied --
        # conversion_tracking.emit has nowhere to write pending rows either,
        # so there is nothing a run could find.
        skipped = {
            "ads_conversion_upload": "skipped: AD_CONVERSIONS_TABLE is not set",
            "at": now_iso(),
        }
        print(json.dumps(skipped))
        return {"ok": True, "configured": False, "dry_run": dry_run}

    try:
        conversions = table("AD_CONVERSIONS_TABLE")
        counts = run(conversions=conversions, credentials=_credentials(), dry_run=dry_run)
    except ConfigurationError as err:
        print(json.dumps({"ads_conversion_upload": "refused", "reason": str(err), "at": now_iso()}))
        raise
    print(json.dumps({"ads_conversion_upload": counts, "dry_run": dry_run, "at": now_iso()}))

    trouble = counts["failed"] + counts["malformed"]
    if trouble:
        # Raised, not swallowed: a run that found conversions Google Ads
        # refused (or rows too malformed to send) and told nobody is exactly
        # the silent-failure shape this Lambda set refuses elsewhere
        # (reconcile_handler's unreadable case, refresh_handler's
        # ConfigurationError). The rows themselves are not lost -- each is
        # `status: "failed"` with its `detail` attached -- this is what puts
        # that fact in front of somebody instead of a schedule quietly
        # reporting `ok` over it.
        raise RuntimeError(
            f"{trouble} conversion(s) need attention ({counts['failed']} refused by Google Ads, "
            f"{counts['malformed']} had a malformed stored event); see each row's 'detail' in "
            f"table {table_name}."
        )
    return {"ok": True, "configured": True, **counts, "dry_run": dry_run}
