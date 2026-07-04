"""Generate crawlable static HTML from published artifacts (SEO).

The web app is a hash-routed single-page app, so its agency pages, rollups, and
fix guides are not individually indexable: search engines see one URL. This
renders a static, server-rendered HTML page per agency, per rollup, and per fix
code at a real path, plus a static agency index, sitemap.xml, and robots.txt, so
the content can be crawled and ranked. Each page carries a unique title, meta
description, canonical URL, Open Graph tags, and JSON-LD, and links into the
interactive app.

Output goes under web/ (the Pages deploy copies web/. to the site root), so the
pages are served at /agency/<id>/, /program/<id>/, and /fix/<code>/.
"""

from __future__ import annotations

# This module emits HTML; long literal lines (URLs, markup) are inherent.
# ruff: noqa: E501
import csv
import datetime as dt
import io
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .anomaly import latest_anomaly
from .atomfeed import agency_change_feed, site_change_feed
from .config import artifacts_dir
from .conformance import assess as conformance_assess
from .constants_export import GRADE_RANK, TIER_LABELS
from .directory import build_directory
from .feeddiff import FeedDiff, diff_artifacts
from .findings_national import agency_findings, plain_language_coverage
from .fixlog import load_fixlog
from .google_gate import from_artifact as google_from_artifact
from .metrics import expiry_status
from .mobilitydb import canonical_state
from .ntd import assess as ntd_assess
from .pages_tools import (
    _render_check_page,
    _render_compare_page,
    _render_query_page,
    _render_tools_page,
)
from .rule_links import RULE_LINKS, RuleLink, rule_link_for
from .score import letter_grade
from .site_shell import (  # noqa: F401  (re-exported: the site's shared shell)
    BASE_URL,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    SEVERITY_LABELS,
    STATIC_NAV_PAGES,
    _breadcrumb,
    _grade_class,
    _nav_active,
    _nav_html,
    _nav_stops_html,
    _page,
    _redirect_page,
    _repo_root,
    esc,
    sync_static_navs,
)
from .timemachine import history_events
from .tool_profiles import detect_tool

FIX_CODES_WITH_PAGES: set[str] = set()  # filled in by render_fixes()


def _route_rule() -> str:
    dots = '<span class="stopdot"></span>'
    return (
        '<div class="route-rule" role="presentation"><span class="stopdot"></span>'
        f'<span class="seg"></span>{dots}<span class="seg"></span>{dots}'
        '<span class="seg"></span><span class="stopdot"></span></div>'
    )


def _fix_guide_link(code: str) -> str:
    if code in FIX_CODES_WITH_PAGES:
        return f' · <a class="fix-guide" href="/fix/{esc(code)}/">Read the fix guide</a>'
    return ""


def _rule_ref_link(code: str) -> str:
    """Inline link to a finding's authoritative rule, for the 'Validator rule'
    line on agency findings. Links the canonical gtfs-validator notice (or the
    relevant GTFS Best Practice / reference) so the Cal-ITP / state-DOT reader
    lands on the same rule their statewide reports already cite. Empty when no
    honest mapping exists (some scorecard-only completeness checks)."""
    link = rule_link_for(code)
    if link is None:
        return ""
    where = (
        "GTFS Best Practices"
        if link.kind == "best_practice"
        else ("the GTFS Schedule reference" if link.kind == "reference" else "the validator rules")
    )
    text = f"See {link.authority}"
    return f' · <a class="rule-ref" href="{esc(link.url)}">{esc(text)}</a><span class="visually-hidden"> (opens {esc(where)} on an external site)</span>'


def _fix_rule_reference(code: str) -> str:
    """The authoritative-rule reference block shown on a /fix/<code>/ page.

    Surfaces the canonical rule a finding maps to: a gtfs-validator notice, a
    GTFS Best Practice, or a GTFS Schedule reference section. Where the
    scorecard's code diverges from the validator notice, the canonical notice is
    named as an alias so the audience recognises it."""
    link: RuleLink | None = RULE_LINKS.get(code)
    if link is None:
        return ""
    if link.is_validator:
        notice = link.canonical or code
        if link.canonical:
            lead = (
                f"This scorecard finding maps to the canonical MobilityData "
                f"GTFS Validator notice <code>{esc(notice)}</code>, the same rule "
                f"behind the statewide GTFS quality reports."
            )
        else:
            lead = (
                f"<code>{esc(code)}</code> is a canonical MobilityData GTFS "
                f"Validator notice, the same rule behind the statewide GTFS "
                f"quality reports."
            )
        link_text = f"Read the authoritative rule for {notice} in the GTFS Validator rules"
    elif link.kind == "best_practice":
        lead = (
            "The GTFS Validator does not flag this (the field is valid GTFS when "
            "left empty), so the expectation comes from the community GTFS Best "
            "Practices."
        )
        link_text = "Read the relevant GTFS Best Practice"
    else:  # reference
        lead = (
            "The GTFS Validator does not flag this, so the expectation comes from "
            "the field's definition in the GTFS Schedule reference."
        )
        link_text = "Read the relevant GTFS Schedule reference section"
    return (
        '\n<h2 class="section-title">Authoritative rule</h2>'
        f"\n<p>{lead} "
        f'<a class="rule-ref" href="{esc(link.url)}">{esc(link_text)}</a>.'
        '<span class="visually-hidden"> (opens on an external site)</span></p>'
    )


def _finding_codes(artifact: dict[str, Any]) -> dict[str, str]:
    """Map each finding code in an artifact to its 'what' text, across measured
    categories. Used to diff one run against the next."""
    out: dict[str, str] = {}
    for cat in artifact.get("categories", {}).values():
        if cat.get("status") == "measured":
            for f in cat.get("findings", []):
                code = f.get("code")
                if code:
                    out.setdefault(str(code), str(f.get("what", "")))
    return out


def _cleared_findings(prev: dict[str, Any] | None, cur: dict[str, Any]) -> list[tuple[str, str]]:
    """Findings present last run but gone this run: a fix that landed. Returns
    (code, what) pairs, where `what` is the previous run's description."""
    if not prev:
        return []
    current = _finding_codes(cur)
    return [(code, what) for code, what in _finding_codes(prev).items() if code not in current]


def _history_section(history: list[dict[str, Any]] | None) -> str:
    """A plain-language timeline of what changed across this feed's history, the
    text companion to the trend chart (and the screen-reader-friendly version of
    it). Empty when the feed has been steady."""
    events = history_events(history or [])
    if not events:
        return ""
    items = "".join(
        f'<li class="event"><span class="event-date">{esc(e.date)}</span> {esc(e.detail)}</li>'
        for e in events[:12]
    )
    return (
        '<section aria-labelledby="history-h"><h2 class="section-title" id="history-h">'
        "What changed over time</h2>"
        '<p class="page-lede">A plain-language history of this feed, newest first.</p>'
        f'<ul class="events">{items}</ul></section>'
    )


def _spark_svg(
    points: list[tuple[str, Any]],
    *,
    aria_label: str,
    w: int = 320,
    h: int = 64,
    pad: float = 8,
    y_min: float = 0.0,
    y_max: float = 100.0,
    css_class: str = "trend-spark",
    dot_r: float = 2.5,
    last_dot_r: float = 4,
    stroke_width: float = 2,
) -> str:
    """One SVG sparkline in the site's three-part accessible pattern, shared by
    the per-agency trend, the national-average chart, and the per-row minis.

    ``points`` is (label, value) pairs oldest first (at least two): the value
    positions the point, clamped to ``y_min``..``y_max`` (pass the data's own
    min/max for an autoscaled line), and its raw text rides in the dot's
    ``<title>`` so hover and long-press get a native readout. Every dot carries
    that tooltip, the last one emphasised. The chart stays ``role="img"`` with
    the full series appended to ``aria_label``, so the numbers are never
    image-only; callers pair it with a text table for the operable equivalent.
    """
    n = len(points)
    span = max(y_max - y_min, 1.0)

    def px(i: int) -> float:
        return pad + (i * (w - 2 * pad) / (n - 1))

    def py(value: Any) -> float:
        v = max(y_min, min(y_max, float(value)))
        return h - pad - ((v - y_min) / span) * (h - 2 * pad)

    pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, (_, v) in enumerate(points))
    series = "; ".join(f"{label} {v}" for label, v in points)
    dots = "".join(
        f'<circle class="trend-dot" cx="{px(i):.1f}" cy="{py(v):.1f}" '
        f'r="{last_dot_r if i == n - 1 else dot_r:g}" fill="currentColor">'
        f"<title>{esc(str(label))}: {esc(str(v))}</title></circle>"
        for i, (label, v) in enumerate(points)
    )
    return (
        f'<svg class="{css_class}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" '
        f'aria-label="{esc(aria_label)}: {esc(series)}">'
        f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="{stroke_width:g}" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        f"{dots}</svg>"
    )


def _spark_mini(history: list[dict[str, Any]] | None, name: str) -> str:
    """A compact per-row score sparkline for the leaderboard-style tables, in
    the same accessible pattern as the big trend chart (dots with native
    tooltips, the series in the aria-label). Autoscaled to its own score range,
    like the national chart, so a few-point move is visible in a table cell (a
    half-point margin keeps a flat series centred). Rows with fewer than two
    checks render an em dash instead of an empty chart."""
    points = [
        (str(p.get("date", "")), p["score"])
        for p in (history or [])
        if isinstance(p.get("score"), (int, float))
    ][-12:]
    if len(points) < 2:
        return '<span class="spark-none">&mdash;</span>'
    scores = [float(v) for _, v in points]
    return _spark_svg(
        points,
        aria_label=f"Score trend for {name}",
        w=80,
        h=20,
        pad=3,
        y_min=min(scores) - 0.5,
        y_max=max(scores) + 0.5,
        css_class="trend-spark spark-mini",
        dot_r=1.5,
        last_dot_r=1.5,
        stroke_width=1.5,
    )


def _trend_section(history: list[dict[str, Any]]) -> str:
    """An 'Over time' block: an overall-score line plus per-category change since
    the previous check. Mirrors the interactive app so static and SPA agree. The
    finding-level change (what cleared or newly appeared) lives in the feed-diff
    section below, so it is not repeated here."""
    if len(history) < 2:
        return (
            '<section aria-labelledby="trend-h"><h2 class="section-title" id="trend-h">Over time</h2>'
            '<p class="page-lede">This is the first scorecard for this agency. A trend and a '
            '"what changed" summary appear here once it has been checked more than once.</p></section>'
        )
    cur, prev = history[-1], history[-2]
    delta = round(cur["score"] - prev["score"], 1)
    direction = f"up {delta}" if delta > 0 else f"down {abs(delta)}" if delta < 0 else "unchanged"

    n = len(history)
    # The shared sparkline: a dot at every check with a native hover tooltip
    # (its date and score), the full series in the aria-label, and every number
    # repeated in the data table below.
    spark = _spark_svg(
        [(str(p["date"]), p["score"]) for p in history],
        aria_label=f"Overall score across {n} checks",
    )

    rows = []
    for key in CATEGORY_ORDER:
        a = (prev.get("categories") or {}).get(key)
        b = (cur.get("categories") or {}).get(key)
        if a is None or b is None:
            continue
        d = round(b - a, 1)
        text = f"up {d}" if d > 0 else f"down {abs(d)}" if d < 0 else "no change"
        sym = "&#9650;" if d > 0 else "&#9660;" if d < 0 else "&mdash;"
        cls = "delta-up" if d > 0 else "delta-down" if d < 0 else "delta-flat"
        rows.append(
            f'<li class="delta-row"><span class="delta-cat">{esc(CATEGORY_LABELS[key])}</span>'
            f'<span class="delta {cls}"><span aria-hidden="true">{sym}</span> {text}</span></li>'
        )
    deltas = f'<ul class="delta-list">{"".join(rows)}</ul>' if rows else ""

    # The "Show the numbers" table is the operable, screen-reader equivalent of
    # the sparkline: every check's date, score, and change from the check before,
    # with the change carried in words and an arrow, never colour alone.
    trows = []
    for i, p in enumerate(history):
        if i == 0:
            change = '<span class="delta delta-flat"><span aria-hidden="true">&mdash;</span> first check</span>'
        else:
            d = round(p["score"] - history[i - 1]["score"], 1)
            t = f"up {d}" if d > 0 else f"down {abs(d)}" if d < 0 else "no change"
            sym = "&#9650;" if d > 0 else "&#9660;" if d < 0 else "&mdash;"
            cls = "delta-up" if d > 0 else "delta-down" if d < 0 else "delta-flat"
            change = f'<span class="delta {cls}"><span aria-hidden="true">{sym}</span> {t}</span>'
        trows.append(
            f'<tr><th scope="row">{esc(str(p["date"]))}</th>'
            f"<td>{esc(str(p['score']))}</td><td>{change}</td></tr>"
        )
    data_table = (
        '<details class="trend-data"><summary>Show the numbers</summary>'
        '<table class="trend-table"><caption class="visually-hidden">Overall score by '
        "check, with the change from the previous check</caption>"
        '<thead><tr><th scope="col">Check</th><th scope="col">Score</th>'
        '<th scope="col">Change</th></tr></thead>'
        f"<tbody>{''.join(trows)}</tbody></table></details>"
    )

    return (
        '<section aria-labelledby="trend-h"><h2 class="section-title" id="trend-h">Over time</h2>'
        f'<p class="page-lede">Overall score across the last {n} checks &mdash; {direction} '
        f"since {esc(prev['date'])}.</p>"
        f'<div class="trend-chart">{spark}</div>'
        f"{data_table}"
        '<h3 class="trend-sub">What changed since your last check</h3>'
        f"{deltas}</section>"
    )


def _feeddiff_summary_line(diff: FeedDiff) -> str:
    """One plain-language sentence on the overall move since the last snapshot."""
    if diff.grade_moved:
        verb = "dropped" if diff.grade_dropped else "improved"
        return (
            f"Grade {verb} from {esc(diff.prev_grade)} to {esc(diff.curr_grade)} since "
            f"{esc(diff.prev_date)}."
        )
    d = round(diff.score_delta, 1)
    if d > 0:
        return f"Overall score rose {d} points since {esc(diff.prev_date)}."
    if d < 0:
        return f"Overall score fell {abs(d)} points since {esc(diff.prev_date)}."
    return f"Overall grade and score held steady since {esc(diff.prev_date)}."


def _feeddiff_feedstate_line(diff: FeedDiff) -> str:
    """Whether the published zip itself changed, in plain language."""
    if not diff.feed_bytes_changed:
        return f"Same feed file as {esc(diff.prev_date)}; the published zip did not change."
    size = ""
    if diff.size_delta:
        kb = round(diff.size_delta / 1024)
        if kb:
            size = f" ({'+' if kb > 0 else ''}{kb} KB)"
    return f"The feed file was re-published since {esc(diff.prev_date)}{size}."


def _feeddiff_finding_cards(changes: list[Any]) -> str:
    """New findings rendered as the same finding cards used elsewhere, so a
    regression reads exactly like the check it represents."""
    items = []
    for c in changes:
        sev = SEVERITY_LABELS.get(c.severity, c.severity)
        count = c.curr_count or 0
        noun = "instance" if count == 1 else "instances"
        items.append(
            f'<li class="finding"><div class="finding-head">'
            f'<span class="sev sev-{esc(str(c.severity).lower())}">{esc(sev)}</span>'
            f'<span class="count">{count} {noun}</span></div>'
            f'<p class="what">{esc(c.what)}</p>'
            f'<p class="code">Validator rule: {esc(c.code)}{_fix_guide_link(str(c.code))}{_rule_ref_link(str(c.code))}</p></li>'
        )
    return "".join(items)


def _feeddiff_changed_rows(changes: list[Any]) -> str:
    """Findings whose instance count moved, with direction stated in words."""
    rows = []
    for c in changes:
        before, after = c.prev_count or 0, c.curr_count or 0
        worse = after > before
        word = "up" if worse else "down"
        sym = "&#9650;" if worse else "&#9660;"
        # More instances of a problem is a decline; fewer is progress.
        cls = "delta-down" if worse else "delta-up"
        rows.append(
            f'<li class="cleared-row"><span class="delta {cls}">'
            f'<span aria-hidden="true">{sym}</span> {word}</span> {esc(c.what)} '
            f'({before} &rarr; {after}) <span class="code">({esc(c.code)})</span></li>'
        )
    return "".join(rows)


def _feeddiff_resolved_rows(changes: list[Any]) -> str:
    """Findings that cleared since the previous snapshot: fixes that landed."""
    return "".join(
        f'<li class="cleared-row"><span class="cleared-mark" aria-hidden="true">&#10003;</span> '
        f'{esc(c.what)} <span class="code">({esc(c.code)})</span></li>'
        for c in changes
    )


def _feeddiff_section(
    prev_artifact: dict[str, Any] | None, cur_artifact: dict[str, Any], agency_id: str
) -> str:
    """A snapshot-to-snapshot diff of this feed: what newly appeared, what cleared,
    and what changed in count, plus whether the feed file itself was re-published.

    The trend section above shows the score's shape; this shows the substance of
    the change a manager can act on. Rendered as accessible lists with the severity
    and direction stated in words, never by colour alone. Empty before there is a
    previous snapshot to compare against (the trend section covers the first
    check)."""
    if prev_artifact is None:
        return ""
    diff = diff_artifacts(prev_artifact, cur_artifact)
    feed_url = f"/agency/{esc(agency_id)}/feed.xml"
    subscribe = (
        '<p class="fineprint"><a href="' + feed_url + '">Subscribe to this feed’s '
        "changes (Atom)</a> to hear about grade drops in a reader, with no sign-up.</p>"
    )
    if not diff.has_changes:
        return (
            '<section aria-labelledby="feeddiff-h"><h2 class="section-title" id="feeddiff-h">'
            "What changed in this feed</h2>"
            f'<p class="page-lede">Nothing changed since {esc(diff.prev_date)}: the same feed '
            "file, the same grade, and the same findings.</p>"
            f"{subscribe}</section>"
        )

    blocks = []
    if diff.new:
        noun = "finding" if len(diff.new) == 1 else "findings"
        blocks.append(
            f'<h3 class="trend-sub">New since {esc(diff.prev_date)} ({len(diff.new)} {noun})</h3>'
            f'<ul class="findings">{_feeddiff_finding_cards(diff.new)}</ul>'
        )
    if diff.changed:
        blocks.append(
            '<h3 class="trend-sub">Changed counts</h3>'
            f'<ul class="cleared-list">{_feeddiff_changed_rows(diff.changed)}</ul>'
        )
    if diff.resolved:
        noun = "finding" if len(diff.resolved) == 1 else "findings"
        blocks.append(
            f'<h3 class="trend-sub">Resolved since {esc(diff.prev_date)} ({len(diff.resolved)} {noun})</h3>'
            f'<ul class="cleared-list">{_feeddiff_resolved_rows(diff.resolved)}</ul>'
        )

    return (
        '<section aria-labelledby="feeddiff-h"><h2 class="section-title" id="feeddiff-h">'
        "What changed in this feed</h2>"
        f'<p class="page-lede">{_feeddiff_summary_line(diff)}</p>'
        f'<p class="diff-feedstate">{_feeddiff_feedstate_line(diff)}</p>'
        f"{''.join(blocks)}{subscribe}</section>"
    )


def _grade_band(score: float) -> str:
    """Map a 0-100 score to a grade-band token (a/b/c/d/f) for bar color: the
    rubric's own letter (score.GRADE_BANDS), lowercased."""
    return letter_grade(score).lower()


def _accessibility_score(comp_cat: dict[str, Any]) -> float | None:
    """The accessibility sub-score (0-100) for a completeness category (ADR 0006).

    Prefers the structured ``accessibility`` block when the artifact carries it,
    and otherwise derives the same number from the wheelchair components that
    already-published artifacts contain, so the sub-score appears without a
    re-score. Returns None when the category is not measured.
    """
    if comp_cat.get("status") != "measured":
        return None
    details = comp_cat.get("details", {})
    acc = details.get("accessibility")
    if isinstance(acc, dict) and isinstance(acc.get("score"), (int, float)):
        return float(acc["score"])
    comp = details.get("components", {})
    if "wheelchair_stops" not in comp and "wheelchair_trips" not in comp:
        return None
    earned = float(comp.get("wheelchair_stops", 0)) + float(comp.get("wheelchair_trips", 0))
    return round(earned / 40 * 100, 1)  # 25 (stops) + 15 (trips) available


def _accessibility_substat(comp_cat: dict[str, Any]) -> str:
    """A small accessibility sub-score block for the Rider experience card."""
    score = _accessibility_score(comp_cat)
    if score is None:
        return ""
    shown = int(score) if float(score).is_integer() else score
    band = _grade_band(score)
    width = max(2, min(100, score))
    details = comp_cat.get("details", {})
    acc = details.get("accessibility") if isinstance(details.get("accessibility"), dict) else {}
    stated = acc.get("stops_stated_pct", details.get("wheelchair_boarding_pct"))
    marked = acc.get("stops_marked_accessible_pct", details.get("wheelchair_marked_accessible_pct"))
    note = "States accessibility, not verified physical usability."
    if isinstance(stated, (int, float)) and isinstance(marked, (int, float)):
        note = (
            f"{int(round(stated))}% of stops state accessibility "
            f"({int(round(marked))}% marked accessible). "
            "Reflects what the feed states, not verified physical usability."
        )
    return (
        '<div class="substat" role="group" aria-label="Accessibility sub-score">'
        '<div class="ptop"><span class="pname">Accessibility</span>'
        f'<span class="pscore">{shown}<span class="outof"> / 100</span></span></div>'
        f'<div class="pbar" role="meter" aria-valuenow="{shown}" aria-valuemin="0" '
        f'aria-valuemax="100" aria-label="Accessibility sub-score">'
        f'<span style="width:{width}%;background:var(--grade-{band})"></span></div>'
        f'<p class="pstat">{esc(note)}</p></div>'
    )


def _fares_substat(comp_cat: dict[str, Any]) -> str:
    """A small fares status line for the Rider experience card (ADR 0008): the
    fare model and whether fares are applied to trips. Renders nothing when fares
    are absent or fare-free, which the summary and findings already cover."""
    if comp_cat.get("status") != "measured":
        return ""
    fares = comp_cat.get("details", {}).get("fares")
    if not isinstance(fares, dict) or fares.get("fare_free"):
        return ""
    model = fares.get("model")
    if model not in ("v2", "legacy"):
        return ""
    model_label = "Fares v2" if model == "v2" else "Legacy fares"
    note = (
        "Fares are applied to trips."
        if fares.get("applied")
        else "Products are published but not applied to any trip yet."
    )
    return (
        '<div class="substat" role="group" aria-label="Fares">'
        '<div class="ptop"><span class="pname">Fares</span>'
        f'<span class="pscore">{esc(model_label)}</span></div>'
        f'<p class="pstat">{esc(note)}</p></div>'
    )


def _board_hero(
    agency_name: str,
    agency_id: str,
    artifact: dict[str, Any],
    history: list[dict[str, Any]],
    peer_record: dict[str, Any] | None = None,
) -> str:
    """The dark status-board hero: a split-flap grade reel, score, trend, and
    status chips. Shared visual language with the interactive app."""
    o = artifact["overall"]
    g = str(o["grade"]).upper()[:1]
    idx = GRADE_RANK.get(g, 0)

    chips = []
    days = (
        artifact.get("categories", {})
        .get("freshness", {})
        .get("details", {})
        .get("days_until_expiry")
    )
    if isinstance(days, (int, float)) and not isinstance(days, bool):
        days = int(days)
        if days <= 0:
            chips.append('<span class="chip warn">Feed expired</span>')
        elif days < 30:
            chips.append(f'<span class="chip warn">Expires in {days} days</span>')
        else:
            chips.append(f'<span class="chip ok">Covers {days} days</span>')
    # Key the chip off the accessibility sub-score specifically (ADR 0006), not
    # the blended completeness score, so it stops firing on (for example) a feed
    # that is accessible but missing fares, and starts firing when accessibility
    # itself is the gap.
    comp = artifact.get("categories", {}).get("completeness", {})
    a11y = _accessibility_score(comp)
    if a11y is not None and a11y < 70:
        chips.append('<span class="chip warn">Accessibility gaps</span>')
    # Flexible (demand-responsive) service shown neutrally (ADR 0007), the same
    # way seasonal service and a missing realtime feed are.
    flex = comp.get("details", {}).get("flex", {})
    if isinstance(flex, dict) and flex.get("has_flex"):
        chips.append('<span class="chip">Flexible service</span>')
    pathways = comp.get("details", {}).get("pathways", {})
    if isinstance(pathways, dict) and pathways.get("has_pathways"):
        chips.append('<span class="chip">Station pathways</span>')
    if artifact.get("categories", {}).get("realtime", {}).get("status") != "measured":
        chips.append('<span class="chip">No realtime feed</span>')

    if len(history) >= 2:
        prev, cur = history[-2], history[-1]
        d = round(cur["score"] - prev["score"], 1)
        if d > 0:
            trend = f'<span aria-hidden="true">&#9650;</span> up {d} since {esc(prev["date"])} &middot; {esc(prev["grade"])} &rarr; {esc(cur["grade"])}'
        elif d < 0:
            trend = (
                f'<span aria-hidden="true">&#9660;</span> down {abs(d)} since {esc(prev["date"])}'
            )
        else:
            trend = f"unchanged since {esc(prev['date'])}"
    else:
        trend = "First scorecard for this agency"

    reel = (
        f'<div class="reel" role="img" aria-label="Overall grade {esc(g)}" '
        f'style="--flap-end: calc(var(--reel-h) * -{idx})">'
        '<div class="reel-strip"><span>F</span><span>D</span><span>C</span><span>B</span><span>A</span></div></div>'
    )
    return (
        '<div class="board-hero"><div class="board-inner">'
        f'<p class="board-kicker"><span class="blip" aria-hidden="true"></span>Feed status &middot; checked {esc(artifact["snapshot_date"])}</p>'
        f'<h1 class="board-title">{esc(agency_name)}</h1>'
        '<p class="board-sub">Based on the feed this agency publishes</p>'
        f'<div class="grade-block">{reel}'
        f'<div class="score-block"><div><span class="score-big">{o["score"]}</span><span class="score-of"> / 100</span></div>'
        f'<p class="score-trend">{trend}</p>{_peer_context(peer_record)}'
        f'<div class="chips">{"".join(chips)}</div></div></div>'
        "</div></div>"
    )


# The app reads the same TIER_LABELS from web/src/generated/constants.js
# (rendered from constants_export.TIER_LABELS by `scorecard render-constants`),
# so the static page and the interactive view agree by construction.


def _peer_context(record: dict[str, Any] | None) -> str:
    """Where this agency stands against the national set and its size peers, the
    server-rendered twin of the app's peer line, so crawlers and no-JS visitors
    see the same context. Empty when the directory record or its percentiles are
    missing."""
    if not record:
        return ""
    nat = record.get("national_percentile")
    if nat is None:
        return ""
    peer = record.get("peer_percentile")
    tier_key = record.get("size_tier")
    tier = TIER_LABELS.get(str(tier_key), str(tier_key))
    peer_part = (
        f" and {peer}% of {esc(tier)} agencies"
        if peer is not None and tier_key not in (None, "unknown")
        else ""
    )
    where = f" Operates in {esc(record['state'])}." if record.get("state") else ""
    return f'<p class="peer-context">Ahead of {nat}% of all tracked agencies{peer_part}.{where}</p>'


