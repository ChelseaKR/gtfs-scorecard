"""Rescore stored dated records under the current rubric, from stored inputs only.

The national trend compares only records produced under one producer contract
(rubric, scoring profile, validator, reader view, measured categories). Every
rubric release therefore restarts it, and records from June to early October
2026 (rubric 1.0 to 1.3) cannot sit in the same average as rubric 1.4 records.
This module asks a narrower question of each stored record: can the score the
current rubric would have given that same feed on that same day be derived
exactly from what the record already stores, without fetching the feed again?

Each category is handled on its own terms:

- **Correctness** is recomputed with the current ``metrics.correctness`` from
  the notice groups the record stores (code, severity, instance count). The
  record must carry every group: the count of groups and the instances per
  severity must match its own ``details``, or it is not rescored.
- **Freshness** is recomputed with the current ``metrics.freshness`` from the
  feed dates the record stores, as of the record's own snapshot date, the same
  way the freshness sweep does. A record that stores no end date is not
  rescored, because "no dates" cannot be told apart from "no date tables".
- **Rider experience completeness** reads the feed archive. Rubric 1.3 (loop
  headsign exemption, ADR 0041) and 1.4 (stop_headsign credit, ADR 0060) only
  ever add headsign credit, and the other components have not changed except
  for archives with no stops or no trips. So the stored score is the current
  score when the record has stops and trips and no missing-headsign finding.
  Otherwise the score of a native current-rubric record of the same feed bytes
  (same sha256, same fare-free setting) is used when one exists. Anything else
  is not rescored.
- **Realtime** is a live observation that cannot be repeated. Its rubric last
  changed in 1.2, so a stored realtime score from rubric 1.2 or later is the
  current rubric's reading of that observation. A rubric 1.0 or 1.1 record that
  measured realtime is not rescored.

A record that cannot be rescored is reported with its reason and contributes no
number. The output never rewrites a dated record; it is a separate derived
file (``rescored-history.json`` beside ``index.json``).
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import RUBRIC_VERSION, SCORING_PROFILE_ID
from .comparisons import reader_archive_profile
from .corrections import grades_a_feed_with_nothing_in_it
from .metrics import CategoryResult, correctness, freshness
from .score import build_scorecard, published_overall
from .sweep import _category_from_json, _feed_dates
from .validate import VALIDATOR_VERSION, NoticeGroup, ValidationReport

RESCORED_HISTORY_FILENAME = "rescored-history.json"
RESCORED_HISTORY_SCHEMA = "rescored-history/1"

#: Rubric versions whose realtime rule is the current one (rubric 1.2, ADR in
#: METHODOLOGY_CHANGELOG: "Realtime quality now assesses only the GTFS-Realtime
#: feed kinds an agency publishes").
REALTIME_RULE_SINCE = ("1.2", "1.3", "1.4")

_CATEGORY_ORDER = ("correctness", "freshness", "completeness", "realtime")

#: Row layout in the stored file. One array per rescored record keeps ~150,000
#: rows to a few megabytes. A category the record did not measure is null, never
#: a number; the letter is not stored because it is derived from the score.
ROW_COLUMNS = (
    "date",
    "score",
    "days_until_expiry",
    "rescored_from_rubric",
    "reader_archive_profile",
    *_CATEGORY_ORDER,
)
_ISO_DATE_LEN = 10


@dataclass(frozen=True)
class RescoreResult:
    """One stored record's rescore: a history row, or the reason there is none."""

    row: dict[str, Any] | None
    reason: str | None
    completeness_source: str | None = None


def _measured(category: Any) -> bool:
    return isinstance(category, dict) and category.get("status") == "measured"


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def completeness_key(artifact: Mapping[str, Any]) -> tuple[str, bool] | None:
    """(feed sha256, fare-free setting): what rider-experience completeness reads."""
    sha = (artifact.get("feed") or {}).get("sha256")
    cat = (artifact.get("categories") or {}).get("completeness")
    if not isinstance(sha, str) or not sha or not isinstance(cat, dict) or not _measured(cat):
        return None
    return sha, bool((cat.get("details") or {}).get("fare_free"))


def native_completeness_scores(
    artifacts: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, bool], float]:
    """Completeness scores from records the current rubric itself produced.

    Keyed by (feed bytes, fare-free setting). A key whose native records
    disagree is left out rather than guessed.
    """
    seen: dict[tuple[str, bool], set[float]] = {}
    for artifact in artifacts:
        if artifact.get("rubric_version") != RUBRIC_VERSION:
            continue
        key = completeness_key(artifact)
        if key is None:
            continue
        score = artifact["categories"]["completeness"].get("score")
        if _number(score):
            seen.setdefault(key, set()).add(float(score))
    return {key: next(iter(values)) for key, values in seen.items() if len(values) == 1}


