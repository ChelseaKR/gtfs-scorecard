"""Combine category results into an overall grade and the top 3 fixes.

Weights follow the rubric (docs/rubric.md): Correctness 35%, Freshness 20%,
Rider experience completeness 25%, Realtime quality 20%. Categories not yet
measured (Phase 1 ships only the first two) are excluded and the remaining
weights renormalized, so an agency is never punished for a category the
scorecard hasn't computed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import CategoryResult, Finding

CATEGORY_WEIGHTS = {
    "correctness": 0.35,
    "freshness": 0.20,
    "completeness": 0.25,
    "realtime": 0.20,
}

GRADE_BANDS = [(90.0, "A"), (80.0, "B"), (70.0, "C"), (60.0, "D"), (0.0, "F")]

# The overall score is published to one decimal. The letter and the band
# margins have to be derived from that same published number, not from the
# unrounded value behind it: a raw 79.96875 publishes as "80.0", and grading
# the raw value labelled it C while docs/rubric.md and the published
# scoring.json both say 80 is a B. Nine live artifacts carried a letter that
# contradicted their own printed score that way (bus-eireann, express-bus-ie,
# slieve-bloom-coach-tours, cape-ann-transportation-authority-cata-447,
# sandy-area-metro-sam at 80.0/C; regional-transportation-commission-rtc at
# 70.0/D; stan-nancy, ukmerge-public-transport,
# vilnius-district-public-transport at 60.0/F), each with a
# margin_to_next_band of 0.0. The grade bands themselves are unchanged; this
# only makes the letter agree with the number beside it.
PUBLISHED_SCORE_DECIMALS = 1


def published_score(score: float) -> float:
    """The 0-100 overall score exactly as it appears in the artifact.

    Every letter, band token, and margin has to be computed from this, so that
    a reader who applies the published bands to the published score gets the
    published letter.
    """
    return round(score, PUBLISHED_SCORE_DECIMALS)


# A dated, plain-language log of methodology versions, newest first. Surfaced on
# the public "how to read" page and in scoring.json so a reader can tell a score
# change apart from a rule change and see exactly when each rubric version took
# effect. The versions and dates are the repository's own (RUBRIC_VERSION, and
# the commit that introduced each). Prepend a new entry whenever the rubric, its
# weights, deductions, grade bands, or what it measures change.
#
# A VALIDATOR_VERSION bump (validate.py) is a methodology change too: run
# `scorecard canary --candidate-version <X.Y.Z>` (or the validator-canary.yml
# workflow) first, attach its impact report to the bump PR, and prepend the
# dated entry the report generates — "Validator X→Y: median score …, N of M
# sampled agencies changed grade band, driven by <code>." — so the observed
# national effect ships with the change (canary.py, docs/rubric.md "Governed
# upgrades").
METHODOLOGY_CHANGELOG: list[dict[str, str]] = [
    {
        "rubric_version": "1.3",
        "effective_date": "2026-07-24",
        "summary": (
            "The headsign component no longer treats a blank trip_headsign as a "
            "defect when every trip on a route follows one closed stop pattern, "
            "one shape, and one direction. This corrects a false positive found "
            "through maintainer feedback on MRC de Joliette's one-way loop routes. "
            "Routes with multiple directions or patterns retain the check, and "
            "the guidance no longer tells producers to copy route names into "
            "trip_headsign."
        ),
    },
    {
        "rubric_version": "1.2",
        "effective_date": "2026-07-13",
        "summary": (
            "Realtime quality now assesses only the GTFS-Realtime feed kinds an agency "
            "publishes. Unconfigured kinds are neutral, and TripUpdates coverage or "
            "VehiclePositions plausibility enters the score only when that kind is configured. "
            "Finding points use the same measurable-component denominator as the category "
            "score, and a dependent measure drops out when its endpoint produced no successful "
            "sample. "
            "A fixed-corpus replay projected 15 of 31 partial-feed artifacts changing letter "
            "bands; see docs/rubric-impact-1.2.md."
        ),
    },
    {
        "rubric_version": "1.1",
        "effective_date": "2026-06-16",
        "summary": (
            "The most rider-affecting fix is ranked first, and every grade now "
            "carries the validator and rubric version that produced it, so a "
            "trend can tell a feed change apart from a methodology change."
        ),
    },
    {
        "rubric_version": "1.0",
        "effective_date": "2026-06-11",
        "summary": (
            "First published rubric: four weighted categories (Correctness 35%, "
            "Freshness 20%, Rider experience 25%, Realtime 20%), A-F grade bands, "
            "scored on the MobilityData gtfs-validator and anchored to the "
            "California Transit Data Guidelines v4.0."
        ),
    },
]


def methodology_changelog() -> list[dict[str, str]]:
    """The dated methodology changelog, newest first (see METHODOLOGY_CHANGELOG).

    Returned as fresh copies so a caller cannot mutate the module constant.
    """
    return [dict(entry) for entry in METHODOLOGY_CHANGELOG]


def methodology() -> dict[str, Any]:
    """A machine-readable description of how the grade is computed: category
    weights, grade bands, and the correctness severity deductions.

    Published as scoring.json so a consumer or a skeptic can read the weights
    and reproduce or contest the grade, rather than treating the letter as an
    opaque opinion. The narrative version lives in docs/rubric.md.
    """
    from . import RUBRIC_VERSION
    from .metrics import COUNT_MULTIPLIER_TIERS, SEVERITY_BASE_DEDUCTION, WIDESPREAD_MULTIPLIER

    multiplier_tiers: list[dict[str, Any]] = [
        {"max_instances": threshold, "multiplier": mult}
        for threshold, mult in COUNT_MULTIPLIER_TIERS
    ]
    multiplier_tiers.append({"max_instances": None, "multiplier": WIDESPREAD_MULTIPLIER})

    return {
        "rubric_version": RUBRIC_VERSION,
        "overall": (
            "Weighted average of the measured categories. The weights of any "
            "unmeasured category are renormalized, so an agency is never punished "
            "for a category it does not have (for example, realtime)."
        ),
        "category_weights": dict(CATEGORY_WEIGHTS),
        "grade_bands": [{"min_score": floor, "grade": letter} for floor, letter in GRADE_BANDS],
        "correctness": {
            "start_score": 100.0,
            "deduction_per_distinct_notice_code": dict(SEVERITY_BASE_DEDUCTION),
            "count_scaling": (
                "Per distinct notice code, not per instance. The base deduction is "
                "multiplied by a tier based on how many instances the code has, so "
                "one systemic export bug cannot zero the score."
            ),
            "count_multiplier_tiers": multiplier_tiers,
        },
        "source": (
            "Scored on top of the MobilityData gtfs-validator. Full methodology "
            "with citations: docs/rubric.md."
        ),
        "changelog": methodology_changelog(),
    }


@dataclass(frozen=True)
class Scorecard:
    """One agency's complete scored result for one snapshot."""

    overall_score: float
    grade: str
    categories: dict[str, CategoryResult]
    top_fixes: list[Finding]

    def to_json(self) -> dict[str, Any]:
        cats: dict[str, Any] = {}
        for name, weight in CATEGORY_WEIGHTS.items():
            if name in self.categories:
                payload = self.categories[name].to_json()
                payload["weight"] = weight
                cats[name] = payload
            else:
                cats[name] = {
                    "name": name,
                    "status": "not_yet_measured",
                    "weight": weight,
                    "summary": "Not scored yet. Nothing here counts against the grade.",
                }
        score = published_score(self.overall_score)
        margin_up, margin_down = grade_margins(score)
        return {
            "overall": {
                "score": score,
                "grade": self.grade,
                # How close the letter sits to its band edges (FIX-07), so a
                # near-boundary grade reads as "a B, 0.4 points from an A" rather
                # than a verdict. Additive fields; margin_to_next_band is null
                # for an A, which has no higher band.
                "margin_to_next_band": margin_up,
                "margin_to_lower_band": margin_down,
            },
            "categories": cats,
            "top_fixes": [{**f.to_json(), "rank": i + 1} for i, f in enumerate(self.top_fixes)],
        }


