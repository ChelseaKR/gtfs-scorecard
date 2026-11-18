"""The sticky header must not hide what a keyboard reader is focused on.

`.site-header` sticks to the top of every page built on the shared shell. Two
things have to hold for that to be safe for someone who does not use a mouse
(WCAG 2.4.7 Focus Visible, 2.4.11 Focus Not Obscured):

- The skip link is the first Tab stop and slides in at the top of the page,
  which is exactly where the header sits. It has to stack above the header or
  it is focused and invisible.
- When focus or an in-page link scrolls the page, the browser lines the target
  up with the top of the scrollport. `scroll-padding-top` on the root tells it
  to stop short of the header, so the target is not parked underneath it.

These read `web/src/styles.css` as text. The behavior itself is exercised in a
browser by `tests/e2e/test_focus_not_obscured.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_CSS = ROOT / "web" / "src" / "styles.css"
NAV_JS = ROOT / "web" / "src" / "nav.js"
LANDING = ROOT / "web" / "index.html"

# The tallest the header gets: 64px of content plus its 3px rule, at a 16px
# root. Stated in rem so the comparison follows the reader's text size.
HEADER_HEIGHT_REM = 67 / 16

_RULE = re.compile(r"(?m)^(?P<selector>[^{}@/]+?)\s*\{(?P<body>[^{}]*)\}")
_PRINT = re.compile(r"@media print\s*\{(?:[^{}]|\{[^{}]*\})*\}")


def _screen_rules() -> list[tuple[str, str]]:
    """Every (selector, declarations) pair that applies on screen."""
    css = _PRINT.sub("", APP_CSS.read_text(encoding="utf-8"))
    return [(m["selector"].strip(), m["body"]) for m in _RULE.finditer(css)]


def _declared(selector: str, prop: str) -> list[str]:
    """Each value `prop` is given in a rule whose selector list names `selector`."""
    values = []
    for selectors, body in _screen_rules():
        if selector not in [s.strip() for s in selectors.split(",")]:
            continue
        match = re.search(rf"(?<![-a-z]){re.escape(prop)}\s*:\s*([^;]+);", body)
        if match:
            values.append(match.group(1).strip())
    return values


def _rem(value: str) -> float:
    match = re.fullmatch(r"([0-9.]+)rem", value)
    assert match, f"expected a rem length, got {value!r}"
    return float(match.group(1))


def test_the_header_is_sticky() -> None:
    # The premise of the two checks below. If the header stops sticking, they
    # stop mattering and this says so.
    assert "sticky" in _declared(".site-header", "position")


def test_skip_link_stacks_above_the_sticky_header() -> None:
    header = max(int(z) for z in _declared(".site-header", "z-index"))
    skip = max(int(z) for z in _declared(".skip-link", "z-index"))
    assert skip > header, (
        f"the skip link (z-index {skip}) is painted under the sticky header "
        f"(z-index {header}), so the first Tab stop is focused but invisible"
    )


def test_scrolling_to_a_target_stops_below_the_sticky_header() -> None:
    padding = _declared("html", "scroll-padding-top")
    assert padding, (
        "html needs scroll-padding-top: without it a focused control or an "
        "in-page link target scrolls to the top edge, under the sticky header"
    )
    assert _rem(padding[-1]) >= HEADER_HEIGHT_REM


def test_open_menu_closes_when_focus_leaves_the_header() -> None:
    # On a narrow screen the open menu is a panel over the top of the page.
    # Tab past its last control and focus lands on something behind the panel.
    # Escape would uncover it, but Escape also pulls focus back to the menu
    # button, so the reader cannot see where they are without losing their
    # place. The menu has to close as focus leaves.
    source = NAV_JS.read_text(encoding="utf-8")
    handler = re.search(
        r'header\.addEventListener\("focusout", function \(e\) \{(.*?)\n  \}\);', source, re.S
    )
    assert handler, "nav.js does not watch focus leaving the header"
    body = handler.group(1)
    assert "relatedTarget" in body and "header.contains" in body and "close()" in body
    # Only a Tab press closes it. The app moves focus to the main region when
    # its data arrives, and a menu opened before then must not snap shut.
    assert "tabbedOut" in body
    assert re.search(r'header\.addEventListener\("keydown"[^}]*e\.key === "Tab"', source, re.S)


def test_landing_menu_closes_when_focus_leaves_the_bar() -> None:
    # The landing page carries its own menu script; same panel, same rule.
    source = LANDING.read_text(encoding="utf-8")
    handler = re.search(
        r'topbar\.addEventListener\("focusout", function \(event\) \{(.*?)\n    \}\);',
        source,
        re.S,
    )
    assert handler, "the landing page does not watch focus leaving its menu bar"
    body = handler.group(1)
    assert "relatedTarget" in body and "topbar.contains" in body and "closeMenu(false)" in body
    assert "tabbedOut" in body
    assert re.search(r'topbar\.addEventListener\("keydown"[^}]*event\.key === "Tab"', source, re.S)
