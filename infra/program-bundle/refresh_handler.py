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
"""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

from common import (
    UpstreamError,
    bundle_row,
    dispatch_bundle_workflow,
    now_iso,
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


def refresh(*, subscriptions: Any, bundles: Any, now: dt.datetime | None = None) -> dict[str, int]:
    """Dispatch a refresh for every due subscription. Returns counts."""
    current = now or dt.datetime.now(dt.UTC)
    counts = {"scanned": 0, "due": 0, "dispatched": 0, "failed": 0}
    for row in _scan_all(subscriptions):
        counts["scanned"] += 1
        if not _due(row, now=current):
            continue
        counts["due"] += 1
        try:
            request = json.loads(str(row.get("request") or "{}"))
        except ValueError:
            request = {}
        if not isinstance(request, dict) or not request.get("agency_ids"):
            counts["failed"] += 1
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
    """EventBridge entrypoint. The event carries nothing the handler reads."""
    counts = refresh(subscriptions=table("SUBSCRIPTIONS_TABLE"), bundles=table("BUNDLES_TABLE"))
    print(json.dumps({"refresh": counts, "at": now_iso()}))
    return {"ok": True, **counts, "dry_run": os.environ.get("DRY_RUN", "0") == "1"}
