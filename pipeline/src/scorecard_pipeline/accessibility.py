"""Accessibility-data deepening: checks that make a feed usable by everyone.

Modeled on the open-source BlinkTag gtfs-accessibility-validator and the
California Transit Data Guidelines. These checks look past whether an
accessibility field is present and ask whether the data actually serves riders
who rely on it: route colors a low-vision rider can read, stop names a screen
reader pronounces correctly, and step-free navigation inside stations.

Findings here are zero-deduction in this slice (wiring and weighting are a
separate pass); they exist to name concrete, respectful fixes. The
gtfs-validator covers structural validity of these same files.
"""

from __future__ import annotations

from .gtfs import read_tables
from .metrics import Finding

# WCAG 2.1 AA requires a contrast ratio of at least 4.5:1 for normal-size text.
# A route badge is small colored text, so this is the right bar for route_color
# against route_text_color.
WCAG_AA_CONTRAST_RATIO = 4.5

# GTFS defaults when a color field is blank: white background, black text.
_DEFAULT_ROUTE_COLOR = "FFFFFF"
_DEFAULT_ROUTE_TEXT_COLOR = "000000"

# Short tokens that screen readers commonly mispronounce or read as a letter
# string when a stop name lacks a tts_stop_name override. Matched case-folded
# against whole words, so "Saint" and "Avenue" spelled out are not flagged.
_TTS_ABBREVIATIONS = frozenset(
    {
        "st",
        "ave",
        "av",
        "blvd",
        "rd",
        "dr",
        "ln",
        "ct",
        "hwy",
        "pkwy",
        "ne",
        "nw",
        "se",
        "sw",
        "ft",
        "jct",
    }
)

# Punctuation that screen readers handle inconsistently inside a stop name.
# "&" is read "ampersand" or skipped; "/" and "@" are read literally or dropped.
_TTS_PUNCTUATION = ("&", "/", "@", "+")


