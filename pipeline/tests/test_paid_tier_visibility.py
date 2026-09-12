"""Where the paid tier may appear, where it may not, and who checks it.

The program report bundle (ADR 0049) is the only thing on this site that costs
money, and the site's credibility rests on two claims that a visibility change
is the easiest way to break:

1. **Agency-facing scoring is free.** An agency looking at its own grade — on
   its scorecard, in its call brief, on its board one-pager, or in the
   self-contained report it hands a board — must never find a price next to it.
   These tests assert the absence, because an absence is exactly what no
   accessibility scan, golden diff, or link checker will notice going away.
2. **A price lives in web/bundle/plan.json and nowhere else.** A price copied
   into a template is a price that keeps selling after the plan changes.

The positive half is here too: the tier is meant to be *findable*, so the
pages a reader actually lands on must reach it, and the accessibility gate must
cover every page that renders a purchase surface rather than only the two that
had one when the tier launched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from scorecard_pipeline.site_shell import FOOTER_HTML, FOOTER_HTML_WITHOUT_US_TOOLS

# pipeline/tests/test_paid_tier_visibility.py -> parents[2] is the repo root.
_REPO = Path(__file__).resolve().parents[2]
_WEB = _REPO / "web"
_GOLDENS = _REPO / "pipeline" / "tests" / "goldens"

_BUNDLE_HREF = 'href="/bundle/"'
# The sentence /support/, /bundle/, and ADR 0049 all use, verbatim.
_INDEPENDENCE = "buys no influence over grades, methodology, or which agencies are listed"


def _plan() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((_WEB / "bundle" / "plan.json").read_text()))


# --- the tier is findable -------------------------------------------------


def test_the_shared_footer_reaches_the_paid_tier_and_says_it_is_paid() -> None:
    """The footer is the only surface that reaches all ~2,000 pages at once.

    It carries the word "paid" in the link text on purpose: a reader must know
    what is on the other side before they click, not after.
    """
    for footer in (FOOTER_HTML, FOOTER_HTML_WITHOUT_US_TOOLS):
        assert _BUNDLE_HREF in footer
        assert "Board report bundle (paid)" in footer
        assert _INDEPENDENCE in footer


def test_the_footer_carries_no_price() -> None:
    """Prices come from plan.json at view time; the footer is static HTML on
    every page, so it can only ever carry a stale one."""
    products = _plan()["products"]
    assert isinstance(products, dict)
    for product in products.values():
        assert f"${product['price']}" not in FOOTER_HTML


def test_each_landing_surface_reaches_the_paid_tier() -> None:
    """The pages a reader arrives on, or goes to when asking "who is this
    for" and "what does it cost"."""
    for rel in (
        "index.html",  # the home page
        "about/index.html",
        "data/index.html",
        "support/index.html",
    ):
        assert _BUNDLE_HREF in (_WEB / rel).read_text(), rel

    # /tools/ and the program rollups are generated; assert the shipped output.
    assert _BUNDLE_HREF in (_GOLDENS / "tools" / "index.html").read_text()
    assert _BUNDLE_HREF in (_GOLDENS / "program" / "california" / "index.html").read_text()


def test_the_home_page_states_the_tier_as_a_section_not_a_passing_mention() -> None:
    html = (_WEB / "index.html").read_text()
    assert 'id="program-tier-h"' in html
    assert "data-plan-summary" in html
    assert 'src="/src/plan-summary.js"' in html
    assert _INDEPENDENCE in html


# --- and it stays away from a specific agency's grade ----------------------


def test_no_agency_facing_page_names_the_paid_tier_in_its_own_content() -> None:
    """An agency page, its call brief, and its on-site board one-pager are the
    free product. The shared footer reaches them like every other page; nothing
    above it may.

    Split on the footer rather than searching the whole document, or this test
    would pass the moment the footer link were moved into the page body.
    """
    for rel in (
        "agency/unitrans/index.html",
        "agency/unitrans/brief/index.html",
        "agency/unitrans/board/index.html",
        "agency/yolobus/index.html",
        "agency/yolobus/board/index.html",
        "agency/barrie-transit/index.html",
    ):
        html = (_GOLDENS / rel).read_text()
        head, sep, _footer = html.partition('<footer class="site-footer">')
        assert sep, f"{rel}: no shared footer found; the split below proves nothing"
        assert "/bundle/" not in head, (
            f"{rel}: the paid tier is named beside one agency's grade. "
            "Program rollups (/program/<id>/) are the surface for that audience."
        )