def _ago(now: dt.datetime, then: dt.datetime) -> str:
    """Plain-language gap between two instants ('3 hours ago', '2 days ago')."""
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 90 * 60:
        minutes = max(1, seconds // 60)
        return "just now" if seconds < 60 else f"{minutes} minutes ago"
    hours = seconds // 3600
    if hours < 36:
        return f"{hours} hours ago"
    days = seconds // 86400
    return f"{days} days ago"


def _liveness_note(record: dict[str, Any] | None, now: dt.datetime | None = None) -> str:
    """How current the change detection is for this feed: when it was last checked
    and last seen to change, from the liveness state. Empty when not yet checked,
    so a feed the monitor has not reached shows nothing rather than a blank claim."""
    if not record:
        return ""
    now = now or dt.datetime.now(dt.UTC)
    try:
        checked = dt.datetime.fromisoformat(str(record.get("checked_at")))
    except (TypeError, ValueError):
        return ""
    parts = [f"Checked for changes {_ago(now, checked)}"]
    changed_raw = record.get("changed_at")
    changed = None
    if changed_raw:
        try:
            changed = dt.datetime.fromisoformat(str(changed_raw))
        except (TypeError, ValueError):
            changed = None
    if changed:
        parts.append(f"last changed {_ago(now, changed)}")
    status = record.get("status")
    if isinstance(status, int) and status not in (200, 304):
        parts.append(f"last fetch returned HTTP {status}")
    return f'<p class="monitoring-note">{esc("; ".join(parts))}.</p>'


_OUTREACH_CODES = ("scorecard_feed_expired", "scorecard_feed_expiring_soon")


def _outreach_note(artifact: dict[str, Any], canonical: str) -> str | None:
    """A short note a liaison can paste into an email to an agency whose feed
    has expired or is about to. Built from the freshness finding so the words
    match the scorecard, and only when there is an expiry finding to act on."""
    fresh = artifact.get("categories", {}).get("freshness", {})
    finding = next((f for f in fresh.get("findings", []) if f.get("code") in _OUTREACH_CODES), None)
    if not finding:
        return None
    name = artifact["agency"]["name"]
    # When the producing tool is known, say who actually makes the change so the
    # note lands as a next step, not a homework assignment (RESEARCH-ROADMAP R5).
    tool = detect_tool(artifact.get("feed", {}).get("static_url"))
    tool_line = ""
    if tool and tool.kind == "hosted":
        tool_line = (
            f"Your feed is produced by {tool.name}, so the quickest path is "
            f"usually forwarding this to your {tool.name} contact.\n\n"
        )
    return (
        f"Hi {name} team,\n\n"
        f"{finding.get('what', '')} {finding.get('why', '')}\n\n"
        f"The fix is usually one export setting: {finding.get('fix', '')}\n\n"
        f"{tool_line}"
        f"This came from your GTFS data quality scorecard, which checks the feed "
        f"you publish and lists the fixes in plain language: {canonical}"
    )


# Wires every .copy-btn on the page (outreach note, vendor request) to copy the
# textarea it points at. Emitted once per page; the textarea is selectable on its
# own, so the note is reachable with no JavaScript.
_COPY_SCRIPT = (
    "<script>document.querySelectorAll('.copy-btn').forEach(function(b){"
    "b.addEventListener('click',function(){"
    "var t=document.getElementById(b.getAttribute('data-copy'));t.focus();t.select();"
    "if(navigator.clipboard){navigator.clipboard.writeText(t.value);}"
    "var o=b.textContent;b.textContent='Copied';"
    "setTimeout(function(){b.textContent=o;},1500);});});</script>"
)


def _embed_section(agency_id: str, agency_name: str) -> str:
    """A copy-paste embed so an agency can show its live grade on its own site or
    feed README. The badge image regenerates daily, so the embed stays current
    with zero backend, and it links back to the full scorecard."""
    badge_svg = f"{BASE_URL}/data/artifacts/{agency_id}/badge.svg"
    badge_json = f"{BASE_URL}/data/artifacts/{agency_id}/badge.json"
    page = f"{BASE_URL}/agency/{agency_id}/"
    markdown = f"[![GTFS data quality]({badge_svg})]({page})"
    shields = f"https://img.shields.io/endpoint?url={badge_json}"
    return (
        '<section class="embed" id="embed" aria-labelledby="embed-h">'
        '<h2 class="section-title" id="embed-h">Show your grade</h2>'
        '<p class="page-lede">Put a live badge on your agency site or feed README. It updates '
        "daily and links back to this scorecard.</p>"
        f'<p><img src="/data/artifacts/{esc(agency_id)}/badge.svg" '
        f'alt="GTFS data quality grade for {esc(agency_name)}"></p>'
        '<label class="visually-hidden" for="embed-md">Badge Markdown</label>'
        f'<textarea id="embed-md" class="outreach-text" rows="2" readonly>{esc(markdown)}</textarea>'
        '<button type="button" class="copy-btn" data-copy="embed-md">Copy Markdown</button>'
        f'<p class="fineprint">Prefer a shields.io style? Point a '
        f'<a href="{esc(shields)}">dynamic endpoint badge</a> at the published '
        f"<code>badge.json</code>.</p>"
        "</section>"
    )


def _outreach_section(artifact: dict[str, Any], canonical: str) -> str:
    """The 'Send the agency a note' block: a ready-to-paste message with a copy
    button (the page emits the copy script once)."""
    note = _outreach_note(artifact, canonical)
    if not note:
        return ""
    return (
        '<section class="outreach" id="send-note" aria-labelledby="send-note-h">'
        '<h2 class="section-title" id="send-note-h">Send the agency a note</h2>'
        '<p class="page-lede">Supporting this agency? Copy this and email it to them. '
        "It names what lapsed, why it matters to riders, and the one setting to change.</p>"
        '<label class="visually-hidden" for="outreach-text">Outreach note</label>'
        f'<textarea id="outreach-text" class="outreach-text" rows="9" readonly>{esc(note)}</textarea>'
        '<button type="button" class="copy-btn" data-copy="outreach-text">Copy note</button>'
        "</section>"
    )


def _vendor_request(artifact: dict[str, Any], canonical: str) -> str | None:
    """A ready-to-send fix request a manager can forward to whoever runs their
    GTFS export (the vendor or scheduling tool). Built from the top fixes so the
    words match the scorecard, with the validator notice codes and the fix-guide
    links, so a non-technical manager can act without translating anything."""
    fixes = artifact.get("top_fixes", [])
    if not fixes:
        return None
    name = artifact["agency"]["name"]
    overall = artifact["overall"]
    lines = [
        f"Hi,\n\nOur GTFS feed ({name}) scored {overall['grade']} "
        f"({overall['score']} out of 100) on the GTFS Scorecard. Could you review "
        "these in our export settings:\n",
    ]
    for i, f in enumerate(fixes, 1):
        lines.append(f"{i}. {f.get('fix', '')}")
        what = f.get("what", "")
        code = f.get("code", "")
        if what:
            lines.append(f"   What: {what}")
        if code:
            lines.append(f"   Validator notice: {code}")
            if code in FIX_CODES_WITH_PAGES:
                lines.append(f"   Guide: {BASE_URL}/fix/{code}/")
        lines.append("")
    lines.append(f"Full scorecard: {canonical}")
    return "\n".join(lines)


def _vendor_section(artifact: dict[str, Any], canonical: str) -> str:
    """The 'Send your vendor a fix request' block: the forwardable artifact a
    manager who does not control the export needs. When the feed host identifies
    the producing tool, the heading and lede name it and say how the fix lands
    there (RESEARCH-ROADMAP R5); otherwise the copy stays generic."""
    note = _vendor_request(artifact, canonical)
    if not note:
        return ""
    tool = detect_tool(artifact.get("feed", {}).get("static_url"))
    heading = "Send your vendor a fix request"
    lede = (
        "You may not control the GTFS export yourself. Copy this "
        "and send it to whoever runs your scheduling software export. It names each fix "
        "with the validator notice and a guide link."
    )
    if tool:
        lede = f"{tool.request_lede} Each fix names the validator notice and a guide link."
        if tool.kind == "hosted":
            heading = f"Send {tool.name} a fix request"
    return (
        '<section class="outreach" id="send-vendor" aria-labelledby="send-vendor-h">'
        f'<h2 class="section-title" id="send-vendor-h">{esc(heading)}</h2>'
        f'<p class="page-lede">{esc(lede)}</p>'
        '<label class="visually-hidden" for="vendor-text">Fix request</label>'
        f'<textarea id="vendor-text" class="outreach-text" rows="10" readonly>{esc(note)}</textarea>'
        '<button type="button" class="copy-btn" data-copy="vendor-text">Copy request</button>'
        "</section>"
    )


# The MapLibre build the agency map shares with the national map (/map/). Pinned
# here once; bumped in one place. The agency map adds it to the page only when the
# feed actually has geometry to draw, so a feed without shapes pays nothing.
_AGENCY_MAP_STOP_LIST_CAP = 250


# The agency map's client script. Kept as a plain string with a JSON-encoded
# placeholder for the geometry URL, so the JavaScript braces don't need doubling
# the way an f-string would force. Linked brushing ties each map line to its row
# in the route table below; the table stays the accessible primary, so brushing
# adds no tab stops and the canvas remains aria-hidden.
_AGENCY_MAP_JS = r"""      (function () {
        if (!window.maplibregl) return;
        var geoUrl = __GEO_URL_JSON__;
        var reduce = window.matchMedia
          && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        var NONE = "__none__";  // sentinel route id; no real route matches

        // Route id -> table row, so a hovered/selected map line can light up its
        // row and vice versa. Visual only: the row text is the accessible source.
        var rows = {};
        document.querySelectorAll(".route-table tr[data-route-key]").forEach(function (tr) {
          rows[tr.getAttribute("data-route-key")] = tr;
        });
        var current = null;   // route id currently brushed, or null
        var pinned = null;    // sticky selection from a tap/click, or null
        var mapReady = false;

        function paintRow(key, on) {
          var tr = rows[key];
          if (tr) tr.classList.toggle("is-brushed", on);
        }
        function highlight(key) {
          if (key === current) return;
          if (current !== null) paintRow(current, false);
          current = key;
          if (mapReady) {
            map.setFilter("routes-hi", ["==", ["get", "route_id"], key === null ? NONE : key]);
          }
          if (key !== null) paintRow(key, true);
        }

        // Hover on desktop; tap to pin on touch (no hover there). Rows carry no
        // links, so a click only toggles the highlight.
        Object.keys(rows).forEach(function (key) {
          var tr = rows[key];
          tr.addEventListener("mouseenter", function () { highlight(key); });
          tr.addEventListener("mouseleave", function () { highlight(pinned); });
          tr.addEventListener("click", function () {
            pinned = (pinned === key) ? null : key;
            highlight(pinned);
          });
        });

        var map = new maplibregl.Map({
          container: "route-map",
          style: "https://tiles.openfreemap.org/styles/positron",
          center: [-96, 38], zoom: 3,
          attributionControl: false,
          keyboard: false
        });
        // Take the canvas out of the tab order synchronously (not only on load),
        // so this aria-hidden map never briefly holds a focusable canvas while a
        // slower basemap style is still loading (WCAG aria-hidden-focus).
        map.getCanvas().setAttribute("tabindex", "-1");
        map.on("load", function () {
          // The canvas is a visual layer only; the route table is the operable
          // equivalent, so keep the canvas out of the keyboard tab order.
          map.getCanvas().setAttribute("tabindex", "-1");
          fetch(geoUrl).then(function (r) { return r.json(); }).then(function (gj) {
            map.addSource("geo", { type: "geojson", data: gj });
            map.addLayer({
              id: "routes", type: "line", source: "geo",
              filter: ["==", ["get", "kind"], "route"],
              layout: { "line-join": "round", "line-cap": "round" },
              paint: { "line-color": ["get", "color"], "line-width": 3.5 }
            });
            // Highlight layer above the base routes, empty until brushing sets its
            // filter to one route id, thickening just that line.
            map.addLayer({
              id: "routes-hi", type: "line", source: "geo",
              filter: ["==", ["get", "route_id"], NONE],
              layout: { "line-join": "round", "line-cap": "round" },
              paint: { "line-color": ["get", "color"], "line-width": 7, "line-opacity": 1 }
            });
            map.addLayer({
              id: "stops", type: "circle", source: "geo",
              filter: ["==", ["get", "kind"], "stop"],
              paint: {
                "circle-radius": 3.5, "circle-color": "#1c1c1c",
                "circle-stroke-width": 1.5, "circle-stroke-color": "#ffffff"
              }
            });
            var b = new maplibregl.LngLatBounds();
            (gj.features || []).forEach(function (f) {
              var g = f.geometry; if (!g) return;
              if (g.type === "Point") { b.extend(g.coordinates); }
              else if (g.type === "LineString") { g.coordinates.forEach(function (c) { b.extend(c); }); }
            });
            if (!b.isEmpty()) { map.fitBounds(b, { padding: 36, animate: !reduce, duration: reduce ? 0 : 600 }); }

            mapReady = true;
            if (current !== null) {
              map.setFilter("routes-hi", ["==", ["get", "route_id"], current]);
            }

            // Hovering a line brushes it and its row; leaving falls back to the
            // pinned selection (or clears).
            map.on("mousemove", "routes", function (e) {
              map.getCanvas().style.cursor = "pointer";
              highlight(e.features[0].properties.route_id);
            });
            map.on("mouseleave", "routes", function () {
              map.getCanvas().style.cursor = "";
              highlight(pinned);
            });

            function popup(e) {
              var p = e.features[0].properties;
              var div = document.createElement("div");
              var strong = document.createElement("strong");
              strong.textContent = p.kind === "route"
                ? (p.label + (p.long && p.long !== p.label ? ": " + p.long : ""))
                : p.name;
              div.appendChild(strong);
              if (p.kind === "route") {
                var sub = document.createElement("div");
                sub.textContent = p.type_label + ", " + p.color_name + " line";
                div.appendChild(sub);
              }
              new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(div).addTo(map);
            }
            map.on("click", "routes", popup);
            map.on("click", "stops", popup);
            map.on("mouseenter", "stops", function () { map.getCanvas().style.cursor = "pointer"; });
            map.on("mouseleave", "stops", function () { map.getCanvas().style.cursor = ""; });
          }).catch(function () {});
        });
      })();"""


def _agency_map_script(geo_url: str) -> str:
    """The MapLibre bootstrap for an agency map: draw routes + stops, fit to the
    data, and respect prefers-reduced-motion (no animated fit). The map is a
    visual enhancement marked aria-hidden; the route table below it is the
    operable, screen-reader equivalent, so the canvas is taken out of the tab
    order and no zoom/pan controls are added. Hovering (or tapping) a line brushes
    its row in the table and the reverse; clicking names the route or stop. Loads
    only on pages that have geometry."""
    js = _AGENCY_MAP_JS.replace("__GEO_URL_JSON__", json.dumps(geo_url))
    return (
        f'    <script src="https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.js"></script>\n'
        "    <script>\n" + js + "\n    </script>"
    )


def _geometry_stop_names(geometry_path: Path) -> list[str]:
    """Stop names from a geometry.geojson, in the file's order, or [] if absent.

    The names live only in the geometry artifact (not the per-day JSON), so the
    page's stop list reads them here. A missing or unreadable file is normal for a
    feed without geometry and yields an empty list, not an error."""
    try:
        gj = json.loads(geometry_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    names: list[str] = []
    for feature in gj.get("features", []):
        props = feature.get("properties", {})
        if props.get("kind") == "stop":
            names.append(str(props.get("name", "")))
    return names


def _brush_key_attr(route: dict[str, Any]) -> str:
    """A ``data-route-key`` for rows whose route the map can draw, so the map
    script can brush a row from its line and the reverse. Undrawable routes get
    nothing: they have no line to link to."""
    if not route.get("has_shape"):
        return ""
    return f' data-route-key="{esc(str(route.get("id", "")))}"'


def _route_map_section(
    artifact: dict[str, Any],
    agency_id: str,
    stop_names: list[str] | None = None,
) -> str:
    """The per-agency route + stop map, with its always-present accessible
    equivalent.

    The map (MapLibre) is the enhancement; the conformant primary is the route
    table and stop summary built from the artifact's ``route_map`` block, reached
    by a 'Skip to route and stop data' bypass before the map. A feed with no
    drawable routes and no located stops renders nothing here.
    """
    route_map = artifact.get("route_map")
    if not isinstance(route_map, dict):
        return ""
    routes = route_map.get("routes") or []
    stop_count = int(route_map.get("stop_count") or 0)
    has_shapes = bool(route_map.get("has_shapes"))
    geo_path = route_map.get("path")
    if not routes and stop_count == 0:
        return ""

    agency_name = esc(artifact.get("agency", {}).get("name", agency_id))

    # The accessible route table: route, type, and the line color described in
    # words (never color alone). Scoped headers for screen-reader navigation.
    drawn = [r for r in routes if r.get("has_shape")]
    if routes:
        rows = "".join(
            f"<tr{_brush_key_attr(r)}>"
            f'<th scope="row">'
            f'<span class="route-swatch" style="background:#{esc(str(r.get("color", "4A4A4A")))}" '
            f'aria-hidden="true"></span>{esc(str(r.get("label", r.get("id", ""))))}'
            + (
                f' <span class="route-long">{esc(str(r.get("long")))}</span>'
                if r.get("long") and r.get("long") != r.get("label")
                else ""
            )
            + "</th>"
            f"<td>{esc(str(r.get('type_label', 'Transit line')))}</td>"
            f"<td>{esc(str(r.get('color_name', '')))}"
            + (
                ""
                if r.get("has_shape")
                else ' <span class="route-noline">(no shape in feed)</span>'
            )
            + "</td></tr>"
            for r in routes
        )
        route_table = (
            '<table class="route-table">'
            f"<caption>Routes in {agency_name}'s feed</caption>"
            '<thead><tr><th scope="col">Route</th><th scope="col">Type</th>'
            '<th scope="col">Line color</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        route_table = '<p class="page-lede">This feed lists no routes.</p>'

    # Stop summary: the count, and the stop names as a collapsible list so the map
    # points have a text equivalent without weighing the page down by default.
    if stop_count:
        names = stop_names or []
        shown = names[:_AGENCY_MAP_STOP_LIST_CAP]
        more = stop_count - len(shown)
        stop_items = "".join(f"<li>{esc(n)}</li>" for n in shown)
        remainder = (
            f'<li class="stop-more">and {more} more (see the full list on the map '
            f'or in the <a href="/{esc(str(geo_path))}">GeoJSON</a>)</li>'
            if more > 0
            else ""
        )
        stop_block = (
            f'<p class="map-stopcount">This feed has <strong>{stop_count}</strong> '
            f"stop{'s' if stop_count != 1 else ''}.</p>"
            + (
                '<details class="stop-list-wrap"><summary>List every stop</summary>'
                f'<ul class="stop-list">{stop_items}{remainder}</ul></details>'
                if stop_items
                else ""
            )
        )
    else:
        stop_block = '<p class="page-lede">This feed has no located stops.</p>'

    # Legend: a swatch plus the route label and color word, so the legend reads
    # without relying on color. Only drawn routes carry a line on the map.
    legend = ""
    if drawn:
        items = "".join(
            f'<li><span class="map-dot" style="background:#{esc(str(r.get("color", "4A4A4A")))}"></span>'
            f"{esc(str(r.get('label', r.get('id', ''))))} "
            f'<span class="legend-note">({esc(str(r.get("color_name", "")))})</span></li>'
            for r in drawn
        )
        legend = f'<ul class="map-legend" aria-label="Route colors">{items}</ul>'

    if has_shapes:
        intro = (
            "Each route is drawn once, using the longest shape its trips follow; "
            "stops are the dots."
        )
    elif stop_count:
        intro = "This feed has no route shapes, so the map shows its stops only."
    else:
        intro = ""

    map_html = ""
    script = ""
    if geo_path:
        map_html = (
            '<a class="skip-link-inline" href="#route-data">Skip to route and stop data</a>'
            '<div id="route-map" class="agency-map" aria-hidden="true"></div>'
            '<p class="fineprint">Basemap: OpenFreeMap, &copy; OpenStreetMap contributors. '
            "Routes and stops: this "
            "agency's GTFS feed.</p>"
        )
        script = _agency_map_script(f"/{geo_path}")

    return (
        '<section aria-labelledby="map-h" class="route-map-section">'
        '<h2 class="section-title" id="map-h">Routes and stops</h2>'
        + (f'<p class="page-lede">{intro}</p>' if intro else "")
        + map_html
        + legend
        + '<div id="route-data" tabindex="-1">'
        + route_table
        + stop_block
        + "</div></section>"
        + script
    )


def _load_effort_bands() -> dict[str, str]:
    """Code -> empirical effort band, from the corpus calibration file.

    Only codes that clear the sample floor get an entry (band_text returns None
    below it). A missing or unreadable file yields an empty mapping, which is
    the gate that keeps calibration purely additive: no file, no bands, output
    unchanged (so golden fixtures without one stay byte-identical)."""
    from .effort_calibration import band_text

    path = _repo_root() / "data" / "effort-calibration.json"
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, ValueError, OSError):
        return {}
    codes = data.get("codes", {}) if isinstance(data, dict) else {}
    bands: dict[str, str] = {}
    for code, stats in sorted(codes.items()):
        if isinstance(stats, dict) and (text := band_text(stats)):
            bands[str(code)] = text
    return bands


def _effort_band_html(code: str, effort_bands: dict[str, str] | None) -> str:
    """Empirical effort band for a notice code, or '' when none applies.

    Additive by design: the hand-authored hint always renders first, and this
    appends the observed runs-to-clear band only when the corpus has enough
    closed episodes for this code (effort_calibration.band_text) and the
    calibration file exists. Absent file -> empty mapping -> no change, so
    goldens rendered without calibration stay byte-identical."""
    band = (effort_bands or {}).get(str(code))
    return f'<p class="effort-band">{esc(band)}</p>' if band else ""


def _render_agency(
    artifact: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
    prev_artifact: dict[str, Any] | None = None,
    dir_record: dict[str, Any] | None = None,
    liveness: dict[str, Any] | None = None,
    stop_names: list[str] | None = None,
    has_fixlog: bool = False,
    now: dt.datetime | None = None,
    effort_bands: dict[str, str] | None = None,
) -> str:
    name = artifact["agency"]["id"], artifact["agency"]["name"]
    agency_id, agency_name = name
    overall = artifact["overall"]
    canonical = f"{BASE_URL}/agency/{agency_id}/"
    desc = (
        f"{agency_name}'s GTFS feed scores {overall['score']} out of 100 "
        f"(grade {overall['grade']}) for data quality: correctness, freshness, "
        "rider-experience completeness, and realtime. Plain-language fixes included."
    )

    map_section = _route_map_section(artifact, agency_id, stop_names)
    # Insert the map and a closing rule only when there is a map, so a feed without
    # geometry renders byte-for-byte as it did before this feature.
    map_block = f"\n    {map_section}\n    {_route_rule()}" if map_section else ""

    fixes = artifact.get("top_fixes", [])
    if fixes:
        alerts = []
        for i, f in enumerate(fixes):
            sev = str(f.get("severity", "")).upper()
            cls = " sev-warning" if sev == "WARNING" else " sev-info" if sev == "INFO" else ""
            pts = f.get("points")
            worth = (
                f'<span class="aworth">worth about +{round(float(pts))} points</span>'
                if isinstance(pts, (int, float)) and pts >= 1
                else ""
            )
            owner = f.get("owner")
            owner_tag = f'<span class="aowner">{esc(owner)}</span>' if owner else ""
            alerts.append(
                f'<div class="alert"><span class="badge{cls}">Fix {i + 1:02d}</span>'
                f'<div><p class="afix">{esc(f["fix"])}{owner_tag}</p>'
                f'<p class="awhy">{esc(f["what"])} {esc(f["why"])}</p>'
                f'<p class="aeta">⏱ {esc(f["effort"])}{worth}</p>'
                f"{_effort_band_html(str(f.get('code', '')), effort_bands)}</div></div>"
            )
        fixes_html = '<div class="alerts">' + "".join(alerts) + "</div>"
    else:
        fixes_html = (
            '<p class="all-clear">Nothing urgent. This feed passed every check we '
            "translate into fixes.</p>"
        )
    # Who makes these changes: when the feed host identifies the producing tool,
    # name the actual path a fix takes (RESEARCH-ROADMAP R5). Shown with the fix
    # list, and for an archive-served feed even without one, because "publish
    # from a live URL" precedes any single fix.
    fix_tool = detect_tool(artifact.get("feed", {}).get("static_url"))
    if fix_tool and (fixes or fix_tool.kind == "archive"):
        fixes_html += f'<p class="fineprint">{esc(fix_tool.fix_path)}</p>'

    cats_html = ""
    measured_vars = []
    for i, key in enumerate(CATEGORY_ORDER):
        cat = artifact["categories"].get(key, {})
        label = CATEGORY_LABELS[key]
        trk = f"{i + 1:02d}"
        if cat.get("status") != "measured":
            note = cat.get("summary") or "Not part of the grade yet."
            cats_html += (
                f'<div class="platform neutral">'
                f'<span class="trk" aria-hidden="true">{trk}</span>'
                f'<div class="pmain"><div class="ptop">'
                f'<span class="pname">{esc(label)}</span>'
                f'<span class="pscore">Not yet measured</span></div>'
                f'<p class="pstat">{esc(note)}</p></div></div>'
            )
            continue
        score = cat["score"]
        width = max(2, min(100, score))
        band = _grade_band(score)
        # Accessibility gets a visible sub-score inside the Rider experience card
        # (ADR 0006); it is a lens on this category, not a change to the grade.
        substat = _accessibility_substat(cat) + _fares_substat(cat) if key == "completeness" else ""
        cats_html += (
            f'<div class="platform">'
            f'<span class="trk" aria-hidden="true">{trk}</span>'
            f'<div class="pmain"><div class="ptop">'
            f'<span class="pname">{esc(label)}</span>'
            f'<span class="pscore">{score}<span class="outof"> / 100</span></span></div>'
            f'<div class="pbar" role="meter" aria-valuenow="{score}" aria-valuemin="0" '
            f'aria-valuemax="100" aria-label="{esc(label)} score">'
            f'<span style="width:{width}%;background:var(--grade-{band})"></span></div>'
            f'<p class="pstat">{esc(cat["summary"])}</p>{substat}</div></div>'
        )
        measured_vars.append({"@type": "PropertyValue", "name": label, "value": score})

    findings = []
    for key in CATEGORY_ORDER:
        cat = artifact["categories"].get(key, {})
        if cat.get("status") == "measured":
            findings.extend(cat.get("findings", []))
    rank = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    findings.sort(key=lambda f: (rank.get(f.get("severity"), 9), -f.get("count", 0)))
    findings_html = (
        "".join(
            f'<li class="finding"><div class="finding-head">'
            f'<span class="sev sev-{str(f.get("severity", "INFO")).lower()}">{SEVERITY_LABELS.get(f.get("severity"), f.get("severity", "Info"))}</span>'
            f'<span class="count">{f.get("count", 0)} {"instance" if f.get("count", 0) == 1 else "instances"}</span></div>'
            f'<p class="what">{esc(f.get("what", ""))}</p><p class="why">{esc(f.get("why", ""))}</p>'
            f'<p class="how"><strong>Fix:</strong> {esc(f.get("fix", ""))} <em>({esc(f.get("effort", ""))})</em></p>'
            f"{_effort_band_html(str(f.get('code', '')), effort_bands)}"
            f'<p class="code">Validator rule: {esc(f.get("code", ""))}{_fix_guide_link(str(f.get("code", "")))}{_rule_ref_link(str(f.get("code", "")))}</p></li>'
            for f in findings
        )
        or '<li class="finding"><p class="what">No findings.</p></li>'
    )

    op_note = artifact.get("agency", {}).get("operating_note")
    op_html = (
        f'<p class="operating-note"><span aria-hidden="true">&#10003;</span> {esc(op_note)}</p>'
        if op_note
        else ""
    )
    _outreach_block = _outreach_section(artifact, canonical)
    _vendor_block = _vendor_section(artifact, canonical)
    _embed_block = _embed_section(agency_id, agency_name)
    # The copy script is emitted once if any copyable block (outreach, vendor,
    # embed) is present, so multiple buttons never double-bind.
    _copy_script = _COPY_SCRIPT if (_outreach_block or _vendor_block or _embed_block) else ""
    crumb = _breadcrumb([("Home", "/"), ("All agencies", "/agencies/"), (agency_name, None)])
    body = f"""    {crumb}
    <a class="backlink" href="/agencies/">&larr; All agencies</a>
    <p class="brief-link"><a href="/agency/{esc(agency_id)}/brief/">Prep for a call: printable one-page brief</a>
      · <a href="/agency/{esc(agency_id)}/board/">For your board packet: printable one-pager</a>
      {f'· <a href="/agency/{esc(agency_id)}/fixes/">Fix log: every issue this feed has cleared</a>' if has_fixlog else ""}
      · <a href="/compare/?a={esc(agency_id)}">Compare with another agency</a>
      · <a href="/subscribe.html">Watch this feed: get an email before it expires</a></p>
    {_board_hero(agency_name, agency_id, artifact, history or [], dir_record)}
    {op_html}
    {_anomaly_note(history)}
    <p class="disclaimer">A data-quality and completeness lens to help an agency improve its
      <abbr title="General Transit Feed Specification">GTFS</abbr> feed. Not an official compliance
      determination from any transit program.
      <a href="/how-to-read/">New to this? How to read your scorecard.</a>
      <a href="/app/#/agency/{esc(agency_id)}">Interactive view of this scorecard.</a>
      Rubric v{esc(artifact.get("rubric_version", "—"))}, validator {esc(artifact.get("validator_version", "—"))}.</p>
    {_liveness_note(liveness, now)}
    {_route_rule()}
    <section aria-labelledby="fixes-h">
      <h2 class="section-title" id="fixes-h">Top things to fix</h2>
      {fixes_html}
    </section>
    {_vendor_block}
    {_outreach_block}
    {_route_rule()}
    <section aria-labelledby="cats-h">
      <h2 class="section-title" id="cats-h">Score by category</h2>
      <div class="platforms">{cats_html}</div>
    </section>
    {_route_rule()}{map_block}
    {_trend_section(history or [])}
    {_feeddiff_section(prev_artifact, artifact, agency_id)}
    {_history_section(history)}
    {_route_rule()}
    <section aria-labelledby="findings-h">
      <h2 class="section-title" id="findings-h">Everything we checked</h2>
      <ul class="findings">{findings_html}</ul>
    </section>
    {_recommendations_section(artifact)}
    {_autofix_section(artifact)}
    {_route_rule()}
    {_ntd_section(artifact)}
    {_canada_equity_section(artifact)}
    {_route_rule()}
    {_conformance_section(artifact, agency_id, agency_name)}
    {_routability_section(artifact)}
    {_otp_section(artifact)}
    {_rt_health_section(agency_id)}
    {_rt_accuracy_section(artifact)}
    {_google_gate_line(artifact, now)}
    {_route_rule()}
    {_standards_section(artifact, (dir_record or {}).get("state", ""))}
    {_route_rule()}
    {_embed_block}
    {_copy_script}"""

    jsonld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"{agency_name} GTFS data quality report",
        "description": desc,
        "url": canonical,
        "includedInDataCatalog": {"@type": "DataCatalog", "url": BASE_URL},
        "creator": {"@type": "Organization", "name": "GTFS Scorecard", "url": BASE_URL},
        "about": {"@type": "Organization", "name": agency_name},
        "variableMeasured": measured_vars,
        "dateModified": artifact["snapshot_date"],
        "distribution": {
            "@type": "DataDownload",
            "encodingFormat": "application/json",
            "contentUrl": f"{BASE_URL}/data/artifacts/{agency_id}/latest.json",
        },
        "keywords": ["GTFS", "transit data quality", "GTFS feed", agency_name],
    }
    title = f"{agency_name} GTFS data quality: grade {overall['grade']} — GTFS Scorecard"
    atom = (
        f'<link rel="alternate" type="application/atom+xml" '
        f'title="{esc(agency_name)} feed quality changes" href="{canonical}feed.xml">'
    )
    # The map stylesheet loads only on pages that actually draw a map.
    if map_section:
        atom += (
            f'\n  <link rel="stylesheet" '
            f'href="https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.css">'
        )
    return _page(
        title=title,
        description=desc,
        canonical=canonical,
        body=body,
        jsonld=jsonld,
        head_extra=atom,
    )


def _brief_trend_line(history: list[dict[str, Any]] | None) -> str:
    """One plain-language sentence on the score's direction since the last check,
    reusing the same delta logic the trend section uses. Neutral on the first
    check."""
    hist = history or []
    if len(hist) < 2:
        return "First check for this agency, so there is no trend yet."
    prev, cur = hist[-2], hist[-1]
    delta = round(cur["score"] - prev["score"], 1)
    if delta > 0:
        return f"Up {delta} points since {prev['date']} ({prev['grade']} to {cur['grade']})."
    if delta < 0:
        return f"Down {abs(delta)} points since {prev['date']} ({prev['grade']} to {cur['grade']})."
    return f"Unchanged since {prev['date']}."


def _brief_changed_section(
    history: list[dict[str, Any]] | None, cleared: list[tuple[str, str]]
) -> str:
    """The 'what changed since the last check' block for the brief: per-category
    deltas plus any findings that cleared. Reuses CATEGORY_ORDER/LABELS and the
    cleared-findings helper so it stays in step with the full page. Empty content
    is handled by the caller."""
    hist = history or []
    rows = ""
    if len(hist) >= 2:
        prev, cur = hist[-2], hist[-1]
        items = []
        for key in CATEGORY_ORDER:
            a = (prev.get("categories") or {}).get(key)
            b = (cur.get("categories") or {}).get(key)
            if a is None or b is None:
                continue
            d = round(b - a, 1)
            text = f"up {d}" if d > 0 else f"down {abs(d)}" if d < 0 else "no change"
            items.append(
                f'<li><span class="brief-cat">{esc(CATEGORY_LABELS[key])}</span> {text}</li>'
            )
        if items:
            rows = f'<ul class="brief-deltas">{"".join(items)}</ul>'
    cleared_html = ""
    if cleared:
        lis = "".join(f"<li>{esc(what)} ({esc(code)})</li>" for code, what in cleared)
        noun = "finding" if len(cleared) == 1 else "findings"
        cleared_html = (
            f'<p class="brief-sub">Fixed since the last check ({len(cleared)} {noun}):</p>'
            f'<ul class="brief-cleared">{lis}</ul>'
        )
    if not rows and not cleared_html:
        rows = "<p>No category changes since the last check.</p>"
    return rows + cleared_html


def _render_brief(
    artifact: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
    prev_artifact: dict[str, Any] | None = None,
    dir_record: dict[str, Any] | None = None,
    liveness: dict[str, Any] | None = None,
    program_ids: set[str] | None = None,
    effort_bands: dict[str, str] | None = None,
) -> str:
    """A calm, print-clean one-page brief for a program liaison to have open or
    printed during an agency check-in. Renders only precomputed artifact fields:
    the grade and trend, what changed since the last check, the top three fixes,
    NTD readiness and ID alignment, the state guideline the score answers to,
    the ready-to-send outreach note when the feed has lapsed, and the key facts
    about the feed. ``program_ids`` is the set of published rollup slugs, so the
    portfolio backlink renders only when the state's rollup page exists.
    Designed to fit one page and to print black-on-white."""
    agency_id = artifact["agency"]["id"]
    agency_name = artifact["agency"]["name"]
    overall = artifact["overall"]
    canonical = f"{BASE_URL}/agency/{agency_id}/brief/"

    # Top three fixes, imperative, with the effort hint, straight from the artifact.
    fixes = artifact.get("top_fixes", [])[:3]
    if fixes:
        fix_items = "".join(
            f'<li class="brief-fix"><p class="brief-fix-do">{esc(f.get("fix", ""))}</p>'
            f'<p class="brief-fix-why">{esc(f.get("what", ""))} {esc(f.get("why", ""))}</p>'
            f'<p class="brief-fix-eta">Effort: {esc(f.get("effort", ""))}</p>'
            f"{_effort_band_html(str(f.get('code', '')), effort_bands)}</li>"
            for f in fixes
        )
        fixes_html = f'<ol class="brief-fixes">{fix_items}</ol>'
    else:
        fixes_html = "<p>Nothing urgent. This feed passed every check we translate into a fix.</p>"

    # NTD readiness verdict and pillars, precomputed at score time.
    readiness = artifact.get("ntd_readiness") or {}
    ntd_status = str(readiness.get("status", "unknown"))
    ntd_label = _NTD_LABELS.get(ntd_status, ntd_status)
    pillar_rows = "".join(
        f"<dt>{esc(_NTD_PILLAR_NAMES.get(p.get('key', ''), p.get('key', '')))} "
        f'<span class="ntd-status ntd-{esc(str(p.get("status", "")))}">'
        f"{esc(_NTD_LABELS.get(str(p.get('status', '')), str(p.get('status', ''))))}</span></dt>"
        f"<dd>{esc(str(p.get('detail', '')))}</dd>"
        for p in readiness.get("pillars", [])
    )
    ntd_html = ""
    if readiness:
        ntd_html = (
            f'<p class="brief-ntd-summary">{esc(str(readiness.get("summary", "")))}</p>'
            f'<dl class="brief-ntd">{pillar_rows}</dl>'
        )

    # agency_id vs NTD ID alignment line, re-worded at render time so old
    # artifacts never resurface pre-final-rule prescriptive copy.
    align = _current_alignment(artifact) or {}
    align_html = ""
    if align:
        a_status = str(align.get("status", "unknown"))
        a_label = _NTD_ALIGN_LABELS.get(a_status, a_status)
        body = esc(str(align.get("detail", "")))
        if align.get("fix"):
            body += f" {esc(str(align.get('fix')))}"
        align_html = (
            f'<p class="brief-align"><strong>agency_id and NTD ID:</strong> '
            f"{esc(a_label)}. {body}</p>"
        )

    # Key facts: feed URL, last checked, days to expiry, feed version, contact/url
    # when the artifact carries them.
    fresh = artifact.get("categories", {}).get("freshness", {}).get("details", {})
    days = fresh.get("days_until_expiry")
    if isinstance(days, (int, float)) and not isinstance(days, bool):
        days = int(days)
        expiry = "Feed has expired." if days <= 0 else f"{days} days of service data remain."
        if fresh.get("last_service_date"):
            expiry += f" Last service date {esc(str(fresh['last_service_date']))}."
    else:
        expiry = "Expiry date not stated in the feed."
    feed = artifact.get("feed", {})
    facts = [
        f"<dt>Feed URL</dt><dd>{esc(str(feed.get('static_url', '')))}</dd>",
        f"<dt>Last checked</dt><dd>{esc(str(artifact.get('snapshot_date', '')))}</dd>",
        f"<dt>Service window</dt><dd>{expiry}</dd>",
    ]
    if fresh.get("feed_version"):
        facts.append(f"<dt>Feed version</dt><dd>{esc(str(fresh['feed_version']))}</dd>")
    comp = artifact.get("categories", {}).get("completeness", {}).get("details", {})
    contact = comp.get("agency_url") or comp.get("agency_contact")
    if contact:
        facts.append(f"<dt>Agency contact</dt><dd>{esc(str(contact))}</dd>")
    where = (dir_record or {}).get("state")
    if where:
        facts.append(f"<dt>State</dt><dd>{esc(str(where))}</dd>")

    # Portfolio backlink: only when the state's rollup page is actually
    # published, so the brief never links a 404.
    portfolio_html = ""
    if where:
        slug = str(where).lower().replace(" ", "-")
        if program_ids and slug in program_ids:
            portfolio_html = (
                f'<p class="brief-portfolio no-print">Part of the '
                f'<a href="/program/{esc(slug)}/">{esc(str(where))} portfolio</a>: '
                "see where this agency sits among the state's feeds before the call.</p>"
            )

    # The state guideline or program the score answers to, one line, so the
    # liaison can cite the right authority without leaving the brief.
    standards_html = ""
    state_std = STATE_STANDARDS.get(str(where or ""))
    if state_std:
        if state_std.get("kind") == "guideline":
            std_lead = f"The published guideline in {esc(str(where))} is "
        else:
            std_lead = "The state transit-data program is "
        standards_html = (
            '<section aria-labelledby="brief-std-h">'
            '<h2 id="brief-std-h">The bar this score answers to</h2>'
            f'<p class="brief-standards">{std_lead}'
            f'<a href="{esc(state_std["url"])}">{esc(state_std["name"])}</a>. '
            f"{esc(state_std['note'])}</p></section>"
        )

    # The ready-to-send outreach note, on the brief itself, so an expired feed's
    # highest-urgency artifact is in hand mid-call rather than a page away. A
    # blockquote prints cleanly; the full page keeps the copy button.
    note = _outreach_note(artifact, f"{BASE_URL}/agency/{agency_id}/")
    outreach_html = (
        (
            '<section aria-labelledby="brief-note-h">'
            '<h2 id="brief-note-h">Ready to send to the agency</h2>'
            f'<blockquote class="brief-outreach">{esc(note)}</blockquote>'
            '<p class="no-print"><a href="/agency/'
            f'{esc(agency_id)}/#send-note">Copy this note from the full scorecard.</a></p>'
            "</section>"
        )
        if note
        else ""
    )

    cleared = _cleared_findings(prev_artifact, artifact)
    body = f"""    <div class="brief">
    <p class="brief-nav no-print"><a href="/agency/{esc(agency_id)}/">&larr; Back to the full scorecard</a></p>
    <header class="brief-head">
      <p class="brief-kicker">Call-prep brief &middot; checked {esc(str(artifact.get("snapshot_date", "")))}</p>
      <h1 class="brief-title">{esc(agency_name)}</h1>
      <p class="brief-grade">Grade {esc(str(overall["grade"]))} &middot; {esc(str(overall["score"]))} / 100</p>
      <p class="brief-trend">{_brief_trend_line(history)}</p>
      <p class="brief-forcall">For this call: lead with the grade and the three fixes below, then
        confirm the feed is current and the NTD details line up. Each fix is framed as a next step,
        not a failure.</p>
    </header>
    <section aria-labelledby="brief-changed-h">
      <h2 id="brief-changed-h">What changed since the last check</h2>
      {_brief_changed_section(history, cleared)}
    </section>
    <section aria-labelledby="brief-fixes-h">
      <h2 id="brief-fixes-h">Top three things to fix</h2>
      {fixes_html}
    </section>
    {outreach_html}
    <section aria-labelledby="brief-ntd-h">
      <h2 id="brief-ntd-h">NTD certification readiness: {esc(ntd_label)}</h2>
      {ntd_html}
      {align_html}
    </section>
    {standards_html}
    <section aria-labelledby="brief-facts-h">
      <h2 id="brief-facts-h">Key facts</h2>
      <dl class="brief-facts">{"".join(facts)}</dl>
    </section>
    {portfolio_html}
    <p class="brief-foot">A data-quality and completeness read to support an agency conversation.
      Not an official compliance determination. Rubric v{esc(str(artifact.get("rubric_version", "—")))},
      validator {esc(str(artifact.get("validator_version", "—")))}.</p>
    </div>"""
    desc = (
        f"Call-prep brief for {agency_name}: grade {overall['grade']}, top fixes, NTD "
        "readiness, and key feed facts on one page."
    )
    title = f"{agency_name} call-prep brief — GTFS Scorecard"
    return _page(title=title, description=desc, canonical=canonical, body=body)


def _render_board_page(
    artifact: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
    prev_artifact: dict[str, Any] | None = None,
    dir_record: dict[str, Any] | None = None,
    effort_bands: dict[str, str] | None = None,
) -> str:
    """A one-page summary written for an agency's board packet (docs/
    RESEARCH-ROADMAP.md E6). The call brief prepares the liaison; this page is
    what the manager hands to board members, so it explains what the grade
    measures, leads with progress, and frames the remaining fixes as the asks.
    Renders only precomputed artifact fields and prints black-on-white."""
    agency_id = artifact["agency"]["id"]
    agency_name = artifact["agency"]["name"]
    overall = artifact["overall"]
    canonical = f"{BASE_URL}/agency/{agency_id}/board/"

    # Progress first. Boards respond to movement, and a cleared finding is the
    # concrete, dated proof that staff time spent on the feed paid off.
    cleared = _cleared_findings(prev_artifact, artifact)
    if cleared:
        wins = "".join(f"<li>{esc(what)}</li>" for _code, what in cleared)
        noun = "issue" if len(cleared) == 1 else "issues"
        progress_html = (
            f"<p>Since the previous check, {len(cleared)} data {noun} "
            f"{'was' if len(cleared) == 1 else 'were'} fixed and verified:</p>"
            f'<ul class="brief-cleared">{wins}</ul>'
        )
    else:
        progress_html = (
            "<p>No newly cleared items this period. The score and trend above "
            "reflect where the feed stands today.</p>"
        )

    # The asks: the same top three fixes the scorecard leads with, framed for a
    # body that approves staff time rather than one that edits the feed.
    fixes = artifact.get("top_fixes", [])[:3]
    if fixes:
        ask_items = "".join(
            f'<li class="brief-fix"><p class="brief-fix-do">{esc(f.get("fix", ""))}</p>'
            f'<p class="brief-fix-why">{esc(f.get("what", ""))} {esc(f.get("why", ""))}</p>'
            f'<p class="brief-fix-eta">Estimated effort: {esc(f.get("effort", ""))}</p>'
            f"{_effort_band_html(str(f.get('code', '')), effort_bands)}</li>"
            for f in fixes
        )
        asks_html = (
            "<p>Three improvements, in priority order, each sized so the board "
            "can see what it is approving:</p>"
            f'<ol class="brief-fixes">{ask_items}</ol>'
        )
    else:
        asks_html = (
            "<p>None at this time. The feed passes every check the scorecard "
            "translates into a fix; the ask is continued upkeep.</p>"
        )

    # Standing among peers, when the directory carries percentiles. The board
    # version names the comparison plainly instead of using the chip styling.
    standing_html = ""
    if dir_record and dir_record.get("national_percentile") is not None:
        nat = dir_record["national_percentile"]
        peer = dir_record.get("peer_percentile")
        tier_key = dir_record.get("size_tier")
        tier = TIER_LABELS.get(str(tier_key), str(tier_key))
        peer_part = (
            f", and ahead of {peer}% of {esc(tier)} agencies nationwide"
            if peer is not None and tier_key not in (None, "unknown")
            else ""
        )
        standing_html = (
            '<section aria-labelledby="board-standing-h">'
            '<h2 id="board-standing-h">Where this agency stands</h2>'
            f"<p>Ahead of {nat}% of all tracked agencies{peer_part}.</p>"
            "</section>"
        )

    who_makes = ""
    tool = detect_tool(artifact.get("feed", {}).get("static_url"))
    if tool and fixes:
        who_makes = f'<p class="brief-fix-why">{esc(tool.fix_path)}</p>'

    body = f"""    <div class="brief">
    <p class="brief-nav no-print"><a href="/agency/{esc(agency_id)}/">&larr; Back to the full scorecard</a></p>
    <header class="brief-head">
      <p class="brief-kicker">Board packet &middot; transit data quality &middot; checked {esc(str(artifact.get("snapshot_date", "")))}</p>
      <h1 class="brief-title">{esc(agency_name)}</h1>
      <p class="brief-grade">Grade {esc(str(overall["grade"]))} &middot; {esc(str(overall["score"]))} / 100</p>
      <p class="brief-trend">{_brief_trend_line(history)}</p>
    </header>
    <section aria-labelledby="board-what-h">
      <h2 id="board-what-h">What this grade measures</h2>
      <p>The quality of the schedule data this agency publishes for trip-planning
      apps: whether riders using Google Maps, Apple Maps, or Transit see current,
      correct, and complete information. It measures the data feed, not service
      quality or operations.</p>
    </section>
    <section aria-labelledby="board-progress-h">
      <h2 id="board-progress-h">Progress this period</h2>
      {progress_html}
    </section>
    <section aria-labelledby="board-asks-h">
      <h2 id="board-asks-h">What needs attention next</h2>
      {asks_html}
      {who_makes}
    </section>
    {standing_html}
    <p class="brief-foot">Produced by the GTFS Scorecard, an open-source data quality
      tool. A data-quality read to support the board conversation, not an official
      compliance determination. Live scorecard: {esc(f"{BASE_URL}/agency/{agency_id}/")}.
      Rubric v{esc(str(artifact.get("rubric_version", "—")))},
      validator {esc(str(artifact.get("validator_version", "—")))}.</p>
    </div>"""
    desc = (
        f"Board-packet one-pager for {agency_name}: grade {overall['grade']}, progress "
        "this period, and the next asks, on one printable page."
    )
    title = f"{agency_name} board one-pager — GTFS Scorecard"
    return _page(title=title, description=desc, canonical=canonical, body=body)


def _receipt_anchor(receipt: dict[str, str]) -> str:
    """A stable fragment id for one receipt, so its link survives re-renders."""
    return f"r-{receipt.get('cleared', '')}-{receipt.get('code', '')}"


def _render_fixlog_page(artifact: dict[str, Any], receipts: list[dict[str, str]]) -> str:
    """The durable fix log (/agency/<id>/fixes/): every finding this feed has
    cleared, dated, newest first, each entry with its own link. The agency page's
    "resolved since last check" line is gone the next day; this is the citable
    record a manager can put in a board packet or an NTD narrative (docs/
    expansion-ideation-2026-07.md, fix verification as a product)."""
    agency_id = artifact["agency"]["id"]
    agency_name = artifact["agency"]["name"]
    canonical = f"{BASE_URL}/agency/{agency_id}/fixes/"

    items = []
    for r in sorted(
        receipts, key=lambda r: (r.get("cleared", ""), r.get("code", "")), reverse=True
    ):
        code = r.get("code", "")
        anchor = _receipt_anchor(r)
        guide = (
            f' <a href="/fix/{esc(code)}/">What this finding means</a>.'
            if code in FIX_CODES_WITH_PAGES
            else ""
        )
        items.append(
            f'<li class="cleared-row" id="{esc(anchor)}">'
            f'<span class="cleared-mark" aria-hidden="true">&#10003;</span> '
            f'{esc(r.get("what", ""))} <span class="code">({esc(code)})</span> '
            f"Reported through {esc(r.get('last_seen', ''))}; the {esc(r.get('cleared', ''))} "
            f"check verified it gone.{guide} "
            f'<a href="#{esc(anchor)}" aria-label="Link to this fix record">Link</a></li>'
        )

    body = f"""    <p class="brief-nav"><a href="/agency/{esc(agency_id)}/">&larr; Back to the full scorecard</a></p>
    <header class="page-head">
      <h1 class="page-title">Fix log: {esc(agency_name)}</h1>
      <p class="page-lede">A dated record of every data issue this feed has cleared since
      tracking began. Each entry keeps its own link, so a specific fix can be cited in a
      board packet, a grant report, or an NTD narrative.</p>
    </header>
    <section aria-labelledby="fixlog-h">
      <h2 class="section-title" id="fixlog-h">{len(receipts)} verified {"fix" if len(receipts) == 1 else "fixes"}</h2>
      <ul class="cleared-list">{"".join(items)}</ul>
      <p class="fineprint">Verified means the daily check stopped reporting the finding. A
      finding that returns and clears again appears as a separate entry.</p>
    </section>"""
    desc = (
        f"Dated, linkable record of {len(receipts)} data-quality "
        f"{'fix' if len(receipts) == 1 else 'fixes'} verified on {agency_name}'s GTFS feed."
    )
    title = f"{agency_name} fix log — GTFS Scorecard"
    return _page(title=title, description=desc, canonical=canonical, body=body)


# Per-category mapping to the standards a feed answers to, including the
# de-facto Google Transit gate (docs/crosswalk.md). Shown next to this agency's
# own category score so a reader sees where it stands against each, framed as a
# lens, never as a pass/fail compliance verdict.
_STANDARDS_MAP = {
    "correctness": "GTFS Schedule best practices, checked by the MobilityData "
    "validator. MobilityData grading: stop locations, route names and colors. "
    "Google Transit: a feed must pass validation to stay in Maps.",
    "freshness": "The FTA National Transit Database expectation of a valid, current "
    "feed. Google Transit: an expired calendar drops the agency from Maps.",
    "completeness": "GTFS Best Practices for rider-facing fields. MobilityData "
    "grading: stop names and headsigns.",
    "realtime": "GTFS-Realtime best practices: a stable URL, high uptime, and frequent updates.",
}

# A state's own GTFS guideline or program, shown to agencies in that state.
# `kind` keeps the framing honest: "guideline" is a published quality rubric the
# score maps to (California is the only one); "program" is a state transit-data
# program shown as a support resource, not a rubric. Adding a state is one block.
STATE_STANDARDS: dict[str, dict[str, str]] = {
    "California": {
        "name": "California Transit Data Guidelines",
        "url": "https://dot.ca.gov/cal-itp/california-transit-data-guidelines",
        "kind": "guideline",
        "note": "Caltrans' published quality guidelines and compliance checklist; "
        "this rubric is anchored to them.",
    },
    "Colorado": {
        "name": "CDOT Digital Transit Mobility",
        "url": "https://www.codot.gov/programs/innovativemobility/mobility-technology/digital-transit-mobility",
        "kind": "program",
        "note": "Colorado's program coordinating GTFS data across transit providers.",
    },
    "Michigan": {
        "name": "Michigan Public Transit Open Data Program",
        "url": "https://miruralmobility.org/",
        "kind": "program",
        "note": "MDOT's program helping agencies produce and maintain GTFS and GTFS-Flex.",
    },
    "Minnesota": {
        "name": "MnDOT Transit",
        "url": "https://www.dot.state.mn.us/transit/",
        "kind": "program",
        "note": "Minnesota's statewide transit program and data resources.",
    },
    "Oregon": {
        "name": "Oregon ODOT Public Transportation",
        "url": "https://www.oregon.gov/odot/rptd/pages/index.aspx",
        "kind": "program",
        "note": "ODOT's Public Transportation Division, which supports statewide GTFS.",
    },
    "Washington": {
        "name": "WSDOT Transportation Data",
        "url": "https://wsdot.wa.gov/about/transportation-data",
        "kind": "program",
        "note": "WSDOT builds and publishes GTFS for Washington transit agencies.",
    },
}


def _recommendations_section(artifact: dict[str, Any]) -> str:
    """Beyond-the-grade opportunities (fares, on-demand service, deeper
    accessibility) attached to the artifact at score time. These do not affect
    the grade; empty when there is nothing to suggest."""
    recs = artifact.get("recommendations") or []
    if not recs:
        return ""
    items = []
    for rec in recs:
        what = esc(str(rec.get("what", "")))
        fix = esc(str(rec.get("fix", "")))
        items.append(
            f'<li class="rec"><p class="rec-what">{what}</p>'
            f'<p class="rec-fix"><strong>Consider:</strong> {fix}</p></li>'
        )
    return (
        '<section aria-labelledby="recs-h"><h2 class="section-title" id="recs-h">'
        "Beyond the grade</h2>"
        '<p class="page-lede">Opportunities that do not change your grade today: fare detail, '
        "on-demand service, and deeper accessibility data.</p>"
        f'<ul class="recs">{"".join(items)}</ul></section>'
    )


def _autofix_section(artifact: dict[str, Any]) -> str:
    """The safe mechanical subset of fixes, offered as a corrected feed.

    The autofix engine (autofix.py) makes only changes that have one certain
    edit (surrounding whitespace, shouting stop and route names) and leaves the
    feed otherwise byte-for-byte. This shows what it touched and, when a download
    URL was attached at score time, a button to grab the corrected zip. Empty
    when the artifact carries no autofix block or found nothing to change."""
    autofix = artifact.get("autofix")
    if not autofix or not autofix.get("available"):
        return ""
    rows = []
    for fix in autofix.get("fixes", []):
        label = esc(str(fix.get("label", "")))
        count = fix.get("count", 0)
        noun = "change" if count == 1 else "changes"
        examples = fix.get("examples") or []
        example_html = (
            f'<p class="autofix-example">For example: {esc(str(examples[0]))}</p>'
            if examples
            else ""
        )
        rows.append(
            f'<li class="autofix-item"><p class="autofix-label">{label} '
            f'<span class="count">{count} {noun}</span></p>{example_html}</li>'
        )
    download_url = autofix.get("download_url")
    if download_url:
        action = (
            f'<p class="autofix-action"><a class="download-btn" href="{esc(str(download_url))}" '
            "download>Download corrected feed</a></p>"
        )
    else:
        action = (
            '<p class="autofix-cli">Run it yourself on your own copy of the feed: '
            "<code>scorecard autofix &lt;feed.zip&gt; --out corrected.zip</code></p>"
        )
    return (
        '<section aria-labelledby="autofix-h"><h2 class="section-title" id="autofix-h">'
        "Some fixes we can make for you</h2>"
        '<p class="page-lede">These are the safe mechanical fixes, applied to a copy of your '
        "feed. They change only what is certain and leave everything else untouched. Review the "
        "diff before you publish.</p>"
        f'<ul class="autofix-list">{"".join(rows)}</ul>{action}</section>'
    )


def _anomaly_note(history: list[dict[str, Any]] | None) -> str:
    """A heads-up when the most recent check looks like a transient glitch rather
    than a real change (a one-day cliff or a calendar that jumped backward), so a
    reader doesn't over-react to a vendor export blip. Empty when nothing is off."""
    anomaly = latest_anomaly(history or [])
    if anomaly is None:
        return ""
    return (
        f'<p class="anomaly-note"><strong>Heads-up:</strong> {esc(anomaly.detail)} '
        f"(checked {esc(anomaly.date)}). This can be a brief vendor export glitch; "
        "watch the next update before acting.</p>"
    )


def _google_gate_line(artifact: dict[str, Any], now: dt.datetime | None = None) -> str:
    """The "will riders see me?" line: whether the feed clears the Google/Apple
    Maps bar of at least four weeks of upcoming service, the de-facto gate for
    staying on the map. When the feed also carries validator errors, say so
    here, because errors are the other thing Maps onboarding checks; a low
    warning-driven grade alone does not remove an agency from riders' apps,
    and this line is where that worry gets answered. ``now`` follows
    render_site's frozen instant so the "days of service ahead" prose is
    reproducible (the golden test relies on that); it defaults to real time."""
    gate = google_from_artifact(artifact, (now or dt.datetime.now(dt.UTC)).date())
    label = {"pass": "Clears", "at_risk": "At risk for", "fail": "Below"}.get(
        gate.status, gate.status
    )
    correctness = artifact.get("categories", {}).get("correctness", {})
    errors = sum(
        int(f.get("count", 0) or 0)
        for f in correctness.get("findings", [])
        if str(f.get("severity", "")).upper() == "ERROR"
    )
    if errors:
        plural = "s" if errors != 1 else ""
        errors_note = (
            f" The feed also carries {errors} validator error{plural}, the other thing "
            "Maps checks at onboarding; the findings below name each fix."
        )
    elif gate.status == "pass":
        errors_note = (
            " No validator errors either, so riders keep seeing this agency in their "
            "trip planners; warnings lower the grade here but do not remove a feed "
            "from Maps."
        )
    else:
        errors_note = ""
    return (
        f'<p class="gate-line"><span class="gate-{gate.status}">{label}</span> '
        f"the Google and Apple Maps four-week coverage bar. {esc(gate.detail)}{errors_note}</p>"
    )


_NTD_LABELS = {"ready": "Ready", "at_risk": "Needs attention", "not_ready": "Not ready"}
_NTD_PILLAR_NAMES = {"published": "Published", "valid": "Valid", "current": "Current"}

# NTD ID alignment is a forward-looking compliance flag, not part of the
# readiness status, so it renders below the pillars with its own label. Reuses
# the readiness status classes (text label carries the meaning; color does not).
# Alignment is an optional convenience, not a graded requirement, so a feed that
# is not aligned reads neutrally (the "unknown" class), never as a problem.
_NTD_ALIGN_LABELS = {
    "aligned": "Aligned",
    "mismatch": "Not aligned",
    "missing": "Not aligned",
    "unknown": "Not checked yet",
}
_NTD_ALIGN_CLASSES = {
    "aligned": "ntd-ready",
    "mismatch": "ntd-unknown",
    "missing": "ntd-unknown",
    "unknown": "ntd-unknown",
}


def _current_alignment(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """The NTD ID alignment block, re-worded at render time.

    Artifacts store the alignment verdict's prose at score time, so a feed not
    re-scored since the July 2025 final-rule copy fix can still carry the old
    prescriptive "should be your NTD ID by report year 2026" text. The stored
    inputs (feed_agency_ids, ntd_id) let us recompute the current wording here,
    so every rendered page speaks final-rule language regardless of artifact
    age; the stored block is the fallback when the inputs are absent."""
    align = artifact.get("ntd_id_alignment")
    if not align:
        return None
    ids = align.get("feed_agency_ids")
    if isinstance(ids, list):
        from .ntd import assess_id_alignment

        return assess_id_alignment([str(v) for v in ids], str(align.get("ntd_id") or "")).to_dict()
    return dict(align)


def _ntd_id_alignment_html(artifact: dict[str, Any]) -> str:
    """Render the NTD ID alignment line, when the check ran for this feed.

    Whether the feed's agency_id matches the agency's NTD ID. Aligning the two
    lets a feed join cleanly to its NTD record; the July 2025 final rule did not
    require that feed change (FTA links them on the P-50 form), so this is shown
    as an optional convenience carrying no score. Absent for artifacts that
    predate the check."""
    align = _current_alignment(artifact)
    if not align:
        return ""
    status = str(align.get("status", "unknown"))
    label = _NTD_ALIGN_LABELS.get(status, status)
    cls = _NTD_ALIGN_CLASSES.get(status, "ntd-unknown")
    detail = str(align.get("detail", ""))
    fix = str(align.get("fix", ""))
    body = esc(detail)
    if fix:
        body += f" {esc(fix)}"
    return (
        '<dl class="standards-list">'
        f'<dt>agency_id matches your NTD ID <span class="ntd-status {cls}">'
        f"{esc(label)}</span></dt><dd>{body}</dd></dl>"
    )


_CIMD_TIER_PHRASE = {"high": "higher need", "moderate": "moderate need", "lower": "lower need"}


def _canada_equity_section(artifact: dict[str, Any]) -> str:
    """A within-Canada served-area need reading from the CIMD, for Canadian
    agencies only (ADR 0027).

    The tier maps economic dependency and situational vulnerability in the areas
    a feed serves onto a within-Canada quintile. It is a Canadian measure and is
    not comparable to the US ACS need tier. The CIMD excludes the territories, so
    a feed there (e.g. Yukon) shows a neutral no-coverage note instead.

    A CA agency the overlay has not computed yet (no ``canada_equity`` record:
    the command has not run, or the agency is new) shows nothing, so the "not
    covered" note is reserved for feeds that were actually queried and fell
    outside CIMD coverage."""
    if artifact.get("agency", {}).get("country", "US") != "CA":
        return ""
    ce = artifact.get("canada_equity")
    if not ce:
        return ""  # not computed yet -> show nothing, not a false territories note
    phrase = _CIMD_TIER_PHRASE.get(ce.get("need_tier") or "")
    if phrase:
        body = (
            "In the areas this feed serves, the Canadian Index of Multiple Deprivation reads as "
            f"<strong>{esc(phrase)}</strong>, a within-Canada measure of economic dependency and "
            "situational vulnerability. Current, complete data matters most where need is highest."
        )
    else:
        body = (
            "The Canadian Index of Multiple Deprivation does not cover the territories, so there is "
            "no served-area need reading for this feed. The data-quality grade above still applies."
        )
    return (
        '<section aria-labelledby="cimd-h" class="feed-details">'
        '<h2 class="section-title" id="cimd-h">Who this service reaches</h2>'
        f'<p class="page-lede">{body}</p></section>'
    )


def _ntd_section(artifact: dict[str, Any]) -> str:
    """Map this feed's scores onto the FTA National Transit Database GTFS
    requirement, so an agency facing annual D-10 certification gets a direct
    'is my feed ready?' read. Three pillars (published, valid, current), each
    labelled in text as well as color so the status never relies on color alone.

    US-only: a non-US agency (agency.country != "US") has no FTA NTD, so this
    returns "" and the page shows just the GTFS-quality rubric. See ADR 0026."""
    if artifact.get("agency", {}).get("country", "US") != "US":
        return ""
    readiness = ntd_assess(artifact)
    rows = []
    for pillar in readiness.pillars:
        label = _NTD_LABELS.get(pillar.status, pillar.status)
        name = _NTD_PILLAR_NAMES.get(pillar.key, pillar.key)
        rows.append(
            f'<dt>{name} <span class="ntd-status ntd-{pillar.status}">{esc(label)}</span></dt>'
            f"<dd>{esc(pillar.detail)}</dd>"
        )
    overall = _NTD_LABELS.get(readiness.status, readiness.status)
    # Curator-recorded reporting arrangement (a shared regional feed, an FTA
    # waiver): shown with the verdict so those agencies are never read as
    # flagged for identity or coverage they do not own (R15).
    ntd_note = str(artifact.get("agency", {}).get("ntd_note") or "").strip()
    note_html = (
        f'<p class="operating-note"><span aria-hidden="true">&#9432;</span> {esc(ntd_note)}</p>'
        if ntd_note
        else ""
    )
    return (
        '<section aria-labelledby="ntd-h" class="feed-details">'
        '<h2 class="section-title" id="ntd-h">'
        '<abbr title="National Transit Database">NTD</abbr> certification readiness '
        f'<span class="ntd-status ntd-{readiness.status}">{esc(overall)}</span></h2>'
        f"{note_html}"
        f'<p class="page-lede">{esc(readiness.summary)}</p>'
        f'<dl class="standards-list">{"".join(rows)}</dl>'
        f"{_ntd_id_alignment_html(artifact)}"
        '<p class="plain-summary"><strong>In plain words:</strong> if you report to the federal '
        "transit database, you have to publish a working, up-to-date feed and confirm it once a "
        "year. This box is a heads-up on whether yours looks ready; it is not the official "
        "sign-off.</p>"
        '<p class="fineprint">A readiness signal mapping this feed to the '
        '<a href="https://www.transit.dot.gov/ntd">'
        '<abbr title="Federal Transit Administration">FTA</abbr> National Transit Database</a> GTFS '
        "requirement (Report Year 2023 onward: a public, valid, current feed, certified "
        'annually on the <abbr title="FTA NTD certification form D-10">D-10</abbr>). Aligning '
        "agency_id with your NTD ID lets the feed line up with your NTD record; the "
        '<a href="https://www.federalregister.gov/documents/2025/07/10/2025-12813/'
        'national-transit-database-reporting-changes-and-clarifications-for-report-years-2025-and-2026">'
        "July 2025 final rule</a> links the two on the P-50 form rather than requiring that "
        "feed change. Not an official determination; your certification is the official "
        "check.</p></section>"
    )


def _rt_health_section(agency_id: str) -> str:
    """Longitudinal realtime reliability for an agency, when the monitor has run.

    Uptime and median header lag over the recorded window, so a reader sees how
    dependable the realtime feed has been, not only its score on the last sample.
    Absent (returns empty) for agencies the monitor has not yet observed, so a
    feed without realtime is never shown a hollow reliability box."""
    from .rt_health import load_observations, summarize

    observations = load_observations(agency_id)
    if not observations:
        return ""
    s = summarize(observations)
    span = ""
    if s.first_ts and s.last_ts and s.last_ts > s.first_ts:
        days = max(1, round((s.last_ts - s.first_ts) / 86400))
        span = f" over the last {days} day{'s' if days != 1 else ''}"
    lag = (
        f"{s.median_lag_seconds}s median lag"
        if s.median_lag_seconds is not None
        else "lag not reported by the feed"
    )
    cov = (
        f" Median trip coverage was {s.median_coverage_pct}%."
        if s.median_coverage_pct is not None
        else ""
    )
    return (
        '<section aria-labelledby="rth-h" class="feed-details">'
        '<h2 class="section-title" id="rth-h">Realtime reliability</h2>'
        f'<p class="page-lede">The realtime feed responded on {s.uptime_pct}% of '
        f"{s.observations} checks{span}, with {esc(lag)}.{esc(cov)}</p>"
        '<p class="fineprint">Sampled on a schedule between full scores, so this '
        "tracks uptime and freshness over time rather than at a single moment.</p></section>"
    )


def _rt_accuracy_section(artifact: dict[str, Any]) -> str:
    """Prediction accuracy from the last full realtime sample: how far arrival
    predictions ran from the schedule, and how many vehicle positions sat on or
    near the route. Both are already computed (rt_drift.py) and recorded in the
    realtime category detail, but were not shown; this surfaces them. Returns
    empty when the feed had too few predictions or positions to measure, so it
    never renders a hollow box (about half of measured feeds have this data)."""
    rt = artifact.get("categories", {}).get("realtime", {})
    if rt.get("status") != "measured":
        return ""
    details = rt.get("details") or {}
    drift = details.get("drift") or {}
    on_route = details.get("vehicles_on_route_pct")
    parts: list[str] = []
    median = drift.get("median_seconds")
    on_time = drift.get("on_time_share_pct")
    if median is not None and on_time is not None:
        median = int(median)
        p90 = drift.get("p90_abs_seconds")
        if median == 0:
            timing = "ran right on the schedule"
        else:
            timing = (
                f"ran a median <strong>{abs(median)}s {'late' if median > 0 else 'early'}</strong> "
                "versus the schedule"
            )
        p90_txt = f", and stayed within {int(p90)}s nine times in ten" if p90 is not None else ""
        parts.append(
            f"Arrival predictions {timing}{p90_txt}. They were on time "
            f"(about a minute early to five late) <strong>{esc(on_time)}%</strong> of the time."
        )
    if on_route is not None:
        parts.append(
            f"<strong>{esc(on_route)}%</strong> of reported vehicle positions sat on or near the "
            "published route shape."
        )
    if not parts:
        return ""
    return (
        '<section aria-labelledby="rta-h" class="feed-details">'
        '<h2 class="section-title" id="rta-h">Prediction accuracy</h2>'
        f'<p class="page-lede">{" ".join(parts)}</p>'
        '<p class="fineprint">From the last full realtime sample: how far live arrival predictions '
        "sat from the schedule, and whether vehicle positions fell on the route. These feed the "
        "realtime score; they change no other category.</p></section>"
    )


def _routability_section(artifact: dict[str, Any]) -> str:
    """Router-flavored usability gaps (single-stop trips, orphan stops) when the
    feed has any. Zero-deduction, so this names a concrete "validates but a rider
    can't use it" problem without implying a score change. Absent when clean."""
    routability = artifact.get("routability")
    if not isinstance(routability, dict):
        return ""
    findings = routability.get("findings") or []
    if not findings:
        return ""
    items = "".join(
        f"<li><strong>{esc(f.get('what', ''))}</strong> {esc(f.get('why', ''))} "
        f"<em>{esc(f.get('fix', ''))}</em></li>"
        for f in findings
        if isinstance(f, dict)
    )
    return (
        '<section aria-labelledby="route-h" class="feed-details">'
        '<h2 class="section-title" id="route-h">Can riders use it?</h2>'
        '<p class="page-lede">Checks beyond structural validation: places where the '
        "feed is valid but a rider still could not travel.</p>"
        f'<ul class="findings">{items}</ul>'
        '<p class="fineprint">These do not change the grade. They catch trips with no '
        "rideable leg and stops no trip serves, the kind of gap a trip planner trips over."
        "</p></section>"
    )


def _otp_section(artifact: dict[str, Any]) -> str:
    """Trip-plannability QA from an OpenTripPlanner run, when the artifact
    carries a routing_qa block (docs/OTP_WIRING_PATTERN.md). Feeds never
    sampled carry no block, so their pages render unchanged; this lights up
    the day the OTP job starts publishing results."""
    rq = artifact.get("routing_qa")
    if not isinstance(rq, dict) or rq.get("status") != "measured":
        return ""
    details = rq.get("details") or {}
    total = details.get("total_sampled")
    routable = details.get("routable_trips")
    if not isinstance(total, int) or not isinstance(routable, int) or total <= 0:
        return ""
    notes = str(details.get("notes") or "").strip()
    notes_html = f'<p class="fineprint">{esc(notes)}</p>' if notes else ""
    return (
        '<section aria-labelledby="otp-h" class="feed-details">'
        '<h2 class="section-title" id="otp-h">Can a rider plan a trip?</h2>'
        f'<p class="page-lede">{routable} of {total} sampled origin&ndash;destination '
        "pairs returned an itinerary in "
        '<a href="https://www.opentripplanner.org/">OpenTripPlanner</a>, the same kind '
        "of engine trip-planning apps run on. This samples the published feed; it does "
        "not change the grade.</p>"
        f"{notes_html}"
        "</section>"
    )


_CONFORMANCE_NAMES = {"valid": "Valid", "current": "Current", "accessible": "Accessible"}


def _conformance_section(artifact: dict[str, Any], agency_id: str, agency_name: str) -> str:
    """The conformance trust mark: a pass/not-yet credential over the same checks
    the grade uses. When earned, the seal and a copy-paste embed appear; when not,
    the criteria show what is left, framed as a mark to earn rather than a failure.
    Each criterion is labelled in text, never by color alone."""
    mark = conformance_assess(artifact)
    rows = []
    for crit in mark.criteria:
        name = _CONFORMANCE_NAMES.get(crit.key, crit.key)
        status = "ntd-ready" if crit.met else "ntd-not_ready"
        label = "Met" if crit.met else "Not yet"
        rows.append(
            f'<dt>{name} <span class="ntd-status {status}">{label}</span></dt>'
            f"<dd>{esc(crit.detail)}</dd>"
        )
    head_status = "ntd-ready" if mark.awarded else "ntd-not_ready"
    head_label = "Awarded" if mark.awarded else "Not yet"
    seal = ""
    if mark.awarded:
        mark_svg = f"{BASE_URL}/data/artifacts/{agency_id}/mark.svg"
        page = f"{BASE_URL}/agency/{agency_id}/"
        markdown = f"[![GTFS conformance mark]({mark_svg})]({page})"
        seal = (
            f'<p><img src="/data/artifacts/{esc(agency_id)}/mark.svg" '
            f'alt="GTFS conformance mark for {esc(agency_name)}"></p>'
            '<label class="visually-hidden" for="mark-md">Conformance mark Markdown</label>'
            f'<textarea id="mark-md" class="outreach-text" rows="2" readonly>{esc(markdown)}'
            "</textarea>"
            '<button type="button" class="copy-btn" data-copy="mark-md">Copy Markdown</button>'
        )
    return (
        '<section aria-labelledby="mark-h" class="feed-details">'
        '<h2 class="section-title" id="mark-h">Conformance mark '
        f'<span class="ntd-status {head_status}">{head_label}</span></h2>'
        f'<p class="page-lede">{esc(mark.summary)}</p>'
        f"{seal}"
        f'<dl class="standards-list">{"".join(rows)}</dl>'
        '<p class="plain-summary"><strong>In plain words:</strong> earn this mark when your feed '
        "passes validation, has not expired, and says whether nearly every stop and trip is "
        "wheelchair accessible.</p>"
        '<p class="fineprint">A pass credential for a feed that is valid, current, and states '
        "wheelchair access on nearly every stop and trip. Accessibility here measures what the "
        "feed publishes, not whether a stop is physically usable. "
        '<a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/conformance.md">'
        "How the conformance mark works.</a></p></section>"
    )


def _standards_section(artifact: dict[str, Any], state: str = "") -> str:
    """How this agency's category scores line up with the standards it relates to.

    Universal references (every US agency): the FTA National Transit Database GTFS
    requirement, the MobilityData grading scheme, and the de-facto Google Transit
    gate. If the agency's state has its own published guideline (STATE_STANDARDS),
    it is shown too. A lens, not a compliance determination.

    US-only: the references here (the FTA National Transit Database requirement,
    US state guidelines) do not apply to a non-US agency, so the whole section is
    omitted for one until Tier 2 localizes the standards lens (ADR 0026).
    """
    if artifact.get("agency", {}).get("country", "US") != "US":
        return ""
    cw = "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/crosswalk.md"
    ntd = "https://www.transit.dot.gov/ntd"
    md = "https://github.com/MobilityData/gtfs-grading-scheme"
    rows = []
    for key in CATEGORY_ORDER:
        cat = artifact.get("categories", {}).get(key, {})
        if cat.get("status") == "measured":
            score = f"{int(round(float(cat.get('score', 0))))} / 100"
        else:
            score = "Not yet published"
        rows.append(
            f"<dt>{esc(CATEGORY_LABELS[key])} "
            f'<span class="std-score">{esc(score)}</span></dt>'
            f"<dd>{esc(_STANDARDS_MAP[key])}</dd>"
        )
    state_std = STATE_STANDARDS.get(state)
    state_html = ""
    if state_std:
        if state_std.get("kind") == "guideline":
            lead = f"In {esc(state)}, the published guideline is "
        else:
            lead = "Your state runs a transit-data program that can help: "
        state_html = (
            f'<p class="page-lede">{lead}'
            f'<a href="{esc(state_std["url"])}">{esc(state_std["name"])}</a>. '
            f"{esc(state_std['note'])}"
        )
        if state_std.get("kind") != "guideline":
            state_html += (
                " Your state publishes no quality rubric of its own, so the closest "
                "published bars a program can hold this feed to are the federal and "
                "industry ones below; the score maps to those."
            )
        state_html += "</p>"
    return (
        '<section aria-labelledby="standards-h" class="feed-details">'
        '<h2 class="section-title" id="standards-h">How this agency maps to the standards</h2>'
        '<p class="page-lede">A data-quality lens, not a compliance determination. Each category '
        "shows this feed's score and the standards it relates to: the "
        f'<a href="{ntd}"><abbr title="Federal Transit Administration">FTA</abbr> National Transit '
        "Database</a> GTFS requirement, the "
        f'<a href="{md}">MobilityData grading scheme</a>, and the Google Transit gate. '
        f'Read the full standards crosswalk: <a href="{cw}">standards crosswalk (docs/crosswalk.md)</a>.</p>'
        f"{state_html}"
        f'<dl class="standards-list">{"".join(rows)}</dl></section>'
    )


def _expired_ago(days: int) -> str:
    """Plain-language age of an expired feed from a negative days-until-expiry."""
    n = -int(days)
    if n < 60:
        return f"{n} days ago"
    if n < 365:
        return f"about {n // 30} months ago"
    years = n // 365
    return f"about {years} year{'s' if years != 1 else ''} ago"


def _index_card(aid: str, a: dict[str, Any], note: str = "") -> str:
    """One agency row for the directory. `note` adds a second meta line (used by
    the expired panel to say how long ago the feed lapsed). A curator's
    operating_note, when present, adds a verified status line below that."""
    last = a["history"][-1]
    extra = f'<p class="meta meta-flag">{esc(note)}</p>' if note else ""
    op_note = a.get("operating_note")
    op = (
        f'<p class="meta op-note"><span aria-hidden="true">&#10003;</span> {esc(op_note)}</p>'
        if op_note
        else ""
    )
    return (
        f'<li class="agency-card"><span class="grade-chip {_grade_class(last["grade"])}">'
        f'{esc(last["grade"])}<span class="visually-hidden"> grade</span></span>'
        f'<div><h3><a href="/agency/{esc(aid)}/">{esc(a["name"])}</a></h3>'
        f'<p class="meta">Overall {last["score"]} out of 100 · '
        f"checked {esc(last['date'])}</p>{extra}{op}</div></li>"
    )


def _render_agency_index(index: dict[str, Any]) -> str:
    canonical = f"{BASE_URL}/agencies/"
    agencies = sorted(index["agencies"].items(), key=lambda kv: kv[1]["name"].lower())

    # Pull expired feeds out of the grade sections so the actionable ones aren't
    # buried in a long alphabetical wall of grade F. Split them: a recently
    # lapsed feed is a one-line re-export the agency can still fix; a feed that
    # has been dead for over a year usually means the URL itself is stale and the
    # canonical endpoint should be re-checked in the Mobility Database.
    lapsed: list[tuple[str, dict[str, Any], int]] = []
    stale: list[tuple[str, dict[str, Any], int]] = []
    graded: list[tuple[str, dict[str, Any]]] = []
    for aid, a in agencies:
        last = a["history"][-1]
        days = last.get("days_until_expiry")
        status = expiry_status(days)
        if status == "lapsed":
            lapsed.append((aid, a, int(days)))
        elif status == "stale":
            stale.append((aid, a, int(days)))
        else:
            graded.append((aid, a))
    # Most recently expired first: the closest to recovery, and the most likely
    # to still be operating.
    lapsed.sort(key=lambda t: t[2], reverse=True)
    stale.sort(key=lambda t: t[2], reverse=True)

    nav = []
    expired_section = ""
    if lapsed or stale:
        nav.append(f'<a href="#expired">Expired ({len(lapsed) + len(stale)})</a>')
        groups = []
        if lapsed:
            rows = "".join(
                _index_card(aid, a, f"Feed expired {_expired_ago(d)} · likely still running")
                for aid, a, d in lapsed
            )
            groups.append(
                '<section aria-labelledby="lapsed-h">'
                '<h3 class="section-sub" id="lapsed-h">Recently lapsed '
                f'<span class="grade-count">{len(lapsed)} '
                f"{'agency' if len(lapsed) == 1 else 'agencies'}</span></h3>"
                '<p class="group-note">Expired within the last year. These agencies are '
                "almost certainly still running. Re-exporting the feed with a calendar that "
                "reaches further out brings them back into trip planners.</p>"
                f'<ul class="agency-list">{rows}</ul></section>'
            )
        if stale:
            rows = "".join(
                _index_card(aid, a, f"Feed expired {_expired_ago(d)} · check the feed URL")
                for aid, a, d in stale
            )
            groups.append(
                '<section aria-labelledby="stale-h">'
                '<h3 class="section-sub" id="stale-h">Expired over a year ago '
                f'<span class="grade-count">{len(stale)} '
                f"{'agency' if len(stale) == 1 else 'agencies'}</span></h3>"
                '<p class="group-note">Expired more than a year ago. For these, the feed URL on '
                "file is still the one listed in the Mobility Database, so the stale data is at "
                "the source: the agency or its vendor stopped refreshing the export. Worth "
                "confirming the agency still runs before reading the grade as a current failure.</p>"
                f'<ul class="agency-list">{rows}</ul></section>'
            )
        expired_section = (
            '<section class="expired-panel" aria-labelledby="expired">'
            '<h2 class="section-title" id="expired">Expired feeds '
            f'<span class="grade-count">{len(lapsed) + len(stale)} '
            f"{'agency' if len(lapsed) + len(stale) == 1 else 'agencies'}</span></h2>"
            '<p class="page-lede">A feed whose calendar has run out is invisible to trip '
            "planners even when the buses keep running. These are pulled out of the grade list "
            "below so the fixable ones are easy to find.</p>"
            f"{''.join(groups)}</section>"
        )

    # Group the remaining (non-expired) agencies by grade: a jump nav, then a
    # section per grade (A first), alphabetical within each.
    by_grade: dict[str, list[tuple[str, dict[str, Any]]]] = {g: [] for g in "ABCDF"}
    for aid, a in graded:
        by_grade.setdefault(str(a["history"][-1]["grade"]), []).append((aid, a))

    sections = []
    for g in "ABCDF":
        members = by_grade.get(g, [])
        if not members:
            continue
        nav.append(f'<a href="#grade-{g}">{g} ({len(members)})</a>')
        rows = "".join(_index_card(aid, a) for aid, a in members)
        sections.append(
            f'<section aria-labelledby="grade-{g}">'
            f'<h2 class="section-title" id="grade-{g}">Grade {g} '
            f'<span class="grade-count">{len(members)} '
            f"{'agency' if len(members) == 1 else 'agencies'}</span></h2>"
            f'<ul class="agency-list">{rows}</ul></section>'
        )

    desc = (
        f"GTFS data quality scorecards for {len(agencies)} transit agencies. Expired feeds are "
        "listed first, split into recently lapsed and long dead, then the rest by grade."
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("All agencies", None)])}
    <h1 class="page-title">All agencies</h1>
    <p class="page-lede">{len(agencies)} transit agencies, each with a
    <abbr title="General Transit Feed Specification">GTFS</abbr> data
    quality grade and the fixes to start with.</p>
    <nav class="grade-jump" aria-label="Other views of the same agencies">Same agencies, other
    views: <a href="/app/">live search and filters</a> · <a href="/map/">on a map</a> ·
    <a href="/routes/">every route</a> · <a href="/compare/">compare two</a></nav>
    <nav class="grade-jump" aria-label="Jump to section">Jump to: {" · ".join(nav)}</nav>
    {expired_section}
    {"".join(sections)}"""
    return _page(
        title="All agencies — GTFS Scorecard",
        description=desc,
        canonical=canonical,
        body=body,
        wide=True,
    )


def _render_rollup(rollup: dict[str, Any]) -> str:
    rid = rollup["rollup"]["id"]
    rname = rollup["rollup"]["name"]
    canonical = f"{BASE_URL}/program/{rid}/"
    desc = (
        f"{rname}: GTFS data quality across {rollup['agency_count']} agencies, "
        f"worst first, with {rollup['needs_attention']} needing attention and the "
        "fixes shared across the group."
    )
    rows_parts = []
    for m in rollup["members"]:
        attn = (
            f' <span class="pill-warn">{esc(m.get("attention_reason") or "needs attention")}</span>'
            if m.get("needs_attention")
            else ""
        )
        rows_parts.append(
            f'<li class="program-row"><span class="grade-chip {_grade_class(m["grade"])}">'
            f'{esc(m["grade"])}<span class="visually-hidden"> grade</span></span>'
            f'<div><h3><a href="/agency/{esc(m["id"])}/">{esc(m["name"])}</a>{attn}</h3>'
            f'<p class="meta">{m["score"]} out of 100 · checked {esc(m["snapshot_date"])}</p>'
            "</div></li>"
        )
    rows = "".join(rows_parts)
    avg = "—" if rollup.get("average_score") is None else f"{rollup['average_score']} out of 100"
    expired_section = _rollup_expired_section(rollup)
    crumb = _breadcrumb([("Home", "/"), ("All agencies", "/agencies/"), (rname, None)])
    body = f"""    {crumb}
    <a class="backlink" href="/agencies/">&larr; All agencies</a>
    <div class="score-hero">
      <div>
        <h1 class="page-title">{esc(rname)}</h1>
        <p class="overall"><strong>{rollup["agency_count"]} agencies</strong> ·
          {avg} average · {rollup["needs_attention"]} need attention</p>
      </div>
    </div>
    {_route_rule()}
    {expired_section}
    <section aria-labelledby="members-h">
      <h2 class="section-title" id="members-h">Agencies, worst first</h2>
      <ul class="program-list">{rows}</ul>
    </section>"""
    return _page(
        title=f"{rname} — GTFS Scorecard", description=desc, canonical=canonical, body=body
    )


def _rollup_member_row(m: dict[str, Any], note: str) -> str:
    """A program-list row for the expired worklist, with a how-long-ago flag."""
    return (
        f'<li class="program-row"><span class="grade-chip {_grade_class(m["grade"])}">'
        f'{esc(m["grade"])}<span class="visually-hidden"> grade</span></span>'
        f'<div><h3><a href="/agency/{esc(m["id"])}/">{esc(m["name"])}</a> '
        f'<span class="pill-warn">{esc(note)}</span></h3>'
        f'<p class="meta">{m["score"]} out of 100 · checked {esc(m["snapshot_date"])}</p>'
        "</div></li>"
    )


def _rollup_expired_section(rollup: dict[str, Any]) -> str:
    """A worklist of this program's expired feeds, split lapsed vs stale.

    This is the call list a liaison reads first: which agencies dropped out of
    trip planners, how long ago, and which kind of fix each one needs.
    """
    by_status: dict[str, list[dict[str, Any]]] = {"lapsed": [], "stale": []}
    for m in rollup["members"]:
        if m.get("expiry_status") in by_status:
            by_status[m["expiry_status"]].append(m)
    if not (by_status["lapsed"] or by_status["stale"]):
        return ""
    for group in by_status.values():
        # Most recently expired first: closest to recovery, most likely still running.
        group.sort(key=lambda m: m.get("days_until_expiry") or 0, reverse=True)

    groups = []
    if by_status["lapsed"]:
        rows = "".join(
            _rollup_member_row(m, f"expired {_expired_ago(m['days_until_expiry'])}")
            for m in by_status["lapsed"]
        )
        groups.append(
            '<h3 class="section-sub" id="rollup-lapsed">Recently lapsed '
            f'<span class="grade-count">{len(by_status["lapsed"])}</span></h3>'
            '<p class="group-note">Expired within the last year. Likely still running; a '
            "re-export with a longer calendar brings each one back into trip planners.</p>"
            f'<ul class="program-list">{rows}</ul>'
        )
    if by_status["stale"]:
        rows = "".join(
            _rollup_member_row(m, f"expired {_expired_ago(m['days_until_expiry'])}")
            for m in by_status["stale"]
        )
        groups.append(
            '<h3 class="section-sub" id="rollup-stale">Expired over a year ago '
            f'<span class="grade-count">{len(by_status["stale"])}</span></h3>'
            '<p class="group-note">Expired more than a year ago. The listed URL is usually still '
            "canonical, so the source stopped refreshing. Confirm the agency still runs before "
            "reading the grade as a current failure.</p>"
            f'<ul class="program-list">{rows}</ul>'
        )
    total = rollup.get("expired", {}).get("total", 0)
    return (
        '<section class="expired-panel" aria-labelledby="rollup-expired-h">'
        '<h2 class="section-title" id="rollup-expired-h">Expired feeds '
        f'<span class="grade-count">{total} of {rollup["agency_count"]}</span></h2>'
        '<p class="page-lede">These feeds have run out and dropped from trip planners. '
        "Start the program's outreach here.</p>"
        f"{''.join(groups)}</section>"
    )


# --- minimal markdown for the fix knowledge base -------------------------------


def _md_link(match: re.Match[str]) -> str:
    label, href = match.group(1), match.group(2)
    # Fix docs cross-reference each other as `other_code.md`; rewrite those to the
    # real on-site path so the links work in the generated site.
    rel = re.fullmatch(r"([a-z0-9_]+)\.md", href)
    if rel:
        href = f"/fix/{rel.group(1)}/"
    # Only allow http(s), site-relative, and anchor hrefs; never javascript:/data:
    # even from a repo-controlled fix doc.
    if not (href.startswith(("http://", "https://", "/", "#"))):
        return label
    return f'<a href="{href}">{label}</a>'


def _md_inline(text: str) -> str:
    text = esc(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _md_link, text)
    return text


def _md_to_html(md: str) -> tuple[str, str]:
    """Very small Markdown subset (headings, lists, paragraphs, inline). Returns
    (html_body, first_h1_text)."""
    out: list[str] = []
    title = ""
    in_list = False
    for line in md.splitlines():
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_md_inline(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("# "):
            title = line[2:].strip()
            out.append(f"<h1>{_md_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f'<h2 class="section-title">{_md_inline(line[3:])}</h2>')
        elif line.strip():
            out.append(f"<p>{_md_inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out), title


def _render_fix(code: str, md: str) -> str:
    canonical = f"{BASE_URL}/fix/{code}/"
    body_html, title_text = _md_to_html(md)
    title_text = title_text or f"Fix: {code}"
    # description: first paragraph after the first heading.
    para = next((re.sub("<[^>]+>", "", p) for p in re.findall(r"<p>(.*?)</p>", body_html)), "")
    desc = (para[:155] or f"How to fix the GTFS validator notice {code}.").strip()
    crumb = _breadcrumb([("Home", "/"), ("All agencies", "/agencies/"), (f"Fix: {code}", None)])
    body = f"""    {crumb}
    <a class="backlink" href="/agencies/">&larr; All agencies</a>
    <article class="feed-details">{body_html}{_fix_rule_reference(code)}</article>"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": title_text,
        "description": desc,
        "url": canonical,
        "about": {"@type": "Thing", "name": f"GTFS validator notice {code}"},
        "publisher": {"@type": "Organization", "name": "GTFS Scorecard", "url": BASE_URL},
    }
    return _page(
        title=f"{title_text} — GTFS Scorecard",
        description=desc,
        canonical=canonical,
        body=body,
        jsonld=jsonld,
    )


