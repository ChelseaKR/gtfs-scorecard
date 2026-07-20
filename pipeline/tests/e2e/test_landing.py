"""The landing service desk renders and changes real published scorecards."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _wait_for_scorecard(page: Page) -> None:
    expect(page.locator("#live-scorecard")).to_have_attribute("aria-busy", "false")


def test_landing_starts_with_a_real_unitrans_record(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    assert page.url == f"{base_url}/"
    expect(page.locator("#scorecard-agency")).to_contain_text("Unitrans")
    expect(page.locator("#scorecard-grade")).to_have_text("B")
    expect(page.locator("#scorecard-score")).to_have_text("80.8")
    expect(page.locator("#scorecard-date")).to_have_attribute("datetime", "2026-07-10")
    expect(page.locator('[data-category="realtime"] .category-value')).to_have_text("Not measured")
    expect(page.locator('[data-category-row="realtime"] [role="meter"]')).to_have_count(0)
    expect(page.locator("#fix-selector button")).to_have_count(3)
    expect(page.locator("#trace-code")).to_have_text("scorecard_wheelchair_boarding_unknown")


def test_landing_switches_record_category_and_fix_without_reload(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    page.get_by_role("button", name="Yolobus").click()
    _wait_for_scorecard(page)
    expect(page.locator("#scorecard-agency")).to_contain_text("Yolobus")
    expect(page.locator("#scorecard-score")).to_have_text("82.2")
    expect(page.locator('[data-category="realtime"] .category-value')).to_have_text("92.2")
    expect(page.locator('[data-agency-id="yolobus"]')).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#scope-scorecard-link")).to_have_attribute("href", "/agency/yolobus/")
    expect(page.locator("#scope-brief-link")).to_have_attribute("href", "/agency/yolobus/brief/")

    page.locator('[data-category="realtime"]').click()
    expect(page.locator("#category-detail-summary")).to_contain_text("Sampled 9 times")

    page.locator('[data-fix-index="2"]').click()
    expect(page.locator("#trace-code")).to_have_text("scorecard_missing_feed_info_dates")
    expect(page.locator("#trace-source-files")).to_contain_text("feed_info.txt")
    assert "feed=yolobus" in page.url
    assert "fix=3" in page.url


def test_landing_search_lazily_pins_another_published_feed(page: Page, base_url: str) -> None:
    requested: list[str] = []
    page.on("request", lambda request: requested.append(request.url))
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)
    assert not any(url.endswith("/api/v1/ids.json") for url in requested)

    search = page.locator("#feed-search")
    search.fill("ABQ RIDE")
    first = page.locator("#feed-results button").first
    expect(first).to_be_visible()
    expect(page.locator("#picker-status")).to_contain_text(re.compile(r"match"))
    first.click()
    _wait_for_scorecard(page)

    expect(page.locator("#scorecard-agency")).to_contain_text("ABQ RIDE")
    assert search.evaluate("element => element === document.activeElement")
    assert any(url.endswith("/api/v1/ids.json") for url in requested)
    assert not any(url.endswith("/api/v1/agencies.json") for url in requested)
    assert not any(url.endswith("/data/artifacts/directory.json") for url in requested)

    search.fill("PATCO Speedline")
    no_fix_record = page.locator('#feed-results button[data-agency-id="patco-speedline-3035"]')
    expect(no_fix_record).to_be_visible()
    no_fix_record.click()
    _wait_for_scorecard(page)
    expect(page.locator("#scorecard-score")).to_have_text("100")
    expect(page.locator("#fix-selector")).to_be_hidden()
    expect(page.locator("#fix-title")).to_have_text("No prioritized fixes in this snapshot.")


def test_landing_controls_keep_keyboard_focus(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    pilot = page.get_by_role("button", name="Yolobus")
    pilot.focus()
    page.keyboard.press("Enter")
    _wait_for_scorecard(page)
    assert pilot.evaluate("element => element === document.activeElement")
    expect(pilot).to_have_attribute("aria-pressed", "true")

    page.locator("#feed-search").focus()
    page.keyboard.type("unitrans")
    expect(page.locator("#feed-results button").first).to_be_visible()
    page.keyboard.press("ArrowDown")
    assert page.locator("#feed-results button").first.evaluate(
        "element => element === document.activeElement"
    )


def test_landing_traces_an_expired_feed_as_a_freshness_check(page: Page, base_url: str) -> None:
    page.route(
        "**/data/artifacts/expired-demo/latest.json",
        lambda route: route.fulfill(
            json={
                "agency": {"id": "expired-demo", "name": "Expired Demo Transit"},
                "snapshot_date": "2026-07-18",
                "overall": {"grade": "F", "score": 44.0},
                "categories": {
                    "correctness": {"status": "measured", "score": 90, "summary": "Measured."},
                    "freshness": {
                        "status": "measured",
                        "score": 0,
                        "summary": "Service data ended.",
                    },
                    "completeness": {"status": "measured", "score": 60, "summary": "Measured."},
                    "realtime": {"status": "not_yet_measured", "summary": "Not measured."},
                },
                "top_fixes": [
                    {
                        "code": "scorecard_feed_expired",
                        "rank": 1,
                        "owner": "Likely your export tool",
                        "fix": "Publish a current service calendar.",
                        "what": "Service data ended 14 days ago.",
                        "why": "Trip planners cannot show current service.",
                        "effort": "One export.",
                    }
                ],
            }
        ),
    )
    page.goto(f"{base_url}/?feed=expired-demo")
    _wait_for_scorecard(page)

    expect(page.locator("#trace-method-title")).to_have_text("Feed validity check")
    expect(page.locator("#trace-source-title")).to_have_text("Published service horizon")
    expect(page.locator("#trace-source-files")).to_contain_text("calendar.txt")


def test_landing_escape_cancels_pending_search(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    search = page.locator("#feed-search")
    search.fill("ab")
    search.press("Escape")
    page.wait_for_timeout(180)

    expect(page.locator("#feed-results")).to_be_hidden()
    expect(page.locator("#picker-status")).to_have_text("Search results closed.")
