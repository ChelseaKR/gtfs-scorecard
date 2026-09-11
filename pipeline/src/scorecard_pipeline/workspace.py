"""Workspace mode: a private, append-only history for feeds nobody publishes (#362).

History, trend and alerts exist for registry feeds because the daily run keeps
their record in ``index.json``. ``scorecard try --history DIR`` gives any other
feed the same memory without publishing it: each run appends one line to
``DIR/<feed>/history.jsonl``, and ``scorecard trend --history DIR`` reads the
ledger back as a trend table plus the alerts ``scorecard alerts`` would raise
for a registered feed with the same history.

What a record may hold is the load-bearing rule: counts and codes only. It
carries the trend point ``publish._history_entry`` builds for ``index.json``,
so the alert rules read exactly the fields they read for a registered feed,
plus the finding codes with their counts and the few freshness facts the
expiry alert reads. It never carries finding text, feed contact fields or a
local path. A local feed is named by its file name, since the SHA-256 already
identifies the bytes.

Two rules keep the ledger auditable.

* **A record measured differently is shown and never compared.** When the
  rubric, scoring profile, profile rubric, validator, reader archive profile
  or measured-category set differs from the previous record, its trend row is
  a labelled boundary. The alert rules read only the run of records measured
  the same way as the newest one, exactly as ``scorecard alerts`` does.
* **A line that cannot be read is skipped and named.** A corrupt line, or a
  record from a schema version this build does not read, is reported with its
  ledger and line number in every output format. A ledger that drops lines
  quietly cannot be audited.

Nothing here is published, and nothing reaches the registry or S3.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .alerts import DEFAULT_EXPIRY_DAYS, AlertItem, alert_urgency, feed_alert_items
from .comparisons import producer_contract, same_producer_contract
from .publish import _history_entry

HISTORY_SCHEMA_VERSION = "1.0"
RECORD_TYPE = "gtfs-scorecard-workspace-history"
HISTORY_FILENAME = "history.jsonl"

# The freshness details the expiry alert reads: `alerts._expiry_item` reads the
# countdown, and `service_periods.read_service_period` reads the service type
# and the seasonal flag to choose between "lapse" and "planned boundary"
# wording. Nothing else from the freshness card is kept.
FRESHNESS_DETAIL_KEYS = ("days_until_expiry", "service_type", "seasonal_boundary")

# The producer contract, in `comparisons.producer_contract` order, as a reader
# would name each part.
_CONTRACT_LABELS = (
    "rubric",
    "scoring profile",
    "scoring profile rubric",
    "validator",
    "reader archive profile",
    "measured categories",
)

# Fields a record must carry, with the types it must carry them as, before any
# reader will use it.
_REQUIRED_FIELDS: dict[str, tuple[type, ...]] = {
    "date": (str,),
    "score": (int, float),
    "grade": (str,),
    "name": (str,),
    "source": (str,),
}

FIRST = "first"
UNCHANGED = "unchanged"
SAME_BYTES = "same_bytes"
CHANGED = "changed"
BOUNDARY = "boundary"

_KIND_LABELS = {
    "expiry": "Expiry",
    "lapse_risk": "Lapse risk",
    "regression": "Regression",
    "export_change": "Export change",
    "anomaly": "Anomaly",
}


class WorkspaceError(ValueError):
    """The history cannot take this run, or there is no history to read."""


def describe_source(feed: str) -> str:
    """How a record names its feed: the URL as given, or a local file's name."""
    if urllib.parse.urlparse(feed).scheme in {"http", "https"}:
        return feed
    return f"local file {Path(feed).name}"


def slug_for(name: str) -> str:
    """The ledger folder for a feed: its display name, lower-cased and hyphenated.

    Letters outside ASCII are kept, so a feed named in Japanese gets its own
    folder instead of collapsing into a shared fallback name.
    """
    slug = re.sub(r"[\W_]+", "-", name.casefold()).strip("-")[:80].strip("-")
    return slug or "feed"


