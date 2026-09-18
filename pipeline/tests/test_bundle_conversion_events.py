"""The bundle pages' conversion steps, held from the page-script side (ADR 0057).

``web/src/bundle.js`` announces the plans shown (``view_item``) and each
checkout link followed (``begin_checkout``); ``web/src/bundle-setup.js``
announces the purchase Stripe returns a buyer with. Both dispatch a
``scorecard:commerce`` event on the document and never call ``gtag``. The GA4
block of ``web/src/measure.js`` checks and forwards them, which
``test_measure_ga4.py`` holds. These tests run the two page scripts in Node
against a stub page and hold what they announce:

- plan ids and prices straight from ``plan.json``, and nothing else;
- the purchase named by a hash of Stripe's order reference, never the
  reference itself;
- nothing at all when the plan says payments are off, or the address carries
  no well-formed order reference;
- the button at the top of ``/bundle/`` selling the entry bundle at the price
  ``plan.json`` gives, and staying a link to the plan list otherwise.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
_WEB = _REPO / "web"
_BUNDLE_JS = _WEB / "src" / "bundle.js"
_SETUP_JS = _WEB / "src" / "bundle-setup.js"
_PLAN = json.loads((_WEB / "bundle" / "plan.json").read_text())
_PAGE = (_WEB / "bundle" / "index.html").read_text()

_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const c = JSON.parse(process.argv[2]);

function element(id) {
  const el = {
    id: id || "",
    attrs: {},
    children: [],
    listeners: {},
    textContent: "",
    className: "",
    href: "",
    hidden: false,
  };
  el.setAttribute = function (n, v) { this.attrs[n] = String(v); };
  el.getAttribute = function (n) { return n in this.attrs ? this.attrs[n] : null; };
  el.hasAttribute = function (n) { return n in this.attrs; };
  el.addEventListener = function (t, fn) {
    (this.listeners[t] = this.listeners[t] || []).push(fn);
  };
  el.append = function () { for (const x of arguments) this.children.push(x); };
  el.appendChild = function (x) { this.children.push(x); return x; };
  el.replaceChildren = function () { this.children = []; };
  el.remove = function () {};
  return el;
}

const byId = {};
for (const id of c.ids || []) {
  byId[id] = element(id);
  if (c.initial && c.initial[id]) Object.assign(byId[id], c.initial[id]);
}
const created = [];
const dispatched = [];
const document = {
  head: element("head"),
  getElementById: function (id) { return byId[id] || null; },
  createElement: function (tag) {
    const el = element("");
    el.tagName = tag;
    created.push(el);
    return el;
  },
  dispatchEvent: function (event) {
    dispatched.push({ type: event.type, detail: JSON.parse(JSON.stringify(event.detail)) });
    return true;
  },
};
class CustomEvent {
  constructor(type, init) { this.type = type; this.detail = init && init.detail; }
}
const location = {
  href: "https://gtfsscorecard.org" + c.path + c.search,
  search: c.search,
};
const window = { SCORECARD_BUNDLE_URL: undefined };
if (c.crypto) window.crypto = require("crypto").webcrypto;
const context = vm.createContext({
  window: window,
  document: document,
  location: location,
  CustomEvent: CustomEvent,
  URL: URL,
  URLSearchParams: URLSearchParams,
  TextEncoder: TextEncoder,
  Intl: Intl,
  HTMLInputElement: function () {},
  HTMLTextAreaElement: function () {},
  HTMLButtonElement: function () {},
  FormData: function () {},
  fetch: function () {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve(c.plan); } });
  },
});
vm.runInContext(source, context);

setTimeout(function () {
  const links = [];
  function walk(el) {
    if (el.tagName === "a") links.push(el);
    (el.children || []).forEach(walk);
  }
  walk(byId["plan-grid"] || element(""));
  const clicks = [];
  for (const target of c.click || []) {
    const el = target === "buy-box-cta"
      ? byId["buy-box-cta"]
      : links.find(function (a) { return a.getAttribute("data-measure-plan") === target; });
    const before = dispatched.length;
    (el.listeners.click || []).forEach(function (fn) { fn({ target: el }); });
    clicks.push(dispatched.slice(before));
  }
  const lead = byId["buy-box-cta"];
  process.stdout.write(JSON.stringify({
    dispatched: dispatched,
    clicks: clicks,
    lead: lead ? {
      href: lead.href,
      text: lead.textContent,
      measure: lead.getAttribute("data-measure"),
      plan: lead.getAttribute("data-measure-plan"),
      price: byId["buy-box-price"].textContent,
    } : null,
    cardPlans: links.map(function (a) { return a.getAttribute("data-measure-plan"); }),
  }));
}, 100);
"""

_BUNDLE_IDS = ["plan-grid", "plan-notice", "plan-fineprint", "buy-box-price", "buy-box-cta"]
_STATIC_LEAD = {
    "buy-box-cta": {"href": "#plans-h", "textContent": "See plans and prices"},
    "buy-box-price": {"textContent": "Every plan and its price is listed below."},
}
_REFERENCE = "cs_live_a1B2c3D4e5F6g7H8"


