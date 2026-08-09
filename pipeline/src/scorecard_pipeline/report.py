"""Board-ready report: one agency's scorecard as a single portable HTML file.

The site already has a board one-pager at /agency/<id>/board/ (docs/
RESEARCH-ROADMAP.md E6), but that page lives on the site and dresses in the
site's chrome. A board packet or a federal grant application wants a file:
something a transit manager can attach to an email, print to PDF from any
browser, and hand across the table with no network in the room. This module
renders that file from the same published artifact fields the site renders,
so the two can never tell different stories. Nothing here computes a new
metric; it re-frames what score.py, ntd.py, and the history index already say.

A state program or a consultancy preparing packets for the agencies it
supports can put its own name, logo, and accent color on the cover via a
small brand YAML file (see load_brand). The accent is decorative only. It
colors a band and rules, never text, so any accent keeps the document
readable and the contrast gate honest.

Run it either way:

    scorecard report --agency unitrans --out unitrans-report.html
    python -m scorecard_pipeline.report --agency unitrans --brand brand.yaml
"""

# ruff: noqa: E501  (long inline-HTML lines, matching render_site)
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .comparisons import same_producer_contract
from .config import artifacts_dir
from .site_shell import BASE_URL, CATEGORY_LABELS, CATEGORY_ORDER, esc

# The rubric documents the report cites in its methodology footer.
_RUBRIC_DOC_URL = "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/rubric.md"
_HOW_TO_READ_URL = f"{BASE_URL}/how-to-read/"

# Print-safe document palette, drawn from the site's light theme so the file
# reads as kin to gtfsscorecard.org. Every text/background pair here is
# asserted AAA by pipeline/scripts/check_contrast.py (the "board report
# document" block); add a pair there before using a new combination.
_INK = "#20241f"
_INK_SOFT = "#3d4339"
_LINE = "#c6ccbe"
_HEAD_BG = "#e5e8df"
_PAPER = "#ffffff"

DEFAULT_ACCENT = "#163a2c"

_LOGO_MEDIA_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class ReportError(ValueError):
    """A report input problem the message explains in plain language."""


@dataclass(frozen=True)
class Brand:
    """The organization putting its name on the report cover.

    ``logo_data_uri`` is the logo embedded as a data: URI so the document
    stays a single self-contained file. ``accent`` is a #rrggbb hex used only
    for decorative bands and rules, never for text.
    """

    name: str
    logo_data_uri: str | None = None
    accent: str = DEFAULT_ACCENT


def _validate_accent(value: str) -> str:
    v = value.strip()
    if len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in v[1:]):
        return v.lower()
    raise ReportError(f"accent must be a #rrggbb hex color, got {value!r}")


def _logo_data_uri(path: Path) -> str:
    media_type = _LOGO_MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        supported = ", ".join(sorted(_LOGO_MEDIA_TYPES))
        raise ReportError(f"logo {path.name}: use one of {supported}")
    try:
        raw = path.read_bytes()
    except OSError as err:
        raise ReportError(f"logo file not readable: {path} ({err})") from err
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def load_brand(path: Path) -> Brand:
    """Read a brand YAML file: ``name`` (required), ``logo`` (optional file
    path, resolved relative to the YAML file), ``accent`` (optional #rrggbb).
    Raises ReportError with a plain-language message on any problem."""
    try:
        raw = yaml.safe_load(path.read_text())
    except OSError as err:
        raise ReportError(f"brand file not readable: {path} ({err})") from err
    except yaml.YAMLError as err:
        raise ReportError(f"brand file {path} is not valid YAML: {err}") from err
    if not isinstance(raw, dict):
        raise ReportError(f"brand file {path} must be a YAML mapping with a 'name' key")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ReportError(f"brand file {path} needs a non-empty 'name'")
    accent = _validate_accent(str(raw.get("accent") or DEFAULT_ACCENT))
    logo_uri = None
    logo = raw.get("logo")
    if logo:
        logo_uri = _logo_data_uri((path.parent / str(logo)).resolve())
    return Brand(name=name, logo_data_uri=logo_uri, accent=accent)


# ---------------------------------------------------------------------------
# Data assembly: artifact + history -> the plain dict the renderer consumes.
# ---------------------------------------------------------------------------


def _change_words(delta: float) -> str:
    if delta > 0:
        return f"up {delta}"
    if delta < 0:
        return f"down {abs(delta)}"
    return "no change"


