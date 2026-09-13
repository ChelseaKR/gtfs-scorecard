"""Weekly refresh for subscribed programs (docs/program-plan.md).

EventBridge invokes this once a week. For every subscription whose status is
``active`` and whose last refresh is at least ``REFRESH_DAYS`` old, it mints a
new bundle id, stores the capability row, re-dispatches report-bundle.yml
with the stored request, and stamps the subscription's ``last_refresh``.

"Monthly" is enforced here as a minimum interval, not a calendar day: a
subscription refreshed on the 3rd is eligible again on the 31st and runs on
the next weekly tick after that. That keeps the schedule one cron rule and
lets a make-good re-run happen without waiting a month.

A dispatch failure for one subscription is logged and does not stop the
others; the next tick tries again because ``last_refresh`` was not moved.

Two more checks before anything is dispatched. A row whose stored price is
not one of the configured refresh prices is skipped and counted as
``not_on_plan``: that is a subscription that moved off the refresh prices, or
a row left over from test mode once live price ids are configured. And the
whole run does nothing unless PAYMENTS_ENABLED is "1"; the EventBridge rule
is disabled with the same gate, so this only matters for a hand invoke.

``not_on_plan`` is a claim about a subscription, so it is only ever reported
when the configuration is good enough to make it. If no refresh price is
configured at all -- a blank, unparseable, or dropped ``STRIPE_PRICE_IDS`` --
every row would fall into it and the tick would answer ``ok`` while no
subscriber was ever refreshed again. That case raises ``ConfigurationError``
and fails the invocation instead.

A third check: a subscription renews a bundle and covers the agencies that
bundle covered, and the cap it was sold under travels on the row as
``agency_cap`` (setup_handler._record_subscription). A stored list longer than
that cap is counted ``over_cap`` and dispatched to nobody -- refused, not
trimmed, because choosing which agencies to drop is not this job's call. The
setup route already holds the stored list to the cap, so nothing the product
does reaches this; what it stops is a hand-edited row quietly sending more
than was ever bought, every month. A row with no readable ``agency_cap`` is
left alone: one predates this rule, and a missing field is not a cap.

Dry run: with DRY_RUN=1 in the environment, or ``{"dry_run": true}`` as the
invoke payload, the run scans and logs what it would dispatch (subscription
id and agency count) and changes nothing: no dispatch, no capability row, no
``last_refresh``. EventBridge's scheduled event never carries the flag.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

from common import (
    SUBSCRIPTION_PLANS,
    UpstreamError,
    bundle_row,
    dispatch_bundle_workflow,
    now_iso,
    payments_enabled,
    price_plans,
    table,
    workflow_inputs,
)

from scorecard_pipeline.bundle import new_bundle_id

REFRESH_DAYS = 28


class ConfigurationError(RuntimeError):
    """The run cannot tell a subscription's plan from its price, because no
    refresh price is configured. Raised rather than reported per row: an
    unreadable or blank ``STRIPE_PRICE_IDS`` would otherwise make every
    subscriber look like one that had left the plan, and the tick would say
    ``ok`` while nobody was ever refreshed again."""


def _due(row: dict[str, Any], *, now: dt.datetime) -> bool:
    if str(row.get("status") or "") != "active":
        return False
    last = str(row.get("last_refresh") or "")
    if not last:
        return True
    try:
        stamp = dt.datetime.fromisoformat(last)
    except ValueError:
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.UTC)
    return now - stamp >= dt.timedelta(days=REFRESH_DAYS)


def _recorded_cap(row: dict[str, Any]) -> int | None:
    """The agency cap this subscription was sold under, or None.

    None is "no cap was recorded", which is what a row written before the
    entitlement rule existed looks like, and it is not a cap of zero and not a
    cap of a hundred. Those rows are left alone: cutting off a paying
    subscriber on the strength of a missing field would be an absence dressed
    up as a decision. A value that is present but unreadable is treated the
    same way, and both are visible in the run's counts rather than inferred.
    """
    raw = row.get("agency_cap")
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        cap = int(raw)
    except (TypeError, ValueError):
        return None
    return cap if cap > 0 else None


def _scan_all(subscriptions: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {}
    while True:
        page = subscriptions.scan(**kwargs)
        rows.extend(page.get("Items") or [])
        start = page.get("LastEvaluatedKey")
        if not start:
            return rows
        kwargs = {"ExclusiveStartKey": start}


def refresh(
    *,
    subscriptions: Any,
    bundles: Any,
    now: dt.datetime | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Dispatch a refresh for every due subscription. Returns counts."""
    current = now or dt.datetime.now(dt.UTC)
    counts = {
        "scanned": 0,
        "due": 0,
        "not_on_plan": 0,
        "no_request": 0,
        "over_cap": 0,
        "dispatched": 0,
        "would_dispatch": 0,
        "failed": 0,
    }
    plans = price_plans()
    if not any(plan in SUBSCRIPTION_PLANS for plan in plans.values()):
        # Every row would now be counted `not_on_plan`, which is a statement
        # about the subscription. It would not be true: the configuration is
        # what is missing, and reporting a config failure as a per-row fact
        # would silently and permanently stop every paying subscriber while
        # the run still answered ok. Refuse the whole run instead.
        raise ConfigurationError(
            "STRIPE_PRICE_IDS configures no refresh price, so no subscription "
            "can be matched to a plan; refusing the run rather than reporting "
            "every subscriber as not on a plan"
        )
    for row in _scan_all(subscriptions):
        counts["scanned"] += 1
        if not _due(row, now=current):
            continue
        if plans.get(str(row.get("price") or "")) not in SUBSCRIPTION_PLANS:
            counts["not_on_plan"] += 1
            continue
        counts["due"] += 1
        try:
            request = json.loads(str(row.get("request") or "{}"))
        except ValueError:
            request = {}
        if not isinstance(request, dict) or not request.get("agency_ids"):
            # A subscription with nothing to build: the webhook created the
            # row at checkout and the buyer never finished the setup form, so
            # they are being billed for nothing. Counted apart from `failed`,
            # which now means only that GitHub refused the dispatch; the two
            # need different answers, and rolling them together hid a paying
            # customer inside a retry statistic.
            print(f"refresh {row.get('id')}: billed, but no setup request was ever stored")
            counts["no_request"] += 1
            continue
        ids = request["agency_ids"]
        count = len(ids) if isinstance(ids, list) else len([i for i in str(ids).split(",") if i])
        cap = _recorded_cap(row)
        if cap is not None and count > cap:
            # A subscription renews a bundle and covers what that bundle
            # covered (setup_handler._inherited_cap), and the setup route holds
            # the stored list to that number, so this is unreachable by any
            # path through the product. It is here because the alternative to
            # refusing is sending more than was ever bought, every month,
            # silently. Refused rather than trimmed: which agencies to drop is
            # not this job's call.
            print(f"refresh {row.get('id')}: {count} agencies stored against a cap of {cap}")
            counts["over_cap"] += 1
            continue
        if dry_run:
            print(f"dry run: would refresh {row.get('id')} ({count} agencies)")
            counts["would_dispatch"] += 1
            continue
        request["bundle_id"] = new_bundle_id()
        request["cadence"] = "monthly"
        # The capability row first. The workflow uploads the archive and emails
        # the link on its own clock; if this Lambda times out between the
        # dispatch and the put, the buyer gets a link to a row that does not
        # exist and reads "expired or never issued" for a bundle sitting in
        # the bucket. A row with no archive behind it is the harmless order.
        bundles.put_item(Item=bundle_row(request, source="refresh"))
        try:
            dispatch_bundle_workflow(workflow_inputs(request))
        except UpstreamError as err:
            print(f"refresh {row.get('id')}: dispatch failed: {err}")
            counts["failed"] += 1
            continue
        subscriptions.update_item(
            Key={"id": str(row["id"])},
            UpdateExpression="SET last_refresh = :t, last_bundle_id = :b",
            ExpressionAttributeValues={":t": now_iso(), ":b": request["bundle_id"]},
        )
        counts["dispatched"] += 1
    return counts


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """EventBridge entrypoint. The scheduled event carries nothing the
    handler reads; a hand invoke may pass ``{"dry_run": true}``."""
    dry_run = os.environ.get("DRY_RUN", "0") == "1" or (
        isinstance(event, dict) and event.get("dry_run") is True
    )
    if not payments_enabled():
        print(json.dumps({"refresh": "skipped: PAYMENTS_ENABLED is not 1", "at": now_iso()}))
        return {"ok": True, "payments_enabled": False, "dry_run": dry_run}
    try:
        counts = refresh(
            subscriptions=table("SUBSCRIPTIONS_TABLE"),
            bundles=table("BUNDLES_TABLE"),
            dry_run=dry_run,
        )
    except ConfigurationError as err:
        # Raised, not returned: a failed invocation is the only signal
        # EventBridge and CloudWatch can alarm on. Returning ok here is how a
        # broken price map would refresh nobody, quietly, for months.
        print(json.dumps({"refresh": "refused", "reason": str(err), "at": now_iso()}))
        raise
    print(json.dumps({"refresh": counts, "dry_run": dry_run, "at": now_iso()}))
    return {"ok": True, "payments_enabled": True, **counts, "dry_run": dry_run}
