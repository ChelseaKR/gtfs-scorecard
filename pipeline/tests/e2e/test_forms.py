"""Error recovery for the public forms and mobile appearance controls."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, expect

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