def _sitemap(urls: list[str]) -> str:
    items = "".join(f"<url><loc>{esc(u)}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{items}</urlset>\n"
    )


def _render_accessibility() -> str:
    """The on-site accessibility statement: what we aim for, how we check, known
    limitations, and a way to report a barrier (the Section 508 / EN 301 549
    feedback mechanism). Detailed evidence lives in docs/accessibility.md (the
    WCAG 2.2 AAA conformance report) and docs/vpat.md (the 508-edition VPAT)."""
    canonical = f"{BASE_URL}/accessibility/"
    repo = "https://github.com/ChelseaKR/gtfs-scorecard"
    body = f"""    {_breadcrumb([("Home", "/"), ("Accessibility", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Accessibility</h1>
    <p class="page-lede">This site is meant to be usable by everyone, including
    people who use a keyboard, a screen reader, a magnifier, or high-contrast
    colours. Here is where we stand and how to tell us when something gets in
    your way.</p>

    {_route_rule()}
    <section><h2 class="section-title">What we aim for</h2>
    <p>We build and test to <abbr title="Web Content Accessibility Guidelines">WCAG</abbr>
    2.2 Level AAA, which goes beyond the Level AA bar that
    <abbr title="Section 508 of the Rehabilitation Act">Section&nbsp;508</abbr> and
    <abbr title="the European accessibility standard">EN&nbsp;301&nbsp;549</abbr> require.
    That covers the landing page, the interactive app, every agency and section page,
    and the printable brief.</p></section>

    <section><h2 class="section-title">How we check</h2>
    <p>Every colour pair is verified to clear AAA contrast in all four themes by an
    automated gate, and accessibility checks (axe and Lighthouse) run on each change.
    On top of the automated checks we review the site by keyboard and with assistive
    technology. You can read the full results in the
    <a href="{repo}/blob/main/docs/accessibility.md">conformance report</a> and the
    <a href="{repo}/blob/main/docs/vpat.md">508-edition <abbr title="Voluntary Product Accessibility Template">VPAT</abbr></a>.</p></section>

    <section><h2 class="section-title">Known limitations</h2>
    <p>We keep an honest list. The national map is a convenience layer built on a
    third-party component; everything it shows is also on the fully accessible
    <a href="/agencies/">agency list</a>, so no one is stranded. A few linked external
    documents (federal rules, validator docs) are outside our control; we summarise
    them in plain language on our own pages.</p></section>

    <section><h2 class="section-title">Report a barrier</h2>
    <p>If any part of this site is hard or impossible to use, please tell us. You do
    not need to know the technical standard, just describe what got in your way.</p>
    <p><a class="download-btn" href="{repo}/issues/new?labels=accessibility&amp;template=accessibility.md">Report an accessibility barrier</a></p>
    <p>If you would rather not file a public issue, you can reach the maintainer
    through the contact link on <a href="https://chelseakr.com">chelseakr.com</a>.
    We aim to acknowledge accessibility reports within a few business days.</p></section>

    <p class="page-lede" style="margin-top:2rem">Last reviewed: 22 June 2026.</p>"""
    return _page(
        title="Accessibility | GTFS Scorecard",
        description="How the GTFS Scorecard meets WCAG 2.2 AAA and Section 508, its known limitations, and how to report an accessibility barrier.",
        canonical=canonical,
        body=body,
    )


