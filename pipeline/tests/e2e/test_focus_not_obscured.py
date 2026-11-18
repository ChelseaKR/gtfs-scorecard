"""Keyboard focus stays in view under the sticky header (WCAG 2.4.7, 2.4.11).

Three ways the header used to hide what a keyboard reader was on: the skip
link was painted underneath it, Shift+Tab scrolled each control to the top
edge and under it, and an in-page link parked its heading there too. Each is
driven here with real key presses on a prerendered page built on the shared
shell. `tests/test_focus_not_obscured.py` holds the same contract in the CSS.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

# A prerendered page with a long main column and an in-page "jump to" nav.
PAGE_PATH = "/pulse/"

# Whether the focused element is the topmost thing at its own corners and
# center, and where it sits relative to the header's bottom edge.
_FOCUS_STATE = """() => {
  const el = document.activeElement;
  const header = document.querySelector(".site-header");
  const r = el.getBoundingClientRect();
  const inset = 2;
  const points = [
    [r.left + r.width / 2, r.top + r.height / 2],
    [r.left + inset, r.top + inset],
    [r.right - inset, r.top + inset],
    [r.left + inset, r.bottom - inset],
    [r.right - inset, r.bottom - inset],
  ];
  const covered = points.some(([x, y]) => {
    const top = document.elementFromPoint(x, y);
    return !top || !(el.contains(top) || top.contains(el)) || header.contains(top);
  });
  return {
    label: (el.textContent || "").trim().slice(0, 40),
    top: r.top,
    headerBottom: header.getBoundingClientRect().bottom,
    covered,
  };
}"""


@pytest.fixture
def shell_page(page: Page, base_url: str) -> Page:
    page.emulate_media(reduced_motion="reduce")  # no smooth scroll to wait out
    page.goto(f"{base_url}{PAGE_PATH}")
    expect(page.locator(".site-header")).to_be_visible()
    return page


def test_skip_link_is_visible_when_focused(shell_page: Page) -> None:
    shell_page.keyboard.press("Tab")
    # The link slides in over 120ms; measure it once it has arrived.
    expect(shell_page.locator(".skip-link")).to_be_in_viewport(ratio=1)
    state = shell_page.evaluate(
        """() => {
          const el = document.activeElement;
          const r = el.getBoundingClientRect();
          const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return { isSkip: el.classList.contains("skip-link"), onTop: top === el, y: r.top };
        }"""
    )
    assert state["isSkip"], "the first Tab stop should be the skip link"
    assert state["y"] >= 0
    assert state["onTop"], "the focused skip link is painted under the sticky header"


def test_shift_tab_does_not_park_focus_under_the_header(shell_page: Page) -> None:
    # Start from the last link in the main column and walk backwards, which is
    # the direction that scrolls each new control to the top of the window.
    shell_page.evaluate(
        """() => {
          const links = [...document.querySelectorAll("main a[href]")];
          links[links.length - 1].focus();
        }"""
    )
    hidden = []
    for _ in range(40):
        shell_page.keyboard.press("Shift+Tab")
        in_main = shell_page.evaluate("() => !!document.activeElement.closest('main')")
        if not in_main:
            break
        state = shell_page.evaluate(_FOCUS_STATE)
        if state["covered"] or state["top"] < state["headerBottom"]:
            hidden.append(state)
    assert not hidden, f"focus went under the sticky header: {hidden[:3]}"


def test_in_page_link_target_clears_the_header(shell_page: Page) -> None:
    links = shell_page.locator('main a[href^="#"]')
    assert links.count() > 0, "the page under test should have an in-page link"
    target_id = (links.first.get_attribute("href") or "")[1:]
    links.first.click()
    state = shell_page.evaluate(
        """(id) => {
          const target = document.getElementById(id);
          const heading = target.matches("h1,h2,h3") ? target : target.querySelector("h1,h2,h3");
          return {
            headingTop: (heading || target).getBoundingClientRect().top,
            headerBottom: document.querySelector(".site-header").getBoundingClientRect().bottom,
          };
        }""",
        target_id,
    )
    assert state["headingTop"] >= state["headerBottom"], (
        f"#{target_id} landed under the sticky header: {state}"
    )


@pytest.mark.parametrize(
    ("path", "button", "panel_host"),
    [(PAGE_PATH, ".nav-menu-btn", ".site-header"), ("/", ".home-menu-toggle", ".topbar")],
)
def test_open_menu_closes_when_focus_moves_past_it(
    page: Page, base_url: str, path: str, button: str, panel_host: str
) -> None:
    # On a narrow screen the open menu is a panel over the top of the page.
    # Tabbing past its last control used to leave it open, with the focused
    # control behind it.
    page.set_viewport_size({"width": 320, "height": 640})
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{base_url}{path}")
    toggle = page.locator(button)
    toggle.focus()
    page.keyboard.press("Enter")
    expect(toggle).to_have_attribute("aria-expanded", "true")

    for _ in range(14):
        page.keyboard.press("Tab")
        outside = page.evaluate(
            "(host) => !document.activeElement.closest(host)",
            panel_host,
        )
        if outside:
            break
    else:
        pytest.fail("focus never left the open menu")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    on_top = page.evaluate(
        """() => {
          const el = document.activeElement;
          const r = el.getBoundingClientRect();
          const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return !!top && (el.contains(top) || top.contains(el));
        }"""
    )
    assert on_top, "the control that took focus is still behind the menu panel"
