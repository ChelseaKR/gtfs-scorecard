"""The history tables' delivery path in infra/program-bundle (ADR 0063, phase 2).

A paid ``history_once`` checkout is answered by the setup route with a 30-day
capability link to the newest ``history/<YYYY-MM>/history.zip`` and an email;
nothing is built and no workflow is dispatched. These tests hold that branch
to its refusals (tier closed, store unreadable, no build yet: each with the
checkout left unused), its idempotence (a reload answers the same link), the
download route's refusal to presign any key but the one a row may name, the
entitlement scan's indifference to history rows, and the reconciler's reading
of the named key. The Lambda modules are loaded the way the Lambda loads them
and the AWS clients are fakes, as in test_program_bundle_handlers.py.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE_DIR = REPO / "infra" / "program-bundle"

PRICE_BUNDLE_25 = "price_bundle25example"
PRICE_HISTORY = "price_historyexample"
PRICE_FOREIGN = "price_somethingelseexample"
CONFIGURED = json.dumps(
    {
        "bundle_25": PRICE_BUNDLE_25,
        "bundle_100": "price_bundle100example",
        "refresh_mo": "price_refreshmoexample",
        "refresh_yr": "price_refreshyrexample",
        "history_once": PRICE_HISTORY,
    }
)
NEWEST = "history/2026-10/history.zip"
OLDER = "history/2026-09/history.zip"


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


common = _load("common")
_load("conversion_tracking")  # imported by name from webhook_handler, as the Lambda does
setup_handler = _load("setup_handler")
webhook_handler = _load("webhook_handler")
reconcile_handler = _load("reconcile_handler")


class ConditionalCheckFailedException(Exception):
    pass


class FakeTable:
    """A DynamoDB table with the conditional put, get, update and scan these
    handlers use; one page, no filter evaluation needed for the rows here."""

    def __init__(self, key: str = "bundle_id") -> None:
        self.key = key
        self.items: dict[str, dict[str, Any]] = {}

    def put_item(self, Item: dict[str, Any], **kwargs: Any) -> None:
        if "ConditionExpression" in kwargs and Item[self.key] in self.items:
            raise ConditionalCheckFailedException(kwargs["ConditionExpression"])
        self.items[Item[self.key]] = dict(Item)

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        row = self.items.get(Key[self.key])
        return {"Item": dict(row)} if row is not None else {}

    def update_item(self, Key: dict[str, Any], **kwargs: Any) -> None:
        row = self.items.setdefault(Key[self.key], {self.key: Key[self.key]})
        values = kwargs.get("ExpressionAttributeValues", {})
        names = kwargs.get("ExpressionAttributeNames", {})
        for clause in kwargs["UpdateExpression"].removeprefix("SET ").split(","):
            target, _, placeholder = clause.strip().partition(" = ")
            row[names.get(target, target)] = values[placeholder]

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        return {"Items": [dict(row) for row in self.items.values()]}


class FakeS3:
    """list_objects_v2 over a set of keys (paged when asked), head_object with
    the three answers that matter, and a presign that records its parameters."""

    def __init__(
        self, keys: list[str] | None = None, *, page: int | None = None, fail: bool = False
    ) -> None:
        self.keys = list(keys or [])
        self.page = page
        self.fail = fail
        self.listed: list[dict[str, Any]] = []
        self.presigned: dict[str, Any] | None = None

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        self.listed.append(dict(kwargs))
        if self.fail:
            raise RuntimeError("SlowDown")
        prefix = str(kwargs.get("Prefix") or "")
        matching = sorted(k for k in self.keys if k.startswith(prefix))
        start = int(kwargs.get("ContinuationToken") or 0)
        if self.page is None:
            return {"Contents": [{"Key": k} for k in matching], "IsTruncated": False}
        chunk = matching[start : start + self.page]
        more = start + self.page < len(matching)
        out: dict[str, Any] = {"Contents": [{"Key": k} for k in chunk], "IsTruncated": more}
        if more:
            out["NextContinuationToken"] = str(start + self.page)
        return out

    def head_object(self, Bucket: str, Key: str) -> None:
        if Key not in self.keys:
            raise KeyError("404")

    def generate_presigned_url(self, op: str, Params: dict[str, Any], ExpiresIn: int) -> str:
        self.presigned = {"op": op, **Params, "expires": ExpiresIn}
        return "https://s3.example/presigned"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPO", "example/scorecard")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "test-restricted-key")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "test-signing-secret")
    monkeypatch.setenv("ARTIFACTS_BUCKET", "example-artifacts")
    monkeypatch.setenv("SUBSCRIPTIONS_TABLE", "subs")
    monkeypatch.setenv("BUNDLES_TABLE", "bundles")
    monkeypatch.setenv("PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("HISTORY_ENABLED", "1")
    monkeypatch.setenv("SES_FROM", "scorecard@example.org")
    monkeypatch.setenv("STRIPE_PRICE_IDS", CONFIGURED)


@pytest.fixture
def tables(monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeTable]:
    fakes = {"SUBSCRIPTIONS_TABLE": FakeTable(key="id"), "BUNDLES_TABLE": FakeTable()}
    for mod in (common, setup_handler, webhook_handler, reconcile_handler):
        monkeypatch.setattr(mod, "table", lambda env, fakes=fakes: fakes[env])
    return fakes


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Mail the setup route sent, captured instead of handed to SES."""
    mails: list[dict[str, str]] = []

    def fake_send(to: str, subject: str, body: str) -> None:
        mails.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(setup_handler, "send_email", fake_send)
    return mails