def _methodology_versions_section() -> str:
    """A visible validator + rubric version stamp and a dated methodology changelog
    on the public methodology page (RESEARCH-ROADMAP R9). The version stamp already
    rides on each agency page; surfacing it here, with the effective-dated changelog,
    means a reader can see what produced a grade and when the rules last moved without
    reading the artifact JSON. Sourced from score.methodology_changelog so the page and
    scoring.json never drift."""
    from . import RUBRIC_VERSION
    from .score import methodology_changelog
    from .validate import VALIDATOR_VERSION

    repo = "https://github.com/ChelseaKR/gtfs-scorecard"
    rows = "".join(
        f"<dt>Rubric v{esc(entry['rubric_version'])} "
        f'<span class="ntd-status ntd-unknown">Effective {esc(entry["effective_date"])}</span></dt>'
        f"<dd>{esc(entry['summary'])}</dd>"
        for entry in methodology_changelog()
    )
    return f"""    {_route_rule()}
    <section aria-labelledby="methodology-h"><h2 class="section-title" id="methodology-h">Methodology and versions</h2>
    <p>Every grade is computed by scorecard rubric <strong>v{esc(RUBRIC_VERSION)}</strong> on top of the
    MobilityData <abbr title="GTFS Schedule Validator">gtfs-validator</abbr> <strong>{esc(VALIDATOR_VERSION)}</strong>,
    anchored to the California Transit Data Guidelines v4.0. The same validator and rubric version are
    stamped on each agency's scorecard, so any grade is traceable to what produced it. The full method,
    with citations, is in the <a href="{repo}/blob/main/docs/rubric.md">scoring rubric</a>.</p>
    <p>When the rubric changes we log it here with the date it took effect, so a score change is never a
    silent rule change:</p>
    <dl class="standards-list">{rows}</dl></section>"""


