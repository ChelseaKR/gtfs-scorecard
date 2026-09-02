"""Governed validator upgrades: shadow-score a candidate version (FIX-06).

The measuring stick must never change blind. `validate.py` pins one
gtfs-validator version, and every validator release adds, removes, or
reclassifies notices — which silently moves grades for every tracked agency at
once. Before a `VALIDATOR_VERSION` bump lands, this module dual-scores a
deterministic national sample with the pinned and the candidate jars, diffs
per-agency grades and per-code notice populations, and renders a Markdown +
JSON impact report. The report includes a ready-to-paste
`score.py:METHODOLOGY_CHANGELOG` entry, so the observed national effect ships
with the bump ("validator X→Y: median score unchanged, N agencies moved one
band, driven by <code>").

Run it via `scorecard canary --candidate-version <X.Y.Z>` (locally or the
manual-dispatch validator-canary.yml workflow). The baseline half reuses the
validator-result cache (vcache.py), so for unchanged feeds it is nearly free;
only the candidate half needs fresh Java runs.

`diff_results` and `render_report` are pure functions over plain result dicts,
so the comparison logic is unit-testable offline without Java or the network.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import statistics
from pathlib import Path
from typing import Any

from .completeness import completeness
from .config import AGENCIES, Agency, raw_dir, repo_root, utc_today
from .fetch import FetchResult, fetch_static
from .gtfs import read_feed_dates
from .metrics import correctness, freshness
from .score import GRADE_BANDS, build_scorecard
from .validate import (
    VALIDATOR_VERSION,
    ValidationReport,
    country_scoped_output_dir,
    parse_report,
    run_validator,
)
from .vcache import load_cached, store_cached

log = logging.getLogger(__name__)

# Grade letters mapped to a numeric band index (F=0 … A=4), derived from the
# rubric's own bands so a band change in score.py flows through automatically.
_BAND_INDEX = {letter: i for i, (_, letter) in enumerate(reversed(GRADE_BANDS))}


def sample_agencies(agency_ids: list[str], size: int = 100, seed: int = 0) -> list[str]:
    """A deterministic, evenly spread sample of agency ids.

    Stride sampling over the sorted id list (the same order shards.py fans out)
    picks every (n/size)-th agency, so the sample spans the whole registry
    instead of clustering, and the same ids come back on every run: the two
    validator versions — and any re-run of the report — see the exact same
    population. ``seed`` rotates the starting offset for an alternative but
    equally reproducible sample.
    """
    if size < 1:
        raise ValueError("sample size must be at least 1")
    ids = sorted(set(agency_ids))
    if len(ids) <= size:
        return ids
    stride = len(ids) / size
    offset = seed % len(ids)
    return sorted(ids[(offset + int(i * stride)) % len(ids)] for i in range(size))


def agency_result(
    agency_id: str, report: ValidationReport, grade: str, score: float
) -> dict[str, Any]:
    """One agency's shadow-run outcome as plain data (the diffing unit)."""
    return {
        "agency_id": agency_id,
        "grade": grade,
        "score": round(score, 1),
        "notices": {g.code: {"severity": g.severity, "total": g.total} for g in report.notices},
    }


def _scored_result(
    agency: Agency, fetched: FetchResult, date: dt.date, report: ValidationReport
) -> dict[str, Any]:
    """Score one validator report exactly the way the daily run does (minus
    realtime, which no validator version affects), so the grade shift the diff
    sees is purely validator-driven."""
    reader_path = fetched.reader_view_path
    cats = [
        c
        for c in (
            correctness(report),
            freshness(
                read_feed_dates(str(reader_path)), today=date, service_type=agency.service_type
            ),
            completeness(str(reader_path), fare_free=agency.fare_free),
        )
        if c is not None
    ]
    scorecard = build_scorecard(cats)
    return agency_result(agency.id, report, scorecard.grade, scorecard.overall_score)


