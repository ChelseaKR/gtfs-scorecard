"""The paid path as one transaction, run against the real code with a
synthetic purchase.

Everything behind /bundle/ is unit-tested a piece at a time in
test_program_bundle_handlers.py (each Lambda), test_bundle.py (the build and
the delivery email) and test_workflow_safety.py (the fulfillment workflow's
own steps). Five joins between those pieces had never executed for a real buyer,
because each of them only happens when somebody buys something, and nobody
has in live mode:

1. **A Payment Link sends the buyer to the page that finishes the order.**
   The redirect is configured in Stripe, by ``scripts/stripe-setup.sh``. This
   module holds the script's declared redirect to the page that exists in this
   repository, and holds that page to accepting the reference Stripe
   substitutes into it. What it cannot check is whether the four links that
   are live today were created with that script; see ``docs/program-plan.md``.

2. **The setup page posts what the setup route reads.** Covered from the
   browser in tests/e2e/test_bundle_setup_form.py, which intercepts the real
   request the real page makes.

3. **The Lambda's ``workflow_dispatch`` is one report-bundle.yml accepts.**
   An input the workflow does not declare is a 422 from GitHub and a paid
   order that never starts; a declared input the Lambda omits with no default
   is the same 422. The dispatch now carries one input, ``order_ref``, because
   a public run log prints every input; the order itself is stored in the
   private bucket, and the key the Lambda writes has to be the key the
   workflow reads.

4. **The weekly tick rebuilds a subscription a month later.** The request is
   stored as JSON at checkout and read back by another Lambda four weeks on.
   Whether what comes back still parses and still builds had never been run.

5. **The webhook's record is what a later refresh inherits its cap from.**
   The ``checkout#`` row is written by the webhook, behind a real signature
   check, and read by the setup route months later. The two halves had only
   ever been tested against hand-written rows.

The transaction test below runs 1 purchase through the whole of it: the setup
route mints the bundle, stores the order and dispatches its reference, the
stored order is collected and fed to the same commands report-bundle.yml
runs, the archive lands under the key the
download route presigns, the email carries the URL that route answers on, and
the reconciler is asked -- with the archive there and with it gone -- whether
the order was delivered.

No Stripe object is created, read or touched anywhere here: Stripe is a
fixture, the same one test_program_bundle_handlers.py uses.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from scorecard_pipeline import bundle_order
from scorecard_pipeline.bundle import (
    BundleRequest,
    archive_key,
    build_bundle,
    parse_request,
)
from scorecard_pipeline.config import AGENCIES, Agency

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "report-bundle.yml"
PLAN_JSON = REPO / "web" / "bundle" / "plan.json"
STRIPE_SETUP = REPO / "scripts" / "stripe-setup.sh"
SETUP_JS = REPO / "web" / "src" / "bundle-setup.js"
SETUP_PAGE = REPO / "web" / "bundle" / "setup" / "index.html"

FROZEN = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.UTC)
BUNDLE_API_BASE = "https://api.example/bundle"


def _harness() -> Any:
    """The fakes and module loader from test_program_bundle_handlers.py.

    Loaded from its file under a name of its own rather than imported: the
    suite runs in importlib mode, so a sibling test module is not on the path,
    and a private copy keeps this module's handler objects consistent with its
    own fakes whichever order the two files are collected in.
    """
    spec = importlib.util.spec_from_file_location(
        "paid_path_harness", Path(__file__).parent / "test_program_bundle_handlers.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _harness()
common = H.common
setup_handler = H.setup_handler
webhook_handler = H.webhook_handler
refresh_handler = H.refresh_handler
reconcile_handler = H.reconcile_handler


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployed environment, as the harness module defines it."""
    monkeypatch.setenv("GITHUB_REPO", "example/scorecard")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "test-restricted-key")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", H.SIGNING_SECRET)
    monkeypatch.setenv("ARTIFACTS_BUCKET", "example-artifacts")
    monkeypatch.setenv("SUBSCRIPTIONS_TABLE", "subs")
    monkeypatch.setenv("BUNDLES_TABLE", "bundles")
    monkeypatch.setenv("PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_PRICE_IDS", H.CONFIGURED_PRICES)
    monkeypatch.delenv("DRY_RUN", raising=False)


