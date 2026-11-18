"""The missing-address page, in a browser, at an address it was not built for.

GitHub Pages serves `/404.html` at whatever address was asked for. The local
test server does not, so the first test hands the browser that file's bytes
at a deep address and a 404 status, which is what the host does. If any
address in the page were relative it would be looked for under the missing
folder: no stylesheet, no header, no theme control.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
MISSING = "/agency/no-such-agency/board/"


def _serve_as_missing(page: Page, base_url: str) -> None:
    body = (REPO_ROOT / "web" / "404.html").read_text(encoding="utf-8")

    def _answer(route: Route) -> None:
        route.fulfill(status=404, content_type="text/html; charset=utf-8", body=body)

    page.route(f"{base_url}{MISSING}", _answer)


def test_the_page_works_at_a_deep_missing_address(page: Page, base_url: str) -> None:
    _serve_as_missing(page, base_url)
    response = page.goto(f"{base_url}{MISSING}")
    assert response is not None and response.status == 404

    expect(page).to_have_title("Page not found — GTFS Scorecard")
    expect(page.locator("h1")).to_have_text("Page not found.")
    # The stylesheet loaded: the header is the sticky pine band.
    header = page.locator(".site-header")
    assert header.evaluate("el => getComputedStyle(el).position") == "sticky"
    # The scripts loaded: theme.js mounted the theme control.
    expect(page.locator("#theme-toggle-btn")).to_be_visible()
    assert page.evaluate("() => document.documentElement.lang") == "en"

    # The three ways on lead to pages that exist.
    links = page.locator("main a")
    expect(links).to_have_text(["Find an agency", "Search scorecards", "Go to the home page"])
    for index in range(3):
        href = links.nth(index).get_attribute("href")
        assert href is not None
        target = page.request.get(f"{base_url}{href}")
        assert target.ok, f"{href} is itself missing"


def test_the_page_is_usable_from_the_keyboard_at_320px(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 320, "height": 640})
    page.emulate_media(reduced_motion="reduce")
    _serve_as_missing(page, base_url)
    page.goto(f"{base_url}{MISSING}")

    width = page.evaluate(
        "() => [document.documentElement.clientWidth, document.documentElement.scrollWidth]"
    )
    assert width[1] <= width[0], f"viewport {width[0]}px, page {width[1]}px"

    page.keyboard.press("Tab")
    skip = page.locator(".skip-link")
    expect(skip).to_be_focused()
    expect(skip).to_be_in_viewport(ratio=1)
    page.keyboard.press("Enter")
    assert page.evaluate("() => document.activeElement.id") == "main"
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.textContent") == "Find an agency"
