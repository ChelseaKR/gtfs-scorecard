"""Per-subscriber feed-health email digests (the opt-in retention loop).

`alerts.py` builds the global list of feeds that need attention. This filters
that list to each opt-in subscriber's agencies and renders the email they
receive: an agency manager or a program liaison only hears from us when one of
the feeds they follow needs action, and an all-clear sends nothing.

Subscriptions live in `subscriptions.yaml` at the repo root. The build and the
send are kept separate (as alerts.py is): everything here is pure and testable
against fixture artifacts; the actual SES send is a thin, lazily-imported
function so the core needs no AWS dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from .alerts import Digest, render_digest
from .config import repo_root
from .portfolio_digest import PortfolioDigest, render_portfolio_digest

# Enough to catch a typo without policing addresses, but restricted to the
# characters a real address uses, so a registered address can't smuggle URL or
# query syntax into the confirm/unsubscribe links built from it.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

# The alert kinds a subscriber can opt into; mirrors AlertItem.kind in alerts.py.
ALERT_KINDS = frozenset({"expiry", "regression", "anomaly"})


class SubscriptionError(ValueError):
    """subscriptions.yaml is malformed; the message says where."""


@dataclass(frozen=True)
class Subscriber:
    """One opt-in recipient: the agencies they follow, the alert kinds they want,
    and whether they have confirmed their address.

    `verified` is the consent gate. It defaults to false, and an unverified
    subscriber is never emailed (see build_emails), so nothing goes to an address
    that has not confirmed. `kinds` is the opt-in granularity (None means every
    kind), so an agency can ask for expiry warnings only. `rollup_ids` is a
    separate opt-in (ADR 0004 amendment): a liaison adds a cohort id to also
    receive that rollup's weekly portfolio digest. It rides the same verified
    gate — an unverified subscriber is never sent a rollup digest either."""

    email: str
    agency_ids: frozenset[str] | None  # None means "every tracked agency"
    verified: bool = False
    kinds: frozenset[str] | None = None  # None means "every alert kind"
    unsub_token: str = ""  # one-click unsubscribe; only set for stored subscribers
    rollup_ids: frozenset[str] | None = None  # rollups opted into for the weekly digest

    def follows(self, agency_id: str) -> bool:
        return self.agency_ids is None or agency_id in self.agency_ids

    def follows_rollup(self, rollup_id: str) -> bool:
        return self.rollup_ids is not None and rollup_id in self.rollup_ids

    def wants(self, agency_id: str, kind: str) -> bool:
        """Whether this subscriber should hear about a given agency and kind."""
        in_kinds = self.kinds is None or kind in self.kinds
        return self.follows(agency_id) and in_kinds


@dataclass(frozen=True)
class Email:
    """A rendered digest email, ready for any transport."""

    to: str
    subject: str
    body: str


def parse_subscribers(raw: object) -> list[Subscriber]:
    """Validate parsed YAML into Subscriber records."""
    if not isinstance(raw, dict) or not isinstance(raw.get("subscribers"), list):
        raise SubscriptionError("subscriptions.yaml must have a top-level 'subscribers:' list")
    subscribers: list[Subscriber] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw["subscribers"]):
        label = f"subscriber {i + 1}"
        if not isinstance(entry, dict):
            raise SubscriptionError(f"{label}: must be a mapping of fields")
        email = entry.get("email")
        if not isinstance(email, str) or not EMAIL_RE.match(email):
            raise SubscriptionError(f"{label}: a valid email is required, got {email!r}")
        if email in seen:
            raise SubscriptionError(f"{label}: duplicate email {email!r}")
        seen.add(email)
        if entry.get("all") is True:
            agency_ids: frozenset[str] | None = None
        else:
            agencies = entry.get("agencies")
            if not isinstance(agencies, list) or not agencies:
                raise SubscriptionError(f"{label}: needs 'agencies: [...]' or 'all: true'")
            agency_ids = frozenset(str(a) for a in agencies)

        kinds_raw = entry.get("kinds")
        if kinds_raw is None:
            kinds: frozenset[str] | None = None
        elif isinstance(kinds_raw, list) and kinds_raw:
            unknown = {str(k) for k in kinds_raw} - ALERT_KINDS
            if unknown:
                raise SubscriptionError(
                    f"{label}: unknown alert kind(s) {sorted(unknown)}; "
                    f"expected from {sorted(ALERT_KINDS)}"
                )
            kinds = frozenset(str(k) for k in kinds_raw)
        else:
            raise SubscriptionError(f"{label}: 'kinds' must be a non-empty list if present")

        rollups_raw = entry.get("rollups")
        if rollups_raw is None:
            rollup_ids: frozenset[str] | None = None
        elif isinstance(rollups_raw, list) and rollups_raw:
            rollup_ids = frozenset(str(r) for r in rollups_raw)
        else:
            raise SubscriptionError(f"{label}: 'rollups' must be a non-empty list if present")

        subscribers.append(
            Subscriber(
                email=email,
                agency_ids=agency_ids,
                verified=bool(entry.get("verified", False)),
                kinds=kinds,
                rollup_ids=rollup_ids,
            )
        )
    return subscribers


def load_subscribers(path: Path | None = None) -> list[Subscriber]:
    """Read subscriptions.yaml; an absent file means no subscribers (not an error)."""
    config_path = path or repo_root() / "subscriptions.yaml"
    if not config_path.exists():
        return []
    return parse_subscribers(yaml.safe_load(config_path.read_text()))


def subscriber_from_item(item: dict[str, Any]) -> Subscriber:
    """Map one DynamoDB item (boto3 resource form: native sets/bools) to a
    Subscriber. The dynamic store holds real opt-in addresses, which is why they
    live here and never in the committed YAML."""
    if item.get("all") is True:
        agency_ids: frozenset[str] | None = None
    else:
        agency_ids = frozenset(str(a) for a in (item.get("agencies") or []))
    kinds_raw = item.get("kinds")
    kinds = frozenset(str(k) for k in kinds_raw) if kinds_raw else None
    rollups_raw = item.get("rollups")
    rollup_ids = frozenset(str(r) for r in rollups_raw) if rollups_raw else None
    return Subscriber(
        email=str(item["email"]),
        agency_ids=agency_ids,
        verified=bool(item.get("verified", False)),
        kinds=kinds,
        unsub_token=str(item.get("unsub_token", "")),
        rollup_ids=rollup_ids,
    )


def load_subscribers_from_dynamo(table_name: str, region: str = "us-west-2") -> list[Subscriber]:
    """Read every subscriber from the DynamoDB store. boto3 is imported lazily so
    the core pipeline keeps no AWS dependency; only this path needs it."""
    import boto3  # type: ignore[import-not-found]  # noqa: PLC0415 - lazy, optional dep

    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    items: list[dict[str, Any]] = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return [subscriber_from_item(item) for item in items]


def personal_digest(subscriber: Subscriber, digest: Digest) -> Digest:
    """The digest narrowed to the agencies and alert kinds this subscriber wants."""
    items = [item for item in digest.items if subscriber.wants(item.agency_id, item.kind)]
    return Digest(as_of=digest.as_of, items=items)


def _subject(digest: Digest) -> str:
    agencies = len({item.agency_id for item in digest.items})
    noun = "feed needs" if agencies == 1 else "feeds need"
    return f"GTFS Scorecard: {agencies} {noun} attention ({digest.as_of.isoformat()})"


def _unsubscribe_footer(subscriber: Subscriber, base: str | None) -> str:
    """A one-click unsubscribe line for an alert email, if we can build one."""
    if not base or not subscriber.unsub_token:
        return ""
    link = (
        f"{base.rstrip('/')}/unsubscribe"
        f"?email={quote(subscriber.email, safe='')}"
        f"&token={quote(subscriber.unsub_token, safe='')}"
    )
    return f"\n\n---\nStop these alerts at any time:\n  {link}\n"


def build_emails(
    subscribers: list[Subscriber], digest: Digest, unsubscribe_base: str | None = None
) -> list[Email]:
    """One email per verified subscriber who has at least one item to act on.

    Two gates: an unverified subscriber is skipped entirely (consent), and a
    subscriber whose followed feeds are all healthy gets nothing (the all-clear
    is silence). Each email carries an unsubscribe link when unsubscribe_base is
    set (the alerts API base)."""
    emails: list[Email] = []
    for subscriber in subscribers:
        if not subscriber.verified:
            continue
        personal = personal_digest(subscriber, digest)
        if not personal.items:
            continue
        body = render_digest(personal) + _unsubscribe_footer(subscriber, unsubscribe_base)
        emails.append(Email(to=subscriber.email, subject=_subject(personal), body=body))
    return emails


def build_portfolio_emails(
    subscribers: list[Subscriber],
    digests: dict[str, PortfolioDigest],
    unsubscribe_base: str | None = None,
) -> list[Email]:
    """One weekly portfolio-digest email per verified subscriber who opted into a
    rollup that has a digest this week.

    The same consent gate as the alert path applies: an unverified subscriber is
    skipped entirely. Unlike the alert digest, a scheduled cohort digest is sent
    on the regular cadence even when it is all-clear — that reassurance is the
    point of a weekly rollup, and the volume is low and opt-in. A subscriber's
    opted-in rollups are combined into one email. `digests` maps rollup id to the
    built PortfolioDigest for the week."""
    emails: list[Email] = []
    for subscriber in subscribers:
        if not subscriber.verified or not subscriber.rollup_ids:
            continue
        mine = [
            digests[rollup_id]
            for rollup_id in sorted(subscriber.rollup_ids)
            if rollup_id in digests
        ]
        if not mine:
            continue
        body = "\n\n".join(render_portfolio_digest(digest) for digest in mine)
        body += _unsubscribe_footer(subscriber, unsubscribe_base)
        as_of = mine[0].as_of
        subject = f"GTFS Scorecard: weekly portfolio digest ({as_of.isoformat()})"
        emails.append(Email(to=subscriber.email, subject=subject, body=body))
    return emails


def verification_email(
    email: str, token: str, base_url: str = "https://gtfsscorecard.org"
) -> Email:
    """The double opt-in confirmation email. Sending this, and only marking a
    subscriber verified when the link is followed, is what lets us promise that
    no agency receives mail it did not ask for."""
    link = f"{base_url}/confirm?token={token}"
    body = (
        "You (or someone using this address) asked for GTFS Scorecard feed-health "
        "alerts.\n\n"
        f"Confirm to start receiving them:\n  {link}\n\n"
        "If you did not request this, ignore this email and nothing will be sent.\n"
    )
    return Email(to=email, subject="Confirm your GTFS Scorecard alerts", body=body)


def send_via_ses(emails: list[Email], sender: str, region: str = "us-west-2") -> int:
    """Send each email through Amazon SES. boto3 is imported lazily so the core
    pipeline has no AWS dependency; only the send path needs it."""
    import boto3  # noqa: PLC0415 - lazy, optional dep

    ses = boto3.client("ses", region_name=region)
    for email in emails:
        ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [email.to]},
            Message={
                "Subject": {"Data": email.subject},
                "Body": {"Text": {"Data": email.body}},
            },
        )
    return len(emails)