def _finding_counts(artifact: dict[str, Any]) -> dict[str, int]:
    """Finding codes and their counts across the measured categories."""
    counts: dict[str, int] = {}
    categories = artifact.get("categories")
    if not isinstance(categories, dict):
        return counts
    for category in categories.values():
        if not isinstance(category, dict) or category.get("status") != "measured":
            continue
        for finding in category.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            code = finding.get("code")
            count = finding.get("count")
            if (
                isinstance(code, str)
                and code
                and isinstance(count, int)
                and not isinstance(count, bool)
            ):
                counts[code] = counts.get(code, 0) + count
    return dict(sorted(counts.items()))


def _freshness_facts(artifact: dict[str, Any]) -> dict[str, Any]:
    """The freshness facts the expiry alert reads, and nothing else."""
    categories = artifact.get("categories")
    freshness = categories.get("freshness") if isinstance(categories, dict) else None
    if not isinstance(freshness, dict):
        return {"finding_codes": []}
    details = freshness.get("details")
    facts: dict[str, Any] = {
        key: details[key]
        for key in FRESHNESS_DETAIL_KEYS
        if isinstance(details, dict) and key in details
    }
    findings = freshness.get("findings")
    facts["finding_codes"] = (
        sorted(
            {
                str(finding["code"])
                for finding in findings
                if isinstance(finding, dict) and finding.get("code")
            }
        )
        if isinstance(findings, list)
        else []
    )
    return facts


def build_record(artifact: dict[str, Any], *, source: str) -> dict[str, Any]:
    """One ledger line for one scored run: counts and codes only."""
    agency = artifact.get("agency")
    name = str(agency.get("name") or "") if isinstance(agency, dict) else ""
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "record_type": RECORD_TYPE,
        "name": name,
        "source": source,
        **_history_entry(artifact),
        "findings": _finding_counts(artifact),
        "freshness": _freshness_facts(artifact),
    }


@dataclass(frozen=True)
class SkippedLine:
    """A ledger line that was not read, where it is, and why."""

    ledger: str
    line: int
    reason: str

    def message(self) -> str:
        return f"{self.ledger} line {self.line}: {self.reason}; skipped"


@dataclass
class Ledger:
    """One feed's readable records, oldest first, and the lines it could not read."""

    slug: str
    records: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[SkippedLine] = field(default_factory=list)


def _record_problem(data: Any) -> str | None:
    """Why a parsed line cannot be used as a record, or ``None`` when it can."""
    if not isinstance(data, dict):
        return "not a JSON object"
    if data.get("record_type") != RECORD_TYPE:
        return "not a workspace history record"
    version = data.get("schema_version")
    major = HISTORY_SCHEMA_VERSION.split(".", 1)[0]
    if not isinstance(version, str) or version.split(".", 1)[0] != major:
        return f"schema version {version!r} is not one this build reads ({major}.x)"
    for key, types in _REQUIRED_FIELDS.items():
        value = data.get(key)
        if not isinstance(value, types) or isinstance(value, bool):
            return f"field {key!r} is missing or malformed"
    try:
        dt.date.fromisoformat(data["date"])
    except ValueError:
        return "field 'date' is not a date"
    return None


