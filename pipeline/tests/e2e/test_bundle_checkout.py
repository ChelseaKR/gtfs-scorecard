"""The buy controls on /bundle/, which exist only after JavaScript has run.

``web/bundle/index.html`` ships an empty ``#plan-grid``; ``web/src/bundle.js`` fetches
``/bundle/plan.json`` and builds the price lines and the "Buy through Stripe" links from it.
So every static check of that page — the byte budget, the structural SEO contract, a grep over
the markup — is looking at a document with no prices and no links in it, and the schema gate in
``tests/test_bundle_plan_contract.py`` proves the data is well formed without proving the page
ever reaches it. These tests close that gap from the other end: they assert against the rendered
DOM, in all three states the renderer has.

The expectations are read from the committed ``plan.json``, the same file the page reads, rather
than frozen as literals. A price change then moves the test and the page together, and the
assertion stays the one that is actually meant: the number on the page is the number in the data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.e2e

# This file is pipeline/tests/e2e/test_bundle_checkout.py, so parents[3] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN_PATH = REPO_ROOT / "web" / "bundle" / "plan.json"
PLAN_ROUTE = "**/bundle/plan.json"
BUY_LABEL = "Buy through Stripe"


def _plan() -> dict[str, Any]:
    """The plan document the deployed page serves, as the tests' source of truth."""
    plan: dict[str, Any] = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    return plan


# What Intl.NumberFormat("en-US", {style: "currency", ...}) prefixes each amount with.
# A currency with no entry here fails loudly rather than comparing against the wrong glyph.
CURRENCY_SYMBOLS = {"USD": "$"}


def _expected_price_text(product: dict[str, Any], currency: str) -> str:
    """What bundle.js renders for one product: the formatted amount plus any cadence."""
    symbol = CURRENCY_SYMBOLS.get(currency)
    assert symbol is not None, f"no expected rendering is recorded for {currency}"
    amount = f"{symbol}{product['price']:,.0f}"
    return f"{amount} per {product['interval']}" if product["interval"] else amount


def _serve_plan(page: Page, plan: dict[str, Any]) -> None:
    def _fulfill(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(plan),
        )

    page.route(PLAN_ROUTE, _fulfill)


def test_four_buy_controls_render_with_live_stripe_payment_links(page: Page, base_url: str) -> None:
    """paymentsAvailable is true today, so the page must actually offer four checkouts."""
    plan = _plan()
    assert plan["paymentsAvailable"] is True, (
        "the committed plan has payments off; this test asserts the selling state and "
        "test_no_plan_is_offered_when_payments_are_unavailable asserts the other one"
    )

    page.goto(f"{base_url}/bundle/")

    buys = page.get_by_role("link", name=BUY_LABEL)
    expect(buys).to_have_count(4)

    hrefs = [buys.nth(index).get_attribute("href") for index in range(4)]
    for href in hrefs:
        assert href is not None and href.startswith("https://buy.stripe.com/"), (
            f"a buy control points at {href!r}"
        )
    assert set(hrefs) == {product["checkout_url"] for product in plan["products"].values()}

    # Each card prints its own plan's price, next to its own plan's link.
    for key, product in plan["products"].items():
        card = page.locator(f'section[aria-labelledby="plan-{key}-h"]')
        expect(card).to_have_count(1)
        expect(card.locator(".plan-price")).to_have_text(
            _expected_price_text(product, plan["currency"])
        )
        expect(card.get_by_role("link", name=BUY_LABEL)).to_have_attribute(
            "href", product["checkout_url"]
        )

    expect(page.locator("#plan-notice")).to_contain_text("Checkout is open")
    expect(page.locator("#plan-fineprint")).to_be_visible()


def test_no_plan_is_offered_when_payments_are_unavailable(page: Page, base_url: str) -> None:
    """The tier shipped in this state, and it has to stay reachable from the same markup.

    Prices and links are left in the served document deliberately: the switch that must
    govern the page is ``paymentsAvailable``, not the absence of a Payment Link.
    """
    plan = _plan()
    plan["paymentsAvailable"] = False
    _serve_plan(page, plan)

    page.goto(f"{base_url}/bundle/")

    cards = page.locator("#plan-grid .support-path")
    expect(cards).to_have_count(4)
    expect(page.locator("#plan-grid .plan-price")).to_have_count(4)
    for index in range(4):
        expect(page.locator("#plan-grid .plan-price").nth(index)).to_have_text("Not yet available")

    expect(page.get_by_role("link", name=BUY_LABEL)).to_have_count(0)
    assert page.locator('#plan-grid a[href*="buy.stripe.com"]').count() == 0
    expect(page.locator("#plan-notice")).to_contain_text("not yet available")
    expect(page.locator("#plan-fineprint")).to_be_hidden()


def test_a_plan_that_cannot_be_read_sells_nothing_and_says_so(page: Page, base_url: str) -> None:
    """Fail closed: an unreadable plan is an absence, never a default offer."""

    def _unavailable(route: Route) -> None:
        route.fulfill(status=503, body="unavailable")

    page.route(PLAN_ROUTE, _unavailable)
    page.goto(f"{base_url}/bundle/")

    notice = page.locator("#plan-notice")
    expect(notice).to_contain_text("Nothing is for sale until it can be read")
    expect(notice).to_have_class("form-status form-status-err")
    expect(page.get_by_role("link", name=BUY_LABEL)).to_have_count(0)
    expect(page.locator("#plan-grid .support-path")).to_have_count(0)
    expect(page.locator("#plan-fineprint")).to_be_hidden()
