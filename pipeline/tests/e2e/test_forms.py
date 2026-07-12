"""Error recovery for the public forms and mobile appearance controls."""

from __future__ import annotations

import json
import re

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.e2e


def test_alert_form_identifies_and_focuses_invalid_fields(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/subscribe.html")
    page.get_by_role("button", name="Email me alerts").click()

    email = page.locator("#email")
    expect(email).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#form-status")).to_have_text("Enter your email.")
    expect(page.locator("#form-status")).to_have_class("form-status form-status-err")
    assert page.evaluate("() => document.activeElement.id") == "email"

    email.fill("person@agency.gov")
    for checkbox in page.locator('input[name="kinds"]').all():
        checkbox.uncheck()
    page.get_by_role("button", name="Email me alerts").click()
    expect(page.locator("#form-status")).to_have_text("Choose at least one kind of alert.")
    assert page.evaluate("() => document.activeElement.name") == "kinds"


def test_agency_submission_focuses_the_first_invalid_field(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/submit.html")
    page.get_by_role("button", name="Submit my agency").click()
    expect(page.locator("#name")).to_have_attribute("aria-invalid", "true")
    assert page.evaluate("() => document.activeElement.id") == "name"

    page.locator("#name").fill("Example Transit")
    page.locator("#static_gtfs_url").fill("not a URL")
    page.get_by_role("button", name="Submit my agency").click()
    expect(page.locator("#static_gtfs_url")).to_have_attribute("aria-invalid", "true")
    assert page.evaluate("() => document.activeElement.id") == "static_gtfs_url"


def test_submission_requires_a_complete_subdivision_pair(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/submit.html")
    page.locator("#name").fill("Example Transit")
    page.locator("#static_gtfs_url").fill("https://example.org/gtfs.zip")
    page.locator("#country").fill("CA")
    page.locator("#subdivision_code").fill("CA-ON")
    page.get_by_role("button", name="Submit my agency").click()

    expect(page.locator("#subdivision_name")).to_have_attribute("aria-invalid", "true")
    assert page.evaluate("() => document.activeElement.id") == "subdivision_name"
    expect(page.locator("#form-status")).to_contain_text("both the subdivision code and name")


def test_instant_score_carries_country_into_tracking_handoff(page: Page, base_url: str) -> None:
    submitted: list[dict[str, object]] = []

    page.route(
        "**/src/config.js",
        lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body='window.SCORECARD_TRY_URL = "/__instant";',
        ),
    )

    def score(route: Route) -> None:
        request = route.request
        if request.method == "POST":
            payload = request.post_data_json
            assert isinstance(payload, dict)
            submitted.append(payload)
            body = {"job_id": "abcdefgh", "status": "pending"}
            route.fulfill(status=202, content_type="application/json", body=json.dumps(body))
            return
        body = {"job_id": "abcdefgh", "status": "done", "grade": "B"}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route(re.compile(r"/__instant(?:/.*)?$"), score)
    page.goto(f"{base_url}/try.html")

    country = page.locator("#try-country")
    expect(country).to_have_value("")
    expect(country).to_have_attribute("required", "")
    page.locator("#try-url").fill("https://example.org/gtfs.zip")
    page.locator("#try-name").fill("Example Transit")
    page.get_by_role("button", name="Score this feed").click()
    expect(country).to_have_attribute("aria-invalid", "true")
    assert page.evaluate("() => document.activeElement.id") == "try-country"

    country.fill("ca")
    page.get_by_role("button", name="Score this feed").click()

    track = page.get_by_role("link", name="Track this feed daily")
    expect(track).to_be_visible(timeout=6_000)
    assert submitted == [
        {
            "url": "https://example.org/gtfs.zip",
            "name": "Example Transit",
            "country": "CA",
        }
    ]
    expect(track).to_have_attribute(
        "href",
        "submit.html?url=https%3A%2F%2Fexample.org%2Fgtfs.zip&name=Example%20Transit&country=CA",
    )
    track.click()
    expect(page.locator("#country")).to_have_value("CA")


def test_mobile_theme_and_menu_keyboard_recovery(page: Page, app_url: str) -> None:
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{app_url}#/")
    menu = page.get_by_role("button", name="Menu")
    menu.click()
    expect(menu).to_have_attribute("aria-expanded", "true")

    theme = page.locator("#theme-toggle-btn")
    expect(theme).to_have_accessible_name("Theme: System")
    theme.click()
    page.get_by_role("menuitemradio", name="High contrast").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "contrast")
    expect(theme).to_have_accessible_name("Theme: High contrast")
    assert page.evaluate("() => document.activeElement.id") == "theme-toggle-btn"

    page.keyboard.press("Escape")
    expect(menu).to_have_attribute("aria-expanded", "false")
    assert page.evaluate("() => document.activeElement.classList.contains('nav-menu-btn')")
