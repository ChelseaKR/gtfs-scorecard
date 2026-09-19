"""The program panel on an agency's scorecard page (ADR 0058).

The panel is the free-to-paid path from the pages search actually lands on:
about 97% of the site's Search Console impressions (2026-06-16 to 2026-09-11)
were agency pages. It is also the one place an agency's own page names the
paid tier, so three properties are held here rather than assumed:

1. **It quotes only what was measured.** The grade, score, and check date come
   from the artifact the page renders, and the price comes from plan.json. A
   page whose artifact lacks any of them, or a render with no sellable plan,
   shows no panel at all rather than a panel with a gap in it.
2. **Every link in it goes somewhere real.** The CTA, the sample, the free
   one-pager, and the methodology anchor all resolve, and the plan it quotes is
   the plan /bundle/ sells.
3. **The negative controls bite.** Each "no panel" case asserts that its
   sabotage actually landed before asserting the absence, so a control that
   silently no-ops cannot read as a pass.

The placement and "nowhere else" rules live next door in
``test_paid_tier_visibility.py``.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.render_site import (
    ProgramOffer,
    _program_offer_section,
    _render_agency,
    load_program_offer,
)

_REPO = Path(__file__).resolve().parents[2]
_WEB = _REPO / "web"
_GOLDENS = _REPO / "pipeline" / "tests" / "goldens"
_FIXTURE = _REPO / "pipeline" / "tests" / "fixtures" / "golden_site"
_FOOTER_TAG = '<footer class="site-footer">'
_PANEL_RE = re.compile(
    r'<section class="action-panel program-offer" aria-labelledby="program-offer-h">.*?</section>',
    re.S,
)
_HREF_RE = re.compile(r'href="([^"]+)"')
_AGENCIES = ("unitrans", "yolobus", "barrie-transit")

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


def test_delivery_promise_is_dropped_when_the_plan_does_not_state_one(tmp_path: Path) -> None:
    offer = load_program_offer(_write_plan(tmp_path, _plan_with(provisioning_business_days=None)))
    assert offer is not None and offer.delivery_days is None
    html = _program_offer_section(_artifact(), "unitrans", "Unitrans", offer, _history())
    assert "business days" not in html


# --- 2. the panel quotes the artifact, and only a measured one --------------


def test_the_panel_states_this_agencys_measured_numbers_and_the_plans_price() -> None:
    artifact = _artifact()
    html = _program_offer_section(artifact, "unitrans", "Unitrans", _offer(), _history())
    overall = artifact["overall"]
    assert f"grade {overall['grade']} ({overall['score']} out of 100)" in html
    assert f"as of the check on {artifact['snapshot_date']}" in html
    assert "<strong>Small bundle:</strong> $17, paid once" in html
    assert "delivered within 3 business days or refunded" in html
    assert "including a monthly refresh" in html
    assert "are free, and they stay free" in html
    assert "buys no influence over grades, methodology, or which agencies are listed" in html


def test_the_panel_lists_only_what_the_report_would_contain() -> None:
    artifact = _artifact()
    artifact["top_fixes"] = []
    html = _program_offer_section(artifact, "unitrans", "Unitrans", _offer(), _history()[:1])
    assert "top fixes" not in html
    assert "score at each check" not in html
    assert "its category scores." in html

    artifact = _artifact()
    assert artifact["top_fixes"], "fixture lost its fixes; this half proves nothing"
    history = _history()
    assert len(history) >= 2, "fixture lost its history; this half proves nothing"
    html = _program_offer_section(artifact, "unitrans", "Unitrans", _offer(), history)
    assert "its category scores, its top fixes, and its score at each check." in html


def _no_grade(a: dict[str, Any]) -> None:
    a["overall"]["grade"] = None


def _unknown_grade(a: dict[str, Any]) -> None:
    a["overall"]["grade"] = "N/A"


def _no_score(a: dict[str, Any]) -> None:
    a["overall"]["score"] = None


def _nan_score(a: dict[str, Any]) -> None:
    a["overall"]["score"] = math.nan


def _bool_score(a: dict[str, Any]) -> None:
    a["overall"]["score"] = True


def _no_overall(a: dict[str, Any]) -> None:
    a["overall"] = None


def _no_date(a: dict[str, Any]) -> None:
    a["snapshot_date"] = ""


_Sabotage = Callable[[dict[str, Any]], None]
_Landed = Callable[[dict[str, Any]], bool]

_SABOTAGE: dict[str, tuple[_Sabotage, _Landed]] = {
    "no-grade": (_no_grade, lambda a: a["overall"]["grade"] is None),
    "unknown-grade": (_unknown_grade, lambda a: a["overall"]["grade"] == "N/A"),
    "no-score": (_no_score, lambda a: a["overall"]["score"] is None),
    "nan-score": (_nan_score, lambda a: math.isnan(a["overall"]["score"])),
    "bool-score": (_bool_score, lambda a: a["overall"]["score"] is True),
    "no-overall": (_no_overall, lambda a: a["overall"] is None),
    "no-date": (_no_date, lambda a: a["snapshot_date"] == ""),
}


@pytest.mark.parametrize("case", sorted(_SABOTAGE))
def test_negative_control_missing_data_offers_nothing(case: str) -> None:
    """Each sabotage must land, then the panel must be absent."""
    sabotage, landed = _SABOTAGE[case]
    control = _program_offer_section(_artifact(), "unitrans", "Unitrans", _offer(), _history())
    assert "program-offer-h" in control, "the unsabotaged control renders no panel"

    artifact = _artifact()
    sabotage(artifact)
    assert landed(artifact), f"{case}: the sabotage did not apply"
    assert _program_offer_section(artifact, "unitrans", "Unitrans", _offer(), _history()) == ""


@pytest.mark.parametrize("case", ["no-grade", "no-score"])
def test_negative_control_full_page_with_missing_grade_names_nothing_paid(case: str) -> None:
    """The whole scorecard page, not just the helper: no panel, no route stop,
    and no /bundle/ link anywhere above the footer."""
    control = _above_footer(_render_agency(_artifact(), _history(), program_offer=_offer()))
    assert "program-offer-h" in control and "/bundle/" in control, (
        "the unsabotaged page has no panel; this control proves nothing"
    )

    sabotage, landed = _SABOTAGE[case]
    artifact = _artifact()
    sabotage(artifact)
    assert landed(artifact), f"{case}: the sabotage did not apply"
    head = _above_footer(_render_agency(artifact, _history(), program_offer=_offer()))
    assert "program-offer" not in head
    assert "/bundle/" not in head
    assert "For programs" not in head


def test_no_offer_no_panel_and_the_page_is_unchanged() -> None:
    """The CLI's standalone scorecard and any render without a sellable plan
    pass no offer. Those pages carry no panel and no route stop for one, and
    they render exactly as the page did before the panel existed."""
    artifact = _artifact()
    without = _render_agency(artifact, _history())
    with_offer = _render_agency(artifact, _history(), program_offer=_offer())
    head = _above_footer(without)
    assert "program-offer" not in head and "/bundle/" not in head
    assert "For programs" not in head
    assert _PANEL_RE.sub("", with_offer).replace(
        '<li><a href="#program-offer-h"><span aria-hidden="true"></span>For programs</a></li>', ""
    ).replace("\n    \n", "\n") == without.replace("\n    \n", "\n")


def test_a_printed_scorecard_drops_the_panel() -> None:
    """A scorecard printed for a board packet carries nothing paid, the same
    rule that already drops the shared footer on paper."""
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


@pytest.mark.parametrize("agency_id", _AGENCIES)
def test_every_link_in_the_rendered_panel_resolves(agency_id: str) -> None:
    head = _above_footer((_GOLDENS / "agency" / agency_id / "index.html").read_text())
    panels = _PANEL_RE.findall(head)
    assert len(panels) == 1, f"{agency_id}: expected one panel, found {len(panels)}"
    hrefs = _HREF_RE.findall(panels[0])
    assert {"/bundle/", "/bundle/sample/", f"/agency/{agency_id}/board/"} <= set(hrefs)
    assert "/how-to-read/#methodology-h" in hrefs
    # The rubric stamp beside the grade links the same methodology anchor.
    assert '<a href="/how-to-read/#methodology-h">Rubric v' in head
    for href in hrefs:
        target = _resolve(href)
        if "#" in href:
            fragment = href.split("#", 1)[1]
            assert f'id="{fragment}"' in target.read_text(), f"{href}: no such anchor"


def test_the_panel_price_is_the_fixture_plan_rendered() -> None:
    offer = load_program_offer(_FIXTURE / "web")
    assert offer is not None, "the golden fixture plan sells nothing; the goldens show no panel"
    for agency_id in _AGENCIES:
        panel = _PANEL_RE.findall((_GOLDENS / "agency" / agency_id / "index.html").read_text())[0]
        assert f"<strong>{offer.label}:</strong> {offer.amount}, paid once" in panel


def test_the_plan_a_live_panel_quotes_is_the_plan_bundle_sells() -> None:
    """The CTA is only honest if /bundle/ sells what the panel quoted. The live
    plan's offer (the one every deployed agency page renders) must appear, label
    and amount, in /bundle/'s own served plan list."""
    offer = load_program_offer(_WEB)
    if offer is None:
        pytest.skip("the live plan sells nothing, so no deployed page renders a panel")
    bundle = (_WEB / "bundle" / "index.html").read_text()
    assert offer.label in bundle
    assert offer.amount in bundle
    assert (_WEB / "bundle" / "sample" / "index.html").is_file()