def _correctness(cat: Mapping[str, Any]) -> CategoryResult | None:
    details = cat.get("details") or {}
    groups: list[NoticeGroup] = []
    for finding in cat.get("findings") or []:
        code, severity, count = finding.get("code"), finding.get("severity"), finding.get("count")
        if not isinstance(code, str) or not isinstance(severity, str) or not isinstance(count, int):
            return None
        groups.append(NoticeGroup(code=code, severity=severity, total=count))
    report = ValidationReport(
        validator_version=str(details.get("validator_version") or ""), notices=groups
    )
    if details.get("distinct_codes") != len(groups):
        return None
    stored_counts = details.get("instances_by_severity")
    if not isinstance(stored_counts, dict) or {
        key: value for key, value in report.count_by_severity().items() if value
    } != {key: value for key, value in stored_counts.items() if value}:
        return None
    return correctness(report)


def _completeness(
    artifact: Mapping[str, Any], native: Mapping[tuple[str, bool], float]
) -> tuple[CategoryResult | None, str]:
    cat = artifact["categories"]["completeness"]
    if artifact.get("rubric_version") == RUBRIC_VERSION:
        return _category_from_json(dict(cat)), "native"
    key = completeness_key(artifact)
    if key is not None and key in native:
        stored = _category_from_json(dict(cat))
        return (
            CategoryResult(
                name="completeness",
                score=native[key],
                summary=stored.summary,
                findings=stored.findings,
                details=stored.details,
            ),
            "same_feed_bytes_native",
        )
    details = cat.get("details") or {}
    stops, trips = details.get("stops"), details.get("trips")
    if not (isinstance(stops, int) and stops > 0 and isinstance(trips, int) and trips > 0):
        return None, "completeness_denominator_empty"
    if details.get("unmeasured_components"):
        return None, "completeness_component_unmeasured"
    if details.get("mixed_case_stop_name_pct") in (None, 0, 0.0):
        # Before issue #300 a feed with no cased stop names scored 0 here; the
        # current rubric drops the component. The stored record cannot say which.
        return None, "completeness_stop_names_ambiguous"
    if any(f.get("code") == "scorecard_missing_headsigns" for f in cat.get("findings") or []):
        return None, "completeness_headsign_credit_needs_feed_bytes"
    return _category_from_json(dict(cat)), "stored_headsigns_complete"


def _provenance_reason(artifact: Mapping[str, Any]) -> str | None:
    """Why a record's provenance rules out a rescore, or None when it does not."""
    if not artifact.get("rubric_version"):
        return "no_rubric_provenance"
    if artifact.get("validator_version") != VALIDATOR_VERSION:
        return "validator_version_differs"
    if not reader_archive_profile(dict(artifact)):
        return "reader_archive_profile_unknown"
    try:
        dt.date.fromisoformat(str(artifact.get("snapshot_date")))
    except ValueError:
        return "snapshot_date_invalid"
    if grades_a_feed_with_nothing_in_it(dict(artifact)):
        return "unreadable_under_current_rubric"
    return None


def _freshness(cat: Any, as_of: dt.date) -> tuple[CategoryResult | None, str]:
    if not _measured(cat):
        return None, "freshness_not_measured"
    details = cat.get("details") or {}
    if not (details.get("feed_end_date") or details.get("last_service_date")):
        return None, "freshness_no_stored_dates"
    fresh = freshness(_feed_dates(details), as_of, details.get("service_type", "fixed"))
    if fresh is None:
        return None, "freshness_unmeasurable"
    return fresh, ""


