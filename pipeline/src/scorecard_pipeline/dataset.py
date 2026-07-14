"""A versioned, citable open dataset of per-feed GTFS quality.

State programs and researchers keep asking the same question: how is small-agency
GTFS doing across the country, and is it getting better? Cal-ITP publishes monthly
per-agency reports for California, but there is no live national open dataset you
can download and analyze. This module turns the published index (the same one the
web app trends from) into one flat, documented table: one row per published feed
record, the latest check, with producer identity, category scores, and expiry
alongside the overall grade.

The functions here are pure over the index dict the rest of the pipeline already
produces, so the artifact is reproducible and safe to re-run:

    {"agencies": {id: {"name", "history": [
        {"date", "grade", "score", "rubric_version", "scoring_profile_id",
         "scoring_profile_rubric_version", "validator_version", "feed_sha256",
         "categories": {...}, "days_until_expiry", "service_horizon_status"}, ...
    ]}}}

Each history point carries category scores under "categories"; "realtime" is
absent when an agency publishes no realtime feed, and is reported as None rather
than zero so a missing feed is not mistaken for a failing one.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from typing import Any

from . import SCHEMA_VERSION
from .comparisons import build_comparison_cohort
from .config import Agency
from .metrics import resolve_service_horizon_status

# The four rubric categories, flattened into their own columns. "realtime" is
# optional: an agency with no realtime feed has no realtime score, reported as
# None rather than zero.
_CATEGORY_KEYS: tuple[str, ...] = ("correctness", "freshness", "completeness", "realtime")

# Stable column order for both the rows and the CSV. Kept as one named constant
# so the JSON field list, the CSV header, and the row dicts can never drift apart.
COLUMNS: tuple[str, ...] = (
    "id",
    "name",
    "date",
    "grade",
    "score",
    "rubric_version",
    "scoring_profile_id",
    "scoring_profile_rubric_version",
    "validator_version",
    "feed_sha256",
    "comparison_eligible",
    *_CATEGORY_KEYS,
    "days_until_expiry",
    "service_horizon_status",
)

# The grades the rubric can assign, in order. Fixing the set means the
# distribution always reports every grade, including the ones at zero, so a
# consumer can chart it without guessing which buckets exist.
_GRADES: tuple[str, ...] = ("A", "B", "C", "D", "F")


def _row_for_agency(agency_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Flatten a feed record's latest history point into one dataset row.

    Returns None when the record has no history, so a freshly added feed that
    has not been scored yet is skipped rather than emitted as a blank row.
    """
    history = entry.get("history") or []
    if not history:
        return None
    latest = history[-1]
    categories = latest.get("categories") or {}
    row: dict[str, Any] = {
        "id": agency_id,
        "name": entry.get("name", agency_id),
        "date": latest.get("date"),
        "grade": latest.get("grade"),
        "score": latest.get("score"),
        "rubric_version": latest.get("rubric_version"),
        "scoring_profile_id": latest.get("scoring_profile_id"),
        "scoring_profile_rubric_version": latest.get("scoring_profile_rubric_version"),
        "validator_version": latest.get("validator_version"),
        "feed_sha256": latest.get("feed_sha256"),
        "days_until_expiry": latest.get("days_until_expiry"),
        "service_horizon_status": resolve_service_horizon_status(latest),
    }
    for key in _CATEGORY_KEYS:
        row[key] = categories.get(key)
    return row


def build_quality_dataset(
    index: dict[str, Any],
    *,
    schema_version: str = "1.2",
    agencies: Iterable[Agency] | None = None,
) -> dict[str, Any]:
    """Build the flat open dataset from a published index.

    One row per published feed record, holding its most recent check: overall grade
    and score, methodology and feed-byte identity, the four category scores
    (realtime None when not published), days until the feed's service expires,
    whether that horizon is unusually distant, and whether the row belongs to
    the current producer-, category-, and identity-safe comparison cohort. Rows
    are sorted by feed id so the artifact is deterministic and diffs cleanly
    between runs. Feed records with no history are skipped.

    `schema_version` versions the dataset's own shape, independent of the
    pipeline's SCHEMA_VERSION, so a downstream citation can pin the table layout.
    """
    entries = index.get("agencies") or {}
    rows: list[dict[str, Any]] = []
    for agency_id in sorted(entries):
        row = _row_for_agency(agency_id, entries[agency_id])
        if row is not None:
            rows.append(row)
    comparable, comparison = build_comparison_cohort(rows, agencies=agencies)
    comparable_ids = {str(row.get("id") or "") for row in comparable}
    for row in rows:
        row["comparison_eligible"] = str(row.get("id") or "") in comparable_ids
    return {
        "schema_version": schema_version,
        "pipeline_schema_version": SCHEMA_VERSION,
        "generated_fields": list(COLUMNS),
        "comparison": comparison,
        "rows": rows,
    }


def _csv_cell(value: Any) -> str:
    """Render one cell. None becomes an empty string so a missing realtime score
    or expiry reads as blank, not the literal text "None"."""
    if value is None:
        return ""
    return str(value)


def to_csv(dataset: dict[str, Any]) -> str:
    """Render the dataset as CSV: a header row plus one row per feed record.

    Column order is fixed by COLUMNS and missing values render as empty cells, so
    the output is deterministic and re-running publish is a no-op. Built with the
    csv module so agency names containing commas or quotes are escaped correctly.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in dataset.get("rows", []):
        writer.writerow([_csv_cell(row.get(col)) for col in COLUMNS])
    return buf.getvalue()


def national_summary(dataset: dict[str, Any]) -> dict[str, Any]:
    """Headline statistics over the dataset for a program or press summary.

    Reports how many feed records are covered, the average overall score (rounded to
    one decimal, None when there are none), the count in each grade bucket A
    through F (every bucket present, including zeros), and the share whose feed
    has not expired (days_until_expiry > 0). Records with an unknown expiry are
    counted as not current, so pct_current never overstates how many feeds are
    safely in date.
    """
    rows = dataset.get("rows", [])
    count = len(rows)
    grade_distribution = {grade: 0 for grade in _GRADES}
    score_total = 0.0
    scored = 0
    current = 0
    for row in rows:
        grade = row.get("grade")
        if grade in grade_distribution:
            grade_distribution[grade] += 1
        score = row.get("score")
        if score is not None:
            score_total += float(score)
            scored += 1
        days = row.get("days_until_expiry")
        if days is not None and days > 0:
            current += 1
    return {
        "agency_count": count,
        "average_score": round(score_total / scored, 1) if scored else None,
        "grade_distribution": grade_distribution,
        "pct_current": round(current / count * 100, 1) if count else 0.0,
    }