def _s3(monkeypatch: pytest.MonkeyPatch, s3: FakeS3) -> FakeS3:
    fake_boto3 = type("boto3", (), {"client": staticmethod(lambda *a, **k: s3)})
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    return s3


def _session(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "cs_test_history",
        "object": "checkout.session",
        "mode": "payment",
        "payment_status": "paid",
        "customer": "cus_example",
        "customer_details": {"email": "Analyst@Example.org"},
        "subscription": None,
        "created": 1_790_000_000,
    }
    base.update(overrides)
    return base


def _stripe(
    monkeypatch: pytest.MonkeyPatch,
    *,
    price: str = PRICE_HISTORY,
    session: dict[str, Any] | None = None,
) -> None:
    served = session if session is not None else _session()
    items = {
        "object": "list",
        "has_more": False,
        "data": [{"id": "li_1", "object": "item", "quantity": 1, "price": {"id": price}}],
    }

    def fake_get(path: str) -> dict[str, Any]:
        return items if "/line_items" in path else served

    monkeypatch.setattr(common, "stripe_get", fake_get)
    monkeypatch.setattr(setup_handler, "stripe_get", fake_get)


def _event(session_id: str = "cs_test_history") -> dict[str, Any]:
    return {
        "rawPath": "/setup",
        "requestContext": {
            "domainName": "api.example.test",
            "http": {"method": "POST", "path": "/setup"},
        },
        "body": json.dumps({"session_id": session_id}),
    }


def _download_event(bundle_id: str) -> dict[str, Any]:
    return {
        "rawPath": f"/download/{bundle_id}",
        "requestContext": {"http": {"method": "GET", "path": f"/download/{bundle_id}"}},
    }


# --- recognizing the plan -------------------------------------------------------------


def test_the_history_price_is_a_recognized_plan_and_a_blank_one_sells_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert common.price_plans()[PRICE_HISTORY] == "history_once"
    assert "history_once" in common.KNOWN_PLANS
    assert "history_once" not in common.PLAN_AGENCY_CAPS
    monkeypatch.setenv(
        "STRIPE_PRICE_IDS", json.dumps({**json.loads(CONFIGURED), "history_once": ""})
    )
    assert PRICE_HISTORY not in common.price_plans()


def test_history_is_closed_unless_both_gates_are_open(monkeypatch: pytest.MonkeyPatch) -> None:
    assert common.history_enabled()
    monkeypatch.setenv("HISTORY_ENABLED", "0")
    assert not common.history_enabled()
    monkeypatch.setenv("HISTORY_ENABLED", "1")
    monkeypatch.setenv("PAYMENTS_ENABLED", "0")
    assert not common.history_enabled()


