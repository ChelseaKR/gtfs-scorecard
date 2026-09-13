"""Post-checkout setup form and the download route (docs/program-plan.md).

Two routes on the program-bundle API, both stateless per request:

``POST /setup``
    The page a buyer lands on after Stripe Checkout posts here with the
    Checkout Session id and the program details (name, accent, logo, agency
    ids). The handler confirms with Stripe that the session is *paid* and
    that its one line item is one of this product's four prices (a paid
    checkout for anything else on the same Stripe account builds nothing),
    settles how many agencies this checkout covers, mints a bundle id,
    validates the request with the pipeline's own parse_request held to that
    number, records the session so a replayed form cannot dispatch twice,
    stores the capability row, dispatches report-bundle.yml, and for a
    subscription stores the request so the weekly refresh can re-dispatch it.

    **A refresh renews a bundle.** A one-time bundle is its own entitlement,
    but ``refresh_mo`` and ``refresh_yr`` are not: each requires an earlier
    bundle purchase on the same address and covers the agencies that bundle
    covered (``_inherited_cap``). Without that rule the two refresh prices
    carried the 100-agency cap in their own right, so $49 a month bought the
    archive the $349 bundle sells and then cancelled -- the cheapest product
    on the page strictly dominating the most expensive one. A refresh with no
    bundle to renew is refused **before the checkout is claimed**, so the
    buyer is left holding an unused checkout they can cancel, not a consumed
    one and no archive.

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

import datetime as dt
import json
import os
import time
import urllib.parse
from dataclasses import replace
from typing import Any, NamedTuple

from common import (
    CHECKOUT_PREFIX,
    ONE_TIME_PLANS,
    PLAN_AGENCY_CAPS,
    SESSION_PREFIX,
    SUBSCRIPTION_PLANS,
    UpstreamError,
    bundle_row,
    checkout_plan,
    dispatch_bundle_workflow,
    html_response,
    json_response,
    payments_enabled,
    scan_all,
    stripe_get,
    table,
    workflow_inputs,
)

from scorecard_pipeline import deadline
from scorecard_pipeline.bundle import (
    BundleError,
    archive_key,
    new_bundle_id,
    parse_request,
)

PRESIGN_SECONDS = 15 * 60
_SESSION_ID_MAX = 200


def _session_key(session_id: str) -> str:
    return f"{SESSION_PREFIX}{session_id}"


def _session_row(session_id: str, bundle_id: str, plan: str, email: str) -> dict[str, Any]:
    """Marks a Checkout Session as consumed. Shares the bundles table under a
    ``session#`` key so one conditional put is the whole idempotency check.
    No ``expires_at``: the claim must outlive the capability row, or a replay
    after 30 days would build a second bundle from one payment.

    ``dispatched`` starts False and is set True only once GitHub has accepted
    the workflow_dispatch. The claim therefore records two different facts --
    "this payment is spoken for" and "a build was actually started" -- so a
    second submission after a failed dispatch can finish the order instead of
    being told a bundle exists that does not.

    ``email`` is the address Stripe collected at that checkout, and it is the
    third fact: *who* this plan was sold to. A refresh subscription renews a
    bundle, so it has to be able to find the bundle it renews, and this row is
    the record written by the route that granted one -- already permanent, and
    permanent on purpose. Without it the only durable link from a buyer to a
    purchase would be the webhook's ``checkout#`` row, whose permanence
    infra/program-bundle/main.tf says in terms is *not* a decision anyone has
    made yet.
    """
    return {
        "bundle_id": _session_key(session_id),
        "consumed_by": bundle_id,
        "plan": plan,
        "email": email,
        "dispatched": False,
    }


def _claim_session(
    bundles: Any, session_id: str, bundle_id: str, plan: str, email: str = ""
) -> bool:
    """Atomically claim the session; False if it was already used."""
    try:
        bundles.put_item(
            Item=_session_row(session_id, bundle_id, plan, email),
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


class _Inherited(NamedTuple):
    """The cap a refresh subscription inherits, and the purchase it came from."""

    cap: int
    plan: str
    session_id: str


def _checkout_email(session: dict[str, Any]) -> str:
    """The address Stripe itself collected at this checkout, case-folded.

    Never the form's ``deliver_to``. That field is text the buyer typed, and
    this address is what decides entitlement below: if the form supplied it,
    anyone who guessed a program's email could inherit that program's cap for
    the price of the cheapest subscription, which is the same arbitrage this
    check exists to close, wearing a different hat.
    """
    details = session.get("customer_details") or {}
    return str(details.get("email") or "").strip().casefold()


def _purchase_rows(bundles: Any) -> list[dict[str, Any]]:
    """Every ``session#`` and ``checkout#`` row in the bundles table.

    The filter is passed to DynamoDB so a growing table does not return its
    capability rows over the wire on every subscription checkout, and the
    prefix is checked again in Python because a filter is a bandwidth saving
    and not a guarantee: the caller has to be correct against whatever comes
    back, including from a fake or a table with no filter support.
    """
    return scan_all(
        bundles,
        FilterExpression="begins_with(bundle_id, :session) OR begins_with(bundle_id, :checkout)",
        ExpressionAttributeValues={":session": SESSION_PREFIX, ":checkout": CHECKOUT_PREFIX},
    )


_NO_PRIOR_BUNDLE = (
    "A refresh renews a bundle you have already bought: it re-sends that same archive, "
    "refreshed, and it does not include a bundle of its own. Nothing was found on this "
    "email address to renew, so nothing was built and your agency list was not used. "
    "Buy a bundle at gtfsscorecard.org/bundle/ with this same address and then start the "
    "refresh, or, if the bundle was bought under a different address, reply to the receipt "
    "Stripe emailed you and the two can be linked by hand. You can cancel this subscription "
    "from that same receipt."
)
_NO_CHECKOUT_EMAIL = (
    "A refresh renews a bundle you have already bought, and this checkout carries no email "
    "address, so there is no way to tell which bundle it renews. Nothing was built and your "
    "checkout has not been used. Reply to the receipt Stripe emailed you and it can be set "
    "up by hand."
)
_CANNOT_SETTLE_PRIOR = (
    "Could not check which bundle this refresh renews just now, so nothing was built and "
    "your checkout has not been used. Open this page again in a few minutes. Do not pay again."
)
# How many earlier checkouts this route will ask Stripe about in one request.
# A `checkout#` row whose plan the webhook could not read carries the word
# "unverified", not a plan, and settling one costs a Stripe call. Ten is far
# past any real buyer's history; past it the honest answer is "not yet", never
# "you never bought a bundle".
_UNSETTLED_CHECKOUT_READS = 10
_WIDEST_ONE_TIME_CAP = max(PLAN_AGENCY_CAPS[plan] for plan in ONE_TIME_PLANS)


def _inherited_cap(bundles: Any, session: dict[str, Any], session_id: str) -> _Inherited:
    """How many agencies a refresh subscription covers: the cap of the bundle
    it renews. Raises ``_Refused`` when there is no such bundle.

    Two durable records answer this, and both outlive the capability row's
    30-day TTL, so a bundle bought in January is still found by a refresh
    started in March:

    ``session#`` rows
        Written here, by the route that grants a bundle, and permanent
        because the claim has to outlive the capability. This is the primary
        record: we wrote it, and its permanence is a decision already made.

    ``checkout#`` rows
        Written by the webhook when a checkout completes. They cover a bundle
        bought before this check existed, and a buyer who paid for a bundle
        and never came back to the setup form -- they still bought it. A row
        whose ``plan`` the webhook could not read is settled against Stripe
        rather than counted as nothing.

    Nothing here trims or upgrades: a buyer over the inherited cap is told the
    number, before the checkout is consumed, and can send the same checkout
    again with a shorter list.
    """
    email = _checkout_email(session)
    if not email:
        raise _Refused(json_response(403, {"ok": False, "error": _NO_CHECKOUT_EMAIL}))
    bought: list[tuple[str, str]] = []  # (plan, the checkout that bought it)
    unsettled: list[str] = []  # checkouts whose plan nothing has read yet
    for row in _purchase_rows(bundles):
        key = str(row.get("bundle_id") or "")
        prefix = next((p for p in (SESSION_PREFIX, CHECKOUT_PREFIX) if key.startswith(p)), "")
        if not prefix:
            continue
        prior = key[len(prefix) :]
        if not prior or prior == session_id:
            continue
        if str(row.get("email") or "").strip().casefold() != email:
            continue
        plan = str(row.get("plan") or "")
        if plan in ONE_TIME_PLANS:
            bought.append((plan, prior))
        elif plan not in SUBSCRIPTION_PLANS:
            # "unverified" from the webhook, or a value written by a version of
            # it this code has not met. Either way it is not evidence that this
            # buyer bought nothing, and treating it as such is how a real
            # customer gets told they never paid.
            unsettled.append(prior)
    widest = max((PLAN_AGENCY_CAPS[plan] for plan, _ in bought), default=0)
    if unsettled and widest < _WIDEST_ONE_TIME_CAP:
        if len(unsettled) > _UNSETTLED_CHECKOUT_READS:
            print(
                json.dumps(
                    {
                        "event": "entitlement_unsettled",
                        "session_id": session_id,
                        "unsettled_checkouts": len(unsettled),
                    }
                )
            )
            raise _Refused(json_response(502, {"ok": False, "error": _CANNOT_SETTLE_PRIOR}))
        for prior in unsettled:
            try:
                settled = checkout_plan(prior)
            except UpstreamError as err:
                # 404 is Stripe saying it has no such session: a stale row, and
                # not evidence either way, so it is skipped. Anything else is an
                # outage, and an outage must not be reported to a buyer as
                # "you never bought a bundle".
                if err.status == 404:
                    continue
                raise _Refused(
                    json_response(502, {"ok": False, "error": _CANNOT_SETTLE_PRIOR})
                ) from err
            if settled and settled[1] in ONE_TIME_PLANS:
                bought.append((settled[1], prior))
    if not bought:
        raise _Refused(json_response(403, {"ok": False, "error": _NO_PRIOR_BUNDLE}))
    plan, prior = max(bought, key=lambda found: PLAN_AGENCY_CAPS[found[0]])
    return _Inherited(PLAN_AGENCY_CAPS[plan], plan, prior)


def _agency_cap(bundles: Any, session: dict[str, Any], session_id: str, plan: str) -> _Inherited:
    """The cap this checkout is held to, and where it came from.

    A one-time bundle is its own entitlement. A refresh is not: it renews one,
    and covers what that one covered. The plan's own number in
    PLAN_AGENCY_CAPS stays a ceiling in both cases, so an inherited cap can
    narrow a refresh and can never widen it.
    """
    ceiling = PLAN_AGENCY_CAPS[plan]
    if plan not in SUBSCRIPTION_PLANS:
        return _Inherited(ceiling, plan, session_id)
    inherited = _inherited_cap(bundles, session, session_id)
    return inherited._replace(cap=min(ceiling, inherited.cap))


def _record_subscription(
    session: dict[str, Any], request: Any, *, price: str, plan: str, entitlement: _Inherited
) -> None:
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
            # What this subscription renews, recorded at purchase time. The
            # stored request is already held to this number, but the number
            # itself has to travel with the subscription: a refresh that
            # re-derived it later would read today's plan caps rather than the
            # bundle this buyer actually bought, and the refresh checks it
            # again every month against the list it is about to send.
            "agency_cap": entitlement.cap,
            "renews_plan": entitlement.plan,
            "renews_session": entitlement.session_id,
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

    bundles = table("BUNDLES_TABLE")
    try:
        session, price, plan = _paid_purchase(session_id)
        # Before the agency list is even read, and long before the checkout is
        # claimed: a refresh with no bundle to renew is refused here, so the
        # buyer still holds an unused checkout and can cancel it rather than
        # being left having paid for a subscription that built nothing.
        entitlement = _agency_cap(bundles, session, session_id, plan)
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
        request = parse_request(raw, max_agencies=entitlement.cap)
    except BundleError as err:
        return json_response(400, {"ok": False, "error": str(err)})

    if not _claim_session(bundles, session_id, request.bundle_id, plan, _checkout_email(session)):
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
    # The promise, computed once, here, from Stripe's own record of when the
    # money moved. Not from the moment this form was submitted: a buyer who
    # pays on Friday and fills the form in on Monday was promised two business
    # days from Friday, and anchoring on the form would quietly hand us the
    # weekend. Stripe has always set `created`; if it ever does not, falling
    # back to now can only make the promise later than it should be, so the
    # row records which anchor was used rather than leaving that unanswerable.
    checkout_epoch = session.get("created")
    anchored = "checkout" if isinstance(checkout_epoch, int | float) else "received"
    checkout_at = (
        deadline.from_epoch(int(checkout_epoch))
        if anchored == "checkout"
        else dt.datetime.now(dt.UTC)
    )
    row = bundle_row(
        request.as_dict(),
        source="checkout",
        session_id=session_id,
        deliver_by_epoch=deadline.deadline_epoch(checkout_at),
    )
    row["deliver_by_anchor"] = anchored
    bundles.put_item(Item=row)

    _record_subscription(session, request, price=price, plan=plan, entitlement=entitlement)

    try:
        # The workflow carries the promised date so the delivery email can
        # state the commitment it is meeting. Carried, not recomputed there:
        # one function decides this date, and it has already decided.
        dispatch = request.as_dict()
        dispatch["promised_by"] = deadline.spoken_date(deadline.deadline_date(checkout_at))
        dispatch_bundle_workflow(workflow_inputs(dispatch))
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
    # The date travels to the page rather than being recomputed there. The
    # promise is one function in one language; a browser working it out again
    # would be a second implementation of a refund liability, and the two
    # would disagree the first time a public holiday fell between them.
    return json_response(
        200,
        {
            "ok": True,
            "bundle_id": request.bundle_id,
            "deliver_by": deadline.deadline_date(checkout_at).isoformat(),
            "promise": deadline.promise_sentence(checkout_at),
        },
    )


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
    key = archive_key(bundle_id)
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