def read_ledger(path: Path, *, slug: str) -> Ledger:
    """Read one feed's ``history.jsonl``, naming every line it has to skip.

    A missing file is an empty ledger, not an error: it is how every history
    starts. Each line is decoded on its own, so one bad byte costs one line.
    """
    ledger = Ledger(slug=slug)
    if not path.is_file():
        return ledger
    label = f"{slug}/{HISTORY_FILENAME}"
    readable: list[tuple[str, int, dict[str, Any]]] = []
    for lineno, raw in enumerate(path.read_bytes().splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            data = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            ledger.skipped.append(SkippedLine(label, lineno, "not valid UTF-8"))
            continue
        except json.JSONDecodeError as exc:
            ledger.skipped.append(SkippedLine(label, lineno, f"not valid JSON ({exc.msg})"))
            continue
        problem = _record_problem(data)
        if problem:
            ledger.skipped.append(SkippedLine(label, lineno, problem))
            continue
        readable.append((data["date"], lineno, data))
    ledger.records = [data for _date, _line, data in sorted(readable, key=lambda t: t[:2])]
    return ledger


@dataclass(frozen=True)
class Step:
    """How one record relates to the record before it."""

    kind: str
    sentence: str


def _score(value: Any) -> str:
    return f"{float(value):.1f}"


def contract_differences(previous: dict[str, Any], record: dict[str, Any]) -> list[str]:
    """Each part of the producer contract that differs, as a reader would name it."""
    changes: list[str] = []
    for label, before, after in zip(
        _CONTRACT_LABELS, producer_contract(previous), producer_contract(record), strict=True
    ):
        if before == after:
            continue
        if isinstance(before, tuple) and isinstance(after, tuple):
            old, new = ", ".join(before) or "none", ", ".join(after) or "none"
        else:
            old, new = str(before) or "not recorded", str(after) or "not recorded"
        changes.append(f"{label} {old} to {new}")
    return changes


def compare_step(previous: dict[str, Any] | None, record: dict[str, Any]) -> Step:
    """Compare a record with the one before it, or say why the two cannot be."""
    if previous is None:
        return Step(FIRST, "First record in this history.")
    if not same_producer_contract(previous, record):
        changes = contract_differences(previous, record)
        why = (
            "; ".join(changes) if changes else "the records do not say fully how they were measured"
        )
        return Step(
            BOUNDARY,
            f"Measured differently from the previous record ({why}), so the two are not compared.",
        )
    before, after = float(previous["score"]), float(record["score"])
    sha = record.get("feed_sha256")
    same_bytes = bool(sha) and sha == previous.get("feed_sha256")
    if same_bytes and before == after and previous["grade"] == record["grade"]:
        return Step(UNCHANGED, "Unchanged: the same feed bytes, scored the same.")
    movement = f"score {_score(before)} to {_score(after)}"
    if previous["grade"] != record["grade"]:
        movement += f", grade {previous['grade']} to {record['grade']}"
    if same_bytes:
        return Step(SAME_BYTES, f"Same feed bytes, {movement}.")
    return Step(CHANGED, f"New export, {movement}.")


def append_run(history_dir: Path, artifact: dict[str, Any], *, source: str) -> tuple[Path, Step]:
    """Append one scored run to its feed's ledger, refusing to mix two feeds.

    The folder is the feed's display name, so two feeds sharing a name would
    share a ledger and be compared with each other. A ledger whose readable
    records name a different source is refused rather than joined. A record
    the reader would have to skip is never written.
    """
    record = build_record(artifact, source=source)
    problem = _record_problem(record)
    if problem:
        raise WorkspaceError(f"this run's record would not be readable ({problem})")
    slug = slug_for(record["name"])
    path = history_dir / slug / HISTORY_FILENAME
    ledger = read_ledger(path, slug=slug)
    others = sorted({str(existing["source"]) for existing in ledger.records} - {source})
    if others:
        raise WorkspaceError(
            f"{slug}/{HISTORY_FILENAME} already records a different feed ({others[0]}); "
            "pass a distinct --name so each feed keeps its own history"
        )
    earlier = [existing for existing in ledger.records if existing["date"] <= record["date"]]
    step = compare_step(earlier[-1] if earlier else None, record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return path, step


def _latest_view(record: dict[str, Any], slug: str) -> dict[str, Any]:
    """The part of a latest artifact the alert rules read, rebuilt from a record.

    ``_expiry_item`` reads the countdown and the feed's name, and
    ``read_service_period`` reads the service type, the seasonal flag and the
    freshness finding codes. A private feed has no ``export_diff`` (``scorecard
    try`` computes none) and no public page, so neither is invented here.
    """
    facts = record.get("freshness")
    facts = facts if isinstance(facts, dict) else {}
    codes = facts.get("finding_codes")
    return {
        "agency": {"id": slug, "name": record.get("name") or slug},
        "categories": {
            "freshness": {
                "details": {key: facts[key] for key in FRESHNESS_DETAIL_KEYS if key in facts},
                "findings": [{"code": code} for code in (codes if isinstance(codes, list) else [])],
            }
        },
        "top_fixes": [],
    }


@dataclass(frozen=True)
class TrendRow:
    record: dict[str, Any]
    step: Step


@dataclass
class FeedTrend:
    slug: str
    name: str
    source: str
    rows: list[TrendRow]
    alerts: list[AlertItem]
    skipped: list[SkippedLine]


@dataclass
class Trend:
    feeds: list[FeedTrend]
    expiry_days: int

    @property
    def skipped(self) -> list[SkippedLine]:
        return [line for feed in self.feeds for line in feed.skipped]


def ledgers_in(history_dir: Path) -> list[str]:
    """The feed folders under ``history_dir`` that hold a ledger."""
    return sorted(
        path.parent.name for path in history_dir.glob(f"*/{HISTORY_FILENAME}") if path.is_file()
    )


def build_trend(
    history_dir: Path,
    *,
    feeds: list[str] | None = None,
    expiry_days: int = DEFAULT_EXPIRY_DAYS,
) -> Trend:
    """Read every ledger (or the named ones) into trend rows and alerts."""
    available = ledgers_in(history_dir)
    if feeds:
        missing = sorted(set(feeds) - set(available))
        if missing:
            raise WorkspaceError(f"no history for {', '.join(missing)} under {history_dir}")
        selected = sorted(set(feeds))
    else:
        selected = available
    if not selected:
        raise WorkspaceError(
            f"no {HISTORY_FILENAME} under {history_dir}; "
            f"`scorecard try --history {history_dir}` writes one"
        )
    trends: list[FeedTrend] = []
    for slug in selected:
        ledger = read_ledger(history_dir / slug / HISTORY_FILENAME, slug=slug)
        rows: list[TrendRow] = []
        previous: dict[str, Any] | None = None
        for record in ledger.records:
            rows.append(TrendRow(record, compare_step(previous, record)))
            previous = record
        alerts: list[AlertItem] = []
        name, source = slug, ""
        if previous is not None:
            name, source = str(previous["name"]), str(previous["source"])
            alerts = sorted(
                feed_alert_items(
                    ledger.records,
                    _latest_view(previous, slug),
                    agency_id=slug,
                    name=name,
                    expiry_days=expiry_days,
                ),
                key=alert_urgency,
            )
        trends.append(FeedTrend(slug, name, source, rows, alerts, ledger.skipped))
    return Trend(trends, expiry_days)


# --- rendering ---------------------------------------------------------------

_COLUMNS = (
    "Date",
    "Grade",
    "Score",
    "Days to expiry",
    "Feed SHA-256",
    "Compared with the previous record",
)


def _cells(row: TrendRow) -> list[str]:
    record = row.record
    days = record.get("days_until_expiry")
    sha = record.get("feed_sha256")
    return [
        str(record["date"]),
        str(record["grade"]),
        _score(record["score"]),
        "not known" if days is None else str(days),
        str(sha)[:12] if sha else "not recorded",
        row.step.sentence,
    ]


def _alert_sentence(item: AlertItem) -> str:
    return (
        f"{_KIND_LABELS.get(item.kind, item.kind)}: {item.headline}. {item.detail} Fix: {item.fix}"
    )


def _intro(trend: Trend) -> str:
    return (
        f"{len(trend.feeds)} feed history(ies). Alerts use the rules `scorecard alerts` "
        f"applies to registered feeds, warning within {trend.expiry_days} days. "
        "Nothing here is published."
    )


def render_text(trend: Trend) -> str:
    """Plain text for a terminal or a log."""
    lines = ["Workspace history trend", "", _intro(trend), ""]
    for feed in trend.feeds:
        lines.extend([f"== {feed.name} ({feed.slug}) ==", f"Source: {feed.source or 'unknown'}"])
        lines.append(" | ".join(_COLUMNS))
        lines.extend(" | ".join(_cells(row)) for row in feed.rows)
        if not feed.rows:
            lines.append("No readable records.")
        lines.append("Alerts:")
        lines.extend(f"  - {_alert_sentence(item)}" for item in feed.alerts)
        if not feed.alerts:
            lines.append("  None.")
        if feed.skipped:
            lines.append("Lines not read:")
            lines.extend(f"  - {line.message()}" for line in feed.skipped)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _md(text: str) -> str:
    return text.replace("|", "\\|")


def render_markdown(trend: Trend) -> str:
    """Markdown with one table per feed, for an issue or a pull request."""
    lines = ["# Workspace history trend", "", _intro(trend), ""]
    for feed in trend.feeds:
        lines.extend(
            [f"## {_md(feed.name)} (`{feed.slug}`)", "", f"Source: {_md(feed.source or 'unknown')}"]
        )
        lines.append("")
        if feed.rows:
            lines.append("| " + " | ".join(_COLUMNS) + " |")
            lines.append("| --- | --- | ---: | ---: | --- | --- |")
            lines.extend("| " + " | ".join(_md(c) for c in _cells(row)) + " |" for row in feed.rows)
        else:
            lines.append("No readable records.")
        lines.extend(["", "### Alerts", ""])
        lines.extend(f"- {_md(_alert_sentence(item))}" for item in feed.alerts)
        if not feed.alerts:
            lines.append("None.")
        if feed.skipped:
            lines.extend(["", "### Lines not read", ""])
            lines.extend(f"- {_md(line.message())}" for line in feed.skipped)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_STYLE = (
    "body{font-family:system-ui,sans-serif;color:#1a1a1a;background:#fff;"
    "max-width:72rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
    "table{border-collapse:collapse;width:100%}"
    "th,td{border:1px solid #555;padding:.35rem .5rem;text-align:left;vertical-align:top}"
    "caption{text-align:left;font-weight:600;margin-bottom:.25rem}"
)


def render_html(trend: Trend) -> str:
    """One self-contained HTML file: inline style, no scripts, nothing fetched."""
    esc = html.escape
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Workspace history trend</title><style>{_STYLE}</style></head>",
        "<body><main><h1>Workspace history trend</h1>",
        f"<p>{esc(_intro(trend))}</p>",
    ]
    for index, feed in enumerate(trend.feeds, start=1):
        heading = f"feed-{index}"
        parts.append(f'<section aria-labelledby="{heading}">')
        parts.append(f'<h2 id="{heading}">{esc(feed.name)} ({esc(feed.slug)})</h2>')
        parts.append(f"<p>Source: {esc(feed.source or 'unknown')}</p>")
        if feed.rows:
            parts.append(
                f"<table><caption>Runs recorded for {esc(feed.name)}, oldest first</caption>"
            )
            parts.append(
                "<thead><tr>"
                + "".join(f'<th scope="col">{esc(c)}</th>' for c in _COLUMNS)
                + "</tr></thead><tbody>"
            )
            for row in feed.rows:
                parts.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in _cells(row)) + "</tr>")
            parts.append("</tbody></table>")
        else:
            parts.append("<p>No readable records.</p>")
        parts.append("<h3>Alerts</h3>")
        if feed.alerts:
            parts.append(
                "<ul>"
                + "".join(f"<li>{esc(_alert_sentence(i))}</li>" for i in feed.alerts)
                + "</ul>"
            )
        else:
            parts.append("<p>None.</p>")
        if feed.skipped:
            parts.append("<h3>Lines not read</h3><ul>")
            parts.extend(f"<li>{esc(line.message())}</li>" for line in feed.skipped)
            parts.append("</ul>")
        parts.append("</section>")
    parts.append("</main></body></html>")
    return "\n".join(parts) + "\n"


RENDERERS: dict[str, Callable[[Trend], str]] = {
    "text": render_text,
    "markdown": render_markdown,
    "html": render_html,
}
