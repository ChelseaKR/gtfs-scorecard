"""Reconstruct how a published grade was reached, one deduction at a time.

Issue #364. ``reproduce`` re-runs the validator and ``/how-to-read/#sandbox``
reweights, but nothing in the project shows the arithmetic behind a number it
publishes. ``docs/rubric.md`` states the ethos as "reproduce or contest the
grade"; without a printed trail the second half needs a reader who is willing
to open ``score.py``.

This module is pure. It reads one artifact and the scoring constants of the
rubric version that artifact declares, and it writes an audit trail. It fetches
nothing, scores nothing, and changes no published value.

Two design rules carry most of the weight here.

**Refuse rather than approximate.** The constants in this repository describe
the current rubric only. Handed an artifact from an older rubric version, this
module raises :class:`UnknownRubricVersion` instead of applying today's weights
to yesterday's score. An arithmetic that looks right and is not would be worse
than no arithmetic, because a reader would carry it into a dispute.

**Report the residual, never absorb it.** A category's published points do not
always sum to its distance from 100, and the overall score cannot always be
recovered from the published category scores. Both gaps are real and both have
documented causes. The trail states the leftover and names the cause it matches;
when it matches no known cause the trail says ``unexplained`` rather than
rounding the difference away. A trail that always balances would be a trail that
cannot be used to find a defect.

The second gap is measurable on the published corpus. Measured on 2026-09-06
over ``data/artifacts``:

* Of the 2,166 rubric-1.3 artifacts carrying a measured category — the ones
  this module will accept — 36 (1.66%) have an ``overall.score`` that a reader
  cannot reproduce by applying the published weights to the published category
  scores. Every one of the 36 is off by exactly one rounding step, and none of
  them crosses a grade band.
* Across all 2,494 artifacts with a measured category, including the 320 still
  on rubric 1.1, the count is 45 (1.80%), and one of those does cross a band:
  ``cape-ann-transportation-authority-cata-447`` publishes 80.0 and a B, while
  recomputing from its published category scores gives 79.9, which reads as a
  C. That artifact is on rubric 1.1, so this module refuses it rather than
  reporting on it. The category weights and grade bands have not changed since
  rubric 1.0, so the overall arithmetic there is comparable; the component
  constants behind the category scores did change, which is what the refusal
  is protecting against.

The cause is the same in every case: the pipeline weights the unrounded
category scores, while the artifact publishes each category rounded to one
decimal. Whether the overall should instead be derived from the published
category scores is a scoring decision, not a reporting one, and it is not taken
here. This module makes the gap visible where it occurs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .score import CATEGORY_WEIGHTS, GRADE_BANDS, grade_margins, letter_grade, published_score

# How close a reconstruction has to land before it counts as the same number.
# The artifact publishes to one decimal, so half a step is the largest
# difference pure rounding can produce.
ROUNDING_STEP = 0.1
_HALF_STEP = ROUNDING_STEP / 2

__all__ = [
    "CategoryTrail",
    "ExplainTrail",
    "UnknownRubricVersion",
    "build_trail",
    "render_json",
    "render_markdown",
    "render_text",
]


class UnknownRubricVersion(ValueError):
    """The artifact was scored under a rubric this build has no constants for.

    Raised instead of falling back to the current constants. The CLI turns this
    into exit code 2, which is the project's "could not be judged" code rather
    than its "judged and failed" code.
    """


@dataclass(frozen=True)
class Deduction:
    """One published line item inside a category."""

    label: str
    points: float
    detail: str = ""


@dataclass(frozen=True)
class CategoryTrail:
    """One category's published score, and what the artifact says produced it."""

    name: str
    measured: bool
    score: float | None
    raw_weight: float
    applied_weight: float | None
    deductions: list[Deduction] = field(default_factory=list)
    points_total: float | None = None
    score_delta: float | None = None
    residual: float | None = None
    residual_reason: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def contribution(self) -> float | None:
        """This category's exact share of the overall score.

        Deliberately unrounded. The overall total is summed from these, so
        rounding here would make the trail's bottom line disagree with the
        pipeline's. Measured on 2026-09-06: rounding the applied weight to six
        decimals and each contribution to four moved the published decimal for
        12 of 2,166 artifacts. Renderers round for display; the arithmetic does
        not.
        """
        if self.score is None or self.applied_weight is None:
            return None
        return self.score * self.applied_weight


