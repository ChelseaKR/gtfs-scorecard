"""Freshness sweep: refresh the time-based freshness category between full scores.

Freshness is a pure function of a feed's calendar dates and today's date (see
metrics.freshness), so once a feed has been fetched and scored, its expiry
countdown can be recomputed cheaply without re-downloading or re-validating.

Why this exists: the classic small-agency failure is a feed that silently
expires. A full score runs the Java validator and is comparatively expensive, so
if it is delayed or skipped (the kind of gap that let a feed's expiry go
unnoticed for a couple of days), the published expiry clock goes stale with it.
This sweep is cheap and has no network or Java dependency, so it can run far more
often and keep the expiry countdown and grade current on its own.

It carries forward the last full score's correctness, completeness, and realtime
(those need a re-fetch to change) and recomputes only freshness for the sweep
date, then re-derives the overall grade and top fixes the same way scoring does.
The result is written as a new dated artifact marked `recompute`, so it never
rewrites a past snapshot's freshness (which must stay fixed at that snapshot's
date) and trend history stays honest.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .gtfs import FeedDates
from .metrics import CategoryResult, Finding, freshness
from .score import CATEGORY_WEIGHTS, build_scorecard


def _date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def _finding_from_json(d: dict[str, Any]) -> Finding:
    # `points` is the serialized deduction (metrics.Finding.to_json); older
    # artifacts predate it, so fall back to 0 — only the relative ordering of
    # same-tier fixes depends on it, and the next full score restores it.
    return Finding(
        code=d["code"],
        severity=d.get("severity", "INFO"),
        count=int(d.get("count", 1)),
        what=d.get("what", ""),
        why=d.get("why", ""),
        fix=d.get("fix", ""),
        effort=d.get("effort", ""),
        deduction=float(d.get("points", 0.0)),
    )


def _category_from_json(d: dict[str, Any]) -> CategoryResult:
    return CategoryResult(
        name=d["name"],
        score=float(d.get("score", 0.0)),
        summary=d.get("summary", ""),
        findings=[_finding_from_json(f) for f in d.get("findings", [])],
        details=dict(d.get("details", {})),
    )


def _feed_dates(details: dict[str, Any]) -> FeedDates:
    # feed_publisher_name is not stored and not read by freshness(), so None.
    # seasonal_boundary round-trips through details (freshness() records it);
    # artifacts from before it existed default to False, the conservative read.
    return FeedDates(
        has_feed_info=bool(details.get("has_feed_info")),
        feed_publisher_name=None,
        feed_version=details.get("feed_version"),
        feed_start_date=_date(details.get("feed_start_date")),
        feed_end_date=_date(details.get("feed_end_date")),
        last_service_date=_date(details.get("last_service_date")),
        seasonal_boundary=bool(details.get("seasonal_boundary")),
    )


def can_resweep(artifact: dict[str, Any]) -> bool:
    """True when freshness was scored from real dates we can recompute against.

    A feed with no readable expiry (the `scorecard_no_expiry_date` case) stores
    no dates, so there is nothing to recompute and a full re-score is the only
    way its freshness changes."""
    fresh = artifact.get("categories", {}).get("freshness", {})
    if fresh.get("status") != "measured":
        return False
    details = fresh.get("details", {})
    return bool(details.get("feed_end_date") or details.get("last_service_date"))


def needs_sweep(artifact: dict[str, Any], today: dt.date) -> bool:
    """True when a feed can be reswept and its latest score predates `today`.

    A feed already scored on the sweep date (a full run, or an earlier sweep the
    same day) is current, so re-sweeping would only restamp it and, worse, demote
    a full score to a freshness-only recompute. Skipping keeps the sweep safe to
    run alongside and after the daily full score, and makes repeat runs no-ops."""
    if not can_resweep(artifact):
        return False
    snapshot = artifact.get("snapshot_date")
    return not (isinstance(snapshot, str) and snapshot >= today.isoformat())


def resweep(artifact: dict[str, Any], today: dt.date) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recompute freshness for `today` and re-derive the grade.

    Returns the new dated artifact and a summary of what moved. The caller
    decides whether to publish it (see cli `freshness-sweep`).
    """
    cats = artifact.get("categories", {})
    fresh_json = cats["freshness"]
    details = fresh_json.get("details", {})
    service_type = details.get("service_type", "fixed")

    new_fresh = freshness(_feed_dates(details), today, service_type)
    # `_feed_dates` rebuilds from a published artifact whose freshness was
    # measured, so the date tables were there and freshness re-measures. The
    # guard keeps the sweep from silently rewriting a category into nothing.
    if new_fresh is None:  # pragma: no cover - a measured category cannot unmeasure
        raise ValueError("re-scoring a measured freshness category produced no measurement")

    measured: list[CategoryResult] = []
    for name, cat in cats.items():
        if cat.get("status") != "measured":
            continue
        measured.append(new_fresh if name == "freshness" else _category_from_json(cat))
    card = build_scorecard(measured).to_json()

    new_cats = {name: dict(cat) for name, cat in cats.items()}
    new_cats["freshness"] = {**new_fresh.to_json(), "weight": CATEGORY_WEIGHTS["freshness"]}

    new_artifact = dict(artifact)
    new_artifact["categories"] = new_cats
    new_artifact["overall"] = card["overall"]
    new_artifact["top_fixes"] = card["top_fixes"]
    new_artifact["snapshot_date"] = today.isoformat()
    # Mark this as a freshness-only recompute, naming the date the feed was last
    # actually fetched, so a consumer never mistakes it for a fresh validation.
    new_artifact["recompute"] = {
        "kind": "freshness",
        "as_of": today.isoformat(),
        "feed_fetched_date": artifact.get("snapshot_date"),
    }

    old = artifact.get("overall", {})
    summary = {
        "id": artifact.get("agency", {}).get("id"),
        "name": artifact.get("agency", {}).get("name"),
        "old_grade": old.get("grade"),
        "new_grade": card["overall"]["grade"],
        "old_score": old.get("score"),
        "new_score": card["overall"]["score"],
        "old_days": details.get("days_until_expiry"),
        "new_days": new_cats["freshness"]["details"].get("days_until_expiry"),
        "grade_changed": old.get("grade") != card["overall"]["grade"],
    }
    return new_artifact, summary