def test_newest_object_is_by_month_across_pages_and_ignores_strays() -> None:
    s3 = FakeS3(
        keys=[
            OLDER,
            "history/2026-11/PROVENANCE.json",
            "history/notes.txt",
            NEWEST,
            "history/2026-08/history.zip",
        ],
        page=2,
    )
    assert common.newest_history_object(s3, "b") == (NEWEST, "2026-10")
    assert len(s3.listed) == 3, "the listing was not followed to the end"
    assert all(call["Prefix"] == "history/" for call in s3.listed)
    assert (
        common.newest_history_object(FakeS3(keys=["history/2026-11/PROVENANCE.json"]), "b") is None
    )


# --- the setup branch -----------------------------------------------------------------


def test_a_paid_history_checkout_gets_a_capability_for_the_newest_object_and_an_email(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable], sent: list[dict[str, str]]
) -> None:
    _stripe(monkeypatch)
    s3 = _s3(monkeypatch, FakeS3(keys=[OLDER, NEWEST]))
    dispatched: list[str] = []
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    resp = setup_handler.handler(_event())
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200, body
    assert body["ok"] is True and body["month"] == "2026-10" and body["emailed"] is True
    assert body["download_url"] == f"https://api.example.test/download/{body['bundle_id']}"
    assert body["expires_in_days"] == 30
    assert dispatched == [], "a history purchase dispatches no build"

    rows = tables["BUNDLES_TABLE"].items
    row = rows[body["bundle_id"]]
    assert row["archive_key"] == NEWEST and row["source"] == "history"
    assert row["plan"] == "history_once" and row["product"] == "history"
    assert row["deliver_to"] == "analyst@example.org", "the address Stripe collected, case-folded"
    assert row["order_ref"] == "" and row["program_name"] == ""
    assert "deliver_by_epoch" not in row, (
        "no two-business-day promise is made for an instant delivery"
    )
    claim = rows["session#cs_test_history"]
    assert claim["consumed_by"] == body["bundle_id"] and claim["plan"] == "history_once"
    assert claim["dispatched"] is True, (
        "the reconciler must not read this claim as a build that never started"
    )
    assert s3.listed, "the store was listed, not guessed"

    assert len(sent) == 1
    mail = sent[0]
    assert mail["to"] == "analyst@example.org"
    assert body["download_url"] in mail["body"] and "2026-10" in mail["body"]
    assert "LICENSE.md" in mail["body"] and "never for sale" in mail["body"]
    assert "$" not in mail["body"], "the email states no price; the receipt is Stripe's"


def test_a_reload_answers_the_same_link_and_consumes_nothing_twice(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable], sent: list[dict[str, str]]
) -> None:
    _stripe(monkeypatch)
    _s3(monkeypatch, FakeS3(keys=[NEWEST]))
    first = json.loads(setup_handler.handler(_event())["body"])
    again = setup_handler.handler(_event())
    body = json.loads(again["body"])
    assert again["statusCode"] == 200
    assert body["bundle_id"] == first["bundle_id"]
    assert body["download_url"] == first["download_url"]
    assert body["already_issued"] is True
    assert len(sent) == 1, "the second visit does not send a second email"
    capability_rows = [k for k in tables["BUNDLES_TABLE"].items if "#" not in k]
    assert capability_rows == [first["bundle_id"]]


@pytest.mark.parametrize(
    ("arrange", "status", "phrase"),
    [
        (lambda m: m.setenv("HISTORY_ENABLED", "0"), 503, "not on sale"),
        (lambda m: None, 503, "No monthly history build"),
    ],
    ids=["tier closed", "no build yet"],
)
def test_the_branch_refuses_before_claiming_when_it_cannot_deliver(
    monkeypatch: pytest.MonkeyPatch,
    tables: dict[str, FakeTable],
    sent: list[dict[str, str]],
    arrange: Any,
    status: int,
    phrase: str,
) -> None:
    _stripe(monkeypatch)
    _s3(monkeypatch, FakeS3(keys=["history/2026-10/PROVENANCE.json"]))
    arrange(monkeypatch)
    resp = setup_handler.handler(_event())
    body = json.loads(resp["body"])
    assert resp["statusCode"] == status
    assert phrase in body["error"] and "checkout has not been used" in body["error"]
    assert tables["BUNDLES_TABLE"].items == {}, "nothing was claimed and no capability was written"
    assert sent == []


