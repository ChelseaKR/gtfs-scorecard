"""The two find-as-you-type agency pickers, driven the way people use them.

Both the home page search and the alerts signup form use the shared picker in
web/src/agency-combobox.js (the WAI-ARIA 1.2 combobox pattern) over the small
agency index at /data/agency-index.json. These tests drive them by keyboard
only and by pointer, read what assistive technology is told (roles, names,
aria-expanded, aria-activedescendant, the live region), and check that both
fields still work as plain fields with JavaScript off.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Browser, Page, Route, expect

pytestmark = pytest.mark.e2e

INDEX = Path(__file__).resolve().parents[3] / "web" / "data" / "agency-index.json"


def _index_rows() -> list[list[str]]:
    rows: list[list[str]] = json.loads(INDEX.read_text())["agencies"]
    return rows


def _name(agency_id: str) -> str:
    return next(row[1] for row in _index_rows() if row[0] == agency_id)


def _requested(page: Page) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url))
    return seen


# --- home page search ---------------------------------------------------------


def test_home_search_is_an_accessible_combobox_that_loads_its_index_lazily(
    page: Page, base_url: str
) -> None:
    requested = _requested(page)
    page.goto(f"{base_url}/")
    combobox = page.get_by_role("combobox", name="Find a published feed")
    expect(combobox).to_have_attribute("aria-expanded", "false")
    expect(combobox).to_have_attribute("aria-autocomplete", "list")
    assert not any(url.endswith("/data/agency-index.json") for url in requested)

    combobox.click()
    page.keyboard.type("yolobus")
    listbox = page.get_by_role("listbox", name="Matching scorecards")
    expect(listbox).to_be_visible()
    expect(combobox).to_have_attribute("aria-expanded", "true")
    expect(combobox).to_have_attribute("aria-controls", "feed-results")
    option = listbox.get_by_role("option", name=re.compile(r"Yolobus"))
    expect(option.first).to_be_visible()
    expect(page.locator("#picker-status")).to_have_text(
        re.compile(r"^(1 match\. Choose it|\d+ matches\. Choose one)")
    )
    assert any(url.endswith("/data/agency-index.json") for url in requested)
    # Neither the history index nor the feed-URL crosswalk is needed to suggest a name.
    assert not any(url.endswith("/data/artifacts/index.json") for url in requested)
    assert not any(url.endswith("/api/v1/ids.json") for url in requested)


def test_home_keyboard_only_choice_opens_the_agency_page(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    combobox = page.get_by_role("combobox", name="Find a published feed")
    combobox.focus()
    page.keyboard.type("yolobus")
    expect(page.get_by_role("listbox", name="Matching scorecards")).to_be_visible()

    page.keyboard.press("ArrowDown")
    first = page.locator("#feed-results [role=option]").first
    expect(first).to_have_attribute("aria-selected", "true")
    expect(combobox).to_have_attribute("aria-activedescendant", first.get_attribute("id") or "")
    # Focus never leaves the text field while moving through the options.
    assert combobox.evaluate("element => element === document.activeElement")

    page.keyboard.press("ArrowUp")
    last = page.locator("#feed-results [role=option]").last
    expect(last).to_have_attribute("aria-selected", "true")
    page.keyboard.press("ArrowDown")
    expect(first).to_have_attribute("aria-selected", "true")

    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r"/agency/yolobus/$"))


def test_home_enter_on_a_clear_name_goes_straight_to_the_agency_page(
    page: Page, base_url: str
) -> None:
    page.goto(f"{base_url}/")
    combobox = page.get_by_role("combobox", name="Find a published feed")
    combobox.fill(_name("abq-ride").lower())
    combobox.press("Enter")
    page.wait_for_url(re.compile(r"/agency/abq-ride/$"))


def test_home_pointer_choice_opens_the_agency_page(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    combobox = page.get_by_role("combobox", name="Find a published feed")
    combobox.fill("PATCO Speedline")
    page.locator("#feed-results [role=option][id]").filter(has_text="patco-speedline-3035").click()
    page.wait_for_url(re.compile(r"/agency/patco-speedline-3035/$"))


def test_home_ambiguous_query_keeps_the_results_page(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    combobox = page.get_by_role("combobox", name="Find a published feed")
    combobox.fill("transit")
    expect(page.get_by_role("listbox", name="Matching scorecards")).to_be_visible()
    page.get_by_role("button", name="Find").click()
    page.wait_for_url(re.compile(r"/app/#/\?q=transit$"))


def test_home_says_when_nothing_matches_and_escape_closes(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    combobox = page.get_by_role("combobox", name="Find a published feed")
    combobox.fill("zzqqxx")
    expect(page.locator("#picker-status")).to_have_text(
        "No published scorecard matches that search."
    )
    expect(combobox).to_have_attribute("aria-expanded", "false")

    combobox.fill("yolo")
    expect(page.locator("#feed-results")).to_be_visible()
    combobox.press("Escape")
    expect(page.locator("#feed-results")).to_be_hidden()
    expect(combobox).to_have_attribute("aria-expanded", "false")
    expect(page.locator("#picker-status")).to_have_text("Search results closed.")


def test_home_search_without_javascript_submits_to_the_results_page(
    browser: Browser, base_url: str
) -> None:
    context = browser.new_context(java_script_enabled=False, service_workers="block")
    try:
        page = context.new_page()
        page.goto(f"{base_url}/")
        field = page.get_by_role("searchbox", name="Find a published feed")
        field.fill("yolobus")
        field.press("Enter")
        page.wait_for_url(re.compile(r"/app/\?q=yolobus$"))
    finally:
        context.close()


# --- alerts signup form -------------------------------------------------------


_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}
_ACCEPTED = {"message": "Check your email to confirm your subscription."}


def _stub_subscribe(page: Page, *, hold: list[Route] | None = None) -> list[dict[str, Any]]:
    """Answer POST <api>/subscribe locally and record each request body.

    With `hold`, accepted requests are parked there unanswered, so a test can
    look at the form while the request is still out and answer it later."""
    bodies: list[dict[str, Any]] = []

    def _answer(route: Route) -> None:
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=_CORS)
            return
        bodies.append(json.loads(route.request.post_data or "{}"))
        if hold is not None:
            hold.append(route)
            return
        route.fulfill(status=200, json=_ACCEPTED, headers=_CORS)

    page.route(re.compile(r"/subscribe$"), _answer)
    return bodies


def test_alerts_agency_field_is_an_accessible_combobox(page: Page, base_url: str) -> None:
    requested = _requested(page)
    page.goto(f"{base_url}/subscribe.html")
    combobox = page.get_by_role("combobox", name="Which agency?")
    expect(combobox).to_have_attribute("aria-expanded", "false")
    expect(combobox).to_have_value("")
    expect(combobox).to_have_accessible_description(re.compile(r"^Type a name and pick it"))

    combobox.focus()
    page.keyboard.type("unitrans")
    listbox = page.get_by_role("listbox", name="Which agency?")
    expect(listbox).to_be_visible()
    unitrans = listbox.get_by_role("option", name=re.compile(r"Unitrans .*Feed ID unitrans"))
    expect(unitrans).to_be_visible()
    expect(page.locator("#agency-status")).to_have_text(re.compile(r"agenc(y|ies) match"))
    # The full history index is never downloaded to list names.
    assert not any(url.endswith("/data/artifacts/index.json") for url in requested)


def test_alerts_keyboard_only_signup_for_one_agency(page: Page, base_url: str) -> None:
    bodies = _stub_subscribe(page)
    page.goto(f"{base_url}/subscribe.html")
    page.locator("#email").focus()
    page.keyboard.type("person@agency.gov")
    page.keyboard.press("Tab")
    combobox = page.get_by_role("combobox", name="Which agency?")
    assert combobox.evaluate("element => element === document.activeElement")
    page.keyboard.type("yolobus")
    expect(page.get_by_role("listbox", name="Which agency?")).to_be_visible()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    expect(combobox).to_have_value(_name("yolobus"))
    expect(combobox).to_have_attribute("aria-expanded", "false")

    page.keyboard.press("Enter")  # implicit submission from the text field
    expect(page.locator("#form-status")).to_have_text(_ACCEPTED["message"])
    assert bodies == [
        {
            "email": "person@agency.gov",
            "agencies": ["yolobus"],
            "kinds": ["expiry", "lapse_risk", "regression", "export_change", "anomaly"],
        }
    ]


def test_alerts_all_agencies_is_offered_but_never_the_default(page: Page, base_url: str) -> None:
    bodies = _stub_subscribe(page)
    page.goto(f"{base_url}/subscribe.html")
    page.locator("#email").fill("person@agency.gov")
    page.get_by_role("button", name="Email me alerts").click()

    combobox = page.get_by_role("combobox", name="Which agency?")
    expect(combobox).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#form-status")).to_have_text(
        "Choose an agency from the list, or choose All agencies."
    )
    assert combobox.evaluate("element => element === document.activeElement")
    assert bodies == []

    # Type and clear, then press Down before the typing pause has passed: the
    # list must still open on the every-agency option.
    page.keyboard.type("yo")
    combobox.fill("")
    page.keyboard.press("ArrowDown")
    option = page.get_by_role("option", name="All agencies")
    expect(option).to_have_attribute("aria-selected", "true")
    # The lone every-agency option is not announced as an agency count.
    expect(page.locator("#agency-status")).to_have_text("")
    page.keyboard.press("Enter")
    expect(combobox).to_have_value("All agencies")
    expect(combobox).not_to_have_attribute("aria-invalid", "true")
    page.get_by_role("button", name="Email me alerts").click()
    expect(page.locator("#form-status")).to_have_text(_ACCEPTED["message"])
    assert bodies[0]["all"] is True
    assert "agencies" not in bodies[0]


def test_alerts_link_from_an_agency_page_arrives_with_the_agency_chosen(
    page: Page, base_url: str
) -> None:
    bodies = _stub_subscribe(page)
    page.goto(f"{base_url}/subscribe.html?agency=unitrans")
    combobox = page.get_by_role("combobox", name="Which agency?")
    expect(combobox).to_have_value(_name("unitrans"))
    page.locator("#email").fill("person@agency.gov")
    page.get_by_role("button", name="Email me alerts").click()
    expect(page.locator("#form-status")).to_have_text(_ACCEPTED["message"])
    assert bodies[0]["agencies"] == ["unitrans"]


def test_alerts_sends_once_however_often_the_button_is_pressed(page: Page, base_url: str) -> None:
    held: list[Route] = []
    bodies = _stub_subscribe(page, hold=held)
    page.goto(f"{base_url}/subscribe.html?agency=yolobus")
    expect(page.get_by_role("combobox", name="Which agency?")).to_have_value(_name("yolobus"))
    page.locator("#email").fill("person@agency.gov")
    button = page.get_by_role("button", name="Email me alerts")
    button.click()
    expect(page.locator("#form-status")).to_have_text("Sending…")
    expect(button).to_be_disabled()
    expect(page.locator("#subscribe-form")).to_have_attribute("aria-busy", "true")
    button.click(force=True)
    page.locator("#email").press("Enter")
    page.wait_for_timeout(200)
    assert len(bodies) == 1

    held[0].fulfill(status=200, json=_ACCEPTED, headers=_CORS)
    expect(page.locator("#form-status")).to_have_text(_ACCEPTED["message"])
    expect(button).to_be_enabled()
    expect(page.locator("#subscribe-form")).not_to_have_attribute("aria-busy", "true")

    # Pressing again with nothing changed repeats the answer instead of
    # asking the API for a second confirmation it would refuse.
    button.click()
    expect(page.locator("#form-status")).to_have_text(_ACCEPTED["message"])
    assert len(bodies) == 1


def test_alerts_typed_full_name_counts_as_a_choice(page: Page, base_url: str) -> None:
    bodies = _stub_subscribe(page)
    page.goto(f"{base_url}/subscribe.html")
    page.locator("#email").fill("person@agency.gov")
    page.get_by_role("combobox", name="Which agency?").fill("abq ride")
    page.get_by_role("button", name="Email me alerts").click()
    expect(page.locator("#form-status")).to_have_text(_ACCEPTED["message"])
    assert bodies[0]["agencies"] == ["abq-ride"]


def test_alerts_agency_field_without_javascript_is_a_labeled_text_box(
    browser: Browser, base_url: str
) -> None:
    context = browser.new_context(java_script_enabled=False, service_workers="block")
    try:
        page = context.new_page()
        page.goto(f"{base_url}/subscribe.html")
        field = page.get_by_role("textbox", name="Which agency?")
        expect(field).to_be_visible()
        expect(field).to_be_editable()
        expect(page.get_by_role("combobox")).to_have_count(0)
        expect(page.locator("#agency-options")).to_be_hidden()
    finally:
        context.close()


def test_alerts_catches_an_address_the_api_would_refuse(page: Page, base_url: str) -> None:
    bodies = _stub_subscribe(page)
    page.goto(f"{base_url}/subscribe.html?agency=unitrans")
    expect(page.get_by_role("combobox", name="Which agency?")).to_have_value(_name("unitrans"))
    email = page.locator("#email")
    email.fill("person@agency")  # the browser accepts it; the API does not
    page.get_by_role("button", name="Email me alerts").click()
    expect(page.locator("#form-status")).to_have_text(
        "Enter a complete email address, like you@agency.gov."
    )
    expect(email).to_have_attribute("aria-invalid", "true")
    assert bodies == []