def letter_grade(score: float) -> str:
    for floor, letter in GRADE_BANDS:
        if score >= floor:
            return letter
    return "F"


def grade_margins(score: float) -> tuple[float | None, float]:
    """How far ``score`` sits from its grade band's edges: (points up to the
    floor of the next-higher band, points down to the current band's own floor).

    GRADE_BANDS makes 89.9 a B and 90.1 an A; publishing the distance keeps the
    letter honest about that edge (FIX-07): 89.9 is "a B, 0.1 points from an A",
    not just a B. The upward margin is None for an A, which has no higher band.
    Rounded to one decimal, like the published score.
    """
    next_floor: float | None = None
    for floor, _letter in GRADE_BANDS:
        if score >= floor:
            margin_up = None if next_floor is None else round(next_floor - score, 1)
            return margin_up, round(score - floor, 1)
        next_floor = floor
    # Below every band cannot occur from the rubric, but degrade to the F band
    # (its floor and the D floor above it) like letter_grade's F fallback.
    return round(GRADE_BANDS[-2][0] - score, 1), round(score - GRADE_BANDS[-1][0], 1)


# A finding that makes the feed unusable to riders (expired, or an error that
# breaks parsing) must outrank a completeness gap, however many stops the gap
# touches. Tier 0 = the feed is broken or expiring; tier 1 = rider-experience
# gaps; tier 2 = informational. This is what keeps an expired feed's top fix
# "re-export your feed" instead of "set wheelchair_boarding on 300 stops".
_OPERATIONAL_CODES = (
    "scorecard_feed_expired",
    "scorecard_feed_expiring_soon",
    "scorecard_no_expiry_date",
)


def _fix_tier(finding: Finding) -> int:
    if finding.severity == "ERROR" or finding.code in _OPERATIONAL_CODES:
        return 0
    if finding.severity == "WARNING":
        return 1
    return 2


def _fix_priority(finding: Finding) -> tuple[int, float, int]:
    """Order candidate fixes by rider impact first (tier), then by score impact
    and how widespread they are."""
    return (_fix_tier(finding), -finding.deduction, -finding.count)


def build_scorecard(categories: list[CategoryResult]) -> Scorecard:
    """Weight measured categories into an overall 0-100 score and pick the
    three highest-impact fixes (most rider-affecting first)."""
    if len({c.name for c in categories}) != len(categories):
        raise ValueError("duplicate category name in scorecard input")
    measured = {c.name: c for c in categories}
    if not measured:
        raise ValueError("at least one measured category is required")

    total_weight = sum(CATEGORY_WEIGHTS[name] for name in measured)
    overall = sum(c.score * (CATEGORY_WEIGHTS[c.name] / total_weight) for c in measured.values())

    # Only findings that actually move the score are candidate "top fixes"; a
    # zero-deduction note (e.g. an informational finding) is never surfaced as
    # something to fix first.
    all_findings = [f for c in measured.values() for f in c.findings if f.deduction > 0]
    top = sorted(all_findings, key=_fix_priority)[:3]

    return Scorecard(
        overall_score=overall,
        grade=letter_grade(published_score(overall)),
        categories=measured,
        top_fixes=top,
    )