def test_an_unreadable_store_is_not_an_empty_store(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable], sent: list[dict[str, str]]
) -> None:
    _stripe(monkeypatch)
    _s3(monkeypatch, FakeS3(keys=[NEWEST], fail=True))
    resp = setup_handler.handler(_event())
    assert resp["statusCode"] == 502
    assert "Could not read the history store" in json.loads(resp["body"])["error"]
    assert tables["BUNDLES_TABLE"].items == {} and sent == []


def test_a_mail_failure_is_reported_as_a_mail_failure_not_an_undelivered_order(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    _stripe(monkeypatch)
    _s3(monkeypatch, FakeS3(keys=[NEWEST]))

    def refuse(to: str, subject: str, body: str) -> None:
        raise common.UpstreamError("sending the delivery email failed: ClientError")

    monkeypatch.setattr(setup_handler, "send_email", refuse)
    resp = setup_handler.handler(_event())
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200 and body["ok"] is True
    assert body["emailed"] is False
    assert body["bundle_id"] in tables["BUNDLES_TABLE"].items, (
        "the link exists; only the copy by mail failed"
    )


def test_a_checkout_without_an_email_still_gets_its_link_on_the_page(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable], sent: list[dict[str, str]]
) -> None:
    _stripe(monkeypatch, session=_session(customer_details={}))
    _s3(monkeypatch, FakeS3(keys=[NEWEST]))
    body = json.loads(setup_handler.handler(_event())["body"])
    assert body["ok"] is True and body["emailed"] is False
    assert sent == []
    assert tables["BUNDLES_TABLE"].items[body["bundle_id"]]["deliver_to"] == ""


def test_a_bundle_checkout_still_takes_the_bundle_path(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable], sent: list[dict[str, str]]
) -> None:
    """The history branch is taken on the plan alone; a bundle purchase with no
    form fields is refused by the bundle path's own validation, untouched."""
    _stripe(monkeypatch, price=PRICE_BUNDLE_25)
    _s3(monkeypatch, FakeS3(keys=[NEWEST]))
    resp = setup_handler.handler(_event())
    assert resp["statusCode"] == 400, json.loads(resp["body"])
    assert sent == []


# --- the download route ---------------------------------------------------------------