def _run(script: Path, case: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [node, "-e", _HARNESS, str(script), json.dumps(case)],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def _bundle(tmp_path: Path, plan: dict[str, Any], click: list[str] | None = None) -> dict[str, Any]:
    case = {
        "path": "/bundle/",
        "search": "",
        "ids": _BUNDLE_IDS,
        "initial": _STATIC_LEAD,
        "plan": plan,
        "click": click or [],
    }
    return _run(_BUNDLE_JS, case, tmp_path)


def _setup(tmp_path: Path, search: str, *, crypto: bool = True) -> dict[str, Any]:
    case = {"path": "/bundle/setup/", "search": search, "ids": [], "crypto": crypto}
    return _run(_SETUP_JS, case, tmp_path)


def _items(keys: list[str]) -> list[dict[str, Any]]:
    return [{"item_id": key, "price": _PLAN["products"][key]["price"]} for key in keys]


_ORDER = ["bundle_25", "bundle_100", "refresh_mo", "refresh_yr"]


# --- /bundle/ ----------------------------------------------------------------


def test_the_plans_on_sale_are_announced_once_as_view_item(tmp_path: Path) -> None:
    assert _PLAN["paymentsAvailable"] is True, "the live plan sells nothing; this proves nothing"
    result = _bundle(tmp_path, _PLAN)
    assert result["dispatched"] == [
        {
            "type": "scorecard:commerce",
            "detail": {
                "event": "view_item",
                "currency": _PLAN["currency"],
                "amount": _PLAN["products"]["bundle_25"]["price"],
                "items": _items(_ORDER),
            },
        }
    ]


def test_every_checkout_link_announces_begin_checkout_for_its_own_plan(tmp_path: Path) -> None:
    result = _bundle(tmp_path, _PLAN, click=["buy-box-cta", *_ORDER])
    assert result["cardPlans"] == _ORDER
    for key, events in zip(["bundle_25", *_ORDER], result["clicks"], strict=True):
        [item] = _items([key])
        assert events == [
            {
                "type": "scorecard:commerce",
                "detail": {
                    "event": "begin_checkout",
                    "currency": _PLAN["currency"],
                    "amount": item["price"],
                    "items": [item],
                },
            }
        ], key


def test_the_top_of_the_page_sells_the_entry_bundle_at_the_plan_price(tmp_path: Path) -> None:
    lead = _bundle(tmp_path, _PLAN)["lead"]
    product = _PLAN["products"]["bundle_25"]
    price = f"${product['price']}"
    assert lead["href"] == product["checkout_url"]
    assert lead["text"] == f"Buy for {price} through Stripe"
    assert lead["price"] == f"{product['label']}: {price}, paid once."
    # PostHog still hears this checkout under the same event as the cards.
    assert (lead["measure"], lead["plan"]) == ("bundle_checkout_click", "bundle_25")


@pytest.mark.parametrize(
    "plan",
    [
        {**_PLAN, "paymentsAvailable": False},
        {"paymentsAvailable": True, "currency": "USD", "products": {}},
        {
            **_PLAN,
            "products": {
                **_PLAN["products"],
                "bundle_25": {**_PLAN["products"]["bundle_25"], "checkout_url": "http://x"},
            },
        },
    ],
    ids=["payments-off", "no-products", "insecure-link"],
)
def test_with_nothing_to_sell_at_the_top_it_stays_a_link_to_the_plans(
    tmp_path: Path, plan: dict[str, Any]
) -> None:
    result = _bundle(tmp_path, plan)
    assert result["lead"] == {
        "href": "#plans-h",
        "text": "See plans and prices",
        "measure": None,
        "plan": None,
        "price": "Every plan and its price is listed below.",
    }
    if plan["paymentsAvailable"] is not True or not plan["products"]:
        assert result["dispatched"] == []


def test_the_static_top_of_the_page_matches_what_the_script_leaves_alone() -> None:
    """The fallback the harness starts from is the markup the page ships."""
    assert 'id="buy-box-cta" class="submit-button" href="#plans-h">See plans and prices</a>' in (
        _PAGE
    )
    assert 'id="buy-box-price" class="plan-price">Every plan and its price is listed below.' in (
        _PAGE
    )
    # Above the plan list, the sample, and the long description: first on the page.
    main = _PAGE[_PAGE.index('<main id="main"') :]
    assert main.index('id="buy-box-cta"') < main.index('href="/bundle/sample/"')
    assert main.index('id="buy-box-cta"') < main.index('id="plans-h"')
    assert main.index('id="buy-box-cta"') < main.index('class="buy-terms"')


# --- /bundle/setup/ -----------------------------------------------------------


def test_the_purchase_is_named_by_a_hash_of_the_order_reference(tmp_path: Path) -> None:
    result = _setup(tmp_path, f"?session_id={_REFERENCE}")
    order = hashlib.sha256(_REFERENCE.encode()).hexdigest()[:32]
    assert result["dispatched"] == [
        {"type": "scorecard:commerce", "detail": {"event": "purchase", "transaction_id": order}}
    ]
    sent = json.dumps(result["dispatched"])
    assert _REFERENCE not in sent and "cs_" not in sent


@pytest.mark.parametrize(
    "search",
    ["", "?session_id=", "?session_id=pi_123", "?session_id=cs_live_<script>", "?other=cs_live_x"],
)
def test_no_well_formed_order_reference_means_no_purchase(tmp_path: Path, search: str) -> None:
    assert _setup(tmp_path, search)["dispatched"] == []


def test_without_web_crypto_nothing_is_announced(tmp_path: Path) -> None:
    assert _setup(tmp_path, f"?session_id={_REFERENCE}", crypto=False)["dispatched"] == []


def test_neither_page_script_calls_google_directly() -> None:
    for script in (_BUNDLE_JS, _SETUP_JS):
        text = script.read_text()
        for name in ("gtag", "dataLayer", "googletagmanager", "google-analytics"):
            assert name not in text, (script.name, name)
