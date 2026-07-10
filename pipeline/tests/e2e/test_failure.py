"""Fetch-failure path: when every artifact request 404s, the spinner must be
replaced by a visible error that announces itself. renderError in
web/src/app.js renders <div class="error-box" role="alert">, so an assistive
tech user hears the failure instead of sitting on a silent spinner."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.e2e


def test_artifact_404_shows_announced_error(page: Page, app_url: str) -> None:
    def _not_found(route: Route) -> None:
        route.fulfill(status=404, body="not found")

    # Covers both DATA_BASES the app tries: /app/data/artifacts/... and
    # /data/artifacts/... (web/src/app.js fetchJson).
    page.route("**/data/artifacts/**", _not_found)
    page.goto(f"{app_url}#/")

    box = page.locator("#main .error-box")
    expect(box).to_be_visible()
    expect(box).to_have_attribute("role", "alert")
    expect(box.locator("h1")).to_have_text("We couldn't load this scorecard.")
    # The same box is what role=alert announces.
    expect(page.get_by_role("alert")).to_contain_text("We couldn't load")
    # It offers a way back out.
    expect(box.locator('a[href="#/"]')).to_be_visible()
    # And the spinner is gone, not sitting under or before the error.
    expect(page.locator("#main .loading")).to_have_count(0)
    expect(page.get_by_text("Loading scorecards…")).to_have_count(0)
