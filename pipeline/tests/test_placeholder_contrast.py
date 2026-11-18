"""Placeholder text is drawn in a color the contrast gate measures.

A placeholder on this site is example copy ("e.g. US or CA",
"https://.../google_transit.zip"), so it is text a reader needs and WCAG 1.4.3
applies to it. Left to the browser it is a mid gray: 4.47:1 on the light card,
3.5:1 on the dark one, 4.1:1 on the landing page. Neither stylesheet set it,
so `check_contrast.py`, which gates the palette, never saw that color at all.

Both stylesheets now draw placeholders in `--ink-soft`, which the gate holds
on every surface a field sits on.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_CSS = ROOT / "web" / "src" / "styles.css"
LANDING_HTML = ROOT / "web" / "index.html"
CHECKER = ROOT / "pipeline" / "scripts" / "check_contrast.py"


def _gate() -> Any:
    spec = importlib.util.spec_from_file_location("check_contrast", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _placeholder_rule(text: str) -> str:
    match = re.search(r"(?m)^\s*::placeholder\s*\{([^{}]*)\}", text)
    assert match, "no ::placeholder rule, so the browser picks the color"
    return match.group(1)


@pytest.mark.parametrize("source", [APP_CSS, LANDING_HTML], ids=["app", "landing"])
def test_placeholders_use_the_gated_soft_ink(source: Path) -> None:
    body = _placeholder_rule(source.read_text(encoding="utf-8"))
    assert re.search(r"(?<![-a-z])color:\s*var\(--ink-soft\)", body)
    # Firefox draws placeholders at reduced opacity unless told otherwise,
    # which would take the measured color back under the bar.
    assert re.search(r"opacity:\s*1\b", body)


def test_the_gate_measures_soft_ink_on_every_field_surface() -> None:
    pairs = {(fg, bg) for _label, fg, bg, _large in _gate().PAIRS}
    for surface in ("paper", "card"):
        assert ("ink-soft", surface) in pairs
    assert ("L_ink-soft", "L_paper") in pairs
