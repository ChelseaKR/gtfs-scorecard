"""Fast merge-gate checks for frontend locale centralization."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_live_frontend_uses_shared_locale_primitives() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    subscribe = (ROOT / "web" / "src" / "subscribe.js").read_text()
    assert 'from "./locale.js"' in app
    assert 'from "./locale.js"' in subscribe
    assert 'toLocaleDateString("en-US"' not in app
    assert ".toLocaleString()" not in app
    assert ".localeCompare(" not in app + subscribe
