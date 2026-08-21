"""The hand-authored static pages must carry the same primary nav as the
generated header, so the wayfinding bar cannot drift between them (it did once:
the static pages were missing three sections, then the new /routes/ stop). This
guards sync_static_navs / _NAV_ITEMS as the single source of truth."""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path

from scorecard_pipeline.site_shell import (
    _NAV_ITEMS,
    _NAV_STOPS_RE,
    STATIC_NAV_PAGES,
    _nav_stops_html,
    static_page_path,
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
        assert match.group(0) == _nav_stops_html(active, path=static_page_path(rel)), (
            f"{rel}: primary nav drifted from _NAV_ITEMS; run `make sync-static-nav`"
        )


def test_a_section_hub_is_never_announced_as_the_current_page() -> None:
    """A filled stop that is not this page is the current item, not the page.

    ARIA 1.2 reserves ``page`` for the current page within a set of pages.
    ``/support/`` fills the About stop because it sits in that section, and
    announcing that link as the current page tells a screen-reader user they
    are already on a link that navigates somewhere else.
    """
    for rel, active in STATIC_NAV_PAGES.items():
        if active is None or active == static_page_path(rel):
            continue
        nav = _NAV_STOPS_RE.search((_REPO / "web" / rel).read_text())
        assert nav is not None, rel
        assert 'aria-current="page"' not in nav.group(0), rel
        assert f'href="{active}" aria-current="true"' in nav.group(0), rel


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


def test_hand_authored_pages_describe_the_shared_social_image() -> None:
    pages = set(STATIC_NAV_PAGES) | {"index.html"}
    alt = "GTFS Scorecard: transit data quality for small agencies."
    for rel in pages:
        html = (_REPO / "web" / rel).read_text()
        assert html.count(f'<meta property="og:image:alt" content="{alt}">') == 1, rel
        assert html.count(f'<meta name="twitter:image:alt" content="{alt}">') == 1, rel


def test_homepages_publish_the_exact_reciprocal_language_pair() -> None:
    expected = [
        ("en", "https://gtfsscorecard.org/"),
        ("es", "https://gtfsscorecard.org/es/"),
    ]
    for rel in ("index.html", "es/index.html"):
        html = (_REPO / "web" / rel).read_text()
        alternates = re.findall(
            r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">',
            html,
        )
        assert alternates == expected, rel
        assert 'hreflang="x-default"' not in html, rel


def test_shared_social_image_has_declared_dimensions() -> None:
    png = (_REPO / "web" / "og.png").read_bytes()
    assert png[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    assert struct.unpack(">II", png[16:24]) == (1200, 630)


def test_consulting_offer_is_reachable_from_public_project_surfaces() -> None:
    """The July hide was explicitly temporary; this is its inverse.

    A paid offer that quietly disappears from every entry point is the failure
    this replaces, so the link is asserted present rather than absent. The
    separation claim is asserted too: paid help never changes a grade.
    """
    public_sources = (
        _REPO / "web" / "support" / "index.html",
        _REPO / "README.md",
        _REPO / "docs" / "support.md",
    )
    for path in public_sources:
        assert "chelseakr.com/consulting" in path.read_text(), path


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

    assert 'id="coverage-registry-count">2,100+' in html
    assert "curated feed records" in html
    assert 'id="coverage-published-count">2,100+' in html
    assert "published scorecards" in html.lower()
    assert "40+" in html
    assert "Countries in registry" in html
    assert "everywhere they publish a feed" not in html

    representative_surfaces = (
        "/agency/unitrans/board/",
        "/program/all/",
        "/app/#/?view=features",
        "/check/",
        "/data/",
    )
    for href in representative_surfaces:
        assert f'href="{href}"' in html, href


def test_landing_leads_with_the_quality_workflow_and_keeps_the_pilot_bounded() -> None:
    html = (_REPO / "web" / "index.html").read_text()
    script = (_REPO / "web" / "src" / "landing-scorecard.js").read_text()

    assert "Find the next fix in a published GTFS feed." in html
    assert (
        "Search an agency to open its latest scorecard and first recommended fix. "
        "You can also check a GTFS ZIP before publishing it."
    ) in html
    assert "Where the scorecard fits in the work" in html
    assert "Start with the work you need to do." in html
    assert "Change and publish the feed" in html
    assert "Your workflow" in html
    assert "Latest published scorecard" in html
    assert "This is not yet a proven service." in html
    assert "A finding that disappears is a finding clearance." in html
    assert "Correctness uses MobilityData's canonical validator." in html
    assert "The scorecard starts the conversation." not in html
    assert "Other tools" not in html
    assert html.index('class="workflow-run"') < html.index('id="live-scorecard"')
    assert html.index('class="task-board"') < html.index('id="live-scorecard"')
    assert "PUBLIC FEED QUALITY / SERVICE DESK" not in html
    assert "One scored feed. Five places to use the evidence." not in html
    assert "Help test the full handoff." not in html
    for element_id in (
        "coverage-registry-count",
        "coverage-published-count",
        "coverage-country-count",
    ):
        assert f'id="{element_id}"' in html
    assert 'fetch("/api/v1/coverage.json"' in script
    assert "gtfs-scorecard-coverage-v1" in script
    assert "COVERAGE_CACHE_TTL_MS" in script
    assert 'id="pilot"' in html
    assert 'href="https://github.com/ChelseaKR/gtfs-scorecard/issues/194"' in html
    for href in (
        "https://mobilitydatabase.org/",
        "https://www.transit.land/",
        "https://github.com/MobilityData/gtfs-validator",
        "https://reports.dds.dot.ca.gov/",
    ):
        assert f'href="{href}"' in html


def test_landing_uses_a_real_interactive_scorecard_instead_of_a_fictional_dashboard() -> None:
    html = (_REPO / "web" / "index.html").read_text()
    script = (_REPO / "web" / "src" / "landing-scorecard.js").read_text()

    assert 'id="live-scorecard"' in html
    assert 'src="/src/landing-scorecard.js?v=20260723-coverage"' in html
    assert "Latest published scorecard" in html
    assert 'role="group" aria-label="Home pilots"' in html
    assert "measured category sets can differ" in html
    assert '<noscript><p class="pilot-fallback">' in html
    assert 'href="/agency/yolobus/"' in html
    assert "Selected fix trace" in html
    assert "Unitrans (ASUCD / City of Davis)" in html
    assert "80.8" in html
    assert "Realtime is excluded from this grade, with no deduction" in html
    for filename in ("stops.txt", "trips.txt", "shapes.txt", "feed_info.txt"):
        assert filename in html + script
    for endpoint in (
        "/data/artifacts/unitrans/latest.json",
        "/data/artifacts/yolobus/latest.json",
    ):
        assert endpoint in script
    assert "/api/v1/ids.json" in script
    assert "/api/v1/agencies.json" not in script
    assert "/data/artifacts/directory.json" not in script
    assert "/src/app.js" not in html
    assert "Fictional example" not in html
    assert "Format example" not in html
    assert "Tri-County Transit" not in html
    assert 'class="who-card"' not in html


def test_landing_pilot_artifacts_have_the_interactive_scorecard_contract() -> None:
    for agency_id in ("unitrans", "yolobus"):
        artifact = json.loads(
            (_REPO / "data" / "artifacts" / agency_id / "latest.json").read_text()
        )
        assert artifact["agency"]["id"] == agency_id
        assert isinstance(artifact["snapshot_date"], str)
        assert isinstance(artifact["overall"]["grade"], str)
        assert isinstance(artifact["overall"]["score"], (int, float))
        assert set(artifact["categories"]) >= {
            "correctness",
            "freshness",
            "completeness",
            "realtime",
        }
        assert len(artifact["top_fixes"]) >= 3
        for fix in artifact["top_fixes"][:3]:
            assert all(isinstance(fix[field], str) for field in ("code", "fix", "what", "why"))

    unitrans = json.loads((_REPO / "data" / "artifacts" / "unitrans" / "latest.json").read_text())
    yolobus = json.loads((_REPO / "data" / "artifacts" / "yolobus" / "latest.json").read_text())
    assert unitrans["categories"]["realtime"]["status"] != "measured"
    assert yolobus["categories"]["realtime"]["status"] == "measured"


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
    canonical = "https://gtfsscorecard.org/agencies/"

    assert html.count(f'<link rel="canonical" href="{canonical}">') == 1
    assert html.count(f'<meta property="og:url" content="{canonical}">') == 1


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