@dataclass(frozen=True)
class ExplainTrail:
    """The whole reconstruction for one artifact."""

    agency: str
    snapshot_date: str
    rubric_version: str
    validator_version: str
    scoring_profile_id: str
    categories: list[CategoryTrail]
    total_weight: float
    recomputed_score: float
    recomputed_published: float
    published_overall_score: float
    published_grade: str
    reconciles: bool
    reconciliation_note: str
    margin_to_next_band: float | None
    margin_to_lower_band: float
    renormalised: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "agency": self.agency,
            "snapshot_date": self.snapshot_date,
            "rubric_version": self.rubric_version,
            "validator_version": self.validator_version,
            "scoring_profile_id": self.scoring_profile_id,
            "weights": {
                "measured_total": round(self.total_weight, 4),
                "renormalised": self.renormalised,
            },
            "categories": [
                {
                    "name": c.name,
                    "measured": c.measured,
                    "score": c.score,
                    "rubric_weight": c.raw_weight,
                    "applied_weight": (
                        None if c.applied_weight is None else round(c.applied_weight, 6)
                    ),
                    "contribution": None if c.contribution is None else round(c.contribution, 4),
                    "deductions": [
                        {"label": d.label, "points": d.points, "detail": d.detail}
                        for d in c.deductions
                    ],
                    "points_total": c.points_total,
                    "score_delta": c.score_delta,
                    "residual": c.residual,
                    "residual_reason": c.residual_reason,
                    "notes": c.notes,
                }
                for c in self.categories
            ],
            "overall": {
                "recomputed": round(self.recomputed_score, 4),
                "recomputed_published": self.recomputed_published,
                "published": self.published_overall_score,
                "grade": self.published_grade,
                "reconciles": self.reconciles,
                "reconciliation_note": self.reconciliation_note,
                "margin_to_next_band": self.margin_to_next_band,
                "margin_to_lower_band": self.margin_to_lower_band,
            },
        }


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _correctness_trail(payload: dict[str, Any], score: float) -> tuple[list[Deduction], list[str]]:
    """Per notice code, the points the artifact published for it.

    ``metrics.correctness`` starts at 100 and subtracts a severity base scaled
    by how widespread the notice is, then floors the result at zero.
    """
    deductions: list[Deduction] = []
    for finding in payload.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        points = _as_float(finding.get("points"))
        if points is None:
            continue
        count = finding.get("count")
        detail = f"{finding.get('severity', 'unknown severity')}"
        if isinstance(count, int):
            detail += f", {count} instance{'' if count == 1 else 's'}"
        deductions.append(
            Deduction(
                label=str(finding.get("code") or "unnamed notice"),
                points=points,
                detail=detail,
            )
        )
    notes: list[str] = []
    details = payload.get("details")
    if isinstance(details, dict):
        distinct = details.get("distinct_codes")
        if isinstance(distinct, int):
            notes.append(f"{distinct} distinct notice code{'' if distinct == 1 else 's'}.")
        by_severity = details.get("instances_by_severity")
        if isinstance(by_severity, dict):
            parts = ", ".join(f"{k.lower()} {v}" for k, v in sorted(by_severity.items()))
            notes.append(f"Instances by severity: {parts}.")
    if score == 0.0:
        notes.append("The category floors at 0, so points beyond 100 do not appear in the score.")
    return deductions, notes


