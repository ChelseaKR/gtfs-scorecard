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
    FOOTER_HTML,
    HOME_PAGE,
    STATIC_NAV_PAGES,
    _nav_stops_html,
    home_nav_html,
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


def test_home_page_nav_and_footer_match_canonical() -> None:
    """The home page keeps its inline-styled header, but its links are
    _NAV_ITEMS and its footer is the shared one (the 2026-11 IA, phase 2)."""
    html = (_REPO / "web" / HOME_PAGE).read_text()
    header = re.search(r'<header class="home-header">.*?</header>', html, re.S)
    assert header is not None
    assert home_nav_html() in header.group(0), "home nav drifted; run `make sync-static-nav`"
    assert html.count(FOOTER_HTML) == 1, "home footer drifted; run `make sync-static-nav`"
    assert html.count("<footer") == 1
    # The footer's rules are inline: the home page loads no stylesheet.
    assert 'href="/src/styles.css"' not in html
    assert ".site-footer {" in html and ".footer-grid {" in html


def test_every_page_in_the_footer_or_nav_still_exists() -> None:
    """Nav and footer point only at pages the site has; no URL was added."""
    web = _REPO / "web"
    hrefs = {href for _, href in _NAV_ITEMS} | set(re.findall(r'href="(/[^"#]*)', FOOTER_HTML))
    goldens = _REPO / "pipeline" / "tests" / "goldens"
    for href in sorted(hrefs):
        rel = href.lstrip("/")
        candidates = [web / rel, web / rel / "index.html", goldens / rel / "index.html"]
        if rel.endswith(".html"):
            candidates = [web / rel]
        assert any(path.is_file() for path in candidates), href


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
    """Every hand-authored page shares the root og.png and its alt text,
    except /bundle/: the paid tier gets its own card (bundle-og.png,
    web/bundle-og.svg) with its own alt text, since a launch post sharing
    /bundle/ should not show a reader the free tool's card."""
    pages = (set(STATIC_NAV_PAGES) | {"index.html"}) - {"bundle/index.html"}
    alt = "GTFS Scorecard: transit data quality for small agencies."
    for rel in pages:
        html = (_REPO / "web" / rel).read_text()
        assert 'content="https://gtfsscorecard.org/og.png"' in html, rel
        assert html.count(f'<meta property="og:image:alt" content="{alt}">') == 1, rel
        assert html.count(f'<meta name="twitter:image:alt" content="{alt}">') == 1, rel
        assert "bundle-og.png" not in html, rel


def test_bundle_page_describes_its_own_social_image() -> None:
    html = (_REPO / "web" / "bundle" / "index.html").read_text()
    alt = (
        "GTFS Scorecard Program Report Bundle: board reports for every "
        "agency your program supports."
    )
    image_url = "https://gtfsscorecard.org/bundle-og.png"
    assert html.count(f'<meta property="og:image" content="{image_url}">') == 1
    assert html.count(f'<meta name="twitter:image" content="{image_url}">') == 1
    assert html.count(f'<meta property="og:image:alt" content="{alt}">') == 1
    assert html.count(f'<meta name="twitter:image:alt" content="{alt}">') == 1
    assert html.count('<meta property="og:image:width" content="1200">') == 1
    assert html.count('<meta property="og:image:height" content="630">') == 1


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