def _relative_luminance(hex_color: str) -> float | None:
    """WCAG relative luminance of an sRGB hex color, or None if unparseable.

    Follows the WCAG 2.1 definition: each channel is normalized to 0-1,
    linearized, then combined with the standard luminance weights.
    """
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        channels = [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    except ValueError:
        return None
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    r, g, b = linear
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(color_a: str, color_b: str) -> float | None:
    """WCAG contrast ratio between two hex colors, or None if either is invalid."""
    la = _relative_luminance(color_a)
    lb = _relative_luminance(color_b)
    if la is None or lb is None:
        return None
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def route_color_contrast_findings(routes_rows: list[dict[str, str]]) -> list[Finding]:
    """Flag routes whose color and text color fall below WCAG-AA contrast.

    A route badge that pairs, say, a mid-gray fill with white text is hard to
    read for low-vision riders and washes out in bright sun at the stop. We
    compute the same contrast ratio browsers and accessibility audits use and
    flag any route under 4.5:1. Blank colors take the GTFS default of black text
    on white, which passes, so a feed that simply omits colors is not flagged.
    """
    low_contrast: list[str] = []
    for row in routes_rows:
        set_color = row.get("route_color", "").strip()
        set_text = row.get("route_text_color", "").strip()
        # Only judge routes that set at least one color of their own; a fully
        # default route is the passing default and not the agency's choice.
        if not (set_color or set_text):
            continue
        bg = set_color or _DEFAULT_ROUTE_COLOR
        fg = set_text or _DEFAULT_ROUTE_TEXT_COLOR
        ratio = _contrast_ratio(bg, fg)
        if ratio is None:
            continue
        if ratio < WCAG_AA_CONTRAST_RATIO:
            label = (
                row.get("route_short_name", "").strip()
                or row.get("route_long_name", "").strip()
                or row.get("route_id", "").strip()
                or "a route"
            )
            low_contrast.append(label)
    if not low_contrast:
        return []
    shown = ", ".join(low_contrast[:5])
    if len(low_contrast) > 5:
        shown += ", and more"
    return [
        Finding(
            code="scorecard_route_color_low_contrast",
            severity="WARNING",
            count=len(low_contrast),
            what=f"{len(low_contrast)} route badge(s) pair a color and text color below "
            f"the WCAG 4.5:1 contrast bar ({shown}).",
            why="Riders with low vision struggle to read a low-contrast route badge. "
            "It also washes out on a phone screen in sunlight at the stop.",
            fix="Adjust route_color or route_text_color so each pair clears 4.5:1. "
            "Often switching the text between black and white is enough.",
            effort="A per-route color setting in your scheduling software.",
            deduction=0.0,
        )
    ]


def _name_needs_tts(name: str) -> bool:
    """True when a stop name has abbreviations or punctuation a screen reader
    is likely to mispronounce, so a tts_stop_name override would help."""
    if any(p in name for p in _TTS_PUNCTUATION):
        return True
    for token in name.replace(".", " ").replace(",", " ").split():
        word = "".join(c for c in token if c.isalpha())
        if word.casefold() in _TTS_ABBREVIATIONS:
            return True
    return False


def tts_stop_name_findings(stops_rows: list[dict[str, str]]) -> list[Finding]:
    """Note stops whose name a screen reader may mispronounce and that have no
    tts_stop_name override.

    tts_stop_name lets an agency spell a stop the way it should sound: "Main
    Street and Second Avenue" instead of "Main St & 2nd Ave", which a screen
    reader may read as "Main saint" or skip the ampersand. We only flag stops
    that both look risky and lack the override, so a feed that already provides
    tts_stop_name is left alone.
    """
    flagged: list[str] = []
    for row in stops_rows:
        name = row.get("stop_name", "").strip()
        if not name:
            continue
        if row.get("tts_stop_name", "").strip():
            continue
        if _name_needs_tts(name):
            flagged.append(name)
    if not flagged:
        return []
    shown = ", ".join(f'"{n}"' for n in flagged[:3])
    if len(flagged) > 3:
        shown += ", and more"
    return [
        Finding(
            code="scorecard_stop_name_needs_tts",
            severity="INFO",
            count=len(flagged),
            what=f"{len(flagged)} stop name(s) use abbreviations or symbols a screen "
            f"reader may mispronounce, with no spoken form set ({shown}).",
            why="A screen reader speaks the raw name. 'Main St & 2nd Ave' can come "
            "out as 'Main saint', or lose the ampersand.",
            fix="Add tts_stop_name with the spoken form, e.g. 'Main Street and Second "
            "Avenue', for the affected stops.",
            effort="A short text field per affected stop; start with the busiest.",
            deduction=0.0,
        )
    ]


def pathway_sufficiency_findings(
    stops_rows: list[dict[str, str]],
    pathways_rows: list[dict[str, str]],
    levels_rows: list[dict[str, str]],
) -> list[Finding]:
    """Flag a station-modeling feed that lacks the pathways or levels data a
    wheelchair user needs to navigate step-free.

    This is relevant only to feeds that model stations (location_type 1) or
    entrances (location_type 2). A flat stop-only feed, which is most small and
    rural agencies, is complete as is and gets nothing here.
    """
    location_types = {row.get("location_type", "").strip() for row in stops_rows}
    models_stations = "1" in location_types or "2" in location_types
    if not models_stations:
        return []

    missing: list[str] = []
    if not pathways_rows:
        missing.append("pathways.txt")
    if not levels_rows:
        missing.append("levels.txt")
    if not missing:
        return []

    missing_list = " and ".join(missing)
    return [
        Finding(
            code="scorecard_station_missing_step_free_data",
            severity="WARNING",
            count=len(missing),
            what=f"This feed models stations or entrances but has no {missing_list}.",
            why="Without pathways and levels, a wheelchair user can't tell if a "
            "step-free route exists inside the station. Trip planners can't route "
            "anyone through it.",
            fix="Add pathways.txt connecting entrances, platforms, and elevators, and "
            "levels.txt for each floor, so the step-free route is described.",
            effort="Worth it for multi-level or large stations; flat stops don't need it.",
            deduction=0.0,
        )
    ]


def accessibility_audit(gtfs_zip_path: str) -> list[Finding]:
    """Read the tables these checks need and run the full accessibility audit."""
    tables = read_tables(
        gtfs_zip_path,
        ["routes.txt", "stops.txt", "pathways.txt", "levels.txt"],
    )
    findings: list[Finding] = []
    findings.extend(route_color_contrast_findings(tables["routes.txt"]))
    findings.extend(tts_stop_name_findings(tables["stops.txt"]))
    findings.extend(
        pathway_sufficiency_findings(
            tables["stops.txt"], tables["pathways.txt"], tables["levels.txt"]
        )
    )
    return findings