def _sensitivity_note() -> str:
    """The latest weight-sensitivity study's headline (FIX-07), or a placeholder
    before the first study has been published. Reads the artifact the
    ``scorecard sensitivity`` command publishes under data/artifacts, the same
    base the other national artifacts are served from; a missing or malformed
    file degrades to the placeholder so the guide renders fine on a fresh
    checkout."""
    path = _repo_root() / "data" / "artifacts" / "sensitivity.json"
    try:
        study = json.loads(path.read_text())
    except (FileNotFoundError, ValueError, OSError):
        study = None
    link = '<a href="/data/artifacts/sensitivity.json">sensitivity.json</a>'
    if not isinstance(study, dict) or not study.get("agency_count"):
        return (
            "the first study has not been published yet. When it runs, its headline "
            f"lands here and the full numbers are published at {link}."
        )
    factor_pct = round(float(study.get("factor", 0.2)) * 100)
    date = esc(str(study.get("generated_at", ""))[:10])
    dated = f", studied {date}" if date else ""
    return (
        f"rescoring all {int(study['agency_count'])} tracked agencies under every "
        f"&plusmn;{factor_pct}% single-weight change, at most "
        f"{study.get('max_grade_change_pct', 0)}% of letter grades move{dated}. "
        f"Full numbers, per perturbation: {link}."
    )


def _render_guide() -> str:
    """A plain-language 'how to read your scorecard' on-ramp for someone who has
    never seen GTFS, including what the grades mean so 'is a B good?' is answered."""
    canonical = f"{BASE_URL}/how-to-read/"
    legend = "".join(
        f'<li class="legend-row"><span class="grade-chip {_grade_class(g)}">{g}</span> '
        f"<span>{meaning}</span></li>"
        for g, meaning in [
            ("A", "Solid. The feed is current and well filled in."),
            ("B", "Good, with a few optional fields to add."),
            ("C", "Working, but with real gaps worth fixing."),
            ("D", "Several gaps; start with the top fix."),
            (
                "F",
                "Usually the feed has expired or is missing required data, so trip planners may have dropped it. This is the urgent one.",
            ),
        ]
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("All agencies", "/agencies/"), ("How to read your scorecard", None)])}
    <a class="backlink" href="/agencies/">&larr; All agencies</a>
    <h1 class="page-title">How to read your scorecard</h1>
    <p class="page-lede">No jargon. Here is what the page is telling you and what to do about it.</p>

    {_route_rule()}
    <section><h2 class="section-title">What this checks</h2>
    <p>Transit apps and trip planners read a file your agency publishes, called a
    <dfn><abbr title="General Transit Feed Specification">GTFS</abbr></dfn> feed.
    It lists your stops, routes, and schedule. This tool downloads that feed every day, runs the
    same validator the State and the apps use, and turns the result into a grade and a short list
    of fixes. It does not look at your buses or your service, only the data file.
    New to the terms? Jump to the <a href="#glossary">glossary</a>.</p>
    <p>The grade blends four things: <strong>Correctness</strong> (does the data follow the rules),
    <strong>Freshness</strong> (is the feed about to expire), <strong>Rider experience</strong>
    (are accessibility, fares, and destinations filled in), and <strong>Realtime quality</strong>
    (if you publish live arrivals, sometimes called
    <abbr title="GTFS Realtime">GTFS-RT</abbr>). If you do not publish realtime, that is fine and
    does not count against you.</p></section>

    {_route_rule()}
    <section><h2 class="section-title">What the grades mean</h2>
    <ul class="legend">{legend}</ul>
    <p class="page-lede">Most small and rural feeds we check land between F and B. A grade is a
    starting point for a conversation, not a verdict on your agency.</p></section>

    {_route_rule()}
    <section><h2 class="section-title">Grade margins and weight sensitivity</h2>
    <p>Letter grades have edges, and a score can sit right next to one: 89.9 is a B and 90.1 is
    an A, yet they are nearly the same feed. So every scorecard artifact states its distance to
    those edges: <code>margin_to_next_band</code> is how many points to the next letter up
    (&ldquo;a B, 0.4 points from an A&rdquo; &mdash; null for an A, which has no higher band), and
    <code>margin_to_lower_band</code> is how far the score sits above the floor of its current
    band. A small upward margin is encouragement, not a warning: it means the next letter is
    within reach, often with a single fix.</p>
    <p>The category weights behind the score are documented judgment calls, so we also measure
    their consequences the same way: {_sensitivity_note()}</p></section>

    {_route_rule()}
    <section><h2 class="section-title">What to do</h2>
    <p>Start at the top of "Top things to fix." We put the most rider-affecting fix first. If your
    feed has expired, that will be fix number one, because an expired feed is invisible to riders
    even while your buses run. Each fix says roughly how long it takes. You do not have to do them
    all; doing the first one and re-publishing is a real win.</p>
    <p>If you did not make the feed yourself, the agency or vendor that exports your GTFS is who
    makes these changes. Hand them the top fix.</p></section>

    {_route_rule()}
    <section><h2 class="section-title">What this is not</h2>
    <p>This is a data-quality lens to help you improve the feed. It is not an official compliance
    determination from any transit program, and a low grade does not mean your service is bad. See the
    <a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/listing-policy.md">listing
    and removal policy</a> for how a listing can be corrected or removed.</p></section>

{_methodology_versions_section()}

    {_route_rule()}
    <section aria-labelledby="glossary-h"><h2 class="section-title" id="glossary-h">Glossary</h2>
    <p class="page-lede">Plain-language definitions for the abbreviations and jargon used across
    the scorecard. Each term is also defined inline the first time it appears on a page.</p>
    <dl class="standards-list">
      <dt><dfn id="g-gtfs"><abbr title="General Transit Feed Specification">GTFS</abbr></dfn></dt>
      <dd>The standard data file an agency publishes so apps can show its stops, routes, and schedule.</dd>
      <dt><dfn id="g-gtfs-rt"><abbr title="GTFS Realtime">GTFS-RT</abbr> (GTFS-Realtime)</dfn></dt>
      <dd>The live companion to GTFS: real-time trip updates, vehicle positions, and service alerts.</dd>
      <dt><dfn id="g-rt"><abbr title="realtime">RT</abbr></dfn></dt>
      <dd>Short for realtime: live arrival and position data, as opposed to the static schedule.</dd>
      <dt><dfn id="g-ntd"><abbr title="National Transit Database">NTD</abbr></dfn></dt>
      <dd>The Federal Transit Administration's national reporting system for transit agencies.</dd>
      <dt><dfn id="g-fta"><abbr title="Federal Transit Administration">FTA</abbr></dfn></dt>
      <dd>The federal agency that funds transit and runs the National Transit Database.</dd>
      <dt><dfn id="g-d10"><abbr title="FTA NTD certification form D-10">D-10</abbr></dfn></dt>
      <dd>The annual NTD certification form on which an agency certifies its GTFS feed.</dd>
      <dt><dfn id="g-acs"><abbr title="American Community Survey">ACS</abbr></dfn></dt>
      <dd>The Census Bureau survey used for the equity overlay's poverty and access indicators.</dd>
      <dt><dfn id="g-mdb"><abbr title="Mobility Database">MDB</abbr></dfn></dt>
      <dd>The Mobility Database, the open catalog of transit feeds the scorecard discovers feeds from.</dd>
      <dt><dfn id="g-gbfs"><abbr title="General Bikeshare Feed Specification">GBFS</abbr></dfn></dt>
      <dd>A sibling open spec for shared bikes and scooters, related to but separate from GTFS.</dd>
      <dt><dfn id="g-yaml">YAML</dfn></dt>
      <dd>The plain-text config format used to add an agency in the repository (no YAML needed via the form).</dd>
      <dt><dfn id="g-ci"><abbr title="continuous integration">CI</abbr></dfn></dt>
      <dd>Continuous integration: automated checks that run on every change, including the feed grader.</dd>
      <dt><dfn id="g-sha"><abbr title="Secure Hash Algorithm, 256-bit">SHA-256</abbr></dfn></dt>
      <dd>A fingerprint of the exact feed bytes scored, so a grade is reproducible and citeable.</dd>
    </dl></section>"""
    return _page(
        title="How to read your scorecard — GTFS Scorecard",
        description="A plain-language guide to the GTFS Scorecard: what it checks, what the A-F grades mean, and what to do first.",
        canonical=canonical,
        body=body,
    )


# State normalization lives with the catalog it normalizes (mobilitydb); the
# private alias keeps existing callers and tests unchanged.
_canonical_state = canonical_state


def _states_by_agency() -> dict[str, str]:
    """Map each tracked agency to its US state for the directory's browse-by-place.

    A curator's `state` in agencies.yaml wins. The Mobility Database cohort,
    which has no hand-set state, is filled from the catalog's subdivision via the
    pinned mdb_id, normalized to a recognized state name (a stray city or region
    in the catalog drops to unlocated rather than becoming its own chip). The
    catalog is only downloaded when at least one agency actually needs it (so
    tests and the pilot registry never hit the network), and any catalog failure
    degrades to unlocated rather than breaking the render.
    """
    from .config import AGENCIES

    states = {aid: a.state for aid, a in AGENCIES.items() if a.state}
    needs_catalog = any(a.mdb_id and aid not in states for aid, a in AGENCIES.items())
    if not needs_catalog:
        return states
    try:
        from .mobilitydb import load_catalog

        by_mdb = {f.mdb_id: f.subdivision for f in load_catalog() if f.mdb_id and f.subdivision}
    except Exception as exc:  # noqa: BLE001 - a catalog hiccup must not break the render
        # The live catalog is the authoritative source, but a transient outage
        # must not silently wipe every agency's state from the rendered site.
        # Carry forward the state from the last published catalog.json instead,
        # so a render without network reproduces the previous state of record.
        print(f"::warning title=state lookup::catalog unavailable: {exc}", file=sys.stderr)
        return _published_states() | states
    for aid, agency in AGENCIES.items():
        if aid not in states and agency.mdb_id:
            sub = by_mdb.get(agency.mdb_id)
            canonical = _canonical_state(sub) if sub else ""
            if canonical:
                states[aid] = canonical
    return states


def _load_liveness() -> dict[str, dict[str, Any]]:
    """The intraday refresh's per-feed change-detection state, keyed by agency id.
    Missing or malformed file degrades to empty, so the site renders fine before
    the first refresh has run."""
    path = _repo_root() / "data" / "liveness.json"
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, ValueError, OSError):
        return {}
    feeds = data.get("feeds", {})
    return feeds if isinstance(feeds, dict) else {}


def _published_states() -> dict[str, str]:
    """State per agency from the last published catalog.json, the offline fallback
    when the live Mobility Database catalog can't be reached. Missing or malformed
    file degrades to empty, same as an unavailable catalog."""
    path = _repo_root() / "web" / "catalog.json"
    try:
        catalog = json.loads(path.read_text())
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return {
        a["id"]: a["state"] for a in catalog.get("agencies", []) if a.get("id") and a.get("state")
    }


def compute_changes(index: dict[str, Any], min_score_delta: float = 1.0) -> list[dict[str, Any]]:
    """Agencies whose grade or score moved between their two most recent checks.

    The "what changed today" feed an ops consumer (a trip planner, a transit app)
    wants instead of diffing the whole catalog. Pure over the index so it is
    testable; worst regressions first, then biggest moves.
    """
    out: list[dict[str, Any]] = []
    for agency_id, entry in index.get("agencies", {}).items():
        hist = entry.get("history", [])
        if len(hist) < 2:
            continue
        prev, cur = hist[-2], hist[-1]
        grade_changed = prev.get("grade") != cur.get("grade")
        delta = round(float(cur.get("score", 0)) - float(prev.get("score", 0)), 1)
        if not grade_changed and abs(delta) < min_score_delta:
            continue
        regressed = grade_changed and (
            GRADE_RANK.get(str(cur.get("grade")), 0) < GRADE_RANK.get(str(prev.get("grade")), 0)
        )
        out.append(
            {
                "id": agency_id,
                "name": entry.get("name", agency_id),
                "from_grade": prev.get("grade"),
                "to_grade": cur.get("grade"),
                "from_score": prev.get("score"),
                "to_score": cur.get("score"),
                "score_delta": delta,
                "regressed": bool(regressed or delta < 0),
                "since": prev.get("date"),
                "date": cur.get("date"),
            }
        )
    # Regressions first (the actionable ones), then largest absolute move.
    out.sort(key=lambda c: (not c["regressed"], -abs(float(c["score_delta"]))))
    return out


def _changes_sections(changes: list[dict[str, Any]]) -> str:
    """The improved/needs-attention sections of the daily change feed
    (compute_changes), side by side on wide screens. Rendered inside the
    national pulse page; reuses the delta-* styles from the per-agency trend
    section."""
    improved = sorted(
        (c for c in changes if not c["regressed"]), key=lambda c: -float(c["score_delta"])
    )
    declined = sorted((c for c in changes if c["regressed"]), key=lambda c: float(c["score_delta"]))

    def _rows(items: list[dict[str, Any]], up: bool) -> str:
        if not items:
            msg = (
                "No agencies improved since their last check."
                if up
                else "No agencies slipped &mdash; a good day."
            )
            return f'<li class="delta-row"><span class="delta-cat">{msg}</span></li>'
        cls, arrow, word = (
            ("delta-up", "&#9650;", "up") if up else ("delta-down", "&#9660;", "down")
        )
        rows = []
        for c in items:
            delta = abs(float(c["score_delta"]))
            grade = (
                f"{esc(c.get('from_grade'))} &rarr; {esc(c.get('to_grade'))}"
                if c.get("from_grade") != c.get("to_grade")
                else esc(c.get("to_grade"))
            )
            rows.append(
                f'<li class="delta-row">'
                f'<a class="delta-cat" href="/agency/{esc(c["id"])}/">{esc(c["name"])}</a>'
                f'<span class="delta {cls}"><span aria-hidden="true">{arrow}</span> '
                f"{word} {delta:g} &middot; {grade}</span></li>"
            )
        return "".join(rows)

    return f"""<div class="section-grid">
    <section aria-labelledby="improved-h">
      <h2 class="section-title" id="improved-h">Most improved</h2>
      <ul class="delta-list">{_rows(improved, True)}</ul>
    </section>
    <section aria-labelledby="attention-h">
      <h2 class="section-title" id="attention-h">Needs attention</h2>
      <ul class="delta-list">{_rows(declined, False)}</ul>
    </section>
    </div>
    <p class="subscribe-line"><a href="/changes/feed.xml">Subscribe to changes (Atom)</a>
    to get grade drops in a feed reader or a webhook, with no sign-up. Each agency
    also has its own feed at <code>/agency/&lt;id&gt;/feed.xml</code>.</p>"""


def _ridership_impact_line(impact: dict[str, Any] | None) -> str:
    """One national sentence weighting quality by rider-trips (ADR 0021).

    Rendered only when the NTD ridership snapshot matched enough feeds to be
    honest, and always with its coverage stated, so the number can never read
    as more national than it is. A stat about trips, never a ranking."""
    if not impact or not impact.get("matched_agencies"):
        return ""
    matched = impact["matched_agencies"]
    total = impact.get("total_agencies", matched)
    trips = impact.get("total_annual_trips", 0)
    pct = impact.get("expired_trips_pct", 0)
    return (
        '<p class="page-lede">Weighted by ridership, these feeds carry about '
        f"<strong>{trips:,}</strong> annual rider-trips (the {matched} of {total} "
        f"tracked agencies with a matched NTD ridership record), and "
        f"<strong>{pct}%</strong> of those trips ride on a feed that has expired. "
        'The same numbers are at <a href="/api/v1/ridership-impact.json">the '
        "ridership-impact API</a>.</p>"
    )


def _render_pulse_page(
    board: dict[str, Any],
    changes: list[dict[str, Any]],
    trend_points: list[dict[str, Any]],
    trend_sum: dict[str, Any],
    improvers: list[dict[str, Any]] | None,
    ridership_impact: dict[str, Any] | None = None,
    histories: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """The national pulse (/pulse/): rankings, what changed, and the trend on
    one page instead of three thin ones. Each former page is a titled section
    with a stable anchor, reached by a plain jump nav (no JS, no tabs), so the
    retired /leaderboard/, /changes/, and /trends/ URLs redirect here without
    losing their in-page destinations. Common problems keeps its own page (it
    is an actionable fix list, a different job) and is linked from here."""
    jump = (
        '<nav class="grade-jump" aria-label="Jump to section">Jump to: '
        '<a href="#rankings">Rankings</a> · <a href="#changes">What changed</a> · '
        '<a href="#trend">The trend</a> · <a href="/problems/">Common problems</a></nav>'
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("National pulse", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">The national pulse.</h1>
    <p class="page-lede">How the country's transit data is doing, on one page: how
    agencies rank, who moved since their last check, and whether the whole corpus is
    getting better. These views cover the feeds this site tracks, not every transit
    agency in the country; an agency that is absent is simply not covered yet, never
    failing.</p>
    {jump}
    <section id="rankings" aria-labelledby="rankings-h" tabindex="-1">
      <h2 class="section-title" id="rankings-h">Rankings</h2>
      {_ridership_impact_line(ridership_impact)}
      {_leaderboard_sections(board, histories)}
    </section>
    {_route_rule()}
    <section id="changes" aria-labelledby="changes-h" tabindex="-1">
      <h2 class="section-title" id="changes-h">What changed since the last check</h2>
      {_changes_sections(changes)}
    </section>
    {_route_rule()}
    <section id="trend" aria-labelledby="trend-h" tabindex="-1">
      <h2 class="section-title" id="trend-h">Is transit data getting better?</h2>
      {_trend_sections(trend_points, trend_sum, improvers)}
    </section>
    <p class="plain-summary"><strong>In plain words:</strong> this page tracks the whole
    country at once, not any single agency. The <a href="/problems/">most common
    problems</a> page names the recurring fixes behind these numbers. Writing about
    this data? <a href="/press/">Start with the reporter's page.</a></p>"""
    return _page(
        title="The national pulse — GTFS Scorecard",
        description=(
            "How US transit data is doing on one page: agency rankings, who improved "
            "or slipped since their last check, and the national trend over time."
        ),
        canonical=f"{BASE_URL}/pulse/",
        body=body,
        wide=True,
        head_extra=(
            '<link rel="alternate" type="application/atom+xml" '
            f'title="GTFS Scorecard feed quality changes" href="{BASE_URL}/changes/feed.xml">'
        ),
    )


