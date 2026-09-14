"""The served /bundle/ page must state what it charges, and never something else.

Measured on the live site on 2026-09-13 (issue #417): `/bundle/` was selling
four plans and the bytes it served contained **no price and no `Offer` node**.
The amounts existed only in the DOM after `web/src/bundle.js` fetched
`plan.json`, so a crawler, an assistant, or a reader without scripting saw a
sales page that sold nothing at no price.

The fix is generated markup, not typed markup, and that distinction is the
reason for most of this file. `web/bundle/plan.json` is the single source of
every price in this project, and the repository already gates its other copies
against it because a copied price keeps selling after the plan changes. A
hand-written `Offer` block would have been one more copy. So the block is
produced by `site_shell.sync_bundle_offers` and these tests fail the build the
moment the committed markup and the plan disagree — which is what makes the
served page a reading of `plan.json` rather than a second opinion about it.

Three properties:

1. **It agrees with the plan**, byte for byte, against the generator.
2. **It says nothing when there is nothing to say.** `paymentsAvailable: false`,
   a product with no numeric price, a checkout link that is not https — each
   removes an offer, and an empty set removes the block. "Never describe what
   the page cannot do" was already the rule in the DOM; this holds the served
   markup to it too.
3. **It states the real amount.** A test that only checked "generator output ==
   file" would pass just as happily if the generator emitted nothing at all, so
   the values are also asserted against `plan.json` directly.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from scorecard_pipeline.site_shell import (
    _BUNDLE_NOSCRIPT_RE,
    _BUNDLE_OFFERS_RE,
    BUNDLE_OFFERS_SCRIPT_ID,
    BUNDLE_RENEWAL_NOTE,
    BUNDLE_SERVICE_ID,
    bundle_noscript_html,
    bundle_noscript_region,
    bundle_offer_nodes,
    bundle_offers_jsonld,
    bundle_offers_region,
    bundle_price_text,
)

# The real repo, not the tmp root conftest points artifacts_dir at.
_REPO = Path(__file__).resolve().parents[2]
_WEB = _REPO / "web"
_PAGE = _WEB / "bundle" / "index.html"
_PLAN = _WEB / "bundle" / "plan.json"


def _plan() -> dict[str, Any]:
    plan: dict[str, Any] = json.loads(_PLAN.read_text())
    return plan


def _region(html: str) -> str:
    match = _BUNDLE_OFFERS_RE.search(html)
    assert match is not None, (
        "web/bundle/index.html has no offers:begin/offers:end region; "
        "`make sync-bundle-offers` has nothing to write into"
    )
    return match.group(0)


def _served_node(html: str) -> dict[str, Any] | None:
    block = re.search(
        rf'<script id="{BUNDLE_OFFERS_SCRIPT_ID}" type="application/ld\+json">(.*?)</script>',
        _region(html),
        re.S,
    )
    return None if block is None else json.loads(block.group(1))


def test_bundle_offers_markup_matches_plan_json() -> None:
    """The committed block is what the generator makes from the current plan.

    This is the whole gate: edit a price in plan.json without running
    `make sync-bundle-offers` and the page keeps advertising the old one, to
    every machine that reads it and to no one who would notice. Compared as the
    exact region text, markers included, so a partial hand-edit inside the
    region fails too.
    """
    assert _region(_PAGE.read_text()) == bundle_offers_region(_plan()), (
        "/bundle/'s offers block and web/bundle/plan.json disagree; "
        "run `make sync-bundle-offers` and commit the result"
    )


def test_the_served_page_states_every_price_the_plan_sells() -> None:
    """Every sellable product reaches the served markup, with its real amount.

    The agreement test above compares the file to the generator; on its own it
    would pass if the generator had stopped emitting anything. This reads the
    amounts back out of the served page and checks them against plan.json,
    which is the claim that actually matters: the page states what it charges.
    """
    plan = _plan()
    assert plan.get("paymentsAvailable") is True, (
        "plan.json is not selling; this test asserts what a selling page must "
        "state and would prove nothing here. The off case is covered by "
        "test_nothing_is_offered_when_the_plan_sells_nothing."
    )
    sellable = {
        str(product["label"]): str(product["price"])
        for product in plan["products"].values()
        if isinstance(product.get("price"), (int, float))
    }
    assert len(sellable) >= 2, "plan.json lists too few products for this sweep to prove anything"

    node = _served_node(_PAGE.read_text())
    assert node is not None, "the served page carries no offers node while the plan is selling"
    assert node["@id"] == BUNDLE_SERVICE_ID, (
        "the offers node does not attach to the page's Service node, so the two "
        "describe two different services"
    )

    offers = node["offers"]
    listed = offers["offers"] if offers.get("@type") == "AggregateOffer" else [offers]
    served = {offer["name"]: offer["price"] for offer in listed}
    assert served == sellable, f"the page offers {served}, the plan sells {sellable}"

    currency = str(plan.get("currency") or "USD")
    for offer in listed:
        assert offer["priceCurrency"] == currency
        assert offer["availability"] == "https://schema.org/InStock"
        assert offer["url"].startswith("https://"), (
            f"{offer['name']}: an Offer with a non-https url is a checkout a "
            "reader cannot be sent to"
        )


def test_the_advertised_price_range_is_two_of_the_advertised_prices() -> None:
    """``lowPrice`` and ``highPrice`` are strings the offers themselves carry.

    A range recomputed and reformatted is a third statement of the same amount:
    "49" in the Offer and "49.0" in the range are two renderings of one price,
    and only one of them is what the plan says.
    """
    node = bundle_offers_jsonld(_plan())
    assert node is not None
    offers = node["offers"]
    if offers.get("@type") != "AggregateOffer":
        return
    prices = [offer["price"] for offer in offers["offers"]]
    assert offers["lowPrice"] in prices and offers["highPrice"] in prices
    assert float(offers["lowPrice"]) == min(float(price) for price in prices)
    assert float(offers["highPrice"]) == max(float(price) for price in prices)
    assert offers["offerCount"] == len(prices)


def test_nothing_is_offered_when_the_plan_sells_nothing() -> None:
    """Each refusal removes an offer, and an empty set removes the block.

    The rule the page already followed in the DOM — never describe what it
    cannot do — applied to the served markup. Each case is exercised rather
    than argued: the live plan is currently selling, so none of these states
    would be reached by reading the committed file alone.
    """
    plan = _plan()
    assert bundle_offer_nodes(plan), "the live plan sells nothing; the cases below prove little"

    off = {**deepcopy(plan), "paymentsAvailable": False}
    assert bundle_offer_nodes(off) == []
    assert bundle_offers_jsonld(off) is None
    assert BUNDLE_OFFERS_SCRIPT_ID not in bundle_offers_region(off)
    assert "149" not in bundle_offers_region(off)

    # A truthy-looking but non-boolean value is not permission to sell.
    assert bundle_offer_nodes({**deepcopy(plan), "paymentsAvailable": "true"}) == []

    priced = deepcopy(plan)
    for product in priced["products"].values():
        product["price"] = None
    assert bundle_offers_jsonld(priced) is None

    insecure = deepcopy(plan)
    for product in insecure["products"].values():
        product["checkout_url"] = "http://buy.example.test/x"
    assert bundle_offers_jsonld(insecure) is None

    one_left = deepcopy(plan)
    for key in list(one_left["products"])[1:]:
        del one_left["products"][key]
    single = bundle_offers_jsonld(one_left)
    assert single is not None
    assert single["offers"]["@type"] == "Offer", (
        "one product must not be wrapped in an AggregateOffer, which would "
        "advertise a range across a single price"
    )


def test_the_offers_node_names_the_page_it_is_on() -> None:
    """``url`` is required of every top-level node of a required @type.

    ``site-seo.json`` requires a ``Service`` on ``/bundle/``, and
    ``check_site_seo.py`` asks each top-level node of that type for this page's
    canonical URL. Without it the deploy gate refuses the page — which is how
    this was caught rather than shipped.
    """
    node = bundle_offers_jsonld(_plan())
    assert node is not None
    assert node["url"] == "https://gtfsscorecard.org/bundle/"
    assert node["@context"] == "https://schema.org"


def test_the_offers_node_is_a_product_google_can_index() -> None:
    """A ``Service`` node is not eligible for Google's Product structured data.

    Measured: the served node was typed only ``Service``, with no ``name`` of
    its own. Google's Product structured data (the free "Popular products" and
    product-snippet surfaces that do not need a Merchant Center account) needs
    a node typed ``Product`` carrying a ``name`` plus at least one of
    ``offers``, ``review``, or ``aggregateRating`` -- and needs it regardless
    of whether a browser or crawler treats this script tag and the page's
    separate hand-authored Service block, which share an ``@id``, as one
    merged node. This node must therefore be self-sufficient: ``Product``
    among its types, with its own ``name``, sitting beside the ``offers`` it
    already carried.
    """
    node = bundle_offers_jsonld(_plan())
    assert node is not None
    assert isinstance(node["@type"], list) and "Product" in node["@type"], (
        "the offers node is not typed Product, so its offers are invisible to "
        "Google's Product structured data"
    )
    assert "Service" in node["@type"], (
        "site-seo.json still requires a Service @type on /bundle/; dropping it "
        "here would redden the structural SEO gate"
    )
    assert node.get("name"), (
        "a Product node with no name fails Google's own required-property check "
        "even though it carries offers"
    )


def test_the_runtime_rewrite_targets_the_block_the_server_wrote() -> None:
    """bundle.js replaces this element; it must not add a second one.

    The served block and the script both use one element id on purpose: the
    script's existing `getElementById(...).remove()` finds the server-rendered
    block, so the page carries exactly one offers node before and after
    scripting, and a plan that stops selling still clears what the server
    wrote. If the ids ever drift apart the page publishes two Service nodes
    with one @id, one of them stale.
    """
    script = (_WEB / "src" / "bundle.js").read_text()
    assert f'"{BUNDLE_OFFERS_SCRIPT_ID}"' in script, (
        "bundle.js no longer names the server-rendered offers block, so it "
        "would append a second one instead of replacing it"
    )
    assert f'"{BUNDLE_SERVICE_ID}"' in script
    served = _served_node(_PAGE.read_text())
    assert served is not None
    for field in ("@context", "@type", "@id", "url", "offers"):
        assert field in served
    # The script builds the same fields; asserting the names appear in its
    # source keeps a renamed key on one side from silently halving the page.
    for field in ("@context", "@type", "@id", "url", "offers"):
        assert field in script, f"bundle.js no longer emits {field!r}"


# --- and the half of #417 a person reads -----------------------------------
#
# The JSON-LD above closed the machine half: a crawler can now read what the
# page charges. A reader with scripting off still read "nothing is for sale from
# this page without it" while four live Payment Links were being served. The
# same generator writes the list they see, from the same plan, under the same
# drift gate. Prices visible without scripting went from 0 of 4 to 4 of 4.


def _noscript_region(html: str) -> str:
    match = _BUNDLE_NOSCRIPT_RE.search(html)
    assert match is not None, (
        "web/bundle/index.html has no noscript-plans:begin/noscript-plans:end region; "
        "`make sync-bundle-offers` has nothing to write into"
    )
    return match.group(0)


def test_the_noscript_plan_list_matches_plan_json() -> None:
    """Same gate as the offers block, on the region a person reads.

    Compared as the exact region text, markers included, so a hand-edit inside
    the region fails as loudly as a stale one: the amounts a reader sees are a
    rendering of plan.json or the build is red.
    """
    assert _noscript_region(_PAGE.read_text()) == bundle_noscript_region(_plan()), (
        "/bundle/'s no-scripting plan list and web/bundle/plan.json disagree; "
        "run `make sync-bundle-offers` and commit the result"
    )


def test_a_reader_without_scripting_sees_every_price_the_plan_sells() -> None:
    """The claim that matters, asserted against plan.json rather than the generator.

    A test that only compared file to generator would pass just as happily if
    the generator emitted an empty block, which is exactly the state #417
    measured on the live site.
    """
    plan = _plan()
    assert plan.get("paymentsAvailable") is True, (
        "plan.json is not selling; this test asserts what a selling page must show"
    )
    region = _noscript_region(_PAGE.read_text())
    currency = str(plan.get("currency") or "USD")
    for key, product in plan["products"].items():
        amount = bundle_price_text(float(product["price"]), currency)
        assert amount in region, f"{key}: a reader without scripting never sees {amount}"
        assert str(product["label"]) in region, f"{key}: its price is shown with no label"
        if product.get("interval"):
            assert f"{amount} per {product['interval']}" in region, (
                f"{key}: an amount with no cadence beside it reads as a one-time charge"
            )


def test_the_noscript_list_sends_nobody_to_a_checkout_it_cannot_finish() -> None:
    """No buy control here, on purpose, and the reason is measurable.

    ``/bundle/setup/`` -- where Stripe returns the buyer -- is a ``<form>`` with
    no ``action`` and no ``method``; ``web/src/bundle-setup.js`` submits it. With
    scripting off it cannot be completed at all. A checkout link in this block
    would therefore take the money and strand the payer, and the refund clock
    starts at the checkout rather than at the form
    (``scorecard_pipeline/deadline.py``), so the stranding is expensive as well
    as rude. The page's rule is to describe nothing it cannot do; this is that
    rule applied to the checkout.

    Asserted from the setup page's own markup, so the day that form gains a
    server-side action this test fails and the decision is revisited rather
    than inherited.
    """
    setup = (_WEB / "bundle" / "setup" / "index.html").read_text()
    form = re.search(r"<form[^>]*id=\"setup-form\"[^>]*>", setup)
    assert form is not None, "the setup form was renamed; this reasoning needs rechecking"
    assert "action=" not in form.group(0) and "method=" not in form.group(0), (
        "/bundle/setup/ can now submit without scripting, so the no-scripting plan "
        "list may carry checkout links; revisit bundle_noscript_html"
    )

    # Both the committed region and what the generator would write now. Checking
    # only the file leaves a generator that has grown a checkout link passing
    # here until someone runs `make sync-bundle-offers` -- which is exactly what
    # a negative control on this test found: sabotaging the generator alone left
    # it green.
    for source, markup in (
        ("web/bundle/index.html", _noscript_region(_PAGE.read_text())),
        ("site_shell.bundle_noscript_html", bundle_noscript_html(_plan())),
    ):
        assert "buy.stripe.com" not in markup and "<a " not in markup, (
            f"{source}: the no-scripting plan list offers a checkout the buyer cannot complete"
        )
        assert "need scripting enabled" in markup, (
            f"{source}: the list states prices but not that it cannot sell, which is "
            "the page's own rule about describing what it cannot do"
        )


def test_the_setup_page_says_its_form_is_dead_without_scripting() -> None:
    """The one dead control on this site that sits after the money changed hands.

    Without this the button is silent: a buyer who has already paid clicks
    "Build my reports", nothing happens, and the two business days they were
    promised are already running.
    """
    setup = (_WEB / "bundle" / "setup" / "index.html").read_text()
    warning = re.search(r"<noscript>\s*<p[^>]*>(.*?)</p>", setup, re.S)
    assert warning is not None, "/bundle/setup/ gives a scripting-off buyer no warning at all"
    text = " ".join(warning.group(1).split())
    assert "scripting" in text
    assert "will not do anything" in text, "the warning does not say the button is dead"


def test_the_renewal_condition_reads_the_same_with_and_without_scripting() -> None:
    """A subscription renews a bundle and does not include one.

    Shown on the scripted card by web/src/bundle.js and on the generated list by
    site_shell. Two renderings of one condition, so they are held to one string:
    a reader quoted "$49 per month" without it has been told the price of
    something other than what they would be buying.
    """
    assert BUNDLE_RENEWAL_NOTE in (_WEB / "src" / "bundle.js").read_text(), (
        "bundle.js no longer states the renewal condition in the words the "
        "generated list uses; the two surfaces have drifted"
    )
    region = _noscript_region(_PAGE.read_text())
    plan = _plan()
    for key, product in plan["products"].items():
        if product.get("interval"):
            assert BUNDLE_RENEWAL_NOTE in region, f"{key}: sold without its renewal condition"


def test_nothing_is_shown_without_scripting_when_the_plan_sells_nothing() -> None:
    """The tier-off rule, applied to the region a person reads.

    Each refusal that removes an Offer removes a card here too, and an empty set
    leaves the sentence saying so and no amount at all -- which is what makes
    switching the tier off still a data change rather than a copy change.
    """
    plan = _plan()
    live = bundle_price_text(float(plan["products"]["bundle_25"]["price"]), plan["currency"])
    assert live in bundle_noscript_html(plan), (
        "the live plan shows no price; the cases below prove little"
    )

    for label, broken in (
        ("payments off", {**deepcopy(plan), "paymentsAvailable": False}),
        ("truthy string", {**deepcopy(plan), "paymentsAvailable": "true"}),
    ):
        rendered = bundle_noscript_html(broken)
        assert "$" not in rendered, f"{label}: an amount survived the tier being off"
        assert "No plan is for sale" in rendered, label

    priced = deepcopy(plan)
    for product in priced["products"].values():
        product["price"] = None
    assert "$" not in bundle_noscript_html(priced)

    insecure = deepcopy(plan)
    for product in insecure["products"].values():
        product["checkout_url"] = "http://buy.example.test/x"
    assert "$" not in bundle_noscript_html(insecure), (
        "a plan whose checkout links are not https states a price to a reader "
        "while stating no Offer to a crawler; the two gates must agree"
    )


def test_the_amount_a_reader_sees_is_the_amount_the_offer_carries() -> None:
    """One plan, two renderings, no third opinion about the number.

    The Offer carries "149" and the reader sees "$149". Both come from
    plan.json, so the only way they can disagree is a formatting bug here --
    which is what this checks, by taking the digits back out of the rendered
    string.
    """
    plan = _plan()
    currency = str(plan.get("currency") or "USD")
    by_name = {node["name"]: node["price"] for node in bundle_offer_nodes(plan)}
    assert by_name, "no offers to compare against"
    for product in plan["products"].values():
        rendered = bundle_price_text(float(product["price"]), currency)
        assert rendered.lstrip("$").replace(",", "") == str(int(product["price"]))
        assert by_name[str(product["label"])] == str(product["price"])


# --- and the answers it gives a search result -------------------------------


# Inline elements add nothing between their neighbours and everything else adds
# a space, so "the <a>open-source command</a>." reads as one sentence rather
# than as "command ." -- which is the difference between a drift check that
# works and one that reports its own tag stripping as a finding.
_INLINE_TAGS = frozenset(
    {"a", "strong", "em", "b", "i", "code", "span", "abbr", "small", "sup", "sub", "br"}
)
_SKIPPED_BODIES = frozenset({"script", "style"})


class _ProseParser(HTMLParser):
    """Collects a page's text, skipping script and style bodies.

    A tokenizer rather than regular expressions, on purpose. The first version
    of this helper stripped ``<script>`` blocks with a pattern that does not
    match an end tag written ``</script >``, and CodeQL raised it on the pull
    request that added it (py/bad-tag-filter, high). Nothing here sanitizes
    untrusted input, but a missed end tag would have swallowed page prose and
    turned this drift check into one that fails, or passes, for the wrong
    reason. The standard library already ends a script or style body the way a
    browser does, so there is no hand-written filter left to get wrong.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED_BODIES:
            self._skipping += 1
        elif tag not in _INLINE_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_BODIES:
            self._skipping = max(0, self._skipping - 1)
        elif tag not in _INLINE_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def _visible_text(html: str) -> str:
    """The page's prose, near enough for a substring comparison.

    Comments are dropped because ``HTMLParser`` routes them to
    ``handle_comment``, which this parser does not keep.
    """
    parser = _ProseParser()
    parser.feed(html)
    parser.close()
    return " ".join("".join(parser.parts).split())


