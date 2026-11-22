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


def test_landing_is_search_places_doors_then_the_example(page: Page, base_url: str) -> None:
    """The short home of the 2026-11 IA (D6), in reading order."""
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    expect(page.get_by_role("heading", level=1)).to_have_text("GTFS feed quality, graded daily.")
    expect(page.locator(".desk-summary")).to_have_text(
        "Find an agency to see its grade, its feed URL, and the first things to fix."
    )
    expect(page.get_by_role("heading", name="Browse by place")).to_be_visible()
    expect(page.get_by_role("link", name="All states and countries")).to_have_attribute(
        "href", "/program/"
    )
    expect(page.get_by_role("heading", name="Start from what you do")).to_be_visible()
    expect(page.locator(".door-register > li")).to_have_count(3)
    expect(
        page.get_by_role("navigation", name="I work at a transit agency").get_by_role(
            "link", name="Watch your feed for free"
        )
    ).to_have_attribute("href", "/subscribe.html")
    expect(page.locator(".workflow-step")).to_have_count(0)

    search_box = page.locator("#feed-picker").bounding_box()
    places_box = page.locator(".place-chips").bounding_box()
    doors_box = page.locator(".task-board").bounding_box()
    scorecard_box = page.locator(".scorecard-demo").bounding_box()
    assert search_box and places_box and doors_box and scorecard_box
    assert search_box["y"] < places_box["y"] < doors_box["y"] < scorecard_box["y"]


def test_landing_stacks_without_horizontal_overflow_on_mobile(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    expect(page.get_by_role("heading", level=1)).to_be_visible()
    expect(page.locator("#feed-search")).to_be_visible()
    expect(page.locator(".door-register > li")).to_have_count(3)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_the_workflow_moved_to_how_to_read_with_its_anchors(page: Page, base_url: str) -> None:
    for anchor, heading in (
        ("workflow-run-h", "Where the scorecard fits in the work"),
        ("ecosystem", "Use the scorecard between discovery and the next feed export."),
        ("pilot", "Remediation workflow"),
    ):
        # A fresh load each time: a same-document hash change is not what a
        # reader following a link from another page gets.
        page.goto("about:blank")
        page.goto(f"{base_url}/how-to-read/#{anchor}")
        expect(page.locator(f"#{anchor}")).to_have_count(1)
        expect(page.get_by_role("heading", name=heading)).to_be_in_viewport()


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
    expect(page.locator("#full-scorecard-link")).to_have_attribute(
        "href",
        f"/agency/yolobus/#finding={first_fix}",
    )
    expect(page.locator("#brief-link")).to_have_attribute(
        "href",
        f"/agency/yolobus/brief/#finding={first_fix}",
    )

    page.locator('[data-category="realtime"]').click()
    expect(page.locator("#category-detail-summary")).to_contain_text("Sampled 9 times")

    page.locator('[data-fix-index="2"]').click()
    expect(page.locator("#trace-code")).to_have_text(third_fix)
    expect(page.locator("#trace-source-files")).to_contain_text("feed_info.txt")
    expect(page.locator("#full-scorecard-link")).to_have_attribute(
        "href",
        f"/agency/yolobus/#finding={third_fix}",
    )
    expect(page.locator("#trace-record-link")).to_have_attribute(
        "href",
        f"/agency/yolobus/#finding={third_fix}",
    )
    assert "feed=yolobus" in page.url
    assert "fix=3" in page.url


def test_landing_search_lazily_opens_another_published_feed(page: Page, base_url: str) -> None:
    requested: list[str] = []
    page.on("request", lambda request: requested.append(request.url))
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)
    assert not any(url.endswith("/data/agency-index.json") for url in requested)

    search = page.locator("#feed-search")
    search.fill("ABQ RIDE")
    first = page.locator("#feed-results [role=option]").first
    expect(first).to_be_visible()
    expect(page.locator("#picker-status")).to_contain_text(re.compile(r"match"))
    assert any(url.endswith("/data/agency-index.json") for url in requested)
    assert not any(url.endswith("/api/v1/ids.json") for url in requested)
    assert not any(url.endswith("/api/v1/agencies.json") for url in requested)
    assert not any(url.endswith("/data/artifacts/directory.json") for url in requested)

    # A chosen suggestion opens the agency's own page, not the example below.
    first.click()
    page.wait_for_url(re.compile(r"/agency/abq-ride/$"))


