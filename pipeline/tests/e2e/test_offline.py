"""Offline support (EXP-20): a visited page stays readable with no network,
and the saved copy announces itself instead of masquerading as current.

These tests run in their own browser context with service workers allowed;
every other e2e context blocks them (see conftest.browser_context_args) so
Playwright route stubs keep working.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Browser, expect

pytestmark = pytest.mark.e2e

AGENCY_ID = "abq-ride"  # a real committed agency, same anchor as test_routes.py


def test_visited_page_is_saved_and_served_offline(browser: Browser, base_url: str) -> None:
    context = browser.new_context(base_url=base_url)
    try:
        page = context.new_page()
        page.goto(f"{base_url}/agency/{AGENCY_ID}/")
        # The worker activates during this first, uncontrolled navigation and
        # claims the page, but only the NEXT navigation flows through its
        # fetch handler — so reload once online to store the copy, then wait
        # for the asynchronous cache.put to land (evaluate awaits the promise;
        # wait_for_function would treat the pending promise itself as truthy).
        page.wait_for_function("navigator.serviceWorker.controller !== null")
        page.reload()
        for _ in range(50):
            if page.evaluate(
                "path => caches.match(path).then(hit => hit !== undefined)",
                f"/agency/{AGENCY_ID}/",
            ):
                break
            page.wait_for_timeout(100)
        else:
            pytest.fail("the visited page never appeared in the offline cache")

        context.set_offline(True)
        page.reload()
        # The saved copy renders, and the honesty note says what it is.
        expect(page.locator("h1")).to_contain_text("ABQ")
        note = page.locator(".offline-note")
        expect(note).to_be_visible()
        expect(note).to_have_attribute("role", "status")
        expect(note).to_contain_text("saved copy")

        # Back online, the note goes away without a reload.
        context.set_offline(False)
        expect(note).to_have_count(0)
    finally:
        context.close()


def test_unsaved_page_offline_gets_the_plain_fallback(browser: Browser, base_url: str) -> None:
    context = browser.new_context(base_url=base_url)
    try:
        page = context.new_page()
        page.goto(f"{base_url}/agency/{AGENCY_ID}/")
        page.wait_for_function("navigator.serviceWorker.controller !== null")

        context.set_offline(True)
        page.goto(f"{base_url}/agency/unitrans/")
        expect(page.locator("h1")).to_have_text("You are offline")
        expect(page.locator("body")).to_contain_text("Pages you visit while online")
    finally:
        context.close()


def test_offline_note_never_shows_while_online(browser: Browser, base_url: str) -> None:
    context = browser.new_context(base_url=base_url)
    try:
        page = context.new_page()
        page.goto(f"{base_url}/agency/{AGENCY_ID}/")
        expect(page.locator(".offline-note")).to_have_count(0)
    finally:
        context.close()
