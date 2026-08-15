"""Error recovery for the public forms and mobile appearance controls."""

from __future__ import annotations

import json
import re

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.e2e


def test_static_compare_search_filters_large_pickers(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/compare/")

    page.locator("#compare-a-filter").fill("unitrans")
    expect(page.locator("#compare-a option")).to_have_count(2)
    page.locator("#compare-a").select_option("unitrans")

    page.locator("#compare-b-filter").fill("yolobus")
    expect(page.locator("#compare-b option")).to_have_count(3)
    page.locator("#compare-b").select_option("yolobus")
    page.get_by_role("button", name="Compare").click()

    status = page.locator("#compare-status")
    expect(status).to_contain_text(re.compile(r"Comparing Unitrans|Scorecards kept separate"))
    assert "a=unitrans" in page.url and "b=yolobus" in page.url
    if (status.text_content() or "").startswith("Comparing Unitrans"):
        expect(page.locator(".table-scroll-hint")).to_be_visible()
        expect(page.locator(".compare-static-table")).to_be_visible()


def test_compare_pickers_fill_in_from_the_published_list(page: Page, base_url: str) -> None:
    """The document ships an opening window; reaching for the form brings the rest.

    Both selects used to inline every agency, so the page grew with the
    registry. The full list now arrives from /compare/agencies.json on first
    contact with the form, which has to leave the pickers usable and say so.
    """
    page.goto(f"{base_url}/compare/")

    # The document itself carries only the window, not the whole catalog.
    inlined = page.evaluate("() => document.querySelectorAll('#compare-a option').length")
    assert inlined <= 51, f"the document still inlines {inlined} options"

    # Touching the form is the trigger; no click on the load button needed.
    page.locator("#compare-a-filter").click()
    expect(page.locator("#compare-picker-status")).to_contain_text(
        re.compile(r"Both lists now hold all \d+ agencies")
    )
    hydrated = page.evaluate("() => document.querySelectorAll('#compare-a option').length")
    assert hydrated > inlined
    # An agency well past the opening window is now selectable.
    page.locator("#compare-a-filter").fill("unitrans")
    expect(page.locator("#compare-a option")).to_have_count(2)


def test_compare_load_button_fills_the_lists_and_moves_focus(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/compare/")
    load = page.get_by_role("button", name="Load every agency")
    expect(load).to_be_visible()
    load.click()

    expect(page.locator("#compare-picker-status")).to_contain_text(
        re.compile(r"Both lists now hold all \d+ agencies")
    )
    # The button it came from is gone, so focus lands on the first picker
    # instead of falling back to the document.
    expect(load).to_be_hidden()
    assert page.evaluate("() => document.activeElement.id") == "compare-a-filter"


def test_compare_load_button_never_strands_keyboard_focus(page: Page, base_url: str) -> None:
    """The load control hides once the list is in, so focus has to follow it.

    Reaching for a picker starts the load, which means a keyboard can already
    be resting on the button when it disappears. Focus moves to the first
    picker instead of falling back to the document.
    """

    def slow(route: Route) -> None:
        page.wait_for_timeout(600)
        route.continue_()

    page.route("**/compare/agencies.json", slow)
    page.goto(f"{base_url}/compare/")

    # Tab in from the top of the form; the load control is still there because
    # the list it would fetch has not arrived yet.
    page.locator("#compare-a-filter").focus()
    for _ in range(5):
        page.keyboard.press("Tab")
        if page.evaluate("() => document.activeElement.id") == "compare-load":
            break
    assert page.evaluate("() => document.activeElement.id") == "compare-load"

    expect(page.locator("#compare-picker-status")).to_contain_text(
        re.compile(r"Both lists now hold all \d+ agencies")
    )
    expect(page.get_by_role("button", name="Load every agency")).to_be_hidden()
    assert page.evaluate("() => document.activeElement.id") == "compare-a-filter"


def test_compare_says_so_and_offers_a_retry_when_the_list_fails(page: Page, base_url: str) -> None:
    page.route("**/compare/agencies.json", lambda route: route.abort())
    page.goto(f"{base_url}/compare/")

    page.get_by_role("button", name="Load every agency").click()
    expect(page.locator("#compare-picker-status")).to_contain_text(
        "The complete agency list could not load."
    )
    # The opening options and a keyboard-reachable retry both survive.
    retry = page.get_by_role("button", name="Try loading every agency again")
    expect(retry).to_be_visible()
    assert page.evaluate("() => document.querySelectorAll('#compare-a option').length") > 1


def test_compare_shared_link_reads_back_without_the_full_list(page: Page, base_url: str) -> None:
    """A shared comparison renders and names both agencies in the pickers,
    without pulling the picker list it does not need."""
    requested: list[str] = []
    page.on("request", lambda request: requested.append(request.url))
    page.goto(f"{base_url}/compare/?a=unitrans&b=yolobus")

    expect(page.locator("#compare-status")).to_contain_text(
        re.compile(r"Comparing|Scorecards kept separate")
    )
    assert page.locator("#compare-a").input_value() == "unitrans"
    assert page.locator("#compare-b").input_value() == "yolobus"
    assert not [url for url in requested if url.endswith("/compare/agencies.json")]


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


def test_instant_score_result_url_cannot_execute_a_script_url(page: Page, base_url: str) -> None:
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
            body = {"job_id": "abcdefgh", "status": "pending"}
            route.fulfill(status=202, content_type="application/json", body=json.dumps(body))
            return
        # A misbehaving or compromised backend must not turn a result link into
        # a clickable javascript: URL; try.js routes it through the same
        # safeUrl() guard app.js uses for every dynamic href.
        body = {
            "job_id": "abcdefgh",
            "status": "done",
            "grade": "B",
            "result_url": 'javascript:window.__pwned=1//"',
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route(re.compile(r"/__instant(?:/.*)?$"), score)
    page.goto(f"{base_url}/try.html")
    page.locator("#try-url").fill("https://example.org/gtfs.zip")
    page.locator("#try-country").fill("us")
    page.get_by_role("button", name="Score this feed").click()

    link = page.get_by_role("link", name="View the full result")
    expect(link).to_be_visible(timeout=6_000)
    href = link.get_attribute("href") or ""
    assert not href.lower().startswith("javascript:")
    assert page.evaluate("() => window.__pwned") is None


def test_instant_score_artifact_grade_cannot_inject_attributes(page: Page, base_url: str) -> None:
    page.route(
        "**/src/config.js",
        lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body='window.SCORECARD_TRY_URL = "/__instant";',
        ),
    )
    hostile_grade = 'A" onmouseover="window.__pwned=1'

    def score(route: Route) -> None:
        if route.request.method == "POST":
            route.fulfill(
                status=202,
                content_type="application/json",
                body=json.dumps({"job_id": "abcdefgh", "status": "pending"}),
            )
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "job_id": "abcdefgh",
                    "status": "done",
                    "grade": "A",
                    "result_url": "/__artifact",
                }
            ),
        )

    page.route(re.compile(r"/__instant(?:/.*)?$"), score)
    page.route(
        "**/__artifact",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "overall": {"grade": hostile_grade, "score": 91},
                    "categories": {},
                    "top_fixes": [],
                }
            ),
        ),
    )
    page.goto(f"{base_url}/try.html")
    page.locator("#try-url").fill("https://example.org/gtfs.zip")
    page.locator("#try-country").fill("us")
    page.get_by_role("button", name="Score this feed").click()

    chip = page.locator(".grade-chip")
    expect(chip).to_be_visible(timeout=6_000)
    expect(chip).to_have_class("grade-chip grade-f")
    expect(chip).to_contain_text(hostile_grade)
    expect(page.locator("[onmouseover]")).to_have_count(0)
    assert page.evaluate("() => window.__pwned") is None


