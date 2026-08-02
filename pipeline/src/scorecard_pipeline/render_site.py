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
import hashlib
import html as html_lib
import io
import json
import math
import re
import shutil
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import yaml
from markdown_it import MarkdownIt
from yaml.nodes import MappingNode, ScalarNode

from ._stats import _GRADES
from .anomaly import latest_anomaly
from .atomfeed import agency_change_feed, site_change_feed
from .comparisons import (
    current_producer_contract_suffix,
    reader_archive_profile,
    same_producer_contract,
)
from .config import Agency, artifacts_dir
from .conformance import assess as conformance_assess
from .constants_export import GRADE_RANK
from .directory import build_directory
from .feeddiff import FeedDiff, diff_artifacts
from .findings_national import agency_findings, plain_language_coverage
from .fixlog import load_fixlog
from .google_gate import from_artifact as google_from_artifact
from .i18n import (
    APP_CATALOG_LOCALES,
    CATALOG_DIR,
    PSEUDOLOCALE,
    SUPPORTED_LOCALES,
    load_app_catalog,
    load_catalog,
    validate_catalogs,
)
from .identity import normalized_mdb_id, resolve_published_agency_name
from .instance import ORG_NAME
from .jurisdiction_guidance import guidance_for
from .location import country_name, resolve_published_location
from .metrics import (
    expiry_status,
    operating_signal,
    presented_freshness_summary,
    resolve_service_horizon_status,
)
from .mobilitydb import canonical_state
from .ntd import assess as ntd_assess
from .ntd import presented_readiness as presented_ntd_readiness
from .pages_tools import (
    _render_check_page,
    _render_compare_page,
    _render_query_page,
    _render_tools_page,
)
from .rule_links import (
    BEST_PRACTICE,
    REALTIME_REFERENCE,
    REFERENCE,
    RULE_LINKS,
    RuleLink,
    rule_link_for,
)
from .score import letter_grade
from .site_shell import (  # noqa: F401  (re-exported: the site's shared shell)
    _SOCIAL_IMAGE_HEIGHT,
    _SOCIAL_IMAGE_URL,
    _SOCIAL_IMAGE_WIDTH,
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
from .timemachine import finding_codes as _finding_codes
from .timemachine import grade_story, history_events
from .tool_profiles import detect_tool

FIX_CODES_WITH_PAGES: set[str] = set()  # filled in by render_fixes()


def _strip_blank_line_whitespace(markup: str) -> str:
    """Keep optional template fragments from leaving whitespace-only lines."""
    return re.sub(r"(?m)^[ \t]+$", "", markup)


def _finding_severity_badge(value: object) -> str:
    """Render an artifact severity from fixed labels and CSS classes only."""
    key = str(value or "").upper()
    if key == "ERROR":
        class_name, label = "sev-error", SEVERITY_LABELS["ERROR"]
    elif key == "WARNING":
        class_name, label = "sev-warning", SEVERITY_LABELS["WARNING"]
    else:
        class_name, label = "sev-info", SEVERITY_LABELS["INFO"]
    return f'<span class="sev {class_name}">{esc(label)}</span>'


# Non-validator RuleLink.kind -> the phrase naming that authority, for the
# "Finding code" line's visually-hidden context. A dict, not an if/elif
# chain, so a kind added to rule_links.py without an entry here raises a
# KeyError instead of silently falling through to the wrong authority name
# (exactly the kind of drift ADR 0024 exists to prevent).
_NON_VALIDATOR_WHERE = {
    BEST_PRACTICE: "GTFS Best Practices",
    REFERENCE: "the GTFS Schedule reference",
    REALTIME_REFERENCE: "the GTFS-Realtime reference",
}


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


_SAFE_FINDING_CODE = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_AGENCY_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_finding_code(value: object) -> str:
    code = str(value or "")
    return code if _SAFE_FINDING_CODE.fullmatch(code) else ""


def _finding_card_attrs(fix: dict[str, Any]) -> str:
    code = _safe_finding_code(fix.get("code"))
    if not code:
        return ""
    return f' id="finding-{esc(code)}" data-finding-card="{esc(code)}"'


def _finding_url(
    path: str,
    code: str,
    *,
    agency_id: str | None = None,
    anchor: str = "finding-handoff",
) -> str:
    """Attach one validated finding to a route without accepting arbitrary URLs."""
    safe_code = _safe_finding_code(code)
    if not safe_code:
        return path
    query = {"finding": safe_code}
    if agency_id and _SAFE_AGENCY_ID.fullmatch(agency_id):
        query["agency"] = agency_id
    fragment = f"#{anchor}" if anchor else ""
    return f"{path}?{urlencode(query)}{fragment}"


_FINDING_CONTEXT_SCRIPT = """<script>
(function () {
  "use strict";
  var safeCode = /^[A-Za-z0-9_-]+$/;
  var safeAgency = /^[A-Za-z0-9_-]+$/;
  var params = new URL(window.location.href).searchParams;
  var requested = params.get("finding") || "";
  if (!safeCode.test(requested)) requested = "";

  document.querySelectorAll("[data-finding-handoff]").forEach(function (handoff) {
    var panels = Array.from(handoff.querySelectorAll("[data-finding-panel]"));
    if (!panels.length) return;
    var selected = panels.some(function (panel) {
      return panel.getAttribute("data-finding-panel") === requested;
    }) ? requested : panels[0].getAttribute("data-finding-panel");
    panels.forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-finding-panel") !== selected;
    });
    handoff.querySelectorAll("[data-finding-choice]").forEach(function (choice) {
      if (choice.getAttribute("data-finding-choice") === selected) {
        choice.setAttribute("aria-current", "true");
      } else {
        choice.removeAttribute("aria-current");
      }
    });
    document.querySelectorAll("[data-finding-card]").forEach(function (card) {
      card.classList.toggle(
        "finding-selected",
        card.getAttribute("data-finding-card") === selected
      );
    });
  });

  document.querySelectorAll("[data-handoff-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var panel = button.closest("[data-finding-panel]");
      var field = panel && panel.querySelector("textarea");
      var status = panel && panel.querySelector("[data-copy-status]");
      if (!field) return;
      var copied = navigator.clipboard && window.isSecureContext
        ? navigator.clipboard.writeText(field.value)
        : Promise.reject();
      copied.catch(function () {
        field.focus();
        field.select();
        document.execCommand("copy");
      }).then(function () {
        if (status) status.textContent = "Copied.";
      });
    });
  });

  document.querySelectorAll("[data-fix-context]").forEach(function (context) {
    var agency = params.get("agency") || "";
    var code = context.getAttribute("data-fix-context") || "";
    if (!safeAgency.test(agency) || !safeCode.test(code)) return;
    context.hidden = false;
    var agencyLabel = context.querySelector("[data-context-agency]");
    if (agencyLabel) agencyLabel.textContent = agency;
    var base = "/agency/" + encodeURIComponent(agency) + "/";
    var finding = "?finding=" + encodeURIComponent(code);
    context.querySelectorAll("[data-context-target]").forEach(function (link) {
      var target = link.getAttribute("data-context-target");
      if (target === "scorecard") link.href = base + finding + "#finding-handoff";
      if (target === "brief") link.href = base + "brief/" + finding + "#finding-handoff";
      if (target === "board") link.href = base + "board/" + finding + "#finding-handoff";
      if (target === "history") link.href = base + finding + "#trend-h";
    });
  });
}());
</script>"""


def _finding_handoff(
    artifact: dict[str, Any],
    agency_id: str,
    surface_path: str,
) -> str:
    """Render one operational handoff whose selection survives across surfaces.

    The artifact remains the source of every statement. The handoff does not
    claim who owns the change and does not create a ticket or workflow state.
    """
    agency_name = str(artifact.get("agency", {}).get("name") or agency_id)
    fixes = [
        fix for fix in artifact.get("top_fixes", [])[:3] if _safe_finding_code(fix.get("code"))
    ]
    if not fixes:
        return ""

    choices: list[str] = []
    panels: list[str] = []
    for index, fix in enumerate(fixes, start=1):
        code = _safe_finding_code(fix.get("code"))
        choice_href = _finding_url(surface_path, code)
        choices.append(
            f'<a href="{esc(choice_href)}" data-finding-choice="{esc(code)}">'
            f"<span>0{index}</span> {esc(code)}</a>"
        )
        evidence_url = _finding_url(
            f"{BASE_URL}/agency/{agency_id}/",
            code,
        )
        recheck = (
            "Publish the changed feed at the same URL. On the next complete, comparable "
            "scorecard run, confirm that this finding is no longer reported."
        )
        handoff_text = (
            f"Agency: {agency_name}\n"
            f"Finding: {code}\n"
            f"Feed evidence: {fix.get('what', '')}\n"
            f"Why it matters: {fix.get('why', '')}\n"
            f"Requested change: {fix.get('fix', '')}\n"
            f"Recheck: {recheck}\n"
            f"Evidence: {evidence_url}"
        )
        guide_link = (
            f'<a href="{esc(_finding_url(f"/fix/{code}/", code, agency_id=agency_id))}">'
            "Open fix guide</a>"
            if code in FIX_CODES_WITH_PAGES
            else ""
        )
        surface_links = [
            guide_link,
            f'<a href="{esc(_finding_url(f"/agency/{agency_id}/brief/", code))}">Call brief</a>',
            f'<a href="{esc(_finding_url(f"/agency/{agency_id}/board/", code))}">Board view</a>',
            f'<a href="{esc(_finding_url(f"/agency/{agency_id}/", code, anchor="trend-h"))}">Feed history</a>',
        ]
        panels.append(
            f'<div class="handoff-panel" data-finding-panel="{esc(code)}"'
            f"{' hidden' if index > 1 else ''}>"
            '<dl class="handoff-grid">'
            f"<div><dt>Feed evidence</dt><dd>{esc(fix.get('what', ''))}</dd></div>"
            f"<div><dt>Next action</dt><dd>{esc(fix.get('fix', ''))}</dd></div>"
            f"<div><dt>Recheck</dt><dd>{esc(recheck)}</dd></div>"
            "</dl>"
            f'<nav class="handoff-links" aria-label="Finding {esc(code)} links">'
            f"{''.join(link for link in surface_links if link)}</nav>"
            '<details class="handoff-copy">'
            "<summary>Copy handoff text</summary>"
            f'<textarea readonly rows="8" aria-label="Handoff text for {esc(code)}">{esc(handoff_text)}</textarea>'
            '<div class="handoff-copy-actions"><button type="button" class="copy-btn" '
            "data-handoff-copy>Copy handoff</button>"
            '<span class="copy-status" data-copy-status aria-live="polite"></span></div>'
            "</details></div>"
        )

    return (
        '<section class="finding-handoff" id="finding-handoff" '
        'data-finding-handoff aria-labelledby="finding-handoff-h">'
        '<div class="handoff-head"><div>'
        '<p class="handoff-kicker">Finding handoff</p>'
        '<h2 id="finding-handoff-h">Move one finding to a recheck</h2></div>'
        "<p>Select one finding. Copy the request, make the change in the "
        "feed-producing tool, then compare the next complete run.</p></div>"
        '<nav class="finding-picker" aria-label="Select a prioritized finding">'
        f"{''.join(choices)}</nav>{''.join(panels)}</section>{_FINDING_CONTEXT_SCRIPT}"
    )


def _rule_ref_link(code: str) -> str:
    """Inline link to a finding's authoritative rule, for the 'Finding code'
    line on agency findings. Links the canonical gtfs-validator notice (or the
    relevant GTFS Best Practice / reference) so the Cal-ITP / state-DOT reader
    lands on the canonical rule used across validator reports. Empty when no
    honest mapping exists (some scorecard-only completeness checks)."""
    link = rule_link_for(code)
    if link is None:
        return ""
    where = "the validator rules" if link.is_validator else _NON_VALIDATOR_WHERE[link.kind]
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
                f"GTFS Validator notice <code>{esc(notice)}</code>, so the finding "
                f"can be checked against the ecosystem's shared rule text."
            )
        else:
            lead = (
                f"<code>{esc(code)}</code> is a canonical MobilityData GTFS "
                f"Validator notice used in validator reports across the GTFS ecosystem."
            )
        link_text = f"Read the authoritative rule for {notice} in the GTFS Validator rules"
    elif link.kind == BEST_PRACTICE:
        if code in {"scorecard_feed_expired", "scorecard_feed_expiring_soon"}:
            lead = (
                "This scorecard finding combines feed_info and calendar service "
                "dates to estimate when riders lose trip-planning coverage. The "
                "GTFS Validator has related expiry notices, but no single validator "
                "rule uses this exact combined calculation, so the operational "
                "expectation comes from the community GTFS Best Practices."
            )
        else:
            lead = (
                "The GTFS Validator does not flag this, so the expectation comes "
                "from the community GTFS Best Practices."
            )
        link_text = "Read the relevant GTFS Best Practice"
    elif link.kind == REALTIME_REFERENCE:
        lead = (
            "This scorecard finding concerns GTFS-Realtime, while the MobilityData "
            "GTFS Validator validates GTFS Schedule. The linked GTFS-Realtime "
            "reference defines the message this scorecard checks."
        )
        link_text = "Read the relevant GTFS-Realtime reference section"
    else:  # reference
        lead = (
            "The linked GTFS Schedule reference defines the field or data this "
            "scorecard finding checks."
        )
        link_text = "Read the relevant GTFS Schedule reference section"
    return (
        '\n<h2 class="section-title">Authoritative rule</h2>'
        f"\n<p>{lead} "
        f'<a class="rule-ref" href="{esc(link.url)}">{esc(link_text)}</a>.'
        '<span class="visually-hidden"> (opens on an external site)</span></p>'
    )


def _cleared_findings(prev: dict[str, Any] | None, cur: dict[str, Any]) -> list[tuple[str, str]]:
    """Findings present in one comparable check but absent from the next.

    Returns ``(code, what)`` pairs, where ``what`` is the earlier check's
    description. Absence establishes later feed state, not who changed it or
    why.
    """
    if not prev or not same_producer_contract(prev, cur):
        return []
    current = _finding_codes(cur)
    return [(code, what) for code, what in _finding_codes(prev).items() if code not in current]


def _previous_indexed_artifact(
    agency_id: str,
    history: list[dict[str, Any]],
    dated_artifacts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the exact prior indexed snapshot when it is locally hydrated.

    A bounded Pages checkout can contain old cutover artifacts plus the current
    record without containing the immediately preceding record. Treating the
    second-to-last local file as "previous" would then compare non-adjacent
    checks and could claim a finding cleared in the wrong interval.
    """
    if len(history) < 2:
        return None
    indexed_previous = history[-2]
    previous_date = str(indexed_previous.get("date") or "")
    if not previous_date:
        return None
    from .publish import _history_entry

    for artifact in reversed(dated_artifacts):
        try:
            if str(artifact.get("snapshot_date") or "") != previous_date:
                continue
            if str(artifact.get("agency", {}).get("id") or "") != agency_id:
                continue
            candidate_summary = _history_entry(artifact)
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if any(candidate_summary.get(field) != value for field, value in indexed_previous.items()):
            continue
        return artifact
    return None


def _history_section(
    history: list[dict[str, Any]] | None,
    artifacts: list[dict[str, Any]] | None = None,
) -> str:
    """A plain-language timeline of what changed across this feed's history, the
    text companion to the trend chart (and the screen-reader-friendly version of
    it). Leads with a short deterministic "grade story" paragraph — a few dated
    sentences tracing how the current grade came to be, composed from the dated
    artifacts (``artifacts``, oldest first) so cleared findings are named too.
    Empty when the feed has been steady."""
    comparable_history = _current_rubric_history(history or [])
    events = history_events(comparable_history)
    if not events:
        return ""
    comparable_artifacts = current_producer_contract_suffix(artifacts or [])
    story = grade_story(comparable_history, comparable_artifacts)
    story_html = f'<p class="grade-story">{" ".join(esc(s) for s in story)}</p>' if story else ""
    items = "".join(
        f'<li class="event"><span class="event-date">{esc(e.date)}</span> {esc(e.detail)}</li>'
        for e in events[:12]
    )
    return (
        '<section aria-labelledby="history-h"><h2 class="section-title" id="history-h">'
        "What changed over time</h2>"
        f"{story_html}"
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
    comparable = _current_rubric_history(history or [])
    points = [
        (str(p.get("date", "")), p["score"])
        for p in comparable
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


def _current_rubric_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The contiguous history suffix produced by one complete contract.

    Rubric, scoring profile, validator, and measured categories must all match.
    Missing provenance restarts the trend at the latest point.
    """
    return current_producer_contract_suffix(history)


def _service_bar_chart(
    rows: list[tuple[str, float, str]],
    *,
    title: str,
    note: str,
    css_class: str = "",
) -> str:
    """Direct-labelled horizontal percentage bars for ranked comparisons.

    The list is the chart and its text equivalent: every label, exact percentage,
    and supporting count stays visible in semantic HTML. The track is decorative
    and starts with a stop marker, borrowing the visual language of a transit
    route without asking color to carry meaning. Values are clamped to the
    zero-based 0–100 scale used by every caller.
    """
    if not rows:
        return ""
    items = []
    for label, raw_value, detail in rows:
        value = max(0.0, min(100.0, float(raw_value)))
        shown = f"{value:g}%"
        items.append(
            f'<li class="service-bar" style="--value:{value:g}">'
            '<div class="service-bar-head">'
            f'<span class="service-bar-label">{esc(label)}</span>'
            f'<span class="service-bar-value">{shown}'
            f'<span class="service-bar-detail">{esc(detail)}</span></span></div>'
            '<div class="service-track" aria-hidden="true">'
            '<span class="service-fill"></span><span class="service-stop"></span></div></li>'
        )
    extra = f" {css_class}" if css_class else ""
    return (
        f'<figure class="service-chart{extra}"><figcaption>'
        f'<span class="service-chart-title">{esc(title)}</span>'
        f'<span class="service-chart-note">{esc(note)}</span></figcaption>'
        f'<ol class="service-bars">{"".join(items)}</ol>'
        '<div class="service-scale" aria-hidden="true"><span>0%</span><span>100%</span></div>'
        "</figure>"
    )


def _bucket_chart(
    rows: list[tuple[str, int]],
    *,
    title: str,
    note: str,
    css_class: str = "",
    accessible_unit: str | None = None,
) -> str:
    """Ordered count buckets as zero-based columns with visible exact values.

    This is for distributions whose order matters (age ranges), not ranked
    categories. Equal-width buckets are deliberately presented as named bands,
    not as a continuous time axis, because their underlying ranges differ.
    """
    if not rows:
        return ""
    maximum = max((count for _, count in rows), default=0)
    items = []
    for label, count in rows:
        height = round((count / maximum) * 100, 1) if maximum else 0
        aria_label = ""
        aria_hidden = ""
        if accessible_unit:
            unit = accessible_unit if count == 1 else f"{accessible_unit}s"
            aria_label = f' aria-label="{esc(f"{count} {unit}, {label}")}"'
            aria_hidden = ' aria-hidden="true"'
        items.append(
            f'<li class="bucket-bar" style="--height:{height:g}"{aria_label}>'
            f'<span class="bucket-value"{aria_hidden}>{count}</span>'
            '<span class="bucket-column" aria-hidden="true"><span></span></span>'
            f'<span class="bucket-label"{aria_hidden}>{esc(label)}</span></li>'
        )
    extra = f" {css_class}" if css_class else ""
    return (
        f'<figure class="bucket-chart{extra}" style="--bins:{len(rows)}"><figcaption>'
        f'<span class="service-chart-title">{esc(title)}</span>'
        f'<span class="service-chart-note">{esc(note)}</span></figcaption>'
        f'<ol class="bucket-bars">{"".join(items)}</ol></figure>'
    )


def _movement_balance(changes: list[dict[str, Any]]) -> str:
    """Part-to-whole summary of agencies with a material latest change.

    The band covers only the significant changes returned by ``compute_changes``;
    the note says so explicitly to avoid implying that quiet agencies were
    measured as unchanged in this view.
    """
    improved = sum(not bool(c.get("regressed")) for c in changes)
    declined = sum(bool(c.get("regressed")) for c in changes)
    total = improved + declined
    if not total:
        return '<p class="page-lede">No material score or grade changes were detected.</p>'
    return (
        '<figure class="movement-chart"><figcaption>'
        '<span class="service-chart-title">Direction of material changes</span>'
        '<span class="service-chart-note">Feed scorecards shown in the change lists below.</span>'
        "</figcaption>"
        '<ul class="movement-counts">'
        f'<li class="movement-up"><strong>{improved}</strong> improved</li>'
        f'<li class="movement-down"><strong>{declined}</strong> slipped</li></ul>'
        '<div class="movement-band" aria-hidden="true">'
        f'<span class="movement-up" style="--share:{improved}"></span>'
        f'<span class="movement-down" style="--share:{declined}"></span></div>'
        '<p class="movement-note">This summarizes significant movers, not every quiet feed.</p>'
        "</figure>"
    )


def _trend_section(history: list[dict[str, Any]]) -> str:
    """An 'Over time' block: an overall-score line plus per-category change since
    the previous check. Mirrors the interactive app so static and SPA agree. The
    finding-level change (what cleared or newly appeared) lives in the feed-diff
    section below, so it is not repeated here."""
    comparable = _current_rubric_history(history)
    if len(comparable) < 2:
        lead = (
            "The producer or measurement contract changed since the prior check, so the trend "
            "restarts here. No improvement or regression is claimed across that boundary."
            if len(history) >= 2
            else 'This is the first scorecard for this agency. A trend and a "what changed" '
            "summary appear here once it has been checked more than once."
        )
        return (
            '<section aria-labelledby="trend-h"><h2 class="section-title" id="trend-h">Over time</h2>'
            f'<p class="page-lede">{lead}</p></section>'
        )
    history = comparable
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
        count = c.curr_count or 0
        noun = "instance" if count == 1 else "instances"
        items.append(
            f'<li class="finding"><div class="finding-head">'
            f"{_finding_severity_badge(c.severity)}"
            f'<span class="count">{count} {noun}</span></div>'
            f'<p class="what">{esc(c.what)}</p>'
            f'<p class="code">Finding code: {esc(c.code)}{_fix_guide_link(str(c.code))}{_rule_ref_link(str(c.code))}</p></li>'
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
    """Findings the later comparable snapshot no longer reports."""
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
    if not same_producer_contract(prev_artifact, cur_artifact):
        return (
            '<section aria-labelledby="feeddiff-h"><h2 class="section-title" '
            'id="feeddiff-h">What changed in this feed</h2>'
            '<p class="page-lede">The scoring or measurement contract changed since the '
            "previous snapshot, so finding and score changes restart here. No issue is "
            "described as new, resolved, improved, or regressed across this boundary.</p>"
            "</section>"
        )
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
    # The export diff (EXP-18): what changed in the feed file itself, from the
    # structure fingerprint the pipeline remembers between runs. Shown first
    # because a content change is usually the cause of the finding changes
    # below it. Descriptive only; change is normal and carries no judgment.
    export = cur_artifact.get("export_diff")
    if export and export.get("changes"):
        items = "".join(f"<li>{esc(change)}</li>" for change in export["changes"])
        blocks.append(
            '<h3 class="trend-sub">What changed inside the export</h3>'
            f'<ul class="cleared-list">{items}</ul>'
            '<p class="fineprint">Read from the feed file itself, compared with the '
            "previous export. A service change is normal; this is a heads-up so "
            "nothing disappears silently.</p>"
        )
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
            f'<h3 class="trend-sub">No longer reported since {esc(diff.prev_date)} '
            f"({len(diff.resolved)} {noun})</h3>"
            f'<ul class="cleared-list">{_feeddiff_resolved_rows(diff.resolved)}</ul>'
            '<p class="fineprint">This records the later feed state. It does not '
            "establish who made a change or why.</p>"
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


def _accessibility_depth_signals(artifact: dict[str, Any]) -> str:
    """Adoption-framed accessibility-depth signals (EXP-05).

    The second accessibility lens (``accessibility.py``, modeled on the
    BlinkTag ``gtfs-accessibility-validator``) checks field plausibility
    (route-color contrast a low-vision rider can read, stop names a screen
    reader pronounces correctly) and pathway-graph connectivity (step-free
    routing inside stations) -- past whether a field is merely populated. Those
    checks are zero-deduction: they never move the sub-score above or the
    grade, and are surfaced here as adoption progress to make, not as failures,
    so a small agency is never shamed for a gap the field-presence sub-score
    already treats fairly. Empty when the feed has nothing to flag or the
    checks did not run.
    """
    recs = [
        r for r in (artifact.get("recommendations") or []) if r.get("category") == "accessibility"
    ]
    if not recs:
        return ""
    items = "".join(
        f'<li><p class="a11y-depth-what">{esc(str(r.get("what", "")))}</p>'
        f'<p class="a11y-depth-fix"><strong>Consider:</strong> {esc(str(r.get("fix", "")))}</p>'
        "</li>"
        for r in recs
    )
    noun = "signal" if len(recs) == 1 else "signals"
    return (
        '<div class="a11y-depth">'
        f'<p class="a11y-depth-label">{len(recs)} accessibility depth {noun}</p>'
        f'<ul class="a11y-depth-list">{items}</ul>'
        '<p class="a11y-depth-note">Opportunities to strengthen the data, not deductions from '
        "the sub-score above. States what the second accessibility lens can check from the "
        "feed, not verified physical usability.</p>"
        "</div>"
    )


def _accessibility_substat(comp_cat: dict[str, Any], artifact: dict[str, Any] | None = None) -> str:
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
    from .mode_language import boarding_place_noun

    place_plural = boarding_place_noun(artifact or {}, plural=True)
    note = "States accessibility, not verified physical usability."
    if isinstance(stated, (int, float)) and isinstance(marked, (int, float)):
        note = (
            f"{round(stated)}% of {place_plural} state accessibility "
            f"({round(marked)}% marked accessible). "
            "Reflects what the feed states, not verified physical usability."
        )
    depth = _accessibility_depth_signals(artifact) if artifact is not None else ""
    return (
        '<div class="substat" role="group" aria-label="Accessibility sub-score">'
        '<div class="ptop"><span class="pname">Accessibility</span>'
        f'<span class="pscore">{shown}<span class="outof"> / 100</span></span></div>'
        f'<div class="pbar" role="meter" aria-valuenow="{shown}" aria-valuemin="0" '
        f'aria-valuemax="100" aria-label="Accessibility sub-score">'
        f'<span style="width:{width}%;background:var(--grade-{band})"></span></div>'
        f'<p class="pstat">{esc(note)}</p>{depth}</div>'
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


def _board_hero(  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
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
    fresh_details = artifact.get("categories", {}).get("freshness", {}).get("details", {})
    days = fresh_details.get("days_until_expiry")
    horizon_status = resolve_service_horizon_status(fresh_details, artifact.get("snapshot_date"))
    if isinstance(days, (int, float)) and not isinstance(days, bool):
        days = int(days)
        if horizon_status == "unusually_distant":
            chips.append('<span class="chip warn">Review service end date</span>')
        elif days <= 0:
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
    realtime = artifact.get("categories", {}).get("realtime", {})
    if realtime.get("status") != "measured":
        chips.append(f'<span class="chip">{esc(_realtime_unmeasured_label(realtime))}</span>')

    comparable_history = _current_rubric_history(history)
    if len(comparable_history) >= 2:
        prev, cur = comparable_history[-2], comparable_history[-1]
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
        trend = (
            "Methodology changed; trend restarts here"
            if len(history) >= 2
            else "First scorecard for this agency"
        )

    reel = (
        f'<div class="reel" role="img" aria-label="Overall grade {esc(g)}" '
        f'style="--flap-end: calc(var(--reel-h) * -{idx})">'
        '<div class="reel-strip"><span>F</span><span>D</span><span>C</span><span>B</span><span>A</span></div></div>'
    )
    from .mode_language import mode_label

    service_mode = mode_label(artifact)
    mode_html = (
        f'<p class="board-mode"><span>Service mode</span> {esc(service_mode)}</p>'
        if service_mode
        else ""
    )
    return (
        '<div class="board-hero" id="report-overview"><div class="board-inner">'
        f'<p class="board-kicker"><span class="blip" aria-hidden="true"></span>Feed status &middot; checked {esc(artifact["snapshot_date"])}</p>'
        f'<h1 class="board-title"><bdi>{esc(agency_name)}</bdi></h1>'
        '<p class="board-sub">Based on the feed this agency publishes</p>'
        f"{mode_html}"
        f'<div class="grade-block">{reel}'
        f'<div class="score-block"><div><span class="score-big">{o["score"]}</span><span class="score-of"> / 100</span></div>'
        f'<p class="score-trend">{trend}</p>{_peer_context(peer_record)}'
        f'<div class="chips">{"".join(chips)}</div></div></div>'
        "</div></div>"
    )


def _realtime_unmeasured_label(category: dict[str, Any]) -> str:
    """Truthful short label for an unmeasured realtime category."""
    summary = str(category.get("summary") or "").casefold()
    if "access key" in summary or "api key" in summary or "authentication" in summary:
        return "Realtime access needed"
    return "Realtime not yet published"


def _peer_context(record: dict[str, Any] | None) -> str:
    """Location context retained after public percentile claims were removed.

    The name is kept for internal-call compatibility. A scorecard may say where
    its feed record is catalogued, but it does not claim a national or size-peer
    standing.
    """
    if not record:
        return ""
    location = _location_label(record)
    return (
        f'<p class="peer-context">Catalogued in <bdi>{esc(location)}</bdi>.</p>' if location else ""
    )


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


# How the quiet confidence line names the fetch source (EXP-01). Keyed by the
# artifact's confidence.fetch_source (fetch.py: origin | mirror | unknown); an
# unrecognized value falls back to no phrase rather than guessing.
_CONFIDENCE_SOURCE_PHRASES = {
    "origin": " from the agency's own feed",
    "mirror": " from the Mobility Database's mirror copy of the feed",
    "unknown": " from a snapshot whose original source was not recorded",
}


def _confidence_section(artifact: dict[str, Any]) -> str:
    """The measurement-confidence read (EXP-01): one quiet line saying how much
    of the grade this run could measure and from what source, plus an expandable
    per-signal breakdown. A legibility layer on the one grade; it never shows a
    second letter or number, and low confidence describes our measurement
    coverage, not the feed. Artifacts published before schema 1.5 carry no
    confidence block and render byte-for-byte as before (returns empty)."""
    conf = artifact.get("confidence")
    if not conf:
        return ""
    source_phrase = _CONFIDENCE_SOURCE_PHRASES.get(str(conf.get("fetch_source", "")), "")
    line = (
        f"Measured {conf.get('measured_categories', 0)} of "
        f"{conf.get('total_categories', 0)} score categories{source_phrase}."
    )
    level = str(conf.get("level", ""))
    level_html = f"<p>Confidence in this measurement: {esc(level)}.</p>" if level else ""
    notes = "".join(f"<li>{esc(note)}</li>" for note in conf.get("notes", []))
    notes_html = f"<ul>{notes}</ul>" if notes else ""
    return (
        f'<p class="confidence-note">{esc(line)}</p>\n'
        f'    <details class="confidence-how"><summary>How we measured this</summary>'
        f"{level_html}{notes_html}"
        '<p class="fineprint">Confidence describes how much the pipeline could '
        "measure this run, not the feed itself. It never changes the grade.</p>"
        "</details>"
    )


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


def _embed_section(agency_id: str, agency_name: str, grade: str) -> str:
    """A copy-paste embed so an agency can show its live grade on its own site or
    feed README. The badge image regenerates after a completed scoring check, so
    the embed stays in step with the scorecard and links back to it. The copied
    Markdown's alt text names the agency and its current grade, not a generic
    "GTFS data quality", so a reader who can't see the image (a screen reader,
    a client that strips images) still gets the badge's actual content, and an
    agency pasting it into a README gets human-readable anchor text instead of
    an opaque image link with none."""
    badge_svg = f"{BASE_URL}/data/artifacts/{agency_id}/badge.svg"
    badge_json = f"{BASE_URL}/data/artifacts/{agency_id}/badge.json"
    page = f"{BASE_URL}/agency/{agency_id}/"
    alt_text = f"{agency_name} GTFS data quality grade: {grade}"
    markdown = f"[![{alt_text}]({badge_svg})]({page})"
    shields = f"https://img.shields.io/endpoint?url={badge_json}"
    return (
        '<section class="embed" id="embed" aria-labelledby="embed-h">'
        '<h2 class="section-title" id="embed-h">Show your grade</h2>'
        '<p class="page-lede">Put a badge on your agency site or feed README. It updates '
        "after each completed scoring check and links back to this scorecard.</p>"
        f'<p><img src="/data/artifacts/{esc(agency_id)}/badge.svg" '
        f'alt="{esc(alt_text)}"></p>'
        '<label class="visually-hidden" for="embed-md">Badge Markdown</label>'
        f'<textarea id="embed-md" class="outreach-text" rows="2" readonly>{esc(markdown)}</textarea>'
        '<button type="button" class="copy-btn" data-copy="embed-md">Copy Markdown</button>'
        f'<p class="fineprint">Prefer a shields.io style? Point a '
        f'<a href="{esc(shields)}">dynamic endpoint badge</a> at the published '
        f"<code>badge.json</code>.</p>"
        "</section>"
    )


def _citation_reference(
    artifact: dict[str, Any], agency_id: str, agency_name: str, record_url: str
) -> str:
    """The plain-text formatted reference for a single agency's pinned, dated
    record (EXP-09). Names exactly what a citation needs to resolve to a fixed
    claim: which record (the dated JSON, not the page that keeps changing),
    what methodology produced it (rubric + validator version), and what feed
    bytes it scored (the sha256 already carried in ``feed`` for FIX-01
    provenance), so a manager, board packet, or regulatory filing can cite a grade
    the way a paper cites a dataset snapshot instead of a URL that quietly
    drifts."""
    date = str(artifact.get("snapshot_date", ""))
    year = date[:4] or "n.d."
    rubric = str(artifact.get("rubric_version", "—"))
    validator = str(artifact.get("validator_version", "—"))
    reader_profile = reader_archive_profile(artifact) or "unknown"
    sha = str((artifact.get("feed") or {}).get("sha256", "") or "")
    sha_note = f", feed sha256 {sha[:12]}…" if sha else ""
    overall = artifact.get("overall") or {}
    grade_note = f"grade {overall.get('grade', '—')} ({overall.get('score', '—')}/100)"
    return (
        f"GTFS Scorecard. ({year}). {agency_name} GTFS feed-quality record, "
        f"dated {date} ({grade_note}, rubric v{rubric}, gtfs-validator "
        f"{validator}, reader archive profile {reader_profile}{sha_note}). {record_url}"
    )


def _citation_bibtex(
    artifact: dict[str, Any], agency_id: str, agency_name: str, record_url: str
) -> str:
    """The same record as a BibTeX @misc entry, for a researcher's reference
    manager. The key is built from the agency slug and the record date so two
    records for the same agency never collide."""
    date = str(artifact.get("snapshot_date", ""))
    year = date[:4] or "n.d."
    rubric = str(artifact.get("rubric_version", "—"))
    validator = str(artifact.get("validator_version", "—"))
    reader_profile = reader_archive_profile(artifact) or "unknown"
    overall = artifact.get("overall") or {}
    key = f"gtfsscorecard-{agency_id}-{date}".replace(":", "")
    note = (
        f"Checked {date}; rubric v{rubric}; gtfs-validator {validator}; "
        f"reader archive profile {reader_profile}; "
        f"grade {overall.get('grade', '—')} ({overall.get('score', '—')}/100)"
    )
    return (
        f"@misc{{{key},\n"
        f"  title        = {{{agency_name} GTFS feed-quality record}},\n"
        "  author       = {GTFS Scorecard},\n"
        f"  year         = {{{year}}},\n"
        f"  howpublished = {{\\url{{{record_url}}}}},\n"
        f"  note         = {{{note}}}\n"
        "}"
    )


def _citation_section(artifact: dict[str, Any], agency_id: str, agency_name: str) -> str:
    """A 'Cite this record' affordance (EXP-09): a stable, versioned, per-agency
    record any manager, board, or regulatory filing can point at, distinct from the
    live page above (which is overwritten on every check). The record it cites
    is the dated JSON artifact the publish step already writes and never
    overwrites (``<agency>/<date>.json``), pinning grade, category scores,
    methodology (rubric + validator version + reader archive profile), and
    provenance (the exact feed bytes scored, by sha256) as they stood on that date, backed by the
    per-agency history archive so the cited state is reproducible. Emits both a
    plain-text formatted reference and a BibTeX entry, each with a copy button
    (the page-level copy script wires them), so citing a grade takes one click
    instead of hand-formatting one."""
    date = str(artifact.get("snapshot_date", ""))
    if not date:
        return ""
    record_url = f"{BASE_URL}/data/artifacts/{agency_id}/{date}.json"
    reference = _citation_reference(artifact, agency_id, agency_name, record_url)
    bibtex = _citation_bibtex(artifact, agency_id, agency_name, record_url)
    repo = "https://github.com/ChelseaKR/gtfs-scorecard"
    return (
        '<section class="citation" id="cite" aria-labelledby="cite-h">'
        '<h2 class="section-title" id="cite-h">Cite this record</h2>'
        '<p class="page-lede">This page updates on every check. The record below does not: it is '
        f'the dated file this grade came from, published at <a href="{esc(record_url)}">'
        f"{esc(record_url)}</a> and never overwritten, pinning the grade, category scores, "
        "rubric version, validator version, reader archive profile, and the scored feed's "
        "sha256 as they stood on "
        f"{esc(date)}. Use it in a board packet, a regulatory filing, or a research citation "
        "instead of linking the live page, whose content will differ on your next visit.</p>"
        '<label class="visually-hidden" for="cite-text">Formatted reference</label>'
        f'<textarea id="cite-text" class="outreach-text" rows="3" readonly>{esc(reference)}</textarea>'
        '<button type="button" class="copy-btn" data-copy="cite-text">Copy reference</button>'
        '<label class="visually-hidden" for="cite-bibtex">BibTeX</label>'
        f'<textarea id="cite-bibtex" class="outreach-text" rows="7" readonly>{esc(bibtex)}</textarea>'
        '<button type="button" class="copy-btn" data-copy="cite-bibtex">Copy BibTeX</button>'
        '<p class="fineprint">Citing the tool itself rather than one agency\'s record? Use the '
        f'repo\'s <a href="{esc(repo)}/blob/main/CITATION.cff">CITATION.cff</a>.</p>'
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
    words match the scorecard, with the finding codes and the fix-guide
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
            lines.append(f"   Finding code: {code}")
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
# A national or statewide aggregate can contain tens of thousands of routes.
# Rendering every row makes the scorecard unusably large even though the same
# complete data already ships in the per-agency JSON artifact. Keep ordinary
# agency tables unchanged while bounding aggregate pages.
_AGENCY_MAP_ROUTE_LIST_CAP = 500


# The agency map's client script. Kept as a plain string with a JSON-encoded
# placeholder for the geometry URL, so the JavaScript braces don't need doubling
# the way an f-string would force. Linked brushing ties each map line to its row
# in the route table below; the table stays the accessible primary and the canvas
# remains aria-hidden. The table is also the keyboard surface: the script makes
# each drawable route's row focusable (so a page without the script gains no
# inert tab stops), focus brushes its line, and Enter or Space pins it, the
# keyboard equivalent of hovering and clicking a line on the canvas.
_AGENCY_MAP_JS = r"""      function initAgencyMap() {
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
        // links, so a click only toggles the highlight. The rows are also the
        // keyboard surface (the canvas stays aria-hidden and untabbable): each
        // becomes focusable here, not in the markup, so a page without this
        // script gains no inert tab stops, focus brushes its line, and Enter
        // or Space toggles the pin, mirroring the click.
        function togglePin(key) {
          pinned = (pinned === key) ? null : key;
          highlight(pinned);
          // Reflect the pin on each row so a screen reader announces the toggle
          // state, not just that a control was activated.
          Object.keys(rows).forEach(function (k) {
            rows[k].setAttribute("aria-pressed", k === pinned ? "true" : "false");
          });
        }
        Object.keys(rows).forEach(function (key) {
          var tr = rows[key];
          tr.setAttribute("tabindex", "0");
          // The row is an operable toggle (focus brushes its route; Enter/Space
          // pins it), so give it a button role, a pressed state, and an
          // accessible name so assistive tech perceives it as actionable. Its
          // cell text (route name and detail) supplies the name.
          tr.setAttribute("role", "button");
          tr.setAttribute("aria-pressed", "false");
          tr.addEventListener("mouseenter", function () { highlight(key); });
          tr.addEventListener("mouseleave", function () { highlight(pinned); });
          tr.addEventListener("focus", function () { highlight(key); });
          tr.addEventListener("blur", function () { highlight(pinned); });
          tr.addEventListener("click", function () { togglePin(key); });
          tr.addEventListener("keydown", function (e) {
            if (e.key !== "Enter" && e.key !== " ") return;
            e.preventDefault();  // Space must pin, never scroll the page
            togglePin(key);
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
            var statusEl = document.getElementById("route-map-load-status");
            if (statusEl) statusEl.textContent = "Interactive route map loaded.";
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
          }).catch(function () {
            var statusEl = document.getElementById("route-map-load-status");
            if (statusEl) statusEl.textContent =
              "The route data could not load. The complete route and stop data is still below.";
          });
        });
      }"""


def _agency_map_script(geo_url: str) -> str:
    """The MapLibre bootstrap for an agency map: draw routes + stops, fit to the
    data, and respect prefers-reduced-motion (no animated fit). The map is a
    visual enhancement marked aria-hidden; the route table below it is the
    operable, screen-reader equivalent, so the canvas is taken out of the tab
    order and no zoom/pan controls are added. Hovering (or tapping) a line brushes
    its row in the table and the reverse; clicking names the route or stop. The
    same rows carry the keyboard model: the script makes each drawable route's
    row focusable, focusing it brushes its line, and Enter or Space pins the
    selection exactly as a click does. MapLibre and the route geometry load only
    after an explicit request, so the optional canvas cannot block the scorecard."""
    js = _AGENCY_MAP_JS.replace("__GEO_URL_JSON__", json.dumps(geo_url))
    return (
        "    <script>\n"
        "      (function () {\n"
        '        var loadEl = document.getElementById("route-map-load");\n'
        '        var statusEl = document.getElementById("route-map-load-status");\n'
        '        var mapEl = document.getElementById("route-map");\n' + js + "\n"
        '        loadEl.addEventListener("click", function () {\n'
        "          loadEl.disabled = true;\n"
        '          loadEl.textContent = "Loading map…";\n'
        '          if (statusEl) statusEl.textContent = "Loading the interactive route map.";\n'
        '          var css = document.createElement("link");\n'
        '          css.rel = "stylesheet";\n'
        f'          css.href = "https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.css";\n'
        "          document.head.appendChild(css);\n"
        '          var script = document.createElement("script");\n'
        f'          script.src = "https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.js";\n'
        "          script.onload = function () {\n"
        "            loadEl.hidden = true;\n"
        '            if (mapEl) mapEl.textContent = "";\n'
        "            initAgencyMap();\n"
        "          };\n"
        "          script.onerror = function () {\n"
        "            loadEl.disabled = false;\n"
        '            loadEl.textContent = "Try loading the map again";\n'
        "            if (statusEl) statusEl.textContent =\n"
        '              "The map could not load. The complete route and stop data is still below.";\n'
        "          };\n"
        "          document.head.appendChild(script);\n"
        "        });\n"
        "      })();\n"
        "    </script>"
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

    ferry_only = artifact.get("mode_profile", {}).get("ferry_only") is True
    stop_noun = "terminal" if ferry_only else "stop"
    stop_noun_plural = "terminals" if ferry_only else "stops"

    agency_name = esc(artifact.get("agency", {}).get("name", agency_id))

    # The accessible route table: route, type, and the line color described in
    # words (never color alone). Scoped headers for screen-reader navigation.
    shown_routes = routes[:_AGENCY_MAP_ROUTE_LIST_CAP]
    hidden_route_count = max(0, len(routes) - len(shown_routes))
    drawn = [r for r in shown_routes if r.get("has_shape")]
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
            for r in shown_routes
        )
        route_caption = (
            f"First {len(shown_routes):,} of {len(routes):,} routes in {agency_name}'s feed"
            if hidden_route_count
            else f"Routes in {agency_name}'s feed"
        )
        route_remainder = (
            f'<p class="fineprint">Showing {len(shown_routes):,} of {len(routes):,} routes. '
            f'The <a href="/data/artifacts/{esc(agency_id)}/latest.json">current scorecard JSON</a> '
            "contains the complete route list.</p>"
            if hidden_route_count
            else ""
        )
        route_table = (
            '<div class="table-wrap"><table class="route-table">'
            f"<caption>{route_caption}</caption>"
            '<thead><tr><th scope="col">Route</th><th scope="col">Type</th>'
            '<th scope="col">Line color</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>{route_remainder}"
        )
    else:
        route_table = '<p class="page-lede">This feed lists no routes.</p>'

    # Keep the stop count eligible for search snippets, while the stop names stay
    # in the utility-detail boundary with the map and route table. The names form
    # the map points' text equivalent without weighing the page down by default.
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
        stop_summary = (
            f'<p class="map-stopcount">This feed has <strong>{stop_count}</strong> '
            f"{stop_noun if stop_count == 1 else stop_noun_plural}.</p>"
        )
        stop_details = (
            f'<details class="stop-list-wrap"><summary>List every {stop_noun}</summary>'
            f'<ul class="stop-list">{stop_items}{remainder}</ul></details>'
            if stop_items
            else ""
        )
    else:
        stop_summary = f'<p class="page-lede">This feed has no located {stop_noun_plural}.</p>'
        stop_details = ""

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
            f"{stop_noun_plural} are the dots."
        )
    elif stop_count:
        intro = f"This feed has no route shapes, so the map shows its {stop_noun_plural} only."
    else:
        intro = ""

    map_html = ""
    script = ""
    if geo_path:
        map_html = (
            f'<a class="skip-link-inline" href="#route-data">Skip to route and {stop_noun} data</a>'
            '<div class="map-load-panel">'
            '<button type="button" class="button button-secondary" id="route-map-load" '
            'aria-controls="route-map">'
            "Load interactive route map"
            "</button>"
            '<p id="route-map-load-status" class="fineprint" role="status">'
            f"The route and {stop_noun} data is ready below. Load the map only when you want "
            "the geographic view. It uses additional data.</p>"
            "</div>"
            '<div id="route-map" class="agency-map" aria-hidden="true">'
            '<p class="map-fallback">The interactive map has not loaded. '
            f"The route and {stop_noun} data below carries the same information.</p></div>"
            '<p class="fineprint">Basemap: OpenFreeMap, &copy; OpenStreetMap contributors. '
            f"Routes and {stop_noun_plural}: this "
            "agency's GTFS feed.</p>"
        )
        script = _agency_map_script(f"/{geo_path}")

    return (
        '<section aria-labelledby="map-h" class="route-map-section">'
        f'<h2 class="section-title" id="map-h">Routes and {stop_noun_plural}</h2>'
        + (f'<p class="page-lede">{intro}</p>' if intro else "")
        + stop_summary
        + "<div data-nosnippet>"
        + map_html
        + legend
        + '<div id="route-data" tabindex="-1">'
        + route_table
        + stop_details
        + "</div></div></section>"
        + script
    )


def _guided_fix_flow(artifact: dict[str, Any], agency_id: str, has_fixlog: bool) -> str:
    """The closed-loop guided fix flow (EXP-11): one compact three-step loop per
    top fix, stitching the pieces that already exist into a single per-finding
    path — (1) the plain-language finding with its /fix/<code>/ guide, (2) "Make
    the change", naming the producing tool detected from the feed host, and (3)
    "Check the result", explaining that the next comparable run checks whether
    the finding is still reported.

    The boundary stays explicit: the scorecard observes the published feed; an
    action or ticket record is required to attribute a change. Empty when the
    feed has no top fixes, so an all-clear feed renders exactly as it did before
    this feature."""
    fixes = artifact.get("top_fixes", [])
    if not fixes:
        return ""
    fix_tool = detect_tool(artifact.get("feed", {}).get("static_url"))
    tool_path = esc(fix_tool.fix_path) if fix_tool else ""
    if has_fixlog:
        prove_link = (
            f' <a class="fix-guide" href="/agency/{esc(agency_id)}/fixes/">'
            "See this feed's finding-clearance log</a>."
        )
    else:
        prove_link = (
            ' <a class="fix-guide" href="/check/">Self-check a feed before you publish</a>.'
        )
    items = []
    for f in fixes:
        code = str(f.get("code", ""))
        guide = _fix_guide_link(code)
        change = tool_path or (
            "Make this change in whatever tool produces your feed, then re-export."
        )
        items.append(
            f'<li class="fixloop-item"><p class="fixloop-name">{esc(f.get("fix", ""))}{guide}</p>'
            f'<p class="fixloop-step"><strong>Make the change.</strong> {change}</p>'
            f'<p class="fixloop-step"><strong>Check the result.</strong> The next scorecard '
            "run checks this finding again. If a comparable check no longer reports it, "
            "the feed's clearance log records that result. This confirms feed state, not "
            "who made the change."
            f"{prove_link}</p></li>"
        )
    return (
        '<details class="fixloop">'
        "<summary>How to make and check these changes</summary>"
        '<p class="fixloop-lede"><strong>Check the result on the published feed.</strong> '
        "Read the guide, make the change in your tool, and use the next comparable run to "
        "see whether the finding is still reported. Only an action or ticket record can "
        "attribute who made the change.</p>"
        f'<ol class="fixloop-list">{"".join(items)}</ol></details>'
    )


def _rider_impact_section(artifact: dict[str, Any]) -> str:
    """Summarize rider-visible data already present in an artifact.

    This is deliberately a closed, presentation-only disclosure after the
    agency fix list. It does not add a rider score or infer service quality from
    feed quality. Unknown and older artifact shapes stay neutral rather than
    being treated as a gap.
    """

    schedule = _rider_schedule_text(
        _artifact_category(artifact, "freshness"), artifact.get("snapshot_date")
    )
    completeness = _artifact_category(artifact, "completeness")
    from .mode_language import boarding_place_noun

    accessibility = _rider_accessibility_text(
        completeness,
        boarding_place_noun(artifact),
        boarding_place_noun(artifact, plural=True),
        "vessels" if boarding_place_noun(artifact) == "terminal" else "vehicles",
    )
    fare = _rider_fare_text(completeness)
    live = _rider_live_text(_artifact_category(artifact, "realtime"))
    rows = (
        f"<dt>Schedule visibility</dt><dd>{schedule}</dd>"
        f"<dt>Published accessibility data</dt><dd>{accessibility}</dd>"
        f"<dt>Fare information</dt><dd>{fare}</dd>"
        f"<dt>Realtime information</dt><dd>{live}</dd>"
    )
    return (
        '<details class="rider-impact" id="rider-impact">'
        "<summary>Rider view: what this feed publishes</summary>"
        '<p class="rider-impact-intro">A quick read of rider-facing information in this feed.</p>'
        f"<dl>{rows}</dl>"
        '<p class="rider-impact-boundary"><strong>Important:</strong> This does not rate service '
        "reliability. Riders should confirm current service alerts, fares, and accessibility "
        "accommodations with the transit operator before traveling.</p></details>"
    )


def _ferry_enum_text(profile: dict[str, Any], subject: str, field: str) -> str:
    """Explain a ferry enum while keeping blank/0 values explicitly unknown."""
    total = int(profile.get("total_count") or 0)
    stated = int(profile.get("stated_count") or 0)
    allowed = int(profile.get("allowed_count") or 0)
    if total == 0:
        return f"No {subject} were available to measure in this snapshot."
    if stated == 0:
        return f"Unknown: none of the {total:,} {subject} publish {field}."
    stated_label = _numeric_percent(profile.get("stated_pct"))
    allowed_label = _numeric_percent(profile.get("allowed_pct"))
    return (
        f"{_plain_number(stated_label or 0.0)}% of {subject} publish a value; "
        f"{_plain_number(allowed_label or 0.0)}% of all {subject} explicitly say allowed "
        f"({allowed:,} of {total:,}). Unstated values remain unknown."
    )


def _ferry_profile_section(artifact: dict[str, Any]) -> str:
    """Render the ungraded ferry subset without extending the scoring rubric."""
    profile = artifact.get("ferry_profile")
    if not isinstance(profile, dict) or profile.get("measured") is not True:
        return ""

    hierarchy = profile.get("terminal_hierarchy", {})
    hierarchy = hierarchy if isinstance(hierarchy, dict) else {}
    boarding = int(hierarchy.get("boarding_location_count") or 0)
    parented = int(hierarchy.get("parented_boarding_location_count") or 0)
    stations = int(hierarchy.get("referenced_station_count") or 0)
    if boarding == 0:
        hierarchy_text = "No ferry boarding locations were available to measure."
    elif parented == 0:
        hierarchy_text = (
            f"{boarding:,} ferry boarding locations; no parent-station hierarchy is published."
        )
    else:
        hierarchy_text = (
            f"{boarding:,} ferry boarding locations; {parented:,} link to "
            f"{stations:,} referenced station record{'s' if stations != 1 else ''}."
        )

    stop_access = profile.get("stop_access", {})
    stop_access = stop_access if isinstance(stop_access, dict) else {}
    eligible = int(stop_access.get("eligible_terminal_count") or 0)
    access_stated = int(stop_access.get("stated_count") or 0)
    if eligible == 0:
        access_text = (
            "Not applicable: no ferry boarding location is linked to a parent station, "
            "so stop_access is not permitted here."
        )
    elif access_stated == 0:
        access_text = (
            f"Unknown: none of the {eligible:,} eligible child terminal locations publish "
            "stop_access."
        )
    else:
        direct = int(stop_access.get("direct_count") or 0)
        through = int(stop_access.get("through_station_count") or 0)
        access_pct = _numeric_percent(stop_access.get("stated_pct"))
        access_text = (
            f"{_plain_number(access_pct or 0.0)}% of eligible child terminal "
            f"locations publish access: {direct:,} direct from the street network and "
            f"{through:,} through the station or its pathways."
        )

    accessibility = profile.get("accessibility", {})
    accessibility = accessibility if isinstance(accessibility, dict) else {}
    terminal_access = accessibility.get("terminals", {})
    trip_access = accessibility.get("trips", {})
    terminal_access = terminal_access if isinstance(terminal_access, dict) else {}
    trip_access = trip_access if isinstance(trip_access, dict) else {}
    accessibility_text = (
        _ferry_enum_text(terminal_access, "ferry boarding locations", "wheelchair_boarding")
        + " "
        + _ferry_enum_text(trip_access, "ferry trips", "wheelchair_accessible")
        + " This reports published values, not verified physical usability."
    )

    bikes = profile.get("bikes", {})
    cars = profile.get("cars", {})
    bikes = bikes if isinstance(bikes, dict) else {}
    cars = cars if isinstance(cars, dict) else {}

    fares = profile.get("fares", {})
    fares = fares if isinstance(fares, dict) else {}
    model = str(fares.get("model") or "none")
    if fares.get("fare_free") is True:
        fares_text = "Whole feed: the service is curated as fare-free."
    elif fares.get("applied") is True:
        label = {"legacy": "GTFS Fares v1", "v2": "GTFS Fares v2"}.get(model, model)
        fares_text = f"Whole feed: applied fare data is published using {label}."
    elif model == "v2":
        fares_text = (
            "Whole feed: Fares v2 products are present, but no leg rules apply them to trips."
        )
    else:
        fares_text = (
            "Whole feed: no applied fare data is published. This is not evidence that ferry "
            "service is free."
        )

    realtime = profile.get("realtime", {})
    realtime = realtime if isinstance(realtime, dict) else {}
    kinds = realtime.get("configured_kinds", [])
    kinds = kinds if isinstance(kinds, list) else []
    kind_labels = {
        "trip_updates": "Trip Updates",
        "vehicle_positions": "Vehicle Positions",
        "service_alerts": "Service Alerts",
    }
    realtime_text = (
        "Whole feed: configured GTFS-Realtime endpoints are "
        + ", ".join(kind_labels.get(str(kind), str(kind).replace("_", " ")) for kind in kinds)
        + "."
        if kinds
        else "Whole feed: no GTFS-Realtime endpoints are configured in this scorecard."
    )

    items = [
        (
            "Ferry service",
            f"{int(profile.get('route_count') or 0):,} routes · {int(profile.get('trip_count') or 0):,} trips",
        ),
        ("Terminal structure", hierarchy_text),
        ("Terminal access", access_text),
        ("Published accessibility", accessibility_text),
        ("Bicycles", _ferry_enum_text(bikes, "ferry trips", "bikes_allowed")),
        ("Cars", _ferry_enum_text(cars, "ferry trips", "cars_allowed")),
        ("Fares", fares_text),
        ("Realtime", realtime_text),
    ]
    cards = "".join(
        f"<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>" for label, value in items
    )
    return (
        '<section class="feed-details ferry-profile" aria-labelledby="ferry-profile-h">'
        '<p class="ferry-profile-kicker">Ungraded capability read</p>'
        '<h2 class="section-title" id="ferry-profile-h">Ferry data profile</h2>'
        '<p class="page-lede">A ferry-specific view of what this GTFS feed publishes. '
        "Schedule measurements use ferry routes and trips only; fare and realtime facts are "
        "labelled as whole-feed. Unknown values are not treated as no.</p>"
        f'<dl class="ferry-profile-grid">{cards}</dl>'
        '<p class="fineprint">Descriptive only. This profile does not change the grade or '
        "verify vessels, terminal facilities, vehicle carriage, fares, or accessibility in "
        'the real world. Field meanings follow the <a href="https://gtfs.org/documentation/'
        'schedule/reference/">GTFS Schedule reference</a>.</p></section>'
    )


def _artifact_category(artifact: dict[str, Any], name: str) -> dict[str, Any]:
    categories = artifact.get("categories", {})
    category = categories.get(name, {}) if isinstance(categories, dict) else {}
    return category if isinstance(category, dict) else {}


def _measured_details(category: dict[str, Any]) -> dict[str, Any]:
    details = category.get("details", {})
    return details if category.get("status") == "measured" and isinstance(details, dict) else {}


def _rider_schedule_text(freshness: dict[str, Any], snapshot_date: Any = None) -> str:
    fresh_details = freshness.get("details", {})
    fresh_details = fresh_details if isinstance(fresh_details, dict) else {}
    days = (
        _numeric_percent(fresh_details.get("days_until_expiry"))
        if freshness.get("status") == "measured"
        else None
    )
    if days is None:
        return "Schedule visibility is not known from this scorecard."
    if resolve_service_horizon_status(fresh_details, snapshot_date) == "unusually_distant":
        end = fresh_details.get("effective_expiry_date")
        through = f" through {esc(str(end))}" if end else " to an unusually distant date"
        return (
            f"The feed states that service is published{through}. This may be intentional "
            "or a placeholder; confirm current service with the transit operator."
        )
    if days > 0:
        return f"The feed's last published service date is in {_plain_number(days)} days."
    if days == 0:
        return "The feed's last published service date is today."
    return f"The feed's last published service date was {_plain_number(abs(days))} days ago."


def _rider_accessibility_text(
    completeness: dict[str, Any],
    place: str = "stop",
    places: str = "stops",
    vehicles: str = "vehicles",
) -> str:
    comp_details = _measured_details(completeness)
    access = comp_details.get("accessibility", {})
    access = access if isinstance(access, dict) else {}
    stops = _numeric_percent(
        access.get("stops_stated_pct", comp_details.get("wheelchair_boarding_pct"))
    )
    trips = _numeric_percent(
        access.get("trips_stated_pct", comp_details.get("wheelchair_accessible_pct"))
    )
    if stops is not None and trips is not None:
        text = (
            f"Accessibility information is stated for {_plain_number(stops)}% of {places} and "
            f"{_plain_number(trips)}% of trips."
        )
    elif stops is not None:
        text = (
            f"Accessibility information is stated for {_plain_number(stops)}% of {places}; "
            "trip coverage is not known."
        )
    elif trips is not None:
        text = (
            f"Accessibility information is stated for {_plain_number(trips)}% of trips; "
            f"{place.capitalize()} coverage is not known."
        )
    else:
        text = "Published accessibility-data coverage is not known from this scorecard."
    return text + (
        f" This measures published data, not whether {places} or {vehicles} are physically usable."
    )


def _rider_fare_text(completeness: dict[str, Any]) -> str:
    comp_details = _measured_details(completeness)
    fare_free = comp_details.get("fare_free")
    has_fares = comp_details.get("has_fares")
    fares = comp_details.get("fares", {})
    fares = fares if isinstance(fares, dict) else {}
    if fare_free is True:
        return "The feed marks this service as fare-free."
    if has_fares is True:
        model = fares.get("model")
        model_label = (
            {"legacy": "GTFS Fares v1", "v2": "GTFS Fares v2"}.get(model)
            if isinstance(model, str)
            else None
        )
        if model_label is None and isinstance(model, str) and model:
            model_label = model
        return (
            f"Fare information is published using {esc(model_label)}."
            if model_label
            else "Fare information is published in the feed."
        )
    if has_fares is False and fare_free is False:
        return "No fare information is published in the feed."
    return "Fare-information availability is not known from this scorecard."


def _rider_live_text(realtime: dict[str, Any]) -> str:
    rt_details = realtime.get("details", {})
    rt_details = rt_details if isinstance(rt_details, dict) else {}
    coverage = (
        _numeric_percent(rt_details.get("coverage_pct"))
        if realtime.get("status") == "measured"
        else None
    )
    reachable = _numeric_percent(rt_details.get("kinds_reachable"))
    if coverage is not None:
        return (
            f"Live-arrival data covered {_plain_number(coverage)}% of scheduled trips "
            "in the sampled window."
        )
    if realtime.get("status") == "measured" and reachable is not None and reachable > 0:
        return "One or more realtime feeds were reachable; live-arrival coverage is not known."
    if realtime.get("status") == "measured" and reachable == 0:
        return "No realtime feed was reachable during sampling."
    return "Realtime-feed availability and live-arrival coverage are not known from this scorecard."


def _plain_number(value: float) -> str:
    """A stable, compact number for static/interactive disclosure parity."""
    rounded = round(value, 1)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.1f}"


def _load_effort_bands() -> dict[str, str]:
    """Code -> empirical clearance-timing band, from the calibration file.

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
    """Empirical clearance timing for a notice code, or '' when none applies.

    Additive by design: the hand-authored hint always renders first, and this
    appends a causally neutral timing band only when the corpus has enough
    compatible closed episodes for this code (effort_calibration.band_text)
    and the calibration file exists. Absent file -> empty mapping -> no change,
    so goldens rendered without calibration stay byte-identical."""
    band = (effort_bands or {}).get(str(code))
    return f'<p class="effort-band">{esc(band)}</p>' if band else ""


def _location_label(record: dict[str, Any] | None) -> str:
    """Human location label from the portable directory contract.

    Existing U.S. pages keep their familiar state-only label. Everywhere else
    includes the country so names such as Georgia, Victoria, and England are
    not presented without geographic context.
    """
    row = record or {}
    country = str(row.get("country") or "US").strip().upper()
    subdivision = str(row.get("subdivision_name") or "").strip()
    legacy_state = str(row.get("state") or "").strip()
    if country == "US":
        return subdivision or legacy_state
    country_label = country_name(country, country)
    if subdivision:
        return f"{subdivision}, {country_label}"
    return country_label or legacy_state


@dataclass(frozen=True)
class AgencySeoMetadata:
    """Unique search metadata planned for one published feed record."""

    title: str
    description: str
    dataset_name: str


def _ellipsize(value: str, limit: int) -> str:
    """Fit human text within ``limit`` without cutting a trailing separator."""
    if len(value) <= limit:
        return value
    if limit <= 1:
        return "…"[:limit]
    return value[: limit - 1].rstrip(" ,-/;:") + "…"


def _seo_location_label(location_label: str, limit: int) -> str:
    """Keep a useful location within a metadata budget."""
    if len(location_label) <= limit:
        return location_label
    country = location_label.rsplit(",", 1)[-1].strip()
    if country and len(country) <= limit:
        return country
    return _ellipsize(location_label, limit)


def _agency_seo_metadata(
    agency_name: str,
    *,
    location_label: str = "",
    rt_measured: bool = False,
    disambiguator: str = "",
) -> AgencySeoMetadata:
    """Build bounded metadata while keeping any disambiguator visible."""
    if disambiguator:
        title_disambiguator = _ellipsize(disambiguator, 20)
        title_suffix = f" [{title_disambiguator}] GTFS quality report"
    else:
        title_location = _seo_location_label(location_label, 25)
        title_qualifier = f" ({title_location})" if title_location else ""
        title_suffix = f"{title_qualifier} GTFS quality report"
    title_name = _ellipsize(agency_name, max(1, 60 - len(title_suffix)))
    title = f"{title_name}{title_suffix}"

    desc_tail = (
        ": service dates, validator findings, rider information, realtime, and fixes."
        if rt_measured
        else ": service dates, validator findings, rider information, and fixes."
    )
    desc_prefix = "GTFS quality report for "
    desc_disambiguator = _ellipsize(disambiguator, 24)
    identity_prefix = f"[{desc_disambiguator}] " if desc_disambiguator else ""
    desc_location = _seo_location_label(location_label, 35)
    location_suffix = f" in {desc_location}" if desc_location else ""
    max_desc_name = max(
        1,
        155 - len(desc_prefix) - len(identity_prefix) - len(location_suffix) - len(desc_tail),
    )
    desc_name = _ellipsize(agency_name, max_desc_name)
    description = f"{desc_prefix}{identity_prefix}{desc_name}{location_suffix}{desc_tail}"

    dataset_context = ", ".join(value for value in (location_label, disambiguator) if value)
    dataset_name = (
        f"{agency_name} ({dataset_context}) GTFS data quality report"
        if dataset_context
        else f"{agency_name} GTFS data quality report"
    )
    if len(title) > 60 or len(description) > 155:
        raise ValueError(f"agency SEO metadata exceeds its length budget for {agency_name!r}")
    return AgencySeoMetadata(title, description, dataset_name)


def _metadata_collision_components(
    planned: dict[str, AgencySeoMetadata],
) -> list[set[str]]:
    """Return connected groups that collide on any indexable metadata field."""
    parent = {agency_id: agency_id for agency_id in planned}

    def find(agency_id: str) -> str:
        while parent[agency_id] != agency_id:
            parent[agency_id] = parent[parent[agency_id]]
            agency_id = parent[agency_id]
        return agency_id

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for field in ("title", "description", "dataset_name"):
        seen: dict[str, str] = {}
        for agency_id, metadata in planned.items():
            value = str(getattr(metadata, field)).casefold()
            if value in seen:
                union(agency_id, seen[value])
            else:
                seen[value] = agency_id

    groups: dict[str, set[str]] = {}
    for agency_id in planned:
        groups.setdefault(find(agency_id), set()).add(agency_id)
    return [group for group in groups.values() if len(group) > 1]


def _plan_agency_seo_metadata(
    records: list[dict[str, Any]],
    artifacts_by_id: dict[str, dict[str, Any]],
    registry_by_id: dict[str, Agency],
) -> dict[str, AgencySeoMetadata]:
    """Plan unique titles, descriptions, and Dataset names for the corpus."""
    planned: dict[str, AgencySeoMetadata] = {}
    record_by_id = {str(record["id"]): record for record in records}
    for agency_id, record in record_by_id.items():
        artifact = artifacts_by_id[agency_id]
        planned[agency_id] = _agency_seo_metadata(
            str(record.get("name") or agency_id),
            location_label=_location_label(record),
            rt_measured=(
                artifact.get("categories", {}).get("realtime", {}).get("status") == "measured"
            ),
        )

    for group in _metadata_collision_components(planned):
        agencies = [registry_by_id.get(agency_id) for agency_id in sorted(group)]
        variants = [agency.feed_variant.strip() if agency else "" for agency in agencies]
        mdb_ids = [
            normalized_mdb_id(agency.mdb_id) if agency and agency.mdb_id else ""
            for agency in agencies
        ]
        if all(variants) and len({value.casefold() for value in variants}) == len(group):
            qualifiers = dict(zip(sorted(group), variants, strict=True))
        elif all(mdb_ids) and len(set(mdb_ids)) == len(group):
            qualifiers = {
                agency_id: f"MDB {mdb_id.removeprefix('mdb-')}"
                for agency_id, mdb_id in zip(sorted(group), mdb_ids, strict=True)
            }
        else:
            qualifiers = {
                agency_id: f"record {hashlib.sha256(agency_id.encode()).hexdigest()[:8]}"
                for agency_id in group
            }
        for agency_id in group:
            record = record_by_id[agency_id]
            artifact = artifacts_by_id[agency_id]
            planned[agency_id] = _agency_seo_metadata(
                str(record.get("name") or agency_id),
                location_label=_location_label(record),
                rt_measured=(
                    artifact.get("categories", {}).get("realtime", {}).get("status") == "measured"
                ),
                disambiguator=qualifiers[agency_id],
            )

    remaining = _metadata_collision_components(planned)
    for group in remaining:
        for agency_id in group:
            record = record_by_id[agency_id]
            artifact = artifacts_by_id[agency_id]
            planned[agency_id] = _agency_seo_metadata(
                str(record.get("name") or agency_id),
                location_label=_location_label(record),
                rt_measured=(
                    artifact.get("categories", {}).get("realtime", {}).get("status") == "measured"
                ),
                disambiguator=(f"record {hashlib.sha256(agency_id.encode()).hexdigest()[:8]}"),
            )

    remaining = _metadata_collision_components(planned)
    if remaining:
        collisions = ", ".join(",".join(sorted(group)) for group in remaining)
        raise ValueError(f"agency SEO metadata is not unique: {collisions}")
    return planned


def _render_agency(  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    artifact: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
    prev_artifact: dict[str, Any] | None = None,
    dir_record: dict[str, Any] | None = None,
    liveness: dict[str, Any] | None = None,
    stop_names: list[str] | None = None,
    has_fixlog: bool = False,
    now: dt.datetime | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    effort_bands: dict[str, str] | None = None,
    seo_metadata: AgencySeoMetadata | None = None,
) -> str:
    name = artifact["agency"]["id"], artifact["agency"]["name"]
    agency_id, agency_name = name
    overall = artifact["overall"]
    canonical = f"{BASE_URL}/agency/{agency_id}/"
    location_record = dict(dir_record or {})
    location_record["country"] = location_record.get("country") or artifact.get("agency", {}).get(
        "country", "US"
    )
    location_label = _location_label(location_record) if dir_record else ""
    # The portable directory is authoritative for location. Enrich a local copy
    # so every country-gated body helper behaves correctly for older artifacts
    # that predate the additive agency.country field, without mutating callers.
    effective_country = str(location_record.get("country") or "US").upper()
    artifact = {
        **artifact,
        "agency": {**artifact.get("agency", {}), "country": effective_country},
    }
    # Older artifacts predate mode-aware copy. Adapt a deep copy at render time
    # so ferry and mixed-mode pages are correct before their next scoring run.
    from .mode_language import adapt_artifact_language

    artifact = adapt_artifact_language(artifact)
    rt_measured = artifact.get("categories", {}).get("realtime", {}).get("status") == "measured"
    metadata = seo_metadata or _agency_seo_metadata(
        agency_name,
        location_label=location_label,
        rt_measured=rt_measured,
    )
    title = metadata.title
    desc = metadata.description

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
            code = _safe_finding_code(f.get("code"))
            finding_attrs = (
                f' id="finding-{esc(code)}" data-finding-card="{esc(code)}"' if code else ""
            )
            pts = f.get("points")
            worth = (
                f'<span class="aworth">worth about +{round(float(pts))} '
                "points in its category</span>"
                if isinstance(pts, (int, float)) and pts >= 1
                else ""
            )
            owner = f.get("owner")
            owner_tag = f'<span class="aowner">{esc(owner)}</span>' if owner else ""
            alerts.append(
                f'<div class="alert"{finding_attrs}><span class="badge{cls}">Fix {i + 1:02d}</span>'
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
        summary = (
            presented_freshness_summary(cat, artifact.get("snapshot_date"))
            if key == "freshness"
            else str(cat.get("summary") or "")
        )
        if cat.get("status") != "measured":
            note = summary or "Not part of the grade yet."
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
        substat = (
            _accessibility_substat(cat, artifact) + _fares_substat(cat)
            if key == "completeness"
            else ""
        )
        cats_html += (
            f'<div class="platform">'
            f'<span class="trk" aria-hidden="true">{trk}</span>'
            f'<div class="pmain"><div class="ptop">'
            f'<span class="pname">{esc(label)}</span>'
            f'<span class="pscore">{score}<span class="outof"> / 100</span></span></div>'
            f'<div class="pbar" role="meter" aria-valuenow="{score}" aria-valuemin="0" '
            f'aria-valuemax="100" aria-label="{esc(label)} score">'
            f'<span style="width:{width}%;background:var(--grade-{band})"></span></div>'
            f'<p class="pstat">{esc(summary)}</p>{substat}</div></div>'
        )
        measured_vars.append({"@type": "PropertyValue", "name": label, "value": score})

    findings = []
    for key in CATEGORY_ORDER:
        cat = artifact["categories"].get(key, {})
        if cat.get("status") == "measured":
            findings.extend(cat.get("findings", []))
    rank = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    findings.sort(key=lambda f: (rank.get(f.get("severity"), 9), -f.get("count", 0)))
    findings_html = "".join(
        f'<li class="finding"><div class="finding-head">'
        f"{_finding_severity_badge(f.get('severity'))}"
        f'<span class="count">{f.get("count", 0)} {"instance" if f.get("count", 0) == 1 else "instances"}</span></div>'
        f'<p class="what">{esc(f.get("what", ""))}</p><p class="why">{esc(f.get("why", ""))}</p>'
        f'<p class="how"><strong>Fix:</strong> {esc(f.get("fix", ""))} <em>({esc(f.get("effort", ""))})</em></p>'
        f"{_effort_band_html(str(f.get('code', '')), effort_bands)}"
        f'<p class="code">Finding code: {esc(f.get("code", ""))}{_fix_guide_link(str(f.get("code", "")))}{_rule_ref_link(str(f.get("code", "")))}</p></li>'
        for f in findings
    )
    if findings_html:
        finding_word = "finding" if len(findings) == 1 else "findings"
        findings_block = (
            f'<p class="findings-count">{len(findings)} {finding_word}, ordered by severity.</p>'
            '<details class="evidence-drawer"><summary>Show every finding</summary>'
            f'<ul class="findings">{findings_html}</ul></details>'
        )
    else:
        findings_block = (
            '<p class="all-clear">No findings. This feed passed every measured check.</p>'
        )

    op_note = artifact.get("agency", {}).get("operating_note")
    op_html = (
        f'<p class="operating-note"><span aria-hidden="true">&#10003;</span> {esc(op_note)}</p>'
        if op_note
        else ""
    )
    # The measurement-confidence read rides on its own line only when the
    # artifact carries one, so a pre-1.5 artifact renders byte-for-byte as it
    # did before this feature.
    confidence = _confidence_section(artifact)
    confidence_block = f"\n    {confidence}" if confidence else ""
    ferry_profile = _ferry_profile_section(artifact)
    ferry_profile_block = f"\n    {ferry_profile}" if ferry_profile else ""
    _outreach_block = _outreach_section(artifact, canonical)
    _vendor_block = _vendor_section(artifact, canonical)
    _embed_block = _embed_section(agency_id, agency_name, str(overall["grade"]))
    _citation_block = _citation_section(artifact, agency_id, agency_name)
    action_links = []
    if _vendor_block:
        action_links.append(
            '<a class="report-action report-action-primary" href="#send-vendor">Send fixes</a>'
        )
    action_links.extend(
        [
            f'<a class="report-action" href="/agency/{esc(agency_id)}/board/">Board one-pager</a>',
            f'<a class="report-action" href="/agency/{esc(agency_id)}/brief/">Call brief</a>',
            f'<a class="report-action" href="/compare/?a={esc(agency_id)}">Compare</a>',
            '<a class="report-action" href="/subscribe.html">Watch this feed</a>',
            f'<a class="report-action" href="/claim/?agency={esc(agency_id)}">Correct listing</a>',
        ]
    )
    if has_fixlog:
        action_links.append(
            f'<a class="report-action" href="/agency/{esc(agency_id)}/fixes/">Clearance log</a>'
        )
    actions = (
        '<nav class="report-actions" aria-label="Scorecard actions">'
        + "".join(action_links)
        + "</nav>"
    )
    report_stops = [
        ("Overview", "#report-overview"),
        ("Fixes", "#fixes-h"),
    ]
    if artifact.get("ferry_profile"):
        report_stops.append(("Ferry profile", "#ferry-profile-h"))
    report_stops.append(("Scores", "#cats-h"))
    if map_section:
        report_stops.append(("Routes", "#map-h"))
    report_stops.extend(
        [
            ("History", "#trend-h"),
            ("Evidence", "#findings-h"),
            ("Standards", "#standards-h"),
        ]
    )
    report_route = (
        '<nav class="report-route" aria-label="On this scorecard">'
        '<p class="report-route-kicker">Report route</p>'
        '<p class="report-route-title">Sections on this page</p><ol>'
        + "".join(
            f'<li><a href="{href}"><span aria-hidden="true"></span>{label}</a></li>'
            for label, href in report_stops
        )
        + "</ol></nav>"
    )
    # The copy script is emitted once if any copyable block (outreach, vendor,
    # embed, citation) is present, so multiple buttons never double-bind.
    _copy_script = (
        _COPY_SCRIPT
        if (_outreach_block or _vendor_block or _embed_block or _citation_block)
        else ""
    )
    crumb = _breadcrumb([("Home", "/"), ("All agencies", "/agencies/"), (agency_name, None)])
    body = f"""    <div class="report-head">
    {crumb}
    <a class="backlink" href="/agencies/">&larr; All agencies</a>
    {actions}
    {_board_hero(agency_name, agency_id, artifact, history or [], dir_record)}
    {op_html}
    {_anomaly_note(history)}
    <p class="disclaimer">A data-quality and completeness lens to help an agency improve its
      <abbr title="General Transit Feed Specification">GTFS</abbr> feed. Not an official compliance
      determination from any transit program.
      <a href="/how-to-read/">New to this? How to read your scorecard.</a>
      <a href="/app/#/agency/{esc(agency_id)}">Interactive view of this scorecard.</a>
      Rubric v{esc(artifact.get("rubric_version", "—"))}, validator {esc(artifact.get("validator_version", "—"))}.</p>
    </div>
    {report_route}
    <div class="report-content">
    {_liveness_note(liveness, now)}{confidence_block}
    {_route_rule()}
    <section aria-labelledby="fixes-h">
      <h2 class="section-title" id="fixes-h">Top things to fix</h2>
      {fixes_html}
      {_finding_handoff(artifact, agency_id, f"/agency/{agency_id}/")}
      {_guided_fix_flow(artifact, agency_id, has_fixlog)}
    </section>
    {_rider_impact_section(artifact)}{ferry_profile_block}
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
    {_history_section(history, artifacts)}
    {_route_rule()}
    <section aria-labelledby="findings-h">
      <h2 class="section-title" id="findings-h">Everything we checked</h2>
      {findings_block}
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
    {_standards_section(artifact, (dir_record or {}).get("state", ""), (dir_record or {}).get("subdivision_code", ""))}
    {_route_rule()}
    {_embed_block}
    {_citation_block}
    {_copy_script}
    </div>"""
    body = "\n".join(line.rstrip() for line in body.splitlines())

    jsonld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": metadata.dataset_name,
        "description": desc,
        "url": canonical,
        "identifier": [
            {"@type": "PropertyValue", "propertyID": "GTFS Scorecard", "value": agency_id},
            *(
                [
                    {
                        "@type": "PropertyValue",
                        "propertyID": "Mobility Database",
                        "value": str((dir_record or {}).get("mdb_id")),
                    }
                ]
                if (dir_record or {}).get("mdb_id")
                else []
            ),
        ],
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": artifact.get("feed", {}).get("static_url"),
        "includedInDataCatalog": {"@type": "DataCatalog", "url": BASE_URL},
        "creator": {"@type": "Organization", "name": ORG_NAME, "url": BASE_URL},
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
    atom = (
        f'<link rel="alternate" type="application/atom+xml" '
        f'title="{esc(agency_name)} feed quality changes" href="{canonical}feed.xml">'
    )
    return _page(
        title=title,
        description=desc,
        canonical=canonical,
        body=body,
        jsonld=jsonld,
        head_extra=atom,
        country_code=str(location_record.get("country") or "US"),
        wide=True,
        main_modifier="agency-report",
    )


def _brief_trend_line(history: list[dict[str, Any]] | None) -> str:
    """One plain-language sentence on the score's direction since the last check,
    reusing the same delta logic the trend section uses. Neutral on the first
    check."""
    hist = history or []
    comparable = _current_rubric_history(hist)
    if len(comparable) < 2:
        if len(hist) >= 2:
            return (
                "The scoring methodology changed since the prior check; the trend "
                "restarts here without an improvement or regression claim."
            )
        return "First check for this agency, so there is no trend yet."
    prev, cur = comparable[-2], comparable[-1]
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
    comparable = _current_rubric_history(hist)
    if len(comparable) >= 2:
        prev, cur = comparable[-2], comparable[-1]
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
    elif len(hist) >= 2:
        rows = (
            "<p>The scoring methodology changed since the prior check. Category "
            "deltas restart with this scorecard.</p>"
        )
    cleared_html = ""
    if cleared:
        lis = "".join(f"<li>{esc(what)} ({esc(code)})</li>" for code, what in cleared)
        noun = "finding" if len(cleared) == 1 else "findings"
        cleared_html = (
            f'<p class="brief-sub">No longer reported since the last check '
            f"({len(cleared)} {noun}):</p>"
            f'<ul class="brief-cleared">{lis}</ul>'
            '<p class="fineprint">This compares feed state. It does not identify who '
            "made a change or why.</p>"
        )
    if not rows and not cleared_html:
        rows = "<p>No category changes since the last check.</p>"
    return rows + cleared_html


def _render_brief(  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
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
    location_record = dict(dir_record or {})
    location_record["country"] = location_record.get("country") or artifact.get("agency", {}).get(
        "country", "US"
    )
    location_label = _location_label(location_record) if dir_record else ""

    # Top three fixes, imperative, with the effort hint, straight from the artifact.
    fixes = artifact.get("top_fixes", [])[:3]
    if fixes:
        fix_items = "".join(
            f'<li class="brief-fix"{_finding_card_attrs(f)}>'
            f'<p class="brief-fix-do">{esc(f.get("fix", ""))}</p>'
            f'<p class="brief-fix-why">{esc(f.get("what", ""))} {esc(f.get("why", ""))}</p>'
            f'<p class="brief-fix-eta">Effort: {esc(f.get("effort", ""))}</p>'
            f"{_effort_band_html(str(f.get('code', '')), effort_bands)}</li>"
            for f in fixes
        )
        fixes_html = f'<ol class="brief-fixes">{fix_items}</ol>'
    else:
        fixes_html = "<p>Nothing urgent. This feed passed every check we translate into a fix.</p>"

    # NTD readiness verdict and pillars, recomputed from stored inputs so older
    # artifacts gain the RY2026 agency_id presence check without a rescore.
    readiness = presented_ntd_readiness(artifact) or {}
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

    # Optional agency_id-vs-NTD-ID equality line, re-worded at render time so
    # old artifacts never conflate required presence with optional equality.
    align = _current_alignment(artifact) or {}
    align_html = ""
    if align and align.get("status") != "missing":
        a_status = str(align.get("status", "unknown"))
        a_label = _NTD_ALIGN_LABELS.get(a_status, a_status)
        body = esc(str(align.get("detail", "")))
        if align.get("fix"):
            body += f" {esc(str(align.get('fix')))}"
        align_html = (
            f'<p class="brief-align"><strong>agency_id equals NTD ID (optional):</strong> '
            f"{esc(a_label)}. {body}</p>"
        )

    # Key facts: feed URL, last checked, days to expiry, feed version, contact/url
    # when the artifact carries them.
    fresh = artifact.get("categories", {}).get("freshness", {}).get("details", {})
    days = fresh.get("days_until_expiry")
    horizon_status = resolve_service_horizon_status(fresh, artifact.get("snapshot_date"))
    if isinstance(days, (int, float)) and not isinstance(days, bool):
        days = int(days)
        if horizon_status == "unusually_distant":
            end = fresh.get("effective_expiry_date")
            through = f" through {esc(str(end))}" if end else " unusually far ahead"
            expiry = (
                f"The feed states that service is published{through}. Confirm that this "
                "end date is intentional before relying on it as a maintenance signal."
            )
        else:
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
    if location_label:
        facts.append(f"<dt>Location</dt><dd>{esc(location_label)}</dd>")

    # Portfolio backlink: only when the state's rollup page is actually
    # published, so the brief never links a 404.
    portfolio_html = ""
    if where and str((dir_record or {}).get("country") or "US").upper() == "US":
        slug = str(where).lower().replace(" ", "-")
        if program_ids and slug in program_ids:
            portfolio_html = (
                f'<p class="brief-portfolio no-print">Part of the '
                f'<a href="/program/{esc(slug)}/">{esc(str(where))} portfolio</a>: '
                "see where this agency sits among the state's feeds before the call.</p>"
            )

    # The jurisdiction guideline or support resource, when one exists. It is
    # selected by ISO subdivision code, with state-name fallback for old
    # directory records.
    standards_html = ""
    country = str(
        (dir_record or {}).get("country") or artifact.get("agency", {}).get("country") or "US"
    )
    guidance = guidance_for(
        country,
        str((dir_record or {}).get("subdivision_code") or ""),
        str(where or ""),
    )
    local_guidance = guidance["jurisdiction"] or guidance["support"]
    if local_guidance:
        if local_guidance.get("kind") == "guideline":
            std_lead = f"The published guideline in {esc(str(where))} is "
        else:
            std_lead = "A local transit-data support resource is "
        standards_html = (
            '<section aria-labelledby="brief-std-h">'
            '<h2 id="brief-std-h">The bar this score answers to</h2>'
            f'<p class="brief-standards">{std_lead}'
            f'<a href="{esc(local_guidance["url"])}">{esc(local_guidance["name"])}</a>. '
            f"{esc(local_guidance['note'])}</p></section>"
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
    ntd_section = ""
    if country.upper() == "US":
        ntd_section = f"""    <section aria-labelledby="brief-ntd-h">
      <h2 id="brief-ntd-h">NTD GTFS readiness: {esc(ntd_label)}</h2>
      {ntd_html}
      {align_html}
    </section>"""
    call_prompt = (
        "confirm the feed is current and the NTD details line up"
        if country.upper() == "US"
        else "confirm the feed is current and the rider information is complete"
    )
    body = f"""    <div class="brief brief-call">
    <p class="brief-nav no-print"><a href="/agency/{esc(agency_id)}/">&larr; Back to the full scorecard</a></p>
    <header class="brief-head">
      <p class="brief-kicker">Call-prep brief &middot; checked {esc(str(artifact.get("snapshot_date", "")))}</p>
      <h1 class="brief-title">{esc(agency_name)}</h1>
      <p class="brief-grade">Grade {esc(str(overall["grade"]))} &middot; {esc(str(overall["score"]))} / 100</p>
      <p class="brief-trend">{_brief_trend_line(history)}</p>
      <p class="brief-forcall">For this call: lead with the grade and the three fixes below, then
        {call_prompt}. Each fix is framed as a next step,
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
    {_finding_handoff(artifact, agency_id, f"/agency/{agency_id}/brief/")}
    {outreach_html}
{ntd_section}
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
    body = "\n".join(line.rstrip() for line in body.splitlines())
    scope_detail = "NTD readiness" if country.upper() == "US" else "guidance"
    desc = (
        f"Call-prep brief for {agency_name}: grade {overall['grade']}, top fixes, "
        f"{scope_detail}, and key feed facts on one page."
    )
    title = f"{agency_name} call-prep brief — GTFS Scorecard"
    return _page(
        title=title,
        description=desc,
        canonical=canonical,
        body=body,
        robots="noindex,follow",
        country_code=country,
    )


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
    country = str(
        (dir_record or {}).get("country") or artifact.get("agency", {}).get("country") or "US"
    )

    # Progress first. A compatible later check can show that a finding is no
    # longer reported, but not who acted or why.
    cleared = _cleared_findings(prev_artifact, artifact)
    if cleared:
        wins = "".join(f"<li>{esc(what)}</li>" for _code, what in cleared)
        noun = "finding" if len(cleared) == 1 else "findings"
        progress_html = (
            f"<p>Since the previous compatible check, {len(cleared)} {noun} "
            f"{'was' if len(cleared) == 1 else 'were'} no longer reported:</p>"
            f'<ul class="brief-cleared">{wins}</ul>'
            '<p class="fineprint">This records feed state, not who made a change or why.</p>'
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
            f'<li class="brief-fix"{_finding_card_attrs(f)}>'
            f'<p class="brief-fix-do">{esc(f.get("fix", ""))}</p>'
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

    who_makes = ""
    tool = detect_tool(artifact.get("feed", {}).get("static_url"))
    if tool and fixes:
        who_makes = f'<p class="brief-fix-why">{esc(tool.fix_path)}</p>'

    body = f"""    <div class="brief brief-board">
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
    {_finding_handoff(artifact, agency_id, f"/agency/{agency_id}/board/")}
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
    return _page(
        title=title,
        description=desc,
        canonical=canonical,
        body=body,
        robots="noindex,follow",
        country_code=country,
    )


def _receipt_anchor(receipt: dict[str, str]) -> str:
    """A stable fragment id for one receipt, so its link survives re-renders."""
    return f"r-{receipt.get('cleared', '')}-{receipt.get('code', '')}"


def _render_fixlog_page(
    artifact: dict[str, Any],
    receipts: list[dict[str, str]],
    dir_record: dict[str, Any] | None = None,
    seo_metadata: AgencySeoMetadata | None = None,
) -> str:
    """The durable clearance log (/agency/<id>/fixes/), newest first.

    Each receipt says only that one compatible check found a code and a later
    check did not. It is a citable check result, not causal proof that a named
    agency, vendor, or intervention produced the change.
    """
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
      <h1 class="page-title">Finding clearance log: {esc(agency_name)}</h1>
      <p class="page-lede">A dated record of findings that appeared in one compatible
      check and were absent from a later one. Each entry keeps its own link so the check
      result can be cited without guessing who changed the feed or why.</p>
    </header>
    <section aria-labelledby="fixlog-h">
      <h2 class="section-title" id="fixlog-h">{len(receipts)} verified finding {"clearance" if len(receipts) == 1 else "clearances"}</h2>
      <ul class="cleared-list">{"".join(items)}</ul>
      <p class="fineprint">Verified means the later check used the same complete producer
      contract, measured the finding's category, and stopped reporting its code. It does
      not establish who acted, why the feed changed, or how much work it took. A finding
      that returns and clears again appears as a separate entry.</p>
      <p class="fixloop-close">This is the comparable-feed check in the guided change flow.
      Pair a clearance with the owner or vendor's action record when you need evidence of a
      specific intervention. <a href="/agency/{esc(agency_id)}/">Return to the current scorecard</a>.</p>
    </section>"""
    metadata = seo_metadata or _agency_seo_metadata(
        agency_name,
        location_label=_location_label(dir_record),
    )
    report_suffix = " GTFS quality report"
    if not metadata.title.endswith(report_suffix):
        raise ValueError(f"agency SEO title has an unexpected shape for {agency_name!r}")
    # The planned title is corpus-unique and reserves 20 characters for the
    # report suffix. Reusing its complete identity stem preserves location or
    # feed disambiguation, while the shorter clearance suffix remains bounded.
    identity = metadata.title.removesuffix(report_suffix)
    title = f"{identity} GTFS clearance log"
    clearance_label = "clearance" if len(receipts) == 1 else "clearances"
    desc = (
        f"Dated, linkable record of {len(receipts)} finding {clearance_label} "
        f"observed for {identity}."
    )
    if len(title) > 60 or len(desc) > 155:
        raise ValueError(f"fix-log SEO metadata exceeds its length budget for {agency_name!r}")
    country = str(
        (dir_record or {}).get("country") or artifact.get("agency", {}).get("country") or "US"
    )
    return _page(
        title=title,
        description=desc,
        canonical=canonical,
        body=body,
        country_code=country,
    )


def _recommendations_section(artifact: dict[str, Any]) -> str:
    """Beyond-the-grade opportunities (fares, on-demand service) attached to the
    artifact at score time. These do not affect the grade; empty when there is
    nothing to suggest. Accessibility-depth items (EXP-05) are excluded here --
    they get their own celebrated presentation in the Rider experience card's
    accessibility sub-score (see `_accessibility_depth_signals`), not this
    generic list, per the ideation item's "celebrated sub-score" bar."""
    recs = [
        r for r in (artifact.get("recommendations") or []) if r.get("category") != "accessibility"
    ]
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
    """Describe the safe mechanical subset that a user can run locally.

    The autofix engine (autofix.py) makes only changes that have one certain
    edit (surrounding whitespace, shouting stop and route names) and leaves the
    feed otherwise byte-for-byte. Legacy artifacts may carry a public download
    URL, but this renderer deliberately ignores it: the service does not publish
    modified copies of agency feeds. Empty when the artifact carries no autofix
    block or found nothing to change."""
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
    action = (
        '<p class="autofix-cli">Run it locally on a copy of the feed you control: '
        "<code>scorecard autofix &lt;feed.zip&gt; --out corrected.zip</code></p>"
    )
    return (
        '<section aria-labelledby="autofix-h"><h2 class="section-title" id="autofix-h">'
        "Safe fixes you can run locally</h2>"
        '<p class="page-lede">The local command applies only these mechanical changes to a copy '
        "you control. The scorecard does not publish a modified feed. Review the diff before you "
        "publish through your usual process.</p>"
        f'<ul class="autofix-list">{"".join(rows)}</ul>{action}</section>'
    )


def _anomaly_note(history: list[dict[str, Any]] | None) -> str:
    """A heads-up when the most recent check looks like a transient glitch rather
    than a real change (a one-day cliff or a calendar that jumped backward), so a
    reader doesn't over-react to a vendor export blip. Empty when nothing is off."""
    anomaly = latest_anomaly(current_producer_contract_suffix(history or []))
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
_NTD_PILLAR_NAMES = {
    "published": "Published",
    "valid": "Valid",
    "current": "Current",
    "agency_id": "agency_id provided",
}

# Equality between agency_id and the five-digit NTD ID is optional, separate
# from the required agency_id presence pillar, and carries no score. A mismatch
# therefore reads neutrally. A missing value is handled by the readiness pillar
# and the equality row is omitted.
_NTD_ALIGN_LABELS = {
    "aligned": "Equal",
    "mismatch": "Different (allowed)",
    "missing": "Not available",
    "unknown": "Not checked yet",
}
_NTD_ALIGN_CLASSES = {
    "aligned": "ntd-ready",
    "mismatch": "ntd-unknown",
    "missing": "ntd-unknown",
    "unknown": "ntd-unknown",
}


def _current_alignment(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """The agency_id / NTD-ID equality block, re-worded at render time.

    Artifacts store the alignment verdict's prose at score time, so a feed not
    re-scored since the July 2025 final-rule copy fix can still carry the old
    prescriptive "should be your NTD ID by report year 2026" text. The stored
    inputs (feed_agency_ids, ntd_id) let us recompute the current wording here,
    so every rendered page distinguishes required agency_id presence from
    optional equality regardless of artifact age. The stored block is the
    fallback when the inputs are absent."""
    align = artifact.get("ntd_id_alignment")
    if not align:
        return None
    ids = align.get("feed_agency_ids")
    if isinstance(ids, list):
        from .ntd import assess_id_alignment

        return assess_id_alignment([str(v) for v in ids], str(align.get("ntd_id") or "")).to_dict()
    return dict(align)


def _ntd_id_alignment_html(artifact: dict[str, Any]) -> str:
    """Render the optional NTD-ID equality line when it can be compared.

    RY2026 requires agency_id presence and a P-50 crosswalk, but not equality to
    the five-digit NTD ID. Missing presence is already shown as a readiness
    pillar, so this neutral, zero-deduction row is omitted when there is no value
    to compare. It is also absent for artifacts that predate the check."""
    align = _current_alignment(artifact)
    if not align or align.get("status") == "missing":
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
        f'<dt>agency_id equals your NTD ID (optional) <span class="ntd-status {cls}">'
        f"{esc(label)}</span></dt><dd>{body}</dd></dl>"
    )


def _current_shapes_readiness(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """The shapes readiness block, re-worded at render time from the stored trip
    counts, the same way ``_current_alignment`` re-words the agency_id check —
    so a wording fix reaches every page without a rescore."""
    shapes = artifact.get("shapes_readiness")
    if not shapes:
        return None
    total = shapes.get("total_trips")
    with_shape = shapes.get("trips_with_shape")
    if isinstance(total, int) and isinstance(with_shape, int):
        from .ntd import assess_shapes_readiness

        return assess_shapes_readiness(total, with_shape).to_dict()
    return dict(shapes)


def _shapes_readiness_html(artifact: dict[str, Any]) -> str:
    """Render the shapes.txt readiness line, when the check ran for this feed.

    FTA's July 2025 final rule requires shapes.txt from Reduced, Rural, and
    Tribal NTD reporters starting Report Year 2026 (Full Reporters, RY2025).
    Absent for artifacts that predate the check."""
    shapes = _current_shapes_readiness(artifact)
    if not shapes:
        return ""
    status = str(shapes.get("status", "not_ready"))
    label = _NTD_LABELS.get(status, status)
    detail = str(shapes.get("detail", ""))
    fix = str(shapes.get("fix", ""))
    body = esc(detail)
    if fix:
        body += f" {esc(fix)}"
    return (
        '<dl class="standards-list">'
        f'<dt>shapes.txt covers your trips <span class="ntd-status ntd-{status}">'
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
    'is my feed ready?' read. Four pillars (published, valid, current, agency_id),
    each labelled in text as well as color so status never relies on color alone.

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
        '<abbr title="National Transit Database">NTD</abbr> GTFS readiness '
        f'<span class="ntd-status ntd-{readiness.status}">{esc(overall)}</span></h2>'
        f"{note_html}"
        f'<p class="page-lede">{esc(readiness.summary)}</p>'
        f'<dl class="standards-list">{"".join(rows)}</dl>'
        f"{_ntd_id_alignment_html(artifact)}"
        f"{_shapes_readiness_html(artifact)}"
        '<p class="plain-summary"><strong>In plain words:</strong> if you report to the federal '
        "transit database, you have to publish a working, up-to-date feed, provide a stable "
        "agency_id for each represented reporter, and confirm the feed and P-50 crosswalk each "
        "year. This box is a heads-up; your filings are the official check.</p>"
        '<p class="fineprint">A readiness signal mapping this feed to the '
        '<a href="https://www.transit.dot.gov/ntd">'
        '<abbr title="Federal Transit Administration">FTA</abbr> National Transit Database</a> GTFS '
        "requirement (Report Year 2023 onward: a public, valid, current feed, certified "
        'annually on the <abbr title="FTA NTD certification form D-10">D-10</abbr>). For RY2026, '
        "each represented reporter needs a stable agency_id, unique within the feed and "
        "crosswalked to its five-digit NTD ID on P-50; the values do not need to be equal. "
        "FTA also requires shapes.txt in the published GTFS: Full Reporters from Report "
        "Year 2025, and Reduced, Rural, and Tribal Reporters from Report Year 2026. Not an "
        "official determination; your certification is the official check.</p></section>"
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
    """Live predictions versus schedule from the last full realtime sample: how far arrival
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
        '<h2 class="section-title" id="rta-h">Live predictions vs schedule</h2>'
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
    from .mode_language import adapt_text, boarding_place_noun, language_kind

    kind = language_kind(artifact)
    place = boarding_place_noun(artifact)
    rows = []
    for crit in mark.criteria:
        name = _CONFORMANCE_NAMES.get(crit.key, crit.key)
        status = "ntd-ready" if crit.met else "ntd-not_ready"
        label = "Met" if crit.met else "Not yet"
        rows.append(
            f'<dt>{name} <span class="ntd-status {status}">{label}</span></dt>'
            f"<dd>{esc(adapt_text(crit.detail, kind))}</dd>"
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
        f'<p class="page-lede">{esc(adapt_text(mark.summary, kind))}</p>'
        f"{seal}"
        f'<dl class="standards-list">{"".join(rows)}</dl>'
        '<p class="plain-summary"><strong>In plain words:</strong> earn this mark when your feed '
        f"passes validation, has not expired, and says whether nearly every {place} and trip is "
        "wheelchair accessible.</p>"
        '<p class="fineprint">A pass credential for a feed that is valid, current, and states '
        f"wheelchair access on nearly every {place} and trip. Accessibility here measures what the "
        f"feed publishes, not whether a {place} is physically usable. "
        '<a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/conformance.md">'
        "How the conformance mark works.</a></p></section>"
    )


def _numeric_percent(value: Any) -> float | None:
    """``value`` as a percentage, or None when it isn't really one.

    Excludes bool even though ``isinstance(True, int)`` is True in Python: a
    future refactor that stores a plain "meets the floor" flag under a details
    key this reads must not silently pass as a percentage here.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and math.isfinite(value):
        return float(value)
    return None


def _california_guideline_checklist(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """The California Minimum GTFS Guidelines v2.0 Data Process Checklist, item
    by item, scored from data this scorecard already computes -- no new metric,
    per E11/03-A7's own scope. Each item's ``met`` is True/False when this tool
    can honestly check it, or None when it cannot (the guideline covers ground
    the scorecard does not, by design: it wraps the canonical validator and
    scores rider-facing completeness, it does not run a second GTFS-Realtime
    validator or track publish-cadence history). Wording and grouping mirror
    the checklist's own three sections (fetched and verified 2026-07-05; see
    docs/crosswalk.md) so a reader can match an item back to the source.
    """
    comp = artifact.get("categories", {}).get("completeness", {})
    comp_measured = comp.get("status") == "measured"
    comp_codes = {f.get("code") for f in comp.get("findings", [])} if comp_measured else set()
    comp_details = comp.get("details", {}) if comp_measured else {}

    correctness = artifact.get("categories", {}).get("correctness", {})
    errors: int | None = None
    if correctness.get("status") == "measured":
        errors = sum(
            1
            for f in correctness.get("findings", [])
            if str(f.get("severity", "")).upper() == "ERROR"
        )

    reachable = artifact.get("feed", {}).get("reachable")

    access = comp_details.get("accessibility") or {}
    stops_num = _numeric_percent(access.get("stops_stated_pct"))
    trips_num = _numeric_percent(access.get("trips_stated_pct"))
    wheelchair_met: bool | None = None
    wheelchair_detail = "Accessibility completeness has not been measured."
    if stops_num is not None and trips_num is not None:
        wheelchair_met = stops_num >= 90 and trips_num >= 90
        wheelchair_detail = (
            f"States wheelchair access on {round(stops_num)}% of "
            f"{('terminals' if artifact.get('mode_profile', {}).get('ferry_only') is True else 'stops')} and "
            f"{round(trips_num)}% of trips."
        )

    shapes = _current_shapes_readiness(artifact)
    shapes_met = shapes.get("status") == "ready" if shapes else None

    has_fares = comp_details.get("has_fares") if comp_measured else None
    fare_free = comp_details.get("fare_free") if comp_measured else None
    fares_met = True if fare_free else (bool(has_fares) if has_fares is not None else None)

    contact_met = "scorecard_no_feed_contact" not in comp_codes if comp_measured else None

    return [
        {
            "section": "GTFS Schedule",
            "label": "Publish GTFS Schedule at a stable, automatically-fetchable URL",
            "met": bool(reachable) if reachable is not None else None,
            "detail": "The published feed URL downloaded at the last check."
            if reachable
            else "The published feed URL did not download at the last check."
            if reachable is False
            else "This feed has not yet been checked for reachability.",
        },
        {
            "section": "GTFS Schedule",
            "label": "Implement required fields: Fares v2, text-to-speech stop names, "
            "shapes.txt, wheelchair_boarding, and Pathways where applicable",
            "met": None,
            "detail": "This scorecard measures wheelchair_boarding, shapes.txt coverage, "
            "fare data, and station pathways separately, below; it does not check the "
            "Fares v2 format specifically or text-to-speech stop names.",
        },
        {
            "section": "GTFS Schedule",
            "label": "Achieve a passing score in every category of the MobilityData GTFS "
            "Grading Scheme v1",
            "met": None,
            "detail": "This scorecard automates a proxy for the Grading Scheme's rider-"
            "facing fields (see the standards crosswalk) rather than running the scheme "
            "itself, which grades by comparison to the real world by hand.",
        },
        {
            "section": "GTFS Schedule",
            "label": "Publish changes to the base schedule at least one week ahead of "
            "every service change",
            "met": None,
            "detail": "This scorecard does not track a feed's publish history, so advance "
            "notice cannot be checked.",
        },
        {
            "section": "GTFS Schedule",
            "label": "Produce no critical errors in the MobilityData GTFS Validator",
            "met": (errors == 0) if errors is not None else None,
            "detail": "Passes validation with no errors."
            if errors == 0
            else f"{errors} validator error{'s' if errors != 1 else ''} to resolve."
            if errors
            else "Validation has not run for this feed yet.",
        },
        {
            "section": "GTFS Realtime",
            "label": "Publish Trip Updates, Vehicle Positions, and Alerts feeds",
            "met": None,
            "detail": "This scorecard checks realtime reachability and freshness overall; "
            "it does not check for all three feed types individually.",
        },
        {
            "section": "GTFS Realtime",
            "label": "Update Trip Updates and Vehicle Positions at least every 20 seconds",
            "met": None,
            "detail": "This scorecard samples realtime freshness; it does not check this "
            "specific 20-second cadence.",
        },
        {
            "section": "GTFS Realtime",
            "label": "Publish information for at least 99% of vehicles in service",
            "met": None,
            "detail": "This scorecard measures the share of scheduled trips represented "
            "in TripUpdates, a related but different figure than vehicle coverage.",
        },
        {
            "section": "GTFS Realtime",
            "label": "Keep 100% of trip_ids consistent between Schedule and Realtime",
            "met": None,
            "detail": "This scorecard does not currently check trip_id consistency "
            "between the Schedule and Realtime feeds.",
        },
        {
            "section": "GTFS Realtime",
            "label": "Produce no critical errors in the Center for Urban Transportation "
            "Research realtime validator",
            "met": None,
            "detail": "This scorecard does not run the CUTR realtime validator.",
        },
        {
            "section": "Data Access & Maintenance",
            "label": "Publish accessible feed links on the agency or regional partner website",
            "met": None,
            "detail": "This scorecard does not check the agency's own website.",
        },
        {
            "section": "Data Access & Maintenance",
            "label": "Register GTFS and GTFS-Realtime feeds with transit.land and the "
            "Mobility Database",
            "met": None,
            "detail": "This scorecard does not currently check aggregator registration "
            "for this section.",
        },
        {
            "section": "Data Access & Maintenance",
            "label": "Designate a technical contact in feed_info.txt's feed_contact_email",
            "met": contact_met,
            "detail": "feed_info.txt states a technical contact."
            if contact_met
            else "feed_info.txt has no feed_contact_email or feed_contact_url."
            if contact_met is False
            else "Contact completeness has not been measured.",
        },
        {
            "section": "Rider experience (measured elsewhere on this checklist's behalf)",
            "label": "wheelchair_boarding stated on stops and trips",
            "met": wheelchair_met,
            "detail": wheelchair_detail,
        },
        {
            "section": "Rider experience (measured elsewhere on this checklist's behalf)",
            "label": "shapes.txt with a shape for every trip",
            "met": shapes_met,
            "detail": str(shapes.get("detail", ""))
            if shapes
            else "Shape coverage has not been measured for this feed.",
        },
        {
            "section": "Rider experience (measured elsewhere on this checklist's behalf)",
            "label": "Fare data published, or the service marked fare-free",
            "met": fares_met,
            "detail": "This service is marked fare-free."
            if fare_free
            else "Fare data is published."
            if fares_met
            else "No fare data is published."
            if fares_met is False
            else "Fare completeness has not been measured.",
        },
    ]


def _california_guideline_html(artifact: dict[str, Any]) -> str:
    """The California checklist, rendered as a labelled list grouped by the
    guideline's own three sections. A pass/gap/not-measured read, never a
    compliance determination -- the official checklist and its own reporting
    are the authoritative source (docs/crosswalk.md)."""
    items = _california_guideline_checklist(artifact)
    measured = [i for i in items if i["met"] is not None]
    met_count = sum(1 for i in items if i["met"])
    rows = []
    for item in items:
        if item["met"] is True:
            mark, cls = "Meets", "ntd-ready"
        elif item["met"] is False:
            mark, cls = "Gap", "ntd-not_ready"
        else:
            mark, cls = "Not measured here", "ntd-unknown"
        rows.append(
            f'<li><span class="ntd-status {cls}">{esc(mark)}</span> '
            f"<strong>{esc(item['label'])}</strong>"
            f'<p class="fineprint">{esc(item["detail"])}</p></li>'
        )
    return (
        '<details class="confidence-how"><summary>California Minimum GTFS Guidelines '
        f"checklist ({met_count} of {len(measured)} measured items met)</summary>"
        '<p class="fineprint">The state\'s own Data Process Checklist, matched item by '
        'item to what this scorecard already measures. An item marked "not measured '
        'here" is real ground the checklist covers that this tool does not check; see '
        "the official checklist for the full picture.</p>"
        f'<ul class="autofix-list">{"".join(rows)}</ul></details>'
    )


def _standards_section(
    artifact: dict[str, Any], state: str = "", subdivision_code: str = ""
) -> str:
    """How this agency's category scores line up with the standards it relates to.

    Universal GTFS references are shown globally. US agencies also receive the
    FTA NTD overlay; California receives its guideline, while selected state
    programs are labelled as support resources rather than scoring authorities.
    """
    country = str(artifact.get("agency", {}).get("country", "US"))
    guidance = guidance_for(country, subdivision_code, state)
    universal = guidance["universal"]
    national = guidance["national"]
    cw = "/crosswalk/"
    rows = []
    for key in CATEGORY_ORDER:
        cat = artifact.get("categories", {}).get(key, {})
        if cat.get("status") == "measured":
            score = f"{round(float(cat.get('score', 0)))} / 100"
        elif key == "realtime" and _realtime_unmeasured_label(cat) == "Realtime access needed":
            score = "Access needed to measure"
        else:
            score = "Not yet published"
        note = str(universal["category_notes"][key])
        if national and key in national.get("category_notes", {}):
            note += f" {national['category_notes'][key]}"
        rows.append(
            f"<dt>{esc(CATEGORY_LABELS[key])} "
            f'<span class="std-score">{esc(score)}</span></dt>'
            f"<dd>{esc(note)}</dd>"
        )
    state_std = guidance["jurisdiction"] or guidance["support"]
    state_html = ""
    if state_std:
        if state_std.get("kind") == "guideline":
            lead = (
                f"In {esc(state)}, the published guideline is "
                if state
                else "The published guideline for this jurisdiction is "
            )
        else:
            lead = "A local transit-data support resource is "
        state_html = (
            f'<p class="page-lede">{lead}'
            f'<a href="{esc(state_std["url"])}">{esc(state_std["name"])}</a>. '
            f"{esc(state_std['note'])}"
        )
        if state_std.get("kind") != "guideline":
            state_html += " This resource supports agencies; it is not a scoring authority."
        state_html += "</p>"
        if state_std.get("kind") == "guideline":
            state_html += _california_guideline_html(artifact)
    refs = list(universal["references"])
    if national:
        refs.append(national)
    ref_links = ", ".join(
        f'<a href="{esc(str(ref["url"]))}">{esc(str(ref["name"]))}</a>' for ref in refs
    )
    return (
        '<section aria-labelledby="standards-h" class="feed-details">'
        '<h2 class="section-title" id="standards-h">How this agency maps to the standards</h2>'
        f'<p class="page-lede">{esc(str(universal["note"]))} Useful references here are '
        f"{ref_links}. "
        f'Read the full <a href="{cw}">standards crosswalk</a>.</p>'
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
        f'<div><h3><a href="/agency/{esc(aid)}/"><bdi>{esc(a["name"])}</bdi></a></h3>'
        f'<p class="meta">Overall {last["score"]} out of 100 · '
        f"checked {esc(last['date'])}</p>{extra}{op}</div></li>"
    )


_AGENCY_INDEX_PAGE_SIZE = 80


def _agency_index_href(page: int) -> str:
    """Stable public URL for one human-readable directory page."""
    return "/agencies/" if page == 1 else f"/agencies/page/{page}/"


def _agency_index_groups(
    index: dict[str, Any], liveness: dict[str, dict[str, Any]]
) -> tuple[int, list[dict[str, Any]]]:
    """Directory rows grouped in their practitioner-facing reading order.

    The returned rows are already ordered. Pagination happens after grouping so
    every feed appears exactly once and the page chain stays deterministic.
    """
    agencies = sorted(index["agencies"].items(), key=lambda kv: kv[1]["name"].lower())
    lapsed: list[tuple[str, dict[str, Any], int]] = []
    stale_reachable: list[tuple[str, dict[str, Any], int]] = []
    stale_unreachable: list[tuple[str, dict[str, Any], int]] = []
    current: list[tuple[str, dict[str, Any], int | None]] = []
    for aid, agency in agencies:
        last = agency["history"][-1]
        days = last.get("days_until_expiry")
        status = expiry_status(days)
        if status == "lapsed":
            lapsed.append((aid, agency, int(days)))
        elif status == "stale":
            failures = int((liveness.get(aid) or {}).get("consecutive_failures") or 0)
            if operating_signal(status, failures) == "unreachable":
                stale_unreachable.append((aid, agency, int(days)))
            else:
                stale_reachable.append((aid, agency, int(days)))
        else:
            current.append((aid, agency, None))

    # Most recently expired first: the closest to recovery, and the most likely
    # to still be operating. Current records retain alphabetical order.
    lapsed.sort(key=lambda row: row[2], reverse=True)
    stale_reachable.sort(key=lambda row: row[2], reverse=True)
    stale_unreachable.sort(key=lambda row: row[2], reverse=True)
    return len(agencies), [
        {
            "key": "lapsed",
            "heading": "Recently lapsed",
            "note": (
                "Expired within the last year. These feeds are almost certainly still running. "
                "Re-exporting the feed with a calendar that reaches further out brings them "
                "back into trip planners."
            ),
            "rows": [
                (aid, agency, f"Feed expired {_expired_ago(days)} · likely still running")
                for aid, agency, days in lapsed
            ],
        },
        {
            "key": "stale",
            "heading": "Expired over a year ago",
            "note": (
                "Expired more than a year ago. For these, the feed URL on file is still the one "
                "listed in the Mobility Database, so the stale data is at the source: the agency "
                "or its vendor stopped refreshing the export. Worth confirming the agency still "
                "runs before reading the grade as a current failure."
            ),
            "rows": [
                (aid, agency, f"Feed expired {_expired_ago(days)} · check the feed URL")
                for aid, agency, days in stale_reachable
            ],
        },
        {
            "key": "unreachable",
            "heading": "Long unreachable",
            "note": (
                "Expired more than a year ago, and the feed URL itself has not answered the last "
                "30 checks in a row — a stronger signal than an old calendar alone. This may "
                "mean the feed moved, the listing is stale, or service has changed; we cannot "
                "tell which from here. Worth confirming directly before reading it either way."
            ),
            "rows": [
                (
                    aid,
                    agency,
                    f"Feed expired {_expired_ago(days)} · link unreachable for 30+ checks",
                )
                for aid, agency, days in stale_unreachable
            ],
        },
        {
            "key": "current",
            "heading": "Current and upcoming service",
            "note": (
                "Listed alphabetically. Each grade describes only that feed's published bytes "
                "under its stated scoring contract; this list is not a cross-feed ranking."
            ),
            "rows": [(aid, agency, "") for aid, agency, _ in current],
        },
    ]


def _agency_index_pager(page: int, page_count: int, *, label: str) -> str:
    """Compact crawlable previous/next navigation for the directory."""
    if page_count <= 1:
        return ""
    previous = (
        f'<a rel="prev" href="{_agency_index_href(page - 1)}">&larr; Previous page</a>'
        if page > 1
        else '<span aria-hidden="true">&larr; Previous page</span>'
    )
    following = (
        f'<a rel="next" href="{_agency_index_href(page + 1)}">Next page &rarr;</a>'
        if page < page_count
        else '<span aria-hidden="true">Next page &rarr;</span>'
    )
    return (
        f'<nav class="directory-pager" aria-label="{esc(label)}">{previous}'
        f'<span aria-current="page">Page {page} of {page_count}</span>{following}</nav>'
    )


def _agency_index_head_links(page: int, page_count: int) -> str:
    """HTML discovery links for the adjacent directory documents."""
    links = []
    if page > 1:
        links.append(f'<link rel="prev" href="{BASE_URL}{_agency_index_href(page - 1)}">')
    if page < page_count:
        links.append(f'<link rel="next" href="{BASE_URL}{_agency_index_href(page + 1)}">')
    return "\n  ".join(links)


def _agency_index_jump_nav(*, has_expired: bool, has_current: bool) -> str:
    """On-page links only for sections present in the current bounded page."""
    links = []
    if has_expired:
        links.append('<a href="#expired">Expired feeds on this page</a>')
    if has_current:
        links.append('<a href="#current">Current service on this page</a>')
    if not links:
        return ""
    return (
        f'<nav class="grade-jump" aria-label="Jump to section">Jump to: {" · ".join(links)}</nav>'
    )


def _render_agency_index(
    index: dict[str, Any],
    liveness: dict[str, dict[str, Any]],
    *,
    page: int = 1,
    page_size: int = _AGENCY_INDEX_PAGE_SIZE,
) -> str:
    """Render one bounded page of the crawlable agency directory."""
    total, groups = _agency_index_groups(index, liveness)
    page_count = max(1, math.ceil(total / page_size))
    if page < 1 or page > page_count:
        raise ValueError(f"directory page {page} is outside 1..{page_count}")

    flat_rows: list[tuple[str, str, dict[str, Any], str]] = []
    group_by_key = {str(group["key"]): group for group in groups}
    for group in groups:
        flat_rows.extend(
            (str(group["key"]), aid, agency, note) for aid, agency, note in group["rows"]
        )
    start = (page - 1) * page_size
    page_rows = flat_rows[start : start + page_size]
    end = start + len(page_rows)

    rows_by_group: dict[str, list[tuple[str, dict[str, Any], str]]] = {}
    for key, aid, agency, note in page_rows:
        rows_by_group.setdefault(key, []).append((aid, agency, note))

    expired_keys = ("lapsed", "stale", "unreachable")
    expired_total = sum(len(group_by_key[key]["rows"]) for key in expired_keys)
    expired_groups = []
    for key in expired_keys:
        selected = rows_by_group.get(key, [])
        if not selected:
            continue
        group = group_by_key[key]
        rows = "".join(_index_card(aid, agency, note) for aid, agency, note in selected)
        expired_groups.append(
            f'<section aria-labelledby="{key}-h">'
            f'<h3 class="section-sub" id="{key}-h">{esc(group["heading"])} '
            f'<span class="grade-count">{len(selected)} on this page · '
            f"{len(group['rows'])} total</span></h3>"
            f'<p class="group-note">{esc(group["note"])}</p>'
            f'<ul class="agency-list">{rows}</ul></section>'
        )
    expired_section = ""
    if expired_groups:
        expired_section = (
            '<section class="expired-panel" aria-labelledby="expired">'
            '<h2 class="section-title" id="expired">Expired feeds '
            f'<span class="grade-count">{expired_total} total</span></h2>'
            '<p class="page-lede">A feed whose calendar has run out is invisible to trip '
            "planners even while service continues. These are pulled out of the current-service "
            "list so the fixable ones are easy to find.</p>"
            f"{''.join(expired_groups)}</section>"
        )

    current_section = ""
    selected_current = rows_by_group.get("current", [])
    if selected_current:
        current_group = group_by_key["current"]
        rows = "".join(_index_card(aid, agency, note) for aid, agency, note in selected_current)
        current_section = (
            '<section aria-labelledby="current">'
            '<h2 class="section-title" id="current">Current and upcoming service '
            f'<span class="grade-count">{len(selected_current)} on this page · '
            f"{len(current_group['rows'])} total</span></h2>"
            f'<p class="group-note">{esc(current_group["note"])}</p>'
            f'<ul class="agency-list">{rows}</ul></section>'
        )

    canonical_path = _agency_index_href(page)
    canonical = f"{BASE_URL}{canonical_path}"
    page_suffix = f", page {page}" if page > 1 else ""
    title = f"Agency scorecards{page_suffix} — GTFS Scorecard"
    desc = (
        f"Page {page} of {page_count} for {total} published GTFS feed scorecards, "
        "including current, recently expired, and older published feeds."
    )
    jump_nav = _agency_index_jump_nav(
        has_expired=bool(expired_groups),
        has_current=bool(selected_current),
    )
    pager_top = _agency_index_pager(page, page_count, label="Directory pages before the list")
    pager_bottom = _agency_index_pager(page, page_count, label="Directory pages after the list")
    body = f"""    {_breadcrumb([("Home", "/"), ("All agencies", None)])}
    <h1 class="page-title">Agency scorecards</h1>
    <p class="page-lede">{total} published feed scorecards, each with a
    <abbr title="General Transit Feed Specification">GTFS</abbr> data
    quality grade and the fixes to start with.</p>
    <p class="fineprint">Showing records {start + 1 if total else 0}&ndash;{end} of {total}.
      Use the page links to browse the complete directory.</p>
    <nav class="grade-jump" aria-label="Other views of the same scorecards">Same scorecards, other
    views: <a href="/app/">live search and filters</a> · <a href="/map/">on a map</a> ·
    <a href="/routes/">every route</a> · <a href="/compare/">compare two</a></nav>
{pager_top}
{jump_nav}
{expired_section}
{current_section}
{pager_bottom}"""
    return _page(
        title=title,
        description=desc,
        canonical=canonical,
        head_extra=_agency_index_head_links(page, page_count),
        body=body,
        wide=True,
    )


def _grade_distribution_bar(dist: dict[str, Any], total: int) -> str:
    """One labelled segment per grade, sized by share -- the Python twin of
    app.js's gradeDistributionBar, so the static program page shows the same
    shape crawlers and no-JS visitors get everywhere else. Decorative fill, but
    each segment is a labelled list item so the same information (grade,
    count, share) is available without color; empty when there is nothing to
    show a distribution over."""
    if not total:
        return ""
    segs = []
    for g in _GRADES:
        raw = dist.get(g)
        n = raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
        if not n:
            continue
        pct = round(100 * n / total)
        segs.append(
            f'<li class="grade-seg {_grade_class(g)}" style="--share:{pct}" '
            f'title="{n} graded {g} ({pct}%)"><span class="seg-fill" aria-hidden="true">'
            f'</span><span class="seg-label">{g} <span class="seg-n">{n}</span></span></li>'
        )
    return (
        '<ul class="grade-distribution" aria-label="Grade distribution across this program">'
        f"{''.join(segs)}</ul>"
    )


def _rollup_percentile_context(payload: dict[str, Any]) -> str:
    """Compatibility shim for retired public program-percentile output."""
    del payload
    return ""


def _comparison_contract_text(comparison: dict[str, Any]) -> str:
    """Human-readable producer contract behind a cross-feed aggregate."""
    rubric = esc(comparison.get("required_rubric_version") or "current")
    profile = esc(comparison.get("required_scoring_profile_id") or "current")
    validator = esc(comparison.get("required_validator_version") or "current")
    reader_profile = esc(comparison.get("required_reader_archive_profile") or "raw-v1")
    raw_categories = comparison.get("required_measured_categories") or []
    categories = [
        esc(CATEGORY_LABELS.get(str(category), str(category))) for category in raw_categories
    ]
    measured = ", ".join(categories) if categories else "one shared measured-category set"
    return (
        f"rubric {rubric}, scoring profile {profile}, MobilityData gtfs-validator "
        f"{validator}, reader archive profile {reader_profile}, and measured categories {measured}"
    )


def _guarded_comparison_count(payload: dict[str, Any]) -> int:
    """A cross-feed denominator only when both public count fields agree.

    The aggregate APIs carry a convenient top-level count and the same count in
    their auditable ``comparison`` block.  Rendering fails closed when either is
    missing, malformed, or stale so a legacy metric cannot appear beside a new
    zero-cohort disclaimer.
    """
    raw_comparison = payload.get("comparison")
    comparison = raw_comparison if isinstance(raw_comparison, dict) else {}
    nested = comparison.get("eligible_count")
    declared = payload.get("comparison_eligible_count")
    if not (
        isinstance(nested, int)
        and not isinstance(nested, bool)
        and isinstance(declared, int)
        and not isinstance(declared, bool)
        and nested == declared
        and nested > 0
    ):
        return 0
    return nested


def _render_rollup(rollup: dict[str, Any]) -> str:
    rid = rollup["rollup"]["id"]
    rname = rollup["rollup"]["name"]
    canonical = f"{BASE_URL}/program/{rid}/"
    desc = (
        f"{rname}: GTFS data quality across {rollup['agency_count']} feed scorecards, "
        f"attention work first, with {rollup['needs_attention']} needing attention and the "
        "fixes shared across the group."
    )
    rows_parts = []
    for m in rollup["members"]:
        top_fix_code = _safe_finding_code(m.get("top_fix_code"))
        handoff_link = (
            f' · <a class="program-next" href="{esc(_finding_url(f"/agency/{m['id']}/", top_fix_code))}">'
            "Open next finding</a>"
            if top_fix_code
            else ""
        )
        attn = (
            f' <span class="pill-warn">{esc(m.get("attention_reason") or "needs attention")}</span>'
            if m.get("needs_attention")
            else ""
        )
        rows_parts.append(
            f'<li class="program-row"><span class="grade-chip {_grade_class(m["grade"])}">'
            f'{esc(m["grade"])}<span class="visually-hidden"> grade</span></span>'
            f'<div><h3><a href="/agency/{esc(m["id"])}/">{esc(m["name"])}</a>{attn}</h3>'
            f'<p class="meta">{m["score"]} out of 100 · checked {esc(m["snapshot_date"])}'
            f"{handoff_link}</p>"
            "</div></li>"
        )
    rows = "".join(rows_parts)
    raw_comparison = rollup.get("comparison")
    comparison = raw_comparison if isinstance(raw_comparison, dict) else {}
    raw_comparable_count = comparison.get("eligible_count")
    comparable_count = (
        raw_comparable_count
        if isinstance(raw_comparable_count, int) and not isinstance(raw_comparable_count, bool)
        else 0
    )
    raw_distribution = rollup.get("grade_distribution")
    distribution = raw_distribution if isinstance(raw_distribution, dict) else {}
    distribution_total = sum(
        count
        for count in distribution.values()
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0
    )
    average_score = rollup.get("average_score")
    guarded_summary = bool(
        comparable_count > 0
        and isinstance(average_score, (int, float))
        and not isinstance(average_score, bool)
        and distribution_total == comparable_count
    )
    avg = f"{average_score} out of 100 average" if guarded_summary else "average unavailable"
    comparison_contract = _comparison_contract_text(comparison)
    dist_bar = _grade_distribution_bar(distribution, comparable_count) if guarded_summary else ""
    dist_section = (
        f'<section aria-labelledby="dist-h"><h2 class="section-title visually-hidden" '
        f'id="dist-h">Grade distribution</h2>{dist_bar}</section>'
        if dist_bar
        else ""
    )
    expired_section = _rollup_expired_section(rollup)
    shapes_section = _rollup_shapes_section(rollup)
    common_fixes_section = _rollup_common_fixes_section(rollup) if guarded_summary else ""
    if guarded_summary:
        comparison_note = (
            f"The average and grade distribution use {comparable_count} canonical, "
            "non-duplicate feed scorecards under one producer contract: "
            f"{comparison_contract}. Every member remains listed below."
        )
    else:
        comparison_note = (
            "The cross-feed average, grade distribution, and shared-fix counts are "
            "unavailable until this rollup has a complete guarded summary under "
            f"{comparison_contract}. Every member remains listed below."
        )
    # Country rollups state their denominator plainly (global_coverage.py's
    # convention): this page measures reviewed feed records, not operators or
    # a country's public transport, and never claims country coverage.
    country_label = str(
        rollup["rollup"].get("country_name") or rollup["rollup"].get("country_code") or ""
    ).strip()
    scope_html = ""
    if country_label:
        record_count = rollup["agency_count"]
        noun = "reviewed feed record" if record_count == 1 else "reviewed feed records"
        scope_html = (
            f'<p class="fineprint">Scope: {record_count} {noun} tracked in '
            f"{esc(country_label)}. This page measures those records, not operators, "
            f"routes, or all public transport in {esc(country_label)}, and it is not "
            f"a claim that GTFS Scorecard covers {esc(country_label)}.</p>"
        )
    crumb = _breadcrumb([("Home", "/"), ("All agencies", "/agencies/"), (rname, None)])
    body = f"""    {crumb}
    <a class="backlink" href="/agencies/">&larr; All agencies</a>
    <div class="score-hero">
      <div>
        <h1 class="page-title">{esc(rname)}</h1>
        <p class="overall"><strong>{rollup["agency_count"]} feed scorecards</strong> ·
          {avg} · {rollup["needs_attention"]} need attention</p>
        <p class="fineprint">{comparison_note}</p>{scope_html}
      </div>
    </div>
    {_route_rule()}
    {dist_section}
    {expired_section}
    {shapes_section}
    {common_fixes_section}
    <section aria-labelledby="members-h">
      <h2 class="section-title" id="members-h">Feed scorecards: attention first, then alphabetical</h2>
      <ul class="program-list">{rows}</ul>
    </section>"""
    body = "\n".join(line.rstrip() for line in body.splitlines())
    return _page(
        title=f"{rname} — GTFS Scorecard", description=desc, canonical=canonical, body=body
    )


def _rollup_member_row(m: dict[str, Any], note: str) -> str:
    """A program-list row for the expired worklist, with a how-long-ago flag."""
    top_fix_code = _safe_finding_code(m.get("top_fix_code"))
    handoff_link = (
        f' · <a class="program-next" href="{esc(_finding_url(f"/agency/{m['id']}/", top_fix_code))}">'
        "Open next finding</a>"
        if top_fix_code
        else ""
    )
    return (
        f'<li class="program-row"><span class="grade-chip {_grade_class(m["grade"])}">'
        f'{esc(m["grade"])}<span class="visually-hidden"> grade</span></span>'
        f'<div><h3><a href="/agency/{esc(m["id"])}/">{esc(m["name"])}</a> '
        f'<span class="pill-warn">{esc(note)}</span></h3>'
        f'<p class="meta">{m["score"]} out of 100 · checked {esc(m["snapshot_date"])}'
        f"{handoff_link}</p>"
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


def _rollup_shapes_section(rollup: dict[str, Any]) -> str:
    """A worklist of this program's members not yet covered by shapes.txt, the
    liaison-facing half of the per-agency NTD shapes readiness check (03-A1).
    FTA's July 2025 final rule requires shapes.txt covering every trip for
    Reduced, Rural, and Tribal NTD reporters by Report Year 2026 (Full
    Reporters already, RY2025); this checks the feed itself, not each
    agency's reporter type, so it is a heads-up to check against each
    agency's own filing, never a claim that a listed agency is currently
    out of compliance. Absent when nothing in the cohort has a gap, or when
    the cohort has no measured members (all non-US, or artifacts that
    predate the check)."""
    shapes = rollup.get("shapes_readiness")
    if not shapes or not (shapes["not_ready"] or shapes["at_risk"]):
        return ""
    gaps = [m for m in rollup["members"] if m.get("shapes_status") in ("not_ready", "at_risk")]
    gaps.sort(key=lambda m: (m["shapes_status"] != "not_ready", m["id"]))
    rows = "".join(
        _rollup_member_row(m, _NTD_LABELS.get(m["shapes_status"], m["shapes_status"])) for m in gaps
    )
    measured = shapes["total"] - shapes["not_measured"]
    return (
        '<section class="expired-panel" aria-labelledby="rollup-shapes-h">'
        '<h2 class="section-title" id="rollup-shapes-h">shapes.txt coverage '
        f'<span class="grade-count">{shapes["ready"]} of {measured}</span></h2>'
        '<p class="page-lede">The FTA National Transit Database requires shapes.txt covering '
        "every trip (Reduced, Rural, and Tribal reporters by Report Year 2026; Full Reporters "
        "already). These agencies are not fully covered yet. Check each one against its own "
        "NTD filing.</p>"
        f'<ul class="program-list">{rows}</ul></section>'
    )


def _rollup_common_fixes_section(rollup: dict[str, Any]) -> str:
    """The fixes this program's own agencies already share, from each member's
    top_fixes (build_rollup's common_fixes, counted the same way and already
    published in the rollup JSON, just not previously rendered anywhere). A
    liaison reads this as "one export setting would lift several agencies at
    once", the same framing top_fixes already uses per agency, applied across
    the cohort. Cross-links each code's fix guide the same way agency findings
    do. Only codes shared by more than one member appear (build_rollup already
    filters to that), so this is never a single agency's own list restated;
    absent when nothing in the cohort is shared."""
    common = rollup.get("common_fixes") or []
    if not common:
        return ""
    rid = rollup["rollup"]["id"]
    top = 10
    shown = common[:top]
    rows = "".join(
        f'<li class="event"><p><strong>{esc(item["fix"])}</strong>'
        f"{_fix_guide_link(item['code'])}</p>"
        f'<p class="meta">Shared by {item["agencies"]} agencies in this group.</p></li>'
        for item in shown
    )
    more = (
        f'<p class="fineprint">{len(common) - top} more shared fixes not shown here; see the '
        f'full list at <a href="/data/artifacts/rollups/{esc(rid)}.json">{esc(rid)}.json</a>.</p>'
        if len(common) > top
        else ""
    )
    return (
        '<section aria-labelledby="rollup-common-fixes-h">'
        '<h2 class="section-title" id="rollup-common-fixes-h">Fixes shared across this group'
        "</h2>"
        '<p class="page-lede">The same fix shows up in more than one agency\'s top 3 here, '
        "often the same export setting or scheduling-software step. Worth raising once with "
        "every agency it touches.</p>"
        f'<ul class="events">{rows}</ul>{more}</section>'
    )


# --- CommonMark rendering for the fix knowledge base ---------------------------

_FIX_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")
_AUTHORED_FRONT_MATTER = re.compile(
    r"\A---\r?\n(?P<header>.*?)(?:\r?\n)---(?:\r?\n|\Z)",
    flags=re.DOTALL,
)
_AUTHORED_DATE_KEYS = frozenset({"date_published", "date_modified"})
_MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True)
class _AuthoredMarkdown:
    """Markdown body with dates supplied and reviewed by its author."""

    body: str
    date_published: str
    date_modified: str


def _parse_authored_date(value: object, *, field: str, source: str) -> str:
    if isinstance(value, dt.datetime):
        raise ValueError(f"{source}: {field} must be an ISO date, not a timestamp")
    if isinstance(value, dt.date):
        return value.isoformat()
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{source}: {field} must use YYYY-MM-DD")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{source}: {field} is not a valid calendar date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{source}: {field} must use canonical YYYY-MM-DD")
    return value


def _load_authored_metadata(header: str, source: str) -> dict[str, object]:
    try:
        node = yaml.compose(header)
    except yaml.YAMLError as exc:
        raise ValueError(f"{source}: authored front matter is invalid YAML") from exc
    if not isinstance(node, MappingNode):
        raise ValueError(f"{source}: authored front matter must be a mapping")

    keys: list[str] = []
    for key_node, _value_node in node.value:
        if not isinstance(key_node, ScalarNode) or key_node.tag != "tag:yaml.org,2002:str":
            raise ValueError(f"{source}: authored front matter keys must be strings")
        key = key_node.value
        if key in keys:
            raise ValueError(f"{source}: duplicate authored front matter key {key!r}")
        keys.append(key)

    actual_keys = set(keys)
    unknown = sorted(actual_keys - _AUTHORED_DATE_KEYS)
    missing = sorted(_AUTHORED_DATE_KEYS - actual_keys)
    if unknown:
        raise ValueError(f"{source}: unknown authored front matter keys: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"{source}: missing authored front matter keys: {', '.join(missing)}")
    try:
        metadata = yaml.safe_load(header)
    except yaml.YAMLError as exc:
        raise ValueError(f"{source}: authored front matter is invalid YAML") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"{source}: authored front matter must be a mapping")
    return {key: metadata[key] for key in keys}


def _parse_authored_markdown(text: str, source: str) -> _AuthoredMarkdown:
    """Parse strict leading YAML dates without leaking metadata into article prose."""
    match = _AUTHORED_FRONT_MATTER.match(text)
    if match is None:
        if text.startswith("---"):
            raise ValueError(f"{source}: authored front matter has no exact closing delimiter")
        raise ValueError(f"{source}: authored Markdown must start with YAML front matter")

    metadata = _load_authored_metadata(match.group("header"), source)
    date_published = _parse_authored_date(
        metadata["date_published"],
        field="date_published",
        source=source,
    )
    date_modified = _parse_authored_date(
        metadata["date_modified"],
        field="date_modified",
        source=source,
    )
    if date_modified < date_published:
        raise ValueError(f"{source}: date_modified cannot be before date_published")
    return _AuthoredMarkdown(
        body=text[match.end() :],
        date_published=date_published,
        date_modified=date_modified,
    )


def _authored_dates_html(document: _AuthoredMarkdown) -> str:
    def visible_date(value: str) -> str:
        date = dt.date.fromisoformat(value)
        return f"{date.day} {_MONTH_NAMES[date.month]} {date.year}"

    return (
        '<p class="fineprint article-dates">Published: '
        f'<time datetime="{document.date_published}">'
        f"{visible_date(document.date_published)}</time>. "
        "Last reviewed: "
        f'<time datetime="{document.date_modified}">'
        f"{visible_date(document.date_modified)}</time>.</p>"
    )


def _insert_authored_dates(body_html: str, document: _AuthoredMarkdown) -> str:
    dates = _authored_dates_html(document)
    if "</h1>" not in body_html:
        return dates + body_html
    return body_html.replace("</h1>", f"</h1>{dates}", 1)


def _plain_html_text(fragment: str) -> str:
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", fragment))
    return re.sub(r"\s+", " ", text).strip()


def _md_to_html(md: str) -> tuple[str, str]:
    """Render trusted authored Markdown and return the body plus its first H1.

    CommonMark preserves wrapped paragraphs and list continuation lines. Raw
    HTML stays disabled so a guide cannot inject arbitrary page markup.
    """
    md = re.sub(r"\]\(([a-z0-9_]+)\.md\)", r"](/fix/\1/)", md)
    tokens = _FIX_MARKDOWN.parse(md)
    title = ""
    for index, token in enumerate(tokens[:-1]):
        next_token = tokens[index + 1]
        if token.type == "heading_open" and token.tag == "h1" and next_token.type == "inline":
            title = next_token.content.strip()
            break
    body = _FIX_MARKDOWN.render(md).strip()
    body = body.replace("<h2>", '<h2 class="section-title">')
    body = body.replace("<h3>", '<h3 class="section-subtitle">')
    body = body.replace("<table>", '<table class="leaderboard">')
    return body, title


def _fix_description(body_html: str, code: str) -> str:
    """Use the first explanatory paragraph, never the finding-code line."""
    for paragraph in re.findall(r"<p>(.*?)</p>", body_html, flags=re.DOTALL):
        text = _plain_html_text(paragraph)
        if not text or text.lower().startswith("code:"):
            continue
        if len(text) > 155:
            text = text[:152].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
        return text
    return f"What the GTFS data-quality finding {code} means and how to fix it."


def _fix_article_about(code: str) -> dict[str, str]:
    """Describe a fix article without overstating the finding's provenance."""
    link = rule_link_for(code)
    if link is not None and link.is_validator:
        notice = link.canonical or code
        name = f"GTFS validator notice {notice}"
    else:
        name = f"GTFS data-quality finding {code}"
    return {"@type": "Thing", "name": name}


def _fix_category(code: str) -> str:
    if any(term in code for term in ("calendar", "service", "feed_expiration", "feed_info")):
        return "Service dates and freshness"
    if any(term in code for term in ("wheelchair", "pathway", "accessible")):
        return "Accessibility"
    if any(term in code for term in ("shape", "stop", "route", "trip", "travel")):
        return "Routes, stops, and shapes"
    if any(term in code for term in ("fare", "currency")):
        return "Fares"
    return "Feed structure and publishing"


def _tech_article_jsonld(
    *,
    headline: str,
    description: str,
    canonical: str,
    about: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the stable identity shared by crawlable practitioner articles.

    Publication dates are intentionally outside this helper so their
    provenance and lifecycle stay with the authored-content renderer.
    """
    article: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": headline,
        "description": description,
        "url": canonical,
        "image": {
            "@type": "ImageObject",
            "url": _SOCIAL_IMAGE_URL,
            "width": _SOCIAL_IMAGE_WIDTH,
            "height": _SOCIAL_IMAGE_HEIGHT,
        },
        "author": {"@type": "Organization", "name": ORG_NAME, "url": BASE_URL},
        "publisher": {"@type": "Organization", "name": ORG_NAME, "url": BASE_URL},
        "mainEntityOfPage": canonical,
    }
    if about is not None:
        article["about"] = about
    return article


def _render_fix_index(guides: list[dict[str, str]]) -> str:
    """Topic hub for the curated GTFS errors and fixes knowledge base."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for guide in guides:
        grouped.setdefault(guide["category"], []).append(guide)
    order = [
        "Service dates and freshness",
        "Accessibility",
        "Routes, stops, and shapes",
        "Fares",
        "Feed structure and publishing",
    ]
    sections: list[str] = []
    for category in order:
        entries = grouped.get(category, [])
        if not entries:
            continue
        items = "".join(
            '<li class="finding">'
            f'<p class="what"><a href="/fix/{esc(entry["code"])}/">'
            f"{esc(entry['title'])}</a></p>"
            f'<p class="why">{esc(entry["description"])}</p>'
            f'<p class="code">Finding code: {esc(entry["code"])}</p></li>'
            for entry in entries
        )
        section_id = f"fix-{len(sections)}"
        sections.append(
            f'<section aria-labelledby="{section_id}"><h2 class="section-title" '
            f'id="{section_id}">{esc(category)}</h2><ul class="findings">{items}</ul></section>'
        )
    canonical = f"{BASE_URL}/fix/"
    body = f"""    {_breadcrumb([("Home", "/"), ("GTFS errors and fixes", None)])}
    <a class="backlink" href="/problems/">&larr; Common problems</a>
    <h1 class="page-title">GTFS errors and fixes.</h1>
    <p class="page-lede">Plain-language guides to GTFS findings and data gaps that
    affect riders most. Start with the code on your scorecard, then follow the steps and
    republish the feed.</p>
    {"".join(sections)}"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "GTFS errors and fixes",
        "description": "Plain-language guides for common GTFS findings.",
        "url": canonical,
        "hasPart": [
            {"@type": "TechArticle", "name": guide["title"], "url": f"{canonical}{guide['code']}/"}
            for guide in guides
        ],
    }
    return _page(
        title="GTFS errors and fixes — GTFS Scorecard",
        description="Plain-language guides for common GTFS findings, with rider impact, repair steps, and what to check after republishing.",
        canonical=canonical,
        body=body,
        jsonld=jsonld,
    )


def _render_fix(code: str, document: _AuthoredMarkdown) -> str:
    canonical = f"{BASE_URL}/fix/{code}/"
    body_html, title_text = _md_to_html(document.body)
    title_text = title_text or f"Fix: {code}"
    desc = _fix_description(body_html, code)
    body_html = _insert_authored_dates(body_html, document)
    crumb = _breadcrumb([("Home", "/"), ("GTFS errors and fixes", "/fix/"), (f"Fix: {code}", None)])
    after_republish = (
        '<section aria-labelledby="afterfix-h"><h2 class="section-title" id="afterfix-h">'
        "After you republish</h2>"
        "<p>Once the changed feed is live at your published URL, the next scorecard run "
        "checks it again. When the same complete producer contract no longer reports this "
        "finding, it can be recorded as a dated finding clearance. That confirms the later "
        "feed state, not who changed the feed or why.</p></section>"
    )
    fix_context = (
        f'<aside class="fix-context" id="finding-handoff" data-fix-context="{esc(code)}" hidden>'
        '<p class="handoff-kicker">Selected finding</p>'
        f"<h2>Keep {esc(code)} attached to the agency record</h2>"
        "<p>Agency record: <code data-context-agency></code>. Use this guide, publish the "
        "changed feed, then return to the selected scorecard for the comparable recheck.</p>"
        '<nav class="handoff-links" aria-label="Selected agency links">'
        '<a data-context-target="scorecard" href="/agencies/">Scorecard</a>'
        '<a data-context-target="brief" href="/agencies/">Call brief</a>'
        '<a data-context-target="board" href="/agencies/">Board view</a>'
        '<a data-context-target="history" href="/agencies/">Feed history</a>'
        "</nav></aside>"
    )
    body = f"""    {crumb}
    <a class="backlink" href="/fix/">&larr; All GTFS fixes</a>
    {fix_context}
    <article class="feed-details">{body_html}{_fix_rule_reference(code)}{after_republish}</article>
    {_FINDING_CONTEXT_SCRIPT}"""
    jsonld = _tech_article_jsonld(
        headline=title_text,
        description=desc,
        canonical=canonical,
        about=_fix_article_about(code),
    )
    jsonld["datePublished"] = document.date_published
    jsonld["dateModified"] = document.date_modified
    return _page(
        title=f"{title_text} — GTFS Scorecard",
        description=desc,
        canonical=canonical,
        body=body,
        jsonld=jsonld,
    )


def _render_crosswalk_page(document: _AuthoredMarkdown) -> str:
    """The standards crosswalk (docs/crosswalk.md) as a crawlable page.

    Previously linked only as a raw GitHub blob from agency pages; rendering it
    on-site puts it in the sitemap and gives it the same JSON-LD/meta treatment
    as every other page, for the same reason /fix/<code>/ pages exist rather
    than pointing at the Markdown source."""
    canonical = f"{BASE_URL}/crosswalk/"
    body_html, title_text = _md_to_html(document.body)
    title_text = title_text or "How the grade maps to the standards"
    para = next((re.sub("<[^>]+>", "", p) for p in re.findall(r"<p>(.*?)</p>", body_html)), "")
    desc = (
        para[:155]
        or "How the scorecard's categories map to NTD, California's "
        "guidelines, the GTFS Grading Scheme, and Google Transit."
    ).strip()
    body_html = _insert_authored_dates(body_html, document)
    crumb = _breadcrumb([("Home", "/"), ("How to read this", "/how-to-read/"), ("Crosswalk", None)])
    body = f"""    {crumb}
    <article class="feed-details">{body_html}</article>"""
    jsonld = _tech_article_jsonld(
        headline=title_text,
        description=desc,
        canonical=canonical,
    )
    jsonld["datePublished"] = document.date_published
    jsonld["dateModified"] = document.date_modified
    return _page(
        title=f"{title_text} — GTFS Scorecard",
        description=desc,
        canonical=canonical,
        body=body,
        jsonld=jsonld,
    )


def _render_claim_page() -> str:
    """Explain the evidence-backed correction and agency-claim process.

    Claims are deliberately reviewed by a person. Opening an issue proves
    neither employment nor control of a feed, so this page names the accepted
    proof paths and the public status language before collecting a request.
    """
    canonical = f"{BASE_URL}/claim/"
    issue_url = (
        "https://github.com/ChelseaKR/gtfs-scorecard/issues/new"
        "?template=claim-agency.yml&labels=agency-claim"
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("Correct or claim a listing", None)])}
    <a class="backlink" href="/agencies/">&larr; All agencies</a>
    <h1 class="page-title">Correct or claim an agency listing</h1>
    <p class="page-lede">Tell us when a name, feed URL, service status, or other
    listing detail is wrong. Agency staff can also ask to become the verified
    contact for a listing. A request is not treated as proof by itself.</p>

    {_route_rule()}
    <section aria-labelledby="correction-h"><h2 class="section-title" id="correction-h">Corrections do not require a claim</h2>
    <p>Anyone can report a factual error. Link to the agency's official website,
    public feed page, procurement record, or another source that lets a reviewer
    confirm the change. We correct supported facts without requiring the agency
    to create or maintain an account.</p></section>

    <section aria-labelledby="proof-h"><h2 class="section-title" id="proof-h">How an agency claim is verified</h2>
    <p>Use one of these proof paths. Do not put private email addresses, access
    tokens, or credentials in a public issue.</p>
    <ul>
      <li><strong>Official webpage:</strong> publish a short confirmation or the
      scorecard URL on an agency-controlled website.</li>
      <li><strong>Feed-host proof:</strong> place the one-time text supplied by a
      reviewer at the public feed host or in an adjacent public file.</li>
      <li><strong>Official-domain email:</strong> send confirmation privately from
      an agency-controlled domain after opening the issue.</li>
    </ul>
    <p>Until a reviewer checks one of those paths, the request remains
    <strong>unverified</strong>. Verification confirms the contact's relationship
    to the listing; it does not endorse the score or change the rubric.</p></section>

    <section aria-labelledby="review-h"><h2 class="section-title" id="review-h">What happens next</h2>
    <ol>
      <li>Open a request and describe the exact correction or claim.</li>
      <li>A maintainer checks the public evidence and may ask for one missing detail.</li>
      <li>The underlying registry is changed in a reviewed pull request, leaving a public audit trail.</li>
      <li>The next scoring run republishes the listing. Removal requests are handled under the same policy.</li>
    </ol>
    <p><a class="download-btn" id="claim-issue-link" href="{issue_url}">Open a correction or claim request</a></p>
    <p class="fineprint">Public issues are appropriate for public facts only. For
    private proof, open the issue without the private detail and use the maintainer
    contact it provides.</p></section>

    <script>
    (function () {{
      var agency = new URLSearchParams(window.location.search).get("agency");
      if (!agency || !/^[a-z0-9][a-z0-9-]{{0,119}}$/.test(agency)) return;
      var link = document.getElementById("claim-issue-link");
      link.href += "&title=" + encodeURIComponent("Correct or claim: " + agency);
      var note = document.createElement("p");
      note.className = "fineprint";
      note.textContent = "Listing selected: " + agency;
      link.parentNode.insertBefore(note, link);
    }})();
    </script>"""
    return _page(
        title="Correct or claim a transit agency listing | GTFS Scorecard",
        description=(
            "Report a GTFS listing correction or verify an agency contact using "
            "public evidence, feed-host proof, or official-domain email."
        ),
        canonical=canonical,
        body=body,
        jsonld={
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "Correct or claim a transit agency listing",
            "url": canonical,
            "isPartOf": {"@type": "WebSite", "name": "GTFS Scorecard", "url": BASE_URL},
        },
    )


def _render_spanish_rider_page() -> str:
    """Spanish-first agency lookup, the first localized rider-facing surface."""
    text = load_catalog("es")
    canonical = f"{BASE_URL}/es/"
    body = f"""    <nav class="breadcrumb" aria-label="Migas de pan"><ol>
      <li><a href="/">GTFS Scorecard</a></li>
      <li><span aria-current="page">Espa&ntilde;ol</span></li>
    </ol></nav>
    <p><a href="/" hreflang="en">Read this site in English</a></p>
    <h1 class="page-title">{esc(text["spanish_page_title"])}</h1>
    <p class="page-lede">{esc(text["spanish_page_lede"])}</p>

    {_route_rule()}
    <section class="feed-details" aria-labelledby="buscar-agencia">
      <h2 class="section-title" id="buscar-agencia">Busca tu agencia</h2>
      <form id="agency-search-es" class="check-form"
            data-ready="{esc(text["agency_search_ready"])}"
            data-error="{esc(text["agency_search_error"])}"
            data-missing="{esc(text["agency_search_missing"])}">
        <label for="agency-es">{esc(text["agency_search_label"])}</label>
        <input id="agency-es" name="agency" list="agency-options-es" autocomplete="off"
               placeholder="{esc(text["agency_search_placeholder"])}" required>
        <datalist id="agency-options-es"></datalist>
        <p><button type="submit" disabled>{esc(text["agency_search_button"])}</button></p>
        <p id="agency-status-es" class="form-status" role="status" aria-live="polite">
          {esc(text["agency_search_loading"])}
        </p>
      </form>
      <noscript><p><a href="/agencies/" hreflang="en">Abre el directorio completo (en ingl&eacute;s)</a>.</p></noscript>
    </section>

    <section aria-labelledby="que-significa">
      <h2 class="section-title" id="que-significa">Qu&eacute; significa la ficha</h2>
      <p>{esc(text["spanish_page_scope"])}</p>
      <ul>
        <li><strong>Vigencia:</strong> si el calendario publicado cubre los pr&oacute;ximos d&iacute;as.</li>
        <li><strong>Experiencia del pasajero:</strong> si el feed incluye nombres, destinos y datos de accesibilidad.</li>
        <li><strong>Correcciones:</strong> acciones concretas que la agencia o su proveedor puede revisar.</li>
      </ul>
      <p>Las fichas detalladas est&aacute;n disponibles actualmente en ingl&eacute;s. Los grados,
      las fechas y los valores num&eacute;ricos no cambian con el idioma.</p>
    </section>"""
    return _page(
        title=f"{text['spanish_page_title']} | GTFS Scorecard",
        description=str(text["spanish_page_lede"]),
        canonical=canonical,
        body=body,
        lang="es",
        head_extra=(
            '<link rel="alternate" hreflang="en" href="https://gtfsscorecard.org/">\n'
            '  <link rel="alternate" hreflang="es" href="https://gtfsscorecard.org/es/">\n'
            '  <script src="/src/es.js" defer></script>'
        ),
    )


def _sitemap(urls: list[str], lastmods: dict[str, str] | None = None) -> str:
    """Render a deduplicated sitemap with truthful per-URL modification dates."""
    modified = lastmods or {}
    items = "".join(
        f"<url><loc>{esc(url)}</loc>"
        f"{f'<lastmod>{esc(modified[url])}</lastmod>' if modified.get(url) else ''}</url>"
        for url in dict.fromkeys(urls)
    )
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
    automated gate. Axe checks a representative set of page families in the accessibility
    workflow, Lighthouse checks the landing page in the publishing workflow, and browser
    tests exercise keyboard and form journeys. We also review with a keyboard. A recorded
    screen-reader walkthrough is still pending, so automated results are not presented as
    an assistive-technology attestation. You can read the full results in the
    <a href="{repo}/blob/main/docs/accessibility.md">conformance report</a> and the
    <a href="{repo}/blob/main/docs/vpat.md">508-edition <abbr title="Voluntary Product Accessibility Template">VPAT</abbr></a>.</p></section>

    <section><h2 class="section-title">Known limitations</h2>
    <p>We keep an honest list. The agency map is a convenience layer built on a
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

    <p class="page-lede" style="margin-top:2rem">Last reviewed: 13 July 2026.</p>"""
    return _page(
        title="Accessibility | GTFS Scorecard",
        description="How the GTFS Scorecard meets WCAG 2.2 AAA and Section 508, its known limitations, and how to report an accessibility barrier.",
        canonical=canonical,
        body=body,
    )


def _status_commitment_section(doc: dict[str, Any]) -> str:
    """The monitoring commitment half of /status/ (EXP-10): what
    `api/v1/status.json` says, in prose, so a consumer does not have to parse
    JSON to decide whether to depend on this feed: the cadence tiers, current
    direct-URL liveness, and the degradation policy. Extends
    FIX-11's internal run-summary outward as a stated, checkable commitment.
    Returns a fragment (no page chrome); composed into the combined /status/
    page by `_render_status` alongside `_status_evidence_section`."""
    record = doc["refresh_success_record"]
    policy = doc["degradation_policy"]
    hours = record["hours_since_last_check"]
    unreachable_after = int(policy["unreachable_after_consecutive_checks"])
    clean_pct = record.get("currently_clean_pct", record.get("success_rate_pct"))

    as_of = str(record["as_of"])
    try:
        as_of_label = dt.datetime.fromisoformat(as_of).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        as_of_label = as_of
    as_of_html = f'<time datetime="{esc(as_of)}">{esc(as_of_label)}</time>'

    tier_rows = "".join(
        f"<tr><td>{esc(t['tier'].replace('_', ' ').title())}</td>"
        f"<td>{esc(t['cadence'])}</td>"
        f"<td>{esc(t['applies_to'])}</td></tr>"
        for t in doc["commitment"]["tiers"]
    )

    if record["feeds_tracked"]:
        if all(hours.get(key) is not None for key in ("min", "median", "max")):
            check_age = f"""<p>The latest direct checks range from
        <strong>{esc(str(hours["min"]))}</strong> to
        <strong>{esc(str(hours["max"]))}</strong> hours old. The median is
        <strong>{esc(str(hours["median"]))}</strong> hours.</p>"""
        else:
            check_age = "<p>No valid direct-check timestamps are available yet.</p>"
        record_section = f"""<p>As of {as_of_html}, direct liveness state covers
        <strong>{record["feeds_tracked"]}</strong> current feed records.</p>
        <dl>
          <dt>Checking clean</dt><dd><strong>{record["healthy"]}</strong> (latest direct check succeeded)</dd>
          <dt>Recent check failure</dt><dd><strong>{record["degraded"]}</strong> (1&ndash;{unreachable_after - 1} consecutive direct checks failed)</dd>
          <dt>Flagged unreachable</dt><dd><strong>{record["unreachable"]}</strong> ({unreachable_after} or more consecutive direct checks failed)</dd>
        </dl>
        <p>Currently checking clean: <strong>{esc(str(clean_pct))}%</strong> of tracked feed records.</p>
        {check_age}
        <p class="fineprint">Direct liveness calls each configured feed URL without a mirror.
        The daily full scoring run can use the Mobility Database mirror, so the liveness counts
        here and the run totals below answer different questions.</p>"""
    else:
        record_section = (
            "<p>No direct liveness state has been recorded yet on this deployment "
            "(the intraday refresh has not run). This section fills in once it has.</p>"
        )

    policy_items = "".join(f"<li>{esc(s)}</li>" for s in policy["statements"])

    return f"""    <h2 class="section-title" id="commitment-h">Monitoring status and schedule</h2>
    <p>The schedule is the service commitment. The liveness record shows what the pipeline
    observed at each configured feed URL. Machine-readable at
    <a href="/api/v1/status.json">/api/v1/status.json</a>.</p>

    <section class="feed-details" aria-labelledby="record-h"><h3 class="section-title" id="record-h">Current feed URL liveness</h3>
    {record_section}</section>

    <section aria-labelledby="cadence-h"><h3 class="section-title" id="cadence-h">Scheduled checks</h3>
    <p>Each feed belongs to one of two direct-liveness tiers. A separate full validation is
    scheduled once daily for every registered feed. The latest-run section below records what
    that daily work completed.</p>
    <div class="table-wrap"><table><thead><tr><th scope="col">Check</th><th scope="col">Cadence</th>
    <th scope="col">Applies to</th></tr></thead><tbody>{tier_rows}</tbody></table></div></section>

    <section aria-labelledby="degradation-h"><h3 class="section-title" id="degradation-h">When a check fails</h3>
    <p>The scorecard keeps the last successful evidence available and makes the degraded state visible:</p>
    <ul>{policy_items}</ul></section>

    <p class="fineprint">This section is generated from the same liveness state used by the
    intraday refresh. It reports only observations the pipeline recorded.</p>"""


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
    <p>New checks use scorecard rubric <strong>v{esc(RUBRIC_VERSION)}</strong> on top of the
    MobilityData <abbr title="GTFS Schedule Validator">gtfs-validator</abbr> <strong>{esc(VALIDATOR_VERSION)}</strong>,
    using portable GTFS fields and published weights. California guidance informed the first profile and
    remains a local authority for California, not a worldwide compliance standard. The same validator and
    methodology version used for each stored grade is stamped on its scorecard, so older and current
    results remain traceable without implying they are directly comparable. The full method,
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
    from . import RUBRIC_VERSION

    path = _repo_root() / "data" / "artifacts" / "sensitivity.json"
    try:
        study = json.loads(path.read_text())
    except (FileNotFoundError, ValueError, OSError):
        study = None
    link = '<a href="/data/artifacts/sensitivity.json">sensitivity.json</a>'
    comparison = study.get("comparison") if isinstance(study, dict) else None
    valid_current_study = bool(
        isinstance(comparison, dict)
        and comparison.get("eligible_count") == study.get("agency_count")
        and comparison.get("eligible_count")
        and comparison.get("required_rubric_version") == RUBRIC_VERSION
        and comparison.get("required_measured_categories")
    )
    if not valid_current_study:
        return (
            "a current-contract study has not been published yet. When it runs, its headline "
            f"lands here and the full numbers are published at {link}."
        )
    factor_pct = round(float(study.get("factor", 0.2)) * 100)
    date = esc(str(study.get("generated_at", ""))[:10])
    dated = f", studied {date}" if date else ""
    return (
        f"rescoring {int(study['agency_count'])} comparison-eligible feed records under every "
        f"&plusmn;{factor_pct}% single-weight change, at most "
        f"{study.get('max_grade_change_pct', 0)}% of letter grades move{dated}. "
        f"Full numbers, per perturbation: {link}."
    )


# The methodology sandbox (EXP-06): a dependency-free widget on /how-to-read/
# that lets a reader move the four rubric weights and watch, entirely client
# side, how the grade distribution shifts. It fetches the same scoring.json the
# pipeline publishes (weights + grade bands) and the flat agencies.json (each
# agency's measured category scores), so the default weights, the band
# thresholds, and the overall-score formula all come from the published data at
# runtime -- nothing about the rubric is hardcoded here. The recompute mirrors
# score.build_scorecard exactly: overall = weighted average of the *measured*
# categories, with the weights of any unmeasured category (realtime is null for
# most agencies) renormalized out, then mapped to a letter by the grade bands'
# min_score thresholds. Only rows in the published comparison cohort enter the
# sandbox, and at the default weights nothing moves. That is visible proof the
# JS and the pipeline compute the same score without naming hypothetical movers.
_SANDBOX_JS = r"""    <script>
      (function () {
        var root = document.getElementById("sandbox");
        if (!root || !window.fetch || !window.Promise) return;
        var CATS = ["correctness", "freshness", "completeness", "realtime"];
        var GRADES = ["A", "B", "C", "D", "F"];
        var status = document.getElementById("sandbox-status");
        var summary = document.getElementById("sandbox-summary");
        var resetBtn = document.getElementById("sandbox-reset");
        var sliders = {}, outputs = {};
        CATS.forEach(function (c) {
          sliders[c] = root.querySelector('input[data-cat="' + c + '"]');
          outputs[c] = root.querySelector('output[data-cat="' + c + '"]');
        });

        var bands = null, defaults = {}, agencies = [];

        function gradeFor(score) {
          for (var i = 0; i < bands.length; i++) {
            if (score >= bands[i].min_score) return bands[i].grade;
          }
          return bands[bands.length - 1].grade;
        }

        function overallFor(a, w) {
          var num = 0, den = 0;
          for (var i = 0; i < CATS.length; i++) {
            var s = a[CATS[i]];
            if (s === null || s === undefined) continue;
            num += s * w[CATS[i]];
            den += w[CATS[i]];
          }
          return den > 0 ? num / den : 0;
        }

        function currentWeights() {
          var w = {};
          CATS.forEach(function (c) { w[c] = Number(sliders[c].value) / 100; });
          return w;
        }

        function recompute() {
          var w = currentWeights();
          CATS.forEach(function (c) {
            outputs[c].textContent = sliders[c].value + "%";
          });
          var userCounts = {}, pubCounts = {};
          GRADES.forEach(function (g) { userCounts[g] = 0; pubCounts[g] = 0; });
          var changed = 0;
          agencies.forEach(function (a) {
            // Baseline: the same formula run at the published weights, so any
            // difference below is attributable to the user's weights alone, not
            // to rounding of the published category scores. At the default slider
            // positions user weights equal published, so nothing moves -- the
            // visible proof the sandbox and the pipeline compute the same grade.
            var bo = overallFor(a, defaults);
            var pub = gradeFor(bo);
            if (pubCounts[pub] === undefined) pubCounts[pub] = 0;
            pubCounts[pub]++;
            var uo = overallFor(a, w);
            var ug = gradeFor(uo);
            userCounts[ug]++;
            if (ug !== pub) {
              changed++;
            }
          });

          var rows = GRADES.map(function (g) {
            return '<tr><td><span class="grade-chip grade-' + g.toLowerCase() +
              '">' + g + "</span></td><td>" + pubCounts[g] +
              "</td><td>" + userCounts[g] + "</td><td>" +
              (userCounts[g] - pubCounts[g] > 0 ? "+" : "") +
              (userCounts[g] - pubCounts[g]) + "</td></tr>";
          }).join("");
          summary.innerHTML =
            '<p class="sandbox-headline">' +
            (changed === 0
              ? "These are the published weights: no eligible feed record changes band."
              : changed + " of " + agencies.length +
                " eligible feed records change letter grade under these weights.") +
            "</p>" +
            '<div class="sandbox-table-scroll"><table class="sandbox-table">' +
            "<caption class=\"visually-hidden\">Comparison-eligible feed records per grade band: the sandbox's baseline at the published weights versus your weights</caption>" +
            "<thead><tr><th scope=\"col\">Grade</th><th scope=\"col\">At published weights</th>" +
            "<th scope=\"col\">Your weights</th><th scope=\"col\">Change</th></tr></thead>" +
            "<tbody>" + rows + "</tbody></table></div>";
        }

        function applyDefaults() {
          CATS.forEach(function (c) {
            sliders[c].value = Math.round((defaults[c] || 0) * 100);
          });
          recompute();
        }

        Promise.all([
          fetch("/api/v1/scoring.json").then(function (r) { return r.json(); }),
          fetch("/api/v1/agencies.json").then(function (r) { return r.json(); }),
        ]).then(function (res) {
          var scoring = res[0], agenciesDoc = res[1];
          bands = (scoring.grade_bands || []).slice().sort(function (a, b) {
            return b.min_score - a.min_score;
          });
          defaults = scoring.category_weights || {};
          agencies = (agenciesDoc.agencies || []).filter(function (a) {
            return a.comparison_eligible === true && typeof a.score === "number";
          });
          if (!agencies.length) {
            if (status) {
              status.textContent =
                "No current-contract comparison cohort is available for the sandbox yet.";
            }
            return;
          }
          CATS.forEach(function (c) {
            sliders[c].disabled = false;
            sliders[c].addEventListener("input", recompute);
          });
          resetBtn.disabled = false;
          resetBtn.addEventListener("click", applyDefaults);
          if (status) status.hidden = true;
          root.querySelector(".sandbox-controls").hidden = false;
          applyDefaults();
        }).catch(function () {
          if (status) {
            status.textContent =
              "The live sandbox could not load the scoring data. " +
              "The weights and grade bands are still described above.";
          }
        });
      })();
    </script>"""


_SANDBOX_STYLE = """    <style>
      #sandbox .sandbox-controls { display: grid; gap: 0.9rem; margin: 1rem 0; }
      #sandbox .sandbox-slider { display: grid; grid-template-columns: 10rem 1fr 3.5rem; align-items: center; gap: 0.75rem; }
      #sandbox .sandbox-slider label { font-weight: 600; }
      #sandbox .sandbox-slider input[type="range"] { width: 100%; min-height: 44px; accent-color: var(--green); }
      #sandbox .sandbox-slider output { font-variant-numeric: tabular-nums; text-align: right; color: var(--ink-soft); }
      #sandbox .sandbox-buttons { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
      #sandbox .sandbox-headline { font-weight: 600; margin: 0.75rem 0; }
      #sandbox .sandbox-table-scroll { overflow-x: auto; }
      #sandbox table.sandbox-table { border-collapse: collapse; width: 100%; max-width: 34rem; }
      #sandbox table.sandbox-table th, #sandbox table.sandbox-table td { text-align: left; padding: 0.35rem 0.75rem; border-bottom: 1.5px solid var(--line); font-variant-numeric: tabular-nums; }
      @media (max-width: 40rem) { #sandbox .sandbox-slider { grid-template-columns: 1fr; gap: 0.25rem; } #sandbox .sandbox-slider output { text-align: left; } }
    </style>"""


def _sandbox_section() -> str:
    """The interactive methodology sandbox (EXP-06): four weight sliders, a reset,
    and a live grade-distribution summary, all computed client-side from the
    published scoring.json and agencies.json. Additive to the guide page; degrades
    to the static explanation above when scripting or the data fetch is
    unavailable. The slider labels mirror the four rubric categories; their
    starting positions are placeholders that the inline JS immediately overwrites
    with the published weights it fetches at runtime (the single-source rule)."""
    labels = [
        ("correctness", "Correctness"),
        ("freshness", "Freshness"),
        ("completeness", "Rider experience"),
        ("realtime", "Realtime quality"),
    ]
    sliders = "".join(
        f'      <div class="sandbox-slider">'
        f'<label for="w-{cat}">{label}</label>'
        f'<input type="range" id="w-{cat}" data-cat="{cat}" min="0" max="100" step="1" '
        f'value="0" disabled aria-describedby="w-{cat}-out">'
        f'<output id="w-{cat}-out" data-cat="{cat}" for="w-{cat}">—</output></div>'
        for cat, label in labels
    )
    return f"""    {_route_rule()}
    <section id="sandbox" aria-labelledby="sandbox-h">
    <h2 class="section-title" id="sandbox-h">Methodology sandbox</h2>
    <p>The grade blends the four categories with fixed weights. Curious how much those
    weights matter? Move the sliders to reweight the rubric and watch how the aggregate
    grade distribution changes for the current comparison-eligible cohort. The sandbox
    never names hypothetical winners or losers. Nothing is saved and no grade on the
    site changes; this is a what-if you run in your own browser. Feed records without
    realtime data have that weight spread across the categories they do have, exactly
    as the published score does.</p>
    <p id="sandbox-status" role="status">Loading the live weights and eligible feed scores…</p>
    <div class="sandbox-controls" hidden>
{sliders}
      <div class="sandbox-buttons">
        <button type="button" id="sandbox-reset" class="download-btn" disabled>Reset to published weights</button>
      </div>
    </div>
    <div id="sandbox-summary" aria-live="polite"></div>
    </section>
{_SANDBOX_STYLE}"""


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
    It lists your stops, routes, and schedule. This tool is scheduled to download that feed once a day,
    run the canonical validator used across the GTFS ecosystem, and turn the result into a grade and a
    short list of fixes. The <a href="/status/">status page</a> shows when that work actually completed.
    It does not inspect your vehicles or judge your service, only the data file.
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

{_sandbox_section()}

    {_route_rule()}
    <section><h2 class="section-title">What to do</h2>
    <p>Start at the top of "Top things to fix." We put the most rider-affecting fix first. If your
    feed has expired, that will be fix number one, because an expired feed is invisible to riders
    even while service continues. Each fix says roughly how long it takes. You do not have to do them
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
    <section id="glossary" aria-labelledby="glossary-h"><h2 class="section-title" id="glossary-h">Glossary</h2>
    <p class="page-lede">Plain-language definitions for the abbreviations and jargon used across
    the scorecard. Each term is also defined inline the first time it appears on a page.</p>
    <dl class="standards-list">
      <dt><dfn id="g-gtfs"><abbr title="General Transit Feed Specification">GTFS</abbr></dfn></dt>
      <dd>The standard data file an agency publishes so apps can show its stops, routes, and schedule.</dd>
      <dt><dfn id="g-gtfs-rt"><abbr title="GTFS Realtime">GTFS-RT</abbr> (GTFS-Realtime)</dfn></dt>
      <dd>The live companion to GTFS: real-time trip updates, vehicle positions, and service alerts.</dd>
      <dt><dfn id="g-rt"><abbr title="realtime">RT</abbr></dfn></dt>
      <dd>Short for realtime: live arrival and position data, as opposed to the static schedule.</dd>
    </dl>
    <h3 class="section-sub">United States terms</h3>
    <p>These appear only on the site's explicitly U.S.-scoped reporting and equity views.</p>
    <dl class="standards-list">
      <dt><dfn id="g-ntd"><abbr title="National Transit Database">NTD</abbr></dfn></dt>
      <dd>The U.S. Federal Transit Administration's reporting system for transit agencies.</dd>
      <dt><dfn id="g-fta"><abbr title="Federal Transit Administration">FTA</abbr></dfn></dt>
      <dd>The United States federal agency that funds transit and runs the National Transit Database.</dd>
      <dt><dfn id="g-d10"><abbr title="FTA NTD certification form D-10">D-10</abbr></dfn></dt>
      <dd>The annual U.S. NTD form on which an agency certifies its GTFS feed.</dd>
      <dt><dfn id="g-acs"><abbr title="American Community Survey">ACS</abbr></dfn></dt>
      <dd>The U.S. Census Bureau survey used for the U.S. equity overlay's poverty and access indicators.</dd>
    </dl>
    <h3 class="section-sub">Data and implementation terms</h3>
    <dl class="standards-list">
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
    </dl></section>
{_SANDBOX_JS}"""
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

    A curator's `state` in the registry wins. The Mobility Database cohort,
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
        from .identity import normalized_mdb_id
        from .mobilitydb import load_catalog

        by_mdb = {
            normalized_mdb_id(f.mdb_id): f.subdivision
            for f in load_catalog()
            if f.mdb_id and f.subdivision
        }
    except Exception as exc:
        # The live catalog is the authoritative source, but a transient outage
        # must not silently wipe every agency's state from the rendered site.
        # Carry forward the state from the last published catalog.json instead,
        # so a render without network reproduces the previous state of record.
        print(f"::warning title=state lookup::catalog unavailable: {exc}", file=sys.stderr)
        return _published_states() | states
    for aid, agency in AGENCIES.items():
        if aid not in states and agency.mdb_id:
            sub = by_mdb.get(normalized_mdb_id(agency.mdb_id))
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


def compute_changes(
    index: dict[str, Any],
    min_score_delta: float = 1.0,
    *,
    allowed_ids: set[str] | None = None,
    required_rubric_version: str | None = None,
) -> list[dict[str, Any]]:
    """Agencies whose grade or score moved between their two most recent checks.

    The "what changed today" feed an ops consumer (a trip planner, a transit app)
    wants instead of diffing the whole catalog. Pure over the index so it is
    testable; worst regressions first, then biggest moves.
    """
    out: list[dict[str, Any]] = []
    for agency_id, entry in index.get("agencies", {}).items():
        if allowed_ids is not None and agency_id not in allowed_ids:
            continue
        hist = entry.get("history", [])
        if len(hist) < 2:
            continue
        prev, cur = hist[-2], hist[-1]
        if required_rubric_version is not None and (
            str(prev.get("rubric_version") or "") != required_rubric_version
            or str(cur.get("rubric_version") or "") != required_rubric_version
        ):
            continue
        if not same_producer_contract(prev, cur):
            continue
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


def _changes_sections(changes: list[dict[str, Any]], *, baseline_date: str | None = None) -> str:
    """The upward/downward sections of the change feed
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
                "No comparable upward moves were recorded in this snapshot."
                if up
                else "No comparable downward moves were recorded in this snapshot."
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
                f'<a class="delta-cat" href="/agency/{esc(c["id"])}/"><bdi>{esc(c["name"])}</bdi></a>'
                f'<span class="delta {cls}"><span aria-hidden="true">{arrow}</span> '
                f"{word} {delta:g} &middot; {grade}</span></li>"
            )
        return "".join(rows)

    movement = (
        '<p class="page-lede">This is the first comparable snapshot under the current '
        f"scoring contract, dated {esc(baseline_date)}. Any scores from earlier contracts "
        "are intentionally excluded, so there is no prior comparable snapshot yet.</p>"
        if not changes and baseline_date
        else _movement_balance(changes)
    )
    return f"""{movement}
    <div class="section-grid">
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
    """One United States context sentence weighting quality by rider-trips (ADR 0021).

    Rendered only when the NTD ridership snapshot matched enough feeds to be
    honest, and always with its coverage stated. A stat about trips, never a
    worldwide ranking."""
    if not impact or not impact.get("matched_ntd_reporters", impact.get("matched_agencies")):
        return ""
    matched = impact.get("matched_ntd_reporters", impact.get("matched_agencies", 0))
    total = impact.get("total_feed_records", impact.get("total_agencies", matched))
    excluded = impact.get("duplicate_feed_records_excluded", 0)
    trips = impact.get("total_annual_trips", 0)
    pct = impact.get("expired_trips_pct", 0)
    duplicate_note = (
        f"{excluded} feed records sharing an NTD ID were excluded rather than double-counted. "
        if excluded
        else ""
    )
    return (
        '<p class="page-lede"><strong>United States ridership context:</strong> '
        "among unique, unambiguous NTD reporter matches, tracked feeds carry about "
        f"<strong>{trips:,}</strong> annual rider-trips ({matched} matches across {total} "
        f"eligible feed records), and "
        f"<strong>{pct}%</strong> of those trips ride on a feed that has expired. "
        f"{duplicate_note}"
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
    """The coverage overview (/pulse/): named changes and the corpus trend.

    Absolute rankings and individual percentiles are deliberately absent. The
    retired /leaderboard/, /changes/, and /trends/ URLs redirect to the closest
    useful section. Common problems keeps its own actionable page.
    """
    del histories  # retained in the signature for direct-caller compatibility
    comparison = board.get("comparison") or {}
    raw_eligible_count = comparison.get("eligible_count")
    guarded_comparisons_available = bool(
        isinstance(raw_eligible_count, int)
        and not isinstance(raw_eligible_count, bool)
        and raw_eligible_count > 0
    )
    if guarded_comparisons_available:
        baseline_date = (
            str(trend_points[0].get("date") or "").strip() if len(trend_points) == 1 else None
        )
        changes_content = _changes_sections(changes, baseline_date=baseline_date)
        trend_content = _trend_sections(trend_points, trend_sum, improvers)
    else:
        changes_content = (
            '<p class="page-lede">Named changes are unavailable until current-contract '
            "checks create a comparable cohort. No improvement or regression claim is made "
            "for this snapshot.</p>"
        )
        trend_content = (
            '<p class="page-lede">The covered-corpus trend is unavailable until '
            "current-contract checks create a comparable cohort.</p>"
        )
    jump = (
        '<nav class="grade-jump" aria-label="Jump to section">Jump to: '
        '<a href="#changes">What changed</a> · '
        '<a href="#trend">The trend</a> · <a href="/problems/">Common problems</a></nav>'
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("Coverage overview", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Coverage overview.</h1>
    <p class="page-lede">How the public transit feeds in this site's current coverage
    are changing and whether the comparable covered corpus is getting better. This is
    not a census of any country or of the world. An absent scorecard is simply not
    covered yet.</p>
    {jump}
    <p class="fineprint">Absolute score rankings and individual percentiles are not
    published. Named changes compare a feed only with its own prior check when the rubric,
    scoring profile, validator, and measured category set are unchanged. Corpus aggregates
    use {_comparison_contract_text(comparison)}; records with unresolved duplicate identities
    are excluded.</p>
    {_ridership_impact_line(ridership_impact)}
    <section id="changes" aria-labelledby="changes-h" tabindex="-1">
      <h2 class="section-title" id="changes-h">What changed since the last check</h2>
      {changes_content}
    </section>
    {_route_rule()}
    <section id="trend" aria-labelledby="trend-h" tabindex="-1">
      <h2 class="section-title" id="trend-h">Is transit data getting better?</h2>
      {trend_content}
    </section>
    <p class="plain-summary"><strong>In plain words:</strong> this page tracks the covered
    corpus at once, not any single agency. The <a href="/problems/">most common
    problems</a> page names the recurring fixes behind these numbers. Writing about
    this data? <a href="/press/">Start with the reporter's page.</a></p>"""
    body = "\n".join(line.rstrip() for line in body.splitlines())
    return _page(
        title="Coverage overview — GTFS Scorecard",
        description=(
            "How the public GTFS feeds covered by this site are changing, and the "
            "comparable corpus trend over time."
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
    this hub remains a coverage subpage even though feature discovery now has a
    direct primary-nav entry."""
    pct_ready = ntd_payload.get("pct_ready", 0)
    monitored = rt_rollup.get("monitored_count", 0)
    universal_areas = [
        (
            "/realtime/",
            "Realtime reliability",
            f"{monitored} realtime feeds monitored",
            "Uptime and freshness for the agencies that publish GTFS-Realtime.",
        ),
        (
            "/adoption/",
            "What feeds publish",
            "Flex, fares, pathways, translations, and accessibility data",
            "Adoption of optional parts of GTFS, and how complete wheelchair-access data is.",
        ),
    ]
    us_areas = [
        (
            "/ntd/",
            "NTD GTFS readiness",
            f"{pct_ready}% of assessed U.S. feeds look ready to certify",
            "Which U.S. feeds are published, valid, current, and identified with "
            "agency_id against the FTA requirement, with a state breakdown.",
        ),
        (
            "/equity/",
            "U.S. equity overlay",
            "Where weak data meets high need",
            "A U.S.-specific view using domestic demographic sources and state geography.",
        ),
    ]

    def area_items(areas: list[tuple[str, str, str, str]]) -> str:
        return "".join(
            f'<li class="finding"><p class="what"><a href="{esc(href)}">{esc(name)}</a> '
            f'<span class="count">{esc(stat)}</span></p>'
            f'<p class="why">{esc(what)}</p></li>'
            for href, name, stat, what in areas
        )

    body = f"""    {_breadcrumb([("Home", "/"), ("Focus areas", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Focus areas.</h1>
    <p class="page-lede">Open one lens per question. Realtime reliability and GTFS
    feature adoption apply across the covered corpus. Regional policy views are
    separated below and only apply where their source data and rules do.</p>
    <h2 class="section-title">Across current coverage</h2>
    <ul class="findings">{area_items(universal_areas)}</ul>
    <h2 class="section-title">United States</h2>
    <ul class="findings">{area_items(us_areas)}</ul>
    <p class="fineprint">Every lens measures published data, never a compliance
    determination or on-the-ground service quality, and none of them changes a
    grade.</p>"""
    return _page(
        title="Focus areas — GTFS Scorecard",
        description=(
            "Worldwide GTFS quality lenses, plus clearly scoped regional policy views "
            "for jurisdictions where local source data applies."
        ),
        canonical=f"{BASE_URL}/focus/",
        body=body,
    )


def _write_catalog(write: Callable[..., None], catalog: list[dict[str, Any]]) -> None:
    """Write catalog.json and catalog.csv with row-level producer provenance."""
    from . import DATA_ATTRIBUTION, DATA_LICENSE, SCHEMA_VERSION

    rubric_versions = sorted(
        {str(row.get("rubric_version") or "").strip() or "unknown" for row in catalog}
    )
    catalog_rubric = rubric_versions[0] if len(rubric_versions) == 1 else "mixed"
    if not rubric_versions:
        catalog_rubric = "unknown"

    payload = {
        "source": BASE_URL,
        "schema_version": SCHEMA_VERSION,
        # This describes the rows actually published, not the version imported
        # by the renderer. During a methodology rollout the honest value is mixed.
        "rubric_version": catalog_rubric,
        "rubric_versions": rubric_versions,
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
        "comparison_eligible",
        "size_tier",
        "snapshot_date",
        "days_until_expiry",
        "service_horizon_status",
        "expiry_status",
        "mdb_id",
        "rubric_version",
        "scoring_profile_id",
        "scoring_profile_rubric_version",
        "validator_version",
        "reader_archive_profile",
        "feed_sha256",
        "feed_url",
        "top_fix",
        "scorecard_url",
        "country",
        "subdivision_code",
        "subdivision_name",
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
    agency_id: str,
    artifact: dict[str, Any],
    state: str = "",
    country: str = "",
    subdivision_code: str = "",
    subdivision_name: str = "",
) -> dict[str, Any] | None:
    """A GeoJSON point feature for an agency, or None when it has no geometry.

    Location fields come from the portable directory record; they ride along so
    the map and accessible list share country and subdivision filters.
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
            "subdivision_code": subdivision_code or "",
            "subdivision_name": subdivision_name or state or "",
            "has_flex": has_flex,
            # The grade letter is drawn as the marker's label so grade is never
            # carried by colour alone (WCAG 1.4.1); colour only reinforces it.
            "color": _MAP_GRADE_COLOR.get(grade, "#5a5a5a"),
            "url": f"/agency/{agency_id}/",
        },
    }


_MAP_LIB_VERSION = "4.7.1"
_MAP_TABLE_INITIAL_ROWS = 50


def _render_map_page(features: list[dict[str, Any]]) -> str:
    """The agency map page: every located agency as a point labelled with its
    grade letter and coloured by grade, rendered client-side by MapLibre over the
    keyless OpenFreeMap basemap and clustered at low zoom.

    The map is an enhancement. The conformant primary is the agency table below
    it (grade, state, score, link), reached by a 'Skip to the agency list'
    bypass before the map. A bounded first set is server-rendered; a reader can
    explicitly load the complete filterable table, or follow the crawlable
    paginated directory without JavaScript. The MapLibre canvas is marked
    aria-hidden and kept out of the tab order, so a keyboard or screen-reader
    user works the table, never the canvas (docs/vpat.md).

    Linked brushing ties each point to its row: hovering a point lights up its
    row (scrolled into view unless reduced motion is set), and hovering or
    focusing a row enlarges its point through a highlight layer, mirroring the
    agency map's routes-hi pattern. The rows' existing agency links are the tab
    stops (no extra tabindex); Space pins the highlight, Enter keeps its meaning
    and follows the link. A user-driven filter updates a live result count
    without moving focus out of the native control."""
    count = len(features)
    legend_items = "".join(
        f'<li><span class="map-dot" style="background:{color}">'
        f'<span class="map-dot-letter" aria-hidden="true">{grade}</span></span>'
        f"Grade {grade}</li>"
        for grade, color in _MAP_GRADE_COLOR.items()
    )
    # The accessible primary's bounded first set. The same sorted records become
    # the complete table only after an explicit load, keeping the initial DOM
    # stable at national scale.
    rows_data = sorted(
        (
            {
                "id": str(p.get("id", "")),
                "name": str(p.get("name", "")),
                "grade": str(p.get("grade", "?")),
                "state": str(p.get("state", "") or ""),
                "country": str(p.get("country", "") or ""),
                "subdivision_code": str(p.get("subdivision_code", "") or ""),
                "subdivision_name": str(p.get("subdivision_name", "") or ""),
                "country_name": country_name(
                    str(p.get("country", "") or ""), str(p.get("country", "") or "")
                ),
                "has_flex": bool(p.get("has_flex", False)),
                "score": p.get("score"),
            }
            for p in (f.get("properties", {}) for f in features)
        ),
        key=lambda r: r["name"].lower(),
    )
    # The agency link ties each row to its GeoJSON feature for linked brushing.
    # Do not duplicate that identifier in a data attribute: at full coverage,
    # repeated row metadata has a measurable first-paint cost.
    table_rows = "".join(
        f'<tr data-grade="{esc(r["grade"])}" '
        f'data-state="{esc(r["state"])}" '
        f'data-country="{esc(r["country"])}" '
        f'data-subdivision="{esc(r["subdivision_code"])}" '
        f'data-has-flex="{str(r["has_flex"]).lower()}">'
        f'<td><a href="/agency/{esc(r["id"])}/"><bdi>{esc(r["name"])}</bdi></a></td>'
        f"<td>{esc(r['grade'])}</td>"
        f"<td><bdi>{esc(_location_label(r)) or '&mdash;'}</bdi></td>"
        f"<td>{esc(r['score'])}</td></tr>"
        for r in rows_data[:_MAP_TABLE_INITIAL_ROWS]
    )
    # Countries are the primary scope. Every covered ISO subdivision is a
    # namespaced drill-down, so adding a country needs no renderer branch and
    # names such as Georgia cannot collide.
    countries = sorted(
        {(r["country"], r["country_name"]) for r in rows_data if r["country"]},
        key=lambda row: (row[1], row[0]),
    )
    country_opts = "".join(
        f'<option value="country:{esc(code)}">{esc(name)}</option>' for code, name in countries
    )
    subdivisions = sorted(
        {
            (
                r["subdivision_code"],
                r["subdivision_name"],
                r["country_name"],
                r["country"],
            )
            for r in rows_data
            if r["subdivision_code"] and r["subdivision_name"]
        },
        key=lambda row: (row[2], row[1], row[0]),
    )
    subdivision_name_counts = Counter((code, name.casefold()) for _, name, _, code in subdivisions)
    subdivision_options = []
    for code, name, parent, country in subdivisions:
        disambiguator = (
            f" ({esc(code)})" if subdivision_name_counts[(country, name.casefold())] > 1 else ""
        )
        subdivision_options.append(
            f'<option value="subdivision:{esc(code)}">{esc(name)}{disambiguator}, '
            f"{esc(parent)}</option>"
        )
    subdivision_opts = "".join(subdivision_options)
    legacy_states = sorted(
        {
            r["state"]
            for r in rows_data
            if r["state"] and r["country"] in ("", "US") and not r["subdivision_code"]
        }
    )
    legacy_opts = "".join(
        f'<option value="{esc(state)}">{esc(state)}, United States</option>'
        for state in legacy_states
    )
    location_opts = (
        f'<optgroup label="Countries">{country_opts}</optgroup>' if country_opts else ""
    ) + (
        f'<optgroup label="Subdivisions">{subdivision_opts}{legacy_opts}</optgroup>'
        if subdivision_opts or legacy_opts
        else ""
    )
    grade_opts = "".join(f'<option value="{g}">Grade {g}</option>' for g in _MAP_GRADE_COLOR)
    country_labels_json = json.dumps(
        {code: name for code, name in countries}, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    initial_count = min(count, _MAP_TABLE_INITIAL_ROWS)
    needs_complete_load = count > _MAP_TABLE_INITIAL_ROWS
    list_button_hidden = "" if needs_complete_load else " hidden"
    list_status = (
        f"The first {initial_count} of {count} scorecards are ready. Choose a filter or load the "
        "complete list to fetch the remaining records."
        if needs_complete_load
        else f"All {count} scorecards are ready, and the filters are available."
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("Agency map", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Agency map.</h1>
    <p class="page-lede">Every tracked feed scorecard with locatable
    <abbr title="General Transit Feed Specification">GTFS</abbr> stops, placed at the feed's
    service area, labelled with its grade letter and coloured by grade. {count} feed scorecards
    are on the map. Select a point for its grade and a link to the scorecard, or work
    the list below.</p>
    <p class="page-lede">To see the actual route lines instead of one point per feed scorecard,
    open <a href="/routes/">every route on one map</a>.</p>
    <a class="skip-link-inline" href="#agency-list">Skip to the agency list</a>
    <form class="map-filters" aria-label="Filter the map and list">
      <p class="map-filters-intro">Filter by grade, location, or flexible service. The map and the list update together.</p>
      <div class="map-filter-row">
        <label for="map-grade">Grade</label>
        <select id="map-grade" name="grade" aria-describedby="map-list-status"><option value="">All grades</option>{grade_opts}</select>
        <label for="map-state">Location</label>
        <select id="map-state" name="state" aria-describedby="map-list-status"><option value="">All locations</option>{location_opts}</select>
      </div>
      <div class="map-filter-row">
        <label><input type="checkbox" id="map-flex" name="flex" aria-describedby="map-list-status"> Offers GTFS-Flex (demand-responsive service)</label>
      </div>
    </form>
    <div class="map-load-panel">
      <button type="button" class="button button-secondary" id="map-list-load"{list_button_hidden}>
        Load the complete filterable list
      </button>
      <p id="map-list-status" class="fineprint" role="status">{esc(list_status)}
        <a href="/agencies/">Browse the paginated agency directory.</a></p>
    </div>
    <div class="map-load-panel">
      <button type="button" class="button button-secondary" id="map-load">
        Load interactive map
      </button>
      <p id="map-load-status" class="fineprint" role="status">The first scorecard rows are ready
        now. Load the map only when you want the geographic view. It also loads the complete list.</p>
    </div>
    <div id="map" class="national-map national-map-pending" aria-hidden="true"><p class="map-fallback">
      The interactive map has not loaded. Use the complete-list control or the paginated agency
      directory for the same feed records, grades, locations, and scorecard links.</p></div>
    <ul class="map-legend" aria-label="Grade colours">{legend_items}</ul>
    <p class="fineprint">Points are placed at each feed's median stop. Basemap:
      OpenFreeMap, &copy; OpenStreetMap contributors. Data: this scorecard, CC BY 4.0.</p>
    <section id="agency-list" tabindex="-1" aria-labelledby="agency-list-h">
      <h2 class="section-title" id="agency-list-h">Every feed scorecard on the map</h2>
      <p class="map-count" role="status"><span id="map-result-count">{initial_count}</span> of {count}
        feed scorecards shown.</p>
      <table class="leaderboard map-table">
        <caption class="visually-hidden">Feed scorecards on the coverage map, with grade, location,
          and score. Use the grade and location filters above to narrow the list.</caption>
        <thead><tr><th scope="col">Scorecard</th><th scope="col">Grade</th>
          <th scope="col">Location</th><th scope="col">Score</th></tr></thead>
        <tbody id="map-tbody">{table_rows}</tbody>
      </table>
    </section>
    <noscript><p class="fineprint">The first {initial_count} map records are listed above.
      Browse the <a href="/agencies/">complete paginated agency directory</a> for every
      scorecard without JavaScript.</p></noscript>
    <script>
      (function () {{
        var gradeEl = document.getElementById("map-grade");
        var stateEl = document.getElementById("map-state");
        var flexEl = document.getElementById("map-flex");
        var countEl = document.getElementById("map-result-count");
        var tbodyEl = document.getElementById("map-tbody");
        var agencyListEl = document.getElementById("agency-list");
        var listLoadEl = document.getElementById("map-list-load");
        var listStatusEl = document.getElementById("map-list-status");
        var loadEl = document.getElementById("map-load");
        var loadStatusEl = document.getElementById("map-load-status");
        var mapEl = document.getElementById("map");
        var rows = Array.prototype.slice.call(
          document.querySelectorAll("#map-tbody tr"));
        var countryNames = {country_labels_json};
        var all = null;  // the full FeatureCollection, fetched once
        var dataPromise = null;
        var rowsHydrated = {str(not needs_complete_load).lower()};
        var map = null;

        function rowAgencyId(tr) {{
          var link = tr.querySelector('a[href^="/agency/"]');
          var href = link ? link.getAttribute("href") : "";
          var match = /^\\/agency\\/([^/]+)\\/$/.exec(href);
          return match ? match[1] : "";
        }}

        function textValue(value) {{
          return value === null || value === undefined ? "" : String(value);
        }}

        function locationLabel(properties) {{
          var country = textValue(properties.country || "US").toUpperCase();
          var subdivision = textValue(properties.subdivision_name);
          var state = textValue(properties.state);
          if (country === "US") return subdivision || state || "—";
          var parent = countryNames[country] || country;
          return subdivision ? subdivision + ", " + parent : parent || state || "—";
        }}

        function tableRow(feature) {{
          var p = feature && feature.properties ? feature.properties : {{}};
          var id = textValue(p.id);
          if (!/^[a-z0-9][a-z0-9-]*$/.test(id)) return null;
          var tr = document.createElement("tr");
          tr.setAttribute("data-grade", textValue(p.grade || "?"));
          tr.setAttribute("data-state", textValue(p.state));
          tr.setAttribute("data-country", textValue(p.country));
          tr.setAttribute("data-subdivision", textValue(p.subdivision_code));
          tr.setAttribute("data-has-flex", p.has_flex ? "true" : "false");

          var nameCell = document.createElement("td");
          var link = document.createElement("a");
          link.href = "/agency/" + id + "/";
          var name = document.createElement("bdi");
          name.textContent = textValue(p.name || id);
          link.appendChild(name);
          nameCell.appendChild(link);
          tr.appendChild(nameCell);

          [textValue(p.grade || "?"), locationLabel(p), textValue(p.score)].forEach(
            function (value, index) {{
              var cell = document.createElement("td");
              if (index === 1) {{
                var bdi = document.createElement("bdi");
                bdi.textContent = value;
                cell.appendChild(bdi);
              }} else {{
                cell.textContent = value;
              }}
              tr.appendChild(cell);
            }}
          );
          return tr;
        }}

        function setFiltersDisabled(disabled) {{
          gradeEl.disabled = disabled;
          stateEl.disabled = disabled;
          if (flexEl) flexEl.disabled = disabled;
        }}

        function hydrateRows(geojson) {{
          if (rowsHydrated) return;
          var features = geojson && Array.isArray(geojson.features) ? geojson.features.slice() : [];
          features.sort(function (left, right) {{
            var a = textValue((left.properties || {{}}).name).toLowerCase();
            var b = textValue((right.properties || {{}}).name).toLowerCase();
            return a < b ? -1 : a > b ? 1 : 0;
          }});
          var fragment = document.createDocumentFragment();
          features.forEach(function (feature) {{
            var tr = tableRow(feature);
            if (tr) fragment.appendChild(tr);
          }});
          while (tbodyEl.firstChild) tbodyEl.removeChild(tbodyEl.firstChild);
          tbodyEl.appendChild(fragment);
          rows = Array.prototype.slice.call(tbodyEl.querySelectorAll("tr"));
          rowsHydrated = true;
          setFiltersDisabled(false);
          if (listLoadEl) listLoadEl.hidden = true;
          if (listStatusEl) {{
            listStatusEl.textContent =
              "Complete list loaded. Grade, location, and flexible-service filters are ready.";
          }}
        }}

        function loadData(afterRows) {{
          if (!dataPromise) {{
            dataPromise = fetch("/map.geojson", {{ headers: {{ Accept: "application/geo+json" }} }})
              .then(function (response) {{
                if (!response.ok) throw new Error("map data " + response.status);
                return response.json();
              }})
              .then(function (geojson) {{
                if (!geojson || !Array.isArray(geojson.features)) {{
                  throw new Error("map data has no feature list");
                }}
                all = geojson;
                hydrateRows(geojson);
                return geojson;
              }})
              .catch(function (error) {{
                dataPromise = null;
                throw error;
              }});
          }}
          return dataPromise.then(function (geojson) {{
            if (afterRows) afterRows();
            return geojson;
          }});
        }}

        function matches(grade, state, country, subdivision, hasFlex) {{
          var g = gradeEl.value, loc = stateEl.value, f = flexEl && flexEl.checked;
          var countryPrefix = "country:";
          var subdivisionPrefix = "subdivision:";
          var locOk = !loc ||
            (loc.indexOf(countryPrefix) === 0
              ? country === loc.slice(countryPrefix.length)
              : loc.indexOf(subdivisionPrefix) === 0
              ? subdivision === loc.slice(subdivisionPrefix.length)
              : state === loc);
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
                             tr.getAttribute("data-subdivision"),
                             tr.getAttribute("data-has-flex"));
            tr.hidden = !ok;
            if (ok) shown++;
          }});
          if (countEl) countEl.textContent = shown;
        }}

        // A changed filter updates the count in its role="status" live region
        // (see #map-result-count), which a screen reader announces on its own,
        // and the "Skip to the agency list" link jumps there on demand. So the
        // filter never moves focus: on a native <select>, keyboard arrow keys
        // fire "change" per option, and moving focus then would yank the caret
        // out of the control mid-choice (WCAG 3.2.2 On Input).
        function initMap() {{
        var reduce = window.matchMedia
          && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        var worldBounds = [[-180, -85], [180, 85]];
        map = new maplibregl.Map({{
          container: "map",
          style: "https://tiles.openfreemap.org/styles/positron",
          bounds: worldBounds,
          fitBoundsOptions: {{ padding: 16, duration: 0 }},
          keyboard: false,
          attributionControl: false
        }});
        // Take the canvas out of the tab order synchronously (not only on load),
        // so this aria-hidden map never briefly holds a focusable canvas while a
        // slower basemap style is still loading (WCAG aria-hidden-focus).
        map.getCanvas().setAttribute("tabindex", "-1");
        // No on-canvas controls: the canvas is aria-hidden and out of the tab
        // order, so it must hold nothing focusable. Scroll/pinch zooms; clicking
        // a cluster zooms in; the table is the operable primary.

        var NONE = "__none__";  // sentinel agency id; no real feature matches
        var fittedLocation = "";  // last location that changed the default camera

        // Agency id -> table row, so a hovered map point can light up its row
        // and the reverse. Visual only: the row text is the accessible source.
        var rowById = {{}};
        var current = null;   // agency id currently brushed, or null
        var pinned = null;    // sticky selection from Space or a row tap, or null
        var hiReady = false;  // the highlight layer exists once the map loads

        function paintRow(id, on) {{
          var tr = rowById[id];
          if (tr) tr.classList.toggle("is-brushed", on);
        }}
        function highlight(id) {{
          if (id === current) return;
          if (current !== null) paintRow(current, false);
          current = id;
          if (hiReady) {{
            map.setFilter("agencies-hi", ["==", ["get", "id"], id === null ? NONE : id]);
          }}
          if (id !== null) paintRow(id, true);
        }}
        function togglePin(id) {{
          pinned = (pinned === id) ? null : id;
          highlight(pinned);
        }}

        // Row -> point: hovering or focusing a row enlarges its point. The
        // row's existing agency link is the tab stop (no tabindex added), so
        // focus reaching it brushes through focusin; Space pins the highlight,
        // while Enter keeps its meaning and follows the link. A click outside
        // the link pins too, for touch.
        function wireRows() {{
          rowById = {{}};
          rows.forEach(function (tr) {{
            var id = rowAgencyId(tr);
            if (!id) return;
            rowById[id] = tr;
            if (tr.getAttribute("data-map-wired") === "true") return;
            tr.setAttribute("data-map-wired", "true");
            tr.addEventListener("mouseenter", function () {{ highlight(id); }});
            tr.addEventListener("mouseleave", function () {{ highlight(pinned); }});
            tr.addEventListener("focusin", function () {{ highlight(id); }});
            tr.addEventListener("focusout", function () {{ highlight(pinned); }});
            tr.addEventListener("click", function (e) {{
              if (e.target && e.target.closest && e.target.closest("a")) return;
              togglePin(id);
            }});
            tr.addEventListener("keydown", function (e) {{
              if (e.key !== " ") return;
              e.preventDefault();  // Space pins, never scrolls the page
              togglePin(id);
            }});
          }});
        }}
        wireRows();

        function filtered() {{
          if (!all) return {{ type: "FeatureCollection", features: [] }};
          return {{
            type: "FeatureCollection",
            features: all.features.filter(function (f) {{
              var p = f.properties || {{}};
              return matches(
                p.grade,
                p.state || "",
                p.country || "",
                p.subdivision_code || "",
                p.has_flex
              );
            }})
          }};
        }}
        function fitFiltered(data) {{
          // The default camera shows the world. Once a reader chooses a
          // location, move the optional visual map to those results.
          if (!map) return;
          var location = stateEl.value;
          if (!location) {{
            // Clearing a location restores the default camera once. Grade and
            // Flex changes with no active location leave a reader's pan/zoom
            // alone instead of repeatedly snapping the map back.
            if (fittedLocation) {{
              map.fitBounds(worldBounds, {{
                padding: 16, animate: !reduce, duration: reduce ? 0 : 500
              }});
            }}
            fittedLocation = "";
            return;
          }}
          fittedLocation = location;
          if (!data.features.length) return;
          if (data.features.length === 1) {{
            map.easeTo({{
              center: data.features[0].geometry.coordinates,
              zoom: 7, animate: !reduce, duration: reduce ? 0 : 500
            }});
            return;
          }}
          var bounds = new maplibregl.LngLatBounds();
          data.features.forEach(function (feature) {{
            bounds.extend(feature.geometry.coordinates);
          }});
          map.fitBounds(bounds, {{
            padding: 48, maxZoom: 8,
            animate: !reduce, duration: reduce ? 0 : 500
          }});
        }}
        function applyFilter() {{
          filterTable();
          var data = filtered();
          var src = map && map.getSource("agencies");
          if (src) src.setData(data);
          fitFiltered(data);
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
          // Highlight layer above the base points, empty until brushing sets
          // its filter to one agency id, enlarging just that point (the agency
          // map's routes-hi pattern). Added before the grade letters so the
          // letter still draws on top of the enlarged disc.
          map.addLayer({{
            id: "agencies-hi", type: "circle", source: "agencies",
            filter: ["==", ["get", "id"], NONE],
            paint: {{
              "circle-radius": 12, "circle-color": ["get", "color"],
              "circle-stroke-width": 2, "circle-stroke-color": "#ffffff"
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
          hiReady = true;
          if (current !== null) {{
            map.setFilter("agencies-hi", ["==", ["get", "id"], current]);
          }}
          mapEl.classList.remove("national-map-pending");
          if (loadStatusEl) loadStatusEl.textContent =
            "Interactive basemap loaded. Loading the scorecard points and complete list.";
          loadData(wireRows)
            .then(function () {{
              applyFilter();
              if (loadStatusEl) loadStatusEl.textContent =
                "Interactive map and complete scorecard list loaded.";
            }})
            .catch(function () {{
              if (loadStatusEl) loadStatusEl.textContent =
                "The basemap loaded, but the scorecard points did not. The paginated agency " +
                "directory is still available.";
            }});

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
          // Point -> row: hovering a point brushes its row and scrolls it into
          // view (skipped under prefers-reduced-motion); leaving falls back to
          // the pinned selection (or clears).
          map.on("mousemove", "agencies", function (e) {{
            map.getCanvas().style.cursor = "pointer";
            var id = e.features[0].properties.id;
            highlight(id);
            var tr = rowById[id];
            if (tr && !tr.hidden && !reduce) {{
              tr.scrollIntoView({{ block: "nearest" }});
            }}
          }});
          map.on("mouseleave", "agencies", function () {{
            map.getCanvas().style.cursor = "";
            highlight(pinned);
          }});
          map.on("mouseenter", "clusters", function () {{ map.getCanvas().style.cursor = "pointer"; }});
          map.on("mouseleave", "clusters", function () {{ map.getCanvas().style.cursor = ""; }});
        }});
        }}
        function syncFilters() {{
          if (!map || !all || !map.getSource || !map.getSource("agencies")) {{
            filterTable();
            return;
          }}
          applyFilter();
        }}
        function onFilterChange() {{
          // The first filter choice is also an explicit request for the
          // complete dataset. Keep the chosen value, announce the short load,
          // then apply it to every row and (when present) every map point.
          if (!rowsHydrated) {{
            if (listStatusEl) listStatusEl.textContent =
              "Loading the complete scorecard list for this filter.";
            loadData()
              .then(syncFilters)
              .catch(function () {{
                setFiltersDisabled(false);
                filterTable();
                if (listStatusEl) listStatusEl.textContent =
                  "The complete list could not load. This filter applies to the first " +
                  "{initial_count} rows only; use the paginated agency directory for every " +
                  "scorecard.";
              }});
            return;
          }}
          syncFilters();
        }}
        gradeEl.addEventListener("change", onFilterChange);
        stateEl.addEventListener("change", onFilterChange);
        if (flexEl) flexEl.addEventListener("change", onFilterChange);
        filterTable();

        listLoadEl.addEventListener("click", function () {{
          if (listLoadEl.getAttribute("aria-disabled") === "true") return;
          listLoadEl.setAttribute("aria-disabled", "true");
          listLoadEl.textContent = "Loading complete list…";
          if (listStatusEl) listStatusEl.textContent = "Loading the complete scorecard list.";
          loadData()
            .then(function () {{
              syncFilters();
              // This explicit action asked to open the complete result set, so
              // move focus to its existing tabindex="-1" region after the
              // initiating button is removed. Filter-triggered hydration never
              // moves focus out of the selected control.
              if (agencyListEl) agencyListEl.focus();
            }})
            .catch(function () {{
              listLoadEl.removeAttribute("aria-disabled");
              listLoadEl.textContent = "Try loading the complete list again";
              if (listStatusEl) listStatusEl.textContent =
                "The complete list could not load. The first scorecards and paginated agency " +
                "directory are still available.";
            }});
        }});

        loadEl.addEventListener("click", function () {{
          loadEl.disabled = true;
          loadEl.textContent = "Loading map…";
          if (loadStatusEl) loadStatusEl.textContent = "Loading the interactive map.";
          var css = document.createElement("link");
          css.rel = "stylesheet";
          css.href = "https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.css";
          document.head.appendChild(css);
          var script = document.createElement("script");
          script.src = "https://unpkg.com/maplibre-gl@{_MAP_LIB_VERSION}/dist/maplibre-gl.js";
          script.onload = function () {{
            loadEl.hidden = true;
            initMap();
          }};
          script.onerror = function () {{
            loadEl.disabled = false;
            loadEl.textContent = "Try loading the map again";
            if (loadStatusEl) loadStatusEl.textContent =
              "The map could not load. Use the complete-list control or paginated agency directory.";
          }};
          document.head.appendChild(script);
        }});
      }})();
    </script>"""  # noqa: S608 - static HTML template text, never executed as SQL
    return _page(
        title="Agency map — GTFS Scorecard",
        description=(
            "A world map of the feed scorecards currently covered, labelled and coloured "
            "by GTFS data quality grade."
        ),
        canonical=f"{BASE_URL}/map/",
        wide=True,
        body=body,
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
    """The MapLibre bootstrap for the all-routes coverage map.

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
        var worldBounds = [[-180, -85], [180, 85]];
        var map = new maplibregl.Map({{
          container: "routes-map",
          style: "https://tiles.openfreemap.org/styles/positron",
          bounds: worldBounds,
          fitBoundsOptions: {{ padding: 16, duration: 0 }},
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
    """The all-routes coverage map: every feed record's route shapes on one canvas,
    rendered from a single PMTiles archive of vector tiles.

    This is an exploratory enhancement, not the conformant data interface. A
    map of route lines cannot be a literal data table, so the page leads
    with a prominent bypass to the equivalents that *are* AAA-conformant: the
    sortable scorecard list and the per-scorecard route tables. See docs/vpat.md.
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
    <p class="page-lede">The route shapes of every tracked feed record, drawn from each
    feed's own <abbr title="General Transit Feed Specification">GTFS</abbr> and
    combined on a single map. {route_count} routes from {agency_count} feed records are
    on it. Recolour by route type or by the scorecard's data-quality grade, and select
    a line for the named operator and a link to its scorecard.</p>
    <p class="page-lede"><strong>This map is a visual extra, not the accessible way
    to read the data.</strong> A map of this many route lines can't be a data table.
    For a screen-reader and keyboard friendly view, use
    <a href="/agencies/">the alphabetical scorecard list</a>; each scorecard
    carries <a href="/agency/unitrans/">a route-by-route table</a> of its lines.</p>
    <section aria-labelledby="routes-map-h" class="route-map-section">
      <h2 id="routes-map-h" class="section-title">All tracked routes</h2>
      <a class="skip-link-inline" href="#routes-after-map">Skip to the accessible scorecard list</a>
      <fieldset class="map-colormode">
        <legend>Colour routes by</legend>
        <label><input type="radio" name="route-color-mode" value="type" checked> Route type</label>
        <label><input type="radio" name="route-color-mode" value="grade"> Scorecard grade</label>
      </fieldset>
      <div id="routes-map" class="national-map" aria-hidden="true"></div>
      <ul class="map-legend" id="legend-type" aria-label="Route type colours">{type_legend_items}</ul>
      <ul class="map-legend" id="legend-grade" aria-label="Scorecard grade colours" hidden>{grade_legend_items}</ul>
    </section>
    <div id="routes-after-map" tabindex="-1"></div>
    <p class="page-lede">Read the data without the map:</p>
    <ul class="route-skip-targets">
      <li><a href="/app/">All scorecards</a>, searchable by name, country, subdivision, grade, and size.</li>
      <li><a href="/pulse/#changes">Coverage changes</a> since each feed's prior check.</li>
      <li>Each scorecard (for example <a href="/agency/unitrans/">Unitrans</a>) lists its
        routes and stops in a table.</li>
    </ul>
    <p class="fineprint">Routes are one representative shape per route, simplified for
    the combined view; zoom in for detail. Tiles are served as a single PMTiles
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
            "A world vector map of every tracked feed record's transit routes, "
            "coloured by route type or data-quality grade."
        ),
        canonical=f"{BASE_URL}/routes/",
        body=body,
        head_extra=head_extra,
    )


def _leaderboard_sections(
    board: dict[str, Any], histories: dict[str, list[dict[str, Any]]] | None = None
) -> str:
    """Render only same-feed changes from the legacy leaderboard payload.

    The function is kept for downstream callers of the v1 payload, but ignores
    ``top`` and ``bottom`` even if an old cached payload contains them. This is
    defense in depth for the no-absolute-rankings policy.
    """
    hist = histories or {}
    comparison = board.get("comparison") or {}

    def _trend_cell(r: dict[str, Any]) -> str:
        return f"<td>{_spark_mini(hist.get(str(r['id'])), str(r.get('name', r['id'])))}</td>"

    def _trips_cell(r: dict[str, Any]) -> str:
        t = r.get("annual_trips")
        return f"<td>{esc(f'{t:,}')}</td>" if t is not None else "<td></td>"

    def _move_table(rows: list[dict[str, Any]], caption: str) -> str:
        if not rows:
            return ""
        show_trips = any(r.get("annual_trips") is not None for r in rows)
        items = "".join(
            f'<tr><td><a href="/agency/{esc(r["id"])}/"><bdi>'
            f"{esc(r.get('name', r['id']))}</bdi></a></td>"
            f"<td>{esc(r.get('grade'))}</td><td>{esc(r.get('score'))}</td>"
            f"<td>{'+' if r['score_delta'] > 0 else ''}{esc(r['score_delta'])}</td>"
            f"{_trips_cell(r) if show_trips else ''}{_trend_cell(r)}</tr>"
            for r in rows
        )
        trips_th = "<th>Riders/yr</th>" if show_trips else ""
        return (
            f'<section class="feed-details"><h2 class="section-title">{esc(caption)}</h2>'
            '<table class="leaderboard"><thead><tr><th>Agency</th><th>Grade</th>'
            f"<th>Score</th><th>Change</th>{trips_th}<th>Trend</th></tr></thead>"
            f"<tbody>{items}</tbody></table></section>"
        )

    return f"""<div class="section-grid">
    {_move_table(board.get("most_improved", []), "Recent improvements")}
    {_move_table(board.get("most_declined", []), "Changes to review")}
    </div>
    <p class="fineprint">These rows compare each feed only with its own prior check when
    the rubric, scoring profile, validator, and measured category set are unchanged.
    Absolute rankings and individual percentiles are not published.
    The v1-compatible JSON is available at
    <a href="/api/v1/leaderboard.json">leaderboard.json</a>; its historical top and bottom
    arrays are always empty. {esc(comparison.get("note", ""))}</p>"""


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
        comparable = row.get("comparison_eligible_count")
        feed_records = row.get("feed_record_count", row.get("agency_count", 0))
        noun = "feed record" if feed_records == 1 else "feed records"
        label = f"{name}: {_NEED_LABELS.get(tier, tier)}, {feed_records} {noun} covered"
        if (
            isinstance(comparable, int)
            and not isinstance(comparable, bool)
            and comparable > 0
            and isinstance(share, (int, float))
            and not isinstance(share, bool)
        ):
            comparable_noun = (
                "comparable feed record" if comparable == 1 else "comparable feed records"
            )
            label += f", {share}% on D or F across {comparable} {comparable_noun}"
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
    raw_comparison = overlay.get("comparison")
    comparison = raw_comparison if isinstance(raw_comparison, dict) else {}
    raw_eligible_count = comparison.get("eligible_count")
    comparable_count = (
        raw_eligible_count
        if isinstance(raw_eligible_count, int) and not isinstance(raw_eligible_count, bool)
        else 0
    )
    guarded_scores_available = comparable_count > 0
    priority = (overlay.get("priority") or []) if guarded_scores_available else []
    states = overlay.get("states") or []
    by_state = {str(s.get("state")): s for s in states}

    if not guarded_scores_available:
        table = ""
        lead = (
            "ACS transit-need tiers remain available, but score-based priority, state "
            "medians, and D/F shares are unavailable until current-contract checks create "
            "a comparable cohort. No state quality ranking is shown for this snapshot."
        )
    elif priority:
        rows = "".join(
            f"<tr><td>{esc(s['state'])}</td><td>{esc(s['low_grade_share'])}%</td>"
            f"<td>{esc(s['comparison_eligible_count'])}</td>"
            f"<td>{esc(s.get('median_score'))}</td></tr>"
            for s in priority
        )
        table = (
            '<section aria-labelledby="priority-h"><h2 class="section-title" id="priority-h">'
            "High-need states</h2>"
            '<table class="leaderboard"><thead><tr><th scope="col">State</th>'
            '<th scope="col">D/F share</th><th scope="col">Comparable feeds</th>'
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
    # every state the map shades is also readable as text. A guarded score share
    # may order states within a need tier only when the comparison cohort exists.
    states_table = ""
    if states:
        tier_rank = {"high": 0, "moderate": 1, "lower": 2, "unknown": 3}
        ordered = sorted(
            states,
            key=lambda s: (
                tier_rank.get(str(s.get("need_tier")), 9),
                -float(s.get("low_grade_share") or 0) if guarded_scores_available else 0,
                str(s.get("state")),
            ),
        )

        def _score_cell(state: dict[str, Any], key: str, suffix: str = "") -> str:
            state_count = state.get("comparison_eligible_count")
            if not (
                guarded_scores_available
                and isinstance(state_count, int)
                and not isinstance(state_count, bool)
                and state_count > 0
            ):
                return "Not compared"
            value = state.get(key)
            return f"{esc(value)}{suffix}" if value is not None else "Not compared"

        srows = "".join(
            f'<tr data-state-key="{esc(s.get("state"))}">'
            f'<th scope="row">{esc(s.get("state"))}</th>'
            f"<td>{esc(_NEED_LABELS.get(str(s.get('need_tier')), s.get('need_tier')))}</td>"
            f"<td>{_score_cell(s, 'low_grade_share', '%')}</td>"
            f"<td>{esc(s.get('feed_record_count', s.get('agency_count')))}</td>"
            f"<td>{esc(s.get('comparison_eligible_count', 0))}</td>"
            f"<td>{_score_cell(s, 'median_score')}</td></tr>"
            for s in ordered
        )
        states_table = (
            '<section aria-labelledby="states-h"><h2 class="section-title" id="states-h">'
            "Every state</h2>"
            '<p class="page-lede">The ACS need tier for every state we track, with guarded '
            "score summaries only where a comparable feed cohort exists.</p>"
            '<table class="leaderboard"><thead><tr><th scope="col">State</th>'
            '<th scope="col">Need tier</th><th scope="col">D/F share</th>'
            '<th scope="col">Feed records</th><th scope="col">Comparable feeds</th>'
            '<th scope="col">Median score</th></tr></thead>'
            f"<tbody>{srows}</tbody></table></section>"
        )

    choropleth = ""
    skip = ""
    if states_geo and by_state:
        choropleth = _equity_choropleth(states_geo, by_state)
        if choropleth:
            skip = '<a class="skip-link-inline" href="#equity-tables">Skip to the state tables</a>'
    brush_script = _EQUITY_BRUSH_JS if choropleth else ""

    plain_summary = (
        "this highlights high-need states where a guarded score cohort also shows weak "
        "feeds, so help can go where it matters most."
        if guarded_scores_available
        else "this shows ACS transit-need tiers without making state quality comparisons "
        "until current-contract feed checks are available."
    )
    comparison_contract = _comparison_contract_text(comparison)
    return _page(
        title="Equity overlay — GTFS Scorecard",
        description="Where weak GTFS data meets high transit need, from Census ACS indicators.",
        canonical=f"{BASE_URL}/equity/",
        wide=True,
        body=_strip_blank_line_whitespace(
            f"""    {_breadcrumb([("Home", "/"), ("Equity overlay", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Equity overlay.</h1>
    <p class="page-lede">{lead}</p>
    {skip}
    {choropleth}
    <div id="equity-tables" tabindex="-1">
    {table}
    {states_table}
    </div>
    <p class="plain-summary"><strong>In plain words:</strong> {plain_summary} It never changes
    any feed's grade.</p>
    <p class="fineprint">Need tiers come from Census
    <abbr title="American Community Survey">ACS</abbr> (poverty, zero-vehicle households,
    disability share), joined to agencies by state. They prioritize data-quality help; they
    never change a grade. Score summaries use {comparable_count} canonical, non-duplicate feed
    scorecards under {comparison_contract}. The same data is at
    <a href="/api/v1/equity.json">the equity API (equity.json)</a>. State outlines:
    public-domain simplified geometry (docs/decisions/0022-equity-choropleth.md). State-level is
    a first cut; a tract-level refinement is in progress.</p>
    {brush_script}"""
        ),
    )


def _render_ntd_page(
    payload: dict[str, Any], histories: dict[str, list[dict[str, Any]]] | None = None
) -> str:
    """The national NTD GTFS-readiness view, for an FTA or state-DOT
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
            "look ready to certify</strong> against four feed checks for RY2026: the "
            "feed is published at a working "
            "URL, it is valid, its calendar has not lapsed, and agency.txt provides "
            "agency_id for the P-50 crosswalk."
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
        '<p class="page-lede">Since Report Year 2023, NTD reporters with fixed-route '
        "service have had to publish and maintain GTFS. For RY2026, every submission must "
        "provide a stable agency_id for each represented reporter and crosswalk it to the "
        "reporter's NTD ID on P-50; agency_id does not need to equal that five-digit ID. "
        "An agency that cannot comply yet can request "
        "a one-year waiver by showing it is pursuing technical assistance to establish "
        "its GTFS data. The same rule adds shapes.txt to the published feed: "
        '<a href="/ntd/shapes/">does your feed need shapes.txt, explained</a>.</p>'
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
    current GTFS feed and certify it each year. For RY2026, each represented reporter also
    needs a stable agency_id crosswalked on P-50. This page reads those four feed signals
    for every feed we track and rolls them up, so a program can see at a glance how its
    agencies are doing.</p>
    <p class="fineprint">This is a data-quality heads-up, not an official compliance
    determination. Each agency's annual
    <a href="https://www.transit.dot.gov/ntd">D-10 certification</a> is the official one.
    The same numbers are published as <abbr title="JavaScript Object Notation">JSON</abbr>
    at <a href="/ntd.json">ntd.json</a>.</p>""",
    )


_FEDERAL_REGISTER_RY2026 = (
    "https://www.federalregister.gov/documents/2025/07/10/2025-12813/"
    "national-transit-database-reporting-changes-and-clarifications-for-report-years-2025-and-2026"
)


def _render_shapes_page(shapes: dict[str, Any]) -> str:
    """The shapes.txt RY2026 explainer (/ntd/shapes/): does your GTFS feed need
    shapes.txt, who FTA's requirement covers and when, how to check and fix a
    feed, and where tracked feeds stand nationally and per state.

    One page for two readers on the same external clock: the small-agency
    manager hearing about the requirement for the first time, and the reporter
    covering it (the for-reporters section is the story-shaped cut). The numbers
    come from the shapes rollup published in ntd.json and stay population-level;
    per-agency worklists live on the program pages, never here. Like every
    readiness surface, it states what a feed contains and does not certify
    anything; reporter type and waiver status live in the agency's own NTD
    filing.
    """
    canonical = f"{BASE_URL}/ntd/shapes/"
    total = shapes.get("total", 0)
    pct_ready = shapes.get("pct_ready", 0)
    by_state = shapes.get("by_state", {}) or {}
    if total:
        state_rows = "".join(
            f"<tr><td>{esc(state)}</td><td>{esc(c.get('ready', 0))}</td>"
            f"<td>{esc(c.get('at_risk', 0))}</td><td>{esc(c.get('not_ready', 0))}</td>"
            f"<td>{esc(c.get('total', 0))}</td></tr>"
            for state, c in sorted(by_state.items())
        )
        numbers = (
            '<section class="feed-details"><h2 class="section-title">Where tracked feeds '
            "stand</h2>"
            f'<p class="page-lede">Across the {esc(total)} US feeds this site tracks and '
            f"checks, <strong>{esc(pct_ready)}% carry a shape for every trip</strong>. "
            "The rest have the file to add or finish before their report year.</p>"
            '<table class="leaderboard"><thead><tr><th>Coverage</th><th>Feeds</th></tr></thead>'
            "<tbody>"
            f"<tr><td>Every trip has a shape</td><td>{esc(shapes.get('ready', 0))}</td></tr>"
            "<tr><td>Some trips are missing one</td>"
            f"<td>{esc(shapes.get('at_risk', 0))}</td></tr>"
            f"<tr><td>No shapes yet</td><td>{esc(shapes.get('not_ready', 0))}</td></tr>"
            "</tbody></table>"
            '<h3 class="section-title">By state</h3>'
            '<table class="leaderboard"><thead><tr><th>State</th><th>Full</th>'
            "<th>Partial</th><th>None</th><th>Checked</th></tr></thead>"
            f"<tbody>{state_rows}</tbody></table></section>"
        )
        reporter_numbers = (
            f"<p>&ldquo;Of {esc(total)} tracked US transit feeds checked, "
            f"{esc(pct_ready)}% include a shape for every trip.&rdquo; "
            "The per-state counts above support a local cut, counted over the covered "
            "set with the state named. The same numbers are machine-readable in "
            '<a href="/ntd.json">ntd.json</a>.</p>'
        )
    else:
        numbers = (
            '<section class="feed-details"><h2 class="section-title">Where tracked feeds '
            'stand</h2><p class="page-lede">No feeds have been checked for shape coverage '
            "yet.</p></section>"
        )
        reporter_numbers = (
            "<p>Once the coverage rollup has run, this page carries the national and "
            "per-state numbers; the machine-readable copy lives in "
            '<a href="/ntd.json">ntd.json</a>.</p>'
        )
    body = f"""    {_breadcrumb([("Home", "/"), ("NTD readiness", "/ntd/"), ("shapes.txt, explained", None)])}
    <a class="backlink" href="/ntd/">&larr; NTD readiness</a>
    <h1 class="page-title">Does your GTFS feed need shapes.txt?</h1>
    <p class="page-lede">If your agency reports fixed-route or deviated-fixed-route service
    to the <abbr title="Federal Transit Administration">FTA</abbr>'s National Transit
    Database, yes: the GTFS feed you publish needs to include shapes.txt. Full Reporters
    have needed it since Report Year 2025, and Reduced, Rural, and Tribal Reporters join
    in Report Year 2026.</p>

    <section class="feed-details"><h2 class="section-title">What shapes.txt is</h2>
    <p>shapes.txt is the file in a GTFS feed that traces each trip's path along the street
    or rail line, point by point. Trip planners use it to draw your routes on the map.
    A feed without it still lists stops and times, but an app can only connect the stops
    with straight lines, so the map shows vehicles cutting across blocks they never
    travel.</p>
    <p>Each row in trips.txt points at a path through its shape_id column. Full coverage
    means every trip carries a shape_id that matches a path in shapes.txt.</p></section>

    <section class="feed-details"><h2 class="section-title">Who needs it, and when</h2>
    <p>FTA's July 2025 final rule added shapes.txt to the GTFS that
    <abbr title="National Transit Database">NTD</abbr> reporters with fixed-route or
    deviated-fixed-route service publish and certify each year on the D-10 form. The
    requirement phases in by reporter type:</p>
    <table class="leaderboard"><thead><tr><th>NTD reporter type</th>
    <th>shapes.txt required from</th></tr></thead><tbody>
      <tr><td>Full Reporters</td><td>Report Year 2025</td></tr>
      <tr><td>Reduced, Rural, and Tribal Reporters</td><td>Report Year 2026</td></tr>
    </tbody></table>
    <p>Report Year 2026 is the step that reaches most small agencies, many of them
    publishing GTFS under the NTD requirement for the first time. An agency that cannot
    comply yet can request a one-year waiver by showing it is pursuing technical
    assistance to establish its GTFS data. Your reporter type and any waiver live in your
    own NTD filing, not on this site.</p>
    <p class="fineprint">Source: FTA's
    <a href="{_FEDERAL_REGISTER_RY2026}">NTD reporting changes for report years 2025 and
    2026</a>. Reporters with no fixed-route or deviated-fixed-route service are outside
    the GTFS requirement.</p></section>

    <section class="feed-details"><h2 class="section-title">Check whether your feed has it</h2>
    <p>The shapes.txt check already runs on every US feed this site tracks: open
    <a href="/agencies/">your agency's scorecard page</a> and look for &ldquo;shapes.txt
    covers your trips&rdquo; in the NTD GTFS readiness section. If your agency is
    not tracked here, <a href="/try.html">paste your feed's URL</a> to grade it in about a
    minute, or run <a href="/check/">the pre-publish check</a> on an export you have not
    published yet; that one reads the zip in your browser and uploads nothing.</p></section>

    <section class="feed-details"><h2 class="section-title">How to add it</h2>
    <p>Shape data usually comes from the software that builds your feed, not from
    hand-drawn maps. If a vendor or scheduling tool produces your GTFS export, ask for
    shapes.txt in the export, with trips.shape_id set to match. If some trips already have
    shapes, the remaining work is to fill in the rest so every trip has a path.</p>
    <p>After you republish, the next completed scoring run re-checks your feed and the readiness line
    on your agency's page updates on its own.</p></section>

    {numbers}

    <section class="feed-details"><h2 class="section-title">For reporters: the Report Year
    2026 story</h2>
    <p>The story here is population-level: a federal data requirement reaches the smallest
    transit agencies in Report Year 2026, and a measurable share of published feeds do not
    carry the file yet. When FTA finalized the rule in July 2025, it estimated that just
    over a third of reporters already provided shapes.txt.</p>
    {reporter_numbers}
    <p>Two claims these numbers do not support. First, &ldquo;Agency X is out of
    compliance&rdquo;: reporter type and waiver status live in an agency's own NTD filing,
    and this site reads published feeds, not filings; it states what a feed contains and
    certifies nothing. Second, a worst-agencies ranking: the site covers the feeds it
    tracks, so absence means not covered, never failing, and these denominators differ
    from FTA's (tracked feeds, not all NTD reporters). Attribution and more guidance:
    <a href="/press/">writing about this data</a>.</p></section>

    <p class="fineprint">This page is a data-quality heads-up, not an official compliance
    determination or legal advice. The official record is each agency's own NTD filing and
    annual <a href="https://www.transit.dot.gov/ntd">D-10 certification</a>.</p>"""
    jsonld = _tech_article_jsonld(
        headline="Does your GTFS feed need shapes.txt? The RY2026 NTD requirement, explained",
        description=(
            "Who FTA's shapes.txt requirement covers, the Report Year 2026 phase-in for "
            "small transit agencies, and how to check and fix a GTFS feed."
        ),
        canonical=canonical,
        about={"@type": "Thing", "name": "GTFS shapes.txt NTD requirement"},
    )
    return _page(
        title=(
            "Does your GTFS feed need shapes.txt? The RY2026 NTD requirement, explained "
            "— GTFS Scorecard"
        ),
        description=(
            "Who FTA's shapes.txt requirement covers and when it starts, the Report Year "
            "2026 phase-in for small transit agencies, how to check your feed, and where "
            "tracked feeds stand."
        ),
        canonical=canonical,
        wide=True,
        body=body,
        jsonld=jsonld,
    )


_ACCESS_BAND_LABELS = {
    "most": "Nearly every stop marked",
    "some": "Some stops marked",
    "none": "No accessibility data yet",
}


def _portable_rollup_table(
    countries: list[dict[str, Any]], columns: list[tuple[str, str, str]]
) -> str:
    """Country-first aggregate table with nested covered subdivisions.

    ``columns`` is ``(payload key, heading, suffix)``. The API remains the
    authoritative machine contract; this is its small accessible HTML twin.
    """
    if not countries:
        return ""

    def cells(row: dict[str, Any]) -> str:
        parts = []
        for key, _label, suffix in columns:
            value = row.get(key)
            rendered = "&mdash;" if value is None else f"{esc(value)}{suffix}"
            parts.append(f"<td>{rendered}</td>")
        return "".join(parts)

    rows: list[str] = []
    subdivision_disclosures: list[str] = []
    headings = "".join(f'<th scope="col">{esc(label)}</th>' for _key, label, _ in columns)
    for country in countries:
        label = str(country.get("country_name") or country.get("country_code") or "Unlocated")
        rows.append(f'<tr><th scope="row"><bdi>{esc(label)}</bdi></th>{cells(country)}</tr>')
        subdivisions = country.get("subdivisions") or []
        if not subdivisions:
            continue
        subdivision_rows: list[str] = []
        for subdivision in subdivisions:
            sub_label = str(subdivision.get("subdivision_name") or "Unlocated")
            subdivision_rows.append(
                f'<tr><th scope="row"><span aria-hidden="true">↳ </span><bdi>{esc(sub_label)}</bdi>'
                f'<span class="visually-hidden">, <bdi>{esc(label)}</bdi></span></th>'
                f"{cells(subdivision)}</tr>"
            )
        noun = "subdivision" if len(subdivisions) == 1 else "subdivisions"
        subdivision_disclosures.append(
            '<details class="subdivision-rollup"><summary>Show '
            f"{len(subdivisions)} covered {noun} in <bdi>{esc(label)}</bdi></summary>"
            '<div class="table-wrap"><table class="leaderboard">'
            f'<caption class="visually-hidden">Covered subdivisions in {esc(label)}</caption>'
            f'<thead><tr><th scope="col">Subdivision</th>{headings}</tr></thead>'
            f"<tbody>{''.join(subdivision_rows)}</tbody></table></div></details>"
        )
    return (
        '<section class="feed-details"><h2 class="section-title">By country and subdivision</h2>'
        '<div class="table-wrap"><table class="leaderboard"><thead><tr>'
        f'<th scope="col">Location</th>{headings}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"{''.join(subdivision_disclosures)}</section>"
    )


def _access_sections(coverage: dict[str, Any]) -> str:
    """The accessibility-data coverage sections, inside the What-feeds-publish
    page: how many feeds let a wheelchair user plan a trip at all (the share of
    stops carrying ``wheelchair_boarding``), across the corpus and by U.S. state, with the
    most complete feeds highlighted. Changes no grade; framed as coverage to
    build on, for the advocate and the program staff who support them."""
    count = coverage.get("measured_feed_record_count", coverage.get("agency_count", 0))
    comparable_count = _guarded_comparison_count(coverage)
    raw_count = coverage.get("feed_record_count", 0)
    bands = coverage.get("bands", {})
    if comparable_count > 0 and count:
        band_rows = "".join(
            f"<tr><td>{esc(_ACCESS_BAND_LABELS.get(key, key))}</td>"
            f"<td>{esc(bands.get(key, 0))}</td></tr>"
            for key in ("most", "some", "none")
        )
        band_chart = _service_bar_chart(
            [
                (
                    _ACCESS_BAND_LABELS[key],
                    round(100 * int(bands.get(key, 0)) / count, 1),
                    f"{bands.get(key, 0)} of {count} feeds",
                )
                for key in ("most", "some", "none")
            ],
            title="Stop-level accessibility coverage",
            note="Share of feeds in each coverage band.",
            css_class="access-coverage-chart",
        )
        band_table = (
            '<section class="feed-details"><h2 class="section-title">Where feeds stand</h2>'
            f'{band_chart}<details class="viz-data"><summary>Show the table</summary>'
            '<table class="leaderboard"><thead><tr><th>Stop-level coverage</th>'
            f"<th>Feeds</th></tr></thead><tbody>{band_rows}</tbody></table></details></section>"
        )
        complete = coverage.get("most_complete", [])
        complete_rows = "".join(
            f'<tr><td><a href="/agency/{esc(m["id"])}/"><bdi>{esc(m["name"])}</bdi></a></td>'
            f"<td><bdi>{esc(_location_label(m))}</bdi></td><td>{esc(m['pct'])}%</td></tr>"
            for m in complete
        )
        complete_table = (
            (
                '<section class="feed-details"><h2 class="section-title">Most complete</h2>'
                '<p class="page-lede">Feed records whose stops are the most fully marked for '
                "wheelchair access. A target to aim for.</p>"
                '<table class="leaderboard"><thead><tr><th>Feed record</th><th>Location</th>'
                f"<th>Stops marked</th></tr></thead><tbody>{complete_rows}</tbody></table></section>"
            )
            if complete
            else ""
        )
        state_rows = "".join(
            f"<tr><td>{esc(s['state'])}</td>"
            f"<td>{esc(s.get('feed_records', s.get('agencies', 0)))}</td>"
            f"<td>{esc(s.get('average_boarding_pct'))}%</td><td>{esc(s['most'])}</td>"
            f"<td>{esc(s['none'])}</td></tr>"
            for s in coverage.get("states", [])
        )
        state_table = (
            '<section class="feed-details"><h2 class="section-title">United States by state</h2>'
            '<table class="leaderboard"><thead><tr><th>State</th><th>Feed records</th>'
            "<th>Avg stops marked</th><th>Nearly all</th><th>None yet</th></tr></thead>"
            f"<tbody>{state_rows}</tbody></table></section>"
        )
        location_table = _portable_rollup_table(
            coverage.get("countries") or [],
            [
                ("feed_records", "Feed records", ""),
                ("average_boarding_pct", "Avg stops marked", "%"),
                ("most", "Nearly all", ""),
                ("none", "None yet", ""),
            ],
        )
        lead = (
            f"Across {esc(count)} feeds, an average of "
            f"<strong>{esc(coverage.get('average_boarding_pct'))}% of stops</strong> carry "
            "wheelchair-access information. When a stop is unmarked, a rider who uses a "
            "wheelchair cannot tell from a trip planner whether they can board there."
        )
    elif comparable_count <= 0:
        band_table = complete_table = state_table = location_table = ""
        lead = (
            "Cross-feed accessibility coverage is unavailable until current-contract "
            "checks create a comparable feed-record cohort. This snapshot makes no "
            "corpus-wide completeness or named-feed claim."
        )
    else:
        band_table = complete_table = state_table = location_table = ""
        lead = (
            f"{comparable_count} feed records meet the comparison contract, but none has "
            "a readable accessibility-detail block yet."
        )
    comparison_note = (
        f"The directory contains {esc(raw_count)} published feed records; "
        f"{esc(comparable_count)} meet {_comparison_contract_text(coverage.get('comparison') or {})}, "
        f"and {esc(count)} supply the accessibility detail used here."
        if comparable_count > 0
        else f"The directory contains {esc(raw_count)} published feed records. "
        "No cross-feed denominator is published for this snapshot."
    )
    return f"""<p class="page-lede">{lead}
    <strong>What this measures:</strong> whether feeds publish the data, never
    whether a stop is physically usable.</p>
    <div class="section-grid">
    {band_table}
    {complete_table}
    </div>
    {location_table}
    {state_table}
    <p class="fineprint">Coverage is the share of a feed's stops carrying
    <code>wheelchair_boarding</code> and trips carrying <code>wheelchair_accessible</code>,
    the portable GTFS accessibility fields used by trip planners. California's
    Transit Data Guidelines are one regional source for this published scoring profile,
    not its worldwide authority. It never changes a grade. The
    same data is at <a href="/api/v1/accessibility.json">the accessibility API
    (accessibility.json)</a>. This page is about data completeness; for how this site itself
    meets <abbr title="Web Content Accessibility Guidelines">WCAG</abbr>, see
    <a href="/accessibility/">Accessibility</a>. {comparison_note}</p>"""


def _render_adoption_page(adoption: dict[str, Any], coverage: dict[str, Any]) -> str:
    """What feeds publish (/adoption/): the capability-adoption view (flexible
    service, fares and Fares v2, station pathways, translations) and the accessibility-data
    coverage view, one page instead of two with identical skeletons. Reads the
    the corpus adoption and accessibility-coverage rollups.
    Changes no grade; a lens on where the spec is spreading, framed as adoption
    to encourage. The retired /access/ URL redirects to #access here."""
    count = adoption.get("measured_feed_record_count", adoption.get("agency_count", 0))
    comparable_count = _guarded_comparison_count(adoption)
    raw_count = adoption.get("feed_record_count", 0)
    if comparable_count > 0 and count:
        capabilities = [
            ("Flexible (demand-responsive) service", adoption.get("flex") or {}),
            ("Fare data (any model)", adoption.get("fares") or {}),
            ("Fare data using Fares v2", adoption.get("fares_v2") or {}),
            ("Station accessibility (pathways)", adoption.get("pathways") or {}),
            ("Step-free station paths", adoption.get("step_free") or {}),
            ("Contactless payment declared (cEMV)", adoption.get("cemv") or {}),
            ("Translated rider information", adoption.get("translations") or {}),
        ]

        def cap_row(label: str, share: dict[str, Any] | None) -> str:
            s = share or {}
            return (
                f"<tr><td>{esc(label)}</td><td>{esc(s.get('count', 0))}</td>"
                f"<td>{esc(s.get('measured_feed_record_count', count))}</td>"
                f"<td>{esc(s.get('pct', 0))}%</td></tr>"
            )

        cap_rows = "".join(cap_row(label, share) for label, share in capabilities)
        cap_chart = _service_bar_chart(
            [
                (
                    label,
                    float(share.get("pct", 0)),
                    f"{share.get('count', 0)} of "
                    f"{share.get('measured_feed_record_count', count)} measured feeds",
                )
                for label, share in sorted(
                    capabilities, key=lambda row: float(row[1].get("pct", 0)), reverse=True
                )
            ],
            title="Adoption by capability",
            note="Share of tracked feeds publishing each optional capability.",
            css_class="adoption-chart",
        )
        cap_table = (
            '<section class="feed-details"><h2 class="section-title">What feeds publish</h2>'
            f'{cap_chart}<details class="viz-data"><summary>Show the table</summary>'
            '<table class="leaderboard"><thead><tr><th>Capability</th><th>Feeds</th>'
            "<th>Measured feeds</th>"
            f"<th>Share</th></tr></thead><tbody>{cap_rows}</tbody></table></details></section>"
        )
        flex_sample = adoption.get("flex_sample", [])
        flex_rows = "".join(
            f'<tr><td><a href="/agency/{esc(m["id"])}/"><bdi>{esc(m["name"])}</bdi></a></td>'
            f"<td><bdi>{esc(_location_label(m))}</bdi></td></tr>"
            for m in flex_sample
        )
        flex_table = (
            (
                '<section class="feed-details"><h2 class="section-title">Publishing flexible '
                'service</h2><p class="page-lede">Feeds that already describe demand-responsive or '
                "dial-a-ride service in GTFS-Flex, so a trip planner can offer it.</p>"
                '<table class="leaderboard"><thead><tr><th>Feed record</th><th>Location</th></tr></thead>'
                f"<tbody>{flex_rows}</tbody></table></section>"
            )
            if flex_sample
            else ""
        )
        translation_sample = adoption.get("translations_sample", [])
        translation_rows = "".join(
            f'<tr><td><a href="/agency/{esc(m["id"])}/"><bdi>{esc(m["name"])}</bdi></a></td>'
            f"<td><bdi>{esc(_location_label(m))}</bdi></td>"
            f"<td>{esc(', '.join(m.get('languages') or []))}</td>"
            f"<td>{esc(m.get('translation_count', 0))}</td></tr>"
            for m in translation_sample
        )
        translation_table = (
            (
                '<section class="feed-details"><h2 class="section-title">Publishing translations</h2>'
                '<p class="page-lede">Feeds with usable rider-facing text in '
                "<code>translations.txt</code>.</p>"
                '<table class="leaderboard"><thead><tr><th>Feed record</th><th>Location</th>'
                "<th>Language tags</th><th>Rows</th></tr></thead>"
                f"<tbody>{translation_rows}</tbody></table></section>"
            )
            if translation_sample
            else ""
        )
        state_rows = "".join(
            f"<tr><td>{esc(s['state'])}</td>"
            f"<td>{esc(s.get('feed_records', s.get('agencies', 0)))}</td>"
            f"<td>{esc(s['flex'])}</td><td>{esc(s['fares'])}</td>"
            f"<td>{esc(s['fares_v2'])}</td><td>{esc(s['pathways'])}</td>"
            f"<td>{esc(s.get('translations', 0))} of "
            f"{esc(s.get('translations_measured', 0))}</td></tr>"
            for s in adoption.get("states", [])
        )
        state_table = (
            '<section class="feed-details"><h2 class="section-title">United States by state</h2>'
            '<table class="leaderboard"><thead><tr><th>State</th><th>Feed records</th>'
            "<th>Flex</th><th>Fares</th><th>Fares v2</th><th>Pathways</th>"
            "<th>Translations (of measured)</th></tr></thead>"
            f"<tbody>{state_rows}</tbody></table></section>"
        )
        location_table = _portable_rollup_table(
            adoption.get("countries") or [],
            [
                ("feed_records", "Feed records", ""),
                ("flex", "Flex", ""),
                ("fares", "Fares", ""),
                ("fares_v2", "Fares v2", ""),
                ("pathways", "Pathways", ""),
                ("translations", "Translations", ""),
                ("translations_measured", "Translation measured", ""),
            ],
        )
        flex_s = adoption.get("flex", {})
        fares = adoption.get("fares", {})
        v2 = adoption.get("fares_v2", {})
        paths = adoption.get("pathways", {})
        translations = adoption.get("translations", {})
        translation_denominator = translations.get("measured_feed_record_count", 0)
        translation_sentence = (
            f" Among {esc(translation_denominator)} feeds measured for translations, "
            f"<strong>{esc(translations.get('pct', 0))}%</strong> publish rider-facing translations."
            if translation_denominator
            else " Translation adoption will appear after current feeds are measured."
        )
        lead = (
            f"Across {esc(count)} feeds, <strong>{esc(flex_s.get('pct', 0))}%</strong> publish "
            f"flexible (demand-responsive) service, <strong>{esc(fares.get('pct', 0))}%</strong> "
            f"publish fare data ({esc(v2.get('pct', 0))}% using the newer Fares v2), and "
            f"<strong>{esc(paths.get('pct', 0))}%</strong> model stations with accessible paths. "
            "These are optional parts of GTFS; adoption shows where the spec is spreading."
            f"{translation_sentence}"
        )
    elif comparable_count <= 0:
        cap_table = flex_table = translation_table = state_table = location_table = ""
        lead = (
            "Cross-feed capability adoption is unavailable until current-contract checks "
            "create a comparable feed-record cohort. This snapshot makes no adoption-rate "
            "or named-feed claim."
        )
    else:
        cap_table = flex_table = translation_table = state_table = location_table = ""
        lead = (
            f"{comparable_count} feed records meet the comparison contract, but none has "
            "a readable capability-detail block yet."
        )
    comparison_note = (
        f"The directory contains {esc(raw_count)} published feed records; "
        f"{esc(comparable_count)} meet {_comparison_contract_text(adoption.get('comparison') or {})}, "
        f"and {esc(count)} supply the capability detail used here."
        if comparable_count > 0
        else f"The directory contains {esc(raw_count)} published feed records. "
        "No cross-feed denominator is published for this snapshot."
    )
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
    <p><a class="button-link" href="/app/#/?view=features">Build a feature shortlist</a></p>
    {jump}
    <section id="features" aria-labelledby="features-h" tabindex="-1">
      <h2 class="section-title" id="features-h">Optional parts of GTFS</h2>
      <div class="section-grid">
      {cap_table}
      {flex_table}
      {translation_table}
      </div>
      {location_table}
      {state_table}
    </section>
    {_route_rule()}
    <section id="access" aria-labelledby="access-h" tabindex="-1">
      <h2 class="section-title" id="access-h">Accessibility data coverage</h2>
      {_access_sections(coverage)}
    </section>
    <p class="plain-summary"><strong>In plain words:</strong> a feed does not need any of these to
    earn a good grade. This tracks where optional parts of GTFS are catching on, so an
    agency can see what peers publish and a program can see where to help next.</p>
    <p class="fineprint">Adoption is read from each feed's own files: GTFS-Flex
    (<code>locations.geojson</code>, <code>booking_rules.txt</code>), fare data
    (<code>fare_attributes.txt</code> for the legacy model, <code>fare_products.txt</code> and
    <code>fare_leg_rules.txt</code> for Fares v2), and GTFS-Pathways (<code>pathways.txt</code>,
    <code>levels.txt</code>), plus rider-facing translations (<code>translations.txt</code>).
    It never changes a grade. The same data is at
    <a href="/api/v1/adoption.json">the adoption API (adoption.json)</a>.
    {comparison_note}</p>"""
    return _page(
        title="What feeds publish — GTFS Scorecard",
        description=(
            "Which GTFS features covered transit feeds publish (flexible service, fares and "
            "Fares v2, station pathways, translations) and how complete their accessibility data is."
        ),
        canonical=f"{BASE_URL}/adoption/",
        body=_strip_blank_line_whitespace(body),
        wide=True,
    )


_STALENESS_BUCKETS: tuple[tuple[str, Callable[[float], bool]], ...] = (
    ("under 1 day", lambda d: d < 1),
    ("1-2 days", lambda d: 1 <= d < 3),
    ("3-7 days", lambda d: 3 <= d < 8),
    ("over 7 days", lambda d: d >= 8),
)


def _staleness_distribution(
    catalog: list[dict[str, Any]], now: dt.datetime
) -> list[tuple[str, int]]:
    """Bucket every tracked agency's snapshot age (catalog[i]["retrieved_at"],
    which is the artifact's generated_at) so /status/ can answer "how fresh is
    this dataset right now" without trusting the maintainer's word (FIX-11's
    "excellent looks like" bar). An unparsable or missing timestamp counts as
    "unknown" rather than being silently dropped."""
    counts: dict[str, int] = {label: 0 for label, _ in _STALENESS_BUCKETS}
    unknown = 0
    for row in catalog:
        raw = row.get("retrieved_at")
        try:
            when = dt.datetime.fromisoformat(str(raw))
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt.UTC)
        except (TypeError, ValueError):
            unknown += 1
            continue
        age_days = max(0.0, (now - when).total_seconds() / 86400)
        for label, test in _STALENESS_BUCKETS:
            if test(age_days):
                counts[label] += 1
                break
    result = [(label, counts[label]) for label, _ in _STALENESS_BUCKETS]
    if unknown:
        result.append(("unknown", unknown))
    return result


def _status_shard_rows(shards: list[dict[str, Any]]) -> str:
    rows = []
    for s in shards:
        rows.append(
            "<tr>"
            f"<td>{esc(str(s.get('shard', '')))}</td>"
            f"<td>{s.get('scored', 0)}</td>"
            f"<td>{s.get('reused', 0)}</td>"
            f"<td>{s.get('unreachable', 0)}</td>"
            f"<td>{s.get('mirrored', 0)}</td>"
            f"<td>{s.get('cache_hit', 0)}</td>"
            f"<td>{s.get('wall_clock_seconds', 0):.0f}s</td>"
            "</tr>"
        )
    return "".join(rows)


def _scope_run_summary(
    run_summary: dict[str, Any] | None, catalog: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Bound named run evidence to currently published feed records.

    Aggregate shard counts still describe the historical run's attempted set.
    Removed records are counted, never retained as dead public links or names.
    The transform is idempotent so both the API boundary and HTML helper can
    apply it defensively.
    """
    if run_summary is None:
        return None
    published_ids = {str(row.get("id") or "") for row in catalog}
    published_ids.discard("")

    def _scope_named_unreachable(record: dict[str, Any]) -> dict[str, Any]:
        raw = [str(agency_id) for agency_id in record.get("unreachable_agencies", [])]
        current = [agency_id for agency_id in raw if agency_id in published_ids]
        source = int(record.get("source_unreachable_agency_count", len(raw)))
        outside = int(
            record.get(
                "unreachable_outside_current_published_set",
                max(0, source - len(current)),
            )
        )
        result = dict(record)
        result.update(
            {
                "unreachable_agencies": current,
                "source_unreachable_agency_count": source,
                "current_published_unreachable_count": len(current),
                "unreachable_outside_current_published_set": outside,
            }
        )
        return result

    raw_ids = [str(agency_id) for agency_id in run_summary.get("unreachable_agencies", [])]
    current_ids = [agency_id for agency_id in raw_ids if agency_id in published_ids]
    source_count = int(run_summary.get("source_unreachable_agency_count", len(raw_ids)))
    omitted = int(
        run_summary.get(
            "unreachable_outside_current_published_set",
            max(0, source_count - len(current_ids)),
        )
    )
    scoped = dict(run_summary)
    scoped.update(
        {
            "unreachable_agencies": current_ids,
            "source_unreachable_agency_count": source_count,
            "current_published_unreachable_count": len(current_ids),
            "unreachable_outside_current_published_set": omitted,
            "published_feed_record_count": len(published_ids),
            "shards": [
                _scope_named_unreachable(shard)
                for shard in run_summary.get("shards", [])
                if isinstance(shard, dict)
            ],
            "scope_note": (
                "Aggregate counts describe the feed-record set attempted by that run. "
                "Named unreachable records are restricted to the current published catalog; "
                "records outside that catalog are counted but not named or linked."
            ),
        }
    )
    return scoped


def _status_evidence_section(
    run_summary: dict[str, Any] | None, catalog: list[dict[str, Any]], now: dt.datetime
) -> str:
    """The latest-run-evidence half of /status/ (FIX-11,
    docs/ideation/02-large-scale-fixes.md): what the latest scheduled run did --
    shard outcomes, unreachable feeds, mirror fallbacks, validator cache hits --
    plus how stale the published catalog is right now. Users are asked to trust
    scheduled refreshes happened; the operational evidence used to live only in private
    Actions logs, so one shard failing left ~1/12 of feed records silently showing
    older data with no signal anywhere on the site. This section is that
    signal, built entirely from data/artifacts/run/latest.json (merged by
    `scorecard run-summary merge` in the collect job) and the same catalog the
    directory page reads -- no separate trust required. Returns a fragment (no
    page chrome); composed into the combined /status/ page by `_render_status`
    alongside `_status_commitment_section`."""
    run_summary = _scope_run_summary(run_summary, catalog)
    staleness = _staleness_distribution(catalog, now)
    staleness_rows = "".join(
        f"<tr><td>{esc(label)}</td><td>{count}</td></tr>" for label, count in staleness
    )
    staleness_chart = _bucket_chart(
        staleness,
        title="Snapshot age distribution",
        note=f"All {len(catalog)} tracked feed scorecards, grouped by snapshot age.",
        css_class="staleness-chart",
        accessible_unit="feed scorecard",
    )

    if run_summary is None:
        run_section = """    <section class="feed-details"><h3 class="section-title">Run summary</h3>
    <p>No run-health summary has been published yet. This page fills in the day after the
    first run that writes <code>data/artifacts/run/latest.json</code>.</p></section>"""
    else:
        generated_at = dt.datetime.fromisoformat(run_summary["generated_at"])
        degraded = bool(run_summary.get("degraded"))
        threshold_pct = round(run_summary.get("degraded_threshold", 0) * 100)
        badge_class = "pill-warn" if degraded else "pill-ok"
        badge_text = "Run completed with warnings" if degraded else "Run completed"
        unreachable_agencies = run_summary.get("unreachable_agencies", [])
        omitted_unreachable = int(run_summary.get("unreachable_outside_current_published_set", 0))
        names_by_id = {row["id"]: row["name"] for row in catalog}
        current_unreachable_list = (
            "<ul>"
            + "".join(
                f'<li><a href="/agency/{esc(aid)}/">{esc(names_by_id.get(aid, aid))}</a></li>'
                for aid in unreachable_agencies
            )
            + "</ul>"
            if unreachable_agencies
            else "<p>No currently published feed record was unreachable in this run.</p>"
        )
        omitted_note = (
            f'<p class="fineprint">{omitted_unreachable} additional '
            f"{'record was' if omitted_unreachable == 1 else 'records were'} part of this "
            "run's attempted set but are outside the current published catalog. They remain "
            "in the run totals without being named or linked here.</p>"
            if omitted_unreachable
            else ""
        )
        unreachable_list = current_unreachable_list + omitted_note
        degraded_note = (
            f"""<p>More than {threshold_pct}% of attempted feed records could not be
        refreshed, so this run exceeded the warning threshold. Records from that set that
        remain in the current catalog are listed below.</p>"""
            if degraded
            else ""
        )
        shard_count = run_summary.get("shard_count", 0)
        shard_word = "shard" if shard_count == 1 else "shards"
        run_section = f"""    <section class="feed-details"><h3 class="section-title">Run summary</h3>
    <p><span class="{badge_class}">{badge_text}</span> Recorded
    {esc(_ago(now, generated_at))} ({esc(generated_at.strftime("%Y-%m-%d %H:%M UTC"))}).
    The run attempted {run_summary.get("agency_count", 0)} feed records across
    {shard_count} {shard_word}. The current catalog contains
    {run_summary.get("published_feed_record_count", len(catalog))} feed records.</p>
    <p class="fineprint">The badge describes this scoring run, not agency feed availability.
    Current direct-URL liveness is reported above.</p>
    {degraded_note}
    <dl>
      <dt>Scored (fresh data this run)</dt><dd>{run_summary.get("scored", 0)}</dd>
      <dt>Reused (feed unchanged since last check)</dt><dd>{run_summary.get("reused", 0)}</dd>
      <dt>Unreachable (all attempted records)</dt><dd>{run_summary.get("unreachable", 0)}</dd>
      <dt>Unreachable records still in the current catalog</dt><dd>{run_summary.get("current_published_unreachable_count", 0)}</dd>
      <dt>Fell back to the Mobility Database mirror</dt><dd>{run_summary.get("mirrored", 0)}</dd>
      <dt>Validator cache hits</dt><dd>{run_summary.get("cache_hit", 0)}</dd>
    </dl>
    </section>

    <details class="viz-data"><summary>Show per-shard breakdown</summary>
    <div style="overflow-x:auto"><table class="trend-table">
      <caption class="visually-hidden">Outcome counts by CI shard</caption>
      <thead><tr><th scope="col">Shard</th><th scope="col">Scored</th>
      <th scope="col">Reused</th><th scope="col">Unreachable</th><th scope="col">Mirrored</th>
      <th scope="col">Cache hit</th><th scope="col">Wall clock</th></tr></thead>
      <tbody>{_status_shard_rows(run_summary.get("shards", []))}</tbody>
    </table></div>
    </details>

    <section class="feed-details"><h3 class="section-title">Feed records unreachable this run</h3>
    <p>The pipeline could not fetch or validate these currently published feeds in that run;
    each continues to show its last successful scorecard. A feed host outage is one possible
    cause, but this evidence does not diagnose why a check failed.</p>
    {unreachable_list}
    </section>"""

    return f"""    <h2 class="section-title" id="evidence-h">Latest full scoring run</h2>
    <p>This section reports one completed scoring run. It separates all attempted records from
    records that remain in the current catalog and shows the age of each published score.
    Machine-readable at
    <a href="/api/v1/run-status.json">/api/v1/run-status.json</a>.</p>

{run_section}

    <section class="feed-details"><h3 class="section-title">Catalog freshness</h3>
    <p>Age of the most recent successful score behind each current scorecard. A score can be
    older than this run when its source was unchanged or could not be fetched.</p>
    {staleness_chart}
    <details class="viz-data"><summary>Show snapshot-age table</summary>
    <div style="overflow-x:auto"><table class="trend-table">
      <caption class="visually-hidden">Feed scorecard count by snapshot age</caption>
      <thead><tr><th scope="col">Snapshot age</th><th scope="col">Feed scorecards</th></tr></thead>
      <tbody>{staleness_rows}</tbody>
    </table></div></details>
    </section>

    <p class="fineprint">Built from <a href="/api/v1/run-status.json">the run-status API</a>,
    refreshed after each completed scoring run. See <a href="/how-to-read/">how to read a scorecard</a> for what
    the grades themselves mean.</p>"""


def _global_coverage_value(value: object, unit: str = "") -> str:
    """Present one readiness-gate value without making ``null`` look like zero."""
    if value is None:
        return "Not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if unit == "percent" and isinstance(value, (int, float)):
        return f"{value:g}%"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _global_coverage_charts(doc: dict[str, Any], feed_count: object, criteria: list[Any]) -> str:
    """Two chart views of the same gate numbers, in the shared route-bar
    grammar: progress toward the record threshold, and the per-country balance
    the concentration ceiling constrains. Every value stays visible as text;
    the thresholds come from the published criteria, never a second hardcoded
    copy."""

    def threshold_for(key: str) -> float | None:
        for criterion in criteria:
            if isinstance(criterion, dict) and criterion.get("key") == key:
                threshold = criterion.get("threshold")
                if isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
                    return float(threshold)
        return None

    charts_html = ""
    record_threshold = threshold_for("reviewed_feed_records")
    if isinstance(feed_count, int) and record_threshold:
        share = min(100.0, round(feed_count / record_threshold * 100, 1))
        charts_html += _service_bar_chart(
            [("Reviewed feed records", share, f"{feed_count:,} of {int(record_threshold):,}")],
            title="Progress toward the record threshold",
            note="Reviewed European feed records as a share of the release threshold.",
            css_class="coverage-progress",
        )
    raw_countries = doc.get("countries")
    country_rows = [
        row
        for row in (raw_countries if isinstance(raw_countries, list) else [])
        if isinstance(row, dict)
        and isinstance(row.get("feed_record_count"), int)
        and row.get("feed_record_count", 0) > 0
    ]
    if isinstance(feed_count, int) and feed_count > 0 and country_rows:
        ceiling = threshold_for("largest_country_share")
        ceiling_note = (
            f"No single country may hold more than {ceiling:g}% of the cohort."
            if ceiling
            else "Shares of the reviewed cohort by country."
        )
        bars = [
            (
                str(row.get("country_name") or row.get("country_code") or "Unknown"),
                round(row["feed_record_count"] / feed_count * 100, 1),
                f"{row['feed_record_count']:,} records"
                if row["feed_record_count"] != 1
                else "1 record",
            )
            for row in sorted(country_rows, key=lambda r: -int(r.get("feed_record_count", 0)))
        ]
        charts_html += _service_bar_chart(
            bars,
            title="Reviewed records by country",
            note=ceiling_note,
            css_class="coverage-countries",
        )
    return charts_html


def _global_coverage_section(payload: dict[str, Any] | None) -> str:
    """Render the public view of the evidence-gated European beta contract.

    The JSON remains the audit record.  This view gives a non-technical reader
    the same pass/fail criteria, denominators, and exception counts without
    implying that a reviewed GTFS cohort represents all European transport.
    """
    doc = payload if isinstance(payload, dict) else {}
    ready = doc.get("ready") is True and doc.get("status") == "ready"
    badge_class = "pill-ok" if ready else "pill-warn"
    badge_text = "Ready" if ready else "Not ready"

    raw_cohort = doc.get("cohort")
    cohort = raw_cohort if isinstance(raw_cohort, dict) else {}
    feed_count = cohort.get("feed_record_count")
    country_count = cohort.get("country_count")
    if feed_count is None or country_count is None:
        cohort_line = (
            "No coverage-gate payload has been published on this deployment yet. "
            "The beta cannot be marked ready without that evidence."
        )
    else:
        feed_word = "record" if feed_count == 1 else "records"
        country_word = "country" if country_count == 1 else "countries"
        cohort_line = (
            f"The reviewed cohort currently contains <strong>{esc(_global_coverage_value(feed_count))}</strong> "
            f"GTFS Schedule feed {feed_word} across "
            f"<strong>{esc(_global_coverage_value(country_count))}</strong> {country_word}."
        )

    raw_criteria = doc.get("criteria")
    criteria = raw_criteria if isinstance(raw_criteria, list) else []
    charts_html = _global_coverage_charts(doc, feed_count, criteria)

    criterion_rows: list[str] = []
    operator_labels = {">=": "at least", "<=": "at most", "=": "equals"}
    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        unit = str(criterion.get("unit") or "")
        current = _global_coverage_value(criterion.get("actual"), unit)
        threshold = _global_coverage_value(criterion.get("threshold"), unit)
        operator = operator_labels.get(
            str(criterion.get("operator") or ""), str(criterion.get("operator") or "")
        )
        met = criterion.get("met") is True
        criterion_rows.append(
            f'<tr><th scope="row">{esc(str(criterion.get("label") or criterion.get("key") or "Criterion"))}</th>'
            f"<td>{esc(current)}</td><td>{esc(operator)} {esc(threshold)}</td>"
            f'<td><span class="{"pill-ok" if met else "pill-warn"}">'
            f"{'Met' if met else 'Not met'}</span></td></tr>"
        )
    if not criterion_rows:
        criterion_rows.append(
            '<tr><th scope="row">Coverage gate payload</th><td>Not available</td>'
            '<td>Published evidence required</td><td><span class="pill-warn">Not met</span></td></tr>'
        )

    raw_exceptions = doc.get("exceptions")
    exceptions = raw_exceptions if isinstance(raw_exceptions, list) else []
    exception_rows: list[str] = []
    for exception in exceptions:
        if not isinstance(exception, dict):
            continue
        count = exception.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            continue
        exception_rows.append(
            f'<tr><th scope="row">{esc(str(exception.get("label") or exception.get("key") or "Exception"))}</th>'
            f"<td>{count:,}</td></tr>"
        )
    if exception_rows:
        exceptions_html = f"""<div class="table-wrap"><table>
      <caption>Coverage-gate exceptions by reason</caption>
      <thead><tr><th scope="col">Reason</th><th scope="col">Count</th></tr></thead>
      <tbody>{"".join(exception_rows)}</tbody></table></div>
    <p class="fineprint">A feed record can appear under more than one reason. The JSON lists
    the affected record identifiers.</p>"""
    else:
        exceptions_html = "<p>No coverage-gate exceptions are recorded.</p>"

    methodology_url = (
        "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/global-expansion.md"
    )
    return f"""    <h2 class="section-title" id="global-coverage">European beta readiness</h2>
    <p><span class="{badge_class}">{badge_text}</span> {cohort_line}</p>
    <p>This is a bounded European <abbr title="General Transit Feed Specification">GTFS</abbr>
    Schedule beta gate based on feed records with reviewed reuse evidence. It is not a claim
    of coverage for all European public transport, and it does not assess NeTEx coverage.</p>
    {charts_html}
    <section aria-labelledby="global-criteria-h"><h3 class="section-title" id="global-criteria-h">Readiness criteria</h3>
    <div class="table-wrap"><table>
      <caption>Current European beta measures compared with release thresholds</caption>
      <thead><tr><th scope="col">Measure</th><th scope="col">Current</th>
      <th scope="col">Threshold</th><th scope="col">Status</th></tr></thead>
      <tbody>{"".join(criterion_rows)}</tbody></table></div></section>

    <section aria-labelledby="global-exceptions-h"><h3 class="section-title" id="global-exceptions-h">Exceptions</h3>
    {exceptions_html}</section>

    <p class="fineprint">Read the auditable <a href="/api/v1/global-coverage.json">global coverage JSON</a>
    or the <a href="{methodology_url}">global expansion methodology</a>. Counts are feed records,
    not agencies, operators, routes, or services.</p>"""


def _render_status(
    status_doc: dict[str, Any],
    run_summary: dict[str, Any] | None,
    catalog: list[dict[str, Any]],
    now: dt.datetime,
    global_coverage: dict[str, Any] | None = None,
) -> str:
    """The one public /status/ page. EXP-10 (the refresh/liveness commitment)
    and FIX-11 (latest-run evidence) both used to render their own
    full page to this same URL, so whichever `write()` ran last silently
    clobbered the other's file on disk. This composes both instead: the
    commitment (`_status_commitment_section`, sourced from
    `api/v1/status.json`) on top, framed as what we commit to; latest-run
    evidence (`_status_evidence_section`, sourced from
    `api/v1/run-status.json`) below, framed as latest-run evidence; and the
    bounded European GTFS beta gate last. All three JSON endpoints are
    cross-linked from here and from within each section."""
    canonical = f"{BASE_URL}/status/"
    body = f"""    {_breadcrumb([("Home", "/"), ("Status", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Service status</h1>
    <p class="page-lede">This page shows whether configured feed URLs are responding, whether
    scheduled scoring completed, and whether the bounded European beta criteria are met.
    Direct liveness checks and the mirror-assisted daily run are reported separately because
    they measure different things. Machine-readable at
    <a href="/api/v1/status.json">/api/v1/status.json</a>,
    <a href="/api/v1/run-status.json">/api/v1/run-status.json</a>, and
    <a href="/api/v1/global-coverage.json">/api/v1/global-coverage.json</a>.</p>

    {_route_rule()}
{_status_commitment_section(status_doc)}

    {_route_rule()}
{_status_evidence_section(run_summary, catalog, now)}

    {_route_rule()}
{_global_coverage_section(global_coverage)}"""
    return _page(
        title="Status | GTFS Scorecard",
        description=(
            "The scorecard's monitoring schedule, current direct feed-URL liveness, latest full "
            "scoring run, catalog freshness, and bounded European GTFS beta readiness."
        ),
        canonical=canonical,
        body=body,
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
      <li>"N of the M feeds this site tracks in [country or subdivision] have expired."
      Counts over the covered set, with the exact geographic scope named.</li>
      <li>"Agency X's feed does not say which stops are wheelchair accessible." A statement
      about published data, and usually a one-setting fix in the agency's software.</li>
      <li>"Across the feeds currently covered, [pct]% publish fare data." This is a claim
      about this site's corpus, not about all agencies in the world.</li>
    </ul></section>

    <section class="feed-details"><h2 class="section-title">Claims it does not support</h2>
    <ul>
      <li><strong>"The worst transit agency in [country]."</strong> The scorecard covers a
      curated set of feeds, not every agency in any country; absence means not covered,
      never failing, and a position here is not a national rank.</li>
      <li><strong>"Agency X's vehicles are inaccessible."</strong> The accessibility number
      measures whether the data is published, never whether a stop or vehicle is usable.</li>
      <li><strong>"Agency X is out of compliance."</strong> Nothing here is an official
      determination; the readiness signals map data quality onto requirements, and the
      official checks belong to the agencies and their regulators.</li>
      <li><strong>Grade differences as agency performance.</strong> A grade describes the
      published feed bytes under a disclosed scoring contract, not the agency's capacity or
      service quality. Public absolute rankings and individual peer percentiles are not
      published; direct comparisons appear only for like-for-like scorecards.</li>
    </ul></section>

    <section class="feed-details"><h2 class="section-title">Story-ready data</h2>
    <p>Every number on this site is downloadable. Start with the
    <a href="/pulse/">coverage overview</a>, then use the country and subdivision
    rows in <a href="/api/v1/by-location.json">the location API</a> to state the
    denominator precisely. For a citable snapshot, use a dated
    <a href="https://github.com/ChelseaKR/gtfs-scorecard/releases">dataset release</a>
    rather than the live site, which can change after a completed scoring run. Methodology, rubric weights, and
    the validator version are all published:
    <a href="/how-to-read/">how to read a scorecard</a> and
    <a href="/data/">the open dataset</a>.</p></section>

    <section class="feed-details"><h2 class="section-title">United States reporting context</h2>
    <p>U.S.-only reporting can also use the <a href="/ntd/">FTA NTD readiness</a>
    view, <a href="/ntd/shapes/">Report Year 2026 shapes.txt explainer</a>, state
    program pages, and the compatibility
    <a href="/api/v1/by-state.json">by-state API</a>. These sources support claims
    about the covered U.S. feeds and should not be generalized to other countries.</p></section>

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
      <li><strong>Zero validator errors</strong> is the same baseline publishers and
      trip-planning apps apply, so your feed loads everywhere riders look.</li>
      <li><strong>A 30-day forward window</strong> stops the silent failure where a feed
      quietly expires and trip planners drop your agency.</li>
      <li><strong>Accessibility fields</strong> let a wheelchair user plan a trip at all.</li>
      <li><strong>A stable public URL</strong> lets trip planners refresh the feed
      reliably instead of silently retaining an obsolete copy.</li>
    </ul></section>

    <section class="feed-details"><h2 class="section-title">Verify it cheaply</h2>
    <p>You do not need to take the vendor's word for it. Find your agency on this site to see
    where the feed stands today, add a <a href="{repo}/blob/main/docs/ci-action.md">GTFS
    Scorecard check</a> to a build so a bad feed fails before it publishes, or
    <a href="/try.html">request a one-off score</a> through the GitHub-backed path.</p></section>

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
    """The corpus realtime-reliability view, for a data team or a regional program.
    Reads the rollup (``rt_national.national_rt``) over the uptime and header-lag
    samples the monitor already records and shows how many realtime feeds are
    reliable, the corpus median uptime and freshness, a U.S. state breakdown, and
    the most reliable feeds. It changes no grade; absence of a realtime feed is
    shown neutrally elsewhere, so this page only covers agencies that publish one.
    """
    count = nat.get("monitored_feed_record_count", nat.get("monitored_count", 0))
    comparable_count = _guarded_comparison_count(nat)
    raw_count = nat.get("feed_record_count", 0)
    raw_monitored_count = nat.get("raw_monitored_feed_record_count", 0)
    bands = nat.get("bands", {})
    if comparable_count > 0 and count:
        band_rows = "".join(
            f"<tr><td>{esc(_RT_BAND_LABELS.get(key, key))}</td><td>{esc(bands.get(key, 0))}</td></tr>"
            for key in ("reliable", "mostly", "spotty")
        )
        band_chart = _service_bar_chart(
            [
                (
                    _RT_BAND_LABELS[key],
                    round(100 * int(bands.get(key, 0)) / count, 1),
                    f"{bands.get(key, 0)} of {count} feeds",
                )
                for key in ("reliable", "mostly", "spotty")
            ],
            title="Realtime reliability bands",
            note="Share of monitored feeds in each uptime band.",
            css_class="reliability-chart",
        )
        band_table = (
            '<section class="feed-details"><h2 class="section-title">Where feeds stand</h2>'
            f'{band_chart}<details class="viz-data"><summary>Show the table</summary>'
            '<table class="leaderboard"><thead><tr><th>Reliability</th><th>Feeds</th>'
            f"</tr></thead><tbody>{band_rows}</tbody></table></details></section>"
        )
        reliable = nat.get("most_reliable", [])
        hist = histories or {}
        reliable_rows = "".join(
            f'<tr><td><a href="/agency/{esc(m["id"])}/"><bdi>{esc(m["name"])}</bdi></a></td>'
            f"<td><bdi>{esc(_location_label(m))}</bdi></td><td>{esc(m['uptime_pct'])}%</td>"
            f"<td>{esc(m.get('median_lag_seconds'))}</td>"
            f"<td>{_spark_mini(hist.get(str(m['id'])), str(m['name']))}</td></tr>"
            for m in reliable
        )
        reliable_table = (
            (
                '<section class="feed-details"><h2 class="section-title">Most reliable</h2>'
                '<p class="page-lede">Comparison-eligible feed records that responded on nearly every check, freshest '
                "first. A target to aim for.</p>"
                '<table class="leaderboard"><thead><tr><th>Feed record</th><th>Location</th>'
                "<th>Uptime</th><th>Median lag (s)</th><th>Score trend</th></tr></thead>"
                f"<tbody>{reliable_rows}</tbody></table></section>"
            )
            if reliable
            else ""
        )
        state_rows = "".join(
            f"<tr><td>{esc(s['state'])}</td>"
            f"<td>{esc(s.get('feed_records', s.get('agencies', 0)))}</td>"
            f"<td>{esc(s.get('median_uptime_pct'))}%</td><td>{esc(s['reliable'])}</td></tr>"
            for s in nat.get("states", [])
        )
        state_table = (
            '<section class="feed-details"><h2 class="section-title">United States by state</h2>'
            '<table class="leaderboard"><thead><tr><th>State</th><th>Feeds</th>'
            "<th>Median uptime</th><th>Reliable</th></tr></thead>"
            f"<tbody>{state_rows}</tbody></table></section>"
        )
        location_table = _portable_rollup_table(
            nat.get("countries") or [],
            [
                ("feed_records", "Feed records", ""),
                ("median_uptime_pct", "Median uptime", "%"),
                ("reliable", "Reliable", ""),
            ],
        )
        lag = nat.get("median_lag_seconds")
        lag_txt = f"{esc(lag)} seconds" if lag is not None else "not recorded"
        lead = (
            f"Across <strong>{esc(count)} monitored feed records</strong>, the median realtime "
            f"feed responded <strong>{esc(nat.get('median_uptime_pct'))}% of the time</strong>, "
            f"with the data arriving about {lag_txt} behind real time."
        )
    elif comparable_count <= 0:
        band_table = reliable_table = state_table = location_table = ""
        lead = (
            "Cross-feed realtime reliability is unavailable until current-contract checks "
            "create a comparable feed-record cohort. The raw monitor state contains "
            f"{esc(raw_monitored_count)} observed feed records, but this snapshot makes no "
            "reliability aggregate or named-feed claim."
        )
    else:
        band_table = reliable_table = state_table = location_table = ""
        lead = (
            f"{comparable_count} feed records meet the comparison contract, but none has "
            "a realtime monitor observation yet."
        )
    comparison_note = (
        f"The directory contains {esc(raw_count)} published feed records; "
        f"{esc(comparable_count)} meet {_comparison_contract_text(nat.get('comparison') or {})}, "
        f"and {esc(count)} have realtime observations used here."
        if comparable_count > 0
        else f"The directory contains {esc(raw_count)} published feed records. "
        "No cross-feed denominator is published for this snapshot."
    )
    return _page(
        title="Realtime reliability — GTFS Scorecard",
        description=(
            "How reliable the covered GTFS-Realtime feed records are: "
            "uptime and freshness across the corpus, with regional breakdowns."
        ),
        canonical=f"{BASE_URL}/realtime/",
        wide=True,
        body=_strip_blank_line_whitespace(
            f"""    {_breadcrumb([("Home", "/"), ("Realtime reliability", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Realtime reliability.</h1>
    <p class="page-lede">{lead}</p>
    {band_table}
    {reliable_table}
    {location_table}
    {state_table}
    <p class="plain-summary"><strong>In plain words:</strong> a realtime feed is only useful if
    it is actually up and current. This tracks whether each monitored feed responded when we
    checked and how far behind real time it was. An agency that publishes no realtime feed is not
    counted here and is never penalized for it.</p>
    <p class="fineprint">Reliability is the share of monitor runs the feed responded to, over the
    recorded window; freshness is the median header lag. It never changes a grade. The same data
    is at <a href="/api/v1/realtime.json">the realtime API (realtime.json)</a>. Sampling is
    periodic, not continuous, so this is a reliability signal, not a complete uptime log.
    {comparison_note}</p>"""
        ),
    )


_PROBLEM_CHART_LABELS = {
    "scorecard_wheelchair_boarding_unknown": "Stops missing wheelchair boarding information",
    "scorecard_wheelchair_accessible_unknown": (
        "Trips missing wheelchair accessibility information"
    ),
    "unknown_column": "Non-standard columns",
    "unknown_file": "Non-standard files",
    "expired_calendar": "Expired service calendars",
    "service_window_outside_feed_period": "Service dates outside the feed period",
}


def _problem_chart_label(problem: dict[str, Any]) -> str:
    """Stable corpus label for a problem whose ``what`` may contain one
    agency's instance counts. Known common findings get practitioner-facing
    copy; other validator codes get a readable fallback rather than presenting
    one feed's numbers as the name of a corpus metric."""
    code = str(problem.get("code") or "problem")
    if code in _PROBLEM_CHART_LABELS:
        return _PROBLEM_CHART_LABELS[code]
    return code.removeprefix("scorecard_").replace("_", " ").capitalize()


def _render_problems_page(nat: dict[str, Any]) -> str:
    """The corpus "most common GTFS problems" knowledge base, for a practitioner
    or a journalist. Reads the prevalence rollup and lists
    the most widespread problems across tracked feeds, each with how many feeds
    share it, what it means, and the one fix. Framed as common, fixable problems,
    never as a ranking of who is worst; it changes no grade.
    """
    problems = nat.get("problems", [])
    total = nat.get("comparison_feed_record_count", nat.get("total_agencies", 0))
    comparable_count = _guarded_comparison_count(nat)
    raw_count = nat.get("feed_record_count", 0)
    guarded_available = comparable_count > 0 and total == comparable_count
    if guarded_available and problems:
        rows = ""
        for p in problems:
            code = esc(p["code"])
            label = _problem_chart_label(p)
            guide = (
                f' <a class="fix-guide" href="/fix/{code}/">Read the fix guide</a>'
                if p["code"] in FIX_CODES_WITH_PAGES
                else ""
            )
            rows += (
                '<li class="event">'
                f"<p><strong>{esc(label)}</strong> "
                f'<span class="mgrade">({esc(p["prevalence_pct"])}% of feeds, '
                f"{esc(p['severity'])})</span></p>"
                f'<p class="problem-example"><strong>Typical finding:</strong> {esc(p["what"])}</p>'
                f"<p>{esc(p['why'])}</p>"
                f"<p><strong>Fix:</strong> {esc(p['fix'])}"
                f"{(' Effort: ' + esc(p['effort']) + '.') if p.get('effort') else ''}"
                f"{guide}</p>"
                "</li>"
            )
        chart_rows = [
            (
                _problem_chart_label(p),
                float(p.get("prevalence_pct", 0)),
                f"{p.get('feed_records', p.get('agencies', 0))} feed records",
            )
            for p in problems[:6]
        ]
        prevalence_chart = _service_bar_chart(
            chart_rows,
            title="The six most widespread problems",
            note="Share of comparison-eligible feed records carrying each problem.",
            css_class="problems-chart",
        )
        body_problems = (
            f"{prevalence_chart}"
            '<h3 class="section-sub">What each problem means and how to fix it</h3>'
            f'<ul class="events">{rows}</ul>'
        )
        lead = (
            f"Across {esc(total)} comparable feed records, these are the problems most feeds "
            "share. Each one is common, which means each fix helps a lot of riders at once."
        )
    elif guarded_available:
        body_problems = ""
        lead = (
            f"The {esc(total)} comparable feed records have no aggregated findings in this "
            "snapshot. This is a measured empty result under one producer contract."
        )
    else:
        problems = []
        body_problems = ""
        lead = (
            "Cross-feed problem prevalence is unavailable until current-contract checks "
            "create a comparable feed-record cohort. This snapshot makes no clean-corpus "
            "or most-common-problem claim."
        )
    # Plain-language coverage governance: how much of what readers see in the corpus
    # carries curated what/why/fix text, plus the queue of what to curate next.
    # The metric makes the curation debt visible, which is the feature.
    coverage = plain_language_coverage(nat)
    if guarded_available and coverage["total_codes"]:
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
                '<div class="table-wrap"><table class="leaderboard"><thead><tr><th>Notice code</th>'
                "<th>Instances</th><th>Feed records</th></tr></thead>"
                f"<tbody>{queue_rows}</tbody></table></div>"
            )
        else:
            queue_table = "<p>Every problem code seen in the covered corpus has curated text.</p>"
        coverage_section = (
            '<section class="feed-details" aria-labelledby="coverage-h">'
            '<h2 class="section-title" id="coverage-h">Plain-language coverage</h2>'
            f"<p>Of the <strong>{esc(coverage['total_codes'])}</strong> distinct problem "
            f"codes seen in the covered corpus, <strong>{esc(coverage['curated_codes'])}</strong> carry "
            "vetted plain-language text: "
            f"<strong>{esc(coverage['distinct_code_coverage'])}%</strong> of codes and "
            f"<strong>{esc(coverage['instance_weighted_coverage'])}%</strong> of all finding "
            "instances. Codes without curated text fall back to a generic line that links "
            "to the validator's rule documentation.</p>"
            f"{queue_table}</section>"
        )
    else:
        coverage_section = ""
    plain_summary = (
        "most feeds trip on the same handful of things, and most of those are one export "
        "setting. If you run an agency, scanning this list is a fast way to find a fix that "
        "probably applies to you too."
        if guarded_available and problems
        else "this page waits for a valid comparison denominator before describing a problem "
        "as common across feeds. Open an individual scorecard for its own current findings."
    )
    return _page(
        title="The most common GTFS problems — GTFS Scorecard",
        description=(
            "The most widespread GTFS data problems across covered transit feeds, how many "
            "feed records share each, and the one fix for each."
        ),
        canonical=f"{BASE_URL}/problems/",
        wide=True,
        body=_strip_blank_line_whitespace(
            f"""    {_breadcrumb([("Home", "/"), ("Common problems", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">The most common GTFS problems.</h1>
    <p class="page-lede">{lead}</p>
    <section aria-labelledby="problems-h">
    <h2 class="section-title visually-hidden" id="problems-h">Most common problems</h2>
    {body_problems}
    </section>
    {coverage_section}
    <p class="plain-summary"><strong>In plain words:</strong> {plain_summary}</p>
    <p class="fineprint">The directory contains {esc(raw_count)} published feed records.
    Prevalence uses {esc(comparable_count)} canonical, non-duplicate records under
    {_comparison_contract_text(nat.get("comparison") or {})}. It never changes a grade.
    The same data is at
    <a href="/api/v1/problems.json">the problems API (problems.json)</a>.</p>"""
        ),
    )


def _trend_sections(
    points: list[dict[str, Any]],
    summary: dict[str, Any],
    improvers: list[dict[str, Any]] | None = None,
) -> str:
    """The guarded corpus quality trend, inside the coverage page: the average score over
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
            aria_label=f"Covered-corpus average score by date (axis {lo:.1f} to {hi:.1f})",
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
            f"Across feed scorecards with one rubric, scoring profile, validator, and measured "
            f"category set, the corpus average score {move} between "
            f"{esc(summary['first']['date'])} and {esc(summary['last']['date'])} "
            f"(now {esc(summary['last']['average_score'])})."
        )
        chart = f'<section class="feed-details"><h2 class="section-title">Covered-corpus average score</h2><p>{spark}</p>{axis}</section>'
    elif len(points) == 1:
        table = chart = ""
        date = esc(str(points[0].get("date") or ""))
        lead = (
            f"Comparable history under the current scoring contract begins on {date}. "
            "A trend appears after the corpus is checked on a later date. Rechecks on "
            "the same day update that day's snapshot instead of adding another point."
        )
    else:
        table = chart = ""
        lead = (
            "A coverage trend appears here once the corpus has been checked on more than one day."
        )

    # Top improvers section
    if improvers:
        imp_rows = "".join(
            f"<tr>"
            f'<td><a href="/agency/{esc(r["id"])}/"><bdi>{esc(r["name"])}</bdi></a></td>'
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


def _remove_unlisted_agency_pages(agency_pages: Path, published_ids: set[str]) -> None:
    """Remove generated HTML for ids absent from the bounded artifact index."""
    if not agency_pages.exists():
        return
    for page_dir in agency_pages.iterdir():
        if page_dir.is_dir() and page_dir.name not in published_ids:
            shutil.rmtree(page_dir)


def _remove_stale_agency_index_pages(page_root: Path) -> None:
    """Remove only generated numeric directory pages before rebuilding them."""
    if not page_root.exists():
        return
    for page_dir in page_root.iterdir():
        if page_dir.is_dir() and page_dir.name.isdigit():
            shutil.rmtree(page_dir)


def _scope_liveness_state(
    liveness_state: dict[str, dict[str, Any]], published_ids: set[str]
) -> dict[str, dict[str, Any]]:
    """Restrict refresh-success evidence to the current published catalog."""
    return {
        agency_id: record
        for agency_id, record in liveness_state.items()
        if agency_id in published_ids
    }


def _has_auditable_change_contract(payload: object) -> bool:
    """Whether a named-change snapshot discloses a complete comparison contract."""
    if not isinstance(payload, dict):
        return False
    comparison = payload.get("comparison")
    eligible = payload.get("comparison_eligible_count")
    changes = payload.get("changes")
    if not isinstance(comparison, dict) or not isinstance(eligible, int):
        return False
    if comparison.get("eligible_count") != eligible:
        return False
    if not isinstance(changes, list) or payload.get("count") != len(changes):
        return False
    for key in (
        "required_rubric_version",
        "required_scoring_profile_id",
        "required_validator_version",
        "required_reader_archive_profile",
    ):
        if not isinstance(comparison.get(key), str) or not comparison[key].strip():
            return False
    return isinstance(comparison.get("required_measured_categories"), list)


def _prune_unverifiable_change_snapshots(changes_dir: Path) -> None:
    """Remove legacy named-change JSON that cannot prove its comparison basis."""
    if not changes_dir.exists():
        return
    for path in changes_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            payload = None
        if not _has_auditable_change_contract(payload):
            path.unlink(missing_ok=True)


def _apply_registry_agency_names(
    index: dict[str, Any],
    registry_by_id: dict[str, Agency],
) -> bool:
    """Overlay mutable curated names onto the current derived index."""
    changed = False
    for agency_id, entry in (index.get("agencies") or {}).items():
        if not isinstance(entry, dict):
            continue
        registry = registry_by_id.get(str(agency_id))
        name = resolve_published_agency_name(
            str(agency_id),
            registry_name=registry.name if registry else "",
            artifact_name=str(entry.get("name") or ""),
        )
        if entry.get("name") != name:
            entry["name"] = name
            changed = True
    return changed


def render_site(now: dt.datetime | None = None) -> list[Path]:  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
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
    index_file = art / "index.json"
    index = json.loads(index_file.read_text()) if index_file.exists() else {"agencies": {}}
    published_ids = {str(agency_id) for agency_id in (index.get("agencies") or {})}
    raw_liveness_state = _load_liveness()
    liveness_state = _scope_liveness_state(raw_liveness_state, published_ids)
    # Empirical finding-clearance timing, loaded once for the whole render.
    # Empty when the corpus has not yet written a calibration file, which keeps
    # the causally neutral band purely additive (EXP-03).
    effort_bands = _load_effort_bands()
    written: list[Path] = []
    urls: list[str] = [
        f"{BASE_URL}/",
        f"{BASE_URL}/about/",
        f"{BASE_URL}/support/",
        f"{BASE_URL}/fetcher/",
        f"{BASE_URL}/data/",
        f"{BASE_URL}/submit.html",
        f"{BASE_URL}/try.html",
        f"{BASE_URL}/subscribe.html",
        f"{BASE_URL}/agencies/",
    ]
    sitemap_lastmods: dict[str, str] = {}
    FIX_CODES_WITH_PAGES.clear()  # rebuilt below; never carry state across calls

    def write(
        rel: str, content: str, url: str | None = None, *, lastmod: str | None = None
    ) -> None:
        path = web / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        written.append(path)
        if url:
            urls.append(url)
            if lastmod:
                sitemap_lastmods[url] = lastmod

    # Fix KB pages first, so agency findings can link to the ones that exist.
    fixes_dir = root / "docs" / "fixes"
    fix_guides: list[dict[str, str]] = []
    for md_file in sorted(fixes_dir.glob("*.md")):
        if md_file.stem == "README":
            continue
        FIX_CODES_WITH_PAGES.add(md_file.stem)
    for md_file in sorted(fixes_dir.glob("*.md")):
        if md_file.stem == "README":
            continue
        code = md_file.stem
        document = _parse_authored_markdown(md_file.read_text(), str(md_file))
        body_html, title_text = _md_to_html(document.body)
        fix_guides.append(
            {
                "code": code,
                "title": title_text or f"Fix: {code}",
                "description": _fix_description(body_html, code),
                "category": _fix_category(code),
            }
        )
        write(
            f"fix/{code}/index.html",
            _render_fix(code, document),
            f"{BASE_URL}/fix/{code}/",
            lastmod=document.date_modified,
        )
    write("fix/index.html", _render_fix_index(fix_guides), f"{BASE_URL}/fix/")

    write("how-to-read/index.html", _render_guide(), f"{BASE_URL}/how-to-read/")
    # Retire the hand-built visual prototype now that its strongest ideas live
    # in the shared system. Keep old links useful without presenting a third,
    # stale design language or indexing duplicate guidance.
    write("concept/index.html", _redirect_page("/how-to-read/", "Design concept"))
    write("accessibility/index.html", _render_accessibility(), f"{BASE_URL}/accessibility/")
    write("claim/index.html", _render_claim_page(), f"{BASE_URL}/claim/")
    validate_catalogs()
    write("es/index.html", _render_spanish_rider_page(), f"{BASE_URL}/es/")
    for locale in SUPPORTED_LOCALES:
        write(f"locales/{locale}.json", (CATALOG_DIR / f"{locale}.json").read_text())
    for locale in APP_CATALOG_LOCALES:
        write(f"locales/app.{locale}.json", (CATALOG_DIR / f"app.{locale}.json").read_text())
    # The derived pseudolocale ships only as a preview catalog the app loads
    # behind an explicit ?l10n=en-XA request; it is not a production language.
    write(
        f"locales/app.{PSEUDOLOCALE}.json",
        json.dumps(load_app_catalog(PSEUDOLOCALE), sort_keys=True, indent=2, ensure_ascii=False)
        + "\n",
    )

    # The consumer-facing freshness/uptime commitment (EXP-10): machine-readable
    # status.json, extending FIX-11's internal run-summary outward. Built from
    # the same liveness state the intraday refresh keeps, so it renders (with
    # an honest empty record) even before the first refresh has ever run. The
    # human-readable page is written later, once the run summary and catalog
    # (FIX-11's half of /status/) are also ready -- see `_render_status`.
    from .status_commitment import build_status_commitment

    status_doc = build_status_commitment(liveness_state, now, BASE_URL)
    status_doc["scope"] = {
        "published_feed_record_count": len(published_ids),
        "liveness_records_in_scope": len(liveness_state),
        "liveness_records_outside_current_published_set": (
            len(raw_liveness_state) - len(liveness_state)
        ),
        "note": (
            "Liveness statistics are restricted to feed records in the current published "
            "artifact index. Records outside that index are excluded."
        ),
    }
    write(
        "api/v1/status.json",
        json.dumps(status_doc, indent=2, sort_keys=True) + "\n",
    )
    crosswalk_file = root / "docs" / "crosswalk.md"
    if crosswalk_file.exists():
        crosswalk = _parse_authored_markdown(crosswalk_file.read_text(), str(crosswalk_file))
        write(
            "crosswalk/index.html",
            _render_crosswalk_page(crosswalk),
            f"{BASE_URL}/crosswalk/",
            lastmod=crosswalk.date_modified,
        )

    # web/ is committed between renders. Remove generated scorecard directories
    # that are no longer present in the registry-bounded index, or a delisted
    # feed would retain a directly reachable HTML page after disappearing from
    # the directory and sitemap.
    _remove_unlisted_agency_pages(web / "agency", published_ids)
    from .publish import enrich_index_history_provenance

    index_changed = enrich_index_history_provenance(index, art)
    from .config import AGENCIES

    # CLI renders have the registry loaded already. Direct library callers use
    # the same manifest-aware reader without mutating the process-global map.
    registry_by_id = dict(AGENCIES)
    if not registry_by_id:
        from .agencies import read_agencies

        registry_by_id = {agency.id: agency for agency in read_agencies()}
    index_changed |= _apply_registry_agency_names(index, registry_by_id)
    if index_changed:
        index_file.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    # Per-feed score histories, keyed by id, for compact trend graphics on
    # named change, NTD one-fix, and realtime tables.
    histories: dict[str, list[dict[str, Any]]] = {
        str(aid): (entry or {}).get("history") or []
        for aid, entry in (index.get("agencies") or {}).items()
    }
    # Per-feed change-detection freshness from the intraday refresh; loaded once,
    # early, so both the directory's expired-feed split and each agency page
    # (below) read the same state. Keep every directory document bounded: the
    # production corpus is large enough that one giant HTML list delays first
    # paint even though the content itself is static.
    agency_page_root = web / "agencies" / "page"
    _remove_stale_agency_index_pages(agency_page_root)
    agency_count = len(index.get("agencies") or {})
    agency_page_count = max(1, math.ceil(agency_count / _AGENCY_INDEX_PAGE_SIZE))
    for page_number in range(1, agency_page_count + 1):
        page_href = _agency_index_href(page_number)
        page_rel = (
            "agencies/index.html" if page_number == 1 else f"agencies/page/{page_number}/index.html"
        )
        write(
            page_rel,
            _render_agency_index(
                index,
                liveness_state,
                page=page_number,
                page_size=_AGENCY_INDEX_PAGE_SIZE,
            ),
            f"{BASE_URL}{page_href}" if page_number > 1 else None,
        )
    states = _states_by_agency()

    # Pass 1: read each scorecard once to build the catalog records the
    # directory needs (grade, score, location, size, and comparison provenance).
    catalog: list[dict[str, Any]] = []
    directory_catalog: list[dict[str, Any]] = []
    ntd_artifacts: list[dict[str, Any]] = []
    artifacts_by_id: dict[str, dict[str, Any]] = {}
    problem_findings_by_id: dict[str, list[dict[str, Any]]] = {}
    from .features import feature_measurements

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
        categories = artifact.get("categories", {})
        fresh = artifact.get("categories", {}).get("freshness", {}).get("details", {})
        comp = artifact.get("categories", {}).get("completeness", {}).get("details", {})
        feed = artifact.get("feed", {})
        fixes = artifact.get("top_fixes", [])
        days = fresh.get("days_until_expiry")
        agency_cfg = registry_by_id.get(agency_id)
        artifact_agency = artifact.setdefault("agency", {})
        artifact_agency["name"] = resolve_published_agency_name(
            agency_id,
            registry_name=agency_cfg.name if agency_cfg else "",
            artifact_name=str(artifact_agency.get("name") or ""),
        )
        location = resolve_published_location(
            registry_country=agency_cfg.country if agency_cfg else "",
            registry_subdivision_code=agency_cfg.subdivision_code if agency_cfg else "",
            registry_subdivision_name=agency_cfg.subdivision_name if agency_cfg else "",
            artifact_country=str(artifact_agency.get("country") or ""),
            artifact_subdivision_code=str(artifact_agency.get("subdivision_code") or ""),
            artifact_subdivision_name=str(artifact_agency.get("subdivision_name") or ""),
            legacy_state=states.get(agency_id, ""),
        )
        # Artifacts don't persist state; inject it so the NTD portfolio's
        # per-state breakdown works at publish time.
        artifact_agency["state"] = states.get(agency_id, "")
        artifacts_by_id[agency_id] = artifact
        ntd_artifacts.append(artifact)
        problem_findings_by_id[agency_id] = agency_findings(artifact)
        catalog_record = {
            "id": agency_id,
            "name": artifact["agency"]["name"],
            "grade": overall["grade"],
            "score": overall["score"],
            "correctness": (categories.get("correctness") or {}).get("score"),
            "freshness": (categories.get("freshness") or {}).get("score"),
            "completeness": (categories.get("completeness") or {}).get("score"),
            "realtime": (categories.get("realtime") or {}).get("score"),
            "state": states.get(agency_id, ""),
            # ISO country code so consumers and the app can place non-US
            # agencies (Canada) instead of bucketing them as unlocated.
            "country": location.country_code,
            "stops": comp.get("stops"),
            "snapshot_date": artifact["snapshot_date"],
            "days_until_expiry": days,
            "service_horizon_status": resolve_service_horizon_status(
                fresh, artifact.get("snapshot_date")
            ),
            "expiry_status": expiry_status(days),
            # Readiness for the FTA NTD GTFS requirement (published/valid/
            # current/agency_id), so a state program can filter its portfolio by who is
            # ready to certify without opening each scorecard. NTD is a
            # US-federal concept, so this is null for non-US feeds (ADR 0026):
            # the directory filter and national rollup never count them.
            "ntd_ready": (ntd_assess(artifact).status if location.country_code == "US" else None),
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
            "reader_archive_profile": reader_archive_profile(artifact),
            "rubric_version": artifact.get("rubric_version"),
            "scoring_profile_id": (artifact.get("scoring_profile") or {}).get("id"),
            "scoring_profile_rubric_version": (artifact.get("scoring_profile") or {}).get(
                "rubric_version"
            ),
            "retrieved_at": artifact.get("generated_at"),
            "feed_sha256": feed.get("sha256"),
        }
        if location.subdivision_code:
            catalog_record["subdivision_code"] = location.subdivision_code
        if location.subdivision_name:
            catalog_record["subdivision_name"] = location.subdivision_name
        catalog.append(catalog_record)
        directory_record = dict(catalog_record)
        directory_record.update(feature_measurements(artifact))
        directory_catalog.append(directory_record)

    # The directory dataset the coverage view reads: per-feed size tier plus
    # national and location summaries. Score aggregates use a current-rubric,
    # identity-safe cohort; every record remains searchable. Built before the
    # flat catalog because it enriches each record in place with size_tier,
    # which the catalog then carries too. Written alongside index.json under
    # data/artifacts so the web app reaches it through the same data base it uses
    # for index.json and per-agency artifacts, and so the existing
    # `git add data/artifacts` publishes it.
    directory = build_directory(
        directory_catalog,
        dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        agencies=registry_by_id.values(),
    )
    (art / "directory.json").write_text(json.dumps(directory, indent=2, sort_keys=True) + "\n")
    by_id = {r["id"]: r for r in directory["agencies"]}
    agency_seo_metadata = _plan_agency_seo_metadata(
        directory["agencies"],
        artifacts_by_id,
        registry_by_id,
    )
    # build_directory adds the existing catalog's size and comparison fields.
    # Copy only those established fields back; feature measurements belong to
    # directory.json and features.json, not the older flat catalog contract.
    for catalog_record in catalog:
        directory_record = by_id[catalog_record["id"]]
        for key in (
            "size_tier",
            "national_percentile",
            "peer_percentile",
            "comparison_eligible",
        ):
            catalog_record[key] = directory_record[key]
    from . import RUBRIC_VERSION
    from .comparisons import build_comparison_cohort

    comparable_records, _comparison_metadata = build_comparison_cohort(
        catalog, agencies=registry_by_id.values()
    )
    comparable_ids = {str(record["id"]) for record in comparable_records}
    comparable_artifacts = [
        artifacts_by_id[agency_id]
        for agency_id in sorted(comparable_ids)
        if agency_id in artifacts_by_id
    ]
    aggregate_context = {
        "feed_record_count": len(catalog),
        "comparison_eligible_count": len(comparable_ids),
        "comparison": _comparison_metadata,
    }

    # Row-level consumer feature data: every current feed record, with unknown
    # measurements kept distinct from a measured feature absence. The live
    # directory reads the same enriched records, while this stable v1 endpoint
    # lets other consumers build their own capability, completeness, and
    # geography filters without opening ~1,200 per-agency artifacts.
    from .features import build_feature_dataset

    feature_payload = build_feature_dataset(
        directory["agencies"], directory["generated_at"], _comparison_metadata
    )
    write(
        "api/v1/features.json",
        json.dumps(feature_payload, indent=2, sort_keys=True) + "\n",
    )

    # Evidence-gated global expansion contract: this deliberately measures a
    # bounded European GTFS Schedule cohort, not Europe as a whole. Build it
    # from the registry plus the same directory and feature documents consumers
    # receive, then publish the complete evidence rows for auditability.
    from .global_coverage import build_global_coverage

    global_coverage_payload = build_global_coverage(
        registry_by_id.values(),
        directory,
        feature_payload,
        now.astimezone(dt.UTC).isoformat(timespec="seconds"),
        now=now,
    )
    write(
        "api/v1/global-coverage.json",
        json.dumps(global_coverage_payload, indent=2, sort_keys=True) + "\n",
    )

    # Daily change feed: agencies whose grade or score moved since their last
    # check, so a consumer ingests transitions instead of diffing the whole
    # catalog. Written under data/artifacts (served and committed like the rest)
    # as a stable changes/latest.json plus an immutable dated copy.
    from . import DATA_ATTRIBUTION, DATA_LICENSE, SCHEMA_VERSION

    changes = compute_changes(
        index,
        allowed_ids=comparable_ids,
        required_rubric_version=RUBRIC_VERSION,
    )
    changes_payload = {
        "schema_version": SCHEMA_VERSION,
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "feed_record_count": len(catalog),
        "comparison_eligible_count": len(comparable_ids),
        "comparison": _comparison_metadata,
        "count": len(changes),
        "changes": changes,
    }
    changes_dir = art / "changes"
    changes_dir.mkdir(parents=True, exist_ok=True)
    # Before the comparison contract was explicit, dated change snapshots did
    # not disclose enough producer provenance to audit their named moves. Do
    # not keep serving those legacy claims merely because artifact hydration is
    # additive. Valid dated snapshots remain immutable.
    _prune_unverifiable_change_snapshots(changes_dir)
    changes_text = json.dumps(changes_payload, indent=2, sort_keys=True) + "\n"
    (changes_dir / "latest.json").write_text(changes_text)
    (changes_dir / f"{now.date().isoformat()}.json").write_text(changes_text)
    # The human view of the movers lives on the national pulse page now; the
    # retired URL keeps working via a static redirect (no sitemap entry).
    write("changes/index.html", _redirect_page("/pulse/#changes", "What changed"))
    # The same movers as a static Atom feed, so a reader, a state liaison, or a
    # webhook can subscribe to grade drops without an opt-in store or an email
    # sender (the email digest covers confirmed subscribers; this covers everyone
    # else). Deterministic: timestamps come from snapshot dates, not wall-clock.
    write(
        "changes/feed.xml",
        site_change_feed(changes, base_url=BASE_URL, comparison=_comparison_metadata),
    )

    # Machine-readable methodology (category weights, grade bands, correctness
    # deductions) so the grade is reproducible and contestable, not an opaque
    # opinion. Published alongside the artifacts.
    from .score import methodology

    scoring_json = json.dumps(methodology(), indent=2) + "\n"
    (art / "scoring.json").write_text(scoring_json)
    # Also publish it under the site's api/v1, next to leaderboard.json and
    # agencies.json, so the methodology sandbox on /how-to-read/ (and any other
    # consumer) can fetch the same weights + grade bands the pipeline scored with
    # over same-origin HTTP. One source (score.methodology), two byte-identical
    # copies, so the interactive widget and the pipeline agree by construction.
    write("api/v1/scoring.json", scoring_json)

    # Public pipeline-health surface (FIX-11): what the latest recorded run did,
    # merged by `scorecard run-summary merge` into data/artifacts/run/latest.json
    # in the collect job. Absent on the first render after this shipped (no run
    # has published a summary yet); the page and API both degrade to an
    # explicit "not published yet" rather than a broken page.
    run_summary_path = art / "run" / "latest.json"
    run_summary: dict[str, Any] | None = None
    if run_summary_path.exists():
        try:
            run_summary = json.loads(run_summary_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"::warning title=unreadable run summary::{run_summary_path}: {exc}",
                file=sys.stderr,
            )
    run_summary = _scope_run_summary(run_summary, catalog)
    write("api/v1/run-status.json", json.dumps(run_summary, indent=2, sort_keys=True) + "\n")
    # The combined /status/ page (EXP-10 + FIX-11): the commitment (status_doc,
    # computed above from liveness state) and latest-run evidence (run_summary
    # + catalog, both ready by this point in the render), composed into one page.
    write(
        "status/index.html",
        _render_status(status_doc, run_summary, catalog, now, global_coverage_payload),
        f"{BASE_URL}/status/",
    )

    # liveness_state was loaded earlier (with the directory page); each agency
    # page below reuses that same read.

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
        agency_cfg = registry_by_id.get(agency_id)
        artifact_agency = artifact.setdefault("agency", {})
        artifact_agency["name"] = resolve_published_agency_name(
            agency_id,
            registry_name=agency_cfg.name if agency_cfg else "",
            artifact_name=str(artifact_agency.get("name") or ""),
        )
        # Feed every public narrative surface the same mode-aware copy. This
        # covers the full scorecard, call brief, and board one-pager together.
        from .mode_language import adapt_artifact_language

        artifact = adapt_artifact_language(artifact)
        artifact["canada_equity"] = canada_equity.get(agency_id)
        feature = _map_feature(
            agency_id,
            artifact,
            by_id[agency_id].get("state", ""),
            by_id[agency_id].get("country", ""),
            by_id[agency_id].get("subdivision_code", ""),
            by_id[agency_id].get("subdivision_name", ""),
        )
        if feature is not None:
            map_features.append(feature)
        history = index["agencies"][agency_id].get("history", [])
        # The dated snapshots (oldest first; the newest equals latest.json) drive
        # both the previous-run finding diff and the grade story, so read each one
        # once and reuse. An unreadable day is skipped, not fatal.
        dated = sorted((art / agency_id).glob("[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json"))
        dated_artifacts: list[dict[str, Any]] = []
        for dated_path in dated:
            try:
                dated_artifacts.append(json.loads(dated_path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        prev_artifact = _previous_indexed_artifact(agency_id, history, dated_artifacts)
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
                artifacts=dated_artifacts,
                effort_bands=effort_bands,
                seo_metadata=agency_seo_metadata[agency_id],
            ),
            f"{BASE_URL}/agency/{agency_id}/",
            lastmod=str(artifact.get("snapshot_date") or "") or None,
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
        )
        # The board packet one-pager: same precomputed fields, different reader
        # (the agency's board rather than the liaison), so progress leads and the
        # fixes read as the asks (docs/RESEARCH-ROADMAP.md E6).
        write(
            f"agency/{agency_id}/board/index.html",
            _render_board_page(
                artifact, history, prev_artifact, by_id[agency_id], effort_bands=effort_bands
            ),
        )
        # The durable clearance log, only once the collect step has recorded at
        # least one provenance-bearing receipt. Remove a previously generated
        # page when reconciliation fails closed, or committed web output would
        # keep serving a stale claim after its evidence disappeared.
        fixlog_page_dir = web / "agency" / agency_id / "fixes"
        if receipts:
            write(
                f"agency/{agency_id}/fixes/index.html",
                _render_fixlog_page(
                    artifact,
                    receipts,
                    by_id[agency_id],
                    seo_metadata=agency_seo_metadata[agency_id],
                ),
                f"{BASE_URL}/agency/{agency_id}/fixes/",
            )
        elif fixlog_page_dir.exists():
            shutil.rmtree(fixlog_page_dir)
        # This feed's own Atom history (grade moves, expiry crossings, score
        # swings), so anyone supporting the agency can subscribe to just it. The
        # events are the same ones the "What changed over time" timeline shows.
        write(
            f"agency/{agency_id}/feed.xml",
            agency_change_feed(
                agency_id,
                artifact["agency"]["name"],
                history_events(_current_rubric_history(history)),
                base_url=BASE_URL,
            ),
        )

    # A flat machine-readable catalog so a consumer gets every agency's grade and
    # feed URL in one request instead of fetching every artifact.
    _write_catalog(write, catalog)

    # The open national quality dataset (one row per agency, latest score) plus a
    # CSV, so researchers and state programs can download and analyze it directly.
    from .dataset import build_quality_dataset, to_csv

    dataset = build_quality_dataset(index, agencies=registry_by_id.values())
    write("dataset.json", json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    write("dataset.csv", to_csv(dataset))

    # NTD GTFS-readiness portfolio (national + per state), so a program
    # lead can see "% ready to certify" without opening each scorecard.
    from .ntd import one_fix_from_ready, portfolio_summary, shapes_portfolio_summary

    # portfolio_summary excludes non-US feeds itself (NTD is US-federal); the full
    # ntd_artifacts list still feeds the GTFS-quality rollups below. See ADR 0026.
    summary = portfolio_summary(ntd_artifacts)
    one_fix = one_fix_from_ready(ntd_artifacts)
    # Additive: shapes.txt coverage rolled up the same way (FTA requires the file
    # from Full Reporters in RY2025 and Reduced, Rural, and Tribal Reporters in
    # RY2026), counted only over feeds where the check ran.
    shapes_summary = shapes_portfolio_summary(ntd_artifacts)
    shapes_payload: dict[str, Any] = {
        "total": shapes_summary.total,
        "ready": shapes_summary.ready,
        "at_risk": shapes_summary.at_risk,
        "not_ready": shapes_summary.not_ready,
        "pct_ready": shapes_summary.pct_ready,
        "by_state": shapes_summary.by_state,
    }
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
        "shapes": shapes_payload,
    }
    write("ntd.json", json.dumps(ntd_payload, indent=2, sort_keys=True) + "\n")
    # The human page over the same readiness numbers, for an FTA or state-DOT lead.
    write("ntd/index.html", _render_ntd_page(ntd_payload, histories), f"{BASE_URL}/ntd/")
    # The shapes.txt explainer: the RY2026 requirement in plain language, with the
    # national and per-state coverage numbers, for the manager hearing about the
    # requirement for the first time and the reporter covering it.
    write(
        "ntd/shapes/index.html",
        _render_shapes_page(shapes_payload),
        f"{BASE_URL}/ntd/shapes/",
    )

    # National accessibility-data coverage (how many feeds let a wheelchair user
    # plan a trip at all), for advocates and the programs that support them. Built
    # from the same artifacts already read, published as an API endpoint and a page.
    from .access import coverage_record, national_coverage

    coverage_records = [
        rec for art in comparable_artifacts if (rec := coverage_record(art)) is not None
    ]
    coverage = national_coverage(coverage_records)
    coverage_payload = {
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        **aggregate_context,
        **coverage,
    }
    write(
        "api/v1/accessibility.json",
        json.dumps(coverage_payload, indent=2, sort_keys=True) + "\n",
    )
    # Accessibility coverage lives on the What-feeds-publish page now.
    write("access/index.html", _redirect_page("/adoption/#access", "Accessibility data coverage"))

    # National adoption of the newer GTFS capabilities (flexible service, fare
    # data and Fares v2, station pathways), read from the same per-agency detail
    # completeness already records. Published as an API endpoint and a page.
    from .adoption import adoption_record, national_adoption

    adoption_records = [
        rec for art in comparable_artifacts if (rec := adoption_record(art)) is not None
    ]
    adoption_national = national_adoption(adoption_records)
    adoption_payload = {
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        **aggregate_context,
        **adoption_national,
    }
    write(
        "api/v1/adoption.json",
        json.dumps(adoption_payload, indent=2, sort_keys=True) + "\n",
    )
    write(
        "adoption/index.html",
        _render_adoption_page(adoption_payload, coverage_payload),
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
            cfg = registry_by_id.get(rt_id)
            name = cfg.name if cfg else index["agencies"].get(rt_id, {}).get("name", rt_id)
            rt_summaries.append(
                {
                    "id": rt_id,
                    "name": name,
                    "state": states.get(rt_id, ""),
                    "country": cfg.country if cfg else "",
                    "subdivision_code": cfg.subdivision_code if cfg else "",
                    "subdivision_name": cfg.subdivision_name if cfg else "",
                    **health.to_dict(),
                }
            )
    comparable_rt_summaries = [
        summary for summary in rt_summaries if str(summary.get("id") or "") in comparable_ids
    ]
    rt_rollup = national_rt(comparable_rt_summaries)
    rt_payload = {
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        **aggregate_context,
        "raw_monitored_feed_record_count": len(rt_summaries),
        **rt_rollup,
    }
    write(
        "api/v1/realtime.json",
        json.dumps(rt_payload, indent=2, sort_keys=True) + "\n",
    )
    write(
        "realtime/index.html",
        _render_rt_page(rt_payload, histories),
        f"{BASE_URL}/realtime/",
    )

    # National "most common problems" knowledge base, for practitioners and the
    # press. Findings are retained by feed id in pass 1, then restricted to the
    # guarded cohort here so duplicate or old-contract records cannot inflate
    # prevalence or the curation queue.
    from .findings_national import national_problems

    problems = national_problems(
        [problem_findings_by_id[agency_id] for agency_id in sorted(comparable_ids)],
        total_feed_records=len(comparable_ids),
    )
    problems_payload = {
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        **aggregate_context,
        **problems,
    }
    write(
        "api/v1/problems.json",
        json.dumps(problems_payload, indent=2, sort_keys=True) + "\n",
    )
    write(
        "problems/index.html",
        _render_problems_page(problems_payload),
        f"{BASE_URL}/problems/",
    )

    # National quality trend over time, derived from the per-agency histories in
    # the index (no new stored state), for the "is transit data getting better?"
    # question. Pure and reproducible.
    from .national_trend import as_of_points, trend_summary

    # Corpus claims use the same identity-safe, current-rubric cohort as the
    # directory aggregates. Strip older rubric points before building the
    # series so a methodology release cannot appear as national improvement or
    # regression. The named top-improvers ranking is retired; Pulse already
    # carries the guarded same-feed change view.
    trend_index = {
        "agencies": {
            agency_id: {
                **entry,
                "history": _current_rubric_history(entry.get("history", [])),
            }
            for agency_id, entry in index.get("agencies", {}).items()
            if agency_id in comparable_ids
        }
    }
    trend_points = as_of_points(trend_index)
    trend_sum = trend_summary(trend_points)
    improvers: list[dict[str, Any]] = []
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
                "comparison": _comparison_metadata,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    write("trends/index.html", _redirect_page("/pulse/#trend", "Coverage trend"))

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

    # The CLI populates AGENCIES before rendering. Direct library callers (the
    # golden renderer and downstream instance builders) may not, so load the
    # same registry file locally for coverage counts without mutating the
    # module-global registry.
    coverage_agencies = list(AGENCIES.values())
    if not coverage_agencies:
        coverage_agencies = list(registry_by_id.values())

    locations = {
        str(record["id"]): {
            "country": str(record.get("country") or ""),
            "subdivision_code": str(record.get("subdivision_code") or ""),
            "subdivision_name": str(record.get("subdivision_name") or ""),
        }
        for record in catalog
    }

    api = build_api(
        index,
        agencies=coverage_agencies,
        states=states,
        locations=locations,
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

    # United States rider-trips context (ADR 0021): when the NTD ridership snapshot is present
    # (the daily run fetches it via `scorecard ntd-ridership --fetch`), weight
    # quality by annual unlinked passenger trips and publish the national
    # numbers. National framing only: trips on expired feeds, never a ranking.
    from .ridership import duplicate_ntd_reporter_ids, load_ridership, weighted_impact

    ridership_impact: dict[str, Any] | None = None
    # This endpoint is optional. Remove an earlier render before inspecting the
    # current inputs so a missing NTD snapshot or empty guarded cohort can never
    # leave old, unguarded national numbers publicly reachable.
    ridership_api_path = web / "api" / "v1" / "ridership-impact.json"
    ridership_api_path.unlink(missing_ok=True)
    ridership_csv = root / "data" / "ntd-ridership.csv"
    rid = load_ridership(ridership_csv)
    if rid is not None and comparable_ids:
        rid_records = []
        for a in ntd_artifacts:
            agency_id = str(a.get("agency", {}).get("id", ""))
            if agency_id not in comparable_ids:
                continue
            cfg = AGENCIES.get(agency_id)
            if cfg is None or cfg.country != "US":
                continue
            days = (a.get("categories", {}).get("freshness", {}).get("details", {})).get(
                "days_until_expiry"
            )
            rid_records.append(
                {
                    "id": agency_id,
                    "ntd_id": cfg.ntd_id,
                    "score": a.get("overall", {}).get("score"),
                    "grade": a.get("overall", {}).get("grade"),
                    "expiry_status": expiry_status(days),
                }
            )
        candidate_impact = weighted_impact(
            rid_records,
            rid,
            quarantined_ntd_ids=duplicate_ntd_reporter_ids(AGENCIES.values()),
        )
        if candidate_impact.get("matched_ntd_reporters", 0) > 0:
            ridership_impact = candidate_impact
            write(
                "api/v1/ridership-impact.json",
                json.dumps(
                    {
                        "license": DATA_LICENSE,
                        "attribution": DATA_ATTRIBUTION,
                        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                        "source": "FTA NTD annual metrics (data.transportation.gov, g27i-aq2u)",
                        "comparison_eligible_count": len(comparable_ids),
                        "comparison": _comparison_metadata,
                        **ridership_impact,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )

    # The coverage overview: worldwide comparisons stay score/delta-only. U.S.
    # NTD ridership is shown in the explicitly labelled context sentence above,
    # never used to move U.S. feeds ahead of equally scored feeds elsewhere.
    # retired URLs redirect to their anchors so old links keep working.
    board = leaderboard(
        index,
        dataset,
        agencies=registry_by_id.values(),
    )
    write(
        "pulse/index.html",
        _render_pulse_page(
            board, changes, trend_points, trend_sum, improvers, ridership_impact, histories
        ),
        f"{BASE_URL}/pulse/",
    )
    write("leaderboard/index.html", _redirect_page("/pulse/#changes", "Feed changes"))

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
        to_parquet(dataset["rows"], str(web / "api" / "v1" / "agencies.parquet"))
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

    write("sitemap.xml", _sitemap(urls, sitemap_lastmods))
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
