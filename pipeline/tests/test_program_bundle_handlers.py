"""Unit tests for the program-bundle Lambdas (infra/program-bundle): the
Stripe signature check, the post-checkout setup route (paid gate, what was
actually bought, the plan's agency cap, idempotent session claim, dispatch),
the download route, the webhook's event handling, the weekly refresh, and
the daily reconciler that looks for orders which bought nothing.
Same harness as test_infra_handlers.py: the modules load from their files,
boto3 stays lazy, tables are fakes, and the two network calls (GitHub
dispatch, Stripe session read) are monkeypatched.

The Stripe event fixtures are shaped like Stripe's, with ids that follow
its prefixes but are not real objects, and no key-shaped strings anywhere.

The price ids below stand in for the four in `terraform.tfvars`. A session is
only ever served through `_stripe` so that the session object and its line
items come from one fixture: a test that paid for `bundle_25` cannot
accidentally describe itself as `bundle_100` on one of the two reads."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE_DIR = REPO / "infra" / "program-bundle"
SIGNING_SECRET = "test-signing-secret"

# The four configured prices, and one that belongs to something else on the
# same Stripe account (the family-greenhouse case the setup route must refuse).
PRICE_BUNDLE_25 = "price_bundle25example"
PRICE_BUNDLE_100 = "price_bundle100example"
PRICE_REFRESH_MO = "price_refreshmoexample"
PRICE_REFRESH_YR = "price_refreshyrexample"
PRICE_FOREIGN = "price_somethingelseexample"
CONFIGURED_PRICES = json.dumps(
    {
        "bundle_25": PRICE_BUNDLE_25,
        "bundle_100": PRICE_BUNDLE_100,
        "refresh_mo": PRICE_REFRESH_MO,
        "refresh_yr": PRICE_REFRESH_YR,
    }
)


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # the handlers import `common` by name, as the Lambda does
    spec.loader.exec_module(mod)
    return mod


common = _load("common")
setup_handler = _load("setup_handler")
webhook_handler = _load("webhook_handler")
refresh_handler = _load("refresh_handler")
reconcile_handler = _load("reconcile_handler")


class _ConditionExpression:
    """Evaluate one DynamoDB condition expression against the existing item.

    The handlers' idempotency is a condition expression, so a fake that
    ignores the expression and answers "the key is present" proves nothing
    about it: the whole `_claim_session` argument would pass with the
    condition deleted. This reads the real string instead.

    The grammar is exactly what these handlers write and no more:
    ``attribute_exists(a)``, ``attribute_not_exists(a)``, ``a = :v``,
    ``a <> :v``, ``AND``, ``OR`` and parentheses, with ``#n`` names resolved
    through ExpressionAttributeNames. ``item`` is None when the row does not
    exist. A comparison against an absent attribute is false, as DynamoDB
    evaluates it -- which is why a `session#` row written before
    `dispatch_state` existed refuses a retry rather than allowing one.
    """

    def __init__(
        self,
        expression: str,
        item: dict[str, Any] | None,
        values: dict[str, Any] | None,
        names: dict[str, str] | None,
    ) -> None:
        self.tokens = expression.replace("(", " ( ").replace(")", " ) ").split()
        self.at = 0
        self.item = item
        self.values = values or {}
        self.names = names or {}

    def evaluate(self) -> bool:
        result = self._or()
        assert self.at == len(self.tokens), f"unparsed tokens: {self.tokens[self.at :]}"
        return result

    def _next(self) -> str:
        token = self.tokens[self.at]
        self.at += 1
        return token

    def _peek(self) -> str:
        return self.tokens[self.at] if self.at < len(self.tokens) else ""

    def _or(self) -> bool:
        value = self._and()
        while self._peek() == "OR":
            self.at += 1
            # Both sides are always evaluated: the right side has to consume
            # its tokens whatever the left side answered.
            value = self._and() or value
        return value

    def _and(self) -> bool:
        value = self._term()
        while self._peek() == "AND":
            self.at += 1
            value = self._term() and value
        return value

    def _term(self) -> bool:
        token = self._next()
        if token == "(":
            value = self._or()
            assert self._next() == ")"
            return value
        if token in ("attribute_exists", "attribute_not_exists"):
            assert self._next() == "("
            attribute = self.names.get(self._next(), self.tokens[self.at - 1])
            assert self._next() == ")"
            present = self.item is not None and attribute in self.item
            return present if token == "attribute_exists" else not present
        attribute = self.names.get(token, token)
        operator = self._next()
        placeholder = self._next()
        assert placeholder in self.values, f"no value for {placeholder}"
        if self.item is None or attribute not in self.item:
            return False
        actual, expected = self.item[attribute], self.values[placeholder]
        if operator == "=":
            return bool(actual == expected)
        if operator == "<>":
            return bool(actual != expected)
        raise AssertionError(f"unsupported operator {operator}")


class FakeTable:
    """Enough of a DynamoDB Table for these handlers: a dict with the
    conditional-put and update shapes they use."""

    def __init__(self, items: dict[str, dict[str, Any]] | None = None, key: str = "bundle_id"):
        self.key = key
        self.items: dict[str, dict[str, Any]] = dict(items or {})
        self.updates: list[dict[str, Any]] = []

    def _allows(self, key_value: str, kwargs: dict[str, Any]) -> bool:
        condition = kwargs.get("ConditionExpression")
        if not condition:
            return True
        return _ConditionExpression(
            condition,
            self.items.get(key_value),
            kwargs.get("ExpressionAttributeValues"),
            kwargs.get("ExpressionAttributeNames"),
        ).evaluate()

    def put_item(self, Item: dict[str, Any], **kwargs: Any) -> None:
        if not self._allows(Item[self.key], kwargs):
            raise ConditionalCheckFailedException(kwargs.get("ConditionExpression", ""))
        self.items[Item[self.key]] = dict(Item)

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        item = self.items.get(Key[self.key])
        return {"Item": item} if item else {}

    def update_item(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)
        key_value = kwargs["Key"][self.key]
        # Honouring the condition here is the difference between a test that
        # proves a foreign subscription creates no row and one that would
        # pass either way.
        if not self._allows(key_value, kwargs):
            raise ConditionalCheckFailedException(kwargs.get("ConditionExpression", ""))
        row = self.items.setdefault(key_value, {self.key: key_value})
        values = kwargs.get("ExpressionAttributeValues", {})
        names = kwargs.get("ExpressionAttributeNames", {})
        for clause in kwargs["UpdateExpression"].removeprefix("SET ").split(","):
            target, _, placeholder = clause.strip().partition(" = ")
            row[names.get(target, target)] = values[placeholder]

    def scan(self, **_: Any) -> dict[str, Any]:
        return {"Items": list(self.items.values())}


class ConditionalCheckFailedException(Exception):
    pass


def _sign(payload: bytes, *, secret: str = SIGNING_SECRET, at: int | None = None) -> str:
    stamp = int(time.time()) if at is None else at
    digest = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPO", "example/scorecard")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "test-restricted-key")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("ARTIFACTS_BUCKET", "example-artifacts")
    monkeypatch.setenv("SUBSCRIPTIONS_TABLE", "subs")
    monkeypatch.setenv("BUNDLES_TABLE", "bundles")
    # The deployed shape while the gate is open: the four price ids reach the
    # Lambdas, so they can tell what was bought. Tests that need the gate shut
    # or the prices missing take them away again.
    monkeypatch.setenv("PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_PRICE_IDS", CONFIGURED_PRICES)
    monkeypatch.delenv("DRY_RUN", raising=False)


@pytest.fixture
def tables(monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeTable]:
    fakes = {"SUBSCRIPTIONS_TABLE": FakeTable(key="id"), "BUNDLES_TABLE": FakeTable()}
    for mod in (common, setup_handler, webhook_handler, refresh_handler, reconcile_handler):
        monkeypatch.setattr(mod, "table", lambda env, fakes=fakes: fakes[env])
    return fakes


# ---------------------------------------------------------------------------
# common: signature verification and workflow inputs
# ---------------------------------------------------------------------------


def test_signature_accepts_a_fresh_correct_v1() -> None:
    body = b'{"id":"evt_1"}'
    assert common.verify_stripe_signature(body, _sign(body), SIGNING_SECRET)


def test_signature_refuses_wrong_secret_stale_timestamp_and_malformed_headers() -> None:
    body = b'{"id":"evt_1"}'
    assert not common.verify_stripe_signature(body, _sign(body, secret="other"), SIGNING_SECRET)
    old = int(time.time()) - common.SIGNATURE_TOLERANCE_SECONDS - 1
    assert not common.verify_stripe_signature(body, _sign(body, at=old), SIGNING_SECRET)
    assert not common.verify_stripe_signature(body, "v1=abc", SIGNING_SECRET)
    assert not common.verify_stripe_signature(body, "t=notanumber,v1=abc", SIGNING_SECRET)
    assert not common.verify_stripe_signature(body, _sign(body), "")
    assert not common.verify_stripe_signature(body, "", SIGNING_SECRET)


def test_signature_accepts_any_matching_v1_among_several() -> None:
    body = b"{}"
    good = _sign(body)
    header = good.replace(",v1=", ",v1=deadbeef,v1=")
    assert common.verify_stripe_signature(body, header, SIGNING_SECRET)


def test_workflow_inputs_flatten_ids_and_default_the_optional_fields() -> None:
    inputs = common.workflow_inputs(
        {
            "bundle_id": "a" * 32,
            "program_name": "P",
            "agency_ids": ["x", "y"],
            "deliver_to": "p@example.org",
        }
    )
    assert inputs == {
        "bundle_id": "a" * 32,
        "program_name": "P",
        "accent": "",
        "logo": "",
        "agency_ids": "x,y",
        "deliver_to": "p@example.org",
        "cadence": "one_time",
        "dispatch_key": common.dispatch_key("a" * 32),
        "promised_by": "",
    }


def test_the_dispatch_key_names_a_bundle_without_naming_it() -> None:
    """report-bundle.yml's artifact name and concurrency group are rendered on
    a public run page, and the bundle id is the download credential. This is
    what they carry instead: stable per bundle, different for every bundle,
    and no way back to the id it came from."""
    first, second = "a" * 32, "b" * 32
    key = common.dispatch_key(first)

    assert key == common.dispatch_key(first), "the same bundle must group with itself"
    assert key != common.dispatch_key(second), "two bundles must not share a group"
    assert first not in key and key not in first, "the key must not contain the id, or vice versa"
    assert len(key) == 16 and all(c in "0123456789abcdef" for c in key)
    # A truncated digest of a 128-bit token, so it is a name and not a hint.
    assert key == hashlib.sha256(first.encode()).hexdigest()[:16]


def test_dispatch_posts_to_the_workflow_dispatch_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(method: str, url: str, headers: dict[str, str], payload: Any = None) -> Any:
        calls.append((method, url, payload))
        return {}

    monkeypatch.setattr(common, "_request", fake_request)
    common.dispatch_bundle_workflow({"bundle_id": "b"})
    assert calls == [
        (
            "POST",
            "https://api.github.com/repos/example/scorecard/actions/workflows/report-bundle.yml/dispatches",
            {"ref": "main", "inputs": {"bundle_id": "b"}},
        )
    ]


def test_request_wraps_http_errors_as_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(common.urllib.request, "urlopen", boom)
    with pytest.raises(common.UpstreamError, match="failed"):
        common._request("GET", "https://api.stripe.com/v1/x", {})
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    with pytest.raises(common.UpstreamError, match="not configured"):
        common.stripe_get("/v1/x")


# ---------------------------------------------------------------------------
# setup route
# ---------------------------------------------------------------------------


def _paid_session(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "cs_test_example",
        "object": "checkout.session",
        "mode": "payment",
        "payment_status": "paid",
        "customer": "cus_example",
        "customer_details": {"email": "buyer@example.org"},
        "subscription": None,
    }
    base.update(overrides)
    return base


def _line_items(*prices: str, has_more: bool = False) -> dict[str, Any]:
    """The shape of GET /v1/checkout/sessions/{id}/line_items."""
    return {
        "object": "list",
        "has_more": has_more,
        "data": [
            {"id": f"li_example{n}", "object": "item", "quantity": 1, "price": {"id": price}}
            for n, price in enumerate(prices)
        ],
    }


def _stripe(
    monkeypatch: pytest.MonkeyPatch,
    session: dict[str, Any] | None = None,
    *,
    price: str = PRICE_BUNDLE_25,
    line_items: dict[str, Any] | None = None,
) -> list[str]:
    """Serve one Checkout Session and its line items from a single fixture.

    ``common.stripe_get`` is patched, not ``setup_handler.stripe_get``: the
    line-items read happens inside ``common.checkout_plan``, so patching only
    the name the handler imported would leave the real network call in place
    for half the reads. Returns the list of paths asked for.
    """
    served = session if session is not None else _paid_session()
    items = line_items if line_items is not None else _line_items(price)
    paths: list[str] = []

    def fake_get(path: str) -> dict[str, Any]:
        paths.append(path)
        # The real path carries a query string ("/line_items?limit=10"), so
        # this matches on the segment, not on the end of the string.
        return items if "/line_items" in path else served

    monkeypatch.setattr(common, "stripe_get", fake_get)
    monkeypatch.setattr(setup_handler, "stripe_get", fake_get)
    return paths


def _setup_event(form: dict[str, Any]) -> dict[str, Any]:
    return {
        "rawPath": "/setup",
        "requestContext": {"http": {"method": "POST", "path": "/setup"}},
        "body": json.dumps(form),
    }


def _form(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "session_id": "cs_test_example",
        "program_name": "Example Program",
        "accent": "#2c5f70",
        "agency_ids": "unitrans,yolobus",
        "deliver_to": "liaison@example.org",
    }
    base.update(overrides)
    return base


def test_setup_paid_one_time_dispatches_and_records_the_capability(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    dispatched: list[dict[str, str]] = []
    paths = _stripe(monkeypatch, price=PRICE_BUNDLE_100)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    resp = setup_handler.handler(_setup_event(_form()))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200, body
    bundle_id = body["bundle_id"]
    assert len(bundle_id) == 32
    assert dispatched[0]["bundle_id"] == bundle_id
    assert dispatched[0]["agency_ids"] == "unitrans,yolobus"
    assert dispatched[0]["cadence"] == "one_time"
    rows = tables["BUNDLES_TABLE"].items
    assert rows[bundle_id]["deliver_to"] == "liaison@example.org"
    assert rows[bundle_id]["source"] == "checkout"
    assert rows[bundle_id]["expires_at"] > int(time.time())
    assert rows["session#cs_test_example"]["consumed_by"] == bundle_id
    # The claim records the plan, so a support question about one session can
    # be answered from the row rather than from Stripe.
    assert rows["session#cs_test_example"]["plan"] == "bundle_100"
    assert tables["SUBSCRIPTIONS_TABLE"].items == {}
    # The line items were actually read, not assumed.
    assert paths == [
        "/v1/checkout/sessions/cs_test_example",
        "/v1/checkout/sessions/cs_test_example/line_items?limit=10",
    ]


def test_setup_subscription_stores_the_request_and_price_for_the_refresh(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    session = _paid_session(mode="subscription", subscription="sub_example")
    _stripe(monkeypatch, session, price=PRICE_REFRESH_MO)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", lambda inputs: None)

    resp = setup_handler.handler(_setup_event(_form(deliver_to="")))
    assert resp["statusCode"] == 200
    sub = tables["SUBSCRIPTIONS_TABLE"].items["sub_example"]
    assert sub["status"] == "active"
    # The refresh re-checks the price before it dispatches anything.
    assert sub["price"] == PRICE_REFRESH_MO
    assert sub["plan"] == "refresh_mo"
    stored = json.loads(sub["request"])
    assert stored["cadence"] == "monthly"
    # No deliver_to in the form: the payer's email from the session is used.
    assert stored["deliver_to"] == "buyer@example.org"


def test_setup_cadence_follows_the_price_not_the_session_mode(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """A one-time price in a session that claims `mode: subscription` buys a
    one-time bundle. The price is the thing that was paid for; `mode` is a
    field on an object the buyer's own checkout produced."""
    session = _paid_session(mode="subscription", subscription="sub_example")
    _stripe(monkeypatch, session, price=PRICE_BUNDLE_25)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", lambda inputs: None)

    assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 200
    assert tables["SUBSCRIPTIONS_TABLE"].items == {}


