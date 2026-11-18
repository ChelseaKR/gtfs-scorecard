"""ADR 0081: search titles for /program/all/, /gtfs-validator/ and NTD state pages.

Each page now names what its searchers type: a GTFS feed list, the GTFS
validator, and "<state> transit GTFS for NTD". Guarded here: the approved
wording, the length bounds at the extremes, counts taken from the page's own
payload, the other rollups left alone, and one plain "GTFS validator" link to
the guide from each of the four pages that competed with it for that query.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.ntd import state_pages
from scorecard_pipeline.pages_tools import _render_check_page
from scorecard_pipeline.render_site import (
    _DESC_MAX,
    _TITLE_MAX,
    VALIDATOR_PAGE_DESCRIPTION,
    _all_rollup_search_copy,
    _ntd_state_title,
    _render_focus_page,
    _render_guide,
    _render_ntd_state_page,
    _render_rollup,
)

_REPO = Path(__file__).resolve().parents[2]


class _Page(HTMLParser):
    """A page's title, meta description, links (href, text) and visible text."""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.links: list[tuple[str, str]] = []
        self.text: list[str] = []
        self._in_title = False
        self._href: str | None = None
        self._link_text: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and attr.get("name") == "description":
            self.description = str(attr.get("content") or "")
        elif tag in {"script", "style"}:
            self._skip += 1
        elif tag == "a":
            self._href = str(attr.get("href") or "")
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag in {"script", "style"}:
            self._skip -= 1
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._link_text).split())))
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.text.append(data)
            if self._href is not None:
                self._link_text.append(data)

    @property
    def words(self) -> str:
        return " ".join("".join(self.text).split())


def _page(html: str) -> _Page:
    page = _Page()
    page.feed(html)
    return page


def _head(html: str) -> tuple[str, str]:
    page = _page(html)
    return page.title, page.description


def _guide_links(html: str) -> list[str]:
    """The text of every link to the validator guide that names the query."""
    return [
        text
        for href, text in _page(html).links
        if href == "/gtfs-validator/" and "GTFS validator" in text
    ]


def _rollup(rid: str, name: str, count: int, attention: int) -> dict[str, Any]:
    return {
        "rollup": {"id": rid, "name": name},
        "agency_count": count,
        "average_score": None,
        "grade_distribution": {},
        "comparison": {"eligible_count": 0},
        "needs_attention": attention,
        "expired": {"lapsed": 0, "stale": 0, "total": 0},
        "shapes_readiness": {
            "ready": 0,
            "at_risk": 0,
            "not_ready": 0,
            "not_measured": 1,
            "total": 1,
        },
        "members": [
            {"id": "m", "name": "M", "grade": "C", "score": 70.0, "snapshot_date": "2026-10-03"}
        ],
        "common_fixes": [],
    }


# --- /program/all/ ---------------------------------------------------------


def test_feed_list_copy_matches_the_approved_wording() -> None:
    title, desc = _all_rollup_search_copy(2493, 1076)
    assert title == "GTFS feed list: quality grades for 2,493 transit feeds"
    assert desc == (
        "All 2,493 tracked transit GTFS feeds in one list, each with its quality grade; "
        "1,076 need attention, plus the fixes they share."
    )


@pytest.mark.parametrize(("count", "attention"), [(1, 0), (1, 1), (2, 2), (99_999, 99_999)])
def test_feed_list_copy_fits_the_bounds_and_agrees_in_number(count: int, attention: int) -> None:
    title, desc = _all_rollup_search_copy(count, attention)
    assert 15 <= len(title) <= _TITLE_MAX
    assert 50 <= len(desc) <= _DESC_MAX
    if count == 1:
        assert "1 transit feed" in title and "transit feeds" not in title
    if attention == 0:
        assert "none need attention" in desc
    if attention == 1:
        assert "1 needs attention" in desc


def test_the_all_rollup_page_states_its_own_counts() -> None:
    html = _render_rollup(_rollup("all", "All tracked agencies", 2493, 1076))
    title, desc = _head(html)
    assert title == "GTFS feed list: quality grades for 2,493 transit feeds"
    assert "1,076 need attention" in desc
    # The page itself shows the same two numbers the snippet repeats.
    words = _page(html).words
    assert "2493 feed scorecards" in words and "1076 need attention" in words


