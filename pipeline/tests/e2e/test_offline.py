"""Offline support (EXP-20): a visited page stays readable with no network,
and the saved copy announces itself instead of masquerading as current.

These tests run in their own browser context with service workers allowed;
every other e2e context blocks them (see conftest.browser_context_args) so
Playwright route stubs keep working.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Browser, BrowserContext, Page, expect

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


# --- JSON is network first, and a saved copy says how old it is. ---

_CURRENT_CACHE = """async () => {
  const keys = (await caches.keys()).filter(k => k.startsWith("scorecard-offline-"));
  if (keys.length !== 1) throw new Error("expected one offline cache, got " + keys);
  return keys[0];
}"""

_FETCH_TEXT = "path => fetch(path).then(r => r.text())"

_SEED_COPY = """async ([path, body, headers]) => {
  const name = (await caches.keys()).find(k => k.startsWith("scorecard-offline-"));
  const cache = await caches.open(name);
  await cache.put(path, new Response(body, { status: 200, headers }));
}"""

_SAVED_TEXT = """path => caches.match(path).then(hit => hit ? hit.text() : null)"""


def _controlled_context(browser: Browser, base_url: str) -> tuple[BrowserContext, Page]:
    """A page the worker controls, so its fetches go through the fetch handler."""
    context = browser.new_context(base_url=base_url, timezone_id="America/Los_Angeles")
    page = context.new_page()
    page.goto(f"{base_url}/agency/{AGENCY_ID}/")
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    return context, page


def _wait_for_saved_text(page: Page, path: str, expected: str) -> None:
    for _ in range(100):
        if page.evaluate(_SAVED_TEXT, path) == expected:
            return
        page.wait_for_timeout(100)
    pytest.fail(f"{path} never reached the cache as {expected!r}")


def _publish(site_root: Path, name: str, body: str) -> str:
    """Put a JSON file on the served site and return its URL path."""
    folder = site_root / "data" / "sw-test"
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(body)
    return f"/data/sw-test/{name}"


def test_online_json_is_fresh_even_with_a_stale_saved_copy(
    browser: Browser, base_url: str, site_root: Path
) -> None:
    path = _publish(site_root, "fresh.json", '{"checked": "today"}')
    context, page = _controlled_context(browser, base_url)
    try:
        page.evaluate(_SEED_COPY, [path, '{"checked": "weeks ago"}', {}])
        assert page.evaluate(_FETCH_TEXT, path) == '{"checked": "today"}'
        # The fresh answer replaces the old copy for the next offline visit.
        _wait_for_saved_text(page, path, '{"checked": "today"}')
        expect(page.locator(".offline-note")).to_have_count(0)
    finally:
        context.close()


def test_online_error_is_not_covered_up_by_a_saved_copy(browser: Browser, base_url: str) -> None:
    path = "/data/sw-test/not-published.json"
    context, page = _controlled_context(browser, base_url)
    try:
        page.evaluate(_SEED_COPY, [path, '{"checked": "weeks ago"}', {}])
        status = page.evaluate("path => fetch(path).then(r => r.status)", path)
        assert status == 404
        # The error reached the page and did not replace the good copy.
        assert page.evaluate(_SAVED_TEXT, path) == '{"checked": "weeks ago"}'
    finally:
        context.close()


def test_offline_json_is_the_saved_copy_and_the_note_names_its_date(
    browser: Browser, base_url: str, site_root: Path
) -> None:
    path = _publish(site_root, "dated.json", '{"checked": "today"}')
    context, page = _controlled_context(browser, base_url)
    try:
        page.evaluate(
            _SEED_COPY,
            [path, '{"checked": "weeks ago"}', {"Date": "Fri, 11 Sep 2026 20:00:00 GMT"}],
        )
        context.set_offline(True)
        assert page.evaluate(_FETCH_TEXT, path) == '{"checked": "weeks ago"}'
        note = page.locator(".offline-note")
        expect(note).to_contain_text("saved copy")
        expect(note).to_contain_text("September 11, 2026")

        # The page still shows that data once the network is back, so the note
        # must not vanish and leave it looking current.
        context.set_offline(False)
        expect(note).to_contain_text("back online")
        expect(note).to_contain_text("September 11, 2026")
    finally:
        context.close()


def test_saved_copy_with_no_date_names_no_date(browser: Browser, base_url: str) -> None:
    path = "/data/sw-test/undated.json"
    context, page = _controlled_context(browser, base_url)
    try:
        page.evaluate(_SEED_COPY, [path, "{}", {}])
        context.set_offline(True)
        assert page.evaluate(_FETCH_TEXT, path) == "{}"
        note = page.locator(".offline-note")
        expect(note).to_contain_text("dates shown were current when it was saved")
        expect(note).not_to_contain_text("1970")
        expect(note).not_to_contain_text("Invalid")
    finally:
        context.close()


def test_the_oldest_saved_date_is_the_one_named(browser: Browser, base_url: str) -> None:
    context, page = _controlled_context(browser, base_url)
    try:
        for name, date in (
            ("newer.json", "Sun, 01 Nov 2026 20:00:00 GMT"),
            ("older.json", "Fri, 11 Sep 2026 20:00:00 GMT"),
        ):
            page.evaluate(_SEED_COPY, [f"/data/sw-test/{name}", "{}", {"Date": date}])
        context.set_offline(True)
        page.evaluate(_FETCH_TEXT, "/data/sw-test/older.json")
        page.evaluate(_FETCH_TEXT, "/data/sw-test/newer.json")
        note = page.locator(".offline-note")
        expect(note).to_contain_text("September 11, 2026")
        expect(note).not_to_contain_text("November 1, 2026")
    finally:
        context.close()


def test_a_new_cache_version_clears_the_old_one(browser: Browser, base_url: str) -> None:
    context = browser.new_context(base_url=base_url)
    try:
        page = context.new_page()
        # A page with no nav.js, so no worker yet: the state a returning browser
        # is in, with last version's cache on disk.
        page.goto(f"{base_url}/llms.txt")
        page.evaluate(
            """async () => {
              const old = await caches.open("scorecard-offline-v2");
              await old.put("/data/artifacts/index.json", new Response("{}"));
            }"""
        )
        page.goto(f"{base_url}/agency/{AGENCY_ID}/")
        page.wait_for_function("navigator.serviceWorker.controller !== null")
        assert page.evaluate(_CURRENT_CACHE) != "scorecard-offline-v2"
        assert page.evaluate("caches.has('scorecard-offline-v2')") is False
        assert page.evaluate(_SAVED_TEXT, "/data/artifacts/index.json") is None
    finally:
        context.close()


def test_index_json_is_never_saved_and_the_view_says_so_offline(
    browser: Browser, base_url: str
) -> None:
    context, page = _controlled_context(browser, base_url)
    try:
        # The real consumer: "My agencies" loads the full index.
        with page.expect_response(
            lambda r: r.url.endswith("/data/artifacts/index.json") and r.status == 200
        ):
            page.goto(f"{base_url}/app/#/cohort")
        expect(page.locator("#main h1, #main h2").first).to_be_visible(timeout=60_000)
        # Give a save that should not happen time to land.
        page.wait_for_timeout(1500)
        assert page.evaluate(_SAVED_TEXT, "/data/artifacts/index.json") is None

        context.set_offline(True)
        page.reload()
        expect(page.locator("#main .error-box")).to_contain_text("index.json")
    finally:
        context.close()


def test_json_over_the_size_cap_is_not_saved(
    browser: Browser, base_url: str, site_root: Path
) -> None:
    big = _publish(site_root, "big.json", " " * (17 * 1024 * 1024))
    small = _publish(site_root, "small.json", "{}")
    context, page = _controlled_context(browser, base_url)
    try:
        assert len(page.evaluate(_FETCH_TEXT, big)) == 17 * 1024 * 1024
        page.evaluate(_FETCH_TEXT, small)
        _wait_for_saved_text(page, small, "{}")
        assert page.evaluate(_SAVED_TEXT, big) is None
    finally:
        context.close()


def test_directory_view_reads_offline_with_the_dated_note(browser: Browser, base_url: str) -> None:
    context, page = _controlled_context(browser, base_url)
    try:
        page.goto(f"{base_url}/app/")
        expect(page.locator("#main h1, #main h2").first).to_be_visible(timeout=60_000)
        for _ in range(100):
            if page.evaluate(
                """async () => (await caches.match("/app/")) !== undefined
                  && (await caches.match("/data/artifacts/directory.json")) !== undefined"""
            ):
                break
            page.wait_for_timeout(100)
        else:
            pytest.fail("the app shell and directory never reached the cache")

        context.set_offline(True)
        page.reload()
        expect(page.locator("#main .error-box")).to_have_count(0)
        expect(page.locator("#main h1, #main h2").first).to_be_visible(timeout=60_000)
        day = page.evaluate(
            """async () => {
              const saved = await caches.match("/data/artifacts/directory.json");
              return new Date(saved.headers.get("Date")).toLocaleDateString("en-US",
                { year: "numeric", month: "long", day: "numeric" });
            }"""
        )
        expect(page.locator(".offline-note")).to_contain_text(f"saved on {day}")
    finally:
        context.close()
