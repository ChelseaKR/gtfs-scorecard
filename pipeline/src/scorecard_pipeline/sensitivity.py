"""Rubric weight sensitivity: would the letters survive different judgment calls?

The category weights (score.py:CATEGORY_WEIGHTS, 35/20/25/20) are judgment
calls, honestly documented in docs/rubric.md — but their *consequences* are
not: nobody can see whether the national grade picture is an artifact of that
split or robust to it. This measures it (FIX-07): rescore the latest national
snapshot under one-at-a-time weight perturbations (each category ±20%,
renormalized) and report the share of agencies whose letter grade changes
under each, plus the overall maximum churn. Publishing the result extends the
project's "reproduce or contest the grade" stance to the weights themselves.

It is pure over the published index the site already trends from (each
agency's latest per-category scores ride on its history entries), so the study
is reproducible and adds no per-agency work. It changes no grade; it measures
how stable the grades are. Run via ``scorecard sensitivity``, which publishes
data/artifacts/sensitivity.json; the how-to-read page surfaces the headline.
"""

from __future__ import annotations

from typing import Any

from .score import CATEGORY_WEIGHTS, letter_grade, published_score

# The published perturbation size: each weight moved by this fraction of itself.
DEFAULT_FACTOR = 0.2


def latest_category_scores(index: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Each agency's most recent per-category scores from the published index.

    Keyed by agency id. Only categories the rubric weighs are kept, and an
    agency with no scored history (or no category scores on its latest entry)
    is omitted, so an unscored agency neither counts as churned nor pads the
    denominator.
    """
    out: dict[str, dict[str, float]] = {}
    for agency_id, entry in (index.get("agencies") or {}).items():
        history = sorted(entry.get("history") or [], key=lambda h: str(h.get("date", "")))
        if not history:
            continue
        cats = history[-1].get("categories") or {}
        scores = {
            name: float(value)
            for name, value in cats.items()
            if name in CATEGORY_WEIGHTS
            and isinstance(value, int | float)
            and not isinstance(value, bool)
        }
        if scores:
            out[agency_id] = scores
    return out


def rescore(categories: dict[str, float], weights: dict[str, float]) -> float:
    """The overall 0-100 score for one agency's measured category scores under
    ``weights``, renormalized over the measured categories exactly as
    build_scorecard does, so an agency is never punished for a category the
    scorecard hasn't computed."""
    total = sum(weights[name] for name in categories)
    return sum(score * weights[name] / total for name, score in categories.items())


def published_letter(categories: dict[str, float], weights: dict[str, float]) -> str:
    """The letter this agency would publish under ``weights``.

    Rounds through ``published_score`` before grading, because that is what the
    artifact does. Grading the raw weighted average instead is the bug
    ``score.py`` documents and ``publish._validate_published_overall`` refuses
    to write: a raw 79.96875 publishes as 80.0 and grades as B, and the
    unrounded value grades as C. That guard runs inside ``publish()`` and never
    saw this study, which ``cli._cmd_sensitivity`` writes straight to
    ``sensitivity.json`` (#310).
    """
    return letter_grade(published_score(rescore(categories, weights)))


def perturbed_weights(factor: float = DEFAULT_FACTOR) -> list[dict[str, Any]]:
    """One-at-a-time perturbations of CATEGORY_WEIGHTS: each category moved by
    ±``factor`` of its own weight, then the whole set renormalized to sum to 1.

    Each entry carries the category, the direction, and the full renormalized
    weight set that was applied (rounded to 4 decimals — the same numbers the
    churn is computed with, so the published study is reproducible from its own
    artifact).
    """
    out: list[dict[str, Any]] = []
    for name in CATEGORY_WEIGHTS:
        for direction, sign in (("up", 1.0), ("down", -1.0)):
            raw = dict(CATEGORY_WEIGHTS)
            raw[name] = CATEGORY_WEIGHTS[name] * (1.0 + sign * factor)
            total = sum(raw.values())
            out.append(
                {
                    "category": name,
                    "direction": direction,
                    "weights": {k: round(v / total, 4) for k, v in raw.items()},
                }
            )
    return out


def weight_sensitivity(
    per_agency: dict[str, dict[str, float]], *, factor: float = DEFAULT_FACTOR
) -> dict[str, Any]:
    """The study: per perturbation, the share of agencies whose letter grade
    changes, plus the overall maximum churn across perturbations.

    Baseline letters are recomputed from the same category scores under the
    published weights (never read back from the index), so baseline and
    perturbed grades come through the identical renormalization path and the
    only moving part is the weights. Both sides grade the published score, so a
    feed on a band edge is compared from the letter its own page shows.
    """
    baseline = {
        agency_id: published_letter(cats, CATEGORY_WEIGHTS)
        for agency_id, cats in per_agency.items()
    }
    total = len(per_agency)
    if total == 0:
        # No denominator means no robustness result. Publishing synthetic
        # perturbations with 0% churn would read as evidence that the rubric is
        # stable when the study did not measure a single feed record.
        return {
            "factor": factor,
            "agency_count": 0,
            "perturbations": [],
            "max_grade_change_pct": None,
        }
    perturbations: list[dict[str, Any]] = []
    for perturbation in perturbed_weights(factor):
        changed = sum(
            1
            for agency_id, cats in per_agency.items()
            if published_letter(cats, perturbation["weights"]) != baseline[agency_id]
        )
        share = round(changed / total * 100, 1)
        perturbations.append(
            {**perturbation, "agencies_changed": changed, "grade_change_pct": share}
        )
    max_churn = max(p["grade_change_pct"] for p in perturbations)
    return {
        "factor": factor,
        "agency_count": total,
        "perturbations": perturbations,
        "max_grade_change_pct": max_churn,
    }
