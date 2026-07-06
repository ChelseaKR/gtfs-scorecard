"""Embeddable SVG grade badge.

The roadmap's organic-distribution piece (docs/roadmap.md): an agency can put
"GTFS quality: B" on its own developer page the way open-source projects embed
a build-status badge, and every badge links back to the scorecard. Badges are
static SVG written next to each agency's artifacts, so they cost nothing to
serve and need no badge service.

The SVG is self-contained (no external fonts or images) and carries a <title>
so screen readers announce the grade rather than reading raw markup.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

# Grade colours chosen for contrast on white and to stay distinguishable to
# common colour-vision deficiencies; the letter itself is the primary signal,
# never colour alone.
_GRADE_COLOR = {
    "A": "#1f7a4d",
    "B": "#3f7d20",
    "C": "#9a7d0a",
    "D": "#b5651d",
    "F": "#a32020",
}
_LABEL = "GTFS quality"
_FALLBACK_COLOR = "#5a5a5a"

# Feed-status segment appended to the badge so a stale feed reads at a glance,
# not only its letter grade. Keyed by metrics.expiry_status tokens; statuses not
# listed here (current, unknown) add no segment.
_STATUS_LABEL = {
    "lapsed": "feed expired",
    "stale": "feed expired",
    "expiring_soon": "expires soon",
}
_STATUS_COLOR = {
    "lapsed": "#a32020",
    "stale": "#a32020",
    "expiring_soon": "#b5651d",
}

# Rough monospace-ish width per character at 11px; good enough to size the
# rounded rectangle without measuring text in a browser.
_CHAR_PX = 6.5
_PAD = 8.0


def _segment_width(text: str) -> int:
    return round(len(text) * _CHAR_PX + 2 * _PAD)


def render_badge(grade: str, score: float | None = None, expiry_status: str | None = None) -> str:
    """Return an SVG badge string for a grade.

    When a score is given it is shown alongside the letter (e.g. "B 84"), which
    is the form most useful on an agency's own page. When expiry_status marks a
    feed as expired or expiring, a coloured status segment is appended so the
    feed's health reads at a glance, not only its grade.
    """
    grade = (grade or "?").upper()
    value = grade if score is None else f"{grade} {round(score)}"
    color = _GRADE_COLOR.get(grade[:1], _FALLBACK_COLOR)

    status = (expiry_status or "").lower()
    status_text = _STATUS_LABEL.get(status)
    status_color = _STATUS_COLOR.get(status, _FALLBACK_COLOR)

    left_w = _segment_width(_LABEL)
    mid_w = _segment_width(value)
    status_w = _segment_width(status_text) if status_text else 0
    total = left_w + mid_w + status_w
    label_x = left_w / 2
    value_x = left_w + mid_w / 2
    status_x = left_w + mid_w + status_w / 2
    title = f"{_LABEL}: {value}" + (f" ({status_text})" if status_text else "")
    # Escape everything text-derived; grade/score are constrained today, but this
    # is the one output path that builds markup, so don't rely on that.
    value_text = escape(value)
    label_text = escape(_LABEL)
    title_text = escape(title)
    title_attr = escape(title, {'"': "&quot;"})

    status_rect = ""
    status_label = ""
    if status_text:
        status_rect = (
            f'<rect x="{left_w + mid_w}" width="{status_w}" height="20" rx="3" '
            f'fill="{status_color}"/>'
        )
        status_label = f'<text x="{status_x:.0f}" y="14">{escape(status_text)}</text>'

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" '
        f'role="img" aria-label="{title_attr}">'
        f"<title>{title_text}</title>"
        f'<rect width="{total}" height="20" rx="3" fill="#2b2b2b"/>'
        f'<rect x="{left_w}" width="{mid_w}" height="20" rx="3" fill="{color}"/>'
        f'<rect x="{left_w}" width="4" height="20" fill="{color}"/>'
        f"{status_rect}"
        f'<g fill="#ffffff" font-family="Verdana,Geneva,sans-serif" '
        f'font-size="11" text-anchor="middle">'
        f'<text x="{label_x:.0f}" y="14">{label_text}</text>'
        f'<text x="{value_x:.0f}" y="14" font-weight="bold">{value_text}</text>'
        f"{status_label}"
        f"</g></svg>\n"
    )


# Conformance mark colours: a single green seal, awarded only on a clean pass.
_MARK_LABEL = "GTFS"
_MARK_VALUE = "conformant"
_MARK_COLOR = "#1f7a4d"


def render_mark() -> str:
    """Return an SVG seal for the conformance mark.

    Only written when a feed earns the mark, so it carries no "not yet" state;
    its mere presence is the credential. Self-contained and titled for screen
    readers, like the grade badge.
    """
    left_w = _segment_width(_MARK_LABEL)
    right_w = _segment_width(_MARK_VALUE)
    total = left_w + right_w
    label_x = left_w / 2
    value_x = left_w + right_w / 2
    title = f"{_MARK_LABEL} {_MARK_VALUE}"
    title_text = escape(title)
    title_attr = escape(title, {'"': "&quot;"})
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" '
        f'role="img" aria-label="{title_attr}">'
        f"<title>{title_text}</title>"
        f'<rect width="{total}" height="20" rx="3" fill="#2b2b2b"/>'
        f'<rect x="{left_w}" width="{right_w}" height="20" rx="3" fill="{_MARK_COLOR}"/>'
        f'<rect x="{left_w}" width="4" height="20" fill="{_MARK_COLOR}"/>'
        f'<g fill="#ffffff" font-family="Verdana,Geneva,sans-serif" '
        f'font-size="11" text-anchor="middle">'
        f'<text x="{label_x:.0f}" y="14">{escape(_MARK_LABEL)}</text>'
        f'<text x="{value_x:.0f}" y="14" font-weight="bold">{escape(_MARK_VALUE)}</text>'
        f"</g></svg>\n"
    )