def _completeness_trail(
    payload: dict[str, Any], _score: float
) -> tuple[list[Deduction], list[str]]:
    """Findings, plus which components this feed gave nothing to measure."""
    deductions = [
        Deduction(
            label=str(f.get("code") or "unnamed finding"),
            points=points,
            detail=(
                f"{f.get('severity', 'unknown severity')}"
                + (f", {f['count']} affected" if isinstance(f.get("count"), int) else "")
            ),
        )
        for f in (payload.get("findings") or [])
        if isinstance(f, dict) and (points := _as_float(f.get("points"))) is not None
    ]
    notes: list[str] = []
    details = payload.get("details")
    if isinstance(details, dict):
        components = details.get("components")
        if isinstance(components, dict):
            earned = {k: v for k, v in components.items() if isinstance(v, int | float)}
            unmeasured = sorted(k for k, v in components.items() if v is None)
            if earned:
                notes.append(
                    "Component points earned: "
                    + ", ".join(f"{k} {v}" for k, v in sorted(earned.items()))
                    + "."
                )
            if unmeasured:
                notes.append(
                    "Components this feed gave nothing to measure, dropped from the "
                    "denominator rather than scored zero: " + ", ".join(unmeasured) + "."
                )
        unmeasured_list = details.get("unmeasured_components")
        if (
            isinstance(unmeasured_list, list)
            and unmeasured_list
            and not any("denominator" in n for n in notes)
        ):
            notes.append(
                "Components this feed gave nothing to measure, dropped from the "
                "denominator rather than scored zero: "
                + ", ".join(str(u) for u in unmeasured_list)
                + "."
            )
    return deductions, notes


_FRESHNESS_FIELDS = (
    ("effective_expiry_date", "Effective expiry"),
    ("days_until_expiry", "Days until expiry"),
    ("feed_start_date", "feed_info start"),
    ("feed_end_date", "feed_info end"),
    ("last_service_date", "Last service date"),
    ("service_horizon_status", "Service horizon"),
    ("service_type", "Service type"),
    ("seasonal_boundary", "Seasonal boundary"),
)


def _freshness_trail(payload: dict[str, Any], _score: float) -> tuple[list[Deduction], list[str]]:
    """Freshness is a curve over the effective expiry, not a list of deductions.

    Any findings the category published are still listed, but the inputs that
    place the curve point matter more to a reader disputing the number.
    """
    deductions = [
        Deduction(
            label=str(f.get("code") or "unnamed finding"),
            points=points,
            detail=str(f.get("severity", "")),
        )
        for f in (payload.get("findings") or [])
        if isinstance(f, dict) and (points := _as_float(f.get("points"))) is not None
    ]
    notes = ["Freshness is a curve over the effective expiry date, not a sum of deductions."]
    details = payload.get("details")
    if isinstance(details, dict):
        for key, label in _FRESHNESS_FIELDS:
            value = details.get(key)
            if value is not None:
                notes.append(f"{label}: {value}.")
    return deductions, notes


def _generic_trail(payload: dict[str, Any], _score: float) -> tuple[list[Deduction], list[str]]:
    deductions = [
        Deduction(
            label=str(f.get("code") or "unnamed finding"),
            points=points,
            detail=str(f.get("severity", "")),
        )
        for f in (payload.get("findings") or [])
        if isinstance(f, dict) and (points := _as_float(f.get("points"))) is not None
    ]
    return deductions, []


_TRAIL_BUILDERS = {
    "correctness": _correctness_trail,
    "completeness": _completeness_trail,
    "freshness": _freshness_trail,
}


# Why a category's published points can legitimately fail to sum to its
# distance from 100. Each entry is a structural property of how that category
# is scored, documented in docs/rubric.md and in the rubric changelog.
_STRUCTURAL_RESIDUAL_REASONS = {
    "freshness": (
        "freshness is scored from a curve over the effective expiry date, so published "
        "findings need not sum to the drop"
    ),
    "completeness": (
        "completeness renormalises over the components this feed could be measured on, "
        "so component points need not sum to the drop"
    ),
    "realtime": (
        "realtime scores only the feed kinds the agency publishes, and its points use the "
        "same measurable-component denominator as the category score (rubric 1.2), so they "
        "need not sum to the drop"
    ),
}


