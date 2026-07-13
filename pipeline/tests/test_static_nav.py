"""The hand-authored static pages must carry the same primary nav as the
generated header, so the wayfinding bar cannot drift between them (it did once:
the static pages were missing three sections, then the new /routes/ stop). This
guards sync_static_navs / _NAV_ITEMS as the single source of truth."""

from __future__ import annotations

import json
import re
from pathlib import Path

from scorecard_pipeline.site_shell import (
    _NAV_ITEMS,
    _NAV_STOPS_RE,
    STATIC_NAV_PAGES,
    _nav_stops_html,
)

# The real repo (not the per-test tmp root that conftest points artifacts_dir at):
# this file is pipeline/tests/test_static_nav.py, so parents[2] is the repo root.
_REPO = Path(__file__).resolve().parents[2]


def test_static_pages_nav_matches_canonical() -> None:
    web = _REPO / "web"
    for rel, active in STATIC_NAV_PAGES.items():
        html = (web / rel).read_text()
        match = _NAV_STOPS_RE.search(html)
        assert match is not None, f"{rel}: no nav-stops block found"
        assert match.group(0) == _nav_stops_html(active), (
            f"{rel}: primary nav drifted from _NAV_ITEMS; run `make sync-static-nav`"
        )


def test_active_section_targets_a_real_nav_item() -> None:
    # An active section, when set, must be one of the canonical hrefs (else the
    # static page would mark a non-existent stop and never highlight it).
    hrefs = {href for _, href in _NAV_ITEMS}
    for rel, active in STATIC_NAV_PAGES.items():
        assert active is None or active in hrefs, f"{rel}: active {active!r} not in _NAV_ITEMS"


def test_hand_authored_pages_do_not_block_on_remote_fonts() -> None:
    pages = set(STATIC_NAV_PAGES) | {"concept/index.html"}
    for rel in pages:
        html = (_REPO / "web" / rel).read_text()
        assert "fonts.googleapis.com" not in html, rel
        assert "fonts.gstatic.com" not in html, rel


def test_interactive_app_consolidates_to_the_crawlable_directory() -> None:
    html = (_REPO / "web" / "app" / "index.html").read_text()

    assert '<link rel="canonical" href="https://gtfsscorecard.org/agencies/">' in html


def test_open_data_page_publishes_data_catalog_jsonld() -> None:
    html = (_REPO / "web" / "data" / "index.html").read_text()
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html)

    assert match is not None
    data = json.loads(match.group(1))
    assert data["@type"] == "DataCatalog"
    assert data["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert "worldwide" in data["description"]
    assert "United States and Canada" not in data["description"]
    assert data["dataset"][0]["license"] == data["license"]
    assert data["dataset"][0]["distribution"][0]["contentUrl"].endswith("dataset.json")

    assert "United States NTD readiness" in html
    assert "analyze the whole country" not in html
    assert "does not\n      relicense or redistribute the underlying GTFS files" in html
    assert "feed records in the current file" in html
    assert "agencies in the current file" not in html