def test_the_self_contained_board_report_carries_no_purchase_link() -> None:
    """report.py's document travels off this site: it is emailed, printed, and
    put in board packets, and it is also the thing the bundle sells. A purchase
    link in its methodology footer would advertise the bundle inside the very
    artifact a program bought, to the agency whose grade it carries.

    Deliberate owner-visible policy: the footer is unchanged, and this test is
    the record of that decision rather than an accident waiting to be undone.
    """
    for golden in sorted((_GOLDENS / "report").glob("*.html")):
        text = golden.read_text()
        assert "/bundle/" not in text, golden.name
        assert "buy" not in text.lower(), golden.name


def test_the_printed_one_pager_drops_the_footer_entirely() -> None:
    """On paper the shared footer is not rendered at all, so the board packet
    an agency prints from its own page carries no link to anything paid."""
    css = (_WEB / "src" / "styles.css").read_text()
    print_block = re.search(r"@media print \{(.*?)\n\}", css, re.S)
    assert print_block is not None
    assert re.search(r"\.site-footer[^{]*\{[^}]*display:\s*none", print_block.group(1))


def test_the_program_rollup_names_the_tier_after_the_member_list() -> None:
    """The one generated page family that names the tier in its body. It is a
    group view, read by the people the tier is for, and the offer sits after
    the member list rather than beside any one grade."""
    html = (_GOLDENS / "program" / "california" / "index.html").read_text()
    assert html.index('id="members-h"') < html.index('id="bundle-h"')
    assert _INDEPENDENCE in html
    assert "free, printable board one-pager on its own page" in html


# --- every price comes from plan.json -------------------------------------


def test_no_template_carries_a_price_that_plan_json_owns() -> None:
    """The design rule from ADR 0049: "/bundle/ and /bundle/setup/ read every
    price from web/bundle/plan.json". Every new surface reads it the same way,
    so switching the tier off stays a data change.

    Searched as the rendered amount ("$149"), which is the form that would
    actually mislead a reader, rather than the bare digits.
    """
    products = _plan()["products"]
    assert isinstance(products, dict)
    amounts = [f"${product['price']}" for product in products.values()]
    assert amounts, "plan.json lists no products; this test would pass vacuously"

    searched = [
        *(path for path in _WEB.rglob("*.html") if "/agency/" not in path.as_posix()),
        *(_WEB / "src").glob("*.js"),
        *(_REPO / "pipeline" / "src" / "scorecard_pipeline").glob("*.py"),
    ]
    assert len(searched) > 100, "the file sweep collapsed; it would prove nothing"
    for path in searched:
        text = path.read_text(errors="ignore")
        for amount in amounts:
            assert amount not in text, f"{path}: carries the literal price {amount}"


# --- and the accessibility gate sees what was added -----------------------


def test_the_a11y_gate_covers_every_page_that_renders_a_purchase_surface() -> None:
    """A purchase control rendered after a fetch is invisible to a scan that
    does not wait for it, and a page that is not in the config is not scanned
    at all. Derive the page set from the markup instead of maintaining a list:
    adding a plan summary to a sixth page fails here until the gate covers it.
    """
    config = json.loads((_REPO / ".pa11yci.json").read_text())
    waits = {}
    for entry in config["urls"]:
        url = entry["url"] if isinstance(entry, dict) else entry
        waits[url.replace("http://127.0.0.1:8080", "")] = (
            entry.get("wait", 0) if isinstance(entry, dict) else 0
        )

    rendered_from_plan_json = set()
    for path in _WEB.rglob("*.html"):
        text = path.read_text(errors="ignore")
        if "data-plan-summary" in text or 'id="plan-grid"' in text:
            served = "/" + path.relative_to(_WEB).as_posix().removesuffix("index.html")
            rendered_from_plan_json.add(served.replace("/index.html", "/"))

    assert rendered_from_plan_json >= {"/", "/bundle/", "/support/"}
    for served in sorted(rendered_from_plan_json):
        assert served in waits, f"{served} renders a plan but the axe gate never opens it"
        assert waits[served] >= 1000, (
            f"{served} renders its plan after a fetch; without a wait the scan "
            "examines a page that has no purchase surface on it yet"
        )
