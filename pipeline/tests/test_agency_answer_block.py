"""The agency page's answer block and the order below it (ADR 0085).

Readers land on one scorecard from search. The page now opens with what they
came for: the grade, the feed file, and one primary action ("Watch this
feed"), with the other actions as text links. The measurement notes moved,
unchanged, into "How we measured this" after the evidence. These tests hold:

1. the order of the head, and that the failed-address sentence comes first;
2. the breadcrumb's place level, only when that place page was rendered;
3. exactly one primary action, and the other actions as plain links;
4. the notes below the evidence, with their text unchanged;
5. the "On this page" route, whose every stop exists on the page;
6. the rider line at the start of "About this feed";
7. the two counted controls, and the privacy sentence that names them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.render_site import _RIDER_LINE, _render_agency

_REPO = Path(__file__).resolve().parents[2]
_GOLDENS = Path(__file__).resolve().parent / "goldens" / "agency"
_GOLDEN_IDS = sorted(p.parent.name for p in _GOLDENS.glob("*/index.html"))
_MDB_COPY = "https://files.mobilitydatabase.org/mdb-615/latest.zip"
_PRIVACY_SENTENCE = (
    "When you press Watch this feed or Copy URL on a scorecard, the cookieless counter "
    "records that the button was pressed."
)


def _artifact(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "agency": {"id": "demo-transit", "name": "Demo Transit"},
        "overall": {"grade": "D", "score": 63.5},
        "snapshot_date": "2026-11-09",
        "categories": {"realtime": {"status": "not_yet_measured"}},
        "feed": {"static_url": "https://feeds.example.org/demo/gtfs.zip"},
    }
    base.update(overrides)
    return base


def _record(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"id": "demo-transit", "country": "US", "state": "North Carolina"}
    base.update(overrides)
    return base


def _visible(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _head(html: str) -> str:
    start = html.index('<div class="report-head">')
    return html[start : html.index('<nav class="report-route"', start)]


def _main(html: str) -> str:
    return html[html.index("<main") : html.index("</main>")]


# --- 1. the order of the head ---------------------------------------------------------


def test_the_head_reads_crumb_grade_feed_file_watch_then_links() -> None:
    html = _render_agency(_artifact(), dir_record=_record())
    order = [
        'class="breadcrumb"',
        '<div class="answer-block">',
        'class="board-title"',
        'class="score-big"',
        '<section class="feed-card"',
        '<p class="watch-line">',
        '<nav class="report-actions"',
        '<nav class="report-route"',
        '<div class="report-content">',
    ]
    positions = [html.index(marker) for marker in order]
    assert positions == sorted(positions)


def test_a_failed_address_puts_its_sentence_first_and_its_status_on_the_card() -> None:
    artifact = _artifact(fetch={"source": "mirror", "final_url": _MDB_COPY})
    html = _render_agency(artifact, dir_record=_record(), liveness={"status": 404})
    head = _head(html)
    assert head.index('<p class="feed-help">') < head.index('class="breadcrumb"')
    card = re.search(r'<section class="feed-card".*?</section>', html, re.S)
    assert card is not None
    assert '<p class="feed-status">Failed at last check (HTTP 404)' in card.group(0)
    assert f'<a href="{_MDB_COPY}">Newest saved copy</a>' in card.group(0)


@pytest.mark.parametrize("record", [None, {"status": 200}, {"status": 503}])
def test_a_working_or_passing_address_shows_no_failed_status(
    record: dict[str, Any] | None,
) -> None:
    artifact = _artifact(fetch={"source": "mirror", "final_url": _MDB_COPY})
    html = _render_agency(artifact, dir_record=_record(), liveness=record)
    assert "Failed at last check" not in html
    assert "Newest saved copy" not in html


def test_the_duplicate_backlink_is_gone() -> None:
    html = _render_agency(_artifact(), dir_record=_record())
    assert 'class="backlink"' not in _main(html)


# --- 2. the breadcrumb's place level ----------------------------------------------------


def test_the_crumb_names_the_state_page_when_it_was_rendered() -> None:
    html = _render_agency(_artifact(), dir_record=_record(), program_ids={"north-carolina"})
    crumb = re.search(r'<nav class="breadcrumb".*?</nav>', html, re.S)
    assert crumb is not None
    assert _visible(crumb.group(0)) == "Home Agencies North Carolina Demo Transit"
    assert 'href="/agencies/"' in crumb.group(0)
    assert 'href="/program/north-carolina/"' in crumb.group(0)
    assert crumb.group(0).count('itemprop="position"') == 4


def test_the_crumb_names_the_country_page_outside_the_united_states() -> None:
    record = {"id": "demo-transit", "country": "CA"}
    html = _render_agency(_artifact(), dir_record=record, program_ids={"country-ca"})
    crumb = re.search(r'<nav class="breadcrumb".*?</nav>', html, re.S)
    assert crumb is not None
    assert 'href="/program/country-ca/"' in crumb.group(0)
    assert _visible(crumb.group(0)) == "Home Agencies Canada Demo Transit"


def test_no_place_level_when_that_page_was_not_rendered() -> None:
    html = _render_agency(_artifact(), dir_record=_record(), program_ids=set())
    crumb = re.search(r'<nav class="breadcrumb".*?</nav>', html, re.S)
    assert crumb is not None
    assert "/program/" not in crumb.group(0)
    assert _visible(crumb.group(0)) == "Home Agencies Demo Transit"


# --- 3. one primary action ------------------------------------------------------------


@pytest.mark.parametrize("agency_id", _GOLDEN_IDS)
def test_watch_this_feed_is_the_only_primary_action(agency_id: str) -> None:
    main = _main((_GOLDENS / agency_id / "index.html").read_text())
    primaries = re.findall(r'<a [^>]*class="[^"]*\b(?:button|report-action)-primary\b[^>]*>', main)
    assert len(primaries) == 1
    assert f'href="/subscribe.html?agency={agency_id}"' in primaries[0]
    assert "report-action " not in main and 'class="report-action"' not in main


def test_the_other_actions_are_text_links_in_one_labeled_row() -> None:
    html = _render_agency(_artifact(), dir_record=_record(), has_fixlog=True)
    row = re.search(
        r'<nav class="report-actions" aria-label="More for this agency">.*?</nav>', html
    )
    assert row is not None
    labels = re.findall(r"<a [^>]*>([^<]+)</a>", row.group(0))
    assert labels == [
        "Correct this listing",
        "Board one-pager",
        "Call brief",
        "Compare",
        "Clearance log",
    ]
    assert "Send fixes" not in html


def test_no_clearance_log_link_without_a_log() -> None:
    html = _render_agency(_artifact(), dir_record=_record(), has_fixlog=False)
    assert "/fixes/" not in _head(html)


# --- 4. the notes below the evidence, text unchanged --------------------------------


@pytest.mark.parametrize("agency_id", _GOLDEN_IDS)
def test_the_measurement_notes_sit_after_the_evidence(agency_id: str) -> None:
    html = (_GOLDENS / agency_id / "index.html").read_text()
    section = re.search(
        r'<section aria-labelledby="measured-h" class="measured">.*?</section>', html, re.S
    )
    assert section is not None
    assert html.index('id="findings-h"') < section.start()
    body = section.group(0)
    assert '<h2 class="section-title" id="measured-h">How we measured this</h2>' in body
    assert 'class="disclaimer"' in body
    assert "Not an official compliance determination from any transit program." in _visible(body)
    head = _head(html)
    for note in ("monitoring-note", "confidence-note", "disclaimer", "not-fetched"):
        assert note not in head, note
    assert html.count('class="disclaimer"') == 1


def test_the_grade_card_keeps_the_partial_qualifier_and_the_provenance() -> None:
    """ADR 0030: what was not measured is said in the grade card, not lower down."""
    artifact = _artifact(categories={"freshness": {"status": "not_measured"}})
    head = _head(_render_agency(artifact, dir_record=_record()))
    assert 'class="board-sub"' in head


# --- 5. "On this page" --------------------------------------------------------------------


@pytest.mark.parametrize("agency_id", _GOLDEN_IDS)
def test_every_stop_on_this_page_exists(agency_id: str) -> None:
    html = (_GOLDENS / agency_id / "index.html").read_text()
    route = re.search(r'<nav class="report-route".*?</nav>', html, re.S)
    assert route is not None
    assert 'aria-labelledby="report-route-h"' in route.group(0)
    assert '<p class="report-route-title" id="report-route-h">On this page</p>' in route.group(0)
    assert "Report route" not in html and "Sections on this page" not in html
    targets = re.findall(r'href="#([^"]+)"', route.group(0))
    assert "measured-h" in targets and "about-feed-h" in targets
    for target in targets:
        assert f'id="{target}"' in html, target


@pytest.mark.parametrize("agency_id", _GOLDEN_IDS)
def test_every_in_page_link_on_the_scorecard_has_a_target(agency_id: str) -> None:
    html = (_GOLDENS / agency_id / "index.html").read_text()
    main = _main(html)
    for target in set(re.findall(r'href="#([A-Za-z][^"=]*)"', main)):
        assert f'id="{target}"' in html, target


# --- 6. the rider line ------------------------------------------------------------------


def test_the_rider_line_is_the_approved_sentence() -> None:
    assert _RIDER_LINE == (
        "Looking for times or routes? This page checks the data file that trip planners "
        "use. For schedules, use the agency's own website or a trip planner."
    )


@pytest.mark.parametrize("agency_id", _GOLDEN_IDS)
def test_the_rider_line_opens_about_this_feed_after_the_fixes(agency_id: str) -> None:
    html = (_GOLDENS / agency_id / "index.html").read_text()
    about = re.search(r'<section aria-labelledby="about-feed-h".*?</section>', html, re.S)
    assert about is not None
    assert html.index('id="fixes-h"') < about.start()
    first = re.search(r'</h2><p class="rider-line">([^<]*)</p>', about.group(0))
    assert first is not None
    assert first.group(1).replace("&#x27;", "'") == _RIDER_LINE
    assert html.count('class="rider-line"') == 1


def test_the_rider_line_appears_even_when_nothing_about_the_feed_was_measured() -> None:
    html = _render_agency(_artifact(), dir_record=_record())
    assert 'id="about-feed-h"' in html
    assert 'class="rider-line"' in html
    assert (
        'class="page-lede"' not in html.partition('id="about-feed-h"')[2].partition("</section>")[0]
    )


# --- 7. the counted controls and the privacy sentence -----------------------------------


@pytest.mark.parametrize("agency_id", _GOLDEN_IDS)
def test_the_scorecard_counts_only_watch_and_copy_url(agency_id: str) -> None:
    main = _main((_GOLDENS / agency_id / "index.html").read_text())
    names = re.findall(r'data-measure="([^"]+)"', main)
    assert sorted(names) == ["agency_copy_url_click", "agency_watch_click"]


def test_copy_url_is_hidden_until_the_clipboard_is_there() -> None:
    html = _render_agency(_artifact(), dir_record=_record())
    button = re.search(r'<button [^>]*class="copy-url"[^>]*>Copy URL</button>', html)
    assert button is not None
    assert " hidden " in button.group(0)
    assert "if(!navigator.clipboard){return;}b.hidden=false;" in html


def test_no_feed_card_and_no_copy_script_without_a_public_source() -> None:
    html = _render_agency(_artifact(feed={"static_url": "local.zip"}), dir_record=_record())
    assert 'class="feed-card"' not in html
    assert "copy-url" not in html


def test_the_privacy_statement_names_the_two_counted_presses() -> None:
    about = (_REPO / "web" / "about" / "index.html").read_text()
    privacy = about[
        about.index('id="privacy"') : about.index("</section>", about.index('id="privacy"'))
    ]
    assert _PRIVACY_SENTENCE in " ".join(privacy.split())


def test_the_answer_block_has_its_styles() -> None:
    css = (_REPO / "web" / "src" / "styles.css").read_text()
    for selector in (".answer-block {", ".feed-card {", ".copy-url {", ".copy-url[hidden]"):
        assert selector in css, selector


# --- 8. what the grade weighs, under the grade --------------------------------------------


@pytest.mark.parametrize("agency_id", _GOLDEN_IDS)
def test_the_grade_card_says_what_the_grade_weighs(agency_id: str) -> None:
    html = (_GOLDENS / agency_id / "index.html").read_text()
    hero = re.search(r'<div class="board-hero".*?</div></div>\n', html, re.S)
    assert hero is not None
    line = re.search(r'<p class="grade-explainer">.*?</p>', hero.group(0))
    assert line is not None, "the sentence is not inside the grade card"
    assert hero.group(0).index('class="score-big"') < line.start()
    assert _visible(line.group(0)) == (
        "The grade is not a count of validator errors. It also weighs freshness and "
        "rider information. How the grade works"
    )
    assert '<a href="/how-to-read/#methodology-h">How the grade works</a>' in line.group(0)
    assert html.count('class="grade-explainer"') == 1


def test_the_methodology_anchor_the_grade_card_links_exists() -> None:
    how_to_read = (_GOLDENS.parent / "how-to-read" / "index.html").read_text()
    assert 'id="methodology-h"' in how_to_read


def test_the_grade_card_link_is_legible_on_the_dark_board() -> None:
    css = (_REPO / "web" / "src" / "styles.css").read_text()
    assert ".grade-explainer a { color: #f4f6f0;" in css
    assert ".grade-explainer a:focus-visible { outline-color: var(--amber); }" in css


def test_watch_and_the_links_sit_beside_the_grade_not_under_it() -> None:
    """On a wide screen the side column holds the feed file, Watch this feed and
    the other links, so they are above the fold with the grade (ADR 0085)."""
    html = _render_agency(_artifact(), dir_record=_record())
    side = re.search(r'<div class="answer-side">.*?</nav>\s*</div>\s*</div>', html, re.S)
    assert side is not None
    for marker in (
        '<section class="feed-card"',
        '<p class="watch-line">',
        'class="report-actions"',
    ):
        assert marker in side.group(0), marker
    css = (_REPO / "web" / "src" / "styles.css").read_text()
    assert ".answer-side {" in css
