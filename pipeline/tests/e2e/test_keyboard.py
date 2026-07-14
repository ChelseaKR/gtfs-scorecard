"""Keyboard-only flows over the SPA's interactive surfaces: the agency picker,
the findings severity filters, and the compare form. Focus position is read
from document.activeElement, and actions must take real effect — the WCAG 2.2
keyboard-operability claim (docs/vpat.md) as an executable check."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

AGENCY_ID = "abq-ride"


def _tab_to(page: Page, predicate: str, max_tabs: int = 250) -> None:
    """Press Tab until document.activeElement satisfies `predicate` (a JS
    expression over `el`), failing after max_tabs presses. Starts by checking
    the current focus, so it also accepts an already-focused match."""
    check = f"() => {{ const el = document.activeElement; return !!el && ({predicate}); }}"
    for _ in range(max_tabs):
        if page.evaluate(check):
            return
        page.keyboard.press("Tab")
    pytest.fail(f"no focusable element matching {predicate!r} within {max_tabs} tabs")


def _active(page: Page, expression: str) -> object:
    """Evaluate `expression` over the currently focused element."""
    return page.evaluate(f"() => {{ const el = document.activeElement; return {expression}; }}")


def test_keyboard_picker_reaches_agency_page(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/")
    expect(page.locator("#agency-search")).to_be_visible()

    _tab_to(page, "el.id === 'agency-search'")
    page.keyboard.type("abq ride")
    expect(page.locator("#agency-list .agency-card").first).to_be_visible()

    _tab_to(page, "el.matches('#agency-list h2 a')")
    # The keyboard focus is on a real agency link and visibly ringed
    # (styles.css :focus-visible outline).
    href = _active(page, "el.getAttribute('href')")
    assert isinstance(href, str) and href.startswith("#/agency/")
    assert _active(page, "getComputedStyle(el).outlineStyle") != "none"

    page.keyboard.press("Enter")
    expect(page.locator("h1.board-title")).to_be_visible()
    hash_now = page.evaluate("() => location.hash")
    assert isinstance(hash_now, str) and hash_now.startswith("#/agency/")


def test_keyboard_findings_severity_filter(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/agency/{AGENCY_ID}")
    bar = page.locator(".filterbar")
    expect(bar.locator("button")).to_have_count(4)  # All / Errors / Warnings / Info

    _tab_to(page, "el.matches('.filterbar button') && el.dataset.filter === 'ERROR'")
    page.keyboard.press("Enter")

    expect(bar.locator('button[data-filter="ERROR"]')).to_have_attribute("aria-pressed", "true")
    expect(bar.locator('button[data-filter="ALL"]')).to_have_attribute("aria-pressed", "false")
    count_line = page.locator(".findings-count")
    expect(count_line).to_have_text(re.compile(r"^Showing \d+ findings?\.$"))
    # Every rendered finding is an error: the announced count matches the
    # number of error rows, and no other severity is shown.
    match = re.search(r"\d+", count_line.inner_text())
    assert match is not None
    expect(page.locator(".findings .sev-error")).to_have_count(int(match.group()))
    expect(page.locator(".findings .sev-warning")).to_have_count(0)
    expect(page.locator(".findings .sev-info")).to_have_count(0)


def test_keyboard_compare_form(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/compare")
    expect(page.locator("#compare-pick")).to_be_visible()

    # Select options by type-ahead (typing selects the next matching option):
    # unlike ArrowDown, it changes a closed <select>'s value on every platform.
    _tab_to(page, "el.id === 'cmp-a'", max_tabs=40)
    page.keyboard.type("a")
    _tab_to(page, "el.id === 'cmp-b'", max_tabs=5)
    page.keyboard.type("b")

    picked = page.evaluate(
        "() => [document.querySelector('#cmp-a').value, document.querySelector('#cmp-b').value]"
    )
    a_id, b_id = picked
    assert a_id and b_id and a_id != b_id

    _tab_to(page, "el.matches('#compare-pick button.compare-go')", max_tabs=5)
    page.keyboard.press("Enter")

    assert page.evaluate("() => location.hash") == f"#/compare?a={a_id}&b={b_id}"
    # The selected live records may be outside the current homogeneous
    # comparison cohort. Keyboard submission must still navigate and render
    # either the valid table or the explicit methodology/identity guard.
    table = page.locator("table.compare-table")
    guard = page.get_by_role("heading", name="These scorecards are not like-for-like.")
    expect(table.or_(guard)).to_be_visible()
