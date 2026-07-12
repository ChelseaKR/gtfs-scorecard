"""`scorecard reproduce <agency> <date>`: re-derive a published grade from the
archived raw bytes (FIX-02, docs/ideation/02-large-scale-fixes.md).

Pulls the exact feed zip the published artifact scored, keyed by the
``feed.sha256`` the artifact already records, from the content-addressed raw
archive (archive.py); re-runs the validator pinned to the version the artifact
recorded (not necessarily today's ``VALIDATOR_VERSION`` — reproducing a grade
means reproducing the methodology that produced it, the same reasoning
canary.py uses to dual-score a candidate version); rescores
correctness/freshness/completeness exactly the way the daily run does
(cli.py:run_agency); and diffs the result against the published grade, score,
and category scores.

Realtime is deliberately excluded from the comparison: it is sampled from a
live window at fetch time and cannot be re-derived from an archived static
zip, so a reproduce run reports it as not comparable rather than silently
treating a realtime-driven mismatch as a correctness regression.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any

from . import archive
from .completeness import completeness
from .config import Agency, artifacts_dir
from .gtfs import read_feed_dates
from .metrics import correctness, freshness
from .score import build_scorecard
from .validate import parse_report, run_validator


class ReproduceError(RuntimeError):
    """A reproduce run cannot proceed: no published artifact for that
    agency/date, an artifact with no recorded feed hash, or the archived bytes
    are missing (see archive.ArchiveMiss, which this wraps with the artifact
    path for context)."""


def load_published_artifact(agency_id: str, date: str) -> dict[str, Any]:
    """The published dated artifact for one agency/date, or raise
    ReproduceError naming the path that was missing or unreadable."""
    path = artifacts_dir() / agency_id / f"{date}.json"
    try:
        text = path.read_text()
    except FileNotFoundError as exc:
        raise ReproduceError(f"no published artifact at {path}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReproduceError(f"published artifact at {path} is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ReproduceError(f"published artifact at {path} is not a JSON object")
    return data


def _round(value: Any) -> Any:
    return round(value, 1) if isinstance(value, int | float) else value


def reproduce(agency: Agency, date: str) -> dict[str, Any]:
    """Re-run the pinned validator against the archived bytes for one
    published grade and diff the result against what was published.

    Returns a plain dict: whether the reproduction matched exactly
    (``identical``), any per-field differences, which fields were skipped as
    not comparable, and which validator version and feed hash were used —
    the record a disputed-grade conversation or a validator-upgrade study
    (FIX-06) needs to cite.
    """
    artifact = load_published_artifact(agency.id, date)
    sha256 = artifact.get("feed", {}).get("sha256")
    if not sha256:
        raise ReproduceError(f"published artifact for {agency.id}/{date} has no feed.sha256")
    validator_version = artifact.get("validator_version") or None

    try:
        body = archive.fetch(sha256)
    except archive.ArchiveMiss as exc:
        raise ReproduceError(
            f"cannot reproduce {agency.id}/{date}: {exc}. Grades published before this "
            "feed's bytes were archived (or scored on a checkout with no archive bucket "
            "configured) cannot be reproduced from the raw archive."
        ) from exc

    with tempfile.TemporaryDirectory(prefix=f"scorecard-reproduce-{agency.id}-") as tmp:
        tmp_dir = Path(tmp)
        zip_path = tmp_dir / "gtfs.zip"
        zip_path.write_bytes(body)

        version_kwargs = {"version": validator_version} if validator_version else {}
        report_path = run_validator(
            zip_path,
            tmp_dir / "validator",
            country_code=agency.country,
            **version_kwargs,
        )
        report = parse_report(report_path)

        as_of = dt.date.fromisoformat(date)
        cats = [
            correctness(report),
            freshness(
                read_feed_dates(str(zip_path)), today=as_of, service_type=agency.service_type
            ),
            completeness(str(zip_path), fare_free=agency.fare_free),
        ]
        scorecard = build_scorecard(cats)

    published_overall = artifact.get("overall", {})
    published_cats = artifact.get("categories", {})

    diffs: list[str] = []
    if scorecard.grade != published_overall.get("grade"):
        diffs.append(
            f"grade: published {published_overall.get('grade')} vs re-derived {scorecard.grade}"
        )
    if _round(scorecard.overall_score) != _round(published_overall.get("score")):
        diffs.append(
            f"score: published {published_overall.get('score')} vs re-derived "
            f"{_round(scorecard.overall_score)}"
        )
    for name, cat in scorecard.categories.items():
        published_cat = published_cats.get(name, {})
        if published_cat.get("status") != "measured":
            # Not part of the published grade (e.g. realtime with no RT feed);
            # nothing to compare it against.
            continue
        if _round(cat.score) != _round(published_cat.get("score")):
            diffs.append(
                f"{name}: published {published_cat.get('score')} vs re-derived {_round(cat.score)}"
            )

    return {
        "agency_id": agency.id,
        "date": date,
        "sha256": sha256,
        "validator_version": validator_version or "unknown (artifact predates version recording)",
        "identical": not diffs,
        "differences": diffs,
        "not_compared": [
            "realtime (sampled from a live window at fetch time, not re-derivable "
            "from an archived static zip)"
        ],
    }
