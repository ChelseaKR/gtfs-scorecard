"""Mobile-first layout and target-size checks over representative page families.

The static generator emits thousands of pages from a small set of templates.
These routes cover each distinct shell: landing, SPA, agency, program, national
data views, maps, forms, fix guides, redirect aliases and destinations, and the
standalone design concept. The ABQ RIDE page intentionally carries long
validator rule names, making it the regression fixture for min-content
horizontal overflow.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

MOBILE_ROUTES = [
    "/",
    "/app/#/",
    "/agency/abq-ride/",
    "/agency/unitrans/",
    "/program/california/",
    "/pulse/",
    "/problems/",
    "/adoption/",
    "/realtime/",
    "/status/",
    "/focus/",
    "/fix/expired_calendar/",
    "/map/",
    "/routes/",
    "/compare/?a=unitrans&b=yolobus",
    "/query/",
    "/subscribe.html",
    "/check/",
    "/how-to-read/",
]


@pytest.mark.parametrize(
    ("alias", "destination", "fragment_target"),
    [
        ("/changes/", "/pulse/#changes", "#changes"),
        ("/trends/", "/pulse/#trend", "#trend"),
        ("/access/", "/adoption/#access", "#access"),
    ],
)
def test_retired_alias_preserves_destination_fragment(
    page: Page,
    base_url: str,
    alias: str,
    destination: str,
    fragment_target: str,
) -> None:
    """Meta-refresh aliases retain the anchor that identifies absorbed content."""
    page.goto(f"{base_url}{alias}")

    expect(page).to_have_url(f"{base_url}{destination}")
    expect(page.locator(fragment_target)).to_be_attached()


@pytest.mark.parametrize("path", MOBILE_ROUTES)
def test_page_family_fits_mobile_viewport(page: Page, base_url: str, path: str) -> None:
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{base_url}{path}")
    if path.startswith("/app/"):
        expect(page.locator("#main .loading")).to_have_count(0)
    if path.startswith("/compare/?"):
        expect(page.locator("#compare-status")).to_contain_text(
            re.compile(r"Comparing|Scorecards kept separate")
        )

    layout = page.evaluate(
        """() => ({
          viewport: document.documentElement.clientWidth,
          pageWidth: document.documentElement.scrollWidth,
          headings: document.querySelectorAll('h1').length,
          overflowers: Array.from(document.querySelectorAll('body *')).filter((el) => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return s.position !== 'absolute' && r.right >
              document.documentElement.clientWidth + 1;
          }).slice(0, 12).map((el) => ({
            tag: el.tagName,
            id: el.id,
            className: typeof el.className === 'string' ? el.className : '',
            right: Math.round(el.getBoundingClientRect().right),
            width: Math.round(el.getBoundingClientRect().width),
          })),
          wideScrollContainers: Array.from(document.querySelectorAll('body *')).filter((el) =>
            el.scrollWidth > el.clientWidth + 1
          ).slice(0, 12).map((el) => ({
            tag: el.tagName,
            id: el.id,
            className: typeof el.className === 'string' ? el.className : '',
            clientWidth: el.clientWidth,
            scrollWidth: el.scrollWidth,
            overflowX: getComputedStyle(el).overflowX,
          })),
          small: Array.from(document.querySelectorAll([
            'button',
            'input:not([type="checkbox"]):not([type="radio"])',
            'select', 'textarea', 'summary', '.brand', '.backlink', '.theme-toggle'
          ].join(','))).filter((el) => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            // Fractional layout can report 43.999… for a 44px target in
            // Chromium, so compare the rendered size in whole CSS pixels.
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' &&
              (Math.round(r.width) < 44 || Math.round(r.height) < 44);
          }).map((el) => ({
            tag: el.tagName,
            id: el.id,
            className: typeof el.className === 'string' ? el.className : '',
            width: Math.round(el.getBoundingClientRect().width),
            height: Math.round(el.getBoundingClientRect().height),
          })),
          smallChoiceLabels: Array.from(document.querySelectorAll(
            'input[type="checkbox"], input[type="radio"]'
          )).filter((input) => {
            const r = input.getBoundingClientRect();
            if (!(r.width > 0 && r.height > 0)) return false;
            const label = input.closest('label');
            if (!label) return true;
            const lr = label.getBoundingClientRect();
            return Math.round(lr.width) < 44 || Math.round(lr.height) < 44;
          }).map((input) => input.id || input.getAttribute('name')),
        })"""
    )
    assert layout["pageWidth"] <= layout["viewport"], f"{path}: {layout}"
    assert layout["headings"] == 1, f"{path}: expected one h1"
    assert layout["small"] == [], f"{path}: undersized standalone targets: {layout['small']}"
    assert layout["smallChoiceLabels"] == [], f"{path}: undersized checkbox/radio labels"


@pytest.mark.parametrize(
    "path",
    ["/agency/unitrans/", "/compare/?a=unitrans&b=yolobus"],
)
def test_data_dense_pages_fit_320px(page: Page, base_url: str, path: str) -> None:
    """Regression for the report route, route table, history prose, and loaded
    comparison result state: each owns any sideways scrolling instead of widening the
    page at the WCAG reflow width."""
    page.set_viewport_size({"width": 320, "height": 720})
    page.goto(f"{base_url}{path}")
    if path.startswith("/compare/"):
        expect(page.locator("#compare-status")).to_contain_text(
            re.compile(r"Comparing|Scorecards kept separate")
        )
    width = page.evaluate(
        "() => [document.documentElement.clientWidth, document.documentElement.scrollWidth]"
    )
    assert width[1] <= width[0], f"{path}: viewport {width[0]}px, page {width[1]}px"


def test_scorecard_shows_measured_grade_immediately(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{base_url}/agency/abq-ride/")

    label = page.locator(".reel").get_attribute("aria-label") or ""
    match = re.fullmatch(r"Overall grade ([ABCDF])", label)
    assert match is not None
    grade = match.group(1)
    visible = page.evaluate(
        """() => {
          const reel = document.querySelector('.reel').getBoundingClientRect();
          return Array.from(document.querySelectorAll('.reel-strip span'))
            .filter((span) => {
              const r = span.getBoundingClientRect();
              return r.top < reel.bottom && r.bottom > reel.top;
            }).map((span) => span.textContent.trim());
        }"""
    )
    assert visible == [grade]
    assert (
        page.locator(".reel-strip").evaluate("el => getComputedStyle(el).animationName") == "none"
    )


@pytest.mark.parametrize(
    ("path", "selector"),
    [
        ("/problems/", ".problems-chart"),
        ("/adoption/", ".adoption-chart"),
        ("/realtime/", ".reliability-chart"),
        ("/status/", ".staleness-chart"),
    ],
)
def test_visualization_patterns_stay_inside_phone_viewport(
    page: Page, base_url: str, path: str, selector: str
) -> None:
    page.set_viewport_size({"width": 320, "height": 720})
    page.goto(f"{base_url}{path}")
    chart = page.locator(selector)
    if chart.count() == 0:
        # Cross-feed charts deliberately disappear during a methodology
        # migration instead of visualizing stale rows as current evidence.
        expect(page.locator("main")).to_contain_text("unavailable")
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        return
    expect(chart).to_have_count(1)
    bounds = chart.evaluate(
        """el => {
          const r = el.getBoundingClientRect();
          return {
            left: r.left,
            right: r.right,
            viewport: document.documentElement.clientWidth,
            labels: Array.from(el.querySelectorAll(
              '.service-bar-label, .bucket-label, .movement-counts li'
            )).map((node) => node.textContent.trim()),
            values: Array.from(el.querySelectorAll(
              '.service-bar-value, .bucket-value, .movement-counts strong'
            )).map((node) => node.textContent.trim()),
          };
        }"""
    )
    assert bounds["left"] >= -1 and bounds["right"] <= bounds["viewport"] + 1, bounds
    assert bounds["labels"], f"{path}: chart needs visible labels"
    assert bounds["values"], f"{path}: chart needs visible exact values"


@pytest.mark.parametrize("width", [768, 1440])
def test_key_pages_fit_tablet_and_desktop(page: Page, base_url: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    for path in ("/", "/app/#/", "/agency/abq-ride/", "/pulse/", "/compare/"):
        page.goto(f"{base_url}{path}")
        if path.startswith("/app/"):
            expect(page.locator("#main .loading")).to_have_count(0)
        layout = page.evaluate(
            """() => ({
              pageWidth: document.documentElement.scrollWidth,
              viewport: document.documentElement.clientWidth,
              overflowers: Array.from(document.querySelectorAll('body *')).filter((el) => {
                const r = el.getBoundingClientRect();
                return r.right > document.documentElement.clientWidth + 1;
              }).slice(0, 10).map((el) => ({
                tag: el.tagName,
                id: el.id,
                className: typeof el.className === 'string' ? el.className : '',
                left: Math.round(el.getBoundingClientRect().left),
                right: Math.round(el.getBoundingClientRect().right),
                width: Math.round(el.getBoundingClientRect().width),
              })),
              wide: Array.from(document.querySelectorAll('body *')).filter((el) =>
                el.scrollWidth > el.clientWidth + 1
              ).slice(0, 10).map((el) => ({
                tag: el.tagName,
                id: el.id,
                className: typeof el.className === 'string' ? el.className : '',
                clientWidth: el.clientWidth,
                scrollWidth: el.scrollWidth,
              })),
            })"""
        )
        assert layout["pageWidth"] <= layout["viewport"], f"{path} at {width}px: {layout}"


def test_feature_shortlist_keeps_a_readable_tablet_layout(page: Page, base_url: str) -> None:
    """The action row must not consume the prose-width board and collapse the
    empty-state message to a zero-width grid track."""
    page.set_viewport_size({"width": 720, "height": 900})
    page.goto(f"{base_url}/app/#/")
    expect(page.locator("#main .loading")).to_have_count(0)

    layout = page.locator(".feature-match-board").evaluate(
        """el => {
          const board = el.getBoundingClientRect();
          const count = el.querySelector('.agency-count').getBoundingClientRect();
          const actions = el.querySelector('.feature-match-actions').getBoundingClientRect();
          const range = document.createRange();
          range.selectNodeContents(el.querySelector('.agency-count'));
          return {
            boardHeight: board.height,
            countWidth: count.width,
            countLines: range.getClientRects().length,
            actionsBelowCount: actions.top >= count.bottom - 1,
          };
        }"""
    )
    assert layout["countWidth"] >= 300, layout
    assert layout["countLines"] <= 2, layout
    assert layout["actionsBelowCount"], layout
    assert layout["boardHeight"] < 180, layout
    expect(page.get_by_role("button", name="Download matching feeds (CSV)")).to_be_hidden()


@pytest.mark.parametrize(
    ("path", "selector"),
    [("/", ".grade-reel"), ("/agency/unitrans/", ".reel")],
)
def test_reduced_motion_keeps_grade_and_content_visible(
    page: Page, base_url: str, path: str, selector: str
) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{base_url}{path}")

    label = page.locator(selector).get_attribute("aria-label") or ""
    match = re.fullmatch(r"Overall grade ([ABCDF])", label)
    assert match is not None
    grade = match.group(1)
    expect(page.locator(selector)).to_contain_text(grade)
    assert page.evaluate(
        "() => Array.from(document.querySelectorAll('.rise')).every((el) => "
        "getComputedStyle(el).opacity === '1')"
    )


def test_retired_concept_routes_to_current_guide(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/concept/")
    page.wait_for_url(f"{base_url}/how-to-read/")
    expect(page.get_by_role("heading", name="How to read your scorecard")).to_be_visible()