@pytest.fixture
def tables(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    fakes = {
        "SUBSCRIPTIONS_TABLE": H.FakeTable(key="id"),
        "BUNDLES_TABLE": H.FakeTable(),
    }
    for mod in (common, setup_handler, webhook_handler, refresh_handler, reconcile_handler):
        monkeypatch.setattr(mod, "table", lambda env, fakes=fakes: fakes[env])
    return fakes


class _Bucket:
    """One object store, shared by everything that names a key.

    The upload, the download route and the reconciler each derive the key
    themselves. A separate fake per caller would let two of them disagree and
    still pass; one store means a disagreement is a missing object.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.presigned: dict[str, Any] | None = None

    def put(self, key: str, body: bytes) -> None:
        self.objects[key] = body

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_kwargs: Any) -> None:
        self.objects[Key] = Body

    def head_object(self, Bucket: str, Key: str) -> None:
        if Key not in self.objects:
            raise H._ClientError({"Error": {"Code": "404"}})

    def generate_presigned_url(
        self,
        op: str,
        Params: dict[str, Any],
        ExpiresIn: int,
    ) -> str:
        self.presigned = {"op": op, **Params, "expires": ExpiresIn}
        return f"https://s3.example/{Params['Key']}?signed"


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> _Bucket:
    store = _Bucket()
    monkeypatch.setitem(
        sys.modules, "boto3", type("boto3", (), {"client": staticmethod(lambda *a, **k: store)})
    )
    return store


def _publish_fixture(root: Path, agency_id: str) -> None:
    """A published artifact the report renderer can read, and an index entry.

    Copied from test_bundle.py rather than imported for the same reason
    ``_harness`` exists: importlib mode gives sibling modules no path to each
    other.
    """
    art = root / "data" / "artifacts"
    (art / agency_id).mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema_version": "1.5",
        "rubric_version": "1.2",
        "scoring_profile_id": "gtfs-scorecard-1.2",
        "scoring_profile_rubric_version": "1.2",
        "validator_version": "7.0.0",
        "snapshot_date": "2026-09-01",
        "agency": {"id": agency_id, "name": f"{agency_id.title()} Transit"},
        "feed": {"static_url": "https://example.org/gtfs.zip", "reachable": True},
        "overall": {"grade": "B", "score": 81.5},
        "categories": {
            "correctness": {
                "name": "correctness",
                "status": "measured",
                "score": 90.0,
                "weight": 0.35,
                "summary": "The validator flagged 2 kinds of issue.",
            },
            "freshness": {
                "name": "freshness",
                "status": "measured",
                "score": 100.0,
                "weight": 0.2,
                "summary": "Service data covers the next 60 days.",
                "details": {"days_until_expiry": 60},
            },
            "completeness": {
                "name": "completeness",
                "status": "measured",
                "score": 55.0,
                "weight": 0.25,
                "summary": "Wheelchair accessibility is unstated on most stops.",
            },
            "realtime": {
                "name": "realtime",
                "status": "not_yet_measured",
                "weight": 0.2,
                "summary": "No realtime feed is published yet. Nothing counts against the grade.",
            },
        },
        "top_fixes": [],
    }
    (art / agency_id / "latest.json").write_text(json.dumps(artifact))
    index = {
        "schema_version": "1",
        "agencies": {agency_id: {"name": f"{agency_id.title()} Transit"}},
    }
    (art / "index.json").write_text(json.dumps(index))


@pytest.fixture
def published(isolated_repo_root: Path) -> str:
    """One agency with a published scorecard, registered, ready to render."""
    agency_id = "sampletown"
    _publish_fixture(isolated_repo_root, agency_id)
    AGENCIES[agency_id] = Agency(
        id=agency_id, name="Sampletown Transit", static_gtfs_url="https://example.org/g.zip"
    )
    return agency_id


def _workflow() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return loaded


def _declared_inputs() -> dict[str, dict[str, Any]]:
    # PyYAML reads the bare key `on:` as the boolean True (YAML 1.1), so the
    # trigger block is looked up under both spellings rather than one.
    workflow: dict[Any, Any] = _workflow()
    triggers = workflow["on"] if "on" in workflow else workflow[True]
    declared: dict[str, dict[str, Any]] = triggers["workflow_dispatch"]["inputs"]
    assert declared, "report-bundle.yml declares no workflow_dispatch inputs at all"
    return declared


def _collect(bucket: _Bucket, order_ref: str, workdir: Path) -> Path:
    """What report-bundle.yml's collect step does: copy the stored order the
    dispatch names out of the bucket into request.json. The key is derived by
    the Lambda's own ``request_key``; the workflow spells the same prefix."""
    key = common.request_key(order_ref)
    assert key in bucket.objects, f"the Lambda dispatched {order_ref} and stored no order there"
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / "request.json"
    path.write_bytes(bucket.objects[key])
    return path


def _run_the_build(request_json: Path, out_zip: Path) -> tuple[BundleRequest, dict[str, Any]]:
    """What report-bundle.yml does with the collected order: mask, validate
    against the cap it was sold with, then render.

    ``bundle_order.main(["mask", ...])`` is the collect step's own command,
    and ``cap`` feeds ``scorecard bundle --max-agencies``; calling them here
    is the same steps without a runner.
    """
    assert bundle_order.main(["mask", str(request_json)]) == 0
    request, raw = bundle_order.load_order(request_json)
    manifest = build_bundle(
        parse_request(raw, max_agencies=bundle_order.order_cap(raw)), out_zip, now=FROZEN
    )
    return request, manifest


# ---------------------------------------------------------------------------
# Step 1: a Payment Link sends the buyer to the page that finishes the order
# ---------------------------------------------------------------------------


def test_a_payment_link_can_only_send_a_buyer_to_the_page_that_finishes_the_order() -> None:
    """The redirect is the only thing joining a completed checkout to this
    repository, and it is configured once, in Stripe, by a script here.

    Nothing else in the system notices if it is wrong. A link whose redirect
    points anywhere else takes the money, leaves the buyer on a page that
    cannot finish the order, and produces no row, no run and no finding: the
    webhook's ``checkout#`` note is all that would exist, and the reconciler
    would file it as an abandoned checkout weeks later.
    """
    script = STRIPE_SETUP.read_text(encoding="utf-8")
    assert 'success="${SITE}/bundle/setup/?session_id={CHECKOUT_SESSION_ID}"' in script, (
        "the Payment Links must redirect to the setup page carrying the session reference"
    )
    # Every link goes through the one helper that sets that redirect, so a
    # fifth price cannot be added with a redirect of its own.
    assert script.count("payment_links create") == 1, (
        "every Payment Link must be created by the one helper that sets the redirect"
    )
    assert script.count('-d "after_completion[redirect][url]=$success"') == 1
    assert SETUP_PAGE.is_file(), f"{SETUP_PAGE} is the page that redirect names"

    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    urls = [product["checkout_url"] for product in plan["products"].values()]
    assert len(set(urls)) == len(urls) == 4, "four products, four distinct checkouts"
    for url in urls:
        assert url.startswith("https://buy.stripe.com/"), f"{url} is not a Stripe Payment Link"


def test_the_setup_page_accepts_the_reference_stripe_substitutes() -> None:
    """``{CHECKOUT_SESSION_ID}`` becomes a ``cs_...`` id in the address bar.

    Both readers of it have to accept the same shape. The page refuses to
    submit unless the query string matches its own pattern, and the Lambda
    refuses a body whose ``session_id`` does not start with ``cs_``; a
    disagreement between the two is a paid buyer stuck on a form that will not
    send, with no way to reach anyone but the Stripe receipt.
    """
    source = SETUP_JS.read_text(encoding="utf-8")
    assert 'new URLSearchParams(location.search).get("session_id")' in source, (
        "the page must read the reference Stripe substitutes into the redirect"
    )
    assert "/^cs_[A-Za-z0-9_]+$/.test(sessionId)" in source
    # The Lambda's own guard, read from the module rather than restated.
    for reference in ("cs_test_a1B2c3", "cs_live_ZZ99"):
        assert reference.startswith("cs_") and len(reference) <= setup_handler._SESSION_ID_MAX


# ---------------------------------------------------------------------------
# Step 3: the dispatch is one the fulfillment workflow accepts
# ---------------------------------------------------------------------------


def test_every_input_the_lambda_dispatches_is_one_the_workflow_declares() -> None:
    """A ``workflow_dispatch`` naming an input the workflow does not declare
    is a 422, and so is one omitting a required input that has no default.

    Either way GitHub accepts no run, the setup route answers 502, and the
    buyer is told to send the form again -- for ever, because the next attempt
    posts the same inputs. These two files are edited independently and
    deployed independently, and nothing compared them: the first comparison
    would have been the first sale.
    """
    declared = _declared_inputs()
    posted: list[dict[str, Any]] = []

    def capture(method: str, url: str, headers: dict[str, str], payload: Any = None) -> Any:
        posted.append(payload)
        return {}

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(common, "_request", capture)
        common.dispatch_bundle_workflow(common.new_order_ref())
    sent: dict[str, Any] = posted[0]["inputs"]
    # Nothing about the buyer is an input: a public run log prints each one.
    assert set(sent) == set(declared) == {"order_ref"}, (
        f"report-bundle.yml must take the order reference alone; it declares {sorted(declared)}"
    )

    unknown = sorted(set(sent) - set(declared))
    assert not unknown, f"report-bundle.yml declares no input named {unknown}; GitHub answers 422"

    missing = sorted(
        name
        for name, spec in declared.items()
        if spec.get("required") and not str(sent.get(name) or "")
    )
    assert not missing, f"the dispatch leaves required input(s) {missing} empty"

    undeclared_default = sorted(
        name
        for name, spec in declared.items()
        if name not in sent and not spec.get("required") and "default" not in spec
    )
    assert not undeclared_default, (
        f"the Lambda omits {undeclared_default}, which the workflow declares with no default"
    )
    assert all(isinstance(value, str) for value in sent.values()), (
        "every workflow_dispatch input is a string; GitHub refuses anything else"
    )


@pytest.mark.parametrize("cadence", ["one_time", "monthly"])
def test_both_cadences_survive_the_stored_order(
    cadence: str, bucket: _Bucket, tmp_path: Path
) -> None:
    """The two dispatchers store different cadences -- the setup route the
    plan's, the weekly refresh always ``monthly`` -- and the workflow reads
    them back out of the stored object. Both have to validate there."""
    ref = common.new_order_ref()
    common.store_request(
        ref,
        {
            "bundle_id": "b" * 32,
            "program_name": "Example Program",
            "agency_ids": ["unitrans"],
            "deliver_to": "liaison@example.org",
            "cadence": cadence,
            "max_agencies": 25,
        },
    )
    request, raw = bundle_order.load_order(_collect(bucket, ref, tmp_path))
    assert request.cadence == cadence
    assert bundle_order.order_cap(raw) == 25


def test_the_workflow_collects_the_order_from_where_the_lambda_stores_it() -> None:
    """The two halves of the order hand-off are written in different files and
    deployed separately: the Lambda's ``request_key`` names the object, the
    workflow's collect step spells the same path, and Terraform grants the one
    a write and expires the prefix. A drift between any two is a paid order the
    workflow cannot find, so all four are held to one prefix here."""
    step = next(
        s
        for s in _workflow()["jobs"]["bundle"]["steps"]
        if str(s.get("name") or "") == "Collect the order and mask what it holds"
    )
    run = str(step["run"])
    assert f"s3://${{ARTIFACTS_BUCKET}}/{common.REQUESTS_PREFIX}${{ORDER_REF}}.json" in run
    assert "bundle_order mask request.json" in run
    lambda_tf = (REPO / "infra" / "program-bundle" / "main.tf").read_text(encoding="utf-8")
    assert f"/{common.REQUESTS_PREFIX}*" in lambda_tf, "the Lambda role cannot store an order"
    artifacts_tf = (REPO / "infra" / "artifacts" / "main.tf").read_text(encoding="utf-8")
    assert f'prefix = "{common.REQUESTS_PREFIX}"' in artifacts_tf, (
        "stored orders hold a buyer's address and must expire with the link they built"
    )
    cloudfront = (REPO / "infra" / "artifacts" / "public-artifacts-only.js").read_text(
        encoding="utf-8"
    )
    assert common.REQUESTS_PREFIX.rstrip("/") not in cloudfront, (
        "stored orders must stay outside the public CloudFront allow-list"
    )


# ---------------------------------------------------------------------------
# The transaction: one synthetic purchase, every step, in order
# ---------------------------------------------------------------------------


def test_one_purchase_reaches_a_download_the_reconciler_calls_delivered(
    monkeypatch: pytest.MonkeyPatch,
    tables: dict[str, Any],
    bucket: _Bucket,
    published: str,
    tmp_path: Path,
) -> None:
    """One order, from the setup form to the reconciler's verdict.

    Six things have to agree on one bundle id for this to work, and each of
    them is derived independently in a different file: the capability row, the
    dispatch inputs, the archive's S3 key, the download route's key, the URL
    in the delivery email, and the key the reconciler asks S3 about. Every
    unit test in this repository stubs at least one of those seams. This one
    stubs none of them -- Stripe and GitHub are fixtures, and everything
    between them is the real code.
    """
    dispatched: list[str] = []
    H._stripe(monkeypatch, price=H.PRICE_BUNDLE_100)
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    # 1. The buyer fills in the form Stripe redirected them to.
    response = setup_handler.handler(H._setup_event(H._form(agency_ids=published)))
    body = json.loads(response["body"])
    assert response["statusCode"] == 200, body
    bundle_id = body["bundle_id"]
    assert body["promise"] and body["deliver_by"], "the buyer is told the date they were promised"

    # 2. GitHub took exactly one dispatch, for this order, naming it by a
    #    reference that is not the download capability.
    assert len(dispatched) == 1
    order_ref = dispatched[0]
    assert bundle_id not in order_ref
    assert tables["BUNDLES_TABLE"].items[bundle_id]["order_ref"] == order_ref

    # 3. report-bundle.yml collects the stored order and renders from it alone.
    request_json = _collect(bucket, order_ref, tmp_path / "run")
    request, manifest = _run_the_build(request_json, tmp_path / "bundle.zip")
    assert request.bundle_id == bundle_id
    assert manifest["bundle_id"] == bundle_id
    assert manifest["included"] == 1, manifest
    with zipfile.ZipFile(tmp_path / "bundle.zip") as archive:
        assert f"reports/{published}-board-report.html" in archive.namelist()

    # 4. The archive goes to the key the workflow's `archive-key` command names.
    key = archive_key(bundle_id)
    assert key == f"program-bundles/{bundle_id}/bundle.zip"
    bucket.put(key, (tmp_path / "bundle.zip").read_bytes())
    manifest_json = tmp_path / "run" / "manifest.json"
    manifest_json.write_text(json.dumps(manifest))

    # 5. The email carries the URL the download route answers on, and the
    #    promised date the setup route computed -- built by the workflow's own
    #    `email` command from the stored order and the environment.
    sent: list[tuple[str, str, str, str]] = []
    bundle_order.send_delivery_email(
        request_json,
        manifest_json,
        api_base=BUNDLE_API_BASE,
        source="reports@example.org",
        send=lambda *mail: sent.append(mail),
        now=FROZEN,
    )
    [(source, to, _subject, email_body)] = sent
    download_url = f"{BUNDLE_API_BASE}/download/{bundle_id}"
    promised_by = json.loads(request_json.read_text())["promised_by"]
    assert download_url in email_body
    assert promised_by and promised_by in email_body
    assert to == request.deliver_to and source == "reports@example.org"

    # 6. Clicking that URL presigns the object that was just uploaded.
    redirect = setup_handler.handler(
        {
            "rawPath": f"/download/{bundle_id}",
            "requestContext": {"http": {"method": "GET", "path": f"/download/{bundle_id}"}},
        }
    )
    assert redirect["statusCode"] == 302, redirect
    assert bucket.presigned is not None and bucket.presigned["Key"] == key
    assert redirect["headers"]["Location"].startswith(f"https://s3.example/{key}")

    # 7. Two days on, the reconciler is asked about this order twice: once
    #    with the archive where the workflow put it, and once with it gone.
    #    A test that only asserted the first could not tell a reconciler that
    #    checks from one that always answers "delivered".
    later = dt.datetime.now(dt.UTC) + dt.timedelta(hours=48)
    delivered = reconcile_handler.reconcile(
        bundles=tables["BUNDLES_TABLE"], s3=bucket, bucket="example-artifacts", now=later
    )
    assert delivered["findings"] == [], delivered

    bucket.objects.pop(key)
    undelivered = reconcile_handler.reconcile(
        bundles=tables["BUNDLES_TABLE"], s3=bucket, bucket="example-artifacts", now=later
    )
    kinds = {(f["kind"], f["key"]) for f in undelivered["findings"]}
    assert ("undelivered", bundle_id) in kinds, undelivered


# ---------------------------------------------------------------------------
# Step 4: the weekly tick rebuilds a subscription a month later
# ---------------------------------------------------------------------------


def test_the_weekly_tick_rebuilds_the_subscription_it_stored_a_month_earlier(
    monkeypatch: pytest.MonkeyPatch,
    tables: dict[str, Any],
    bucket: _Bucket,
    published: str,
    tmp_path: Path,
) -> None:
    """A subscription's request is written by one Lambda, as JSON, and read
    back by another four weeks later.

    In between it is a string in DynamoDB. Whether what comes out still parses
    -- ``agency_ids`` is a list on the way in and a comma-joined string on the
    way to the workflow -- and still renders had never been run in one piece,
    and the first run would have been a paying subscriber's second month.
    """
    H._stripe(monkeypatch, H._paid_session(subscription="sub_example"), price=H.PRICE_REFRESH_MO)
    H._bought_earlier(tables, "bundle_100")
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", lambda inputs: None)

    first = setup_handler.handler(H._setup_event(H._form(agency_ids=published)))
    assert first["statusCode"] == 200, first["body"]
    stored = tables["SUBSCRIPTIONS_TABLE"].items["sub_example"]
    assert stored["status"] == "active" and stored["agency_cap"] == 100

    # Twenty-eight days on, with nothing else changed.
    stored["last_refresh"] = "2026-01-01T00:00:00+00:00"
    refreshed: list[str] = []
    monkeypatch.setattr(refresh_handler, "dispatch_bundle_workflow", refreshed.append)

    counts = refresh_handler.handler({"detail-type": "Scheduled Event", "detail": {}})
    assert counts["dispatched"] == 1, counts
    assert len(refreshed) == 1
    request_json = _collect(bucket, refreshed[0], tmp_path / "run")
    order = json.loads(request_json.read_text())

    # A new capability, not the one bought in month one: the archive it
    # renews expires after thirty days, so a refresh that reused the id would
    # deliver a link that had already gone dead.
    assert order["bundle_id"] != json.loads(first["body"])["bundle_id"]
    assert order["cadence"] == "monthly"
    # A refresh makes no two-business-day promise, so it carries no date.
    assert not order.get("promised_by")
    # And it is held to the cap the subscription was sold under.
    assert bundle_order.order_cap(order) == 100

    request, manifest = _run_the_build(request_json, tmp_path / "refresh.zip")
    assert manifest["included"] == 1, manifest
    assert request.agency_ids == (published,)
    assert (
        tables["SUBSCRIPTIONS_TABLE"].items["sub_example"]["last_bundle_id"] == order["bundle_id"]
    )


# ---------------------------------------------------------------------------
# Step 5: the webhook's record is what a later refresh inherits its cap from
# ---------------------------------------------------------------------------


def test_a_signed_checkout_event_is_the_purchase_a_later_refresh_renews(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, Any], bucket: _Bucket
) -> None:
    """The webhook writes the only record of a buyer who paid and never came
    back to the setup form, and the entitlement check reads it months later.

    Both halves are tested apart. Together they had never run, and the row in
    between is written by a signature check and a Stripe line-items read that
    the unit tests for the setup route hand-write around. Here the row is
    produced by ``webhook_handler.handler`` from a genuinely signed body, and
    then consumed as-is.
    """
    session_id = "cs_test_boughtinjanuary"
    event = {
        "id": "evt_example",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "mode": "payment",
                "customer_details": {"email": "Buyer@Example.org"},
            }
        },
    }
    raw = json.dumps(event).encode()
    H._stripe(monkeypatch, price=H.PRICE_BUNDLE_100)

    noted = webhook_handler.handler(
        {
            "requestContext": {"http": {"method": "POST"}},
            "headers": {"Stripe-Signature": H._sign(raw)},
            "body": raw.decode(),
        }
    )
    assert noted["statusCode"] == 200 and json.loads(noted["body"])["outcome"] == "noted"
    row = tables["BUNDLES_TABLE"].items[f"{common.CHECKOUT_PREFIX}{session_id}"]
    assert row["plan"] == "bundle_100"
    # The address is kept exactly as Stripe recorded it; the case-folding that
    # matches it to a later checkout happens at the point of comparison.
    assert row["email"] == "Buyer@Example.org"

    # Months later, the same person subscribes to the monthly refresh. The
    # cap they inherit is the one the webhook's row records -- nothing else
    # in the system remembers that purchase.
    H._stripe(
        monkeypatch,
        H._paid_session(subscription="sub_later", customer_details={"email": "buyer@example.org"}),
        price=H.PRICE_REFRESH_MO,
    )
    dispatched: list[str] = []
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", dispatched.append)

    resp = setup_handler.handler(
        H._setup_event(H._form(agency_ids=",".join(f"a{n}" for n in range(60))))
    )
    assert resp["statusCode"] == 200, resp["body"]
    assert len(dispatched) == 1
    assert tables["SUBSCRIPTIONS_TABLE"].items["sub_later"]["agency_cap"] == 100
    assert tables["SUBSCRIPTIONS_TABLE"].items["sub_later"]["renews_session"] == session_id


