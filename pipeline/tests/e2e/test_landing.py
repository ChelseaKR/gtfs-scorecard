"""The landing service desk renders and changes real published scorecards."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.e2e

ARTIFACTS = Path(__file__).resolve().parents[3] / "data" / "artifacts"


def _artifact(agency_id: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ARTIFACTS / agency_id / "latest.json").read_text()))


def _wait_for_scorecard(page: Page) -> None:
    expect(page.locator("#live-scorecard")).to_have_attribute("aria-busy", "false")


def test_landing_starts_with_a_real_unitrans_record(page: Page, base_url: str) -> None:
    artifact = _artifact("unitrans")
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    assert page.url == f"{base_url}/"
    expect(page.locator("#scorecard-agency")).to_contain_text("Unitrans")
    expect(page.locator("#scorecard-grade")).to_have_text(artifact["overall"]["grade"])
    expect(page.locator("#scorecard-score")).to_have_text(str(artifact["overall"]["score"]))
    expect(page.locator("#scorecard-date")).to_have_attribute("datetime", artifact["snapshot_date"])
    realtime = artifact["categories"]["realtime"]
    assert realtime["status"] == "not_yet_measured"
    expect(page.locator('[data-category="realtime"] .category-value')).to_have_text("Not measured")
    expect(page.locator('[data-category-row="realtime"] [role="meter"]')).to_have_count(0)
    expect(page.locator("#fix-selector button")).to_have_count(len(artifact["top_fixes"]))
    expect(page.locator("#trace-code")).to_have_text(artifact["top_fixes"][0]["code"])


def test_landing_puts_the_operating_workflow_before_the_scorecard(
    page: Page, base_url: str
) -> None:
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    expect(page.get_by_role("heading", level=1)).to_have_text(
        "Find the next fix in a published GTFS feed."
    )
    expect(page.locator(".desk-summary")).to_have_text(
        "Search an agency to open its latest scorecard and first recommended fix. "
        "You can also check a GTFS ZIP before publishing it."
    )
    expect(page.locator(".workflow-step")).to_have_count(6)
    expect(page.get_by_role("heading", name="Start with the work you need to do.")).to_be_visible()
    expect(page.get_by_role("link", name="Check a GTFS ZIP")).to_be_visible()
    expect(
        page.get_by_label("Reuse public evidence").get_by_role("link", name="Feed features")
    ).to_be_visible()

    workflow_box = page.locator(".workflow-run").bounding_box()
    tasks_box = page.locator(".task-board").bounding_box()
    scorecard_box = page.locator(".scorecard-demo").bounding_box()
    assert workflow_box is not None
    assert tasks_box is not None
    assert scorecard_box is not None
    assert workflow_box["y"] < scorecard_box["y"]
    assert tasks_box["y"] < scorecard_box["y"]


def test_landing_workflow_stacks_without_horizontal_overflow_on_mobile(
    page: Page, base_url: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    expect(page.get_by_role("heading", level=1)).to_be_visible()
    expect(page.locator(".workflow-run")).to_be_visible()
    expect(page.locator(".task-register > li")).to_have_count(4)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    ledger_box = page.locator(".hero-ledger").bounding_box()
    workflow_box = page.locator(".workflow-run").bounding_box()
    assert ledger_box is not None
    assert workflow_box is not None
    assert ledger_box["y"] < workflow_box["y"]


def test_landing_loads_and_caches_exact_coverage_counts(page: Page, base_url: str) -> None:
    requests = 0

    def fulfill_coverage(route: Route) -> None:
        nonlocal requests
        requests += 1
        route.fulfill(
            json={
                "configured_feed_records": 2185,
                "published_scorecard_pages": 1128,
                "country_count": 46,
            }
        )

    page.route("**/api/v1/coverage.json", fulfill_coverage)
    page.goto(f"{base_url}/")

    expect(page.locator("#coverage-registry-count")).to_have_text("2,185")
    expect(page.locator("#coverage-published-count")).to_have_text("1,128")
    expect(page.locator("#coverage-country-count")).to_have_text("46")
    assert requests == 1

    page.reload()
    expect(page.locator("#coverage-registry-count")).to_have_text("2,185")
    expect(page.locator("#coverage-published-count")).to_have_text("1,128")
    expect(page.locator("#coverage-country-count")).to_have_text("46")
    assert requests == 1


def test_landing_keeps_conservative_coverage_fallbacks_when_request_fails(
    page: Page, base_url: str
) -> None:
    page.route("**/api/v1/coverage.json", lambda route: route.abort())
    page.goto(f"{base_url}/")

    expect(page.locator("#coverage-registry-count")).to_have_text("2,100+")
    expect(page.locator("#coverage-published-count")).to_have_text("2,100+")
    expect(page.locator("#coverage-country-count")).to_have_text("40+")
    expect(page.locator(".coverage-ledger")).to_contain_text("Countries in registry")


def test_landing_switches_record_category_and_fix_without_reload(page: Page, base_url: str) -> None:
    artifact = _artifact("yolobus")
    first_fix = artifact["top_fixes"][0]["code"]
    third_fix = artifact["top_fixes"][2]["code"]
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    page.get_by_role("button", name="Yolobus").click()
    _wait_for_scorecard(page)
    expect(page.locator("#scorecard-agency")).to_contain_text("Yolobus")
    expect(page.locator("#scorecard-score")).to_have_text(str(artifact["overall"]["score"]))
    expect(page.locator('[data-category="realtime"] .category-value')).to_have_text(
        f"{artifact['categories']['realtime']['score']:g}"
    )
    expect(page.locator('[data-agency-id="yolobus"]')).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#scope-scorecard-link")).to_have_attribute(
        "href",
        f"/agency/yolobus/?finding={first_fix}#finding-handoff",
    )
    expect(page.locator("#scope-brief-link")).to_have_attribute(
        "href",
        f"/agency/yolobus/brief/?finding={first_fix}#finding-handoff",
    )

    page.locator('[data-category="realtime"]').click()
    expect(page.locator("#category-detail-summary")).to_contain_text("Sampled 9 times")

    page.locator('[data-fix-index="2"]').click()
    expect(page.locator("#trace-code")).to_have_text(third_fix)
    expect(page.locator("#trace-source-files")).to_contain_text("feed_info.txt")
    expect(page.locator("#scope-scorecard-link")).to_have_attribute(
        "href",
        f"/agency/yolobus/?finding={third_fix}#finding-handoff",
    )
    expect(page.locator("#scope-board-link")).to_have_attribute(
        "href",
        f"/agency/yolobus/board/?finding={third_fix}#finding-handoff",
    )
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