def _residual_reason(name: str, residual: float, n_deductions: int, score: float) -> str:
    """Name the documented cause the leftover matches, or say it is unexplained.

    Order matters. The narrow, arithmetically checkable causes are tested
    first, so a residual is only attributed to a category's scoring shape when
    it is too large to be rounding. "unexplained" is a real outcome and is
    meant to be reachable: it is how a future scoring change that this module
    has not been taught about announces itself instead of hiding.
    """
    if residual == 0.0:
        return ""
    if score == 0.0 and residual > 0:
        return "the category floors at 0, so points beyond 100 do not reach the score"
    # Each published point is rounded to one decimal, and so is the score, so a
    # trail of n line items can drift by up to half a step per item.
    if abs(residual) <= _HALF_STEP * max(n_deductions, 1) + _HALF_STEP:
        return "rounding of each published point to one decimal"
    return _STRUCTURAL_RESIDUAL_REASONS.get(name, "unexplained")


def _category_trails(
    categories_payload: dict[str, Any], measured_names: list[str], total_weight: float
) -> list[CategoryTrail]:
    """One trail per rubric category, measured or not, in rubric order."""
    trails: list[CategoryTrail] = []
    for name, raw_weight in CATEGORY_WEIGHTS.items():
        payload = categories_payload.get(name)
        payload = payload if isinstance(payload, dict) else {}
        if name not in measured_names:
            trails.append(
                CategoryTrail(
                    name=name,
                    measured=False,
                    score=None,
                    raw_weight=raw_weight,
                    applied_weight=None,
                    notes=[
                        "Not measured this run. Its weight is redistributed across the "
                        "measured categories, so it never counts against the grade."
                    ],
                )
            )
            continue
        score = _as_float(payload.get("score"))
        if score is None:  # unreachable: measured_names already required a number
            continue
        builder = _TRAIL_BUILDERS.get(name, _generic_trail)
        deductions, notes = builder(payload, score)
        points_total = round(sum(d.points for d in deductions), 4)
        score_delta = round(100.0 - score, 4)
        residual = round(points_total - score_delta, 4)
        trails.append(
            CategoryTrail(
                name=name,
                measured=True,
                score=score,
                raw_weight=raw_weight,
                applied_weight=raw_weight / total_weight,
                deductions=deductions,
                points_total=points_total,
                score_delta=score_delta,
                residual=residual,
                residual_reason=_residual_reason(name, residual, len(deductions), score),
                notes=notes,
            )
        )
    return trails