def test_a_refresh_with_only_a_webhook_row_of_the_smaller_bundle_inherits_its_cap(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, Any], bucket: _Bucket
) -> None:
    """The negative half of the test above: the cap that travels is the one
    the webhook recorded, not the widest one on the price list.

    Without this, a test that asserted 100 would pass against a handler that
    ignored the row entirely and returned the refresh price's own ceiling.
    """
    session_id = "cs_test_smallbundle"
    event = {
        "id": "evt_example",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "mode": "payment",
                "customer_details": {"email": "buyer@example.org"},
            }
        },
    }
    raw = json.dumps(event).encode()
    H._stripe(monkeypatch, price=H.PRICE_BUNDLE_25)
    webhook_handler.handler(
        {
            "requestContext": {"http": {"method": "POST"}},
            "headers": {"Stripe-Signature": H._sign(raw)},
            "body": raw.decode(),
        }
    )
    assert tables["BUNDLES_TABLE"].items[f"checkout#{session_id}"]["plan"] == "bundle_25"

    H._stripe(
        monkeypatch,
        H._paid_session(subscription="sub_small"),
        price=H.PRICE_REFRESH_MO,
    )
    monkeypatch.setattr(setup_handler, "dispatch_bundle_workflow", lambda inputs: None)
    over = setup_handler.handler(
        H._setup_event(H._form(agency_ids=",".join(f"a{n}" for n in range(26))))
    )
    assert over["statusCode"] == 400
    assert "at most 25 agencies" in json.loads(over["body"])["error"]
    assert "session#" not in "".join(tables["BUNDLES_TABLE"].items), (
        "a list over the inherited cap must not consume the checkout"
    )