def _render_focus_page(ntd_payload: dict[str, Any], rt_rollup: dict[str, Any]) -> str:
    """The focus-areas hub (/focus/): one screen naming the dimensional lenses
    (NTD readiness, realtime reliability, equity, what feeds publish), each with
    its headline number and a one-line reason to open it. These pages share a
    skeleton but serve different audiences, so they stay separate destinations;
    this hub is the front door the primary nav points at."""
    pct_ready = ntd_payload.get("pct_ready", 0)
    monitored = rt_rollup.get("monitored_count", 0)
    areas = [
        (
            "/ntd/",
            "NTD certification readiness",
            f"{pct_ready}% of tracked feeds look ready to certify",
            "Which feeds are published, valid, and current against the FTA "
            "requirement, nationally and by state.",
        ),
        (
            "/realtime/",
            "Realtime reliability",
            f"{monitored} realtime feeds monitored",
            "Uptime and freshness for the agencies that publish GTFS-Realtime.",
        ),
        (
            "/equity/",
            "Equity overlay",
            "Where weak data meets high need",
            "States ordered by how much low-grade data lands on riders with the "
            "fewest alternatives.",
        ),
        (
            "/adoption/",
            "What feeds publish",
            "Flexible service, fares, pathways, and accessibility data",
            "Adoption of the newer, optional parts of GTFS, and how complete "
            "wheelchair-access data is.",
        ),
    ]
    items = "".join(
        f'<li class="finding"><p class="what"><a href="{esc(href)}">{esc(name)}</a> '
        f'<span class="count">{esc(stat)}</span></p>'
        f'<p class="why">{esc(what)}</p></li>'
        for href, name, stat, what in areas
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("Focus areas", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Focus areas.</h1>
    <p class="page-lede">One national lens per question: certification, realtime,
    equity, and what feeds publish. Each opens a full page with the by-state
    breakdown and the agencies leading it.</p>
    <ul class="findings">{items}</ul>
    <p class="fineprint">Every lens measures published data, never a compliance
    determination or on-the-ground service quality, and none of them changes a
    grade.</p>"""
    return _page(
        title="Focus areas — GTFS Scorecard",
        description=(
            "National lenses on US transit data: NTD certification readiness, realtime "
            "reliability, the equity overlay, and what feeds publish."
        ),
        canonical=f"{BASE_URL}/focus/",
        body=body,
    )


def _write_catalog(write: Callable[..., None], catalog: list[dict[str, Any]]) -> None:
    """Write catalog.json and catalog.csv: every agency's grade, score, feed URL,
    days-until-expiry, and top fix in one document."""
    from . import DATA_ATTRIBUTION, DATA_LICENSE, RUBRIC_VERSION, SCHEMA_VERSION

    payload = {
        "source": BASE_URL,
        "schema_version": SCHEMA_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "agencies": catalog,
    }
    write("catalog.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")

    buf = io.StringIO()
    cols = [
        "id",
        "name",
        "state",
        "grade",
        "score",
        "size_tier",
        "national_percentile",
        "snapshot_date",
        "days_until_expiry",
        "expiry_status",
        "mdb_id",
        "validator_version",
        "feed_url",
        "top_fix",
        "scorecard_url",
    ]
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(catalog)
    write("catalog.csv", buf.getvalue())


# Grade colours for the map, matching the badge palette. Chosen to stay
# distinguishable under common colour-vision deficiencies; the grade letter in
# each popup and the legend carries the meaning, never colour alone.
_MAP_GRADE_COLOR = {
    "A": "#1f7a4d",
    "B": "#3f7d20",
    "C": "#9a7d0a",
    "D": "#b5651d",
    "F": "#a32020",
}


def _map_feature(
    agency_id: str, artifact: dict[str, Any], state: str = "", country: str = ""
) -> dict[str, Any] | None:
    """A GeoJSON point feature for an agency, or None when it has no geometry.

    ``state`` and ``country`` come from the directory record (the artifact itself
    carries country but not state); they ride along so the map and list share one
    filter.
    """
    geo = artifact.get("geo")
    if not isinstance(geo, dict):
        return None
    lon, lat = geo.get("lon"), geo.get("lat")
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return None
    overall = artifact.get("overall", {})
    grade = str(overall.get("grade", "?"))
    name = str(artifact.get("agency", {}).get("name", agency_id))
    # Flexible (demand-responsive) service, as detected by flex.py and recorded
    # under categories.completeness.details.flex in the artifact.
    completeness = (artifact.get("categories") or {}).get("completeness") or {}
    flex_details = (completeness.get("details", {}) or {}).get("flex", {}) or {}
    has_flex = bool(flex_details.get("has_flex", False))
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "id": agency_id,
            "name": name,
            "grade": grade,
            "score": overall.get("score"),
            "state": state or "",
            "country": country or "",
            "has_flex": has_flex,
            # The grade letter is drawn as the marker's label so grade is never
            # carried by colour alone (WCAG 1.4.1); colour only reinforces it.
            "color": _MAP_GRADE_COLOR.get(grade, "#5a5a5a"),
            "url": f"/agency/{agency_id}/",
        },
    }


_MAP_LIB_VERSION = "4.7.1"


def _render_map_page(features: list[dict[str, Any]]) -> str:
    """The national map page: every located agency as a point labelled with its
    grade letter and coloured by grade, rendered client-side by MapLibre over the
    keyless OpenFreeMap basemap and clustered at low zoom.

    The map is an enhancement. The conformant primary is the filterable agency
    table below it (grade, state, score, link), reached by a 'Skip to the agency
    list' bypass before the map; the same grade and state selectors filter the
    map and the table together. The MapLibre canvas is marked aria-hidden and
    kept out of the tab order, so a keyboard or screen-reader user works the
    table, never the canvas (docs/vpat.md)."""
    count = len(features)
    legend_items = "".join(
        f'<li><span class="map-dot" style="background:{color}">'
        f'<span class="map-dot-letter" aria-hidden="true">{grade}</span></span>'
        f"Grade {grade}</li>"
        for grade, color in _MAP_GRADE_COLOR.items()
    )
    # The accessible primary: one row per located agency, the same set the map
    # plots. Sorted by name for a stable, scannable order.
    rows_data = sorted(
        (
            {
                "id": str(p.get("id", "")),
                "name": str(p.get("name", "")),
                "grade": str(p.get("grade", "?")),
                "state": str(p.get("state", "") or ""),
                "country": str(p.get("country", "") or ""),
                "has_flex": bool(p.get("has_flex", False)),
                "score": p.get("score"),
            }
            for p in (f.get("properties", {}) for f in features)
        ),
        key=lambda r: r["name"].lower(),
    )
    table_rows = "".join(
        f'<tr data-grade="{esc(r["grade"])}" data-state="{esc(r["state"])}" '
        f'data-country="{esc(r["country"])}" '
        f'data-has-flex="{str(r["has_flex"]).lower()}" '
        f'data-name="{esc(r["name"].lower())}">'
        f'<td><a href="/agency/{esc(r["id"])}/">{esc(r["name"])}</a></td>'
        f"<td>{esc(r['grade'])}</td><td>{esc(r['state'] or r['country']) or '&mdash;'}</td>"
        f"<td>{esc(r['score'])}</td></tr>"
        for r in rows_data
    )
    # Build location options: US states + Canada (using "Canada" as value to avoid
    # collision with California's "CA" state code)
    us_states = sorted({r["state"] for r in rows_data if r["state"]})
    location_opts = "".join(f'<option value="{esc(s)}">{esc(s)}</option>' for s in us_states)
    if any(r["country"] == "CA" for r in rows_data):
        location_opts += '<option value="Canada">Canada</option>'
    grade_opts = "".join(f'<option value="{g}">Grade {g}</option>' for g in _MAP_GRADE_COLOR)
    body = f"""    {_breadcrumb([("Home", "/"), ("National map", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">The national map.</h1>
    <p class="page-lede">Every tracked agency with a locatable
    <abbr title="General Transit Feed Specification">GTFS</abbr> feed, placed at its
    service area, labelled with its grade letter and coloured by grade. {count} agencies
    are on the map. Select a point for its grade and a link to the scorecard, or work
    the list below.</p>
    <p class="page-lede">To see the actual route lines instead of one point per agency,
    open <a href="/routes/">every route on one map</a>.</p>
    <a class="skip-link-inline" href="#agency-list">Skip to the agency list</a>
    <form class="map-filters" aria-label="Filter the map and list">
      <p class="map-filters-intro">Filter by grade, location, or flexible service. The map and the list update together.</p>
      <div class="map-filter-row">
        <label for="map-grade">Grade</label>
        <select id="map-grade" name="grade"><option value="">All grades</option>{grade_opts}</select>
        <label for="map-state">Location</label>
        <select id="map-state" name="state"><option value="">All locations</option>{location_opts}</select>
      </div>
      <div class="map-filter-row">
        <label><input type="checkbox" id="map-flex" name="flex"> Offers GTFS-Flex (demand-responsive service)</label>
      </div>
    </form>
    <div id="map" class="national-map" aria-hidden="true"><p class="map-fallback">The map
      draws here once its library loads from a content delivery network. If it stays
      blank (a blocked or slow network), the agency list below carries everything the
      map shows.</p></div>
    <ul class="map-legend" aria-label="Grade colours">{legend_items}</ul>
    <p class="fineprint">Points are placed at each feed's median stop. Basemap:
      OpenFreeMap, &copy; OpenStreetMap contributors. Data: this scorecard, CC BY 4.0.</p>
    <section id="agency-list" tabindex="-1" aria-labelledby="agency-list-h">
      <h2 class="section-title" id="agency-list-h">Every agency on the map</h2>
      <p class="map-count" role="status"><span id="map-result-count">{count}</span> of {count}
        agencies shown.</p>
      <table class="leaderboard map-table">
        <caption class="visually-hidden">Agencies on the national map, with grade, location,
          and score. Use the grade and location filters above to narrow the list.</caption>
        <thead><tr><th scope="col">Agency</th><th scope="col">Grade</th>
          <th scope="col">Location</th><th scope="col">Score</th></tr></thead>
        <tbody id="map-tbody">{table_rows}</tbody>
      </table>
    </section>
    <script src="https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.js"></script>
    <script>
      (function () {{
        var gradeEl = document.getElementById("map-grade");
        var stateEl = document.getElementById("map-state");
        var flexEl = document.getElementById("map-flex");
        var countEl = document.getElementById("map-result-count");
        var rows = Array.prototype.slice.call(
          document.querySelectorAll("#map-tbody tr"));
        var all = null;  // the full FeatureCollection, fetched once

        function matches(grade, state, country, hasFlex) {{
          var g = gradeEl.value, loc = stateEl.value, f = flexEl && flexEl.checked;
          var locOk = !loc || state === loc || (loc === "Canada" && country === "CA");
          // hasFlex is a string from the table's data attribute and a boolean
          // from the GeoJSON properties; accept both.
          var flexOk = !f || hasFlex === true || hasFlex === "true";
          return (!g || grade === g) && locOk && flexOk;
        }}
        // The table is the conformant primary; filter it even when the map
        // (and MapLibre) never load.
        function filterTable() {{
          var shown = 0;
          rows.forEach(function (tr) {{
            var ok = matches(tr.getAttribute("data-grade"),
                             tr.getAttribute("data-state"),
                             tr.getAttribute("data-country"),
                             tr.getAttribute("data-has-flex"));
            tr.hidden = !ok;
            if (ok) shown++;
          }});
          if (countEl) countEl.textContent = shown;
        }}

        if (!window.maplibregl) {{
          gradeEl.addEventListener("change", filterTable);
          stateEl.addEventListener("change", filterTable);
          if (flexEl) flexEl.addEventListener("change", filterTable);
          filterTable();
          return;
        }}
        var reduce = window.matchMedia
          && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        var map = new maplibregl.Map({{
          container: "map",
          style: "https://tiles.openfreemap.org/styles/positron",
          center: [-96, 38], zoom: 3, keyboard: false,
          attributionControl: false
        }});
        // Take the canvas out of the tab order synchronously (not only on load),
        // so this aria-hidden map never briefly holds a focusable canvas while a
        // slower basemap style is still loading (WCAG aria-hidden-focus).
        map.getCanvas().setAttribute("tabindex", "-1");
        // No on-canvas controls: the canvas is aria-hidden and out of the tab
        // order, so it must hold nothing focusable. Scroll/pinch zooms; clicking
        // a cluster zooms in; the table is the operable primary.

        function filtered() {{
          if (!all) return {{ type: "FeatureCollection", features: [] }};
          return {{
            type: "FeatureCollection",
            features: all.features.filter(function (f) {{
              var p = f.properties || {{}};
              return matches(p.grade, p.state || "", p.country || "", p.has_flex);
            }})
          }};
        }}
        function applyFilter() {{
          filterTable();
          var src = map.getSource("agencies");
          if (src) src.setData(filtered());
        }}

        map.on("load", function () {{
          // The canvas is a visual layer only; the table is the operable
          // equivalent, so keep the canvas out of the keyboard tab order.
          map.getCanvas().setAttribute("tabindex", "-1");
          map.addSource("agencies", {{
            type: "geojson", data: {{ type: "FeatureCollection", features: [] }},
            cluster: true, clusterRadius: 48, clusterMaxZoom: 6
          }});
          // Clusters: a neutral disc with a count, a low-zoom convenience.
          map.addLayer({{
            id: "clusters", type: "circle", source: "agencies",
            filter: ["has", "point_count"],
            paint: {{
              "circle-color": "#3a4a42",
              "circle-radius": ["step", ["get", "point_count"], 14, 25, 18, 100, 24],
              "circle-stroke-width": 1.5, "circle-stroke-color": "#ffffff"
            }}
          }});
          map.addLayer({{
            id: "cluster-count", type: "symbol", source: "agencies",
            filter: ["has", "point_count"],
            layout: {{
              "text-field": ["get", "point_count_abbreviated"],
              "text-font": ["Noto Sans Regular"],
              "text-size": 12, "text-allow-overlap": true
            }},
            paint: {{ "text-color": "#ffffff" }}
          }});
          map.addLayer({{
            id: "agencies", type: "circle", source: "agencies",
            filter: ["!", ["has", "point_count"]],
            paint: {{
              "circle-radius": 9, "circle-color": ["get", "color"],
              "circle-stroke-width": 1, "circle-stroke-color": "#ffffff"
            }}
          }});
          // The grade letter, drawn on every point so grade reads without colour.
          map.addLayer({{
            id: "agency-grade", type: "symbol", source: "agencies",
            filter: ["!", ["has", "point_count"]],
            layout: {{
              "text-field": ["get", "grade"], "text-size": 11,
              "text-font": ["Noto Sans Bold"], "text-allow-overlap": true
            }},
            paint: {{
              "text-color": "#ffffff",
              "text-halo-color": "#1c1c1c", "text-halo-width": 0.8
            }}
          }});
          fetch("/map.geojson").then(function (r) {{ return r.json(); }})
            .then(function (gj) {{ all = gj; applyFilter(); }})
            .catch(function () {{}});

          map.on("click", "clusters", function (e) {{
            var f = map.queryRenderedFeatures(e.point, {{ layers: ["clusters"] }})[0];
            if (!f) return;
            // MapLibre GL >= 3 returns a Promise here (the callback form was
            // removed); a click on a cluster zooms in to expand it.
            Promise.resolve(
              map.getSource("agencies").getClusterExpansionZoom(f.properties.cluster_id)
            ).then(function (zoom) {{
              map.easeTo({{
                center: f.geometry.coordinates, zoom: zoom,
                animate: !reduce, duration: reduce ? 0 : 500
              }});
            }}).catch(function () {{}});
          }});
          map.on("click", "agencies", function (e) {{
            var p = e.features[0].properties;
            var link = document.createElement("a");
            link.href = p.url; link.textContent = p.name + " (grade " + p.grade + ")";
            var div = document.createElement("div");
            div.appendChild(link);
            new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(div).addTo(map);
          }});
          ["clusters", "agencies"].forEach(function (layer) {{
            map.on("mouseenter", layer, function () {{ map.getCanvas().style.cursor = "pointer"; }});
            map.on("mouseleave", layer, function () {{ map.getCanvas().style.cursor = ""; }});
          }});
        }});
        gradeEl.addEventListener("change", applyFilter);
        stateEl.addEventListener("change", applyFilter);
        if (flexEl) flexEl.addEventListener("change", applyFilter);
      }})();
    </script>"""
    head_extra = (
        f'<link rel="stylesheet" '
        f'href="https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.css">'
    )
    return _page(
        title="National map — GTFS Scorecard",
        description="A national map of transit agencies labelled and coloured by GTFS data quality grade.",
        canonical=f"{BASE_URL}/map/",
        wide=True,
        body=body,
        head_extra=head_extra,
    )


# The protomaps PMTiles client, pinned alongside MapLibre. It registers the
# pmtiles:// protocol so MapLibre can read a single range-requested archive of
# vector tiles straight from static hosting (no tile server). See ADR 0023.
_PMTILES_LIB_VERSION = "3.2.1"

# Where the committed national-routes archive lives, served by the same static
# host as the rest of the site (GitHub Pages, which honours HTTP range requests).
_NATIONAL_ROUTES_PMTILES = "/tiles/national-routes.pmtiles"

# Route-type colours for the all-routes map, paired with the words the legend
# shows, so meaning never rides on colour alone (WCAG 1.4.1). Order is the legend
# order; the trailing entry is the catch-all for less common modes.
_ROUTE_TYPE_MAP_COLORS: list[tuple[str, str]] = [
    ("Bus", "#1A7A46"),
    ("Rail", "#8844AA"),
    ("Subway / metro", "#3344CC"),
    ("Tram / light rail", "#C03020"),
    ("Ferry", "#1B7FA8"),
    ("Trolleybus", "#B5651D"),
]
_ROUTE_TYPE_OTHER = ("Other modes", "#5a5a5a")


def _route_type_color_expr() -> list[Any]:
    """A MapLibre ``match`` expression: route ``type`` string -> line colour."""
    expr: list[Any] = ["match", ["get", "type"]]
    for label, color in _ROUTE_TYPE_MAP_COLORS:
        expr.extend([label, color])
    expr.append(_ROUTE_TYPE_OTHER[1])  # fallback for unlisted modes
    return expr


def _grade_color_expr() -> list[Any]:
    """A MapLibre ``match`` expression: agency ``grade`` letter -> line colour."""
    expr: list[Any] = ["match", ["get", "grade"]]
    for grade, color in _MAP_GRADE_COLOR.items():
        expr.extend([grade, color])
    expr.append("#5a5a5a")  # ungraded / unknown
    return expr


def _routes_map_script() -> str:
    """The MapLibre bootstrap for the national all-routes map.

    Reads the vector tiles from a single PMTiles archive over the pmtiles://
    protocol (range requests, no tile server), draws every agency's route lines,
    and lets the reader recolour by route type or agency grade. The canvas is a
    visual enhancement marked aria-hidden: it carries no keyboard tab stop and no
    zoom controls, because the operable equivalent is the agencies list and the
    per-agency route tables linked above it. prefers-reduced-motion is honoured
    (no animated fly-to on click)."""
    type_expr = json.dumps(_route_type_color_expr(), separators=(",", ":"))
    grade_expr = json.dumps(_grade_color_expr(), separators=(",", ":"))
    return f"""    <script src="https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.js"></script>
    <script src="https://unpkg.com/pmtiles@{_PMTILES_LIB_VERSION}/dist/pmtiles.js"></script>
    <script>
      (function () {{
        if (!window.maplibregl || !window.pmtiles) return;
        var reduce = window.matchMedia
          && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        var typeColor = {type_expr};
        var gradeColor = {grade_expr};
        var protocol = new pmtiles.Protocol();
        maplibregl.addProtocol("pmtiles", protocol.tile);
        var map = new maplibregl.Map({{
          container: "routes-map",
          style: "https://tiles.openfreemap.org/styles/positron",
          center: [-96, 38], zoom: 3,
          attributionControl: false,
          keyboard: false
        }});
        // Take the canvas out of the tab order synchronously (not only on load),
        // so this aria-hidden map never briefly holds a focusable canvas while a
        // slower basemap style is still loading (WCAG aria-hidden-focus).
        map.getCanvas().setAttribute("tabindex", "-1");
        map.on("load", function () {{
          // The canvas is a visual layer only; the agencies list and per-agency
          // route tables are the operable equivalent, so keep it out of the tab
          // order (mirrors the aria-hidden container).
          map.getCanvas().setAttribute("tabindex", "-1");
          map.addSource("routes", {{
            type: "vector",
            url: "pmtiles://{_NATIONAL_ROUTES_PMTILES}",
            attribution: "GTFS Scorecard, CC BY 4.0"
          }});
          map.addLayer({{
            id: "routes-line", type: "line", source: "routes",
            "source-layer": "routes",
            layout: {{ "line-join": "round", "line-cap": "round" }},
            paint: {{ "line-color": typeColor, "line-width": 1.6, "line-opacity": 0.85 }}
          }});
          map.on("click", "routes-line", function (e) {{
            var p = e.features[0].properties;
            var div = document.createElement("div");
            var strong = document.createElement("strong");
            strong.textContent = (p.agency_name || p.agency) + ", route " + p.route;
            div.appendChild(strong);
            var sub = document.createElement("div");
            sub.textContent = p.type + ", grade " + p.grade;
            div.appendChild(sub);
            var link = document.createElement("a");
            link.href = "/agency/" + p.agency + "/";
            link.textContent = "Open this agency's scorecard";
            div.appendChild(link);
            new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(div).addTo(map);
          }});
          map.on("mouseenter", "routes-line", function () {{ map.getCanvas().style.cursor = "pointer"; }});
          map.on("mouseleave", "routes-line", function () {{ map.getCanvas().style.cursor = ""; }});
          // Recolour control: route type (default) or agency grade. Each radio
          // also toggles which text legend is shown.
          var radios = document.querySelectorAll('input[name="route-color-mode"]');
          function apply(mode) {{
            map.setPaintProperty("routes-line", "line-color",
              mode === "grade" ? gradeColor : typeColor);
            var typeLeg = document.getElementById("legend-type");
            var gradeLeg = document.getElementById("legend-grade");
            if (typeLeg) typeLeg.hidden = mode === "grade";
            if (gradeLeg) gradeLeg.hidden = mode !== "grade";
          }}
          radios.forEach(function (r) {{
            r.addEventListener("change", function () {{ if (r.checked) apply(r.value); }});
          }});
        }});
      }})();
    </script>"""


def _render_routes_page(summary: dict[str, Any]) -> str:
    """The national all-routes map: every agency's route shapes on one canvas,
    rendered from a single PMTiles archive of vector tiles.

    This is an exploratory enhancement, not the conformant data interface. A
    national map of route lines cannot be a literal data table, so the page leads
    with a prominent bypass to the equivalents that *are* AAA-conformant: the
    sortable agencies list and the per-agency route tables. See docs/vpat.md.
    """
    agency_count = int(summary.get("agency_count") or 0)
    route_count = int(summary.get("route_count") or 0)

    type_legend_items = "".join(
        f'<li><span class="map-dot" style="background:{color}"></span>{esc(label)}</li>'
        for label, color in [*_ROUTE_TYPE_MAP_COLORS, _ROUTE_TYPE_OTHER]
    )
    grade_legend_items = "".join(
        f'<li><span class="map-dot" style="background:{color}"></span>Grade {grade}</li>'
        for grade, color in _MAP_GRADE_COLOR.items()
    )

    body = f"""    {_breadcrumb([("Home", "/"), ("All routes", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Every route, one map.</h1>
    <p class="page-lede">The route shapes of every tracked agency, drawn from each
    feed's own <abbr title="General Transit Feed Specification">GTFS</abbr> and
    combined on a single map. {route_count} routes from {agency_count} agencies are
    on it. Recolour by route type or by the agency's data-quality grade, and select
    a line for the agency and a link to its scorecard.</p>
    <p class="page-lede"><strong>This map is a visual extra, not the accessible way
    to read the data.</strong> A map of this many route lines can't be a data table.
    For a screen-reader and keyboard friendly view, use
    <a href="/agencies/">the sortable agencies list</a>; each agency's own scorecard
    carries <a href="/agency/unitrans/">a route-by-route table</a> of its lines.</p>
    <section aria-labelledby="routes-map-h" class="route-map-section">
      <h2 id="routes-map-h" class="section-title">National all-routes map</h2>
      <a class="skip-link-inline" href="#routes-after-map">Skip to the accessible agency list</a>
      <fieldset class="map-colormode">
        <legend>Colour routes by</legend>
        <label><input type="radio" name="route-color-mode" value="type" checked> Route type</label>
        <label><input type="radio" name="route-color-mode" value="grade"> Agency grade</label>
      </fieldset>
      <div id="routes-map" class="national-map" aria-hidden="true"></div>
      <ul class="map-legend" id="legend-type" aria-label="Route type colours">{type_legend_items}</ul>
      <ul class="map-legend" id="legend-grade" aria-label="Agency grade colours" hidden>{grade_legend_items}</ul>
    </section>
    <div id="routes-after-map" tabindex="-1"></div>
    <p class="page-lede">Read the data without the map:</p>
    <ul class="route-skip-targets">
      <li><a href="/agencies/">All agencies</a>, sortable by grade, state, and size.</li>
      <li><a href="/pulse/#rankings">National pulse rankings</a> of the highest and lowest scoring feeds.</li>
      <li>Each scorecard (for example <a href="/agency/unitrans/">Unitrans</a>) lists its
        routes and stops in a table.</li>
    </ul>
    <p class="fineprint">Routes are one representative shape per route, simplified for
    the national view; zoom in for detail. Tiles are served as a single PMTiles
    archive over HTTP range requests. Basemap: OpenFreeMap, &copy; OpenStreetMap
    contributors. Data: this scorecard, CC BY 4.0.</p>
{_routes_map_script()}"""
    head_extra = (
        f'<link rel="stylesheet" '
        f'href="https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.css">'
    )
    return _page(
        title="Every route on one map — GTFS Scorecard",
        description=(
            "A national vector map of every tracked agency's transit routes, "
            "coloured by route type or data-quality grade."
        ),
        canonical=f"{BASE_URL}/routes/",
        body=body,
        head_extra=head_extra,
    )


def _leaderboard_sections(
    board: dict[str, Any], histories: dict[str, list[dict[str, Any]]] | None = None
) -> str:
    """Best and worst standings and the biggest movers, as a two-column grid of
    tables inside the national pulse page. The same data the /api/v1 endpoints
    serve. Each row links to that agency's scorecard and carries a small score
    sparkline from its history (an em dash until it has two checks)."""
    hist = histories or {}

    def _trend_cell(r: dict[str, Any]) -> str:
        return f"<td>{_spark_mini(hist.get(str(r['id'])), str(r.get('name', r['id'])))}</td>"

    def _rank_table(rows: list[dict[str, Any]], caption: str) -> str:
        if not rows:
            return ""
        items = "".join(
            f'<tr><td><a href="/agency/{esc(r["id"])}/">{esc(r.get("name", r["id"]))}</a></td>'
            f"<td>{esc(r.get('grade'))}</td><td>{esc(r.get('score'))}</td>{_trend_cell(r)}</tr>"
            for r in rows
        )
        return (
            f'<section class="feed-details"><h2 class="section-title">{esc(caption)}</h2>'
            '<table class="leaderboard"><thead><tr><th>Agency</th><th>Grade</th>'
            f"<th>Score</th><th>Trend</th></tr></thead><tbody>{items}</tbody></table></section>"
        )

    def _move_table(rows: list[dict[str, Any]], caption: str) -> str:
        if not rows:
            return ""
        items = "".join(
            f'<tr><td><a href="/agency/{esc(r["id"])}/">{esc(r.get("name", r["id"]))}</a></td>'
            f"<td>{esc(r.get('grade'))}</td><td>{esc(r.get('score'))}</td>"
            f"<td>{'+' if r['score_delta'] > 0 else ''}{esc(r['score_delta'])}</td>"
            f"{_trend_cell(r)}</tr>"
            for r in rows
        )
        return (
            f'<section class="feed-details"><h2 class="section-title">{esc(caption)}</h2>'
            '<table class="leaderboard"><thead><tr><th>Agency</th><th>Grade</th>'
            f"<th>Score</th><th>Change</th><th>Trend</th></tr></thead>"
            f"<tbody>{items}</tbody></table></section>"
        )

    return f"""<div class="section-grid">
    {_rank_table(board.get("top", []), "Highest scoring")}
    {_move_table(board.get("most_improved", []), "Most improved")}
    {_move_table(board.get("most_declined", []), "Needs attention")}
    {_rank_table(board.get("bottom", []), "Lowest scoring")}
    </div>
    <p class="fineprint">Lowest-scoring feeds are listed to help, not to shame: a low
    grade is usually a vendor export setting, and each scorecard names the fix.
    The same standings are available as
    <abbr title="JavaScript Object Notation">JSON</abbr> at
    <a href="/api/v1/leaderboard.json">the leaderboard API (leaderboard.json)</a>.</p>"""


_NEED_LABELS = {
    "high": "High need",
    "moderate": "Moderate need",
    "lower": "Lower need",
    "unknown": "Need unknown",
}

# Choropleth encoding for the equity need tiers. Colour is never the only signal:
# each tier also carries a distinct SVG fill pattern (hatch density) and its name
# in the state's title text and the paired table, so the map reads in greyscale
# and to a screen reader (WCAG 1.4.1). Fills are the same family as the existing
# expired-feed choropleth in styles.css (good green to rust).
_NEED_TIER_FILL = {
    "high": "#b5482a",
    "moderate": "#d6894e",
    "lower": "#5b9c7a",
    "unknown": "#d8d2c4",
}
# Pattern id per tier (defined once in the SVG defs); "" means a plain fill.
_NEED_TIER_PATTERN = {
    "high": "needHatchDense",
    "moderate": "needHatch",
    "lower": "",
    "unknown": "",
}


def _equity_choropleth(states_geo: dict[str, Any], by_state: dict[str, dict[str, Any]]) -> str:
    """An inline SVG choropleth of the ACS need tiers, built from the committed,
    public-domain simplified state geometry (web/us-states.json, see ADR 0022).

    Each state is filled by tier colour with a tier-specific hatch pattern, and
    carries a <title> naming the tier and the numbers, so the map is operable
    without colour and to assistive tech. States with no overlay row render faint
    and inert. It is purely static (no script, no tiles), so reduced-motion needs
    nothing extra. The paired table below carries the same numbers."""
    geo = states_geo.get("states") or {}
    if not geo:
        return ""
    paths = []
    for name, d in geo.items():
        row = by_state.get(name)
        if not row:
            paths.append(
                f'<path d="{esc(d)}" class="need-state need-empty" aria-hidden="true"></path>'
            )
            continue
        tier = str(row.get("need_tier", "unknown"))
        fill = _NEED_TIER_FILL.get(tier, _NEED_TIER_FILL["unknown"])
        pattern = _NEED_TIER_PATTERN.get(tier, "")
        share = row.get("low_grade_share")
        agencies = row.get("agency_count")
        noun = "agency" if agencies == 1 else "agencies"
        label = (
            f"{name}: {_NEED_LABELS.get(tier, tier)}, "
            f"{share}% of feeds on D or F, {agencies} {noun}"
        )
        fill_attr = f"fill:{fill}"
        path = (
            f'<path d="{esc(d)}" class="need-state need-{esc(tier)}" '
            f'data-state="{esc(name)}" style="{fill_attr}">'
            f"<title>{esc(label)}</title></path>"
        )
        # A hatch overlay path for the higher tiers, drawn on top with the same
        # geometry so colour is reinforced by texture in greyscale.
        if pattern:
            path += (
                f'<path d="{esc(d)}" class="need-hatch" '
                f'fill="url(#{pattern})" aria-hidden="true"></path>'
            )
        paths.append(path)
    legend = "".join(
        f'<span class="map-key"><span class="need-swatch need-{tier}" '
        f'aria-hidden="true"></span>{esc(_NEED_LABELS[tier])}</span>'
        for tier in ("high", "moderate", "lower")
    )
    return (
        '<figure class="us-map need-map">'
        f'<svg class="us-map-svg" viewBox="{esc(states_geo.get("viewBox", "0 0 960 600"))}" '
        'role="img" aria-labelledby="need-map-h need-map-desc">'
        '<title id="need-map-h">Transit need by state</title>'
        '<desc id="need-map-desc">Each state is shaded and hatched by its ACS transit-need '
        "tier; the same figures are in the state table below.</desc>"
        "<defs>"
        '<pattern id="needHatch" width="7" height="7" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" '
        'stroke="#3a1d12" stroke-width="1.1" stroke-opacity="0.55"></line></pattern>'
        '<pattern id="needHatchDense" width="4" height="4" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="4" '
        'stroke="#2a1109" stroke-width="1.2" stroke-opacity="0.6"></line></pattern>'
        "</defs>"
        f"{''.join(paths)}"
        "</svg>"
        f'<figcaption class="map-legend"><span class="map-key-lab">Need tier:</span> {legend}'
        '<span class="map-key need-empty-key"><span class="need-swatch need-empty" '
        'aria-hidden="true"></span>No tracked feeds</span></figcaption>'
        "</figure>"
    )


# Brushing between the equity choropleth and the state table: hovering (or, on
# touch, tapping) a state and its table row light each other up. A progressive
# enhancement over the static map and its accessible-primary table, so it adds no
# tab stops and the page reads unchanged with JavaScript off.
_EQUITY_BRUSH_JS = r"""    <script>
      (function () {
        var svg = document.querySelector(".need-map .us-map-svg");
        var tables = document.getElementById("equity-tables");
        if (!svg || !tables) return;
        var paths = {}, rows = {};
        svg.querySelectorAll("path[data-state]").forEach(function (p) {
          paths[p.getAttribute("data-state")] = p;
        });
        tables.querySelectorAll("tr[data-state-key]").forEach(function (r) {
          rows[r.getAttribute("data-state-key")] = r;
        });
        var current = null, pinned = null;
        function paint(key, on) {
          if (paths[key]) paths[key].classList.toggle("is-brushed", on);
          if (rows[key]) rows[key].classList.toggle("is-brushed", on);
        }
        function brush(key) {
          if (key === current) return;
          if (current !== null) paint(current, false);
          current = key;
          if (key !== null) paint(key, true);
        }
        function wire(el, key) {
          el.addEventListener("mouseenter", function () { brush(key); });
          el.addEventListener("mouseleave", function () { brush(pinned); });
          el.addEventListener("click", function () {
            pinned = (pinned === key) ? null : key;
            brush(pinned);
          });
        }
        Object.keys(paths).forEach(function (key) { wire(paths[key], key); });
        Object.keys(rows).forEach(function (key) { wire(rows[key], key); });
      })();
    </script>"""


def _render_equity_page(overlay: dict[str, Any], states_geo: dict[str, Any] | None = None) -> str:
    """The equity overlay page: high-need states carrying many weak feeds, so a
    program sees where bad data lands on riders with the fewest alternatives.
    Rendered from the published overlay (the equity workflow's ACS join); shows a
    neutral note when the overlay has not been computed yet.

    A state-level choropleth visualises the ACS need tiers when both the overlay
    and the committed state geometry are present. The priority and per-state
    tables are the conformant primary: they carry every number the map encodes,
    reached by a 'Skip to the state tables' bypass before the map."""
    priority = overlay.get("priority") or []
    states = overlay.get("states") or []
    by_state = {str(s.get("state")): s for s in states}

    if priority:
        rows = "".join(
            f"<tr><td>{esc(s['state'])}</td><td>{esc(s['low_grade_share'])}%</td>"
            f"<td>{esc(s['agency_count'])}</td><td>{esc(s.get('median_score'))}</td></tr>"
            for s in priority
        )
        table = (
            '<section aria-labelledby="priority-h"><h2 class="section-title" id="priority-h">'
            "High-need states</h2>"
            '<table class="leaderboard"><thead><tr><th scope="col">State</th>'
            '<th scope="col">D/F share</th><th scope="col">Agencies</th>'
            '<th scope="col">Median score</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></section>"
        )
        lead = (
            "High-need states (by ACS poverty, zero-vehicle, and disability shares), "
            "ordered by the share of their feeds on a D or F grade. This is where weak "
            "data lands on riders with the fewest alternatives."
        )
    else:
        table = ""
        lead = (
            "No state currently meets the high-need threshold (two or more of the ACS "
            "poverty, zero-vehicle, and disability indicators in their high band), or the "
            "ACS indicators have not loaded yet. It refreshes from Census ACS on a schedule."
        )

    # The full per-state table: the conformant equivalent of the choropleth, so
    # every state the map shades is also readable as text, ordered by need then
    # by the share of feeds on a low grade.
    states_table = ""
    if states:
        tier_rank = {"high": 0, "moderate": 1, "lower": 2, "unknown": 3}
        ordered = sorted(
            states,
            key=lambda s: (
                tier_rank.get(str(s.get("need_tier")), 9),
                -float(s.get("low_grade_share") or 0),
                str(s.get("state")),
            ),
        )
        srows = "".join(
            f'<tr data-state-key="{esc(s.get("state"))}">'
            f'<th scope="row">{esc(s.get("state"))}</th>'
            f"<td>{esc(_NEED_LABELS.get(str(s.get('need_tier')), s.get('need_tier')))}</td>"
            f"<td>{esc(s.get('low_grade_share'))}%</td>"
            f"<td>{esc(s.get('agency_count'))}</td>"
            f"<td>{esc(s.get('median_score'))}</td></tr>"
            for s in ordered
        )
        states_table = (
            '<section aria-labelledby="states-h"><h2 class="section-title" id="states-h">'
            "Every state</h2>"
            '<p class="page-lede">The need tier and low-grade share for every state we track, '
            "the same figures the map encodes.</p>"
            '<table class="leaderboard"><thead><tr><th scope="col">State</th>'
            '<th scope="col">Need tier</th><th scope="col">D/F share</th>'
            '<th scope="col">Agencies</th><th scope="col">Median score</th></tr></thead>'
            f"<tbody>{srows}</tbody></table></section>"
        )

    choropleth = ""
    skip = ""
    if states_geo and by_state:
        choropleth = _equity_choropleth(states_geo, by_state)
        if choropleth:
            skip = '<a class="skip-link-inline" href="#equity-tables">Skip to the state tables</a>'
    brush_script = _EQUITY_BRUSH_JS if choropleth else ""

    return _page(
        title="Equity overlay — GTFS Scorecard",
        description="Where weak GTFS data meets high transit need, from Census ACS indicators.",
        canonical=f"{BASE_URL}/equity/",
        wide=True,
        body=f"""    {_breadcrumb([("Home", "/"), ("Equity overlay", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Equity overlay.</h1>
    <p class="page-lede">{lead}</p>
    {skip}
    {choropleth}
    <div id="equity-tables" tabindex="-1">
    {table}
    {states_table}
    </div>
    <p class="plain-summary"><strong>In plain words:</strong> this highlights states where many
    weak feeds overlap with riders who most depend on transit, so help can go where it matters
    most. It never changes any agency's grade.</p>
    <p class="fineprint">Need tiers come from Census
    <abbr title="American Community Survey">ACS</abbr> (poverty, zero-vehicle households,
    disability share), joined to agencies by state. They prioritize data-quality help; they
    never change a grade. The same data is at
    <a href="/api/v1/equity.json">the equity API (equity.json)</a>. State outlines:
    public-domain simplified geometry (docs/decisions/0022-equity-choropleth.md). State-level is
    a first cut; a tract-level refinement is in progress.</p>
    {brush_script}""",
    )


def _render_ntd_page(
    payload: dict[str, Any], histories: dict[str, list[dict[str, Any]]] | None = None
) -> str:
    """The national NTD certification-readiness view, for an FTA or state-DOT
    program lead. Reads the same ntd.json the pipeline publishes (the published,
    valid, and current pillars rolled up across every tracked feed) and shows the
    headline share ready to certify plus a per-state breakdown, so a liaison can
    see where the gaps sit without opening each scorecard. It is a heads-up, not an
    official determination; the agency's own D-10 certification is the official one.
    """
    total = payload.get("total", 0)
    by_state = payload.get("by_state", {}) or {}
    if total:
        state_rows = "".join(
            f"<tr><td>{esc(state)}</td><td>{esc(c.get('ready', 0))}</td>"
            f"<td>{esc(c.get('at_risk', 0))}</td><td>{esc(c.get('not_ready', 0))}</td>"
            f"<td>{esc(c.get('total', 0))}</td></tr>"
            for state, c in sorted(by_state.items())
        )
        state_table = (
            '<section class="feed-details"><h2 class="section-title">By state</h2>'
            '<table class="leaderboard"><thead><tr><th>State</th><th>Ready</th>'
            "<th>At risk</th><th>Not ready</th><th>Total</th></tr></thead>"
            f"<tbody>{state_rows}</tbody></table></section>"
        )
        lead = (
            f"<strong>{esc(payload.get('pct_ready', 0))}% of {esc(total)} tracked feeds "
            "look ready to certify</strong> against the three things the "
            "Federal Transit Administration checks: the feed is published at a working "
            "URL, it is valid, and its calendar has not lapsed."
        )
    else:
        state_table = ""
        lead = "No feeds have been assessed for NTD readiness yet."
    one_fix = payload.get("one_fix_from_ready") or []
    one_fix_total = payload.get("one_fix_total", len(one_fix))
    hist = histories or {}
    if one_fix:
        one_fix_rows = "".join(
            f'<tr><td><a href="/agency/{esc(r["id"])}/">{esc(r["name"])}</a></td>'
            f"<td>{esc(r.get('state') or '')}</td><td>{esc(r.get('fix', ''))}</td>"
            f"<td>{_spark_mini(hist.get(str(r['id'])), str(r['name']))}</td></tr>"
            for r in one_fix
        )
        shown_note = (
            f'<p class="fineprint">Showing {len(one_fix)} of {esc(one_fix_total)} feeds; '
            'the full list is in <a href="/ntd.json">ntd.json</a>.</p>'
            if one_fix_total > len(one_fix)
            else ""
        )
        one_fix_table = (
            '<h3 class="section-title">One fix from ready</h3>'
            '<p class="page-lede">Each of these feeds is a single fix away from looking '
            "ready to certify. The fix column is written to be forwarded as-is.</p>"
            '<table class="leaderboard"><thead><tr><th>Agency</th><th>State</th>'
            f"<th>The one fix</th><th>Trend</th></tr></thead><tbody>{one_fix_rows}</tbody></table>"
            f"{shown_note}"
        )
    else:
        one_fix_table = ""
    ry2026 = (
        '<section class="feed-details"><h2 class="section-title">Report year 2026: '
        "small and rural reporters join</h2>"
        '<p class="page-lede">Full reporters have had to include valid GTFS in their NTD '
        "report since report year 2025. Reduced, rural, and tribal reporters join in "
        "report year 2026, which brings most of the small agencies this site tracks into "
        "the requirement for the first time. An agency that cannot comply yet can request "
        "a one-year waiver by showing it is pursuing technical assistance to establish "
        "its GTFS data.</p>"
        f"{one_fix_table}"
        '<p class="fineprint">Source: FTA\'s '
        '<a href="https://www.federalregister.gov/documents/2025/07/10/2025-12813/'
        'national-transit-database-reporting-changes-and-clarifications-for-report-years-2025-and-2026">'
        "NTD reporting changes for report years 2025 and 2026</a>. State programs can "
        'reach small agencies through the <a href="/program/all/">program rollups</a>, and any '
        "expired feed's page carries a ready-to-send outreach note.</p></section>"
    )
    return _page(
        title="NTD readiness — GTFS Scorecard",
        description=(
            "How many tracked transit feeds look ready for FTA National Transit "
            "Database GTFS certification, nationally and by state."
        ),
        canonical=f"{BASE_URL}/ntd/",
        wide=True,
        body=f"""    {_breadcrumb([("Home", "/"), ("NTD readiness", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">NTD readiness.</h1>
    <p class="page-lede">{lead}</p>
    <section class="feed-details"><h2 class="section-title">Where feeds stand</h2>
    <table class="leaderboard"><thead><tr><th>Status</th><th>Feeds</th></tr></thead>
    <tbody>
      <tr><td>Ready to certify</td><td>{esc(payload.get("ready", 0))}</td></tr>
      <tr><td>At risk</td><td>{esc(payload.get("at_risk", 0))}</td></tr>
      <tr><td>Not ready</td><td>{esc(payload.get("not_ready", 0))}</td></tr>
    </tbody></table></section>
    {ry2026}
    {state_table}
    <p class="plain-summary"><strong>In plain words:</strong> since Report Year 2023, every
    NTD reporter with fixed-route or deviated-fixed-route service has to publish a valid,
    current GTFS feed and certify it each year. This page reads the published, valid, and
    current signals for every feed we track and rolls them up, so a program can see at a
    glance how its agencies are doing.</p>
    <p class="fineprint">This is a data-quality heads-up, not an official compliance
    determination. Each agency's annual
    <a href="https://www.transit.dot.gov/ntd">D-10 certification</a> is the official one.
    The same numbers are published as <abbr title="JavaScript Object Notation">JSON</abbr>
    at <a href="/ntd.json">ntd.json</a>.</p>""",
    )


_ACCESS_BAND_LABELS = {
    "most": "Nearly every stop marked",
    "some": "Some stops marked",
    "none": "No accessibility data yet",
}


def _access_sections(coverage: dict[str, Any]) -> str:
    """The accessibility-data coverage sections, inside the What-feeds-publish
    page: how many feeds let a wheelchair user plan a trip at all (the share of
    stops carrying ``wheelchair_boarding``), nationally and by state, with the
    most complete feeds highlighted. Changes no grade; framed as coverage to
    build on, for the advocate and the program staff who support them."""
    count = coverage.get("agency_count", 0)
    bands = coverage.get("bands", {})
    if count:
        band_rows = "".join(
            f"<tr><td>{esc(_ACCESS_BAND_LABELS.get(key, key))}</td>"
            f"<td>{esc(bands.get(key, 0))}</td></tr>"
            for key in ("most", "some", "none")
        )
        band_table = (
            '<section class="feed-details"><h2 class="section-title">Where feeds stand</h2>'
            '<table class="leaderboard"><thead><tr><th>Stop-level coverage</th>'
            f"<th>Feeds</th></tr></thead><tbody>{band_rows}</tbody></table></section>"
        )
        complete = coverage.get("most_complete", [])
        complete_rows = "".join(
            f'<tr><td><a href="/agency/{esc(m["id"])}/">{esc(m["name"])}</a></td>'
            f"<td>{esc(m.get('state'))}</td><td>{esc(m['pct'])}%</td></tr>"
            for m in complete
        )
        complete_table = (
            (
                '<section class="feed-details"><h2 class="section-title">Most complete</h2>'
                '<p class="page-lede">Feeds whose stops are the most fully marked for '
                "wheelchair access. A target to aim for.</p>"
                '<table class="leaderboard"><thead><tr><th>Agency</th><th>State</th>'
                f"<th>Stops marked</th></tr></thead><tbody>{complete_rows}</tbody></table></section>"
            )
            if complete
            else ""
        )
        state_rows = "".join(
            f"<tr><td>{esc(s['state'])}</td><td>{esc(s['agencies'])}</td>"
            f"<td>{esc(s.get('average_boarding_pct'))}%</td><td>{esc(s['most'])}</td>"
            f"<td>{esc(s['none'])}</td></tr>"
            for s in coverage.get("states", [])
        )
        state_table = (
            '<section class="feed-details"><h2 class="section-title">By state</h2>'
            '<table class="leaderboard"><thead><tr><th>State</th><th>Agencies</th>'
            "<th>Avg stops marked</th><th>Nearly all</th><th>None yet</th></tr></thead>"
            f"<tbody>{state_rows}</tbody></table></section>"
        )
        lead = (
            f"Across {esc(count)} feeds, an average of "
            f"<strong>{esc(coverage.get('average_boarding_pct'))}% of stops</strong> carry "
            "wheelchair-access information. When a stop is unmarked, a rider who uses a "
            "wheelchair cannot tell from a trip planner whether they can board there."
        )
    else:
        band_table = complete_table = state_table = ""
        lead = "No accessibility coverage has been measured yet."
    return f"""<p class="page-lede">{lead}
    <strong>What this measures:</strong> whether feeds publish the data, never
    whether a stop is physically usable.</p>
    <div class="section-grid">
    {band_table}
    {complete_table}
    </div>
    {state_table}
    <p class="fineprint">Coverage is the share of a feed's stops carrying
    <code>wheelchair_boarding</code> and trips carrying <code>wheelchair_accessible</code>,
    the fields the California Transit Data Guidelines ask for. It never changes a grade. The
    same data is at <a href="/api/v1/accessibility.json">the accessibility API
    (accessibility.json)</a>. This page is about data completeness; for how this site itself
    meets <abbr title="Web Content Accessibility Guidelines">WCAG</abbr>, see
    <a href="/accessibility/">Accessibility</a>.</p>"""


def _render_adoption_page(adoption: dict[str, Any], coverage: dict[str, Any]) -> str:
    """What feeds publish (/adoption/): the capability-adoption view (flexible
    service, fares and Fares v2, station pathways) and the accessibility-data
    coverage view, one page instead of two with identical skeletons. Reads the
    ``adoption.national_adoption`` and ``access.national_coverage`` rollups.
    Changes no grade; a lens on where the spec is spreading, framed as adoption
    to encourage. The retired /access/ URL redirects to #access here."""
    count = adoption.get("agency_count", 0)
    if count:

        def cap_row(label: str, share: dict[str, Any] | None) -> str:
            s = share or {}
            return (
                f"<tr><td>{esc(label)}</td><td>{esc(s.get('count', 0))}</td>"
                f"<td>{esc(s.get('pct', 0))}%</td></tr>"
            )

        cap_rows = (
            cap_row("Flexible (demand-responsive) service", adoption.get("flex"))
            + cap_row("Fare data (any model)", adoption.get("fares"))
            + cap_row("Fare data using Fares v2", adoption.get("fares_v2"))
            + cap_row("Station accessibility (pathways)", adoption.get("pathways"))
            + cap_row("Step-free station paths", adoption.get("step_free"))
            # cemv_support was adopted into GTFS in September 2025; the count
            # starts near zero by design, so the page watches it spread.
            + cap_row("Contactless payment declared (cEMV)", adoption.get("cemv"))
        )
        cap_table = (
            '<section class="feed-details"><h2 class="section-title">What feeds publish</h2>'
            '<table class="leaderboard"><thead><tr><th>Capability</th><th>Feeds</th>'
            f"<th>Share</th></tr></thead><tbody>{cap_rows}</tbody></table></section>"
        )
        flex_sample = adoption.get("flex_sample", [])
        flex_rows = "".join(
            f'<tr><td><a href="/agency/{esc(m["id"])}/">{esc(m["name"])}</a></td>'
            f"<td>{esc(m.get('state'))}</td></tr>"
            for m in flex_sample
        )
        flex_table = (
            (
                '<section class="feed-details"><h2 class="section-title">Publishing flexible '
                'service</h2><p class="page-lede">Feeds that already describe demand-responsive or '
                "dial-a-ride service in GTFS-Flex, so a trip planner can offer it.</p>"
                '<table class="leaderboard"><thead><tr><th>Agency</th><th>State</th></tr></thead>'
                f"<tbody>{flex_rows}</tbody></table></section>"
            )
            if flex_sample
            else ""
        )
        state_rows = "".join(
            f"<tr><td>{esc(s['state'])}</td><td>{esc(s['agencies'])}</td>"
            f"<td>{esc(s['flex'])}</td><td>{esc(s['fares'])}</td>"
            f"<td>{esc(s['fares_v2'])}</td><td>{esc(s['pathways'])}</td></tr>"
            for s in adoption.get("states", [])
        )
        state_table = (
            '<section class="feed-details"><h2 class="section-title">By state</h2>'
            '<table class="leaderboard"><thead><tr><th>State</th><th>Agencies</th>'
            "<th>Flex</th><th>Fares</th><th>Fares v2</th><th>Pathways</th></tr></thead>"
            f"<tbody>{state_rows}</tbody></table></section>"
        )
        flex_s = adoption.get("flex", {})
        fares = adoption.get("fares", {})
        v2 = adoption.get("fares_v2", {})
        paths = adoption.get("pathways", {})
        lead = (
            f"Across {esc(count)} feeds, <strong>{esc(flex_s.get('pct', 0))}%</strong> publish "
            f"flexible (demand-responsive) service, <strong>{esc(fares.get('pct', 0))}%</strong> "
            f"publish fare data ({esc(v2.get('pct', 0))}% using the newer Fares v2), and "
            f"<strong>{esc(paths.get('pct', 0))}%</strong> model stations with accessible paths. "
            "These are the newer, optional parts of GTFS; adoption shows where the spec is spreading."
        )
    else:
        cap_table = flex_table = state_table = ""
        lead = "No capability adoption has been measured yet."
    jump = (
        '<nav class="grade-jump" aria-label="Jump to section">Jump to: '
        '<a href="#features">Optional features</a> · '
        '<a href="#access">Accessibility data coverage</a></nav>'
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("What feeds publish", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">What feeds publish.</h1>
    <p class="page-lede">{lead}</p>
    <p class="page-lede"><strong>What this measures:</strong> adoption of optional
    parts of the spec, never quality. None of these counts changes a grade, and a
    feed without them is early, not failing.</p>
    {jump}
    <section id="features" aria-labelledby="features-h" tabindex="-1">
      <h2 class="section-title" id="features-h">The newer, optional parts of GTFS</h2>
      <div class="section-grid">
      {cap_table}
      {flex_table}
      </div>
      {state_table}
    </section>
    {_route_rule()}
    <section id="access" aria-labelledby="access-h" tabindex="-1">
      <h2 class="section-title" id="access-h">Accessibility data coverage</h2>
      {_access_sections(coverage)}
    </section>
    <p class="plain-summary"><strong>In plain words:</strong> a feed does not need any of these to
    earn a good grade. This tracks where the newer, optional parts of GTFS are catching on, so an
    agency can see what peers publish and a program can see where to help next.</p>
    <p class="fineprint">Adoption is read from each feed's own files: GTFS-Flex
    (<code>locations.geojson</code>, <code>booking_rules.txt</code>), fare data
    (<code>fare_attributes.txt</code> for the legacy model, <code>fare_products.txt</code> and
    <code>fare_leg_rules.txt</code> for Fares v2), and GTFS-Pathways (<code>pathways.txt</code>,
    <code>levels.txt</code>). It never changes a grade. The same data is at
    <a href="/api/v1/adoption.json">the adoption API (adoption.json)</a>.</p>"""
    return _page(
        title="What feeds publish — GTFS Scorecard",
        description=(
            "Which GTFS features US transit feeds publish (flexible service, fares and "
            "Fares v2, station pathways) and how complete their accessibility data is."
        ),
        canonical=f"{BASE_URL}/adoption/",
        body=body,
        wide=True,
    )


def _render_press_page() -> str:
    """The reporter's page (/press/): how to cite the data, the claims it does
    and does not support, and where the story-ready cuts live. Guards the
    no-shaming principle at the exact moment it is most at risk: a journalist
    reaching for an unfair ranking on deadline. Pure content, no data."""
    canonical = f"{BASE_URL}/press/"
    body = f"""    {_breadcrumb([("Home", "/"), ("For reporters", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Writing about this data.</h1>
    <p class="page-lede">Everything here is free to use with attribution
    (<abbr title="Creative Commons Attribution 4.0">CC BY 4.0</abbr>): "GTFS Scorecard
    (gtfsscorecard.org), scored on top of the MobilityData gtfs-validator." This page says
    what the numbers can and cannot support, so a story built on them holds up.</p>

    <section class="feed-details"><h2 class="section-title">Claims the data supports</h2>
    <ul>
      <li>"Agency X's published schedule data expired on [date], so trip planners like
      Google Maps stop showing its service." Expiry is read directly from the feed.</li>
      <li>"N of the M feeds tracked in [state] have expired." Counts over the covered
      set, with the state named.</li>
      <li>"Agency X's feed does not say which stops are wheelchair accessible." A statement
      about published data, and usually a one-setting fix in the agency's software.</li>
      <li>"Nationally, [pct]% of tracked feeds look ready for the federal
      <abbr title="National Transit Database">NTD</abbr> GTFS requirement."</li>
    </ul></section>

    <section class="feed-details"><h2 class="section-title">Claims it does not support</h2>
    <ul>
      <li><strong>"The worst transit agency in America."</strong> The scorecard covers the
      feeds it tracks, not every agency; absence means not covered, never failing, and a
      position on a list here is not a national rank.</li>
      <li><strong>"Agency X's buses are inaccessible."</strong> The accessibility number
      measures whether the data is published, never whether a stop or vehicle is usable.</li>
      <li><strong>"Agency X is out of compliance."</strong> Nothing here is an official
      determination; the readiness signals map data quality onto requirements, and the
      official checks belong to the agencies and their regulators.</li>
      <li><strong>Grade comparisons across sizes without saying so.</strong> A 10-bus rural
      system and a metro network face different capacity; the per-agency pages show peer
      percentiles within size bands for that reason.</li>
    </ul></section>

    <section class="feed-details"><h2 class="section-title">Story-ready data</h2>
    <p>Every number on this site is downloadable. For a local story, start with your
    state: the <a href="/pulse/">national pulse</a> for the picture, your state's
    program page (linked from any agency in it) for the portfolio, and the per-state
    rows in <a href="/api/v1/by-state.json">the by-state API</a>. For a citable
    snapshot, use a dated
    <a href="https://github.com/ChelseaKR/gtfs-scorecard/releases">dataset release</a>
    rather than the live site, which changes daily. Methodology, rubric weights, and
    the validator version are all published:
    <a href="/how-to-read/">how to read a scorecard</a> and
    <a href="/data/">the open dataset</a>.</p></section>

    <p class="fineprint">Questions about a specific number, or a correction? Open an
    issue on <a href="https://github.com/ChelseaKR/gtfs-scorecard">the repository</a>;
    the data and the code that produced it are both public.</p>"""
    return _page(
        title="Writing about this data — GTFS Scorecard",
        description=(
            "How reporters can use GTFS Scorecard data: attribution, the claims the "
            "numbers support and the ones they do not, and story-ready downloads."
        ),
        canonical=canonical,
        body=body,
    )


def _render_procurement() -> str:
    """A short, copy-paste page for an agency manager writing a vendor contract or
    RFP: language that asks a GTFS vendor to deliver a feed that passes the same
    canonical checks this site scores on. Pure content, no data; it turns the
    scorecard into a procurement lever, framed as a requirement an agency can set
    rather than a failure to catch after the fact."""
    canonical = f"{BASE_URL}/procurement/"
    repo = "https://github.com/ChelseaKR/gtfs-scorecard"
    clause = (
        "The vendor shall deliver a GTFS Schedule feed that produces zero errors from the "
        "current MobilityData canonical GTFS validator; includes a feed_info.txt with a "
        "service window covering at least the next 30 days at all times; populates "
        "wheelchair_boarding on stops and wheelchair_accessible on trips; and remains "
        "downloadable at a stable public URL. These are the criteria of the GTFS Scorecard "
        "conformance mark (Valid, Current, Accessible); the agency may verify the feed holds "
        "the mark at any time on its public scorecard page, at no cost to either party."
    )
    acceptance = (
        "Before acceptance, the vendor shall demonstrate the delivered feed earns at least "
        "grade B on the GTFS Scorecard rubric, for example by running "
        "`scorecard try <feed-url> --min-grade B` or the equivalent CI check, and shall "
        "provide the resulting report to the agency."
    )
    return _page(
        title="GTFS quality in your vendor contract — GTFS Scorecard",
        description=(
            "Copy-paste contract and RFP language for asking a GTFS vendor to deliver a "
            "feed that passes the canonical validator and stays current."
        ),
        canonical=canonical,
        body=f"""    {_breadcrumb([("Home", "/"), ("For agencies: procurement", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Put feed quality in the contract.</h1>
    <p class="page-lede">A vendor builds your GTFS feed. The cleanest time to require it be
    good is before you sign, not after a rider gets routed to the wrong corner. Here is
    language you can paste into a contract or an <abbr title="Request for Proposal">RFP</abbr>.</p>

    <section class="feed-details"><h2 class="section-title">Sample contract clause</h2>
    <blockquote class="plain-summary">{esc(clause)}</blockquote></section>

    <section class="feed-details"><h2 class="section-title">Sample acceptance test</h2>
    <p>Deliverables need a gate a non-developer can hold. This one is a single command the
    vendor runs and hands you the output of:</p>
    <blockquote class="plain-summary">{esc(acceptance)}</blockquote>
    <p>The conformance mark on the agency's scorecard page is the ongoing version of the
    same gate: it appears while the feed is valid, current, and carries accessibility
    fields, and it disappears when any of those lapses, so a contract can reference it as
    a standing condition rather than a one-time check.</p></section>

    <section class="feed-details"><h2 class="section-title">What each part buys you</h2>
    <ul>
      <li><strong>Zero validator errors</strong> is the same bar the apps and state programs
      apply, so your feed loads everywhere riders look.</li>
      <li><strong>A 30-day forward window</strong> stops the silent failure where a feed
      quietly expires and trip planners drop your agency.</li>
      <li><strong>Accessibility fields</strong> let a wheelchair user plan a trip at all.</li>
      <li><strong>A stable public URL</strong> is the first thing the
      <abbr title="Federal Transit Administration">FTA</abbr> looks for at NTD time.</li>
    </ul></section>

    <section class="feed-details"><h2 class="section-title">Verify it cheaply</h2>
    <p>You do not need to take the vendor's word for it. Find your agency on this site to see
    where the feed stands today, add a <a href="{repo}/blob/main/docs/ci-action.md">GTFS
    Scorecard check</a> to a build so a bad feed fails before it publishes, or
    <a href="/try.html">paste a feed URL</a> to grade it right now.</p></section>

    <p class="fineprint">This is sample language to adapt, not legal advice. Check it against
    your agency's procurement rules.</p>""",
    )


_RT_BAND_LABELS = {
    "reliable": "Reliable (99%+ uptime)",
    "mostly": "Mostly up (90–99%)",
    "spotty": "Spotty (under 90%)",
}


def _render_rt_page(
    nat: dict[str, Any], histories: dict[str, list[dict[str, Any]]] | None = None
) -> str:
    """The national realtime-reliability view, for a data team or a state program.
    Reads the rollup (``rt_national.national_rt``) over the uptime and header-lag
    samples the monitor already records and shows how many realtime feeds are
    reliable, the national median uptime and freshness, a per-state breakdown, and
    the most reliable feeds. It changes no grade; absence of a realtime feed is
    shown neutrally elsewhere, so this page only covers agencies that publish one.
    """
    count = nat.get("monitored_count", 0)
    bands = nat.get("bands", {})
    if count:
        band_rows = "".join(
            f"<tr><td>{esc(_RT_BAND_LABELS.get(key, key))}</td><td>{esc(bands.get(key, 0))}</td></tr>"
            for key in ("reliable", "mostly", "spotty")
        )
        band_table = (
            '<section class="feed-details"><h2 class="section-title">Where feeds stand</h2>'
            '<table class="leaderboard"><thead><tr><th>Reliability</th><th>Feeds</th>'
            f"</tr></thead><tbody>{band_rows}</tbody></table></section>"
        )
        reliable = nat.get("most_reliable", [])
        hist = histories or {}
        reliable_rows = "".join(
            f'<tr><td><a href="/agency/{esc(m["id"])}/">{esc(m["name"])}</a></td>'
            f"<td>{esc(m.get('state'))}</td><td>{esc(m['uptime_pct'])}%</td>"
            f"<td>{esc(m.get('median_lag_seconds'))}</td>"
            f"<td>{_spark_mini(hist.get(str(m['id'])), str(m['name']))}</td></tr>"
            for m in reliable
        )
        reliable_table = (
            (
                '<section class="feed-details"><h2 class="section-title">Most reliable</h2>'
                '<p class="page-lede">Feeds that responded on nearly every check, freshest '
                "first. A target to aim for.</p>"
                '<table class="leaderboard"><thead><tr><th>Agency</th><th>State</th>'
                "<th>Uptime</th><th>Median lag (s)</th><th>Score trend</th></tr></thead>"
                f"<tbody>{reliable_rows}</tbody></table></section>"
            )
            if reliable
            else ""
        )
        state_rows = "".join(
            f"<tr><td>{esc(s['state'])}</td><td>{esc(s['agencies'])}</td>"
            f"<td>{esc(s.get('median_uptime_pct'))}%</td><td>{esc(s['reliable'])}</td></tr>"
            for s in nat.get("states", [])
        )
        state_table = (
            '<section class="feed-details"><h2 class="section-title">By state</h2>'
            '<table class="leaderboard"><thead><tr><th>State</th><th>Feeds</th>'
            "<th>Median uptime</th><th>Reliable</th></tr></thead>"
            f"<tbody>{state_rows}</tbody></table></section>"
        )
        lag = nat.get("median_lag_seconds")
        lag_txt = f"{esc(lag)} seconds" if lag is not None else "not recorded"
        lead = (
            f"Of <strong>{esc(count)} agencies</strong> we monitor for realtime, the median "
            f"feed responded <strong>{esc(nat.get('median_uptime_pct'))}% of the time</strong>, "
            f"with the data arriving about {lag_txt} behind real time."
        )
    else:
        band_table = reliable_table = state_table = ""
        lead = "No realtime feeds have been monitored yet."
    return _page(
        title="Realtime reliability — GTFS Scorecard",
        description=(
            "How reliable transit agencies' GTFS-Realtime feeds are across the country: "
            "uptime and freshness, nationally and by state."
        ),
        canonical=f"{BASE_URL}/realtime/",
        wide=True,
        body=f"""    {_breadcrumb([("Home", "/"), ("Realtime reliability", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Realtime reliability.</h1>
    <p class="page-lede">{lead}</p>
    {band_table}
    {reliable_table}
    {state_table}
    <p class="plain-summary"><strong>In plain words:</strong> a realtime feed is only useful if
    it is actually up and current. This tracks whether each agency's feed responded when we
    checked and how far behind real time it was. An agency that publishes no realtime feed is not
    counted here and is never penalized for it.</p>
    <p class="fineprint">Reliability is the share of monitor runs the feed responded to, over the
    recorded window; freshness is the median header lag. It never changes a grade. The same data
    is at <a href="/api/v1/realtime.json">the realtime API (realtime.json)</a>. Sampling is
    periodic, not continuous, so this is a reliability signal, not a complete uptime log.</p>""",
    )


def _render_problems_page(nat: dict[str, Any]) -> str:
    """The national "most common GTFS problems" knowledge base, for a practitioner
    or a journalist. Reads the prevalence rollup (``findings_national``) and lists
    the most widespread problems across tracked feeds, each with how many feeds
    share it, what it means, and the one fix. Framed as common, fixable problems,
    never as a ranking of who is worst; it changes no grade.
    """
    problems = nat.get("problems", [])
    total = nat.get("total_agencies", 0)
    if problems:
        rows = ""
        for p in problems:
            code = esc(p["code"])
            guide = (
                f' <a class="fix-guide" href="/fix/{code}/">Read the fix guide</a>'
                if p["code"] in FIX_CODES_WITH_PAGES
                else ""
            )
            rows += (
                '<li class="event">'
                f"<p><strong>{esc(p['what'])}</strong> "
                f'<span class="mgrade">({esc(p["prevalence_pct"])}% of feeds, '
                f"{esc(p['severity'])})</span></p>"
                f"<p>{esc(p['why'])}</p>"
                f"<p><strong>Fix:</strong> {esc(p['fix'])}"
                f"{(' Effort: ' + esc(p['effort']) + '.') if p.get('effort') else ''}"
                f"{guide}</p>"
                "</li>"
            )
        body_problems = f'<ul class="events">{rows}</ul>'
        lead = (
            f"Across {esc(total)} tracked feeds, these are the problems the most agencies "
            "share. Each one is common, which means each fix helps a lot of riders at once."
        )
    else:
        body_problems = ""
        lead = "No findings have been aggregated yet."
    # Plain-language coverage governance: how much of what readers see nationally
    # carries curated what/why/fix text, plus the queue of what to curate next.
    # The metric makes the curation debt visible, which is the feature.
    coverage = plain_language_coverage(nat)
    if coverage["total_codes"]:
        queue = coverage["uncurated_queue"][:10]
        if queue:
            queue_rows = "".join(
                f"<tr><td>{esc(q['code'])}</td><td>{esc(q['instances'])}</td>"
                f"<td>{esc(q['agencies'])}</td></tr>"
                for q in queue
            )
            queue_table = (
                "<p>Next up for curation, ranked by how often riders' data actually "
                "hits each problem:</p>"
                '<table class="leaderboard"><thead><tr><th>Notice code</th>'
                "<th>Instances</th><th>Agencies</th></tr></thead>"
                f"<tbody>{queue_rows}</tbody></table>"
            )
        else:
            queue_table = "<p>Every problem code seen nationally has curated text.</p>"
        coverage_section = (
            '<section class="feed-details" aria-labelledby="coverage-h">'
            '<h2 class="section-title" id="coverage-h">Plain-language coverage</h2>'
            f"<p>Of the <strong>{esc(coverage['total_codes'])}</strong> distinct problem "
            f"codes seen nationally, <strong>{esc(coverage['curated_codes'])}</strong> carry "
            "vetted plain-language text: "
            f"<strong>{esc(coverage['distinct_code_coverage'])}%</strong> of codes and "
            f"<strong>{esc(coverage['instance_weighted_coverage'])}%</strong> of all finding "
            "instances. Codes without curated text fall back to a generic line that links "
            "to the validator's rule documentation.</p>"
            f"{queue_table}</section>"
        )
    else:
        coverage_section = ""
    return _page(
        title="The most common GTFS problems — GTFS Scorecard",
        description=(
            "The most widespread GTFS data problems across US transit feeds, how many "
            "agencies share each, and the one fix for each."
        ),
        canonical=f"{BASE_URL}/problems/",
        wide=True,
        body=f"""    {_breadcrumb([("Home", "/"), ("Common problems", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">The most common GTFS problems.</h1>
    <p class="page-lede">{lead}</p>
    <section aria-labelledby="problems-h">
    <h2 class="section-title visually-hidden" id="problems-h">Most common problems</h2>
    {body_problems}
    </section>
    {coverage_section}
    <p class="plain-summary"><strong>In plain words:</strong> most feeds trip on the same handful
    of things, and most of those are one export setting. If you run an agency, scanning this list
    is a fast way to find a fix that probably applies to you too.</p>
    <p class="fineprint">Prevalence is the share of tracked feeds carrying a finding, from the
    same checks each scorecard runs. It never changes a grade. The same data is at
    <a href="/api/v1/problems.json">the problems API (problems.json)</a>.</p>""",
    )


def _trend_sections(
    points: list[dict[str, Any]],
    summary: dict[str, Any],
    improvers: list[dict[str, Any]] | None = None,
) -> str:
    """The national quality trend, inside the pulse page: the average score over
    time as an autoscaled line plus a by-date table and the 90-day improvers.
    A measure of the whole corpus, not of any one agency; changes no grade."""
    if len(points) >= 2:
        scores = [float(p["average_score"]) for p in points]
        lo, hi = min(scores), max(scores)
        # The shared sparkline, autoscaled to the data range (y_min/y_max) so a
        # few-point move is visible: a dot at each date carries a native hover
        # tooltip (date and average), matching the per-agency chart, and the
        # numbers also live in the aria-label and the by-date table below.
        spark = _spark_svg(
            [(str(p["date"]), p["average_score"]) for p in points],
            aria_label=f"National average score by date (axis {lo:.1f} to {hi:.1f})",
            w=640,
            h=120,
            pad=12,
            y_min=lo,
            y_max=hi,
        )
        # A visible range caption, since the line is autoscaled with no drawn axis;
        # aria-hidden because the aria-label and table already carry these numbers.
        axis = (
            f'<p class="trend-axis" aria-hidden="true">Score axis {lo:.0f} to {hi:.0f}. '
            f"{esc(str(points[0]['date']))} to {esc(str(points[-1]['date']))}.</p>"
        )
        rows = "".join(
            f"<tr><td>{esc(p['date'])}</td><td>{esc(p['average_score'])}</td>"
            f"<td>{esc(p['agency_count'])}</td><td>{esc(p['expired_pct'])}%</td></tr>"
            for p in reversed(points)
        )
        table = (
            '<section class="feed-details"><h2 class="section-title">By date</h2>'
            '<table class="leaderboard"><thead><tr><th>Date</th><th>Avg score</th>'
            "<th>Feeds</th><th>Expired</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></section>"
        )
        delta = summary.get("score_delta")
        move = (
            "held about steady"
            if delta is None or abs(delta) < 0.1
            else f"rose {delta} points"
            if delta > 0
            else f"slipped {abs(delta)} points"
        )
        lead = (
            f"Across the feeds we track, the national average score {move} between "
            f"{esc(summary['first']['date'])} and {esc(summary['last']['date'])} "
            f"(now {esc(summary['last']['average_score'])})."
        )
        chart = f'<section class="feed-details"><h2 class="section-title">National average score</h2><p>{spark}</p>{axis}</section>'
    else:
        table = chart = ""
        lead = (
            "A national trend appears here once the corpus has been checked on more than one day."
        )

    # Top improvers section
    if improvers:
        imp_rows = "".join(
            f"<tr>"
            f'<td><a href="/agency/{esc(r["id"])}/">{esc(r["name"])}</a></td>'
            f"<td>{esc(r['score_start'])}</td>"
            f"<td>{esc(r['score_end'])}</td>"
            f"<td>+{esc(r['delta'])}</td>"
            f"</tr>"
            for r in improvers
        )
        improvers_section = (
            '<section class="feed-details" aria-labelledby="improvers-heading">'
            '<h2 id="improvers-heading" class="section-title">'
            "Agencies that improved most (last 90 days)</h2>"
            '<p class="fineprint">Feeds that moved up the most in this period, '
            "measured by overall score. Only agencies with at least three checks are "
            "included.</p>"
            '<table class="leaderboard">'
            "<thead><tr><th>Agency</th><th>Before</th><th>After</th>"
            "<th>Change</th></tr></thead>"
            f"<tbody>{imp_rows}</tbody>"
            "</table></section>"
        )
    else:
        improvers_section = ""

    return f"""<p class="page-lede">{lead}</p>
    {chart}
    <div class="section-grid">
    {table}
    {improvers_section}
    </div>
    <p class="fineprint">The series carries each agency's most recent score forward to each
    date and averages, so it is smooth even though agencies are checked on different days. It
    never changes a grade. The same data is at <a href="/api/v1/trend.json">the trend API
    (trend.json)</a>.</p>"""


def render_site(now: dt.datetime | None = None) -> list[Path]:
    """Generate all static pages, the sitemap, and robots.txt under web/.

    ``now`` is the instant used for wall-clock-relative prose (the liveness
    "checked N hours ago" note); it defaults to the real current time, but a
    caller (e.g. the golden-file test) can freeze it so output derived from
    ``_ago()`` is reproducible.
    """
    now = now or dt.datetime.now(dt.UTC)
    root = _repo_root()
    web = root / "web"
    art = artifacts_dir()
    # Empirical fix-effort bands, loaded once for the whole render. Empty when
    # the corpus has not yet written a calibration file, which keeps the band
    # purely additive (EXP-03).
    effort_bands = _load_effort_bands()
    written: list[Path] = []
    urls: list[str] = [
        f"{BASE_URL}/",
        f"{BASE_URL}/about/",
        f"{BASE_URL}/data/",
        f"{BASE_URL}/concept/",
        f"{BASE_URL}/submit.html",
        f"{BASE_URL}/try.html",
        f"{BASE_URL}/subscribe.html",
        f"{BASE_URL}/agencies/",
        f"{BASE_URL}/map/",
        f"{BASE_URL}/leaderboard/",
        f"{BASE_URL}/equity/",
    ]
    FIX_CODES_WITH_PAGES.clear()  # rebuilt below; never carry state across calls

    def write(rel: str, content: str, url: str | None = None) -> None:
        path = web / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        written.append(path)
        if url:
            urls.append(url)

    # Fix KB pages first, so agency findings can link to the ones that exist.
    fixes_dir = root / "docs" / "fixes"
    for md_file in sorted(fixes_dir.glob("*.md")):
        if md_file.stem == "README":
            continue
        FIX_CODES_WITH_PAGES.add(md_file.stem)
    for md_file in sorted(fixes_dir.glob("*.md")):
        if md_file.stem == "README":
            continue
        code = md_file.stem
        write(
            f"fix/{code}/index.html",
            _render_fix(code, md_file.read_text()),
            f"{BASE_URL}/fix/{code}/",
        )

    write("how-to-read/index.html", _render_guide(), f"{BASE_URL}/how-to-read/")
    write("accessibility/index.html", _render_accessibility(), f"{BASE_URL}/accessibility/")

    index_file = art / "index.json"
    index = json.loads(index_file.read_text()) if index_file.exists() else {"agencies": {}}
    # Per-agency score histories, keyed by id, for the small row sparklines on
    # the leaderboard-style tables (pulse rankings, NTD one-fix, realtime).
    histories: dict[str, list[dict[str, Any]]] = {
        str(aid): (entry or {}).get("history") or []
        for aid, entry in (index.get("agencies") or {}).items()
    }
    write("agencies/index.html", _render_agency_index(index))
    states = _states_by_agency()
    from .config import AGENCIES

    # Pass 1: read each agency once to build the catalog records the directory
    # needs (grade, score, state, size). Percentiles are cross-agency, so the
    # per-agency pages can't be rendered until every score is in.
    catalog: list[dict[str, Any]] = []
    ntd_artifacts: list[dict[str, Any]] = []
    problem_findings: list[list[dict[str, Any]]] = []
    for agency_id in sorted(index["agencies"]):
        latest = art / agency_id / "latest.json"
        if not latest.exists():
            continue
        # One unreadable artifact among ~1,200 agencies must not abort the whole
        # site render; warn (naming the file) and skip just that agency.
        try:
            artifact = json.loads(latest.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"::warning title=unreadable artifact::skipping {latest}: {exc}", file=sys.stderr)
            continue
        overall = artifact["overall"]
        fresh = artifact.get("categories", {}).get("freshness", {}).get("details", {})
        comp = artifact.get("categories", {}).get("completeness", {}).get("details", {})
        feed = artifact.get("feed", {})
        fixes = artifact.get("top_fixes", [])
        days = fresh.get("days_until_expiry")
        agency_cfg = AGENCIES.get(agency_id)
        # Artifacts don't persist state; inject it so the NTD portfolio's
        # per-state breakdown works at publish time.
        artifact.setdefault("agency", {})["state"] = states.get(agency_id, "")
        ntd_artifacts.append(artifact)
        problem_findings.append(agency_findings(artifact))
        catalog.append(
            {
                "id": agency_id,
                "name": artifact["agency"]["name"],
                "grade": overall["grade"],
                "score": overall["score"],
                "state": states.get(agency_id, ""),
                # ISO country code so consumers and the app can place non-US
                # agencies (Canada) instead of bucketing them as unlocated.
                "country": artifact.get("agency", {}).get("country", "US"),
                "stops": comp.get("stops"),
                "snapshot_date": artifact["snapshot_date"],
                "days_until_expiry": days,
                "expiry_status": expiry_status(days),
                # Readiness for the FTA NTD GTFS requirement (published/valid/
                # current), so a state program can filter its portfolio by who is
                # ready to certify without opening each scorecard. NTD is a
                # US-federal concept, so this is null for non-US feeds (ADR 0026):
                # the directory filter and national rollup never count them.
                "ntd_ready": (
                    ntd_assess(artifact).status
                    if artifact["agency"].get("country", "US") == "US"
                    else None
                ),
                # Whether the feed clears Google/Apple Maps' four-week coverage bar.
                "google_gate": google_from_artifact(artifact, dt.date.today()).status,
                "feed_url": feed.get("static_url"),
                "top_fix": fixes[0]["fix"] if fixes else None,
                "scorecard_url": f"{BASE_URL}/agency/{agency_id}/",
                # Identity: the Mobility Database id joins this row to the
                # canonical registry so a consumer never has to fuzzy-match a slug.
                "mdb_id": agency_cfg.mdb_id if agency_cfg else "",
                # Provenance: which validator and rubric produced this grade, when
                # it was generated, and the hash of the exact feed bytes scored, so
                # the grade is reproducible and citeable without opening the
                # per-agency artifact.
                "validator_version": artifact.get("validator_version"),
                "rubric_version": artifact.get("rubric_version"),
                "retrieved_at": artifact.get("generated_at"),
                "feed_sha256": feed.get("sha256"),
            }
        )

    # The directory dataset the national view reads: per-agency size tier and
    # percentile, plus the national and by-state summary. Built before the flat
    # catalog because it enriches each record in place (size_tier, percentiles),
    # which the catalog then carries too. Written alongside index.json under
    # data/artifacts so the web app reaches it through the same data base it uses
    # for index.json and per-agency artifacts, and so the existing
    # `git add data/artifacts` publishes it.
    directory = build_directory(catalog, dt.datetime.now(dt.UTC).isoformat(timespec="seconds"))
    (art / "directory.json").write_text(json.dumps(directory, indent=2, sort_keys=True) + "\n")
    by_id = {r["id"]: r for r in directory["agencies"]}

    # Daily change feed: agencies whose grade or score moved since their last
    # check, so a consumer ingests transitions instead of diffing the whole
    # catalog. Written under data/artifacts (served and committed like the rest)
    # as a stable changes/latest.json plus an immutable dated copy.
    from . import DATA_ATTRIBUTION, DATA_LICENSE, SCHEMA_VERSION

    changes = compute_changes(index)
    changes_payload = {
        "schema_version": SCHEMA_VERSION,
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "count": len(changes),
        "changes": changes,
    }
    changes_dir = art / "changes"
    changes_dir.mkdir(parents=True, exist_ok=True)
    changes_text = json.dumps(changes_payload, indent=2, sort_keys=True) + "\n"
    (changes_dir / "latest.json").write_text(changes_text)
    (changes_dir / f"{dt.date.today().isoformat()}.json").write_text(changes_text)
    # The human view of the movers lives on the national pulse page now; the
    # retired URL keeps working via a static redirect (no sitemap entry).
    write("changes/index.html", _redirect_page("/pulse/#changes", "What changed"))
    # The same movers as a static Atom feed, so a reader, a state liaison, or a
    # webhook can subscribe to grade drops without an opt-in store or an email
    # sender (the email digest covers confirmed subscribers; this covers everyone
    # else). Deterministic: timestamps come from snapshot dates, not wall-clock.
    write("changes/feed.xml", site_change_feed(changes, base_url=BASE_URL))

    # Machine-readable methodology (category weights, grade bands, correctness
    # deductions) so the grade is reproducible and contestable, not an opaque
    # opinion. Published alongside the artifacts.
    from .score import methodology

    (art / "scoring.json").write_text(json.dumps(methodology(), indent=2) + "\n")

    # Per-feed change-detection freshness from the intraday refresh, shown on each
    # page so a reader can see how current the monitoring is. Absent until the
    # refresh has run, in which case the note is simply omitted.
    liveness_state = _load_liveness()

    # Pass 2: render each agency page with its directory record, so the static
    # page shows the same peer line as the interactive view (crawlers and no-JS
    # visitors included). A second read is cheap next to scoring; an artifact
    # that failed to parse in pass 1 is simply absent from the catalog and skipped
    # here too.
    # The Canada CIMD served-area need tiers (ADR 0027), produced by the gated
    # `canada-equity` command, ride on a small committed file; inject each into its
    # agency artifact for the page, and re-publish the file to the API. Absent
    # (the command has not run) simply means Canadian pages show no tier.
    canada_equity: dict[str, Any] = {}
    ce_path = art / "canada-equity.json"
    if ce_path.exists():
        try:
            ce_doc = json.loads(ce_path.read_text())
            canada_equity = ce_doc.get("agencies", {})
            write("api/v1/canada-equity.json", json.dumps(ce_doc, indent=2, sort_keys=True) + "\n")
        except (json.JSONDecodeError, OSError):
            canada_equity = {}

    # Published rollup slugs, read once so each brief can link its state's
    # portfolio page only when that page will actually exist.
    program_ids: set[str] = set()
    rollup_index_file = art / "rollups" / "index.json"
    if rollup_index_file.exists():
        try:
            program_ids = {
                str(r.get("id", ""))
                for r in json.loads(rollup_index_file.read_text()).get("rollups", [])
            }
        except (json.JSONDecodeError, OSError):
            program_ids = set()

    map_features: list[dict[str, Any]] = []
    for agency_id in sorted(index["agencies"]):
        latest = art / agency_id / "latest.json"
        if not latest.exists() or agency_id not in by_id:
            continue
        try:
            artifact = json.loads(latest.read_text())
        except (json.JSONDecodeError, OSError):
            continue  # already warned in pass 1
        artifact["canada_equity"] = canada_equity.get(agency_id)
        feature = _map_feature(
            agency_id,
            artifact,
            by_id[agency_id].get("state", ""),
            artifact.get("agency", {}).get("country", ""),
        )
        if feature is not None:
            map_features.append(feature)
        history = index["agencies"][agency_id].get("history", [])
        # The previous dated snapshot lets the page show which findings cleared
        # since the last check; the newest dated file equals latest.json.
        dated = sorted((art / agency_id).glob("[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json"))
        prev_artifact = None
        if len(dated) >= 2:
            try:
                prev_artifact = json.loads(dated[-2].read_text())
            except (json.JSONDecodeError, OSError):
                prev_artifact = None
        # Stop names for the map's accessible equivalent come from the geometry
        # artifact (the map's own data), kept out of the per-day JSON to avoid
        # bloating it. Absent or unreadable geometry simply means no stop list.
        stop_names = _geometry_stop_names(art / agency_id / "geometry.geojson")
        receipts = load_fixlog(art / agency_id)
        write(
            f"agency/{agency_id}/index.html",
            _render_agency(
                artifact,
                history,
                prev_artifact,
                by_id[agency_id],
                liveness_state.get(agency_id),
                stop_names,
                has_fixlog=bool(receipts),
                now=now,
                effort_bands=effort_bands,
            ),
            f"{BASE_URL}/agency/{agency_id}/",
        )
        write(
            f"agency/{agency_id}/brief/index.html",
            _render_brief(
                artifact,
                history,
                prev_artifact,
                by_id[agency_id],
                liveness_state.get(agency_id),
                program_ids,
                effort_bands=effort_bands,
            ),
            f"{BASE_URL}/agency/{agency_id}/brief/",
        )
        # The board packet one-pager: same precomputed fields, different reader
        # (the agency's board rather than the liaison), so progress leads and the
        # fixes read as the asks (docs/RESEARCH-ROADMAP.md E6).
        write(
            f"agency/{agency_id}/board/index.html",
            _render_board_page(
                artifact, history, prev_artifact, by_id[agency_id], effort_bands=effort_bands
            ),
            f"{BASE_URL}/agency/{agency_id}/board/",
        )
        # The durable fix log, only once the collect step has recorded at least
        # one receipt (fixlog.py); a feed with no cleared findings has no page
        # rather than an empty shell.
        if receipts:
            write(
                f"agency/{agency_id}/fixes/index.html",
                _render_fixlog_page(artifact, receipts),
                f"{BASE_URL}/agency/{agency_id}/fixes/",
            )
        # This feed's own Atom history (grade moves, expiry crossings, score
        # swings), so anyone supporting the agency can subscribe to just it. The
        # events are the same ones the "What changed over time" timeline shows.
        write(
            f"agency/{agency_id}/feed.xml",
            agency_change_feed(
                agency_id,
                artifact["agency"]["name"],
                history_events(history),
                base_url=BASE_URL,
            ),
        )

    # A flat machine-readable catalog so a consumer gets every agency's grade and
    # feed URL in one request instead of fetching every artifact.
    _write_catalog(write, catalog)

    # The open national quality dataset (one row per agency, latest score) plus a
    # CSV, so researchers and state programs can download and analyze it directly.
    from .dataset import build_quality_dataset, to_csv

    dataset = build_quality_dataset(index)
    write("dataset.json", json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    write("dataset.csv", to_csv(dataset))

    # NTD certification-readiness portfolio (national + per state), so a program
    # lead can see "% ready to certify" without opening each scorecard.
    from .ntd import one_fix_from_ready, portfolio_summary

    # portfolio_summary excludes non-US feeds itself (NTD is US-federal); the full
    # ntd_artifacts list still feeds the GTFS-quality rollups below. See ADR 0026.
    summary = portfolio_summary(ntd_artifacts)
    one_fix = one_fix_from_ready(ntd_artifacts)
    ntd_payload = {
        "total": summary.total,
        "ready": summary.ready,
        "at_risk": summary.at_risk,
        "not_ready": summary.not_ready,
        "pct_ready": summary.pct_ready,
        "by_state": summary.by_state,
        # Additive: the report-year-2026 triage list (reduced, rural, and tribal
        # reporters join the GTFS requirement in RY2026). Capped so the JSON
        # stays small; the count is the real total.
        "one_fix_from_ready": one_fix[:40],
        "one_fix_total": len(one_fix),
    }
    write("ntd.json", json.dumps(ntd_payload, indent=2, sort_keys=True) + "\n")
    # The human page over the same readiness numbers, for an FTA or state-DOT lead.
    write("ntd/index.html", _render_ntd_page(ntd_payload, histories), f"{BASE_URL}/ntd/")

    # National accessibility-data coverage (how many feeds let a wheelchair user
    # plan a trip at all), for advocates and the programs that support them. Built
    # from the same artifacts already read, published as an API endpoint and a page.
    from .access import coverage_record, national_coverage

    coverage_records = [rec for art in ntd_artifacts if (rec := coverage_record(art)) is not None]
    coverage = national_coverage(coverage_records)
    write(
        "api/v1/accessibility.json",
        json.dumps(
            {
                "license": DATA_LICENSE,
                "attribution": DATA_ATTRIBUTION,
                "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                **coverage,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    # Accessibility coverage lives on the What-feeds-publish page now.
    write("access/index.html", _redirect_page("/adoption/#access", "Accessibility data coverage"))

    # National adoption of the newer GTFS capabilities (flexible service, fare
    # data and Fares v2, station pathways), read from the same per-agency detail
    # completeness already records. Published as an API endpoint and a page.
    from .adoption import adoption_record, national_adoption

    adoption_records = [rec for art in ntd_artifacts if (rec := adoption_record(art)) is not None]
    adoption_national = national_adoption(adoption_records)
    write(
        "api/v1/adoption.json",
        json.dumps(
            {
                "license": DATA_LICENSE,
                "attribution": DATA_ATTRIBUTION,
                "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                **adoption_national,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    write(
        "adoption/index.html",
        _render_adoption_page(adoption_national, coverage),
        f"{BASE_URL}/adoption/",
    )

    # A copy-paste procurement page so an agency can require feed quality in a
    # vendor contract or RFP, not only catch problems after publication.
    write("procurement/index.html", _render_procurement(), f"{BASE_URL}/procurement/")
    write("press/index.html", _render_press_page(), f"{BASE_URL}/press/")

    # National realtime reliability, for a data team or state program. Built from
    # the uptime/lag samples the realtime monitor already records in data/rt-health
    # (ADR 0012), so it stays serverless and adds no polling. Names come from the
    # registry/index; state from the same map the directory uses.
    from .rt_health import load_observations, state_path, summarize
    from .rt_national import national_rt

    rt_summaries: list[dict[str, Any]] = []
    rt_dir = state_path("_probe").parent
    if rt_dir.exists():
        for hf in sorted(rt_dir.glob("*.json")):
            rt_id = hf.stem
            health = summarize(load_observations(rt_id))
            if health.observations == 0:
                continue
            cfg = AGENCIES.get(rt_id)
            name = cfg.name if cfg else index["agencies"].get(rt_id, {}).get("name", rt_id)
            rt_summaries.append(
                {"id": rt_id, "name": name, "state": states.get(rt_id, ""), **health.to_dict()}
            )
    rt_rollup = national_rt(rt_summaries)
    write(
        "api/v1/realtime.json",
        json.dumps(
            {
                "license": DATA_LICENSE,
                "attribution": DATA_ATTRIBUTION,
                "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                **rt_rollup,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    write("realtime/index.html", _render_rt_page(rt_rollup, histories), f"{BASE_URL}/realtime/")

    # National "most common problems" knowledge base, for practitioners and the
    # press. Aggregated from the findings read in pass 1, so it adds no per-agency
    # work. total_agencies is the scored count, so prevalence is a share of feeds.
    from .findings_national import national_problems

    problems = national_problems(problem_findings, total_agencies=len(catalog))
    write(
        "api/v1/problems.json",
        json.dumps(
            {
                "license": DATA_LICENSE,
                "attribution": DATA_ATTRIBUTION,
                "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                **problems,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    write("problems/index.html", _render_problems_page(problems), f"{BASE_URL}/problems/")

    # National quality trend over time, derived from the per-agency histories in
    # the index (no new stored state), for the "is transit data getting better?"
    # question. Pure and reproducible.
    from .national_trend import as_of_points, top_improvers, trend_summary

    trend_points = as_of_points(index)
    trend_sum = trend_summary(trend_points)
    improvers = top_improvers(index)
    write(
        "api/v1/trend.json",
        json.dumps(
            {
                "license": DATA_LICENSE,
                "attribution": DATA_ATTRIBUTION,
                "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "summary": trend_sum,
                "points": trend_points,
                "top_improvers": improvers,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    write("trends/index.html", _redirect_page("/pulse/#trend", "The national trend"))

    # National map: a single small GeoJSON of every located agency as a point
    # coloured by grade, rendered client-side (no tile server). Agencies whose
    # feed has no located stops carry no geometry and are simply absent.
    geojson = {
        "type": "FeatureCollection",
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "features": map_features,
    }
    write("map.geojson", json.dumps(geojson, sort_keys=True) + "\n")
    write("map/index.html", _render_map_page(map_features), f"{BASE_URL}/map/")

    # Side-by-side compare: one static page over the artifacts that already
    # exist; the two pickers come from the same catalog the directory uses.
    write("compare/index.html", _render_compare_page(catalog), f"{BASE_URL}/compare/")

    # In-browser SQL over the published parquet: the static-first principle
    # applied to analytics (no backend, nothing sent to a server).
    write("query/index.html", _render_query_page(), f"{BASE_URL}/query/")

    # The tools index the primary nav points at: every self-serve tool, one line
    # each, so discovery never depends on the footer.
    write("tools/index.html", _render_tools_page(), f"{BASE_URL}/tools/")

    # Pre-publish check: reads a GTFS zip client-side at the moment of export,
    # before it is published anywhere. No upload, no backend.
    write("check/index.html", _render_check_page(), f"{BASE_URL}/check/")

    # National all-routes map: every agency's route shapes on one canvas, read
    # from a committed PMTiles archive (ADR 0023). The archive itself is built
    # out-of-band by scripts/build_national_pmtiles.py (tippecanoe is not in the
    # daily image); here we only aggregate the route counts for the page copy, so
    # the page renders even when the archive predates the latest geometry.
    from .national_routes import build_national_routes

    route_grades = {
        c["id"]: {"name": str(c.get("name", c["id"])), "grade": str(c.get("grade", "?"))}
        for c in catalog
    }
    national_routes = build_national_routes(art, route_grades)
    write(
        "routes/index.html",
        _render_routes_page(national_routes.summary),
        f"{BASE_URL}/routes/",
    )

    # Versioned static public API: cross-agency endpoints (list, leaderboard, per
    # state, national stats) served as flat JSON from object storage, no query
    # server (ADR 0013). Per-agency detail stays the published artifact.
    from .publicapi import build_api, leaderboard

    api = build_api(
        index,
        states=states,
        base_url=BASE_URL,
        generated_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    )
    for name, payload in api.items():
        write(f"api/v1/{name}", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    # Identity crosswalk: the scorecard slug joined to the Mobility Database id
    # and NTD id it already carries, so a consumer can join grades to either
    # registry (or to FTA data) without fuzzy matching. Ecosystem citizenship:
    # the Transitland Atlas invites exactly this kind of crosswalk use.
    write(
        "api/v1/ids.json",
        json.dumps(
            {
                "license": DATA_LICENSE,
                "attribution": DATA_ATTRIBUTION,
                "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "agencies": [
                    {
                        "id": c["id"],
                        "name": c["name"],
                        "mdb_id": c.get("mdb_id") or None,
                        "ntd_id": (AGENCIES[c["id"]].ntd_id or None)
                        if c["id"] in AGENCIES
                        else None,
                        "feed_url": c.get("feed_url"),
                    }
                    for c in catalog
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    # Rider-trips impact (ADR 0021): when the NTD ridership snapshot is present
    # (the daily run fetches it via `scorecard ntd-ridership --fetch`), weight
    # quality by annual unlinked passenger trips and publish the national
    # numbers. National framing only: trips on expired feeds, never a ranking.
    ridership_impact: dict[str, Any] | None = None
    ridership_csv = root / "data" / "ntd-ridership.csv"
    if ridership_csv.exists():
        from .ridership import parse_ridership_csv, weighted_impact

        rid = parse_ridership_csv(ridership_csv.read_text())
        rid_records = []
        for a in ntd_artifacts:
            cfg = AGENCIES.get(str(a.get("agency", {}).get("id", "")))
            days = (a.get("categories", {}).get("freshness", {}).get("details", {})).get(
                "days_until_expiry"
            )
            rid_records.append(
                {
                    "ntd_id": cfg.ntd_id if cfg else "",
                    "score": a.get("overall", {}).get("score"),
                    "grade": a.get("overall", {}).get("grade"),
                    "expiry_status": expiry_status(days),
                }
            )
        ridership_impact = weighted_impact(rid_records, rid)
        write(
            "api/v1/ridership-impact.json",
            json.dumps(
                {
                    "license": DATA_LICENSE,
                    "attribution": DATA_ATTRIBUTION,
                    "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                    "source": "FTA NTD annual metrics (data.transportation.gov, g27i-aq2u)",
                    **ridership_impact,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    # The national pulse: rankings, movers, and the trend on one page; the three
    # retired URLs redirect to their anchors so old links keep working.
    board = leaderboard(index, build_quality_dataset(index))
    write(
        "pulse/index.html",
        _render_pulse_page(
            board, changes, trend_points, trend_sum, improvers, ridership_impact, histories
        ),
        f"{BASE_URL}/pulse/",
    )
    write("leaderboard/index.html", _redirect_page("/pulse/#rankings", "Rankings"))

    # The focus-areas hub the primary nav points at.
    write(
        "focus/index.html",
        _render_focus_page(ntd_payload, rt_rollup),
        f"{BASE_URL}/focus/",
    )
    # The same national table as Parquet, so a DuckDB or Athena consumer can query
    # it directly (ADR 0013). Best-effort: skipped when the query extra is absent,
    # so the core render never depends on DuckDB.
    from .warehouse import duckdb_available, to_parquet

    if duckdb_available():
        to_parquet(
            build_quality_dataset(index)["rows"], str(web / "api" / "v1" / "agencies.parquet")
        )
        written.append(web / "api" / "v1" / "agencies.parquet")

    # The equity overlay page reads the published overlay (the equity workflow's
    # ACS join, refreshed on its own schedule); a neutral note shows until then.
    try:
        overlay = json.loads((web / "api" / "v1" / "equity.json").read_text())
    except (OSError, ValueError):
        overlay = {}
    # Committed, public-domain simplified state geometry for the equity
    # choropleth (ADR 0022). Absent or unreadable just omits the map; the tables
    # remain the conformant primary.
    try:
        states_geo = json.loads((web / "us-states.json").read_text())
    except (OSError, ValueError):
        states_geo = {}
    write(
        "equity/index.html",
        _render_equity_page(overlay, states_geo),
        f"{BASE_URL}/equity/",
    )

    rollup_index = art / "rollups" / "index.json"
    if rollup_index.exists():
        for r in json.loads(rollup_index.read_text()).get("rollups", []):
            rfile = art / "rollups" / f"{r['id']}.json"
            if rfile.exists():
                write(
                    f"program/{r['id']}/index.html",
                    _render_rollup(json.loads(rfile.read_text())),
                    f"{BASE_URL}/program/{r['id']}/",
                )

    write("sitemap.xml", _sitemap(urls))
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

    # Manifest of the top-level web/ roots this render actually wrote, so the
    # publish workflows can `git add` exactly what render-site produced instead of
    # a hand-typed path list that silently drifts (a missing root broke a publish
    # once). build/ is gitignored: the file is regenerated every run, never
    # committed, and lists only generated paths (hand-authored web/src, the static
    # *.html, web/app, and web/tiles are never written here, so stay excluded).
    roots = sorted({f"web/{p.relative_to(web).parts[0]}" for p in written})
    manifest = root / "build" / "render-manifest.txt"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("\n".join(roots) + "\n")
    return written