def build_trail(artifact: dict[str, Any], *, rubric_version: str | None = None) -> ExplainTrail:
    """Reconstruct the arithmetic behind one artifact's published grade.

    ``rubric_version`` is the version whose constants this build carries; it
    defaults to the package's own. An artifact declaring anything else is
    refused.
    """
    if rubric_version is None:
        from . import RUBRIC_VERSION

        rubric_version = RUBRIC_VERSION

    declared = str(artifact.get("rubric_version") or "")
    if declared != rubric_version:
        raise UnknownRubricVersion(
            f"artifact was scored under rubric version {declared or 'an unstated version'}; "
            f"this build carries constants for {rubric_version} only. "
            "Refusing rather than applying the wrong constants."
        )

    overall = artifact.get("overall")
    if not isinstance(overall, dict):
        raise UnknownRubricVersion("artifact has no overall block to explain")
    published = _as_float(overall.get("score"))
    if published is None:
        raise UnknownRubricVersion("artifact's overall block publishes no score")

    categories_payload = artifact.get("categories")
    categories_payload = categories_payload if isinstance(categories_payload, dict) else {}

    measured_names = [
        name
        for name in CATEGORY_WEIGHTS
        if isinstance(categories_payload.get(name), dict)
        and categories_payload[name].get("status") == "measured"
        and _as_float(categories_payload[name].get("score")) is not None
    ]
    if not measured_names:
        raise UnknownRubricVersion("artifact has no measured category to explain")

    total_weight = sum(CATEGORY_WEIGHTS[name] for name in measured_names)

    trails = _category_trails(categories_payload, measured_names, total_weight)
    # Summed from the exact contributions, which is what the pipeline does.
    # The renderers round these for display, so a printed column can differ
    # from the printed total in its last shown decimal; the total is the one
    # compared against the published score.
    recomputed = sum(c.contribution or 0.0 for c in trails if c.measured)

    recomputed_published = published_score(recomputed)
    reconciles = recomputed_published == published
    if reconciles:
        note = "The published score is what the published category scores and weights produce."
    else:
        drift = round(recomputed_published - published, 4)
        note = (
            f"Recomputing from the published category scores gives {recomputed_published}, "
            f"which is {abs(drift)} away from the published {published}. The pipeline weights "
            "the unrounded category scores, while the artifact publishes each category rounded "
            "to one decimal, so the two can differ by one rounding step. The published score "
            "is the one the grade and the band margins are derived from."
        )
        # Both letters are read off a published_score(...) result at the call
        # site, which is what test_published_grade_path.py requires of every
        # module outside score.py: a letter never comes from a raw value.
        recomputed_letter = letter_grade(published_score(recomputed_published))
        published_letter = letter_grade(published_score(published))
        if recomputed_letter != published_letter:
            note += (
                " This gap crosses a grade band: the recomputed score would read as "
                f"{recomputed_letter} and the published score reads as {published_letter}."
            )

    margin_up, margin_down = grade_margins(published)
    return ExplainTrail(
        agency=str((artifact.get("agency") or {}).get("id") or artifact.get("agency_id") or "")
        if isinstance(artifact.get("agency"), dict)
        else str(artifact.get("agency") or ""),
        snapshot_date=str(artifact.get("snapshot_date") or ""),
        rubric_version=declared,
        validator_version=str(artifact.get("validator_version") or ""),
        scoring_profile_id=str((artifact.get("scoring_profile") or {}).get("id") or "")
        if isinstance(artifact.get("scoring_profile"), dict)
        else "",
        categories=trails,
        total_weight=total_weight,
        recomputed_score=recomputed,
        recomputed_published=recomputed_published,
        published_overall_score=published,
        published_grade=str(overall.get("grade") or letter_grade(published_score(published))),
        reconciles=reconciles,
        reconciliation_note=note,
        margin_to_next_band=margin_up,
        margin_to_lower_band=margin_down,
        renormalised=len(measured_names) < len(CATEGORY_WEIGHTS),
    )


def _band_sentence(trail: ExplainTrail) -> str:
    edges = ", ".join(f"{letter} at {floor:g}" for floor, letter in GRADE_BANDS if floor > 0)
    if trail.margin_to_next_band is None:
        return (
            f"{trail.published_overall_score} is an {trail.published_grade}, the top band, "
            f"{trail.margin_to_lower_band} points above its floor. Band floors: {edges}."
        )
    return (
        f"{trail.published_overall_score} is a {trail.published_grade}: "
        f"{trail.margin_to_next_band} points below the next band and "
        f"{trail.margin_to_lower_band} above this one. Band floors: {edges}."
    )


def _category_text(cat: CategoryTrail) -> list[str]:
    """One category's block in the text report."""
    if not cat.measured:
        return [
            f"{cat.name} (weight {cat.raw_weight:.0%}) - not measured",
            *(f"    {note}" for note in cat.notes),
            "",
        ]
    applied = cat.applied_weight if cat.applied_weight is not None else 0.0
    lines = [
        f"{cat.name} (rubric weight {cat.raw_weight:.0%}, applied {applied:.4f}) scored {cat.score}"
    ]
    for ded in cat.deductions:
        suffix = f" ({ded.detail})" if ded.detail else ""
        lines.append(f"    -{ded.points:>6.1f}  {ded.label}{suffix}")
    if cat.deductions:
        lines.append(f"    {'points listed':>13}: {cat.points_total}")
    lines.append(f"    {'100 - score':>13}: {cat.score_delta}")
    if cat.residual:
        lines.append(f"    {'left over':>13}: {cat.residual}  ({cat.residual_reason})")
    lines.extend(f"    {note}" for note in cat.notes)
    lines.append(f"    contributes {cat.contribution:.4f} to the overall score")
    lines.append("")
    return lines