def _history_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for i, point in enumerate(history):
        if i == 0:
            change = "first check"
        elif not same_producer_contract(history[i - 1], point):
            change = "not compared"
        else:
            change = _change_words(round(float(point["score"]) - float(history[i - 1]["score"]), 1))
        rows.append(
            {
                "date": str(point.get("date", "")),
                "score": point.get("score"),
                "grade": str(point.get("grade", "")),
                "change": change,
            }
        )
    return rows


def _category_rows(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """The four rubric categories in canonical order, with the existing
    plain-language summaries. A category the pipeline has not measured (an
    agency with no realtime feed yet) keeps its neutral summary and shows no
    number, matching the rubric's no-shaming rule."""
    rows = []
    for key in CATEGORY_ORDER:
        cat = (artifact.get("categories") or {}).get(key)
        if not isinstance(cat, dict):
            continue
        measured = cat.get("status", "measured") == "measured"
        rows.append(
            {
                "key": key,
                "label": CATEGORY_LABELS[key],
                "measured": measured,
                "score": cat.get("score") if measured else None,
                "summary": str(cat.get("summary", "")),
            }
        )
    return rows


def _ntd_data(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """The NTD readiness block for a US agency, from stored feed inputs.

    Re-derives current readiness and shapes.txt wording so older artifacts gain
    the RY2026 agency_id presence check without a rescore. A missing or adverse
    shapes check also makes the report's overall label conservative: an offline
    board packet must not make an unqualified ``Ready`` claim from incomplete
    evidence. None for non-US agencies, which have no FTA NTD.
    """
    if artifact.get("agency", {}).get("country", "US") != "US":
        return None
    from .ntd import presented_readiness

    readiness = presented_readiness(artifact)
    if not isinstance(readiness, dict):
        return None
    from .render_site import _NTD_LABELS, _NTD_PILLAR_NAMES, _current_shapes_readiness

    pillars = [
        {
            "name": _NTD_PILLAR_NAMES.get(str(p.get("key")), str(p.get("key"))),
            "label": _NTD_LABELS.get(str(p.get("status")), str(p.get("status"))),
            "detail": str(p.get("detail", "")),
        }
        for p in readiness.get("pillars", [])
    ]
    shapes = _current_shapes_readiness(artifact)
    status = str(readiness.get("status", ""))
    status_label = _NTD_LABELS.get(status, status)
    summary = str(readiness.get("summary", ""))
    if shapes:
        detail = str(shapes.get("detail", ""))
        fix = str(shapes.get("fix", ""))
        shapes_row = {
            "label": _NTD_LABELS.get(str(shapes.get("status")), str(shapes.get("status"))),
            "detail": f"{detail} {fix}".strip(),
        }
        shapes_status = str(shapes.get("status", ""))
        if shapes_status == "not_ready":
            status_label = _NTD_LABELS["not_ready"]
        elif shapes_status == "at_risk" and status == "ready":
            status_label = _NTD_LABELS["at_risk"]
        if shapes_status in {"at_risk", "not_ready"}:
            summary = (
                f"{summary} The shapes.txt coverage check also needs attention: {detail}"
            ).strip()
    else:
        shapes_row = {
            "label": "Not checked",
            "detail": (
                "This scorecard artifact predates the shapes.txt trip-coverage check. "
                "Re-score the feed before relying on this report for NTD readiness."
            ),
        }
        status_label = "Not fully assessed"
        summary = (
            "Published, valid, current, and agency_id are assessed here, but "
            "shapes.txt trip coverage was not checked in this legacy scorecard. "
            "This report therefore cannot make a complete NTD readiness call."
        )
    return {
        "status_label": status_label,
        "summary": summary,
        "pillars": pillars,
        "shapes": shapes_row,
        "note": str(artifact.get("agency", {}).get("ntd_note") or "").strip(),
    }


def build_report_data(
    artifact: dict[str, Any],
    history: list[dict[str, Any]] | None,
    *,
    generated_at: dt.datetime,
) -> dict[str, Any]:
    """Assemble everything the report renders from one published artifact and
    the agency's history series (index.json). Pure re-framing: every value
    already exists in the artifact or the history; nothing is recomputed
    except the plain-language change words."""
    from .render_site import _brief_trend_line

    hist = history or []
    overall = artifact.get("overall", {})
    return {
        "agency": {
            "id": str(artifact.get("agency", {}).get("id", "")),
            "name": str(artifact.get("agency", {}).get("name", "")),
        },
        "checked": str(artifact.get("snapshot_date", "")),
        "grade": str(overall.get("grade", "")),
        "score": overall.get("score"),
        "trend_line": _brief_trend_line(hist),
        "categories": _category_rows(artifact),
        "fixes": list(artifact.get("top_fixes", []))[:3],
        "ntd": _ntd_data(artifact),
        "history": _history_rows(hist),
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        "rubric_version": str(artifact.get("rubric_version", "")),
        "validator_version": str(artifact.get("validator_version", "")),
        "scorecard_url": f"{BASE_URL}/agency/{artifact.get('agency', {}).get('id', '')}/",
    }


# ---------------------------------------------------------------------------
# Rendering: the plain dict -> one self-contained HTML document.
# ---------------------------------------------------------------------------


def _css(accent: str) -> str:
    return f"""    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 0 1.25rem 3rem; background: {_PAPER}; color: {_INK};
      font: 16px/1.55 "Public Sans", "Helvetica Neue", Arial, sans-serif;
    }}
    .accent-band {{ height: 0.5rem; background: {accent}; margin: 0 -1.25rem; }}
    .report {{ max-width: 46rem; margin: 0 auto; }}
    .prepared-by {{
      display: flex; align-items: center; gap: 0.75rem;
      border-bottom: 1px solid {_LINE}; padding: 0.75rem 0; margin-bottom: 1.5rem;
    }}
    .prepared-by img {{ max-height: 3rem; max-width: 12rem; }}
    .prepared-by p {{ margin: 0; color: {_INK_SOFT}; font-size: 0.9375rem; }}
    .kicker {{
      margin: 1.5rem 0 0.25rem; color: {_INK_SOFT};
      font-size: 0.9375rem; letter-spacing: 0.02em; text-transform: uppercase;
    }}
    h1 {{ margin: 0 0 0.5rem; font-size: 1.75rem; line-height: 1.25; }}
    h2 {{
      margin: 2rem 0 0.75rem; font-size: 1.25rem;
      border-bottom: 3px solid {accent}; padding-bottom: 0.25rem;
    }}
    .grade-line {{ font-size: 1.375rem; margin: 0 0 0.25rem; }}
    .trend-line {{ margin: 0; color: {_INK_SOFT}; }}
    table {{ border-collapse: collapse; width: 100%; margin: 0.75rem 0; }}
    caption {{ text-align: left; color: {_INK_SOFT}; font-size: 0.9375rem; padding-bottom: 0.5rem; }}
    th, td {{ border: 1px solid {_LINE}; padding: 0.5rem 0.625rem; text-align: left; vertical-align: top; }}
    thead th {{ background: {_HEAD_BG}; }}
    tbody th {{ font-weight: 600; }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    ol.fixes {{ padding-left: 1.25rem; }}
    ol.fixes li {{ margin: 0 0 1rem; }}
    ol.fixes p {{ margin: 0.25rem 0; }}
    .fix-do {{ font-weight: 600; }}
    .fix-effort, .muted {{ color: {_INK_SOFT}; }}
    dl.pillars {{ margin: 0.75rem 0; }}
    dl.pillars dt {{ font-weight: 600; margin-top: 0.625rem; }}
    dl.pillars dd {{ margin: 0.125rem 0 0; }}
    .status-chip {{
      display: inline-block; border: 1px solid {_INK_SOFT}; border-radius: 0.25rem;
      padding: 0 0.375rem; margin-left: 0.25rem; font-size: 0.875rem; font-weight: 600;
    }}
    .report-foot {{
      margin-top: 2.5rem; border-top: 1px solid {_LINE}; padding-top: 0.75rem;
      color: {_INK_SOFT}; font-size: 0.875rem;
    }}
    a {{ color: {_INK}; }}
    @media print {{
      body {{ padding: 0; font-size: 12px; }}
      .accent-band {{ margin: 0; }}
      section {{ break-inside: avoid; }}
      h2 {{ break-after: avoid-page; }}
      .new-page {{ break-before: page; }}
      .report-foot a[href^="http"]::after {{ content: " (" attr(href) ")"; }}
    }}"""


def _prepared_by_html(brand: Brand | None) -> str:
    if brand is None:
        return ""
    logo = (
        f'<img src="{esc(brand.logo_data_uri)}" alt="{esc(brand.name)} logo">'
        if brand.logo_data_uri
        else ""
    )
    return f'<div class="prepared-by">{logo}<p>Prepared by {esc(brand.name)}</p></div>\n    '


def _categories_html(rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        score = esc(str(row["score"])) if row["measured"] else "Not yet published"
        body.append(
            f'<tr><th scope="row">{esc(row["label"])}</th>'
            f'<td class="num">{score}</td><td>{esc(row["summary"])}</td></tr>'
        )
    return (
        "<table><caption>The four rubric categories, each scored 0 to 100. A category the "
        "pipeline has not measured yet shows no number and never counts against the grade.</caption>"
        '<thead><tr><th scope="col">Category</th><th scope="col" class="num">Score</th>'
        '<th scope="col">Where this feed stands</th></tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _fixes_html(fixes: list[dict[str, Any]]) -> str:
    if not fixes:
        return (
            "<p>None at this time. The feed passes every check the scorecard "
            "translates into a fix; the ask is continued upkeep.</p>"
        )
    items = "".join(
        f'<li><p class="fix-do">{esc(f.get("fix", ""))}</p>'
        f"<p>{esc(f.get('what', ''))} {esc(f.get('why', ''))}</p>"
        f'<p class="fix-effort">Estimated effort: {esc(f.get("effort", ""))}</p></li>'
        for f in fixes
    )
    return (
        "<p>Three improvements, in priority order, each sized so a board can "
        "see what it is approving:</p>"
        f'<ol class="fixes">{items}</ol>'
    )


def _ntd_html(ntd: dict[str, Any] | None) -> str:
    if ntd is None:
        return ""
    pillars = "".join(
        f'<dt>{esc(p["name"])} <span class="status-chip">{esc(p["label"])}</span></dt>'
        f"<dd>{esc(p['detail'])}</dd>"
        for p in ntd["pillars"]
    )
    shapes = ntd.get("shapes")
    if shapes:
        pillars += (
            f'<dt>shapes.txt covers your trips <span class="status-chip">{esc(shapes["label"])}</span></dt>'
            f"<dd>{esc(shapes['detail'])}</dd>"
        )
    note = f'<p class="muted">{esc(ntd["note"])}</p>' if ntd["note"] else ""
    return f"""<section class="new-page" aria-labelledby="ntd-h">
      <h2 id="ntd-h"><abbr title="National Transit Database">NTD</abbr> GTFS readiness <span class="status-chip">{esc(ntd["status_label"])}</span></h2>
      {note}<p>{esc(ntd["summary"])}</p>
      <dl class="pillars">{pillars}</dl>
      <p><strong>In plain words:</strong> agencies that report to the federal National
      Transit Database certify once a year, on form D-10, that they publish a working,
      up-to-date feed. For RY2026, each represented reporter also needs a stable agency_id
      crosswalked to its NTD ID on P-50; the two values need not be equal. This section is
      a heads-up on whether the feed looks ready; the filings are the official check. FTA also
      requires shapes.txt in the published GTFS: Full Reporters from Report Year 2025,
      and Reduced, Rural, and Tribal Reporters from Report Year 2026.</p>
    </section>
    """


def _history_html(rows: list[dict[str, Any]], trend_line: str) -> str:
    if len(rows) < 2:
        return ""
    shown = rows if len(rows) <= 13 else rows[-12:]
    note = (
        f'<p class="muted">Showing the {len(shown)} most recent of {len(rows)} checks.</p>'
        if len(shown) < len(rows)
        else ""
    )
    body = "".join(
        f'<tr><th scope="row">{esc(r["date"])}</th><td class="num">{esc(str(r["score"]))}</td>'
        f"<td>{esc(r['grade'])}</td><td>{esc(r['change'])}</td></tr>"
        for r in shown
    )
    return f"""<section class="new-page" aria-labelledby="trend-h">
      <h2 id="trend-h">Over time</h2>
      <p>{esc(trend_line)} The table lists each daily check.</p>
      {note}<table><caption>Overall score by check, with the change from the previous check stated in words.</caption>
      <thead><tr><th scope="col">Check</th><th scope="col" class="num">Score</th><th scope="col">Grade</th><th scope="col">Change</th></tr></thead>
      <tbody>{body}</tbody></table>
    </section>
    """


def render_report(data: dict[str, Any], brand: Brand | None = None) -> str:
    """One self-contained HTML document from build_report_data output. No
    external stylesheet, font, script, or image: everything a browser needs to
    show or print it travels inside the file."""
    accent = brand.accent if brand else DEFAULT_ACCENT
    name = data["agency"]["name"]
    grade = data["grade"]
    score = data["score"]
    produced = (
        f"Prepared by {esc(brand.name)} with the GTFS Scorecard, an open-source data quality tool for small and rural transit agencies."
        if brand
        else "Produced by the GTFS Scorecard, an open-source data quality tool for small and rural transit agencies."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(name)}: transit data quality report</title>
  <style>
{_css(accent)}
  </style>
</head>
<body>
  <div class="accent-band" role="presentation"></div>
  <div class="report">
    {_prepared_by_html(brand)}<header>
      <p class="kicker">Transit data quality report &middot; checked {esc(data["checked"])}</p>
      <h1>{esc(name)}</h1>
      <p class="grade-line">Grade {esc(grade)} &middot; {esc(str(score))} out of 100</p>
      <p class="trend-line">{esc(data["trend_line"])}</p>
    </header>
    <section aria-labelledby="what-h">
      <h2 id="what-h">What this grade measures</h2>
      <p>The quality of the schedule data in the feed scored here for trip-planning
      apps: whether riders using Google Maps, Apple Maps, or Transit see current,
      correct, and complete information. It measures the data feed, not service
      quality or operations.</p>
    </section>
    <section aria-labelledby="categories-h">
      <h2 id="categories-h">Category scores</h2>
      {_categories_html(data["categories"])}
    </section>
    <section aria-labelledby="fixes-h">
      <h2 id="fixes-h">Top three things to fix</h2>
      {_fixes_html(data["fixes"])}
    </section>
    {_ntd_html(data["ntd"])}{_history_html(data["history"], data["trend_line"])}<footer class="report-foot">
      <p>{produced} Scores follow the public rubric
      (<a href="{esc(_HOW_TO_READ_URL)}">how to read a scorecard</a>; full methodology in
      <a href="{esc(_RUBRIC_DOC_URL)}">docs/rubric.md</a>), rubric v{esc(data["rubric_version"])},
      validator {esc(data["validator_version"])}. Report generated {esc(data["generated_at"])}
      from the {esc(data["checked"])} check. Live scorecard: <a href="{esc(data["scorecard_url"])}">{esc(data["scorecard_url"])}</a>.
      A data-quality read to support the conversation, not an official compliance determination.</p>
    </footer>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Loading and the command-line entry point.
# ---------------------------------------------------------------------------


def _load_inputs(agency_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The agency's latest published artifact and its history series, read the
    same way render_site reads them (latest.json plus index.json)."""
    art = artifacts_dir()
    latest = art / agency_id / "latest.json"
    if not latest.exists():
        raise ReportError(
            f"no published scorecard for {agency_id!r} (expected {latest}); "
            "run `scorecard run --agency <id>` first or check the agency id"
        )
    artifact: dict[str, Any] = json.loads(latest.read_text())
    history: list[dict[str, Any]] = []
    index_file = art / "index.json"
    if index_file.exists():
        index = json.loads(index_file.read_text())
        entry = (index.get("agencies") or {}).get(agency_id) or {}
        history = list(entry.get("history") or [])
    return artifact, history


def generate_report(
    agency_id: str,
    *,
    brand: Brand | None = None,
    out: Path | None = None,
    now: dt.datetime | None = None,
) -> Path:
    """Render the board-ready report for one agency and write it to ``out``
    (default: <agency>-board-report.html in the current directory). Returns
    the written path."""
    artifact, history = _load_inputs(agency_id)
    generated_at = now or dt.datetime.now(dt.UTC)
    data = build_report_data(artifact, history, generated_at=generated_at)
    html_text = render_report(data, brand)
    path = out or Path(f"{agency_id}-board-report.html")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scorecard_pipeline.report",
        description=(
            "Render an agency's published scorecard as one self-contained HTML report, "
            "written for a board packet or a grant application and clean to print to PDF."
        ),
    )
    parser.add_argument("--agency", required=True, help="agency id, e.g. unitrans")
    parser.add_argument(
        "--brand",
        type=Path,
        default=None,
        help="brand YAML (name, optional logo path, optional #rrggbb accent) for the cover",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output path (default: <agency>-board-report.html in the current directory)",
    )
    args = parser.parse_args(argv)
    try:
        brand = load_brand(args.brand) if args.brand else None
        path = generate_report(args.agency, brand=brand, out=args.out)
    except ReportError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