def rescore_artifact(
    artifact: Mapping[str, Any], native: Mapping[tuple[str, bool], float]
) -> RescoreResult:
    """The current rubric's score for one stored dated record, or why not."""
    reason = _provenance_reason(artifact)
    if reason is not None:
        return RescoreResult(None, reason)
    rubric = str(artifact["rubric_version"])
    snapshot = str(artifact["snapshot_date"])
    cats = artifact.get("categories") or {}

    if not _measured(cats.get("correctness")):
        return RescoreResult(None, "correctness_not_measured")
    corr = _correctness(cats["correctness"])
    if corr is None:
        return RescoreResult(None, "correctness_inputs_incomplete")
    fresh, reason = _freshness(cats.get("freshness"), dt.date.fromisoformat(snapshot))
    if fresh is None:
        return RescoreResult(None, reason)
    if not _measured(cats.get("completeness")):
        return RescoreResult(None, "completeness_not_measured")
    comp, source = _completeness(artifact, native)
    if comp is None:
        return RescoreResult(None, source)
    measured = [corr, fresh, comp]
    if _measured(cats.get("realtime")):
        if rubric not in REALTIME_RULE_SINCE:
            return RescoreResult(None, "realtime_rule_predates_1_2")
        measured.append(_category_from_json(dict(cats["realtime"])))

    card = build_scorecard(measured)
    overall = published_overall(card.overall_score)
    days = fresh.details.get("days_until_expiry")
    row = {
        "date": str(snapshot),
        "score": overall["score"],
        "grade": overall["grade"],
        "days_until_expiry": days,
        "reader_archive_profile": reader_archive_profile(dict(artifact)),
        "measured": [c for c in _CATEGORY_ORDER if c in card.categories],
        "categories": {
            c: round(card.categories[c].score, 1) for c in _CATEGORY_ORDER if c in card.categories
        },
        "rescored_from_rubric": str(rubric),
    }
    return RescoreResult(row, None, source)


def reproduces_native(artifact: Mapping[str, Any]) -> bool | None:
    """Whether rescoring a native current-rubric record reproduces it exactly.

    The control for the whole method: the same arithmetic applied to a record
    the current rubric itself published must return its published score,
    letter, and every measured category score, to the published decimal. None
    when the record is not a current-rubric record or cannot be rescored.
    """
    if artifact.get("rubric_version") != RUBRIC_VERSION:
        return None
    result = rescore_artifact(artifact, {})
    if result.row is None:
        return None
    return _matches_published(artifact, result.row)