def test_setup_refuses_a_paid_checkout_for_a_price_that_is_not_ours(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """The family-greenhouse case: a real, paid Checkout Session on the same
    Stripe account, for something that is not a report bundle."""
    dispatched: list[dict[str, str]] = []
    _stripe(monkeypatch, price=PRICE_FOREIGN)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    resp = setup_handler.handler(_setup_event(_form()))
    assert resp["statusCode"] == 403
    assert "not for a GTFS Scorecard report bundle" in resp["body"]
    assert dispatched == []
    assert tables["BUNDLES_TABLE"].items == {}
    assert tables["SUBSCRIPTIONS_TABLE"].items == {}


def test_setup_refuses_a_session_whose_line_items_are_not_one_known_price(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    dispatched: list[dict[str, str]] = []
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    for items in (
        _line_items(),  # nothing bought
        _line_items(PRICE_BUNDLE_25, PRICE_BUNDLE_100),  # two prices in one checkout
        _line_items(PRICE_BUNDLE_25, has_more=True),  # a longer list, refused unread
        {"object": "list", "data": "not-a-list"},  # a shape Stripe would not send
    ):
        _stripe(monkeypatch, line_items=items)
        assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 403
    assert dispatched == []
    assert tables["BUNDLES_TABLE"].items == {}


def test_setup_refuses_everything_when_no_prices_are_configured(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """A half-configured deploy sells nothing rather than selling anything.
    Each of these leaves the Lambda unable to say what a price buys."""
    dispatched: list[dict[str, str]] = []
    _stripe(monkeypatch, price=PRICE_BUNDLE_25)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    for value in (
        "{}",
        "not json",
        "[]",
        json.dumps({"bundle_25": ""}),
        json.dumps({"mystery_plan": PRICE_BUNDLE_25}),
        # The same price id on two plans: which cap would it be?
        json.dumps({"bundle_25": PRICE_BUNDLE_25, "bundle_100": PRICE_BUNDLE_25}),
    ):
        monkeypatch.setenv("STRIPE_PRICE_IDS", value)
        assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 403, value
    monkeypatch.delenv("STRIPE_PRICE_IDS")
    assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 403
    assert dispatched == []
    assert tables["BUNDLES_TABLE"].items == {}


def test_setup_holds_a_bundle_25_purchase_to_twenty_five_agencies(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """`plan.json` sells bundle_25 as "One bundle, up to 25 agencies". The
    26th id is refused with the reason, so the same checkout can be sent
    again with a shorter list; it is not trimmed and not upgraded."""
    dispatched: list[dict[str, str]] = []
    _stripe(monkeypatch, price=PRICE_BUNDLE_25)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    twenty_six = ",".join(f"agency-{n}" for n in range(26))
    resp = setup_handler.handler(_setup_event(_form(agency_ids=twenty_six)))
    assert resp["statusCode"] == 400
    error = json.loads(resp["body"])["error"]
    assert "your plan covers at most 25 agencies; 26 were given" in error
    assert dispatched == []
    # Nothing was claimed either, so the buyer can resend the same session.
    assert tables["BUNDLES_TABLE"].items == {}

    twenty_five = ",".join(f"agency-{n}" for n in range(25))
    assert setup_handler.handler(_setup_event(_form(agency_ids=twenty_five)))["statusCode"] == 200
    assert len(dispatched[0]["agency_ids"].split(",")) == 25


def test_setup_lets_a_bundle_100_purchase_list_more_than_twenty_five(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    dispatched: list[dict[str, str]] = []
    _stripe(monkeypatch, price=PRICE_BUNDLE_100)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    ids = ",".join(f"agency-{n}" for n in range(26))
    assert setup_handler.handler(_setup_event(_form(agency_ids=ids)))["statusCode"] == 200
    assert len(dispatched[0]["agency_ids"].split(",")) == 26

    # 101 is over the product's own ceiling, whatever was paid for.
    too_many = ",".join(f"agency-{n}" for n in range(101))
    over = setup_handler.handler(_setup_event(_form(agency_ids=too_many)))
    assert over["statusCode"] == 400
    assert "at most 100 agencies" in over["body"]


def test_setup_refuses_everything_while_payments_are_disabled(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """Defense in depth behind the Terraform gate that removes the route:
    a stale route or a direct invoke still builds nothing, and the checkout
    is not consumed, so the buyer can come back."""
    dispatched: list[dict[str, str]] = []
    paths = _stripe(monkeypatch, price=PRICE_BUNDLE_25)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    for value in ("0", "", "true", "yes"):
        monkeypatch.setenv("PAYMENTS_ENABLED", value)
        resp = setup_handler.handler(_setup_event(_form()))
        assert resp["statusCode"] == 503, value
        assert "nothing was built" in json.loads(resp["body"])["error"]
    monkeypatch.delenv("PAYMENTS_ENABLED")
    assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 503

    assert dispatched == []
    assert tables["BUNDLES_TABLE"].items == {}
    # Stripe was never even asked: the gate is read before the session is.
    assert paths == []

    monkeypatch.setenv("PAYMENTS_ENABLED", "1")
    assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 200


def test_setup_refuses_unpaid_sessions_and_replays(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    _stripe(monkeypatch, _paid_session(payment_status="unpaid"))
    assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 402

    _stripe(monkeypatch)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", lambda inputs: None)
    assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 200
    replay = setup_handler.handler(_setup_event(_form()))
    assert replay["statusCode"] == 409
    assert "already produced" in replay["body"]


def test_setup_refuses_bad_bodies_bad_session_ids_and_invalid_requests(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    bad_json = {"rawPath": "/setup", "requestContext": {"http": {"method": "POST"}}, "body": "{"}
    assert setup_handler.handler(bad_json)["statusCode"] == 400
    assert setup_handler.handler(_setup_event(_form(session_id="")))["statusCode"] == 400
    assert setup_handler.handler(_setup_event(_form(session_id="pi_x")))["statusCode"] == 400
    _stripe(monkeypatch)
    resp = setup_handler.handler(_setup_event(_form(agency_ids="")))
    assert resp["statusCode"] == 400
    assert "at least one agency" in resp["body"]
    assert tables["BUNDLES_TABLE"].items == {}


def test_setup_reports_upstream_failures_without_losing_the_order(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    def stripe_down(path: str) -> dict[str, Any]:
        raise common.UpstreamError("stripe 500", status=500)

    monkeypatch.setattr(common, "stripe_get", stripe_down)
    monkeypatch.setattr(setup_handler, "stripe_get", stripe_down)
    assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 502

    # The session reads fine but the line items do not: a Stripe outage, or a
    # restricted key without permission to read them. Either way the answer is
    # "not yet", never "build it anyway".
    def line_items_down(path: str) -> dict[str, Any]:
        if "/line_items" in path:
            raise common.UpstreamError("stripe 403", status=403)
        return _paid_session()

    monkeypatch.setattr(common, "stripe_get", line_items_down)
    monkeypatch.setattr(setup_handler, "stripe_get", line_items_down)
    resp = setup_handler.handler(_setup_event(_form()))
    assert resp["statusCode"] == 502
    assert tables["BUNDLES_TABLE"].items == {}

    def github_down(inputs: dict[str, str]) -> None:
        raise common.UpstreamError("github 500")

    _stripe(monkeypatch)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", github_down)
    resp = setup_handler.handler(_setup_event(_form()))
    assert resp["statusCode"] == 502
    body = json.loads(resp["body"])
    assert body["bundle_id"] in tables["BUNDLES_TABLE"].items
    assert "recorded" in body["error"]


def test_setup_lets_a_buyer_finish_an_order_whose_dispatch_never_started(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """The dead end this closes: the first submission claimed the session and
    then GitHub refused the dispatch, so no build exists and no email will
    come. Answering the second submission "this checkout already produced a
    bundle" is false and leaves a paying buyer with no move left. The retry
    finishes the order instead, under the SAME bundle id, so one payment
    still yields exactly one bundle and one download link."""
    attempts: list[dict[str, str]] = []

    def first_call_fails(inputs: dict[str, str]) -> None:
        attempts.append(inputs)
        if len(attempts) == 1:
            raise common.UpstreamError("github 502")

    _stripe(monkeypatch)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", first_call_fails)

    failed = setup_handler.handler(_setup_event(_form()))
    assert failed["statusCode"] == 502
    bundle_id = json.loads(failed["body"])["bundle_id"]
    claim = tables["BUNDLES_TABLE"].items["session#cs_test_example"]
    assert claim["consumed_by"] == bundle_id
    assert claim["dispatched"] is False

    retried = setup_handler.handler(_setup_event(_form()))
    assert retried["statusCode"] == 200, retried["body"]
    assert json.loads(retried["body"])["bundle_id"] == bundle_id
    assert [a["bundle_id"] for a in attempts] == [bundle_id, bundle_id]
    assert tables["BUNDLES_TABLE"].items["session#cs_test_example"]["dispatched"] is True

    # And once a build really started, a third submission is refused again.
    third = setup_handler.handler(_setup_event(_form()))
    assert third["statusCode"] == 409
    assert "already produced" in third["body"]
    assert len(attempts) == 2


def test_setup_will_not_rebuild_a_claim_that_predates_the_dispatched_flag(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """Absence of the flag is not evidence the dispatch failed. A claim
    written before the field existed -- or by a Lambda that died after GitHub
    accepted the dispatch -- must not be re-dispatched on a guess, or one
    payment would buy two builds."""
    _stripe(monkeypatch)
    dispatched: list[dict[str, str]] = []
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)
    tables["BUNDLES_TABLE"].items["session#cs_test_example"] = {
        "bundle_id": "session#cs_test_example",
        "consumed_by": "e" * 32,
        "plan": "bundle_25",
    }

    resp = setup_handler.handler(_setup_event(_form()))
    assert resp["statusCode"] == 409
    assert dispatched == []


def test_setup_separates_an_unknown_checkout_from_a_stripe_outage(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """A 404 means this reference will never resolve -- a truncated address,
    or a test-mode id read with the live key. Reporting it as "could not
    confirm the payment yet" invites the buyer to retry it forever."""

    def missing(path: str) -> dict[str, Any]:
        raise common.UpstreamError("stripe 404", status=404)

    monkeypatch.setattr(common, "stripe_get", missing)
    monkeypatch.setattr(setup_handler, "stripe_get", missing)
    resp = setup_handler.handler(_setup_event(_form()))
    assert resp["statusCode"] == 404
    assert "not one Stripe recognises" in json.loads(resp["body"])["error"]
    assert tables["BUNDLES_TABLE"].items == {}


def test_setup_routes_options_and_unknown_paths() -> None:
    assert (
        setup_handler.handler({"requestContext": {"http": {"method": "OPTIONS"}}})["statusCode"]
        == 204
    )
    resp = setup_handler.handler(
        {"rawPath": "/nope", "requestContext": {"http": {"method": "GET"}}}
    )
    assert resp["statusCode"] == 404


# ---------------------------------------------------------------------------
# download route
# ---------------------------------------------------------------------------


class _FakeS3:
    def __init__(self, exists: bool) -> None:
        self.exists = exists
        self.presigned: dict[str, Any] | None = None

    def head_object(self, Bucket: str, Key: str) -> None:
        if not self.exists:
            raise KeyError("404")

    def generate_presigned_url(self, op: str, Params: dict[str, Any], ExpiresIn: int) -> str:
        self.presigned = {"op": op, **Params, "expires": ExpiresIn}
        return "https://s3.example/presigned"


def _download_event(bundle_id: str) -> dict[str, Any]:
    return {
        "rawPath": f"/download/{bundle_id}",
        "requestContext": {"http": {"method": "GET", "path": f"/download/{bundle_id}"}},
    }


def test_download_redirects_to_a_short_lived_presigned_url(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    bundle_id = "b" * 32
    tables["BUNDLES_TABLE"].items[bundle_id] = {"bundle_id": bundle_id}
    s3 = _FakeS3(exists=True)
    fake_boto3 = type("boto3", (), {"client": staticmethod(lambda *a, **k: s3)})
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    resp = setup_handler.handler(_download_event(bundle_id))
    assert resp["statusCode"] == 302
    assert resp["headers"]["Location"] == "https://s3.example/presigned"
    assert resp["headers"]["Cache-Control"] == "no-store"
    assert s3.presigned is not None
    assert s3.presigned["Key"] == f"program-bundles/{bundle_id}/bundle.zip"
    assert s3.presigned["expires"] == setup_handler.PRESIGN_SECONDS == 900


def test_download_answers_202_while_the_archive_is_missing_and_404_otherwise(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    bundle_id = "c" * 32
    tables["BUNDLES_TABLE"].items[bundle_id] = {"bundle_id": bundle_id}
    s3 = _FakeS3(exists=False)
    fake_boto3 = type("boto3", (), {"client": staticmethod(lambda *a, **k: s3)})
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    assert setup_handler.handler(_download_event(bundle_id))["statusCode"] == 202
    assert setup_handler.handler(_download_event("d" * 32))["statusCode"] == 404
    assert setup_handler.handler(_download_event("not-hex"))["statusCode"] == 404


def test_download_says_expired_rather_than_still_preparing_past_its_ttl(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """The S3 lifecycle rule deletes the archive on day 30; DynamoDB's TTL
    sweep can lag by two more. In that window the row is present and the
    object is gone, which is the same evidence as a build still running. The
    row's own expiry settles it, so nobody is told to keep waiting for a file
    that was deleted."""
    s3 = _FakeS3(exists=False)
    fake_boto3 = type("boto3", (), {"client": staticmethod(lambda *a, **k: s3)})
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    expired = "e" * 32
    tables["BUNDLES_TABLE"].items[expired] = {
        "bundle_id": expired,
        "expires_at": int(time.time()) - 60,
    }
    resp = setup_handler.handler(_download_event(expired))
    assert resp["statusCode"] == 404
    assert "expired" in resp["body"]
    assert "still being generated" not in resp["body"]

    # Inside its thirty days it still reads as in progress, and says what to
    # do if it never finishes.
    live = "f" * 32
    tables["BUNDLES_TABLE"].items[live] = {
        "bundle_id": live,
        "expires_at": int(time.time()) + 600,
    }
    pending = setup_handler.handler(_download_event(live))
    assert pending["statusCode"] == 202
    assert "an hour from now" in pending["body"]


# ---------------------------------------------------------------------------
# webhook
# ---------------------------------------------------------------------------


def _event(event_type: str, obj: dict[str, Any]) -> bytes:
    return json.dumps(
        {"id": "evt_example", "object": "event", "type": event_type, "data": {"object": obj}}
    ).encode()


def _webhook(body: bytes, signature: str | None = None) -> dict[str, Any]:
    return {
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"Stripe-Signature": _sign(body) if signature is None else signature},
        "body": body.decode(),
    }


def test_webhook_refuses_an_unsigned_or_missigned_request(tables: dict[str, FakeTable]) -> None:
    body = _event("customer.subscription.created", {"id": "sub_1", "status": "active"})
    assert webhook_handler.handler(_webhook(body, signature=""))["statusCode"] == 400
    assert webhook_handler.handler(_webhook(body, signature="t=1,v1=00"))["statusCode"] == 400
    assert tables["SUBSCRIPTIONS_TABLE"].items == {}
    assert (
        webhook_handler.handler({"requestContext": {"http": {"method": "GET"}}})["statusCode"]
        == 405
    )


def _subscription(price: str = PRICE_REFRESH_MO, **overrides: Any) -> dict[str, Any]:
    """A Stripe subscription object, with the one item the refresh prices sell."""
    obj: dict[str, Any] = {
        "id": "sub_1",
        "object": "subscription",
        "status": "active",
        "customer": "cus_1",
        "items": {"object": "list", "data": [{"id": "si_1", "price": {"id": price}}]},
    }
    obj.update(overrides)
    return obj


def test_webhook_tracks_subscription_lifecycle(tables: dict[str, FakeTable]) -> None:
    created = _event("customer.subscription.created", _subscription(status="trialing"))
    assert json.loads(webhook_handler.handler(_webhook(created))["body"])["outcome"] == "updated"
    row = tables["SUBSCRIPTIONS_TABLE"].items["sub_1"]
    assert row["status"] == "active"
    assert row["price"] == PRICE_REFRESH_MO
    assert row["plan"] == "refresh_mo"

    past_due = _event("customer.subscription.updated", _subscription(status="past_due"))
    webhook_handler.handler(_webhook(past_due))
    assert tables["SUBSCRIPTIONS_TABLE"].items["sub_1"]["status"] == "past_due"

    deleted = _event("customer.subscription.deleted", _subscription(status="canceled"))
    assert json.loads(webhook_handler.handler(_webhook(deleted))["body"])["outcome"] == "canceled"
    row = tables["SUBSCRIPTIONS_TABLE"].items["sub_1"]
    assert row["status"] == "canceled"
    assert row["canceled_at"]


def test_webhook_never_creates_a_row_for_a_subscription_that_is_not_ours(
    tables: dict[str, FakeTable],
) -> None:
    """Another product's subscription on the same Stripe account, and a
    one-time bundle price used as a subscription: neither is a refresh plan,
    so neither becomes a row the weekly refresh would scan."""
    subs = tables["SUBSCRIPTIONS_TABLE"]
    for price in (PRICE_FOREIGN, PRICE_BUNDLE_25):
        created = _event("customer.subscription.created", _subscription(price))
        body = json.loads(webhook_handler.handler(_webhook(created))["body"])
        assert body["outcome"] == "ignored"
        assert subs.items == {}
    deleted = _event("customer.subscription.deleted", _subscription(PRICE_FOREIGN))
    assert json.loads(webhook_handler.handler(_webhook(deleted))["body"])["outcome"] == "ignored"
    assert subs.items == {}


def test_webhook_still_records_a_tracked_subscription_that_left_the_plan(
    tables: dict[str, FakeTable],
) -> None:
    """A subscription we already track that moved off the refresh prices is
    still updated, so the refresh can see it stopped; it is just never
    created from scratch."""
    subs = tables["SUBSCRIPTIONS_TABLE"]
    webhook_handler.handler(_webhook(_event("customer.subscription.created", _subscription())))
    assert subs.items["sub_1"]["plan"] == "refresh_mo"

    moved = _event("customer.subscription.updated", _subscription(PRICE_FOREIGN))
    assert json.loads(webhook_handler.handler(_webhook(moved))["body"])["outcome"] == "updated"
    assert subs.items["sub_1"]["price"] == ""
    assert subs.items["sub_1"]["plan"] == ""

    canceled = _event("customer.subscription.deleted", _subscription(PRICE_FOREIGN))
    assert json.loads(webhook_handler.handler(_webhook(canceled))["body"])["outcome"] == "canceled"
    assert subs.items["sub_1"]["status"] == "canceled"


def test_webhook_notes_checkouts_and_ignores_everything_else(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    _stripe(monkeypatch, price=PRICE_BUNDLE_25)
    completed = _event(
        "checkout.session.completed",
        {"id": "cs_test_1", "mode": "payment", "customer_details": {"email": "b@example.org"}},
    )
    assert json.loads(webhook_handler.handler(_webhook(completed))["body"])["outcome"] == "noted"
    row = tables["BUNDLES_TABLE"].items["checkout#cs_test_1"]
    assert row["email"] == "b@example.org"
    assert row["plan"] == "bundle_25"
    other = _event("invoice.paid", {"id": "in_1"})
    assert json.loads(webhook_handler.handler(_webhook(other))["body"])["outcome"] == "ignored"
    bad = b"not json"
    assert webhook_handler.handler(_webhook(bad))["statusCode"] == 400


def test_webhook_ignores_a_completed_checkout_for_someone_elses_product(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    _stripe(monkeypatch, price=PRICE_FOREIGN)
    completed = _event("checkout.session.completed", {"id": "cs_test_2", "mode": "payment"})
    assert json.loads(webhook_handler.handler(_webhook(completed))["body"])["outcome"] == "ignored"
    assert tables["BUNDLES_TABLE"].items == {}


def test_webhook_notes_a_checkout_it_could_not_verify_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """A Stripe outage must not turn into 4xx replies that get the endpoint
    disabled, so an unreadable session is noted as `unverified` and a human
    can look it up. A 404 is different: Stripe is up and says there is no
    such session, so there is nothing to note."""

    def down(path: str) -> dict[str, Any]:
        raise common.UpstreamError("stripe 500", status=500)

    monkeypatch.setattr(common, "stripe_get", down)
    completed = _event("checkout.session.completed", {"id": "cs_test_3", "mode": "payment"})
    assert json.loads(webhook_handler.handler(_webhook(completed))["body"])["outcome"] == "noted"
    assert tables["BUNDLES_TABLE"].items["checkout#cs_test_3"]["plan"] == "unverified"

    def missing(path: str) -> dict[str, Any]:
        raise common.UpstreamError("stripe 404", status=404)

    monkeypatch.setattr(common, "stripe_get", missing)
    gone = _event("checkout.session.completed", {"id": "cs_test_4", "mode": "payment"})
    assert json.loads(webhook_handler.handler(_webhook(gone))["body"])["outcome"] == "ignored"
    assert "checkout#cs_test_4" not in tables["BUNDLES_TABLE"].items

    # An id that is not a Checkout Session id is never looked up at all.
    odd = _event("checkout.session.completed", {"id": "not-a-session", "mode": "payment"})
    assert json.loads(webhook_handler.handler(_webhook(odd))["body"])["outcome"] == "ignored"


def test_webhook_reads_a_base64_transport_body(tables: dict[str, FakeTable]) -> None:
    import base64

    body = _event("invoice.paid", {"id": "in_1"})
    event = _webhook(body)
    event["body"] = base64.b64encode(body).decode()
    event["isBase64Encoded"] = True
    assert webhook_handler.handler(event)["statusCode"] == 200


# ---------------------------------------------------------------------------
# weekly refresh
# ---------------------------------------------------------------------------


def _sub(**overrides: Any) -> dict[str, Any]:
    request = {
        "bundle_id": "0" * 32,
        "program_name": "P",
        "accent": "#163a2c",
        "logo": "",
        "agency_ids": ["unitrans"],
        "deliver_to": "p@example.org",
        "cadence": "monthly",
    }
    base: dict[str, Any] = {
        "id": "sub_1",
        "status": "active",
        "price": PRICE_REFRESH_MO,
        "request": json.dumps(request),
    }
    base.update(overrides)
    return base


def test_refresh_dispatches_only_active_due_subscriptions(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    now = dt.datetime(2026, 10, 1, tzinfo=dt.UTC)
    subs = tables["SUBSCRIPTIONS_TABLE"]
    subs.items["sub_never"] = _sub(id="sub_never")
    subs.items["sub_old"] = _sub(id="sub_old", last_refresh="2026-08-01T00:00:00+00:00")
    subs.items["sub_recent"] = _sub(id="sub_recent", last_refresh="2026-09-20T00:00:00+00:00")
    subs.items["sub_canceled"] = _sub(id="sub_canceled", status="canceled")
    subs.items["sub_broken"] = _sub(id="sub_broken", request="{}")
    dispatched: list[dict[str, str]] = []
    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", dispatched.append)

    counts = refresh_handler.refresh(subscriptions=subs, bundles=tables["BUNDLES_TABLE"], now=now)
    assert counts == {
        "scanned": 5,
        "due": 3,
        "not_on_plan": 0,
        # sub_broken is billed with no stored request; that is its own count,
        # not a dispatch failure.
        "no_request": 1,
        "dispatched": 2,
        "would_dispatch": 0,
        "failed": 0,
    }
    assert {d["cadence"] for d in dispatched} == {"monthly"}
    assert len({d["bundle_id"] for d in dispatched}) == 2
    assert all(len(d["bundle_id"]) == 32 for d in dispatched)
    assert subs.items["sub_never"]["last_bundle_id"] in tables["BUNDLES_TABLE"].items
    assert subs.items["sub_old"]["last_refresh"]
    assert "last_refresh" not in subs.items["sub_broken"]
    assert subs.items["sub_recent"]["last_refresh"] == "2026-09-20T00:00:00+00:00"


def test_refresh_skips_rows_that_are_not_on_a_configured_refresh_price(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """Three ways a due row can fail the price check: a price from another
    product, a one-time bundle price, and a row written before the price was
    recorded at all (or left over from test mode after the live ids are
    configured). None of them bills anyone, and none of them builds."""
    subs = tables["SUBSCRIPTIONS_TABLE"]
    subs.items["sub_ok"] = _sub(id="sub_ok")
    subs.items["sub_foreign"] = _sub(id="sub_foreign", price=PRICE_FOREIGN)
    subs.items["sub_one_time"] = _sub(id="sub_one_time", price=PRICE_BUNDLE_25)
    subs.items["sub_no_price"] = _sub(id="sub_no_price", price="")
    dispatched: list[dict[str, str]] = []
    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", dispatched.append)

    counts = refresh_handler.refresh(subscriptions=subs, bundles=tables["BUNDLES_TABLE"])
    assert counts["scanned"] == 4
    assert counts["not_on_plan"] == 3
    assert counts["dispatched"] == 1
    assert len(dispatched) == 1
    assert "last_refresh" not in subs.items["sub_foreign"]


def test_refresh_refuses_the_whole_run_when_no_refresh_price_is_configured(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """The live price ids replaced the test ones, and the one that was
    mistyped is the refresh price. Every row would then be counted
    ``not_on_plan`` -- a claim about the subscription -- and the tick would
    answer ok while no paying subscriber was ever refreshed again. A
    configuration failure has to fail, not be published as a per-row fact."""
    subs = tables["SUBSCRIPTIONS_TABLE"]
    subs.items["sub_a"] = _sub(id="sub_a")
    dispatched: list[dict[str, str]] = []
    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", dispatched.append)

    for value in ("{}", "not json", "[]", json.dumps({"bundle_25": PRICE_BUNDLE_25})):
        monkeypatch.setenv("STRIPE_PRICE_IDS", value)
        with pytest.raises(refresh_handler.ConfigurationError):
            refresh_handler.refresh(subscriptions=subs, bundles=tables["BUNDLES_TABLE"])
        with pytest.raises(refresh_handler.ConfigurationError):
            refresh_handler.handler({}, None)
    assert dispatched == []
    assert tables["BUNDLES_TABLE"].items == {}
    assert "last_refresh" not in subs.items["sub_a"]

    # One refresh price is enough to make `not_on_plan` mean something again.
    monkeypatch.setenv("STRIPE_PRICE_IDS", json.dumps({"refresh_mo": PRICE_REFRESH_MO}))
    assert (
        refresh_handler.refresh(subscriptions=subs, bundles=tables["BUNDLES_TABLE"])["dispatched"]
        == 1
    )


def test_refresh_writes_the_capability_row_before_it_dispatches(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """The workflow uploads the archive and emails the link on its own clock.
    If this Lambda dies between the dispatch and the put, the emailed link
    finds no row and reads "expired or never issued" for a bundle sitting in
    the bucket. The row has to exist before anything can deliver against it."""
    bundles = tables["BUNDLES_TABLE"]
    tables["SUBSCRIPTIONS_TABLE"].items["sub_a"] = _sub(id="sub_a")
    seen: list[list[str]] = []

    def note_rows(inputs: dict[str, str]) -> None:
        seen.append(sorted(bundles.items))

    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", note_rows)
    counts = refresh_handler.refresh(subscriptions=tables["SUBSCRIPTIONS_TABLE"], bundles=bundles)
    assert counts["dispatched"] == 1
    assert len(seen[0]) == 1, "the capability row must already exist at dispatch time"


def test_refresh_counts_a_billed_subscription_with_no_stored_request_apart(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """A subscription the webhook created at checkout whose buyer never
    finished the setup form is being billed for nothing. Rolling it into
    ``failed`` hid a paying customer inside a retry statistic; it now has its
    own count, and ``failed`` means only that GitHub refused the dispatch."""
    subs = tables["SUBSCRIPTIONS_TABLE"]
    subs.items["sub_never_set_up"] = _sub(id="sub_never_set_up", request="")
    subs.items["sub_ok"] = _sub(id="sub_ok")
    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", lambda inputs: None)

    counts = refresh_handler.refresh(subscriptions=subs, bundles=tables["BUNDLES_TABLE"])
    assert counts["no_request"] == 1
    assert counts["failed"] == 0
    assert counts["dispatched"] == 1


def test_refresh_keeps_going_past_a_failed_dispatch(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    subs = tables["SUBSCRIPTIONS_TABLE"]
    subs.items["sub_a"] = _sub(id="sub_a")
    subs.items["sub_b"] = _sub(id="sub_b")
    seen: list[str] = []

    def flaky(inputs: dict[str, str]) -> None:
        seen.append(inputs["bundle_id"])
        if len(seen) == 1:
            raise common.UpstreamError("github 502")

    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", flaky)
    counts = refresh_handler.refresh(subscriptions=subs, bundles=tables["BUNDLES_TABLE"])
    assert counts["dispatched"] == 1
    assert counts["failed"] == 1
    # The failed one keeps no last_refresh, so the next tick retries it.
    assert sum("last_refresh" in row for row in subs.items.values()) == 1


def test_refresh_dry_run_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """DRY_RUN was reported in the response and never honoured. It is honoured
    now, from the environment or from a hand invoke's payload, and the proof
    is that nothing moved: no dispatch, no capability row, no last_refresh."""
    dispatched: list[dict[str, str]] = []
    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", dispatched.append)

    def fresh_subs() -> FakeTable:
        subs = tables["SUBSCRIPTIONS_TABLE"]
        subs.items.clear()
        subs.items["sub_a"] = _sub(id="sub_a")
        subs.items["sub_b"] = _sub(id="sub_b")
        return subs

    subs = fresh_subs()
    counts = refresh_handler.refresh(
        subscriptions=subs, bundles=tables["BUNDLES_TABLE"], dry_run=True
    )
    assert counts["due"] == 2
    assert counts["would_dispatch"] == 2
    assert counts["dispatched"] == 0
    assert dispatched == []
    assert tables["BUNDLES_TABLE"].items == {}
    assert all("last_refresh" not in row for row in subs.items.values())

    # From the environment, through the entrypoint.
    fresh_subs()
    monkeypatch.setenv("DRY_RUN", "1")
    out = refresh_handler.handler({}, None)
    assert out["dry_run"] is True
    assert out["would_dispatch"] == 2 and out["dispatched"] == 0
    assert dispatched == []

    # And from a hand invoke's payload, with DRY_RUN unset.
    fresh_subs()
    monkeypatch.delenv("DRY_RUN")
    out = refresh_handler.handler({"dry_run": True}, None)
    assert out["dry_run"] is True
    assert out["would_dispatch"] == 2 and out["dispatched"] == 0
    assert dispatched == []

    # The scheduled event carries no flag, so the real run still dispatches.
    fresh_subs()
    out = refresh_handler.handler({}, None)
    assert out["dry_run"] is False
    assert out["dispatched"] == 2
    assert len(dispatched) == 2


def test_refresh_does_nothing_while_payments_are_disabled(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    dispatched: list[dict[str, str]] = []
    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", dispatched.append)
    tables["SUBSCRIPTIONS_TABLE"].items["sub_a"] = _sub(id="sub_a")

    monkeypatch.setenv("PAYMENTS_ENABLED", "0")
    out = refresh_handler.handler({}, None)
    assert out == {"ok": True, "payments_enabled": False, "dry_run": False}
    assert dispatched == []
    assert tables["BUNDLES_TABLE"].items == {}
    assert "last_refresh" not in tables["SUBSCRIPTIONS_TABLE"].items["sub_a"]


def test_refresh_handler_entrypoint_reports_counts(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", lambda inputs: None)
    out = refresh_handler.handler({}, None)
    assert out["ok"] is True
    assert out["scanned"] == 0


# ---------------------------------------------------------------------------
# daily reconciler
# ---------------------------------------------------------------------------


class _ReconcileS3:
    """head_object over a set of keys, with the three answers that matter:
    the object is there, S3 says 404, or S3 did not answer."""

    def __init__(self, present: set[str] | None = None, unreadable: set[str] | None = None):
        self.present = set(present or ())
        self.unreadable = set(unreadable or ())
        self.asked: list[str] = []

    def head_object(self, Bucket: str, Key: str) -> None:
        self.asked.append(Key)
        if Key in self.unreadable:
            raise _ClientError({"Error": {"Code": "SlowDown"}})
        if Key not in self.present:
            raise _ClientError({"Error": {"Code": "404"}})


class _ClientError(Exception):
    """Shaped like botocore's: the code is read off `.response`, not the type."""

    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__(str(response))
        self.response = response


class _FakeIssues:
    """The issues half of this repository's API, as `github_request` uses it."""

    def __init__(self, fail: bool = False) -> None:
        self.open: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str]] = []
        self.patches: list[dict[str, Any]] = []
        self.fail = fail
        self._next = 1

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, path))
        if self.fail:
            raise common.UpstreamError(f"{method} {path} -> HTTP 403", status=403)
        if method == "GET":
            return list(self.open)
        if method == "POST":
            assert payload is not None
            issue = {"number": self._next, **payload}
            self._next += 1
            self.open.append(issue)
            return issue
        if method == "PATCH":
            assert payload is not None
            number = int(path.rsplit("/", 1)[1])
            self.patches.append({"number": number, **payload})
            for issue in self.open:
                if issue["number"] == number:
                    issue.update(payload)
            return {}
        raise AssertionError(method)


class _FakeBoto3:
    def __init__(self, s3: _ReconcileS3) -> None:
        self._s3 = s3

    def client(self, service: str, **_: Any) -> Any:
        return self._s3


def _hours_ago(hours: float) -> str:
    return (dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours)).replace(microsecond=0).isoformat()


def _capability(bundle_id: str, *, hours: float = 48, **overrides: Any) -> dict[str, Any]:
    row = {
        "bundle_id": bundle_id,
        "deliver_to": "liaison@example.org",
        "program_name": "Example Program",
        "source": "checkout",
        "created_at": _hours_ago(hours),
        "expires_at": int(time.time()) + 86400,
    }
    row.update(overrides)
    return row


def _reconcile(tables: dict[str, FakeTable], s3: _ReconcileS3) -> dict[str, Any]:
    result: dict[str, Any] = reconcile_handler.reconcile(
        bundles=tables["BUNDLES_TABLE"], s3=s3, bucket="example-artifacts"
    )
    return result


def test_reconcile_reports_a_paid_order_whose_archive_never_arrived(
    tables: dict[str, FakeTable],
) -> None:
    """The dispatch dead-end and a fulfilment run that died look the same
    from here, which is the point: the capability row is written before
    report-bundle.yml is dispatched, so one question covers both."""
    rows = tables["BUNDLES_TABLE"].items
    rows["a" * 32] = _capability("a" * 32)  # paid, no archive
    rows["b" * 32] = _capability("b" * 32)  # paid, delivered
    rows["c" * 32] = _capability("c" * 32, hours=1)  # still rendering

    s3 = _ReconcileS3(present={f"program-bundles/{'b' * 32}/bundle.zip"})
    result = _reconcile(tables, s3)

    assert result["scanned"] == 3
    assert [(f["kind"], f["key"]) for f in result["findings"]] == [("undelivered", "a" * 32)]
    found = result["findings"][0]
    assert found["deliver_to"] == "liaison@example.org"
    assert 47 < found["age_hours"] < 49
    assert "Re-dispatch report-bundle.yml" in found["action"]
    # A row inside the window is not headed at all; the check costs a request.
    assert f"program-bundles/{'c' * 32}/bundle.zip" not in s3.asked


def test_reconcile_reports_a_claim_that_never_dispatched_and_ignores_one_that_did(
    tables: dict[str, FakeTable],
) -> None:
    """The claim the setup route leaves behind when GitHub refuses the
    dispatch. It is deliberately left unfinished so the buyer can retry and
    resume the same bundle; this is what notices when they never come back.

    A claim written before `dispatched` existed says nothing either way, and
    is not reported on a guess. Those orders still reach the digest through
    their capability row, which asks S3 rather than a field nobody wrote.
    """
    rows = tables["BUNDLES_TABLE"].items
    rows["d" * 32] = _capability("d" * 32, hours=30)
    rows["session#cs_stuck"] = {
        "bundle_id": "session#cs_stuck",
        "consumed_by": "d" * 32,
        "plan": "bundle_25",
        "dispatched": False,
    }
    rows["e" * 32] = _capability("e" * 32, hours=30)
    rows["session#cs_built"] = {
        "bundle_id": "session#cs_built",
        "consumed_by": "e" * 32,
        "plan": "bundle_25",
        "dispatched": True,
    }
    rows["f" * 32] = _capability("f" * 32, hours=0.2)
    rows["session#cs_fresh"] = {
        "bundle_id": "session#cs_fresh",
        "consumed_by": "f" * 32,
        "plan": "bundle_25",
        "dispatched": False,
    }
    rows["session#cs_legacy"] = {
        "bundle_id": "session#cs_legacy",
        "consumed_by": "0" * 32,
        "plan": "bundle_25",
    }

    s3 = _ReconcileS3(
        present={
            f"program-bundles/{'e' * 32}/bundle.zip",
            f"program-bundles/{'f' * 32}/bundle.zip",
        }
    )
    findings = _reconcile(tables, s3)["findings"]
    claims = [f for f in findings if f["kind"] == "never_started"]
    assert [f["key"] for f in claims] == ["session#cs_stuck"]
    assert claims[0]["bundle_id"] == "d" * 32
    assert "the claim is still open" in claims[0]["action"]
    # The claim carries no timestamp of its own, so it borrowed the capability
    # row's. Without that a claim caught mid-flight would read as abandoned.
    assert 29 < claims[0]["age_hours"] < 31


def test_reconcile_reports_a_checkout_that_never_reached_the_setup_form(
    tables: dict[str, FakeTable],
) -> None:
    """The webhook notes every paid checkout; the setup route writes a
    `session#` row when the buyer finishes the form. A `checkout#` with no
    sibling is somebody who paid and closed the tab."""
    rows = tables["BUNDLES_TABLE"].items
    rows["checkout#cs_gone"] = {
        "bundle_id": "checkout#cs_gone",
        "plan": "bundle_100",
        "email": "buyer@example.org",
        "seen_at": _hours_ago(72),
    }
    rows["checkout#cs_done"] = {
        "bundle_id": "checkout#cs_done",
        "plan": "bundle_25",
        "email": "other@example.org",
        "seen_at": _hours_ago(72),
    }
    rows["session#cs_done"] = {
        "bundle_id": "session#cs_done",
        "consumed_by": "0" * 32,
        "plan": "bundle_25",
        "dispatch_state": "sent",
        "claimed_at": _hours_ago(72),
    }

    findings = _reconcile(tables, _ReconcileS3())["findings"]
    assert [(f["kind"], f["key"]) for f in findings] == [("abandoned_checkout", "checkout#cs_gone")]
    assert findings[0]["email"] == "buyer@example.org"


def test_reconcile_treats_what_it_could_not_read_as_a_finding_not_as_a_pass(
    tables: dict[str, FakeTable],
) -> None:
    """Two ways this job could quietly report nothing while orders rot: a
    row whose timestamp will not parse, and a bucket that will not answer.
    Neither is allowed to read as "delivered"."""
    rows = tables["BUNDLES_TABLE"].items
    rows["a" * 32] = _capability("a" * 32, created_at="")  # no timestamp at all
    rows["b" * 32] = _capability("b" * 32, created_at="whenever")  # unparseable
    rows["c" * 32] = _capability("c" * 32)  # readable, and S3 will not answer

    s3 = _ReconcileS3(unreadable={f"program-bundles/{'c' * 32}/bundle.zip"})
    findings = _reconcile(tables, s3)["findings"]
    by_key = {f["key"]: f for f in findings}

    assert by_key["a" * 32]["kind"] == "undelivered"
    assert by_key["a" * 32]["age_hours"] is None
    assert by_key["b" * 32]["age_hours"] is None
    assert by_key["c" * 32]["kind"] == "unreadable"
    assert "cannot vouch" in by_key["c" * 32]["action"]


def test_the_reconciler_names_the_order_a_failed_dispatch_left_behind(
    tables: dict[str, FakeTable],
) -> None:
    """The two rows a failed dispatch leaves, read together.

    This is the shape `setup` writes when it has claimed the checkout and
    GitHub then refuses: a capability row with no archive behind it, and a
    claim that never flipped to dispatched. Seeded here rather than driven
    through the handler, so this test describes the reconciler's contract
    with the table and not one particular version of the writer.
    """
    rows = tables["BUNDLES_TABLE"].items
    bundle_id = "a" * 32
    rows[bundle_id] = _capability(bundle_id, hours=24)
    rows["session#cs_test_example"] = {
        "bundle_id": "session#cs_test_example",
        "consumed_by": bundle_id,
        "plan": "bundle_25",
        "dispatched": False,
    }

    findings = _reconcile(tables, _ReconcileS3())["findings"]
    assert sorted(f["kind"] for f in findings) == ["never_started", "undelivered"]
    counts = reconcile_handler.counts_by_kind(findings)
    assert counts == {
        "deadline_breached": 0,
        "undelivered": 1,
        "never_started": 1,
        "abandoned_checkout": 0,
        "unreadable": 0,
    }


def test_the_public_issue_carries_counts_and_nothing_that_identifies_anybody(
    tables: dict[str, FakeTable],
) -> None:
    """The leak test. This repository is public and so are its issues.

    Every identifying field the reconciler holds is either a credential or a
    customer's own details: a bundle id IS the download capability, and
    `deliver_to`, `program_name` and the agency list describe a paying buyer.
    The findings below are stuffed with all of them, in every field the
    walker produces, so this fails if any of it can reach the body.

    The structural reason it cannot is that `issue_body` is given counts and
    never sees a finding. This is the test that keeps that true: the artifact
    name in report-bundle.yml was careful once too.
    """
    secrets = {
        "bundle_id": "d4f1a9c7e2b06835a1c4d9e7f2b60853",
        "deliver_to": "liaison@example.org",
        "email": "buyer@example.org",
        "program_name": "Yolo County Transportation District",
        "key": "session#cs_test_51QexampleSessionReference",
        "plan": "bundle_100",
        "action": "agency_ids unitrans,yolobus; customer cus_example; price price_example",
    }
    # `source` is deliberately not in that list: it is one of two constants
    # ("checkout" or "refresh"), identifies nobody, and "checkout" is a
    # substring of the `abandoned_checkout` count label the body must print.
    # A leak test that fires on a non-secret is one somebody weakens later.
    findings = [
        {"kind": kind, "age_hours": 42.0, "source": "checkout", **secrets}
        for kind in reconcile_handler.KINDS
    ]

    counts = reconcile_handler.counts_by_kind(findings)
    body = reconcile_handler.issue_body(counts)
    title = reconcile_handler.issue_title(counts)
    published = f"{title}\n{body}"

    for field, value in secrets.items():
        assert value not in published, f"{field} reached a public issue"
    # And the shapes, not just these literals: a 32-hex capability, an email
    # address, a Stripe reference.
    assert not re.search(r"\b[0-9a-f]{32}\b", published), "a capability-shaped id reached the issue"
    assert "@" not in published, "an address-shaped string reached the issue"
    assert not re.search(r"\b(cs|cus|sub|price|pi|ch)_[A-Za-z0-9]{6,}", published), (
        "a Stripe-shaped reference reached the issue"
    )
    # What it does carry. One of the kinds is a breach, so the title escalates.
    assert title == "REFUND DUE: 1 program order past the promised delivery date"
    for kind in reconcile_handler.KINDS:
        assert f"{kind:<20}1" in body, kind
    assert reconcile_handler.LOG_GROUP in body


def test_the_reconciler_keeps_one_standing_issue_and_never_closes_it(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """A daily schedule over a standing problem must not open an issue every
    morning, and must not edit the same one every morning either: an issue
    that churns daily stops being read. So the body is compared, and written
    only when it differs. Nothing is ever closed; a human decides that."""
    issues = _FakeIssues()
    monkeypatch.setattr(reconcile_handler, "github_request", issues.request)

    findings = [{"kind": "undelivered", "age_hours": 9.0}]
    assert reconcile_handler.report_findings(findings) == "opened"
    assert len(issues.open) == 1
    assert issues.open[0]["labels"] == [reconcile_handler.ISSUE_LABEL]

    # Same findings tomorrow: nothing is written at all.
    assert reconcile_handler.report_findings(findings) == "unchanged"
    assert len(issues.open) == 1 and issues.patches == []

    # A changed count edits the one issue rather than opening a second.
    assert reconcile_handler.report_findings(findings * 3) == "updated"
    assert len(issues.open) == 1
    assert issues.patches[0]["title"] == "3 program orders need attention"
    assert [m for m, _ in issues.calls if m == "DELETE"] == []
    assert not any("state" in patch for patch in issues.patches), "nothing closes an issue"

    # An issue somebody else labelled is not ours to overwrite.
    issues.open = [{"number": 99, "title": "unrelated", "body": "no marker here"}]
    assert reconcile_handler.report_findings(findings) == "opened"
    assert len(issues.open) == 2


def test_the_reconciler_fails_loudly_when_it_cannot_file_the_report(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """Alerting that silently cannot reach anyone is the defect this module
    exists to close, so it must not be reintroduced one layer up. A run that
    found paid orders and could not report them fails, and says which
    permission is the likely cause rather than making somebody guess."""
    tables["BUNDLES_TABLE"].items["a" * 32] = _capability("a" * 32)
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3(_ReconcileS3()))
    monkeypatch.setattr(reconcile_handler, "github_request", _FakeIssues(fail=True).request)

    with pytest.raises(RuntimeError, match="Issues: Read and write"):
        reconcile_handler.handler({}, None)


def test_reconcile_handler_files_the_report_and_honours_the_gates(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    tables["BUNDLES_TABLE"].items["a" * 32] = _capability("a" * 32)
    issues = _FakeIssues()
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3(_ReconcileS3()))
    monkeypatch.setattr(reconcile_handler, "github_request", issues.request)

    out = reconcile_handler.handler({}, None)
    assert out == {
        "ok": True,
        "payments_enabled": True,
        "scanned": 1,
        "findings": 1,
        "reported": "opened",
        "dry_run": False,
    }
    assert len(issues.open) == 1

    # A dry run looks and files nothing.
    dry = reconcile_handler.handler({"dry_run": True}, None)
    assert dry["reported"] == "dry_run" and dry["dry_run"] is True
    assert len(issues.open) == 1

    # And the commercial gate closes it entirely.
    monkeypatch.setenv("PAYMENTS_ENABLED", "0")
    assert reconcile_handler.handler({}, None) == {
        "ok": True,
        "payments_enabled": False,
        "dry_run": False,
    }
    assert len(issues.open) == 1


def test_reconcile_handler_raises_when_the_bucket_would_not_answer(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """An outage must not be filed as an all-clear, and it must not be filed
    as a delivered order either. The run fails so somebody sees it."""
    tables["BUNDLES_TABLE"].items["a" * 32] = _capability("a" * 32)
    s3 = _ReconcileS3(unreadable={f"program-bundles/{'a' * 32}/bundle.zip"})
    issues = _FakeIssues()
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3(s3))
    monkeypatch.setattr(reconcile_handler, "github_request", issues.request)

    with pytest.raises(RuntimeError, match="could not be read"):
        reconcile_handler.handler({}, None)
    # The report still went out: the orders it could read are still filed.
    assert len(issues.open) == 1


# ---------------------------------------------------------------------------
# the reconciler's schedule, read from terraform
# ---------------------------------------------------------------------------


def test_the_reconcile_schedule_cannot_be_enabled_with_no_way_to_report() -> None:
    """A job that finds paid orders and cannot tell anyone is the defect this
    module exists to close, so the schedule must not be able to run in that
    state.

    The gate it replaced was `ses_from != ""`, a non-blank string that named
    an address on a domain with no MX record. **Non-blank is not reachable**,
    and that is the whole lesson: what gates the rule now is an explicit
    readiness switch, defaulting off, whose description carries the two
    things to confirm before it is flipped.
    """
    terraform = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
    rule = terraform[terraform.index('resource "aws_cloudwatch_event_rule" "daily_reconcile"') :]
    rule = rule[: rule.index("resource ", 1)]
    state = next(line for line in rule.splitlines() if line.strip().startswith("state"))

    assert "var.reconciler_reporting_ready" in state, (
        "the schedule must be gated on a reporting channel confirmed reachable"
    )
    assert 'var.payments_enabled == "1"' in state, "the commercial gate still applies"
    assert "ENABLED" in state and "DISABLED" in state

    # Default off: a plain apply leaves it disabled, so switching it on is a
    # deliberate act and not a surprise from an unrelated apply.
    declaration = terraform[terraform.index('variable "reconciler_reporting_ready"') :]
    declaration = declaration[: declaration.index("\n}")]
    assert "default     = false" in declaration
    assert "Issues: Read and write" in declaration, (
        "the exact permission the design depends on belongs where the operator reads it"
    )
    assert "program-bundle-reconciler" in declaration, (
        "the label has to exist before the first report, so say so here"
    )

    # And the dead email configuration is gone rather than left wired to
    # nothing, so nobody sets it and expects an alert.
    assert "ses_from" not in terraform
    assert "ses:SendEmail" not in terraform


# ---------------------------------------------------------------------------
# the delivery promise, end to end through the handlers
# ---------------------------------------------------------------------------


def test_setup_records_the_promised_date_and_tells_the_buyer(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """The date is computed once, stored on the order, returned to the page
    and carried into the workflow. Four places, one computation: the page
    does not work it out again, and neither does the email."""
    from scorecard_pipeline import deadline as dl

    dispatched: list[dict[str, str]] = []
    # Monday 14 September 2026, 09:00 in the promise's own zone.
    checkout = 1789401600
    _stripe(monkeypatch, _paid_session(created=checkout), price=PRICE_BUNDLE_25)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    resp = setup_handler.handler(_setup_event(_form()))
    assert resp["statusCode"] == 200, resp["body"]
    body = json.loads(resp["body"])

    expected = dl.deadline_date(dl.from_epoch(checkout))
    assert body["deliver_by"] == expected.isoformat() == "2026-09-16"
    assert dl.spoken_date(expected) in body["promise"]
    assert "refunded" in body["promise"]

    row = tables["BUNDLES_TABLE"].items[body["bundle_id"]]
    assert row["deliver_by_epoch"] == dl.deadline_epoch(dl.from_epoch(checkout))
    assert row["deliver_by_anchor"] == "checkout"
    assert dispatched[0]["promised_by"] == dl.spoken_date(expected)


def test_the_promise_is_anchored_to_the_checkout_not_to_the_form(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """A buyer who pays on Friday and fills the form in on Monday was
    promised two business days from Friday. Anchoring on the form would hand
    us the weekend, which is the direction that quietly favours us."""
    from scorecard_pipeline import deadline as dl

    # Friday 11 September 2026, 16:00 in the promise's own zone. Two business
    # days on is Tuesday the 15th, and the weekend is not two of them.
    friday = 1789167600
    _stripe(monkeypatch, _paid_session(created=friday), price=PRICE_BUNDLE_25)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", lambda inputs: None)

    body = json.loads(setup_handler.handler(_setup_event(_form()))["body"])
    assert body["deliver_by"] == dl.deadline_date(dl.from_epoch(friday)).isoformat()
    assert body["deliver_by"] == "2026-09-15", "the weekend is not two business days"

    # A session with no `created` is the only case that falls back to now, and
    # the row says so rather than leaving it unanswerable.
    session = _paid_session()
    session.pop("created", None)
    _stripe(monkeypatch, session, price=PRICE_BUNDLE_25)
    tables["BUNDLES_TABLE"].items.clear()
    second = json.loads(
        setup_handler.handler(_setup_event(_form(session_id="cs_test_other")))["body"]
    )
    assert tables["BUNDLES_TABLE"].items[second["bundle_id"]]["deliver_by_anchor"] == "received"


def _promised(offset_days: float) -> int:
    return int((dt.datetime.now(dt.UTC) + dt.timedelta(days=offset_days)).timestamp())


def test_a_breached_order_is_reported_apart_from_a_merely_late_one(
    tables: dict[str, FakeTable],
) -> None:
    """One is a slow build, the other is a refund owed. They need different
    actions from a person, so they must not arrive as one number.

    The severity also has to survive into the notification: the issue body is
    counts and counts are unranked, so the title is the only place the
    difference can be carried, and it carries it."""
    rows = tables["BUNDLES_TABLE"].items
    rows["a" * 32] = _capability("a" * 32, hours=72, deliver_by_epoch=_promised(-1))
    rows["b" * 32] = _capability("b" * 32, hours=72, deliver_by_epoch=_promised(+1))
    rows["c" * 32] = _capability("c" * 32, hours=72)  # a refresh: no promise

    findings = _reconcile(tables, _ReconcileS3())["findings"]
    by_kind = {f["key"]: f["kind"] for f in findings}
    assert by_kind["a" * 32] == "deadline_breached"
    assert by_kind["b" * 32] == "undelivered"
    assert by_kind["c" * 32] == "undelivered"

    counts = reconcile_handler.counts_by_kind(findings)
    assert counts["deadline_breached"] == 1
    assert counts["undelivered"] == 2

    title = reconcile_handler.issue_title(counts)
    assert title.startswith("REFUND DUE"), title
    assert "1 program order past the promised delivery date" in title
    # And the breach says what to do, which is not what a late build says.
    breach = next(f for f in findings if f["kind"] == "deadline_breached")
    assert "PAST THE PROMISED DATE" in breach["action"]
    assert "program-refunds" in breach["action"]


def test_a_delivered_order_never_breaches_however_late_it_was(
    tables: dict[str, FakeTable],
) -> None:
    """Late and delivered is not a refund by this machinery's reckoning. The
    buyer may still be owed one; that is a judgement, and it is hers."""
    rows = tables["BUNDLES_TABLE"].items
    rows["a" * 32] = _capability("a" * 32, hours=72, deliver_by_epoch=_promised(-5))
    s3 = _ReconcileS3(present={f"program-bundles/{'a' * 32}/bundle.zip"})
    assert _reconcile(tables, s3)["findings"] == []


def test_the_title_does_not_escalate_when_nothing_is_owed(
    tables: dict[str, FakeTable],
) -> None:
    tables["BUNDLES_TABLE"].items["a" * 32] = _capability("a" * 32, hours=72)
    findings = _reconcile(tables, _ReconcileS3())["findings"]
    title = reconcile_handler.issue_title(reconcile_handler.counts_by_kind(findings))
    assert title == "1 program order needs attention"
    assert "REFUND" not in title
