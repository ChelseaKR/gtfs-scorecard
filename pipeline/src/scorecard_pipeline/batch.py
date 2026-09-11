"""Score a list of untracked feeds and build a private cohort rollup (#363).

``scorecard try --batch feeds.csv --out DIR`` is ``scorecard try`` run once per
row of a CSV that a program liaison or a consultancy already holds, followed by
one rollup over the results. Nothing is published and nothing enters the
registry: every file lands under ``DIR``.

Three rules carry the honesty of the output.

* **The CSV is checked before any network call.** A missing or unknown column,
  a malformed row, or a feed listed twice refuses the whole batch, naming the
  row, before anything is fetched.
* **A feed that could not be scored is a row with a reason, never a grade.** A
  dead link, an unreadable archive or a missing local file is listed as "not
  scored" with what went wrong. It is never an F, never a score of zero, and a
  campaign worklist never counts it as already clear: only scored feeds are
  handed to the worklist builder.
* **The same inputs give the same bytes.** Rows keep CSV order whatever order
  the bounded worker pool finishes in, no output carries a wall-clock time,
  and a local feed is recorded by its file name, never by an absolute path.

The rollup reuses the published rollup's shared-fix count
(:func:`rollups.count_shared_fixes`) and the campaign worklists
(:func:`campaigns.build_program_campaign`), which omit grades and scores.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import re
import unicodedata
import urllib.parse
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

from .campaigns import CAMPAIGNS, build_program_campaign, render_program_campaign_markdown
from .metrics import expiry_status
from .net import UnsafeURLError
from .ridership import normalize_ntd_id
from .rollups import _csv_cell, count_shared_fixes
from .validate import validator_country_code

BATCH_SCHEMA_VERSION = "1.0"
REQUIRED_COLUMNS = ("name", "url", "country")
OPTIONAL_COLUMNS = ("ntd_id", "large_feed")
DEFAULT_WORKERS = 2
MAX_WORKERS = 4

# Expiry buckets from `metrics.expiry_status` that belong in the "expiring"
# section: service ends within 30 days, or has already ended.
EXPIRING = ("expiring_soon", "lapsed", "stale")

_TRUE = frozenset({"true", "yes", "1"})
_FALSE = frozenset({"", "false", "no", "0"})

NOTE = (
    "This rollup is private to the folder it was written to. It is not published, it "
    "adds nothing to the registry, and it is not a ranking: feeds are listed in the "
    "order of the CSV, and the worklists leave out grades and scores."
)

_MEMBER_CSV_COLUMNS: tuple[tuple[str, str], ...] = (
    ("feed_name", "name"),
    ("source", "source"),
    ("country", "country"),
    ("ntd_id", "ntd_id"),
    ("status", "status"),
    ("reason", "reason"),
    ("grade", "grade"),
    ("score", "score"),
    ("checked", "checked"),
    ("expiry_status", "expiry_status"),
    ("days_until_expiry", "days_until_expiry"),
    ("top_fix", "top_fix"),
    ("scorecard_json", "scorecard_json"),
    ("scorecard_html", "scorecard_html"),
)


class ScoreFeed(Protocol):
    """The ``scorecard try`` scorer, :func:`cli.run_adhoc_detailed`."""

    def __call__(
        self,
        source: str,
        name: str | None,
        date: dt.date,
        country: str = ...,
        *,
        large_feed: bool = ...,
    ) -> tuple[dict[str, Any], Any]: ...


class BatchInputError(ValueError):
    """The batch cannot run. Raised before anything is fetched."""


@dataclass(frozen=True)
class BatchRow:
    """One validated CSV row. ``source`` is what gets scored; ``display_source`` is
    what every output shows (the link, or a local file's name only)."""

    number: int
    name: str
    source: str
    display_source: str
    country: str
    ntd_id: str
    large_feed: bool
    slug: str


@dataclass(frozen=True)
class BatchResult:
    row: BatchRow
    artifact: dict[str, Any] | None
    reason: str | None


# --- reading the CSV -----------------------------------------------------------------------


def _check_header(header: list[str]) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise BatchInputError(
            f"the CSV is missing required column(s) {', '.join(missing)}; the header must "
            f"include {', '.join(REQUIRED_COLUMNS)}"
        )
    allowed = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
    unknown = [column for column in header if column not in allowed]
    if unknown:
        raise BatchInputError(
            f"unknown column(s) {', '.join(unknown)}; allowed columns are {', '.join(allowed)}"
        )
    repeated = sorted({column for column in header if header.count(column) > 1})
    if repeated:
        raise BatchInputError(f"column(s) listed more than once: {', '.join(repeated)}")


def _slug(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:60].strip("-")
    return slug or "feed"


def _unique_slug(name: str, taken: set[str]) -> str:
    base = _slug(name)
    slug = base
    suffix = 2
    while slug in taken:
        slug = f"{base}-{suffix}"
        suffix += 1
    taken.add(slug)
    return slug


def _source(where: str, url: str, base: Path) -> tuple[str, str]:
    if "://" in url:
        scheme = urllib.parse.urlparse(url).scheme.lower()
        if scheme not in {"http", "https"}:
            raise BatchInputError(
                f"{where}: only http and https links are fetched, got {scheme}://"
            )
        return url, url
    candidate = Path(url).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return str(candidate), candidate.name


def _parse_row(number: int, cells: dict[str, str], base: Path, taken: set[str]) -> BatchRow:
    name = cells["name"]
    if not name:
        raise BatchInputError(f"row {number}: name is empty")
    where = f"row {number} ({name})"
    if not cells["url"]:
        raise BatchInputError(f"{where}: url is empty")
    source, display = _source(where, cells["url"], base)
    try:
        country = validator_country_code(cells["country"])
    except ValueError as exc:
        raise BatchInputError(f"{where}: {exc}") from exc
    raw_ntd = cells.get("ntd_id", "")
    if raw_ntd and not raw_ntd.removesuffix(".0").isdigit():
        raise BatchInputError(f"{where}: ntd_id {raw_ntd!r} is not a number")
    flag = cells.get("large_feed", "").casefold()
    if flag not in _TRUE | _FALSE:
        raise BatchInputError(f"{where}: large_feed must be true or false, got {flag!r}")
    return BatchRow(
        number=number,
        name=name,
        source=source,
        display_source=display,
        country=country,
        ntd_id=normalize_ntd_id(raw_ntd),
        large_feed=flag in _TRUE,
        slug=_unique_slug(name, taken),
    )


def read_batch_csv(path: Path) -> list[BatchRow]:
    """Parse and validate every row, or raise :class:`BatchInputError`.

    Nothing here touches the network. Row numbers count the header as row 1,
    the way a spreadsheet shows them. Blank rows are skipped. A CSV with no feed
    rows is refused: a rollup over nothing would still print a clean summary.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise BatchInputError(f"could not read the CSV: {exc}") from exc
    records = list(csv.reader(io.StringIO(text, newline="")))
    if not records:
        raise BatchInputError("the CSV is empty")
    header = [cell.strip() for cell in records[0]]
    _check_header(header)
    body = [
        (number, record)
        for number, record in enumerate(records[1:], start=2)
        if any(cell.strip() for cell in record)
    ]
    if not body:
        raise BatchInputError("the CSV lists no feeds, so there is nothing to score")

    rows: list[BatchRow] = []
    seen: dict[tuple[str, str], int] = {}
    taken: set[str] = set()
    for number, record in body:
        if len(record) != len(header):
            raise BatchInputError(
                f"row {number}: expected {len(header)} cells, found {len(record)}"
            )
        cells = dict(zip(header, (cell.strip() for cell in record), strict=True))
        row = _parse_row(number, cells, path.parent, taken)
        key = (row.source, row.country)
        if key in seen:
            raise BatchInputError(
                f"row {number} ({row.name}): {row.display_source} for {row.country} is "
                f"already listed on row {seen[key]}; list each feed once"
            )
        seen[key] = number
        rows.append(row)
    return rows


def prepare_output_dir(out_dir: Path) -> None:
    """Refuse an output location that already holds anything.

    A rerun into a used folder would leave an earlier run's scorecard beside a
    rollup that now says the feed could not be scored, and deleting files in a
    folder the user chose is not this command's call.
    """
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise BatchInputError(f"--out {out_dir.name} must be a new or empty directory")


# --- scoring -------------------------------------------------------------------------------


def _local_variants(row: BatchRow) -> list[str]:
    resolved = Path(row.source).expanduser().resolve()
    variants = {resolved.as_uri(), str(resolved), row.source}
    return sorted(variants, key=len, reverse=True)


def _reason(row: BatchRow, exc: Exception) -> str:
    message = str(exc) or type(exc).__name__
    if row.source != row.display_source:
        for variant in _local_variants(row):
            message = message.replace(variant, row.display_source)
    if isinstance(exc, FileNotFoundError):
        lead = "could not find the local file"
    elif isinstance(exc, (requests.RequestException, UnsafeURLError)):
        lead = "could not fetch the feed"
    else:
        lead = "could not read or score the feed"
    return f"{lead}: {message}"


def scrub_local_paths(row: BatchRow, artifact: dict[str, Any]) -> dict[str, Any]:
    """Replace a local feed's absolute location with its file name, everywhere.

    ``scorecard try`` records a local zip as a ``file://`` URI of its resolved
    path. A rollup is meant to be forwarded, so a user name and a folder layout
    have no place in it, and the feed's SHA-256 already identifies the bytes.
    """
    if row.source == row.display_source:
        return artifact
    text = json.dumps(artifact, sort_keys=True)
    for variant in _local_variants(row):
        text = text.replace(json.dumps(variant)[1:-1], row.display_source)
    scrubbed: dict[str, Any] = json.loads(text)
    return scrubbed


def score_batch(
    rows: Sequence[BatchRow],
    *,
    date: dt.date,
    score: ScoreFeed,
    workers: int = DEFAULT_WORKERS,
) -> list[BatchResult]:
    """Score every row with at most ``workers`` feeds in flight.

    Results come back in CSV order. A row whose feed cannot be fetched, read or
    scored becomes a result with a reason and no artifact.
    """
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}, got {workers}")

    def one(row: BatchRow) -> BatchResult:
        try:
            artifact, _report = score(
                row.source, row.name, date, row.country, large_feed=row.large_feed
            )
        except Exception as exc:
            # The same breadth `scorecard try` catches. A failed row is recorded,
            # never scored: see the module docstring.
            return BatchResult(row=row, artifact=None, reason=_reason(row, exc))
        return BatchResult(row=row, artifact=scrub_local_paths(row, artifact), reason=None)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, rows))


# --- the rollup ----------------------------------------------------------------------------


def _member(result: BatchResult) -> dict[str, Any]:
    row = result.row
    member: dict[str, Any] = {
        "slug": row.slug,
        "name": row.name,
        "source": row.display_source,
        "country": row.country,
        "ntd_id": row.ntd_id or None,
        "large_feed": row.large_feed,
    }
    artifact = result.artifact
    if artifact is None:
        member.update(
            status="not_scored",
            reason=result.reason,
            grade=None,
            score=None,
            checked=None,
            days_until_expiry=None,
            expiry_status=None,
            top_fix=None,
            top_fix_code=None,
            scorecard_json=None,
            scorecard_html=None,
        )
        return member
    days = (
        artifact.get("categories", {})
        .get("freshness", {})
        .get("details", {})
        .get("days_until_expiry")
    )
    fixes = artifact.get("top_fixes") or []
    member.update(
        status="scored",
        reason=None,
        grade=artifact["overall"]["grade"],
        score=artifact["overall"]["score"],
        checked=artifact.get("snapshot_date"),
        days_until_expiry=days,
        expiry_status=expiry_status(days),
        top_fix=fixes[0].get("fix") if fixes else None,
        top_fix_code=fixes[0].get("code") if fixes else None,
        scorecard_json=f"feeds/{row.slug}.json",
        scorecard_html=f"feeds/{row.slug}.html",
    )
    return member


def _campaign_view(result: BatchResult) -> dict[str, Any]:
    artifact = result.artifact or {}
    agency = {**(artifact.get("agency") or {}), "id": result.row.slug, "name": result.row.name}
    return {**artifact, "agency": agency}


def build_cohort_rollup(
    results: Sequence[BatchResult], *, as_of: dt.date, cohort_name: str
) -> dict[str, Any]:
    """Aggregate a batch into one private rollup, in CSV order."""
    members = [_member(result) for result in results]
    scored = [result for result in results if result.artifact is not None]

    shared: list[dict[str, Any]] = []
    for entry in count_shared_fixes(
        (result.artifact or {}).get("top_fixes") or [] for result in scored
    ):
        pair = (entry["code"], entry["fix"])
        shared.append(
            {
                "code": entry["code"],
                "fix": entry["fix"],
                "feed_count": entry["agencies"],
                "feeds": [
                    result.row.name
                    for result in scored
                    if any(
                        (fix.get("code", ""), fix.get("fix", "")) == pair
                        for fix in (result.artifact or {}).get("top_fixes") or []
                    )
                ],
            }
        )

    campaigns: list[dict[str, Any]] = []
    views = [_campaign_view(result) for result in scored]
    for kind in CAMPAIGNS:
        campaign = build_program_campaign(
            rollup_id="private-batch",
            rollup_name=cohort_name,
            kind=kind,
            artifacts=views,
            as_of=as_of,
        )
        for target in campaign["targets"]:
            # The public URL would name a page that does not exist for an
            # untracked feed; point at the scorecard this run wrote instead.
            target["scorecard_url"] = f"feeds/{target['agency_id']}.html"
        campaigns.append(campaign)

    expiring = sorted(
        (m for m in members if m["expiry_status"] in EXPIRING),
        key=lambda m: (m["days_until_expiry"], str(m["name"]).casefold(), m["slug"]),
    )
    return {
        "schema_version": BATCH_SCHEMA_VERSION,
        "kind": "private-batch-rollup",
        "cohort": cohort_name,
        "as_of": as_of.isoformat(),
        "feeds_listed": len(members),
        "feeds_scored": len(scored),
        "feeds_not_scored": len(members) - len(scored),
        "members": members,
        "expiring": [
            {
                "name": m["name"],
                "slug": m["slug"],
                "days_until_expiry": m["days_until_expiry"],
                "expiry_status": m["expiry_status"],
            }
            for m in expiring
        ],
        "expiry_unknown": sum(1 for m in members if m["expiry_status"] == "unknown"),
        "shared_fixes": shared,
        "campaigns": campaigns,
        "note": NOTE,
    }


# --- rendering -----------------------------------------------------------------------------


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _result_label(member: dict[str, Any]) -> str:
    if member["status"] != "scored":
        return f"Not scored: {member['reason']}"
    return f"Scored, grade {member['grade']} ({member['score']} / 100)"


def _days(member: dict[str, Any]) -> str:
    days = member["days_until_expiry"]
    return "" if days is None else str(days)


def _demote(markdown: str) -> str:
    return "\n".join("#" + line if line.startswith("#") else line for line in markdown.split("\n"))


def render_rollup_markdown(rollup: dict[str, Any]) -> str:
    """The rollup as Markdown a liaison can paste into notes or a ticket."""
    lines = [
        f"# Private cohort rollup: {rollup['cohort']}",
        "",
        f"Checked {rollup['as_of']}. {rollup['feeds_scored']} of {rollup['feeds_listed']} "
        f"feeds were scored; {rollup['feeds_not_scored']} could not be scored.",
        "",
        "## Feeds",
        "",
        "| Feed | Source | Result | Days of service left | Top fix |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for m in rollup["members"]:
        name = (
            f"[{_md(m['name'])}]({m['scorecard_html']})" if m["scorecard_html"] else _md(m["name"])
        )
        lines.append(
            f"| {name} | {_md(m['source'])} | {_md(_result_label(m))} | {_days(m)} "
            f"| {_md(m['top_fix'] or '')} |"
        )
    lines.extend(["", "## Expiring feeds", ""])
    if rollup["expiring"]:
        for m in rollup["expiring"]:
            lines.append(f"- {m['name']}: {m['days_until_expiry']} days ({m['expiry_status']})")
    else:
        lines.append("No scored feed ends its service within 30 days.")
    if rollup["expiry_unknown"]:
        lines.extend(
            ["", f"{rollup['expiry_unknown']} scored feeds publish no date their service ends."]
        )
    lines.extend(["", "## Fixes shared across the cohort", ""])
    if rollup["shared_fixes"]:
        lines.extend(["| Fix | Code | Feeds |", "| --- | --- | ---: |"])
        for fix in rollup["shared_fixes"]:
            lines.append(f"| {_md(fix['fix'])} | `{fix['code']}` | {fix['feed_count']} |")
    else:
        lines.append("No top fix appears in more than one scored feed.")
    lines.extend(["", "## Worklists", ""])
    for campaign in rollup["campaigns"]:
        lines.append(_demote(render_program_campaign_markdown(campaign)))
    lines.extend([f"_{rollup['note']}_", ""])
    return "\n".join(lines)


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_rollup_html(rollup: dict[str, Any]) -> str:
    """The rollup as one self-contained HTML page. It loads nothing from the network."""
    rows = []
    for m in rollup["members"]:
        name = (
            f'<a href="{_h(m["scorecard_html"])}">{_h(m["name"])}</a>'
            if m["scorecard_html"]
            else _h(m["name"])
        )
        rows.append(
            f'<tr><th scope="row">{name}</th><td>{_h(m["source"])}</td>'
            f"<td>{_h(_result_label(m))}</td><td>{_h(_days(m))}</td>"
            f"<td>{_h(m['top_fix'] or '')}</td></tr>"
        )
    expiring = (
        "<ul>"
        + "".join(
            f"<li>{_h(m['name'])}: {_h(m['days_until_expiry'])} days "
            f"({_h(m['expiry_status'])})</li>"
            for m in rollup["expiring"]
        )
        + "</ul>"
        if rollup["expiring"]
        else "<p>No scored feed ends its service within 30 days.</p>"
    )
    if rollup["expiry_unknown"]:
        expiring += (
            f"<p>{_h(rollup['expiry_unknown'])} scored feeds publish no date their service "
            "ends.</p>"
        )
    shared = (
        "<table><caption>Fixes that appear in more than one scored feed's top fixes"
        '</caption><thead><tr><th scope="col">Fix</th><th scope="col">Code</th>'
        '<th scope="col">Feeds</th></tr></thead><tbody>'
        + "".join(
            f"<tr><td>{_h(fix['fix'])}</td><td><code>{_h(fix['code'])}</code></td>"
            f"<td>{_h(fix['feed_count'])}</td></tr>"
            for fix in rollup["shared_fixes"]
        )
        + "</tbody></table>"
        if rollup["shared_fixes"]
        else "<p>No top fix appears in more than one scored feed.</p>"
    )
    worklists = []
    for campaign in rollup["campaigns"]:
        meta, baseline = campaign["campaign"], campaign["baseline"]
        targets = "".join(
            f'<li><a href="{_h(t["scorecard_url"])}">{_h(t["agency_name"])}</a><ul>'
            + "".join(
                f"<li><code>{_h(f['code'])}</code>: {_h(f['observed'])} "
                f"<strong>Fix:</strong> {_h(f['fix'])}</li>"
                for f in t["findings"]
            )
            + "</ul></li>"
            for t in campaign["targets"]
        )
        worklists.append(
            f"<h3>{_h(meta['name'])}</h3><p>{_h(meta['goal'])}</p>"
            f"<p>{_h(baseline['agencies_targeted'])} of {_h(baseline['agencies_checked'])} "
            f"scored feeds need this fix; {_h(baseline['agencies_already_clear'])} are "
            "already clear.</p>"
            + (f"<ul>{targets}</ul>" if targets else "<p>No scored feed needs this fix.</p>")
        )
    title = f"Private cohort rollup: {rollup['cohort']}"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        f"<title>{_h(title)}</title>\n"
        "<style>body{font-family:system-ui,sans-serif;color:#111;background:#fff;"
        "max-width:60rem;margin:0 auto;padding:1rem;line-height:1.5}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #555;"
        "padding:.4rem;text-align:left;vertical-align:top}a{color:#0b3d91}</style>\n"
        "</head>\n<body>\n<main>\n"
        f"<h1>{_h(title)}</h1>\n"
        f"<p>Checked {_h(rollup['as_of'])}. {_h(rollup['feeds_scored'])} of "
        f"{_h(rollup['feeds_listed'])} feeds were scored; {_h(rollup['feeds_not_scored'])} "
        "could not be scored.</p>\n"
        "<h2>Feeds</h2>\n<table><caption>Every feed in the CSV, in CSV order</caption>"
        '<thead><tr><th scope="col">Feed</th><th scope="col">Source</th>'
        '<th scope="col">Result</th><th scope="col">Days of service left</th>'
        '<th scope="col">Top fix</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>\n"
        f"<h2>Expiring feeds</h2>\n{expiring}\n"
        f"<h2>Fixes shared across the cohort</h2>\n{shared}\n"
        "<h2>Worklists</h2>\n"
        + "\n".join(worklists)
        + f"\n<p><em>{_h(rollup['note'])}</em></p>\n</main>\n</body>\n</html>\n"
    )


def rollup_members_csv(rollup: dict[str, Any]) -> str:
    """Every feed as one spreadsheet row, in CSV order. A feed that was not scored
    has empty grade and score cells, never an F or a zero."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([header for header, _ in _MEMBER_CSV_COLUMNS])
    for member in rollup["members"]:
        writer.writerow([_csv_cell(member.get(key)) for _, key in _MEMBER_CSV_COLUMNS])
    return buffer.getvalue()


def write_batch_outputs(
    out_dir: Path,
    results: Sequence[BatchResult],
    rollup: dict[str, Any],
    *,
    render_html: Callable[[dict[str, Any]], str],
) -> list[Path]:
    """Write every per-feed scorecard and the four rollup files under ``out_dir``."""
    feeds = out_dir / "feeds"
    feeds.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for result in results:
        if result.artifact is None:
            continue
        json_path = feeds / f"{result.row.slug}.json"
        json_path.write_text(json.dumps(result.artifact, indent=2, sort_keys=True) + "\n")
        html_path = feeds / f"{result.row.slug}.html"
        html_path.write_text(render_html(result.artifact))
        written.extend([json_path, html_path])
    for name, text in (
        ("rollup.json", json.dumps(rollup, indent=2, sort_keys=True) + "\n"),
        ("rollup.md", render_rollup_markdown(rollup)),
        ("rollup.html", render_rollup_html(rollup)),
        ("rollup.csv", rollup_members_csv(rollup)),
    ):
        path = out_dir / name
        path.write_text(text)
        written.append(path)
    return written
