"""The agency directory: current feeds first, search, and browse by place.

Before the 2026-11 information architecture (ADR 0085, decision D4), pages 1
to 4 of /agencies/ held nothing but expired feeds, so a first-time visitor met
80 lapsed feeds before a current one. These tests hold:

1. current feeds come first, A to Z, and expired feeds follow in their own
   section, on the same page chain (same URLs, same page count);
2. a single "Jump to expired feeds" link with the total, pointing at the page
   where they start;
3. "Browse by place" links only the state and country pages that exist;
4. the search reuses the home page's form and wording and loads no script
   before the first paint.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.render_site import (
    _agency_index_href,
    _directory_places,
    _published_directory_places,
    _render_agency_index,
)

_GOLDEN = Path(__file__).resolve().parent / "goldens" / "agencies" / "index.html"


def _row(days: int) -> dict[str, Any]:
    return {"grade": "C", "score": 70.0, "date": "2026-11-20", "days_until_expiry": days}


def _index(current: int, lapsed: int) -> dict[str, Any]:
    agencies: dict[str, Any] = {}
    for n in range(current):
        agencies[f"live-{n:03d}"] = {"name": f"Live {n:03d}", "history": [_row(60)]}
    for n in range(lapsed):
        # Expired 10 + n days ago: "recently lapsed".
        agencies[f"gone-{n:03d}"] = {"name": f"Gone {n:03d}", "history": [_row(-10 - n)]}
    return {"agencies": agencies}


def _ids(html: str) -> list[str]:
    return re.findall(r'href="/agency/([a-z]+-\d{3})/"', html)


def _pages(index: dict[str, Any], size: int) -> list[str]:
    total = len(index["agencies"])
    return [
        _render_agency_index(index, {}, page=page, page_size=size)
        for page in range(1, math.ceil(total / size) + 1)
    ]


# --- 1. current first, expired last, same chain -----------------------------------------


def test_current_feeds_come_first_and_expired_feeds_last() -> None:
    pages = _pages(_index(current=5, lapsed=4), size=3)
    assert len(pages) == 3, "the page count is the total over the page size, as before"
    order = [agency_id for html in pages for agency_id in _ids(html)]
    assert order[:5] == [f"live-{n:03d}" for n in range(5)]
    assert sorted(order[5:]) == [f"gone-{n:03d}" for n in range(4)]
    assert len(order) == len(set(order)) == 9


def test_on_a_shared_page_the_current_section_precedes_the_expired_one() -> None:
    html = _render_agency_index(_index(current=2, lapsed=2), {}, page=1, page_size=10)
    assert html.index('id="current"') < html.index('id="expired"')
    assert '<h2 class="section-title" id="current">Current feeds, A to Z ' in html
    assert "Current and upcoming service" not in html


def test_the_page_urls_do_not_change() -> None:
    pages = _pages(_index(current=5, lapsed=4), size=3)
    canonicals = [re.search(r'<link rel="canonical" href="([^"]+)">', p).group(1) for p in pages]  # type: ignore[union-attr]
    assert canonicals == [
        "https://gtfsscorecard.org/agencies/",
        "https://gtfsscorecard.org/agencies/page/2/",
        "https://gtfsscorecard.org/agencies/page/3/",
    ]


# --- 2. one jump link to the expired feeds ------------------------------------------------


def test_the_jump_link_names_the_total_and_the_page_where_expired_feeds_start() -> None:
    pages = _pages(_index(current=5, lapsed=4), size=3)
    # Current feeds fill page 1 and two rows of page 2; expired start on page 2.
    jump = re.search(r'<nav class="grade-jump" aria-label="Jump to section">.*?</nav>', pages[0])
    assert jump is not None
    assert f'href="{_agency_index_href(2)}#expired"' in jump.group(0)
    assert ">Jump to expired feeds (4)</a>" in jump.group(0)
    for html in pages[1:]:
        assert '<a href="#expired">Jump to expired feeds (4)</a>' in html
        assert 'id="expired"' in html


def test_no_jump_link_without_expired_feeds() -> None:
    html = _render_agency_index(_index(current=3, lapsed=0), {}, page=1, page_size=10)
    assert "Jump to expired feeds" not in html
    assert 'id="expired"' not in html


def test_every_in_page_link_on_the_directory_golden_has_a_target() -> None:
    html = _GOLDEN.read_text()
    for target in set(re.findall(r'href="#([^"]+)"', html)):
        assert f'id="{target}"' in html, target


# --- 3. browse by place ----------------------------------------------------------------------


_ROLLUPS = [
    {"id": "all", "name": "All tracked agencies"},
    {"id": "california", "name": "California agencies"},
    {"id": "new-mexico", "name": "New Mexico agencies"},
    {"id": "yolo-county", "name": "Yolo County"},
    {"id": "country-ca", "name": "Canada"},
    {"id": "country-au", "name": "Australia"},
    {"id": "oregon", "name": "Oregon agencies"},
]


def test_places_are_the_written_state_and_country_pages_only() -> None:
    written = {"all", "california", "new-mexico", "yolo-county", "country-ca", "country-au"}
    states, countries = _directory_places(_ROLLUPS, written)
    assert states == [("california", "California"), ("new-mexico", "New Mexico")]
    assert countries == [("country-au", "Australia"), ("country-ca", "Canada")]


def test_places_read_only_rollups_whose_payload_exists(tmp_path: Path) -> None:
    rollups = tmp_path / "rollups"
    rollups.mkdir()
    (rollups / "index.json").write_text(
        '{"rollups": [{"id": "california", "name": "California agencies"},'
        ' {"id": "oregon", "name": "Oregon agencies"}]}'
    )
    (rollups / "california.json").write_text("{}")
    assert _published_directory_places(tmp_path) == ([("california", "California")], [])
    assert _published_directory_places(tmp_path / "missing") == ([], [])


def test_browse_by_place_links_each_place_page() -> None:
    places = ([("california", "California")], [("country-ca", "Canada")])
    html = _render_agency_index(_index(2, 0), {}, page=1, page_size=10, places=places)
    block = re.search(r'<section class="browse-place".*?</section>', html, re.S)
    assert block is not None
    text = " ".join(re.sub(r"<[^>]+>", " ", block.group(0)).split())
    assert text == (
        "Browse by place United States California Other countries Canada "
        "Countries without their own page are in the full list below."
    )
    assert '<a href="/program/california/">California</a>' in block.group(0)
    assert '<a href="/program/country-ca/">Canada</a>' in block.group(0)
    assert html.index('id="browse-place-h"') < html.index('id="current"')


def test_no_place_block_without_places() -> None:
    html = _render_agency_index(_index(2, 0), {}, page=1, page_size=10)
    assert "Browse by place" not in html


# --- 4. the search -------------------------------------------------------------------------------


@pytest.mark.parametrize("page", [1, 2])
def test_every_directory_page_opens_with_the_search(page: int) -> None:
    html = _render_agency_index(_index(3, 2), {}, page=page, page_size=3)
    form = re.search(r'<form class="directory-search".*?</form>', html, re.S)
    assert form is not None
    assert 'action="/app/" method="get" role="search"' in form.group(0)
    assert '<label for="directory-search-input">Find a published feed</label>' in form.group(0)
    assert html.index("<h1") < form.start() < html.index('class="agency-list"')
    # The picker script is fetched on focus, never with the page.
    assert '<script src="/src/agency-combobox.js' not in html
    assert "f.addEventListener('focusin'" in html


def test_the_directory_breadcrumb_reads_agencies() -> None:
    html = _GOLDEN.read_text()
    crumb = re.search(r'<nav class="breadcrumb".*?</nav>', html, re.S)
    assert crumb is not None
    assert " ".join(re.sub(r"<[^>]+>", " ", crumb.group(0)).split()) == "Home Agencies"