def render_text(trail: ExplainTrail) -> str:
    header = f"How {trail.agency or 'this feed'} reached {trail.published_overall_score}"
    lines: list[str] = [
        header,
        "=" * len(header),
        f"Snapshot {trail.snapshot_date or 'undated'} | rubric {trail.rubric_version} | "
        f"validator {trail.validator_version or 'unstated'} | "
        f"profile {trail.scoring_profile_id or 'unstated'}",
        "",
    ]
    for cat in trail.categories:
        lines.extend(_category_text(cat))
    lines.append("Overall")
    lines.append("-------")
    if trail.renormalised:
        lines.append(
            f"Measured weight totals {trail.total_weight:g}, so each measured category's "
            "weight is divided by that to sum to 1."
        )
    for cat in trail.categories:
        if cat.measured:
            lines.append(
                f"    {cat.score} x {cat.applied_weight:.4f} = {cat.contribution:.4f}  ({cat.name})"
            )
    lines.append(f"    sum = {trail.recomputed_score:.4f} -> {trail.recomputed_published}")
    lines.append(f"    published = {trail.published_overall_score}")
    lines.append("")
    lines.append(trail.reconciliation_note)
    lines.append("")
    lines.append(_band_sentence(trail))
    lines.append("")
    lines.append(
        "Every weight, deduction and band above is stated in docs/rubric.md. This trail "
        "reads the artifact only; it does not rescore the feed."
    )
    return "\n".join(lines) + "\n"


def render_markdown(trail: ExplainTrail) -> str:
    lines: list[str] = [
        f"# How {trail.agency or 'this feed'} reached {trail.published_overall_score}",
        "",
        f"Snapshot `{trail.snapshot_date or 'undated'}`, rubric `{trail.rubric_version}`, "
        f"validator `{trail.validator_version or 'unstated'}`, "
        f"scoring profile `{trail.scoring_profile_id or 'unstated'}`.",
        "",
    ]
    for cat in trail.categories:
        lines.append(f"## {cat.name}")
        lines.append("")
        if not cat.measured:
            lines.append(f"Rubric weight {cat.raw_weight:.0%}. Not measured this run.")
            lines.extend(["", *(f"{n}" for n in cat.notes), ""])
            continue
        lines.append(
            f"Rubric weight {cat.raw_weight:.0%}, applied weight `{cat.applied_weight:.4f}`, "
            f"score **{cat.score}**."
        )
        lines.append("")
        if cat.deductions:
            lines.append("| Points | Line item | Detail |")
            lines.append("| ---: | --- | --- |")
            for ded in cat.deductions:
                lines.append(f"| {ded.points} | `{ded.label}` | {ded.detail} |")
            lines.append(f"| **{cat.points_total}** | **points listed** | |")
            lines.append("")
        lines.append(f"`100 - score` is {cat.score_delta}.")
        if cat.residual:
            lines.append(f"Left over: {cat.residual} ({cat.residual_reason}).")
        lines.append("")
        for note in cat.notes:
            lines.append(f"{note}")
            lines.append("")
        lines.append(f"Contributes {cat.contribution:.4f} to the overall score.")
        lines.append("")
    lines.append("## Overall")
    lines.append("")
    if trail.renormalised:
        lines.append(
            f"Measured weight totals {trail.total_weight:g}, so each measured category's "
            "weight is divided by that to sum to 1."
        )
        lines.append("")
    for cat in trail.categories:
        if cat.measured:
            lines.append(
                f"- {cat.name}: {cat.score} x {cat.applied_weight:.4f} = {cat.contribution:.4f}"
            )
    lines.append("")
    lines.append(
        f"Sum {trail.recomputed_score:.4f}, published to one decimal as "
        f"{trail.recomputed_published}. The artifact publishes "
        f"{trail.published_overall_score}."
    )
    lines.append("")
    lines.append(trail.reconciliation_note)
    lines.append("")
    lines.append(_band_sentence(trail))
    lines.append("")
    lines.append(
        "Every weight, deduction and band above is stated in `docs/rubric.md`. This trail "
        "reads the artifact only; it does not rescore the feed."
    )
    return "\n".join(lines) + "\n"


def render_json(trail: ExplainTrail) -> str:
    return json.dumps(trail.to_json(), indent=2, sort_keys=True) + "\n"


RENDERERS = {"text": render_text, "markdown": render_markdown, "json": render_json}
