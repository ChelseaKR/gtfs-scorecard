"""The alerts and About pages in the 2026-11 information architecture.

Both pages lose their loose backlinks for a breadcrumb (Home > Feed alerts,
Home > About). The alerts form asks for the agency before the email, so a
reader arriving from "Watch this feed" meets their choice first. About gains
"Who it is for" and "How the grade works", which link the methodology rather
than repeat it. The privacy anchors every footer links stay where they are.
"""

from __future__ import annotations

import re
from pathlib import Path

_WEB = Path(__file__).resolve().parents[2] / "web"
_ALERTS = (_WEB / "subscribe.html").read_text()
_ABOUT = (_WEB / "about" / "index.html").read_text()
_SUBSCRIBE_JS = (_WEB / "src" / "subscribe.js").read_text()


def _visible(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _main(html: str) -> str:
    return html[html.index("<main") : html.index("</main>")]


def _crumb(html: str) -> str:
    crumb = re.search(r'<nav class="breadcrumb".*?</nav>', _main(html), re.S)
    assert crumb is not None
    return crumb.group(0)


def test_both_pages_trade_the_backlink_for_a_breadcrumb() -> None:
    assert _visible(_crumb(_ALERTS)) == "Home Feed alerts"
    assert _visible(_crumb(_ABOUT)) == "Home About"
    for page in (_ALERTS, _ABOUT):
        main = _main(page)
        assert 'class="backlink"' not in main
        assert main.index('class="breadcrumb"') < main.index("<h1")
        assert 'itemtype="https://schema.org/BreadcrumbList"' in main


def test_the_alerts_form_asks_for_the_agency_before_the_email() -> None:
    form = _ALERTS[_ALERTS.index('<form id="subscribe-form"') : _ALERTS.index("</form>")]
    assert form.index('id="agency"') < form.index('id="email"') < form.index("<legend>")


def test_the_chosen_hint_is_the_approved_sentence_and_lives_in_the_page() -> None:
    assert (
        'data-hint-chosen="Chosen from the scorecard you came from. Type to change it, or '
        'choose All agencies."' in _ALERTS
    )
    # The script carries no copy of its own; it reads the page's words.
    assert 'getAttribute("data-hint-chosen")' in _SUBSCRIBE_JS
    assert "Chosen from the scorecard" not in _SUBSCRIBE_JS
    assert 'src="src/subscribe.js?v=20261121-agency-first"' in _ALERTS


def test_about_says_who_it_is_for_in_three_lines() -> None:
    section = re.search(r'<section aria-labelledby="for-whom-h">.*?</section>', _ABOUT, re.S)
    assert section is not None
    items = [
        " ".join(re.sub(r"<[^>]+>", "", li).split())
        for li in re.findall(r"<li>.*?</li>", section.group(0), re.S)
    ]
    assert items == [
        "Agency staff: your grade, your fixes, and a free alert.",
        "Program staff and consultants: every agency you support on one page.",
        "Data users: feed URLs, the open dataset and the API.",
    ]


def test_about_says_how_the_grade_works_and_links_the_method() -> None:
    section = re.search(r'<section aria-labelledby="grade-works-h">.*?</section>', _ABOUT, re.S)
    assert section is not None
    text = _visible(section.group(0))
    assert text.startswith(
        "How the grade works Four categories, weighted, from the canonical MobilityData "
        "validator plus freshness, rider-information and realtime checks. Unmeasured "
        "categories are left out, not scored as zero."
    )
    assert 'href="/how-to-read/#methodology-h"' in section.group(0)
    assert 'href="/status/"' in section.group(0)
    assert _ABOUT.index('id="grade-works-h"') < _ABOUT.index('id="why-h"')


def test_the_privacy_anchors_the_footer_links_are_still_there() -> None:
    for anchor in ('id="privacy"', 'id="privacy-opt-out"'):
        assert anchor in _ABOUT