def _faq_node(html: str) -> dict[str, Any]:
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        node = json.loads(block)
        if node.get("@type") == "FAQPage":
            return dict(node)
    raise AssertionError("/bundle/ no longer publishes a FAQPage; nothing here can be checked")


def test_every_answer_the_page_publishes_is_an_answer_the_page_gives() -> None:
    """The FAQ structured data restates seven of this page's own sentences.

    Nothing held the two together. A search result is built from the structured
    copy, so a reworded promise on the page -- the delivery window, the refund,
    what a purchase does not buy -- would keep being quoted in its old words to
    every reader who never reaches the page. On the one page that takes money
    that is not a formatting bug, it is a stale commitment.

    Compared as substrings of the rendered prose, so the page may say more than
    it publishes; it may not publish something it does not say.
    """
    page = _PAGE.read_text()
    prose = _visible_text(page)
    questions = _faq_node(page)["mainEntity"]
    assert len(questions) >= 5, "the FAQ shrank; this sweep would prove little"

    for question in questions:
        answer = " ".join(str(question["acceptedAnswer"]["text"]).split())
        assert answer in prose, (
            f"/bundle/ publishes an answer to {question['name']!r} that the page "
            f"itself no longer gives:\n  published: {answer}"
        )
        # And the question is a heading or a term on the page, not only in the
        # structured data, so the FAQ cannot grow a topic the page never raises.
        assert str(question["name"]) in prose, (
            f"/bundle/ publishes the question {question['name']!r}, which appears "
            "nowhere in the page's own text"
        )


