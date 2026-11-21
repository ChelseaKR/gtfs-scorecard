"""The alerts form with JavaScript off, and when the alerts API refuses a request.

Without JavaScript the form cannot send (the API takes JSON only), but it must
not put the reader's address in the page address either, where it would land in
browser history and server logs. When the API refuses a request, the reader
sees the form's own sentence and the field it is about, never the API's terse
text such as "invalid agency id: 'x'".
"""

from __future__ import annotations

import re
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Browser, Page, Route, expect

pytestmark = pytest.mark.e2e

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}


def _refuse(page: Page, status: int, reply: dict[str, Any]) -> None:
    def _answer(route: Route) -> None:
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=_CORS)
            return
        route.fulfill(status=status, json=reply, headers=_CORS)

    page.route(re.compile(r"/subscribe$"), _answer)


def _send(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/subscribe.html?agency=unitrans")
    expect(page.get_by_role("combobox", name="Which agency?")).to_have_value(
        re.compile(r"Unitrans")
    )
    page.locator("#email").fill("person@agency.gov")
    page.get_by_role("button", name="Email me alerts").click()


def test_without_javascript_the_address_never_goes_into_the_page_address(
    browser: Browser, base_url: str
) -> None:
    context = browser.new_context(java_script_enabled=False, service_workers="block")
    try:
        page = context.new_page()
        page.goto(f"{base_url}/subscribe.html")
        # (Playwright's text matching skips noscript, so the note is found by tag.)
        note = page.locator("#subscribe-form noscript p")
        expect(note).to_be_visible()
        expect(note).to_have_text(
            "Sending this form needs JavaScript. With it turned off, nothing is sent."
        )
        page.locator("#email").fill("person@agency.gov")
        page.locator("#agency").fill("unitrans")
        with page.expect_request(lambda request: "/subscribe.html" in request.url) as sent:
            page.get_by_role("button", name="Email me alerts").click()
        request = sent.value
        assert request.method == "POST"
        assert "person" not in request.url and "email=" not in request.url
    finally:
        context.close()


@pytest.mark.parametrize(
    ("reply", "message", "field"),
    [
        # The codes the API sends since this change ...
        (
            {"error": "a valid email is required", "code": "email"},
            "Enter a complete email address, like you@agency.gov.",
            "#email",
        ),
        (
            {"error": "invalid agency id: 'x'", "code": "agency"},
            "Choose an agency from the list, or choose All agencies.",
            "#agency",
        ),
        (
            {"error": "unknown alert kind(s): ['x']", "code": "kinds"},
            "Choose at least one kind of alert.",
            'input[name="kinds"]',
        ),
        # ... and the bare text the API sent before it, until it is redeployed.
        (
            {"error": "a valid email is required"},
            "Enter a complete email address, like you@agency.gov.",
            "#email",
        ),
        (
            {"error": "too many agencies"},
            "Choose an agency from the list, or choose All agencies.",
            "#agency",
        ),
        ({"error": "invalid JSON"}, "Something went wrong. Please try again.", None),
    ],
)
def test_a_refusal_reads_as_the_form_and_marks_its_field(
    page: Page, base_url: str, reply: dict[str, str], message: str, field: str | None
) -> None:
    _refuse(page, 400, reply)
    _send(page, base_url)
    status = page.locator("#form-status")
    expect(status).to_have_text(message)
    if field:
        target = page.locator(field).first
        expect(target).to_have_attribute("aria-invalid", "true")
        assert target.evaluate("element => element === document.activeElement")
    else:
        expect(page.locator("[aria-invalid]")).to_have_count(0)


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (
            {"error": "A confirmation email was just sent. Check your inbox.", "code": "cooldown"},
            "We just sent a confirmation to this address. Check your inbox and spam folder,"
            " or try again in 15 minutes.",
        ),
        (
            {"error": "A confirmation email was just sent. Check your inbox."},
            "We just sent a confirmation to this address. Check your inbox and spam folder,"
            " or try again in 15 minutes.",
        ),
        (
            {"error": "Too many requests. Try again later.", "code": "rate"},
            "Too many requests. Try again later.",
        ),
        ({}, "Too many requests. Try again later."),
    ],
)
def test_a_repeat_or_a_flood_reads_as_the_form(
    page: Page, base_url: str, reply: dict[str, str], message: str
) -> None:
    _refuse(page, 429, reply)
    _send(page, base_url)
    expect(page.locator("#form-status")).to_have_text(message)


def test_an_unexpected_refusal_never_shows_the_api_text(page: Page, base_url: str) -> None:
    _refuse(page, 403, {"error": "forbidden"})
    _send(page, base_url)
    expect(page.locator("#form-status")).to_have_text("Something went wrong. Please try again.")


# --- the confirmed reader back on the site (docs/decisions/0083) ----------------


def test_a_plain_visit_shows_no_confirmation_note(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/subscribe.html")
    expect(page.locator("#confirmed")).to_be_hidden()


def test_a_confirmed_reader_sees_the_note_and_one_named_step_is_announced(
    page: Page, base_url: str
) -> None:
    page.add_init_script(
        "window.__leads = [];"
        "document.addEventListener('scorecard:lead', (e) => window.__leads.push(e.detail));"
    )
    page.goto(f"{base_url}/subscribe.html#confirmed")
    note = page.locator("#confirmed")
    expect(note).to_be_visible()
    expect(note).to_have_text(re.compile(r"^You are subscribed\.\s+Your address is confirmed\."))
    expect(note).to_be_focused()
    # The marker leaves the address, so a reload neither shows the note nor counts again.
    assert page.evaluate("window.location.hash") == ""
    assert page.evaluate("window.__leads") == [{"event": "alert_signup_confirmed"}]
    page.reload()
    expect(note).to_be_hidden()
    assert page.evaluate("window.__leads") == []


def test_without_javascript_a_confirmed_reader_still_sees_the_note(
    browser: Browser, base_url: str
) -> None:
    context = browser.new_context(java_script_enabled=False, service_workers="block")
    try:
        page = context.new_page()
        page.goto(f"{base_url}/subscribe.html#confirmed")
        expect(page.locator("#confirmed")).to_be_visible()
    finally:
        context.close()
