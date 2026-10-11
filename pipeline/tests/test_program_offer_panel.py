"""The program panel on the program rollup pages (ADR 0064, amending 0058).

From 2026-09-18 the panel sat on every agency scorecard (ADR 0058). In 23 days
0 of 2,945 sessions that landed on an agency page reached /bundle/, so the
owner moved it to the rollup pages: /program/all/ and each program's page,
the group views the people it addresses already read. Three properties are
held here rather than assumed:

1. **It quotes only what the plan sells.** The price comes from plan.json. A
   render with no sellable plan shows the plain pointer the app's rollup view
   also shows, word for word, and no price.
2. **Every link in it goes somewhere real.** The CTA, the sample, and the
   counted link all resolve, and the plan it quotes is the plan /bundle/ sells.
3. **The negative controls bite.** Each "no panel" case asserts that its
   sabotage actually landed before asserting the absence, so a control that
   silently no-ops cannot read as a pass.

The placement and "nowhere else" rules live next door in
``test_paid_tier_visibility.py``.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.render_site import (
    _ROLLUP_BUNDLE_SECTION,
    ProgramOffer,
    _program_offer_section,
    _render_agency,
    _render_rollup,
    load_program_offer,
)

_REPO = Path(__file__).resolve().parents[2]
_WEB = _REPO / "web"
_GOLDENS = _REPO / "pipeline" / "tests" / "goldens"
_FIXTURE = _REPO / "pipeline" / "tests" / "fixtures" / "golden_site"
_FOOTER_TAG = '<footer class="site-footer">'
_PANEL_RE = re.compile(
    r'<section class="action-panel program-offer" aria-labelledby="bundle-h">.*?</section>',
    re.S,
)
_HREF_RE = re.compile(r'href="([^"]+)"')
_AGENCIES = ("unitrans", "yolobus", "barrie-transit")
_ROLLUPS = ("all", "california", "yolo-county")

# Deliberately not the live prices: a panel that printed these could only have
# read them from the plan handed to it.
_PLAN: dict[str, Any] = {
    "schema_version": "1",
    "paymentsAvailable": True,
    "currency": "USD",
    "provisioning_business_days": 3,
    "products": {
        "big": {
            "label": "Big bundle",
            "price": 777,
            "interval": None,
            "checkout_url": "https://buy.stripe.com/test_big",
        },
        "small": {
            "label": "Small bundle",
            "price": 17,
            "interval": None,
            "checkout_url": "https://buy.stripe.com/test_small",
        },
        "refresh": {
            "label": "Refresh",
            "price": 5,
            "interval": "month",
            "checkout_url": "https://buy.stripe.com/test_refresh",
        },
    },
}


def _write_plan(root: Path, plan: object) -> Path:
    path = root / "bundle" / "plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan if isinstance(plan, str) else json.dumps(plan))
    return root


def _offer() -> ProgramOffer:
    return ProgramOffer(
        label="Small bundle",
        amount="$17",
        other_plans=True,
        has_refresh=True,
        delivery_days=3,
    )


def _artifact(agency_id: str = "unitrans") -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (_FIXTURE / "data" / "artifacts" / agency_id / "latest.json").read_text()
    )
    return data


def _history(agency_id: str = "unitrans") -> list[dict[str, Any]]:
    index = json.loads((_FIXTURE / "data" / "artifacts" / "index.json").read_text())
    return list(index["agencies"][agency_id]["history"])


def _above_footer(html: str) -> str:
    head, sep, _ = html.partition(_FOOTER_TAG)
    assert sep, "no shared footer; the split proves nothing"
    return head


# --- 1. the plan: read, never typed ------------------------------------------


def test_load_program_offer_quotes_the_cheapest_one_time_plan(tmp_path: Path) -> None:
    offer = load_program_offer(_write_plan(tmp_path, _PLAN))
    assert offer == ProgramOffer(
        label="Small bundle",
        amount="$17",
        other_plans=True,
        has_refresh=True,
        delivery_days=3,
    )


def _plan_with(**changes: Any) -> dict[str, Any]:
    plan = copy.deepcopy(_PLAN)
    for key, value in changes.items():
        plan[key] = value
    return plan


def _only_subscriptions() -> dict[str, Any]:
    plan = copy.deepcopy(_PLAN)
    plan["products"] = {"refresh": plan["products"]["refresh"]}
    return plan


def _no_https_checkout() -> dict[str, Any]:
    plan = copy.deepcopy(_PLAN)
    for product in plan["products"].values():
        product["checkout_url"] = "http://insecure.example/checkout"
    return plan


def _no_numeric_price() -> dict[str, Any]:
    plan = copy.deepcopy(_PLAN)
    for product in plan["products"].values():
        product["price"] = "call us"
    return plan


@pytest.mark.parametrize(
    "plan",
    [
        pytest.param(None, id="no-plan-file"),
        pytest.param("{not json", id="unreadable"),
        pytest.param([], id="not-a-mapping"),
        pytest.param(_plan_with(paymentsAvailable=False), id="payments-off"),
        pytest.param(_plan_with(products={}), id="no-products"),
        pytest.param(_only_subscriptions(), id="only-subscriptions"),
        pytest.param(_no_https_checkout(), id="no-https-checkout"),
        pytest.param(_no_numeric_price(), id="no-numeric-price"),
    ],
)
def test_a_plan_that_sells_nothing_yields_no_offer(tmp_path: Path, plan: object) -> None:
    if plan is not None:
        _write_plan(tmp_path, plan)
    assert load_program_offer(tmp_path) is None


def _rollup(rollup_id: str = "all") -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (_FIXTURE / "data" / "artifacts" / "rollups" / f"{rollup_id}.json").read_text()
    )
    return data


def test_delivery_promise_is_dropped_when_the_plan_does_not_state_one(tmp_path: Path) -> None:
    offer = load_program_offer(_write_plan(tmp_path, _plan_with(provisioning_business_days=None)))
    assert offer is not None and offer.delivery_days is None
    html = _program_offer_section(offer)
    assert ", paid once." in html
    assert "business days" not in html


# --- 2. the panel quotes the plan, and only a sellable one ------------------


def test_the_panel_states_the_plans_price_and_the_two_promises() -> None:
    html = _program_offer_section(_offer())
    assert _PANEL_RE.fullmatch(html), "the panel is not one program-offer section"
    assert "<strong>Small bundle:</strong> $17, paid once" in html
    assert "delivered within 3 business days or refunded" in html
    assert "including a monthly refresh" in html
    assert "free, printable board one-pager on its own page, and always will" in html
    assert "buys no influence over grades, methodology, or which agencies are listed" in html
    # The pointer's "prices are on that page" gives way to the price itself.
    assert "Prices are on that page." not in html
    link = re.search(r'<a [^>]*data-measure="bundle_panel_click"[^>]*>', html)
    assert link is not None and 'href="/bundle/"' in link.group(0)
    assert '<a href="/bundle/sample/">' in html


def test_negative_control_no_sellable_plan_is_the_plain_pointer(tmp_path: Path) -> None:
    """Payments off must quote nothing: the rollup keeps the pointer the app's
    twin view also shows, with no price, no counted link, and no sample."""
    control = _program_offer_section(_offer())
    assert "paid once" in control and "bundle_panel_click" in control, (
        "the unsabotaged control quotes nothing; this proves nothing"
    )
    plan = _plan_with(paymentsAvailable=False)
    assert plan["paymentsAvailable"] is False, "the sabotage did not apply"
    offer = load_program_offer(_write_plan(tmp_path, plan))
    assert offer is None, "a plan with payments off still yields an offer"
    html = _program_offer_section(offer)
    assert html == _ROLLUP_BUNDLE_SECTION
    assert "paid once" not in html and "data-measure" not in html and "/bundle/sample/" not in html


@pytest.mark.parametrize("rollup_id", _ROLLUPS)
def test_the_rollup_page_carries_the_panel_after_its_member_list(rollup_id: str) -> None:
    payload = _rollup(rollup_id)
    html = _above_footer(_render_rollup(payload, None, _offer()))
    panels = _PANEL_RE.findall(html)
    assert len(panels) == 1, f"{rollup_id}: expected one panel, found {len(panels)}"
    assert html.index('id="members-h"') < html.index('id="bundle-h"')
    without = _above_footer(_render_rollup(payload, None, None))
    assert _ROLLUP_BUNDLE_SECTION in without
    assert "program-offer" not in without and "paid once" not in without


def test_negative_control_an_agency_scorecard_cannot_carry_the_panel() -> None:
    """The scorecard renderer no longer takes an offer at all, so no caller can
    put the panel back on an agency page by passing one. The control: the
    keyword really is gone, and the rendered page names nothing paid."""
    import inspect

    assert "program_offer" not in inspect.signature(_render_agency).parameters
    with pytest.raises(TypeError):
        _render_agency(_artifact(), _history(), program_offer=_offer())  # type: ignore[call-arg]
    head = _above_footer(_render_agency(_artifact(), _history()))
    assert "program-offer" not in head
    assert "/bundle/" not in head
    assert "For programs" not in head


def test_a_printed_rollup_drops_the_panel() -> None:
    """A rollup printed for a meeting carries nothing paid, the same rule that
    already drops the shared footer on paper."""
    css = (_WEB / "src" / "styles.css").read_text()
    print_block = re.search(r"@media print \{(.*?)\n\}", css, re.S)
    assert print_block is not None
    assert re.search(r"\.program-offer[^{]*\{[^}]*display:\s*none", print_block.group(1))


def test_the_cli_standalone_scorecard_carries_no_panel() -> None:
    from scorecard_pipeline.cli import _standalone_scorecard_html

    head = _above_footer(_standalone_scorecard_html(_artifact()))
    assert "program-offer" not in head
    assert "/bundle/" not in head


# --- 3. every link in the rendered panel resolves ---------------------------


def _resolve(href: str) -> Path:
    """The file a root-relative href serves, from the goldens (rendered pages)
    or the real web/ tree (hand-authored pages like /bundle/)."""
    path = href.split("#", 1)[0]
    assert path.startswith("/") and not path.startswith("//"), f"{href}: not a site path"
    relative = path.strip("/")
    for base in (_GOLDENS, _WEB):
        candidate = base / relative / "index.html" if path.endswith("/") else base / relative
        if candidate.is_file():
            return candidate
    raise AssertionError(f"{href}: no page serves this path")


@pytest.mark.parametrize("rollup_id", _ROLLUPS)
def test_every_link_in_the_rendered_panel_resolves(rollup_id: str) -> None:
    head = _above_footer((_GOLDENS / "program" / rollup_id / "index.html").read_text())
    panels = _PANEL_RE.findall(head)
    assert len(panels) == 1, f"{rollup_id}: expected one panel, found {len(panels)}"
    hrefs = _HREF_RE.findall(panels[0])
    assert {"/bundle/", "/bundle/sample/"} <= set(hrefs)
    for href in hrefs:
        target = _resolve(href)
        if "#" in href:
            fragment = href.split("#", 1)[1]
            assert f'id="{fragment}"' in target.read_text(), f"{href}: no such anchor"


def test_the_panel_price_is_the_fixture_plan_rendered() -> None:
    offer = load_program_offer(_FIXTURE / "web")
    assert offer is not None, "the golden fixture plan sells nothing; the goldens show no panel"
    for rollup_id in _ROLLUPS:
        panel = _PANEL_RE.findall((_GOLDENS / "program" / rollup_id / "index.html").read_text())[0]
        assert f"<strong>{offer.label}:</strong> {offer.amount}, paid once" in panel


def test_the_plan_a_live_panel_quotes_is_the_plan_bundle_sells() -> None:
    """The CTA is only honest if /bundle/ sells what the panel quoted. The live
    plan's offer (the one every deployed rollup page renders) must appear, label
    and amount, in /bundle/'s own served plan list."""
    offer = load_program_offer(_WEB)
    if offer is None:
        pytest.skip("the live plan sells nothing, so no deployed page renders a panel")
    bundle = (_WEB / "bundle" / "index.html").read_text()
    assert offer.label in bundle
    assert offer.amount in bundle
    assert (_WEB / "bundle" / "sample" / "index.html").is_file()