def test_the_prose_reader_skips_script_bodies_however_the_end_tag_is_written() -> None:
    """The drift check above is only a check while this holds.

    Every FAQ answer is also inside the page's FAQPage JSON-LD, which sits in a
    ``<script>``. A prose reader that let script bodies through would find each
    answer there and pass the drift check on any page at all -- a gate that
    cannot fail. So the skip is pinned here directly, including the end-tag
    spellings a regular expression misses, which is what CodeQL flagged on the
    first version of this helper.
    """
    for end in ("</script>", "</script >", "</SCRIPT>", "</script\n>", "</script\t>"):
        page = f'<p>before</p><script type="application/ld+json">{{"k": "inside"}}{end}<p>after</p>'
        text = _visible_text(page)
        assert "inside" not in text, f"a script body ending {end!r} leaked into the prose"
        assert text == "before after", (end, text)

    assert _visible_text("<p>x</p><style>.y { color: red }</style ><p>z</p>") == "x z"
    assert _visible_text("<p>a</p><!-- not prose --><p>b</p>") == "a b"
    assert _visible_text('<p>the <a href="/x">open-source command</a>.</p>') == (
        "the open-source command."
    )

    # And on the real page: the structured data's own vocabulary never reaches
    # the prose, so an answer found in the prose was found in the prose.
    prose = _visible_text(_PAGE.read_text())
    for token in ('"@type"', "acceptedAnswer", "mainEntity", "application/ld+json"):
        assert token not in prose, f"{token} from a script body leaked into /bundle/'s prose"
