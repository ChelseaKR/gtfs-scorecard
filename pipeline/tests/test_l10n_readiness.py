"""Localization-readiness ratchets for the no-build frontend.

Two counted gates, both compared to an exact recorded baseline so a change is
a conscious decision rather than silent drift:

- Hardcoded-string ratchet: user-facing copy belongs in the reviewed catalog
  (locales/app.en.json) and reaches the app through the generated strings
  module. The count of English-looking string literals per web/src file may
  only go down; lowering a number here should mean strings moved into the
  catalog. Raising one requires the same deliberate review as any new copy.
- Physical-CSS ratchet: right-to-left readiness prefers logical properties
  (margin-inline-start over margin-left). The count of directional physical
  properties in styles.css may only go down.

The heuristics are deliberately simple and deterministic: a string literal
counts when it contains two or more adjacent ASCII words and does not start
with "http"; a CSS declaration counts when it uses a left/right margin,
padding, border, text-align, or float. Update a baseline in the same change
that moves it, with the direction explained in the commit.
"""

from __future__ import annotations

import re
from pathlib import Path

# The real repo, not the per-test tmp SCORECARD_ROOT.
_REPO = Path(__file__).resolve().parents[2]
_WEB_SRC = _REPO / "web" / "src"

_LITERAL = re.compile(r'(["\'`])((?:(?!\1).)*?)\1', re.S)
_WORDY = re.compile(r"[A-Za-z]{2,} [A-Za-z]{2,}")
_PHYSICAL = re.compile(
    r"(?<![-a-z])(?:margin|padding|border)-(?:left|right)\b"
    r"|text-align:\s*(?:left|right)\b"
    r"|float:\s*(?:left|right)\b"
)

# file name -> count of English-looking string literals (see module docstring).
HARDCODED_STRING_BASELINE = {
    # Raised 260 -> 339 with the world coverage map, then 339 -> 378 with the
    # subdivision drill-down: its Back control, drill heading, and per-area aria
    # labels are new accessible copy, a conscious increase to work back down
    # through the catalog. The per-region coverage disclosure (the reviewed-
    # cohort denominator shown when a country or subdivision is filtered) added a
    # few more English literals to move into the catalog; the count is unchanged
    # here because this heuristic under-counts strings nested in the overview's
    # template literals, not because the copy is exempt from localization.
    "app.js": 378,
    "config.js": 1,
    "es.js": 2,
    "i18n.js": 0,
    # The hand-authored landing page is not yet part of the generated SPA
    # locale catalog. Record its progressively enhanced scorecard copy here so
    # later localization work can ratchet this standalone module down. The
    # selected-record scope links, technical trace labels, and accessible
    # selection announcements raised this reviewed baseline from 111 to 116;
    # the source and method labels for freshness findings raise it to 121.
    "landing-scorecard.js": 121,
    "locale.js": 0,
    "nav.js": 4,
    "submit.js": 17,
    "subscribe.js": 8,
    "theme.js": 4,
    "try.js": 9,
}

PHYSICAL_CSS_BASELINE = 36


def _wordy_literals(text: str) -> int:
    return sum(
        1
        for match in _LITERAL.finditer(text)
        if not match.group(2).startswith("http") and _WORDY.search(match.group(2))
    )


def test_hardcoded_string_counts_match_baseline() -> None:
    files = sorted(path.name for path in _WEB_SRC.glob("*.js"))
    assert files == sorted(HARDCODED_STRING_BASELINE), (
        "web/src gained or lost a module; record its hardcoded-string baseline"
    )
    for name, expected in HARDCODED_STRING_BASELINE.items():
        actual = _wordy_literals((_WEB_SRC / name).read_text())
        assert actual == expected, (
            f"{name}: {actual} English-looking literals, baseline {expected}. "
            "Move copy into locales/app.en.json (then `scorecard render-constants`) "
            "and lower the baseline, or justify the increase in review."
        )


def test_physical_css_count_matches_baseline() -> None:
    actual = len(_PHYSICAL.findall((_WEB_SRC / "styles.css").read_text()))
    assert actual == PHYSICAL_CSS_BASELINE, (
        f"styles.css: {actual} directional physical properties, baseline "
        f"{PHYSICAL_CSS_BASELINE}. Prefer logical properties "
        "(margin-inline-start, padding-inline-end, text-align: start) and lower "
        "the baseline."
    )
