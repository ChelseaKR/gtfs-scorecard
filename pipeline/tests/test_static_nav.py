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


def test_consulting_offer_stays_hidden_from_public_project_surfaces() -> None:
    """The temporary hide covers the live page and repository entry points."""
    public_sources = (
        _REPO / "web" / "support" / "index.html",
        _REPO / "README.md",
        _REPO / "docs" / "support.md",
    )
    for path in public_sources:
        text = path.read_text()
        assert "chelseakr.com/consulting" not in text, path
    support_html = public_sources[0].read_text()
    assert "Professional help" not in support_html
    assert "Implement the fixes with Chelsea" not in support_html


def test_local_fonts_do_not_swap_after_first_paint() -> None:
    """Keep slow font loads from moving the landing page or app shell."""
    for rel in ("index.html", "src/styles.css"):
        source = (_REPO / "web" / rel).read_text()
        faces = re.findall(r"@font-face\s*\{[^}]+\}", source, flags=re.DOTALL)
        assert faces, f"{rel}: expected local font declarations"
        assert all("font-display: optional;" in face for face in faces), (
            f"{rel}: local fonts must keep first-paint metrics stable"
        )


def test_accessible_utility_font_is_used_sitewide() -> None:
    for rel in ("index.html", "src/styles.css"):
        source = (_REPO / "web" / rel).read_text()
        assert 'font-family: "Atkinson Hyperlegible Mono"' in source
        assert "overpass-mono-latin.woff2" not in source

    fonts = _REPO / "web" / "fonts"
    assert (fonts / "atkinson-hyperlegible-mono-latin.woff2").is_file()
    assert (fonts / "OFL-Atkinson-Hyperlegible-Mono.txt").is_file()
    assert not (fonts / "overpass-mono-latin.woff2").exists()


def test_landing_names_both_counts_and_the_shipped_service_scope() -> None:
    html = (_REPO / "web" / "index.html").read_text()

    assert "1,600+" in html
    assert "curated feed records" in html
    assert "1,100+" in html
    assert "published scorecards" in html
    assert "everywhere they publish a feed" not in html

    representative_surfaces = (
        "/agency/unitrans/board/",
        "/program/all/",
        "/app/#/?view=features",
        "/fix/",
        "/check/",
        "/data/",
        "/api/v1/index.json",
        "https://github.com/marketplace/actions/gtfs-scorecard-gate",
        "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/board-report.md",
        "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/mcp.md",
    )
    for href in representative_surfaces:
        assert f'href="{href}"' in html, href


def test_public_surfaces_use_solid_color_grounds() -> None:
    """Public surfaces and data keys use flat fills without CSS gradients."""
    landing = (_REPO / "web" / "index.html").read_text()
    shared = (_REPO / "web" / "src" / "styles.css").read_text()

    assert "gradient(" not in landing
    assert "gradient(" not in shared


def test_gtfs_abbreviation_is_not_underlined() -> None:
    selector = 'abbr[title="General Transit Feed Specification"]'
    for rel in ("index.html", "src/styles.css"):
        source = (_REPO / "web" / rel).read_text()
        rule = re.search(rf"{re.escape(selector)}\s*\{{([^}}]+)\}}", source)
        assert rule is not None, rel
        assert "text-decoration: none;" in rule.group(1), rel


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