def test_mobile_theme_and_menu_keyboard_recovery(page: Page, app_url: str) -> None:
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{app_url}#/")
    menu = page.get_by_role("button", name="Menu")
    menu.click()
    expect(menu).to_have_attribute("aria-expanded", "true")

    theme = page.locator("#theme-toggle-btn")
    expect(theme).to_have_accessible_name("Theme: System")
    expect(theme).to_have_attribute("aria-haspopup", "menu")
    expect(theme).to_have_attribute("aria-controls", "theme-menu")

    theme.press("ArrowDown")
    expect(theme).to_have_attribute("aria-expanded", "true")
    expect(page.get_by_role("menuitemradio", name="System")).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(page.get_by_role("menuitemradio", name="Light")).to_be_focused()
    page.keyboard.press("End")
    expect(page.get_by_role("menuitemradio", name="Dark")).to_be_focused()
    page.keyboard.press("Home")
    expect(page.get_by_role("menuitemradio", name="System")).to_be_focused()
    page.keyboard.press("ArrowUp")
    expect(page.get_by_role("menuitemradio", name="Dark")).to_be_focused()
    page.keyboard.press("Escape")
    expect(theme).to_have_attribute("aria-expanded", "false")
    expect(theme).to_be_focused()
    # The theme menu consumes its own Escape instead of also closing the
    # containing mobile navigation and moving focus to that menu's trigger.
    expect(menu).to_have_attribute("aria-expanded", "true")

    theme.click()
    page.get_by_role("menuitemradio", name="High contrast").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "contrast")
    expect(theme).to_have_accessible_name("Theme: High contrast")
    assert page.evaluate("() => document.activeElement.id") == "theme-toggle-btn"

    page.keyboard.press("Escape")
    expect(menu).to_have_attribute("aria-expanded", "false")
    assert page.evaluate("() => document.activeElement.classList.contains('nav-menu-btn')")
