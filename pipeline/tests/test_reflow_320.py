"""Two things that broke at 320 CSS px, the WCAG 1.4.10 reflow width.

- A bare address printed as a link has no place to break. One in a note on a
  program page pushed the whole page 35px wider than the screen, so every
  line of it needed sideways scrolling.
- The scorecard's finding picker cut its three links to fit: "01 score",
  "02 scorecar", "03 scoreca". The part that was cut is the part that tells
  them apart.

Both are read from `web/src/styles.css` here and measured in a browser by
`tests/e2e/test_mobile.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_CSS = ROOT / "web" / "src" / "styles.css"

_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(encoding="utf-8"), flags=re.S)


def _rules(selector: str) -> list[str]:
    """The declarations of every rule whose selector list names ``selector``."""
    return [
        m.group(2)
        for m in _RULE.finditer(_css())
        if selector in [s.strip() for s in m.group(1).split(",")]
    ]


def test_a_long_address_in_the_main_column_can_break() -> None:
    bodies = _rules("main")
    assert any(re.search(r"overflow-wrap:\s*(break-word|anywhere)", body) for body in bodies), (
        "nothing lets an unbroken string in <main> wrap, so one long address "
        "widens the page past a 320px screen"
    )


def test_finding_picker_links_are_never_cut_short() -> None:
    link_rules = _rules(".finding-picker a")
    assert link_rules, "no .finding-picker a rule found"
    for body in link_rules:
        assert "text-overflow" not in body, (
            "the finding picker cuts its link text; the cut part is what tells the links apart"
        )
        assert not re.search(r"overflow:\s*hidden", body)
    # On a narrow screen the links wrap onto more lines instead.
    narrow = _css()[_css().index("@media (max-width: 720px)") :]
    assert re.search(r"\.finding-picker\s*\{[^{}]*flex-wrap:\s*wrap", narrow)