def test_bundle_social_image_has_declared_dimensions() -> None:
    png = (_REPO / "web" / "bundle-og.png").read_bytes()
    assert png[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    assert struct.unpack(">II", png[16:24]) == (1200, 630)


def test_apple_touch_icon_is_the_declared_180_square() -> None:
    png = (_REPO / "web" / "apple-touch-icon.png").read_bytes()
    assert png[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    assert struct.unpack(">II", png[16:24]) == (180, 180)


_FAVICON_LINKS = (
    '<link rel="icon" type="image/svg+xml" href="/favicon.svg">',
    '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">',
    '<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png">',
    '<link rel="shortcut icon" href="/favicon.ico">',
    '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">',
)


def test_hand_authored_pages_carry_the_full_icon_set() -> None:
    """Every hand-authored page links the real mark (favicon.svg) plus its
    PNG/ICO fallbacks and the apple-touch-icon, not the old inline circle+dot
    data URI. Mirrors _page()'s <head> (test_render_site.py), which generated
    pages get automatically; these pages don't, so nothing catches drift here
    except this test."""
    for rel in set(STATIC_NAV_PAGES) | {"index.html", "es/index.html"}:
        html = (_REPO / "web" / rel).read_text()
        for link in _FAVICON_LINKS:
            assert link in html, f"{rel}: missing {link!r}"
        assert "data:image/svg+xml" not in html, f"{rel}: still carries the old inline favicon"


_MONEY_PAGES = (
    _REPO / "web" / "support" / "index.html",
    _REPO / "README.md",
    _REPO / "docs" / "support.md",
    _REPO / "SUPPORT.md",
)


def test_no_public_surface_links_to_the_retired_consulting_page() -> None:
    """The consulting offer was withdrawn (2026-09-01) and its page returns 404.

    The previous test asserted the link *present*, which is how a dead link
    survived on the one page that asks for money. A withdrawn offer must
    disappear from every entry point at once, so the link is asserted absent.
    """
    for path in _MONEY_PAGES:
        assert "chelseakr.com/consulting" not in path.read_text(), path


def test_every_money_page_points_at_the_live_sponsorship_rail() -> None:
    """The one payment rail that exists is GitHub Sponsors; each surface that
    talks about money must reach it, and .github/FUNDING.yml must agree."""
    for path in _MONEY_PAGES:
        assert "https://github.com/sponsors/ChelseaKR" in path.read_text(), path
    funding = (_REPO / ".github" / "FUNDING.yml").read_text()
    assert "github: ChelseaKR" in funding


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

    # The three doors (the 2026-11 IA, D6) and the example scorecard.
    representative_surfaces = (
        "/agencies/",
        "/subscribe.html",
        "/claim/",
        "/check/",
        "/program/",
        "/bundle/",
        "/data/",
        "/data/history/",
        "/agency/unitrans/brief/",
    )
    for href in representative_surfaces:
        assert f'href="{href}"' in html, href


def test_landing_points_at_the_history_tables_from_the_data_door_only() -> None:
    """One link, in the "I use GTFS data" door beside the /data/ link, and
    nowhere else on the page: not in the primary nav, which sync_static_navs
    writes from _NAV_ITEMS, and not in the program-tier section, which sells
    the bundle. The anchor says "paid" before the click, as the bundle's door
    link does, and no amount is typed anywhere on the page: the bundle's
    home-page copy carries none either, its plan summary being fetched at
    view time."""
    html = (_REPO / "web" / "index.html").read_text()
    # The landing page carries its own header and the shared footer.
    head, separator, _footer = html.partition('<footer class="site-footer">')
    assert separator, "the landing page has no footer; the split below proves nothing"
    assert head.count('href="/data/history/"') == 1

    header = re.search(r'<header class="home-header">.*?</header>', html, re.S)
    assert header is not None, "the landing header was renamed; this check now reads nothing"
    assert "/data/history/" not in header.group(0)
    assert _NAV_STOPS_RE.search(html) is None, "the landing page grew the shared nav; split on it"
    assert all("/data/history/" not in href for _label, href in _NAV_ITEMS)

    programs = head[
        head.index('id="programs"') : head.index("</section>", head.index('id="programs"'))
    ]
    assert "/data/history/" not in programs

    door_nav = head.index('<nav aria-labelledby="door-data-h">')
    door = head[door_nav : head.index("</nav>", door_nav)]
    assert 'href="/data/"' in door
    assert '<a href="/data/history/">History tables (paid)</a>' in door

    plan = json.loads((_REPO / "web" / "data" / "history" / "plan.json").read_text())
    assert f"${plan['products']['history_once']['price']}" not in html


def test_landing_is_short_and_the_workflow_moved_to_how_to_read() -> None:
    """The 2026-11 IA, D6: search, browse by place, three doors, the example
    scorecard and "What the score does not establish". The six-step workflow,
    where the scorecard fits, and the pilot moved to /how-to-read/ with the ids
    they had here, text unchanged."""
    html = (_REPO / "web" / "index.html").read_text()
    script = (_REPO / "web" / "src" / "landing-scorecard.js").read_text()
    guide = (_REPO / "pipeline" / "tests" / "goldens" / "how-to-read" / "index.html").read_text()

    assert '<h1 id="home-title">GTFS feed quality, graded daily.</h1>' in html
    assert ("Find an agency to see its grade, its feed URL, and the first things to fix.") in html
    assert "Find the next fix in a published GTFS feed." not in html
    assert '<h2 id="place-chips-h">Browse by place</h2>' in html
    assert '<h2 id="task-board-h">Start from what you do</h2>' in html
    for door in (
        "I work at a transit agency",
        "I support several agencies",
        "I use GTFS data",
    ):
        assert door in html
    assert '<h2 id="scorecard-demo-h">Example scorecard</h2>' in html
    assert "Latest published scorecard" in html
    assert "What the score does not establish" in html
    assert "A finding that disappears is a finding clearance." in html
    assert "Correctness uses MobilityData's canonical validator." in html
    assert html.index('class="task-board"') < html.index('id="live-scorecard"')
    assert html.index('id="live-scorecard"') < html.index('id="notes-h"')
    for element_id in (
        "coverage-registry-count",
        "coverage-published-count",
        "coverage-country-count",
        "door-published-count",
    ):
        assert f'id="{element_id}"' in html
    assert 'fetch("/api/v1/coverage.json"' in script
    assert "gtfs-scorecard-coverage-v1" in script
    assert "COVERAGE_CACHE_TTL_MS" in script
    assert 'getElementById("door-published-count")' in script

    # Moved, not deleted: same text, same ids, now on /how-to-read/.
    for moved in ('id="workflow-run-h"', 'id="ecosystem"', 'id="pilot"'):
        assert moved not in html, moved
        assert moved in guide, moved
    for sentence in (
        "Where the scorecard fits in the work",
        "Change and publish the feed",
        "Your workflow",
        "This is not yet a proven service.",
        "Use the scorecard between discovery and the next feed export.",
        "Remediation workflow",
    ):
        assert sentence in guide, sentence
    for href in (
        "https://github.com/ChelseaKR/gtfs-scorecard/issues/194",
        "https://mobilitydatabase.org/",
        "https://www.transit.land/",
        "https://github.com/MobilityData/gtfs-validator",
        "https://reports.dds.dot.ca.gov/",
    ):
        assert f'href="{href}"' in guide, href


def test_landing_place_chips_link_only_place_pages() -> None:
    html = (_REPO / "web" / "index.html").read_text()
    block = html[html.index("<!-- place-chips:start -->") : html.index("<!-- place-chips:end -->")]
    hrefs = re.findall(r'href="([^"]+)"', block)
    assert hrefs[-1] == "/program/"
    assert '<a href="/program/">All states and countries</a>' in block
    assert 1 <= len(hrefs) - 1 <= 6
    for href in hrefs[:-1]:
        assert re.fullmatch(r"/program/[a-z0-9-]+/", href), href
        assert href not in ("/program/all/", "/program/yolo-county/"), href


def test_landing_uses_a_real_interactive_scorecard_instead_of_a_fictional_dashboard() -> None:
    html = (_REPO / "web" / "index.html").read_text()
    script = (_REPO / "web" / "src" / "landing-scorecard.js").read_text()

    assert 'id="live-scorecard"' in html
    assert 'src="/src/landing-scorecard.js?v=20261121-short-home"' in html
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
    # The search box suggests names from the shared picker's small index,
    # never the feed-URL crosswalk or the full directory.
    picker = (_REPO / "web" / "src" / "agency-combobox.js").read_text()
    assert '"/src/agency-combobox.js?v=20261119-agency-search"' in script
    assert "ScorecardAgencySearch" in script
    assert '"/data/agency-index.json"' in picker
    assert "/api/v1/ids.json" not in script + picker
    assert "/api/v1/agencies.json" not in script
    assert "/data/artifacts/directory.json" not in script
    assert "/src/app.js" not in html
    assert "Fictional example" not in html
    assert "Format example" not in html
    assert "Tri-County Transit" not in html
    assert 'class="who-card"' not in html


def test_landing_keeps_the_agency_picker_script_off_the_first_paint() -> None:
    """The picker script loads after the page, not from the head (LCP budget).

    Every request that starts before the first paint counts against the
    simulated Largest Contentful Paint in lighthouserc.json. With the picker
    as a deferred head script, the home page missed the 2750 ms budget by one
    request (Deploy site, 2026-11-20). landing-scorecard.js now loads it once
    the page has loaded and the browser is idle, or when the search form gets
    focus first; the browser test checks the timing in a real page.
    """
    html = (_REPO / "web" / "index.html").read_text()
    script = (_REPO / "web" / "src" / "landing-scorecard.js").read_text()

    assert "agency-combobox.js" not in html
    assert 'window.addEventListener("load", whenIdle' in script
    assert 'addEventListener("focusin", loadPickerQuietly)' in script


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


def test_interactive_app_names_itself_as_canonical() -> None:
    # ADR 0080: the app used to declare /agencies/ as its canonical. Google
    # ignored that and indexed /app/ under its own URL, so the page now says
    # what is true. The old target must not come back by a partial revert.
    html = (_REPO / "web" / "app" / "index.html").read_text()
    canonical = "https://gtfsscorecard.org/app/"

    assert html.count(f'<link rel="canonical" href="{canonical}">') == 1
    assert html.count(f'<meta property="og:url" content="{canonical}">') == 1
    assert '<link rel="canonical" href="https://gtfsscorecard.org/agencies/">' not in html


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


def test_open_data_dataset_carries_what_google_dataset_search_requires() -> None:
    """Google Dataset Search lists a Dataset only with both a name and a
    description, and the description must run 50 to 5,000 characters."""
    html = (_REPO / "web" / "data" / "index.html").read_text()
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html)
    assert match is not None
    [dataset] = json.loads(match.group(1))["dataset"]
    assert dataset["@type"] == "Dataset"
    assert dataset["name"].strip()
    description = dataset["description"]
    assert 50 <= len(description) <= 5000
    # It describes the published file in the page's own terms: worldwide
    # coverage, one row per feed record, the columns the page lists.
    assert "worldwide" in description
    assert "one row per feed record" in description
    assert "days until the service calendar expires" in description
    assert dataset["isAccessibleForFree"] is True
    assert dataset["creator"] == {
        "@type": "Organization",
        "name": "GTFS Scorecard",
        "url": "https://gtfsscorecard.org/",
    }
    assert dataset["license"] == "https://creativecommons.org/licenses/by/4.0/"
