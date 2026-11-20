"""Fast merge-gate checks for frontend locale centralization."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_live_frontend_uses_shared_locale_primitives() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    subscribe = (ROOT / "web" / "src" / "subscribe.js").read_text()
    # The alerts form no longer sorts or formats anything itself: its agency
    # list comes from the shared picker, which collates the way compareText
    # does (the page's language, base sensitivity, numeric).
    picker = (ROOT / "web" / "src" / "agency-combobox.js").read_text()
    assert 'from "./locale.js"' in app
    assert 'sensitivity: "base", numeric: true' in picker
    assert "document.documentElement.lang" in picker
    assert 'toLocaleDateString("en-US"' not in app
    assert ".toLocaleString()" not in app
    assert ".localeCompare(" not in app + subscribe + picker
