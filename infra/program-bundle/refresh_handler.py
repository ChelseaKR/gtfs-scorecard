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
        "dispatched": 0,
        "would_dispatch": 0,
        "failed": 0,
    }
    plans = price_plans()
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
            counts["failed"] += 1
            continue
        if dry_run:
            ids = request["agency_ids"]
            count = len(ids) if isinstance(ids, list) else len(str(ids).split(","))
            print(f"dry run: would refresh {row.get('id')} ({count} agencies)")
            counts["would_dispatch"] += 1
            continue
        request["bundle_id"] = new_bundle_id()
        request["cadence"] = "monthly"
        try:
            dispatch_bundle_workflow(workflow_inputs(request))
        except UpstreamError as err:
            print(f"refresh {row.get('id')}: dispatch failed: {err}")
            counts["failed"] += 1
            continue
        bundles.put_item(Item=bundle_row(request, source="refresh"))
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
    counts = refresh(
        subscriptions=table("SUBSCRIPTIONS_TABLE"),
        bundles=table("BUNDLES_TABLE"),
        dry_run=dry_run,
    )
    print(json.dumps({"refresh": counts, "dry_run": dry_run, "at": now_iso()}))
    return {"ok": True, "payments_enabled": True, **counts, "dry_run": dry_run}
