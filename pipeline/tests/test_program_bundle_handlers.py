"""Unit tests for the program-bundle Lambdas (infra/program-bundle): the
Stripe signature check, the post-checkout setup route (paid gate, idempotent
session claim, dispatch), the download route, the webhook's event handling,
and the weekly refresh. Same harness as test_infra_handlers.py: the modules
load from their files, boto3 stays lazy, tables are fakes, and the two
network calls (GitHub dispatch, Stripe session read) are monkeypatched.

The Stripe event fixtures are shaped like Stripe's, with ids that follow
its prefixes but are not real objects, and no key-shaped strings anywhere."""

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
        row = self.items.setdefault(kwargs["Key"][self.key], {self.key: kwargs["Key"][self.key]})
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
    }


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
    monkeypatch.setattr(setup_handler, "stripe_get", lambda path: _paid_session())
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
    assert tables["SUBSCRIPTIONS_TABLE"].items == {}


def test_setup_subscription_stores_the_request_for_the_refresh(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    session = _paid_session(mode="subscription", subscription="sub_example")
    monkeypatch.setattr(setup_handler, "stripe_get", lambda path: session)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", lambda inputs: None)

    resp = setup_handler.handler(_setup_event(_form(deliver_to="")))
    assert resp["statusCode"] == 200
    sub = tables["SUBSCRIPTIONS_TABLE"].items["sub_example"]
    assert sub["status"] == "active"
    stored = json.loads(sub["request"])
    assert stored["cadence"] == "monthly"
    # No deliver_to in the form: the payer's email from the session is used.
    assert stored["deliver_to"] == "buyer@example.org"


def test_setup_refuses_unpaid_sessions_and_replays(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    monkeypatch.setattr(
        setup_handler, "stripe_get", lambda path: _paid_session(payment_status="unpaid")
    )
    assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 402

    monkeypatch.setattr(setup_handler, "stripe_get", lambda path: _paid_session())
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
    monkeypatch.setattr(setup_handler, "stripe_get", lambda path: _paid_session())
    resp = setup_handler.handler(_setup_event(_form(agency_ids="")))
    assert resp["statusCode"] == 400
    assert "at least one agency" in resp["body"]
    assert tables["BUNDLES_TABLE"].items == {}


def test_setup_reports_upstream_failures_without_losing_the_order(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    def stripe_down(path: str) -> dict[str, Any]:
        raise common.UpstreamError("stripe 500")

    monkeypatch.setattr(setup_handler, "stripe_get", stripe_down)
    assert setup_handler.handler(_setup_event(_form()))["statusCode"] == 502

    def github_down(inputs: dict[str, str]) -> None:
        raise common.UpstreamError("github 500")

    monkeypatch.setattr(setup_handler, "stripe_get", lambda path: _paid_session())
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


def test_webhook_tracks_subscription_lifecycle(tables: dict[str, FakeTable]) -> None:
    created = _event(
        "customer.subscription.created", {"id": "sub_1", "status": "trialing", "customer": "cus_1"}
    )
    assert json.loads(webhook_handler.handler(_webhook(created))["body"])["outcome"] == "updated"
    assert tables["SUBSCRIPTIONS_TABLE"].items["sub_1"]["status"] == "active"

    past_due = _event("customer.subscription.updated", {"id": "sub_1", "status": "past_due"})
    webhook_handler.handler(_webhook(past_due))
    assert tables["SUBSCRIPTIONS_TABLE"].items["sub_1"]["status"] == "past_due"

    deleted = _event("customer.subscription.deleted", {"id": "sub_1", "status": "canceled"})
    assert json.loads(webhook_handler.handler(_webhook(deleted))["body"])["outcome"] == "canceled"
    row = tables["SUBSCRIPTIONS_TABLE"].items["sub_1"]
    assert row["status"] == "canceled"
    assert row["canceled_at"]


def test_webhook_notes_checkouts_and_ignores_everything_else(tables: dict[str, FakeTable]) -> None:
    completed = _event(
        "checkout.session.completed",
        {"id": "cs_test_1", "mode": "payment", "customer_details": {"email": "b@example.org"}},
    )
    assert json.loads(webhook_handler.handler(_webhook(completed))["body"])["outcome"] == "noted"
    assert tables["BUNDLES_TABLE"].items["checkout#cs_test_1"]["email"] == "b@example.org"
    other = _event("invoice.paid", {"id": "in_1"})
    assert json.loads(webhook_handler.handler(_webhook(other))["body"])["outcome"] == "ignored"
    bad = b"not json"
    assert webhook_handler.handler(_webhook(bad))["statusCode"] == 400


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
    base: dict[str, Any] = {"id": "sub_1", "status": "active", "request": json.dumps(request)}
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
    assert counts == {"scanned": 5, "due": 3, "dispatched": 2, "failed": 1}
    assert {d["cadence"] for d in dispatched} == {"monthly"}
    assert len({d["bundle_id"] for d in dispatched}) == 2
    assert all(len(d["bundle_id"]) == 32 for d in dispatched)
    assert subs.items["sub_never"]["last_bundle_id"] in tables["BUNDLES_TABLE"].items
    assert subs.items["sub_old"]["last_refresh"]
    assert "last_refresh" not in subs.items["sub_broken"]
    assert subs.items["sub_recent"]["last_refresh"] == "2026-09-20T00:00:00+00:00"


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


def test_refresh_handler_entrypoint_reports_counts(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", lambda inputs: None)
    out = refresh_handler.handler({}, None)
    assert out["ok"] is True
    assert out["scanned"] == 0
