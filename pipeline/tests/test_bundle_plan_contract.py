"""The one document on this site that carries a price, and the files that must agree with it.

``web/bundle/plan.json`` is the whole payment surface of ``/bundle/``. ``web/src/bundle.js``
fetches it at runtime and builds the price lines and the "Buy through Stripe" controls from
it, so the served HTML contains no price, no link, and therefore no evidence of a malformed
plan: a wrong price, a ``null`` ``checkout_url``, a typo'd Payment Link or a
``paymentsAvailable: true`` over products nothing backs would all render as a confident page
and ship green. That is this portfolio's "absence rendered as a value" defect pointed at
revenue, which is why the contract lives in ``web/schemas/`` beside the published data
contracts and is enforced here.

**Why three hand-maintained copies of each price, instead of one derived number.**
``docs/program-plan.md`` states the price table, ``scripts/stripe-setup.sh`` holds the cents
constants that create the Stripe Price objects, and ``web/bundle/plan.json`` holds the dollars
the page prints. None of the three is downstream of another. The authoritative price is the
one stored in the Stripe account, which no offline gate can read, so each file is an
independent human transcription of the same decision — and the doc's table is an argument
("these are knobs, not research"), not a build input. Deriving any one of them from another
would delete exactly the transcription error this is here to catch, and would empty the
document's sentence of its content, which is the rule ``docs/lint-complexity-ratchet.md``
already sets for hand-maintained numbers that carry a human justification. So all three stay
hand-written and their *agreement* is the gate. Change a price in all three, or the suite says
which one you missed.

Each parser below asserts it found exactly the four expected keys before anything is compared.
A comparison over an empty mapping succeeds, so a reworded table or a renamed shell constant
would otherwise turn this file from a gate into a green no-op.

The schema deliberately uses no ``format`` keyword: ``format`` is an annotation unless the
validator was built with a ``format_checker``, and a contract that looks enforced and is not is
worse than none. Everything it constrains, it constrains with ``pattern``, ``const``, ``enum``
and ``type``. ``test_the_contract_never_relies_on_an_unchecked_format`` keeps it that way.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

# This file is pipeline/tests/test_bundle_plan_contract.py, so parents[2] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO_ROOT / "web" / "bundle" / "plan.json"
SCHEMA_PATH = REPO_ROOT / "web" / "schemas" / "program-bundle-plan.schema.json"
DOC_PATH = REPO_ROOT / "docs" / "program-plan.md"
SETUP_SCRIPT_PATH = REPO_ROOT / "scripts" / "stripe-setup.sh"
PAGE_PATH = REPO_ROOT / "web" / "bundle" / "index.html"

# The four knobs, written out rather than read from any of the files under test: a key set
# derived from one of them could never disagree with itself.
PRODUCT_KEYS = ("bundle_25", "bundle_100", "refresh_mo", "refresh_yr")

Plan = dict[str, Any]
# key -> (price in whole currency units, billing interval or None for a one-off)
PriceTable = dict[str, tuple[Decimal, str | None]]


def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _live_plan() -> Plan:
    plan: Plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    return plan


def _errors(document: Plan) -> list[str]:
    return [error.message for error in _validator().iter_errors(document)]


# ---------------------------------------------------------------------------
# The contract itself
# ---------------------------------------------------------------------------


def test_the_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def test_the_live_plan_conforms_to_its_schema() -> None:
    """The committed file is what gtfsscorecard.org/bundle/plan.json serves right now."""
    assert _errors(_live_plan()) == []


def test_the_contract_never_relies_on_an_unchecked_format() -> None:
    """``format`` without a ``format_checker`` is documentation, not enforcement."""

    def _formats(node: Any) -> list[str]:
        if isinstance(node, dict):
            found = [str(node["format"])] if "format" in node else []
            for value in node.values():
                found.extend(_formats(value))
            return found
        if isinstance(node, list):
            return [name for item in node for name in _formats(item)]
        return []

    assert _formats(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))) == []


def _null_checkout_url(plan: Plan) -> None:
    plan["products"]["bundle_25"]["checkout_url"] = None


def _null_price(plan: Plan) -> None:
    plan["products"]["refresh_mo"]["price"] = None


def _missing_checkout_url(plan: Plan) -> None:
    del plan["products"]["bundle_100"]["checkout_url"]


def _plain_http_link(plan: Plan) -> None:
    plan["products"]["bundle_25"]["checkout_url"] = "http://buy.stripe.com/28E14m6Yz3Zd9mxeVpgQE00"


def _lookalike_host(plan: Plan) -> None:
    plan["products"]["bundle_25"]["checkout_url"] = (
        "https://buy.stripe.com.checkout.example/28E14m6Yz3Zd9mxeVpgQE00"
    )


def _stripe_dashboard_link(plan: Plan) -> None:
    plan["products"]["refresh_yr"]["checkout_url"] = "https://dashboard.stripe.com/payments"


def _test_mode_link(plan: Plan) -> None:
    plan["products"]["bundle_25"]["checkout_url"] = (
        "https://buy.stripe.com/test_28E14m6Yz3Zd9mxeVpgQE00"
    )


def _missing_product(plan: Plan) -> None:
    del plan["products"]["refresh_yr"]


def _unbacked_product(plan: Plan) -> None:
    plan["products"]["refresh_wk"] = copy.deepcopy(plan["products"]["refresh_mo"])


def _empty_products(plan: Plan) -> None:
    plan["products"] = {}


def _interval_on_a_one_off(plan: Plan) -> None:
    plan["products"]["bundle_100"]["interval"] = "month"


def _interval_dropped_from_a_subscription(plan: Plan) -> None:
    plan["products"]["refresh_mo"]["interval"] = None


def _swapped_subscription_intervals(plan: Plan) -> None:
    plan["products"]["refresh_mo"]["interval"] = "year"
    plan["products"]["refresh_yr"]["interval"] = "month"


def _price_as_a_string(plan: Plan) -> None:
    plan["products"]["bundle_25"]["price"] = "149"


def _free_price(plan: Plan) -> None:
    plan["products"]["bundle_25"]["price"] = 0


def _lowercase_currency(plan: Plan) -> None:
    plan["currency"] = "usd"


def _same_day_promise(plan: Plan) -> None:
    plan["provisioning_business_days"] = 0


def _undeclared_top_level_key(plan: Plan) -> None:
    plan["discount_code"] = "LAUNCH"


def _blank_label(plan: Plan) -> None:
    plan["products"]["refresh_yr"]["label"] = ""


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_null_checkout_url, id="null checkout_url while payments are on"),
        pytest.param(_null_price, id="null price while payments are on"),
        pytest.param(_missing_checkout_url, id="checkout_url absent entirely"),
        pytest.param(_plain_http_link, id="plain http Payment Link"),
        pytest.param(_lookalike_host, id="buy.stripe.com as a subdomain of somewhere else"),
        pytest.param(_stripe_dashboard_link, id="a real Stripe URL that is not a Payment Link"),
        pytest.param(_test_mode_link, id="a test-mode Payment Link on the live page"),
        pytest.param(_missing_product, id="one of the four products missing"),
        pytest.param(_unbacked_product, id="a fifth product nothing on Stripe backs"),
        pytest.param(_empty_products, id="payments on with no products at all"),
        pytest.param(_interval_on_a_one_off, id="a one-off bundle advertised as recurring"),
        pytest.param(_interval_dropped_from_a_subscription, id="a subscription with no interval"),
        pytest.param(_swapped_subscription_intervals, id="monthly and yearly intervals swapped"),
        pytest.param(_price_as_a_string, id="price as a string"),
        pytest.param(_free_price, id="a price of zero"),
        pytest.param(_lowercase_currency, id="currency Intl.NumberFormat would throw on"),
        pytest.param(_same_day_promise, id="a zero-business-day delivery promise"),
        pytest.param(_undeclared_top_level_key, id="an undeclared top-level key"),
        pytest.param(_blank_label, id="a product with no label"),
    ],
)
def test_the_contract_refuses_a_plan_that_would_ship_a_broken_checkout(
    mutate: Callable[[Plan], None],
) -> None:
    plan = _live_plan()
    mutate(plan)
    assert _errors(plan), "the schema accepted a plan the page cannot honour"


def test_payments_may_be_turned_off_with_every_price_and_link_withdrawn() -> None:
    """The "not yet available" state is a legitimate document, not a degraded one.

    ``web/src/bundle.js`` renders it deliberately, and the tier shipped in it for weeks
    before the Stripe rail existed. A contract that only accepted a sellable plan would
    make turning the tier off a schema violation.
    """
    plan = _live_plan()
    plan["paymentsAvailable"] = False
    for product in plan["products"].values():
        product["price"] = None
        product["checkout_url"] = None
    assert _errors(plan) == []


def test_turning_payments_off_does_not_require_withdrawing_the_links() -> None:
    """Only the ``true`` direction is a claim; ``false`` constrains nothing about prices."""
    plan = _live_plan()
    plan["paymentsAvailable"] = False
    assert _errors(plan) == []


# ---------------------------------------------------------------------------
# The three authored price lists
# ---------------------------------------------------------------------------

_DOC_ROW = re.compile(
    r"^\|\s*`(?P<key>[a-z0-9_]+)`\s*\|\s*"
    r"\$(?P<amount>[\d,]+(?:\.\d{2})?)\s+(?P<cadence>once|a month|a year)\s*\|",
    re.MULTILINE,
)
_DOC_CADENCE = {"once": None, "a month": "month", "a year": "year"}

_SCRIPT_CONSTANT = re.compile(r"^(?P<name>[A-Z0-9_]+_CENTS)=(?P<cents>\d+)\s*$", re.MULTILINE)
_SCRIPT_PRICE_LINE = re.compile(
    r'--unit-amount\s+"\$(?P<name>[A-Z0-9_]+_CENTS)".*?--nickname\s+"(?P<key>[a-z0-9_]+)"'
)
_SCRIPT_INTERVAL = re.compile(r"recurring\[interval\]=(?P<interval>[a-z]+)")


def _documented_prices() -> PriceTable:
    """The price table in ``docs/program-plan.md``, as the operator wrote it down."""
    table: PriceTable = {}
    for match in _DOC_ROW.finditer(DOC_PATH.read_text(encoding="utf-8")):
        key = match.group("key")
        if key not in PRODUCT_KEYS:
            continue
        amount = Decimal(match.group("amount").replace(",", ""))
        table[key] = (amount, _DOC_CADENCE[match.group("cadence")])
    return table


def _scripted_prices() -> PriceTable:
    """What ``scripts/stripe-setup.sh`` would create, read through its own wiring.

    The cents constant is bound to a product by the ``prices create`` line that spends it,
    not by a mapping written here, so pointing ``BUNDLE_25_CENTS`` at the 100-agency price
    is a disagreement this can see.
    """
    body = SETUP_SCRIPT_PATH.read_text(encoding="utf-8")
    cents = {m.group("name"): int(m.group("cents")) for m in _SCRIPT_CONSTANT.finditer(body)}
    table: PriceTable = {}
    for line in body.splitlines():
        match = _SCRIPT_PRICE_LINE.search(line)
        if match is None:
            continue
        key = match.group("key")
        if key not in PRODUCT_KEYS:
            continue
        name = match.group("name")
        assert name in cents, f"{key} spends {name}, which the script never assigns"
        interval_match = _SCRIPT_INTERVAL.search(line)
        interval = interval_match.group("interval") if interval_match else None
        table[key] = (Decimal(cents[name]) / 100, interval)
    return table


def _published_prices() -> PriceTable:
    """What ``/bundle/plan.json`` tells the page to print."""
    products = _live_plan()["products"]
    return {
        key: (Decimal(str(product["price"])), product["interval"])
        for key, product in products.items()
        if key in PRODUCT_KEYS and product["price"] is not None
    }


@pytest.mark.parametrize(
    ("source", "reader"),
    [
        pytest.param(DOC_PATH.name, _documented_prices, id="docs/program-plan.md"),
        pytest.param(SETUP_SCRIPT_PATH.name, _scripted_prices, id="scripts/stripe-setup.sh"),
        pytest.param(PLAN_PATH.name, _published_prices, id="web/bundle/plan.json"),
    ],
)
def test_each_price_list_is_read_in_full_before_anything_is_compared(
    source: str, reader: Callable[[], PriceTable]
) -> None:
    """A parser that finds nothing agrees with everything. Fail there instead."""
    assert set(reader()) == set(PRODUCT_KEYS), (
        f"{source} no longer yields exactly {PRODUCT_KEYS}; the agreement check below "
        f"would be comparing whatever survived the reword"
    )


def test_the_document_the_script_and_the_page_state_the_same_prices() -> None:
    documented = _documented_prices()
    scripted = _scripted_prices()
    published = _published_prices()

    disagreements = [
        f"{key}: docs/program-plan.md says {documented[key]}, "
        f"scripts/stripe-setup.sh says {scripted[key]}, "
        f"web/bundle/plan.json says {published[key]}"
        for key in PRODUCT_KEYS
        if not documented[key] == scripted[key] == published[key]
    ]
    assert not disagreements, "\n".join(disagreements)


def test_every_amount_the_script_sets_is_a_whole_number_of_currency_units() -> None:
    """``plan.json`` carries dollars and the script carries cents; a stray 50 cents would
    make one of them unrepresentable rather than merely wrong."""
    for key, (amount, _interval) in _scripted_prices().items():
        assert amount == amount.to_integral_value(), f"{key} is not a whole number of units"


def test_the_page_itself_still_carries_no_price() -> None:
    """docs/program-plan.md: "the site never carries a price of its own".

    Prices live in ``plan.json`` so that turning the tier on or moving a price is a data
    change. A currency amount typed into the markup is a fourth copy that nothing above
    reconciles, and it would survive ``paymentsAvailable: false``.
    """
    hardcoded = re.findall(r"\$\s?[\d,]+(?:\.\d{2})?", PAGE_PATH.read_text(encoding="utf-8"))
    assert hardcoded == [], f"{PAGE_PATH.name} hardcodes {hardcoded}"


# ---------------------------------------------------------------------------
# The pages the paid flow needs to exist at all
# ---------------------------------------------------------------------------

BUDGETS_PATH = REPO_ROOT / "site-budgets.json"

# /bundle/ takes the payment and /bundle/setup/ is where Stripe redirects the buyer
# afterwards to name their agencies. Both are hand-authored files copied into the built
# site, so neither has a renderer that would fail loudly if it stopped being produced.
PAID_FLOW_PAGES = ("bundle/index.html", "bundle/setup/index.html")


@pytest.mark.parametrize("relative", PAID_FLOW_PAGES)
def test_the_paid_flow_pages_are_structurally_required_in_the_built_site(relative: str) -> None:
    """Their absence must be a hard failure, not an untested assumption.

    ``pipeline/scripts/check_site_budgets.py`` separates the two outcomes on purpose: a
    missing ``required`` page exits 2 and always blocks, while a size overage exits 1 and a
    data-refresh deploy may treat it as advisory. Before this entry existed both bundle
    pages were covered only by the ``**/index.html`` pattern at 3,407,872 bytes — a ceiling
    over three hundred times their size, which matches on whatever files happen to be there
    and therefore says nothing at all about these two being among them. A deploy that
    dropped the page that takes the money would have passed every gate in the repository.
    """
    required = json.loads(BUDGETS_PATH.read_text(encoding="utf-8"))["required"]
    assert relative in required, f"{relative} is not a required page in site-budgets.json"
    limit = required[relative]
    size = (REPO_ROOT / "web" / relative).stat().st_size
    assert size <= limit, f"{relative} is {size:,} bytes against a {limit:,}-byte budget"