def test_download_presigns_the_key_a_history_row_names_with_a_dated_filename(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    bundle_id = "a" * 32
    tables["BUNDLES_TABLE"].items[bundle_id] = {"bundle_id": bundle_id, "archive_key": NEWEST}
    s3 = _s3(monkeypatch, FakeS3(keys=[NEWEST]))
    resp = setup_handler.handler(_download_event(bundle_id))
    assert resp["statusCode"] == 302
    assert s3.presigned is not None and s3.presigned["Key"] == NEWEST
    assert (
        s3.presigned["ResponseContentDisposition"]
        == 'attachment; filename="gtfs-scorecard-history-2026-10.zip"'
    )
    assert s3.presigned["expires"] == setup_handler.PRESIGN_SECONDS


def test_download_still_derives_a_bundle_row_key_and_filename(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    bundle_id = "b" * 32
    tables["BUNDLES_TABLE"].items[bundle_id] = {"bundle_id": bundle_id}
    s3 = _s3(monkeypatch, FakeS3(keys=[f"program-bundles/{bundle_id}/bundle.zip"]))
    assert setup_handler.handler(_download_event(bundle_id))["statusCode"] == 302
    assert s3.presigned is not None
    assert s3.presigned["Key"] == f"program-bundles/{bundle_id}/bundle.zip"
    assert (
        s3.presigned["ResponseContentDisposition"]
        == f'attachment; filename="board-reports-{bundle_id[:8]}.zip"'
    )


@pytest.mark.parametrize(
    "named",
    [
        "feeds/abc.zip",
        "history/2026-10/PROVENANCE.json",
        "program-requests/x.json",
        "history/../feeds/x.zip",
    ],
)
def test_download_refuses_a_row_that_names_any_other_key(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable], named: str
) -> None:
    bundle_id = "c" * 32
    tables["BUNDLES_TABLE"].items[bundle_id] = {"bundle_id": bundle_id, "archive_key": named}
    s3 = _s3(monkeypatch, FakeS3(keys=[named]))
    resp = setup_handler.handler(_download_event(bundle_id))
    assert resp["statusCode"] == 404
    assert s3.presigned is None, "nothing may be presigned for a key outside the two allowed shapes"


# --- the rest of the stack --------------------------------------------------------------


def test_the_entitlement_scan_skips_history_rows_without_asking_stripe(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    """A refresh on an address that only ever bought the history tables has no
    bundle to renew, and finding that out costs no Stripe read."""
    asked: list[str] = []

    def fake_checkout_plan(session_id: str) -> Any:
        asked.append(session_id)
        return None

    monkeypatch.setattr(setup_handler, "checkout_plan", fake_checkout_plan)
    bundles = tables["BUNDLES_TABLE"]
    bundles.items["session#cs_old"] = {
        "bundle_id": "session#cs_old",
        "plan": "history_once",
        "email": "analyst@example.org",
        "consumed_by": "d" * 32,
    }
    bundles.items["checkout#cs_older"] = {
        "bundle_id": "checkout#cs_older",
        "plan": "history_once",
        "email": "analyst@example.org",
    }
    session = _session(id="cs_refresh", customer_details={"email": "analyst@example.org"})
    with pytest.raises(setup_handler._Refused) as refused:
        setup_handler._inherited_cap(bundles, session, "cs_refresh")
    assert refused.value.response["statusCode"] == 403
    assert asked == [], "a history row is not an unsettled checkout"


def test_the_webhook_notes_a_history_checkout_under_its_plan(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, FakeTable]
) -> None:
    _stripe(monkeypatch)
    monkeypatch.setattr(webhook_handler, "note_conversion", lambda **kwargs: None)
    outcome = webhook_handler.apply_event(
        "checkout.session.completed",
        {"object": _session()},
        subscriptions=tables["SUBSCRIPTIONS_TABLE"],
        bundles=tables["BUNDLES_TABLE"],
    )
    assert outcome == "noted"
    assert tables["BUNDLES_TABLE"].items["checkout#cs_test_history"]["plan"] == "history_once"


def test_the_reconciler_heads_the_key_a_history_row_names() -> None:
    class ClientError(Exception):
        """Shaped like botocore's: the code is read off `.response`."""

        def __init__(self, code: str) -> None:
            super().__init__(code)
            self.response = {"Error": {"Code": code}}

    class S3:
        def __init__(self) -> None:
            self.asked: list[str] = []

        def head_object(self, Bucket: str, Key: str) -> None:
            self.asked.append(Key)
            if Key != NEWEST:
                raise ClientError("404")

    s3 = S3()
    assert reconcile_handler.artifact_state(s3, "b", "e" * 32, key=NEWEST) == "present"
    assert reconcile_handler.artifact_state(s3, "b", "e" * 32) == "missing"
    assert s3.asked == [NEWEST, f"program-bundles/{'e' * 32}/bundle.zip"]

    class Table:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self.rows = rows

        def scan(self, **kwargs: Any) -> dict[str, Any]:
            return {"Items": list(self.rows)}

    stale = "2026-01-01T00:00:00+00:00"
    gone = "history/2026-07/history.zip"
    table = Table(
        [
            {
                "bundle_id": "f" * 32,
                "archive_key": NEWEST,
                "created_at": stale,
                "source": "history",
            },
            {"bundle_id": "0" * 32, "archive_key": gone, "created_at": stale, "source": "history"},
        ]
    )
    report = reconcile_handler.reconcile(bundles=table, s3=S3(), bucket="b")
    kinds = {finding["key"]: finding for finding in report["findings"]}
    assert "f" * 32 not in kinds, "a history link whose object exists is delivered"
    finding = kinds["0" * 32]
    assert finding["kind"] == "undelivered"
    assert gone in finding["action"] and "history-export.yml" in finding["action"]
