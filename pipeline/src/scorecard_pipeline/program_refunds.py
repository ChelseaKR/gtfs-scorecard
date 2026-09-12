"""Which paid orders are past the delivery promise, and what to do about them.

``/bundle/`` commits to delivery within two business days "or the purchase is
refunded". The daily reconciler notices a breach and says so in a public
GitHub issue, but that issue carries counts and nothing else: the repository
is public, and a bundle id is a download capability while the delivery address
is a customer's own. So the signal is public and the detail is not.

This is the detail half. It runs on the operator's machine, with the
operator's own AWS credentials, reads the table directly, and prints the
Stripe reference for each breached order together with the commands that
refund it.

**It refunds nothing.** It has no Stripe credential, makes no Stripe call, and
prints commands rather than running them. The key deployed in the Lambdas is
restricted to reading Checkout Sessions and cannot refund at all, which is the
correct posture and is not changed by anything here: a credential that can
move money should not be sitting in a scheduled job. The person decides, and
the person runs it.

The breach rule itself lives in ``deadline.is_breached`` and is shared with the
reconciler, so the alert and this list cannot disagree about the same order.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from typing import Any

from . import deadline
from .bundle import archive_key

_SESSION_PREFIX = "session#"
_CHECKOUT_PREFIX = "checkout#"


def breached_orders(
    rows: Iterable[dict[str, Any]],
    *,
    archive_present: Callable[[str], bool],
    now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    """Every capability row past its promise with no archive, worst first.

    ``archive_present`` answers "is the built bundle in the bucket" for one
    bundle id, so the pure part of this stays testable without AWS.
    """
    current = now or dt.datetime.now(dt.UTC)
    found: list[dict[str, Any]] = []
    for row in rows:
        bundle_id = str(row.get("bundle_id") or "")
        if not bundle_id or bundle_id.startswith((_SESSION_PREFIX, _CHECKOUT_PREFIX)):
            continue
        promised = row.get("deliver_by_epoch")
        if not deadline.is_breached(
            promised, now=current, archive_present=archive_present(bundle_id)
        ):
            continue
        # is_breached only returns True for a readable number, so this cannot
        # be None; narrowed here rather than asserted, because a broken
        # assumption should print a row without a date, not crash a report
        # somebody is running because money may be owed.
        late = deadline.days_late(promised, now=current) or 0.0
        promised_day = dt.datetime.fromtimestamp(float(promised or 0), tz=dt.UTC).date()
        found.append(
            {
                "bundle_id": bundle_id,
                "session_id": str(row.get("session_id") or ""),
                "deliver_to": str(row.get("deliver_to") or ""),
                "program_name": str(row.get("program_name") or ""),
                "promised_by": promised_day.isoformat(),
                "days_late": round(late, 1),
                "archive_key": archive_key(bundle_id),
            }
        )
    found.sort(key=lambda order: float(order["days_late"]), reverse=True)
    return found


def refund_commands(order: dict[str, Any]) -> list[str]:
    """The two commands that refund one order, ready to paste.

    Printed, never run. A Checkout Session names a payment intent rather than
    a charge, so the reference has to be read back before the refund; showing
    both steps is also what lets the operator check they are refunding the
    order they think they are before any money moves.
    """
    session = order.get("session_id") or ""
    if not session:
        return [
            "# no checkout session recorded on this row; find the payment in the",
            "# Stripe dashboard by the customer's email address before refunding.",
        ]
    return [
        f"stripe checkout sessions retrieve {session}",
        f'stripe refunds create --payment-intent "$(stripe checkout sessions retrieve {session} '
        '--format json | jq -r .payment_intent)" --reason requested_by_customer',
    ]


def render(orders: list[dict[str, Any]], *, now: dt.datetime | None = None) -> str:
    """The operator's report. Local output, so it may name the order."""
    current = now or dt.datetime.now(dt.UTC)
    if not orders:
        return (
            f"No program orders are past the {deadline.PROVISIONING_BUSINESS_DAYS}-business-day "
            f"delivery promise as at {current.date().isoformat()}.\n"
        )
    lines = [
        f"{len(orders)} program order{'' if len(orders) == 1 else 's'} past the "
        f"{deadline.PROVISIONING_BUSINESS_DAYS}-business-day delivery promise "
        f"as at {current.date().isoformat()}.",
        "",
        "/bundle/ says the purchase is refunded if delivery is later than that.",
        "Either build it (re-dispatch report-bundle.yml with the bundle id) or",
        "refund it. This command does neither; it only tells you which.",
    ]
    for order in orders:
        lines += [
            "",
            f"  bundle_id   {order['bundle_id']}",
            f"  promised by {order['promised_by']}  ({order['days_late']} days late)",
            f"  program     {order['program_name']}",
            f"  deliver to  {order['deliver_to']}",
            f"  archive     s3://<artifacts bucket>/{order['archive_key']}  (absent)",
            "",
        ]
        lines += [f"    {command}" for command in refund_commands(order)]
    return "\n".join(lines) + "\n"