def test_state_and_country_rollups_keep_their_titles() -> None:
    html = _render_rollup(_rollup("ohio", "Ohio agencies", 4, 3))
    title, desc = _head(html)
    assert title == "Ohio agencies: GTFS quality scores — GTFS Scorecard"
    assert desc.startswith("Ohio agencies: GTFS grades for 4 transit feeds")
    # Negative control: the feed-list title is only for the "all" rollup.
    assert "GTFS feed list" not in title and "GTFS feed list" not in desc


# --- /gtfs-validator/ ------------------------------------------------------


def test_validator_guide_title_is_the_documents_h1() -> None:
    doc = (_REPO / "docs" / "gtfs-validator.md").read_text()
    headings = [line[2:] for line in doc.splitlines() if line.startswith("# ")]
    assert headings == ["GTFS validator: check a feed and read the results"]
    assert len(headings[0]) <= _TITLE_MAX


def test_validator_guide_description_matches_the_approved_wording() -> None:
    assert VALIDATOR_PAGE_DESCRIPTION == (
        "How the MobilityData GTFS validator checks a feed, what its notices mean in plain "
        "English, and what the scorecard grade adds."
    )
    assert 50 <= len(VALIDATOR_PAGE_DESCRIPTION) <= _DESC_MAX


@pytest.mark.parametrize(
    "page",
    ["about", "how-to-read", "check", "focus", "home"],
)
def test_competing_pages_link_the_guide_with_the_query_words(page: str) -> None:
    if page == "about":
        html = (_REPO / "web" / "about" / "index.html").read_text()
    elif page == "home":
        html = (_REPO / "web" / "index.html").read_text()
    elif page == "how-to-read":
        html = _render_guide()
    elif page == "check":
        html = _render_check_page()
    else:
        html = _render_focus_page({}, {})
    assert len(_guide_links(html)) == 1, page


def test_negative_control_an_anchor_without_the_words_is_not_counted() -> None:
    old_home = '<p>Read <a href="/gtfs-validator/">how the scorecard uses it</a>.</p>'
    assert _guide_links(old_home) == []
    elsewhere = '<p><a href="/check/">GTFS validator</a></p>'
    assert _guide_links(elsewhere) == []


# --- NTD state pages -------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("Texas", "Texas transit GTFS for NTD: shapes.txt and agency_id"),
        ("North Carolina", "North Carolina transit GTFS for NTD: shapes.txt check"),
        ("District of Columbia", "District of Columbia transit GTFS for NTD: shapes.txt check"),
    ],
)
def test_ntd_state_title_names_the_search(state: str, expected: str) -> None:
    assert _ntd_state_title(state) == expected
    assert len(expected) <= _TITLE_MAX


def test_an_unusually_long_place_name_still_fits() -> None:
    title = _ntd_state_title("Commonwealth of the Northern Mariana Islands and Elsewhere")
    assert len(title) <= _TITLE_MAX
    assert title.endswith(" transit GTFS for NTD")


def _five(state: str) -> list[dict[str, Any]]:
    return [
        {
            "agency": {"id": f"t{i}", "name": f"Agency {i}", "state": state},
            "feed": {"reachable": True, "static_url": "https://ex.org/g.zip"},
            "categories": {
                "correctness": {"status": "measured", "findings": []},
                "freshness": {"status": "measured", "details": {"days_until_expiry": 90}},
            },
            "ntd_id_alignment": {"status": "unknown", "detail": "", "feed_agency_ids": ["x"]},
            "shapes_readiness": {"total_trips": 10, "trips_with_shape": 10},
        }
        for i in range(5)
    ]


def test_ntd_state_page_renders_the_new_title() -> None:
    rows = state_pages(_five("Texas"))["Texas"]
    title, _desc = _head(_render_ntd_state_page("Texas", rows))
    assert title == "Texas transit GTFS for NTD: shapes.txt and agency_id"