def _matches_published(artifact: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    overall = artifact.get("overall") or {}
    published = {
        name: cat.get("score")
        for name, cat in (artifact.get("categories") or {}).items()
        if _measured(cat)
    }
    return bool(
        row["score"] == overall.get("score")
        and row["grade"] == overall.get("grade")
        and row["categories"] == published
    )


def iter_dated_artifacts(root: Path, agency_id: str) -> Iterator[dict[str, Any]]:
    """Readable dated records for one agency whose path, date, and id agree."""
    agency_dir = root / agency_id
    for path in sorted(agency_dir.glob("[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json")):
        try:
            artifact = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(artifact, dict):
            continue
        if str(artifact.get("snapshot_date")) != path.stem:
            continue
        if str((artifact.get("agency") or {}).get("id")) != agency_id:
            continue
        yield artifact


def build_rescored_history(
    root: Path, agency_ids: Iterable[str], *, through: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Rescore every stored pre-current-rubric record for ``agency_ids``.

    ``through`` optionally caps each agency at a date (its index tail), so a
    record newer than the published commit pointer is never used.
    """
    ids = sorted(agency_ids)
    # Pass 1: native completeness by feed bytes, across the whole corpus (a
    # feed record id can change while the bytes do not).
    native = native_completeness_scores(
        artifact for agency_id in ids for artifact in iter_dated_artifacts(root, agency_id)
    )
    agencies: dict[str, list[list[Any]]] = {}
    reproduction: Counter[str] = Counter()
    differing: list[str] = []
    # date -> [sum of rescored scores, sum of published scores, records]
    native_average: dict[str, list[float]] = {}
    max_difference = 0.0
    reasons: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    first_date = last_date = ""
    for agency_id in ids:
        cap = (through or {}).get(agency_id)
        rows: list[list[Any]] = []
        for artifact in iter_dated_artifacts(root, agency_id):
            date = str(artifact["snapshot_date"])
            if cap and date > cap:
                continue
            if artifact.get("rubric_version") == RUBRIC_VERSION:
                control = rescore_artifact(artifact, {}).row
                verdict = None if control is None else _matches_published(artifact, control)
                if control is not None:
                    sums = native_average.setdefault(date, [0.0, 0.0, 0])
                    sums[0] += float(control["score"])
                    sums[1] += float(artifact["overall"]["score"])
                    sums[2] += 1
                    max_difference = max(
                        max_difference,
                        round(
                            abs(float(control["score"]) - float(artifact["overall"]["score"])), 1
                        ),
                    )
                key = "not_rescorable" if verdict is None else "exact" if verdict else "differs"
                reproduction[key] += 1
                if verdict is False and len(differing) < 20:
                    differing.append(f"{agency_id}/{date}")
                continue
            result = rescore_artifact(artifact, native)
            if result.row is None:
                reasons[str(result.reason)] += 1
                continue
            sources[str(result.completeness_source)] += 1
            packed = [result.row.get(column) for column in ROW_COLUMNS[:5]]
            packed.extend(result.row["categories"].get(c) for c in _CATEGORY_ORDER)
            rows.append(packed)
            first_date = min(first_date or date, date)
            last_date = max(last_date, date)
        if rows:
            agencies[agency_id] = rows
    rescored = sum(len(rows) for rows in agencies.values())
    return {
        "schema": RESCORED_HISTORY_SCHEMA,
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "validator_version": VALIDATOR_VERSION,
        "method": (
            "Stored dated records from earlier rubric versions, rescored under the "
            "current rubric from what each record stores, without fetching any feed "
            "again. Correctness and freshness are recomputed; rider-experience "
            "completeness and realtime are carried only where the rubric changes "
            "since that record provably cannot move them. Records that cannot be "
            "rescored that way are counted by reason and contribute no number."
        ),
        "reproduction": {
            "native_records_checked": reproduction["exact"] + reproduction["differs"],
            "native_records_exact": reproduction["exact"],
            "native_records_not_rescorable": reproduction["not_rescorable"],
            "differing_examples": differing,
            "max_overall_difference": max_difference,
            # The control at the level the trend publishes: per date, the
            # average of the rescored native records against the average of
            # what was published, both to the trend's one decimal.
            "native_average_by_date": {
                date: {
                    "records": int(n),
                    "rescored_average": round(rescored_sum / n, 1),
                    "published_average": round(published_sum / n, 1),
                }
                for date, (rescored_sum, published_sum, n) in sorted(native_average.items())
            },
        },
        "coverage": {
            "records_rescored": rescored,
            "records_not_rescored": sum(reasons.values()),
            "not_rescored_by_reason": dict(sorted(reasons.items())),
            "completeness_source": dict(sorted(sources.items())),
            "feed_records": len(agencies),
            "first_date": first_date or None,
            "last_date": last_date or None,
        },
        "columns": list(ROW_COLUMNS),
        "agencies": agencies,
    }


def rescored_history_rows(document: Mapping[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Index-history-shaped rows by agency and date from a rescored-history file.

    Rows carry the current producer contract (they were computed by it) plus
    ``rescored_from_rubric``. A file for another rubric yields nothing, so a
    later rubric release can never splice stale rescored rows into its trend.
    """
    if (
        document.get("schema") != RESCORED_HISTORY_SCHEMA
        or document.get("rubric_version") != RUBRIC_VERSION
        or document.get("scoring_profile_id") != SCORING_PROFILE_ID
        or document.get("validator_version") != VALIDATOR_VERSION
    ):
        return {}
    if list(document.get("columns") or []) != list(ROW_COLUMNS):
        return {}
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for agency_id, rows in (document.get("agencies") or {}).items():
        by_date: dict[str, dict[str, Any]] = {}
        for packed in rows or []:
            if not isinstance(packed, list) or len(packed) != len(ROW_COLUMNS):
                continue
            row = dict(zip(ROW_COLUMNS, packed, strict=True))
            date = str(row["date"] or "")
            if len(date) != _ISO_DATE_LEN or not _number(row["score"]):
                continue
            by_date[date] = {
                "date": date,
                "score": row["score"],
                "grade": published_overall(float(row["score"]))["grade"],
                "days_until_expiry": row["days_until_expiry"],
                "rubric_version": RUBRIC_VERSION,
                "scoring_profile_id": SCORING_PROFILE_ID,
                "scoring_profile_rubric_version": RUBRIC_VERSION,
                "validator_version": VALIDATOR_VERSION,
                "reader_archive_profile": row["reader_archive_profile"],
                "categories": {c: row[c] for c in _CATEGORY_ORDER if _number(row[c])},
                "rescored_from_rubric": row["rescored_from_rubric"],
            }
        if by_date:
            out[str(agency_id)] = by_date
    return out


def splice_rescored(
    history: list[dict[str, Any]], rescored: Mapping[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Replace earlier-rubric index rows with their rescored rows, by date.

    A row already under the current rubric is never replaced. An earlier-rubric
    row with no rescored counterpart stays as it is, so the contract suffix
    still breaks there: a record that could not be rescored ends the series
    instead of being bridged by a carried-forward value.
    """
    out: list[dict[str, Any]] = []
    for row in history:
        date = str(row.get("date") or "")
        replacement = rescored.get(date)
        if row.get("rubric_version") != RUBRIC_VERSION and replacement is not None:
            out.append(replacement)
        else:
            out.append(row)
    return out