def shadow_score_agency(
    agency: Agency, date: dt.date, candidate_version: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Score one agency's feed with both validator versions; return
    (baseline, candidate) result dicts over identical feed bytes.

    The baseline half goes through vcache first, so a feed already validated by
    the daily run costs no Java at all. The candidate report is deliberately
    NOT written to vcache: the cache holds one entry per agency keyed to the
    production version, and storing the candidate would evict the baseline.
    """
    fetched = fetch_static(agency, date)

    baseline_report = load_cached(
        agency.id,
        fetched.sha256,
        VALIDATOR_VERSION,
        country_code=agency.country,
    )
    if baseline_report is None:
        base_dir = country_scoped_output_dir(
            raw_dir() / agency.id / date.isoformat() / "validator",
            agency.country,
        )
        base_path = base_dir / "report.json"
        if not base_path.exists():
            base_path = run_validator(
                fetched.path,
                base_dir,
                country_code=agency.country,
            )
        baseline_report = parse_report(base_path)
        store_cached(
            agency.id,
            fetched.sha256,
            VALIDATOR_VERSION,
            baseline_report,
            country_code=agency.country,
        )

    cand_dir = country_scoped_output_dir(
        raw_dir() / agency.id / date.isoformat() / f"validator-canary-{candidate_version}",
        agency.country,
    )
    cand_path = cand_dir / "report.json"
    if not cand_path.exists():
        cand_path = run_validator(
            fetched.path,
            cand_dir,
            country_code=agency.country,
            version=candidate_version,
        )
    candidate_report = parse_report(cand_path)

    return (
        _scored_result(agency, fetched, date, baseline_report),
        _scored_result(agency, fetched, date, candidate_report),
    )


def _notice_population(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate per-code notice counts across a run's agencies."""
    population: dict[str, dict[str, Any]] = {}
    for result in results:
        for code, group in result["notices"].items():
            entry = population.setdefault(
                code, {"severity": group["severity"], "instances": 0, "agencies": 0}
            )
            entry["instances"] += int(group["total"])
            entry["agencies"] += 1
    return population


def _notice_changes(
    baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per-code population deltas between the two runs: codes the candidate
    validator added, removed, reclassified (severity change), or whose instance
    counts moved. Unchanged codes are omitted; the rest sort by how many notice
    instances the change touches, so the top row is the change's main driver."""
    before = _notice_population(baseline)
    after = _notice_population(candidate)
    changes: list[dict[str, Any]] = []
    for code in sorted(before.keys() | after.keys()):
        b, a = before.get(code), after.get(code)
        if b is None and a is not None:
            status = "added"
        elif a is None and b is not None:
            status = "removed"
        elif b is not None and a is not None and b["severity"] != a["severity"]:
            status = "reclassified"
        elif b is not None and a is not None and b["instances"] != a["instances"]:
            status = "changed"
        else:
            continue
        changes.append(
            {
                "code": code,
                "status": status,
                "severity_before": b["severity"] if b else None,
                "severity_after": a["severity"] if a else None,
                "instances_before": b["instances"] if b else 0,
                "instances_after": a["instances"] if a else 0,
                "agencies_before": b["agencies"] if b else 0,
                "agencies_after": a["agencies"] if a else 0,
            }
        )
    changes.sort(key=lambda c: (-abs(c["instances_after"] - c["instances_before"]), c["code"]))
    return changes


def diff_results(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    skipped: list[str] | None = None,
) -> dict[str, Any]:
    """Pure comparison of two shadow runs over the same sample.

    Takes lists of `agency_result` dicts; returns plain data: per-agency grade
    before/after, the band-move histogram, median score shift, the agencies
    that changed band, and per-notice-code population deltas.
    """
    base_by_id = {r["agency_id"]: r for r in baseline}
    cand_by_id = {r["agency_id"]: r for r in candidate}
    shared = sorted(base_by_id.keys() & cand_by_id.keys())

    agencies: list[dict[str, Any]] = []
    histogram: dict[str, int] = {}
    deltas: list[float] = []
    for agency_id in shared:
        b, c = base_by_id[agency_id], cand_by_id[agency_id]
        delta = round(c["score"] - b["score"], 1)
        move = _BAND_INDEX[c["grade"]] - _BAND_INDEX[b["grade"]]
        agencies.append(
            {
                "agency_id": agency_id,
                "grade_before": b["grade"],
                "grade_after": c["grade"],
                "score_before": b["score"],
                "score_after": c["score"],
                "score_delta": delta,
                "band_move": move,
            }
        )
        deltas.append(delta)
        key = f"{move:+d}" if move else "0"
        histogram[key] = histogram.get(key, 0) + 1

    band_moves = [a for a in agencies if a["band_move"] != 0]
    band_moves.sort(key=lambda a: (-abs(a["band_move"]), a["agency_id"]))

    return {
        "agencies_compared": len(shared),
        "skipped_agencies": sorted(skipped or []),
        "median_score_delta": round(statistics.median(deltas), 1) if deltas else 0.0,
        "band_move_histogram": histogram,
        "band_moves": band_moves,
        "agencies": agencies,
        "notice_changes": _notice_changes(
            [base_by_id[i] for i in shared], [cand_by_id[i] for i in shared]
        ),
    }


def changelog_summary(diff: dict[str, Any], old_version: str, new_version: str) -> str:
    """The one-sentence national effect, phrased for METHODOLOGY_CHANGELOG."""
    median = diff["median_score_delta"]
    median_phrase = (
        "median score unchanged" if median == 0 else f"median score shift {median:+.1f} points"
    )
    moved = len(diff["band_moves"])
    total = diff["agencies_compared"]
    moved_phrase = f"{moved} of {total} sampled agencies changed grade band"
    drivers = diff["notice_changes"]
    driver_phrase = f", driven by {drivers[0]['code']}" if drivers else ""
    return f"Validator {old_version}→{new_version}: {median_phrase}, {moved_phrase}{driver_phrase}."


def _severity_cell(before: str | None, after: str | None) -> str:
    if before == after:
        return before or "–"
    return f"{before or '–'} → {after or '–'}"


def render_report(diff: dict[str, Any], old_version: str, new_version: str, as_of: dt.date) -> str:
    """The Markdown impact report a VALIDATOR_VERSION bump must attach."""
    lines = [
        f"# Validator canary: {old_version} → {new_version}",
        "",
        f"Shadow run over {diff['agencies_compared']} sampled agencies ({as_of.isoformat()}). "
        "Both versions scored identical feed bytes, so every difference below is "
        "validator-driven, not a feed change.",
        "",
        "## Verdict",
        "",
        f"- Median score shift: {diff['median_score_delta']:+.1f} points",
        f"- Agencies that changed grade band: {len(diff['band_moves'])} "
        f"of {diff['agencies_compared']}",
        f"- Notice codes added/removed/reclassified/changed: {len(diff['notice_changes'])}",
    ]
    if diff["skipped_agencies"]:
        lines.append(
            f"- Skipped (fetch or validation failed): {', '.join(diff['skipped_agencies'])}"
        )
    lines += ["", "## Grade-band shift histogram", ""]
    lines += ["| Band move | Agencies |", "| --- | ---: |"]
    histogram = diff["band_move_histogram"]
    for key in sorted(histogram, key=int):
        lines.append(f"| {key} | {histogram[key]} |")
    if not histogram:
        lines.append("| (no agencies compared) | 0 |")

    lines += ["", "## Agencies that changed band", ""]
    if diff["band_moves"]:
        lines += ["| Agency | Grade | Score |", "| --- | --- | --- |"]
        for move in diff["band_moves"]:
            lines.append(
                f"| {move['agency_id']} | {move['grade_before']} → {move['grade_after']} "
                f"| {move['score_before']} → {move['score_after']} |"
            )
    else:
        lines.append("None.")

    lines += ["", "## Top notice-code drivers", ""]
    if diff["notice_changes"]:
        lines += [
            "| Code | Change | Severity | Instances | Agencies |",
            "| --- | --- | --- | ---: | ---: |",
        ]
        for change in diff["notice_changes"][:15]:
            lines.append(
                f"| {change['code']} | {change['status']} "
                f"| {_severity_cell(change['severity_before'], change['severity_after'])} "
                f"| {change['instances_before']} → {change['instances_after']} "
                f"| {change['agencies_before']} → {change['agencies_after']} |"
            )
    else:
        lines.append("No notice-population differences between the two versions.")

    summary = changelog_summary(diff, old_version, new_version)
    lines += [
        "",
        "## Ready-to-paste METHODOLOGY_CHANGELOG entry",
        "",
        "Prepend to `score.py:METHODOLOGY_CHANGELOG` in the same commit that bumps "
        "`VALIDATOR_VERSION`, and attach this report to the PR:",
        "",
        "```python",
        "{",
        '    "rubric_version": RUBRIC_VERSION,  # unchanged: validator upgrade only',
        f'    "effective_date": "{as_of.isoformat()}",',
        '    "summary": (',
        f'        "{summary}"',
        "    ),",
        "},",
        "```",
        "",
    ]
    return "\n".join(lines)


def write_report(
    diff: dict[str, Any],
    old_version: str,
    new_version: str,
    out_dir: Path,
    as_of: dt.date,
) -> tuple[Path, Path]:
    """Write the Markdown report and its machine-readable JSON twin."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"validator-canary-{old_version}-vs-{new_version}"
    md_path = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"
    md_path.write_text(render_report(diff, old_version, new_version, as_of))
    payload = {
        "old_version": old_version,
        "new_version": new_version,
        "as_of": as_of.isoformat(),
        "changelog_summary": changelog_summary(diff, old_version, new_version),
        **diff,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return md_path, json_path


def run_canary(
    candidate_version: str,
    sample_size: int = 100,
    seed: int = 0,
    date: dt.date | None = None,
    out_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Shadow-score the sample with both validator versions and write the
    impact report; returns (markdown_path, json_path).

    One agency's unreachable feed or failed validation must not sink the whole
    canary: failures are logged, listed in the report as skipped, and the
    comparison proceeds over the agencies that did score.
    """
    as_of = date or utc_today()
    sample = sample_agencies(
        sorted(agency_id for agency_id, agency in AGENCIES.items() if agency.is_canonical_feed),
        size=sample_size,
        seed=seed,
    )
    baseline: list[dict[str, Any]] = []
    candidate: list[dict[str, Any]] = []
    skipped: list[str] = []
    for agency_id in sample:
        try:
            base, cand = shadow_score_agency(AGENCIES[agency_id], as_of, candidate_version)
        except Exception as exc:
            log.warning("%s: skipped in canary run (%s)", agency_id, exc)
            skipped.append(agency_id)
            continue
        baseline.append(base)
        candidate.append(cand)
    diff = diff_results(baseline, candidate, skipped=skipped)
    reports_dir = out_dir if out_dir is not None else repo_root() / "data" / "canary"
    return write_report(diff, VALIDATOR_VERSION, candidate_version, reports_dir, as_of)
