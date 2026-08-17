"""Tie the AAA contrast gate's palette to the CSS it is supposed to be gating.

`pipeline/scripts/check_contrast.py` is the merge-blocking contrast gate
(Makefile `verify`), and axe's own `color-contrast` rule is switched off in
`.pa11yci.json` on the grounds that this gate owns contrast. But the gate
measures `THEMES`, a hand-copied table of hex values inside the checker; it
never reads `web/src/styles.css` or the landing palette in `web/index.html`.
Nothing compared the two, so darkening a token in the CSS could take the live
site below AAA with `make verify` still green -- it would have re-measured its
own copy -- and with axe told not to look.

These tests are that comparison. They do not re-check contrast ratios; they
check that the numbers the gate measures are the numbers the browser gets.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "pipeline" / "scripts" / "check_contrast.py"
APP_CSS = ROOT / "web" / "src" / "styles.css"
LANDING_HTML = ROOT / "web" / "index.html"

# THEMES key -> the selector whose declarations override :root for that theme.
# "light" is :root itself.
THEME_SELECTORS = {
    "light": None,
    "dark": ':root[data-theme="dark"] {',
    "contrast": ':root[data-theme="contrast"] {',
}

# Three THEMES entries are not custom properties: they are the background of
# the Fix NN badge, set directly on `.alert .badge` rules. Light inherits the
# severity tokens through var(); dark and contrast override with literals.
BADGE_TOKENS = {"badge-error": "error", "badge-warning": "warning", "badge-info": "info"}

_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\Z")
_DECL = re.compile(r"--([a-z0-9-]+)\s*:\s*([^;]+);")
_VAR = re.compile(r"\Avar\(--([a-z0-9-]+)\)\Z")


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_contrast", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contrast = _load()


def _rule_body(text: str, selector: str) -> str:
    """The declarations of the first rule opened by ``selector``."""
    start = text.index(selector) + len(selector)
    return text[start : text.index("}", start)]


def _declarations(text: str, selector: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in _DECL.finditer(_rule_body(text, selector))}


def _palette(text: str, theme: str) -> dict[str, str]:
    """Custom properties in effect for ``theme``: :root, then its override rule."""
    values = _declarations(text, ":root {")
    selector = THEME_SELECTORS[theme]
    if selector is not None:
        values.update(_declarations(text, selector))
    resolved: dict[str, str] = {}
    for name, raw in values.items():
        indirect = _VAR.match(raw)
        resolved[name] = values.get(indirect.group(1), raw) if indirect else raw
    return resolved


def _badge_background(css: str, theme: str, token: str) -> str:
    """The literal `.alert .badge` background the browser paints for ``theme``."""
    suffix = {"badge-error": "", "badge-warning": ".sev-warning", "badge-info": ".sev-info"}[token]
    prefix = "" if theme == "light" else THEME_SELECTORS[theme].removesuffix(" {") + " "
    rule = f"{prefix}.alert .badge{suffix} {{"
    background = re.search(r"background:\s*([^;]+);", _rule_body(css, rule))
    assert background, f"no background declaration in {rule!r}"
    value = background.group(1).strip()
    indirect = _VAR.match(value)
    return _palette(css, theme)[indirect.group(1)] if indirect else value


@pytest.mark.parametrize("theme", sorted(THEME_SELECTORS))
def test_every_gated_token_matches_the_stylesheet(theme: str) -> None:
    """Each hex the contrast gate measures is the hex the CSS actually ships."""
    app = _palette(APP_CSS.read_text(), theme)
    landing = _palette(LANDING_HTML.read_text(), theme)
    css = APP_CSS.read_text()

    for token, gated in contrast.THEMES[theme].items():
        if token in BADGE_TOKENS:
            shipped = _badge_background(css, theme, token)
        else:
            source, name = (landing, token[2:]) if token.startswith("L_") else (app, token)
            assert name in source, (
                f"{theme}: check_contrast.py measures --{name}, which no longer exists in the "
                "stylesheet. The gate would keep passing on a value the browser never sees."
            )
            shipped = source[name]
        assert _HEX.match(shipped), f"{theme}/{token}: {shipped!r} is not a hex this test can read"
        assert shipped.lower() == gated.lower(), (
            f"{theme}/{token}: the contrast gate measures {gated}, the site ships {shipped}. "
            "Update THEMES in pipeline/scripts/check_contrast.py in the same change as the CSS."
        )


def test_the_gate_measures_every_theme_the_stylesheet_defines() -> None:
    """A new theme in the CSS must be added to the gate, not silently unchecked."""
    css = APP_CSS.read_text()
    declared = {m.group(1) for m in re.finditer(r':root\[data-theme="([a-z]+)"\]\s*\{', css)}
    # `light` only flips color-scheme; its palette is :root, which is gated.
    assert declared - {"light"} <= set(contrast.THEMES), (
        f"themes in styles.css that check_contrast.py does not measure: "
        f"{sorted(declared - {'light'} - set(contrast.THEMES))}"
    )


def test_no_gated_pair_is_skipped_for_an_unresolvable_token() -> None:
    """`main()` silently `continue`s past a pair whose token a theme lacks.

    That is how a renamed token would shrink the checked set without failing:
    fewer pairs measured, same "all pairs pass" output. Every pair has to
    resolve in every theme.
    """
    for theme_name, theme in contrast.THEMES.items():
        for label, foreground, background, _large in contrast.PAIRS:
            for token in (foreground, background):
                if token.startswith("#"):
                    continue
                assert token in theme, f"{theme_name}: pair {label!r} references missing {token!r}"
