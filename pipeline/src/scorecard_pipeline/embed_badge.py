"""The named, dated score badge an agency can embed on its own site.

Served as a static file next to each agency page (``/agency/<id>/badge.svg``)
and linked from a copy-paste snippet on that page, so a badge on an agency's
site always leads back to its scorecard. It names the agency, shows the grade
and score exactly as the scorecard does, and says when the feed was checked.

The older ``/data/artifacts/<id>/badge.svg`` is a compact shields-style grade
pill without a name or a date. It stays in place for embeds that already use it.

Absence is never drawn as a value. When the published record has no usable
grade and score, or its last check is older than ``CURRENT_DAYS`` before the
render, the badge says "No current score" with no letter and no number. A
badge pasted onto someone else's site can outlive its data by months, so a
stale grade must not keep presenting itself as the feed's state.

The SVG is self-contained (no scripts, external fonts, images, or links) and
carries a ``<title>`` plus ``aria-label`` so it reads as one sentence. Every
color comes from badge.py's palette, which check_contrast.py already holds to
the AAA bar: white on the grade colors, and the two text grays on white.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

from .badge import _FALLBACK_COLOR, _GRADE_COLOR

#: A record last checked more than this many days before the render shows no
#: score. The pipeline checks every published feed daily, so two weeks without
#: a fresh check means the feed is not being read, not that it is unchanged.
CURRENT_DAYS = 14

WIDTH = 320
HEIGHT = 58
_LETTER_W = 46
_TEXT_X = _LETTER_W + 10
_NAME_MAX_CHARS = 32
_INK = "#2b2b2b"
_INK_SOFT = _FALLBACK_COLOR
_BORDER = _FALLBACK_COLOR
_PAPER = "#ffffff"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class BadgeState:
    """What one badge says: a current grade, or the honest absence of one."""

    agency_name: str
    grade: str | None
    score: str | None
    checked: str | None

    @property
    def current(self) -> bool:
        return self.grade is not None and self.score is not None


def badge_state(agency_name: str, artifact: dict[str, Any] | None, today: dt.date) -> BadgeState:
    """Read the badge's content from a published artifact.

    The grade and score are taken only when both are well formed and the
    check date is within ``CURRENT_DAYS`` of ``today``. A last-check date that
    is well formed is kept even when the score is not shown, so the badge can
    say when the feed was last read.
    """
    record = artifact if isinstance(artifact, dict) else {}
    checked_raw = record.get("snapshot_date")
    checked = checked_raw if isinstance(checked_raw, str) and _DATE.match(checked_raw) else None
    overall = record.get("overall")
    grade = overall.get("grade") if isinstance(overall, dict) else None
    score = overall.get("score") if isinstance(overall, dict) else None
    valid = (
        isinstance(grade, str)
        and grade in _GRADE_COLOR
        and not isinstance(score, bool)
        and isinstance(score, (int, float))
        and 0 <= float(score) <= 100
        and checked is not None
    )
    if valid and checked is not None:
        age = (today - dt.date.fromisoformat(checked)).days
        valid = 0 <= age <= CURRENT_DAYS
    if not valid:
        return BadgeState(agency_name, None, None, checked)
    return BadgeState(agency_name, str(grade), str(score), checked)


def badge_sentence(state: BadgeState) -> str:
    """The whole badge as one sentence, for its title and aria-label."""
    if state.current:
        return (
            f"{state.agency_name}: GTFS feed quality grade {state.grade}, "
            f"{state.score} of 100, checked {state.checked}. GTFS Scorecard."
        )
    last = f" Last checked {state.checked}." if state.checked else ""
    return f"{state.agency_name}: no current GTFS feed quality score.{last} GTFS Scorecard."


_TRAILING_SHORT_FORM = re.compile(r"^(?P<outer>.*\S)\s*\((?P<inner>[^()]*[A-Za-z][^()]*)\)$")


def _fit(text: str, limit: int) -> str:
    """Fit a name on the badge: whole, then its own short form, then cut on a word."""
    if len(text) <= limit:
        return text
    match = _TRAILING_SHORT_FORM.match(text.strip())
    if match:
        inner = match.group("inner").strip()
        if 2 <= len(inner) <= limit and len(inner) < len(match.group("outer")):
            return inner
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space >= limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,-/;:(") + "…"


def render_named_badge(state: BadgeState) -> str:
    """Return the badge SVG for one agency."""
    sentence = badge_sentence(state)
    name = escape(_fit(state.agency_name, _NAME_MAX_CHARS))
    if state.current:
        stripe = _GRADE_COLOR[str(state.grade)]
        letter = (
            f'<text x="{_LETTER_W / 2:.0f}" y="38" font-size="24" font-weight="bold" '
            f'fill="#ffffff" text-anchor="middle" aria-hidden="true">'
            f"{escape(str(state.grade))}</text>"
        )
        line2 = f"GTFS feed score {escape(str(state.score))} of 100"
        line3 = f"Checked {escape(str(state.checked))} · gtfsscorecard.org"
    else:
        stripe = _FALLBACK_COLOR
        letter = ""
        line2 = "No current score"
        line3 = (
            f"Last checked {escape(state.checked)} · gtfsscorecard.org"
            if state.checked
            else "gtfsscorecard.org"
        )
    label = escape(sentence, {'"': "&quot;"})
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{label}">'
        f"<title>{escape(sentence)}</title>"
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="4" '
        f'fill="{_PAPER}" stroke="{_BORDER}"/>'
        f'<path d="M4.5 0.5H{_LETTER_W}V{HEIGHT - 0.5}H4.5A4 4 0 0 1 0.5 {HEIGHT - 4.5}'
        f'V4.5A4 4 0 0 1 4.5 0.5Z" fill="{stripe}"/>'
        f'<g font-family="Verdana,Geneva,sans-serif" fill="{_INK}">'
        f"{letter}"
        f'<text x="{_TEXT_X}" y="18" font-size="13" font-weight="bold">{name}</text>'
        f'<text x="{_TEXT_X}" y="35" font-size="12">{line2}</text>'
        f'<text x="{_TEXT_X}" y="50" font-size="11" fill="{_INK_SOFT}">{line3}</text>'
        f"</g></svg>\n"
    )