def test_landing_controls_keep_keyboard_focus(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    _wait_for_scorecard(page)

    pilot = page.get_by_role("button", name="Yolobus")
    pilot.focus()
    page.keyboard.press("Enter")
    _wait_for_scorecard(page)
    assert pilot.evaluate("element => element === document.activeElement")
    expect(pilot).to_have_attribute("aria-pressed", "true")

    search = page.locator("#feed-search")
    search.focus()
    page.keyboard.type("unitrans")
    first = page.locator("#feed-results [role=option]").first
    expect(first).to_be_visible()
    page.keyboard.press("ArrowDown")
    # The combobox pattern: focus stays in the field and the active option is
    # named by aria-activedescendant.
    expect(first).to_have_attribute("aria-selected", "true")
    expect(search).to_have_attribute("aria-activedescendant", first.get_attribute("id") or "")
    assert search.evaluate("element => element === document.activeElement")


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


# --- the paid tier, as a reader actually meets it on the landing page -------


def _plan() -> dict[str, Any]:
    """The single source of every price on the site (ADR 0049)."""
    return cast(
        dict[str, Any],
        json.loads((Path(__file__).resolve().parents[3] / "web/bundle/plan.json").read_text()),
    )


def test_landing_shows_every_plan_price_read_from_plan_json(page: Page, base_url: str) -> None:
    """The home page states what the one paid add-on costs, and states it from
    plan.json rather than from copy. The literals here are computed from that
    file, so a price change moves the page and this assertion together and
    neither can quietly disagree with the checkout."""
    plan = _plan()
    assert plan["paymentsAvailable"] is True, "this test describes the tier while it is open"
    page.goto(f"{base_url}/")

    # plan-summary.js stamps the root element when it has finished reading the
    # plan, which is what tells "the tier is off" apart from "the fetch has not
    # landed yet" — two states that look identical in a screenshot.
    expect(page.locator("html")).to_have_attribute("data-plan-summary", "rendered")
    tiles = page.locator("#programs .plan-tile")
    expect(tiles).to_have_count(len(plan["products"]))
    for key, product in plan["products"].items():
        tile = page.locator(f'#programs .plan-tile[data-plan="{key}"]')
        expect(tile.locator(".plan-tile-name")).to_have_text(product["label"])
        amount = f"${product['price']:,}"
        expected = f"{amount} per {product['interval']}" if product["interval"] else amount
        expect(tile.locator(".plan-tile-price")).to_have_text(expected)


def test_landing_states_the_delivery_and_refund_commitment(page: Page, base_url: str) -> None:
    plan = _plan()
    page.goto(f"{base_url}/")
    status = page.locator("#programs [data-plan-status]")
    expect(status).to_contain_text(f"{plan['provisioning_business_days']} business days")
    expect(status).to_contain_text("refunded if it is later than that")


def test_landing_sends_a_buyer_to_the_bundle_page_and_never_straight_to_checkout(
    page: Page, base_url: str
) -> None:
    """A checkout link on the home page would skip the page that states
    delivery, the refund, how long the link lives, and what a purchase does not
    buy. The landing page describes the tier; /bundle/ sells it."""
    page.goto(f"{base_url}/")
    expect(page.locator('#programs a[href="/bundle/"]')).to_have_count(1)
    assert page.locator("#programs a").count() == 1
    assert "buy.stripe.com" not in page.content()


def test_landing_never_shows_a_stale_price_when_the_plan_cannot_be_read(
    page: Page, base_url: str
) -> None:
    """An unreadable plan must leave no amount standing anywhere on the page."""
    page.route("**/bundle/plan.json", lambda route: route.fulfill(status=500, body=""))
    page.goto(f"{base_url}/")
    expect(page.locator("html")).to_have_attribute("data-plan-summary", "unavailable")
    expect(page.locator("#programs [data-plan-status]")).to_contain_text(
        "Paid bundles are not available right now"
    )
    expect(page.locator("#programs .plan-tile")).to_have_count(0)
    for product in _plan()["products"].values():
        assert f"${product['price']:,}" not in page.content()
