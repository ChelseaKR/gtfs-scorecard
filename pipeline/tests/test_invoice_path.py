"""The buy-by-invoice path: the /invoice/ page, its script, and the blank quote.

A public agency that cannot pay through a card link asks for a quote, sends a
purchase order, and receives an invoice. Three things hold that path to the
rules the rest of the paid tier already lives under:

1. **Prices have one owner.** The page and the quote read every amount from
   ``web/bundle/plan.json``. A literal amount in the page, the script, or the
   generator would keep quoting after the plan changes.
2. **Nothing the reader types leaves the browser by this page.** The form
   composes a ``mailto:`` link. The script makes one request, for the plan
   file, and no other.
3. **The quote invents no fact about the seller.** Identity, tax, payment, and
   terms fields are visible markers until a person fills them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import invoice_docs
from scorecard_pipeline.invoice_docs import (
    QUOTE_PRODUCTS,
    load_bundle_plan,
    quote_line_items,
    render_printable_html,
    render_quote_markdown,
    sync_invoice_docs,
    unfilled_markers,
)
from scorecard_pipeline.site_shell import MEASURED_STATIC_PAGES, STATIC_NAV_PAGES

# The real repo, not the per-test tmp SCORECARD_ROOT.
_REPO = Path(__file__).resolve().parents[2]
_PAGE = _REPO / "web" / "invoice" / "index.html"
_SCRIPT = _REPO / "web" / "src" / "invoice.js"
_QUOTE_MD = _REPO / "docs" / "invoice" / "quote-template.md"
_QUOTE_HTML = _REPO / "docs" / "invoice" / "quote-template.html"


def _plan() -> dict[str, Any]:
    return load_bundle_plan(_REPO)


# --- the quote follows the plan ------------------------------------------


def test_the_committed_quote_matches_the_generator() -> None:
    markdown = render_quote_markdown(_plan())
    assert _QUOTE_MD.read_text() == markdown, "run `make sync-invoice-docs`"
    assert _QUOTE_HTML.read_text() == render_printable_html(
        markdown, "Quote: GTFS Scorecard program report bundle"
    ), "run `make sync-invoice-docs`"


def test_every_quote_line_is_a_plan_product_at_the_plan_price() -> None:
    plan = _plan()
    rows = quote_line_items(plan)
    assert [row["key"] for row in rows] == list(QUOTE_PRODUCTS)
    for row in rows:
        product = plan["products"][row["key"]]
        assert row["label"] == product["label"]
        assert row["unit_price"] == f"${product['price']}"
        assert row["billing"] == (f"per {product['interval']}" if product["interval"] else "once")
        assert row["unit_price"] in render_quote_markdown(plan)


def test_a_missing_or_unpriced_product_is_an_error_not_a_blank_row() -> None:
    plan = _plan()
    broken = {**plan, "products": {k: v for k, v in plan["products"].items() if k != "bundle_25"}}
    with pytest.raises(ValueError, match="bundle_25"):
        quote_line_items(broken)
    unpriced = json.loads(json.dumps(plan))
    unpriced["products"]["bundle_100"]["price"] = None
    with pytest.raises(ValueError, match="bundle_100"):
        quote_line_items(unpriced)
    with pytest.raises(ValueError, match="no products"):
        quote_line_items({"currency": "USD"})


def test_money_handles_cents_and_other_currencies() -> None:
    assert invoice_docs._money(1490.5, "USD") == "$1,490.50"
    assert invoice_docs._money(2500, "USD") == "$2,500"
    assert invoice_docs._money(100, "CAD") == "100 CAD"


def test_the_plan_reader_refuses_a_file_that_is_not_an_object(tmp_path: Path) -> None:
    (tmp_path / "web" / "bundle").mkdir(parents=True)
    (tmp_path / "web" / "bundle" / "plan.json").write_text("[]")
    with pytest.raises(ValueError, match="JSON object"):
        load_bundle_plan(tmp_path)


def test_sync_writes_once_and_then_reports_nothing_to_change(tmp_path: Path) -> None:
    (tmp_path / "web" / "bundle").mkdir(parents=True)
    (tmp_path / "web" / "bundle" / "plan.json").write_text(json.dumps(_plan()))
    first = sync_invoice_docs(tmp_path)
    assert sorted(p.name for p in first) == ["quote-template.html", "quote-template.md"]
    assert sync_invoice_docs(tmp_path) == []
    assert (tmp_path / "docs" / "invoice" / "quote-template.md").read_text() == (
        render_quote_markdown(_plan())
    )


def test_the_printable_copy_is_self_contained_and_escapes_its_title() -> None:
    page = render_printable_html("# Heading\n", "A <b>title</b>")
    assert "<title>A &lt;b&gt;title&lt;/b&gt;</title>" in page
    assert "<h1>Heading</h1>" in page
    assert "<script" not in page and "<link" not in page


# --- the quote invents nothing -------------------------------------------


def test_the_blank_quote_carries_markers_and_no_seller_facts() -> None:
    markdown = _QUOTE_MD.read_text()
    markers = unfilled_markers(markdown)
    assert markers, "a blank quote with no fill markers has had facts typed into it"
    owner_fields = {m for m in markers if m.startswith("[OWNER FILL")}
    for needed in (
        "seller legal name",
        "payment instructions",
        "payment terms",
        "list of forms",
        "refund terms",
    ):
        assert f"[OWNER FILL: {needed}]" in owner_fields
    # No tax identifier, account number, or bank detail is spelled out.
    assert not re.search(r"\b\d{2}-\d{7}\b", markdown), "looks like a tax identifier"
    assert not re.search(r"\b\d{8,17}\b", markdown), "looks like an account number"
    assert "IBAN" not in markdown and "routing" not in markdown.lower()


def test_unfilled_markers_finds_only_well_formed_markers() -> None:
    text = "a [OWNER FILL: x] b [BUYER FILL: y z] c [OTHER FILL: no] d [OWNER FILL:]"
    assert unfilled_markers(text) == ["[OWNER FILL: x]", "[BUYER FILL: y z]"]


# --- the page and its script ----------------------------------------------


def _amounts() -> list[str]:
    products = _plan()["products"]
    found = []
    for product in products.values():
        price = product["price"]
        found += [f"${price}", f"${price:,}"]
    return found


def test_the_page_and_script_carry_no_price_and_the_generator_formats_from_the_plan() -> None:
    assert _amounts()
    for path in (_PAGE, _SCRIPT, Path(invoice_docs.__file__)):
        text = path.read_text()
        for amount in _amounts():
            assert amount not in text, f"{path.name}: literal price {amount}"


def test_the_page_is_a_registered_hand_authored_page() -> None:
    assert "invoice/index.html" in STATIC_NAV_PAGES
    assert "invoice/index.html" in MEASURED_STATIC_PAGES
    render_site = (_REPO / "pipeline" / "src" / "scorecard_pipeline" / "render_site.py").read_text()
    assert 'f"{BASE_URL}/invoice/"' in render_site, "the page is not in the sitemap list"
    assert "/invoice/" in (_REPO / ".pa11yci.json").read_text(), "the axe gate never opens it"
    assert "invoice/index.html" in (_REPO / "site-budgets.json").read_text()


def test_the_page_is_reachable_from_the_bundle_page_and_the_support_page() -> None:
    for rel in ("bundle/index.html", "support/index.html"):
        head = (_REPO / "web" / rel).read_text().partition('<footer class="site-footer">')[0]
        assert 'href="/invoice/"' in head, rel


def test_every_price_slot_and_choice_names_a_quotable_product() -> None:
    page = _PAGE.read_text()
    slots = set(re.findall(r'data-price-for="([a-z0-9_]+)"', page))
    choices = set(re.findall(r'name="buy" type="checkbox" value="([a-z0-9_]+)"', page))
    assert slots == set(QUOTE_PRODUCTS)
    assert choices == set(QUOTE_PRODUCTS) | {"other"}
    for key in slots:
        assert key in _plan()["products"]


def test_the_form_goes_nowhere_but_the_readers_mail_program() -> None:
    page = _PAGE.read_text()
    form = re.search(r"<form\b[^>]*>", page)
    assert form is not None
    assert "action=" not in form.group(0) and "method=" not in form.group(0)
    assert "ph-no-capture" in form.group(0)
    script = _SCRIPT.read_text()
    assert script.count("fetch(") == 1 and 'fetch("/bundle/plan.json"' in script
    for forbidden in ("sendBeacon", "XMLHttpRequest", "WebSocket", "localStorage", "cookie"):
        assert forbidden not in script, forbidden
    # The one mail address on the page is the one /support/ already publishes.
    addresses = set(re.findall(r"mailto:([^?\"]+)", page))
    support = (_REPO / "web" / "support" / "index.html").read_text()
    assert len(addresses) == 1 and f"mailto:{next(iter(addresses))}" in support


def test_the_page_asks_for_no_card_bank_or_tax_details() -> None:
    page = _PAGE.read_text().lower()
    assert "do not put card numbers, bank details, or tax identifiers" in page
    for field in ('name="card', 'name="account', 'name="tax', 'name="ssn', 'name="ein'):
        assert field not in page


def test_the_page_and_quote_follow_the_writing_rules() -> None:
    for path in (_PAGE, _QUOTE_MD, _QUOTE_HTML):
        assert path.read_text().count("—") <= 1, f"{path.name}: more than one em dash"
    page = _PAGE.read_text()
    assert "<h1 " in page and page.count("<h1 ") == 1
    assert 'lang="en"' in page
