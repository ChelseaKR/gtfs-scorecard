"""Unit tests for the program-bundle Lambdas (infra/program-bundle): the
Stripe signature check, the post-checkout setup route (paid gate, what was
actually bought, the plan's agency cap, idempotent session claim, dispatch),
the download route, the webhook's event handling, and the weekly refresh.
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


class FakeTable:
    """Enough of a DynamoDB Table for these handlers: a dict with the
    conditional-put and update shapes they use."""

    def __init__(self, items: dict[str, dict[str, Any]] | None = None, key: str = "bundle_id"):
        self.key = key
        self.items: dict[str, dict[str, Any]] = dict(items or {})
        self.updates: list[dict[str, Any]] = []

    def put_item(self, Item: dict[str, Any], ConditionExpression: str | None = None) -> None:
        if ConditionExpression and Item[self.key] in self.items:
            raise ConditionalCheckFailedException("exists")
        self.items[Item[self.key]] = dict(Item)

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        item = self.items.get(Key[self.key])
        return {"Item": item} if item else {}

    def update_item(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)
        key_value = kwargs["Key"][self.key]
        # The only conditional update these handlers use: "write this only if
        # the row already exists". Honouring it here is the difference between
        # a test that proves a foreign subscription creates no row and one
        # that would pass either way.
        condition = kwargs.get("ConditionExpression")
        if condition and condition.startswith("attribute_exists") and key_value not in self.items:
            raise ConditionalCheckFailedException(condition)
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
    for mod in (common, setup_handler, webhook_handler, refresh_handler):
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
        "dispatched": 2,
        "would_dispatch": 0,
        "failed": 1,
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
