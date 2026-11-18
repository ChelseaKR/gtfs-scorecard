"""A text field can be found by its edge (WCAG 1.4.11).

Text fields, selects and text areas on the site are filled within 1.1:1 of
the page behind them in every theme, so the border is the whole boundary of
the control and has to clear 3:1 on its own. They were drawn with `--line`,
the hairline used for cards and table rules, which measures 1.5:1 on paper
in the light theme and 1.6:1 in the dark one.

Fields now take `--field-line`. These tests hold three things: no field rule
goes back to the hairline, the contrast gate measures the new token against
every surface a field sits on, and the two places the dark palette is written
agree.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
APP_CSS = ROOT / "web" / "src" / "styles.css"
CHECKER = ROOT / "pipeline" / "scripts" / "check_contrast.py"

# Selectors that style an <input>, <select> or <textarea>, by tag or by the
# classes the templates put on those tags.
_FIELD = re.compile(
    r"(?<![-\w])(?:input|select|textarea)(?![-\w])"
    r"|\.agency-search\b|\.note-input\b|\.outreach-text\b|\.badge-embed(?![-\w])"
)
# Not fields: the button inside a file input, and checkboxes.
_NOT_FIELD = re.compile(r"::file-selector-button|\[type=\"checkbox\"\]\s*(?:,|$)")
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_BORDER = re.compile(r"(?<![-a-z])border(?:-color)?\s*:\s*([^;]+);")


def _gate() -> Any:
    spec = importlib.util.spec_from_file_location("check_contrast", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(encoding="utf-8"), flags=re.S)


def _field_borders() -> list[tuple[str, str]]:
    found = []
    for match in _RULE.finditer(_css()):
        selectors = [s.strip() for s in match.group(1).split(",")]
        fields = [s for s in selectors if _FIELD.search(s) and not _NOT_FIELD.search(s)]
        if not fields:
            continue
        for border in _BORDER.findall(match.group(2)):
            found.append((", ".join(fields), border.strip()))
    return found


def test_field_rules_are_found() -> None:
    # The test below must not pass by matching nothing.
    assert len(_field_borders()) >= 8


def test_no_field_is_edged_with_the_hairline() -> None:
    hairline = [(sel, border) for sel, border in _field_borders() if "var(--line)" in border]
    assert not hairline, (
        "these fields take --line, which is about 1.5:1 against the page; "
        f"use --field-line: {hairline}"
    )


def test_the_gate_holds_field_edges_to_three_to_one() -> None:
    gate = _gate()
    measured = {(fg, bg) for _label, fg, bg in gate.NON_TEXT_PAIRS}
    for surface in ("paper", "card", "paper-deep"):
        assert ("field-line", surface) in measured
    for theme_name, theme in gate.THEMES.items():
        for surface in ("paper", "card", "paper-deep"):
            measured_ratio = gate.ratio(theme["field-line"], theme[surface])
            assert measured_ratio >= gate.NON_TEXT_MINIMUM, (
                f"{theme_name}: --field-line on --{surface} is {measured_ratio:.2f}:1"
            )


def test_system_dark_and_chosen_dark_agree_on_the_field_edge() -> None:
    css = _css()
    system = css[css.index(":root:not([data-theme]) {") :]
    chosen = css[css.index(':root[data-theme="dark"] {') :]
    pattern = re.compile(r"--field-line:\s*(#[0-9a-fA-F]{6})")
    system_value = pattern.search(system[: system.index("}")])
    chosen_value = pattern.search(chosen[: chosen.index("}")])
    assert system_value and chosen_value
    assert system_value.group(1).lower() == chosen_value.group(1).lower()
