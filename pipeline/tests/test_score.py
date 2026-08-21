"""Tests for category weighting, grading, and top-fix selection."""

from __future__ import annotations

import pytest

from scorecard_pipeline.metrics import CategoryResult, Finding
from scorecard_pipeline.score import build_scorecard, letter_grade


def category(name: str, score: float, findings: list[Finding] | None = None) -> CategoryResult:
    return CategoryResult(name=name, score=score, summary="", findings=findings or [])


def finding(code: str, deduction: float, count: int = 1, severity: str = "WARNING") -> Finding:
    return Finding(
        code=code,
        severity=severity,
        count=count,
        what="w",
        why="y",
        fix="f",
        effort="e",
        deduction=deduction,
    )


def test_letter_grades() -> None:
    assert letter_grade(95) == "A"
    assert letter_grade(90) == "A"
    assert letter_grade(89.9) == "B"
    assert letter_grade(70) == "C"
    assert letter_grade(65) == "D"
    assert letter_grade(12) == "F"


def test_weights_renormalize_over_measured_categories() -> None:
    # correctness 0.35, freshness 0.20 -> renormalized 35/55 and 20/55
    card = build_scorecard([category("correctness", 100.0), category("freshness", 0.0)])
    assert card.overall_score == pytest.approx(100 * 35 / 55)


def test_unmeasured_categories_marked_not_scored() -> None:
    card = build_scorecard([category("correctness", 80.0)])
    payload = card.to_json()
    assert payload["categories"]["realtime"]["status"] == "not_yet_measured"
    assert payload["categories"]["correctness"]["status"] == "measured"
    assert "score" not in payload["categories"]["realtime"]


def test_top_fixes_ranked_by_impact_then_spread() -> None:
    card = build_scorecard(
        [
            category(
                "correctness",
                60.0,
                [
                    finding("small", deduction=4.0),
                    finding("big", deduction=24.0),
                    finding("wide", deduction=8.0, count=300),
                    finding("narrow", deduction=8.0, count=2),
                ],
            )
        ]
    )
    assert [f.code for f in card.top_fixes] == ["big", "wide", "narrow"]


def test_top_fixes_pull_from_all_categories() -> None:
    card = build_scorecard(
        [
            category("correctness", 90.0, [finding("c1", 4.0)]),
            category("freshness", 50.0, [finding("f1", 15.0)]),
        ]
    )
    assert card.top_fixes[0].code == "f1"


def test_requires_a_measured_category() -> None:
    with pytest.raises(ValueError):
        build_scorecard([])


def test_methodology_exposes_weights_bands_and_deductions() -> None:
    from scorecard_pipeline.score import methodology

    m = methodology()
    assert m["category_weights"]["correctness"] == 0.35
    assert sum(m["category_weights"].values()) == 1.0
    grades = [b["grade"] for b in m["grade_bands"]]
    assert grades == ["A", "B", "C", "D", "F"]
    assert m["correctness"]["deduction_per_distinct_notice_code"]["ERROR"] == 12.0
    assert m["correctness"]["start_score"] == 100.0
    # The count-multiplier thresholds are published so the grade is reproducible.
    tiers = m["correctness"]["count_multiplier_tiers"]
    assert {"max_instances": 5, "multiplier": 1.0} in tiers
    assert {"max_instances": 50, "multiplier": 1.5} in tiers
    assert tiers[-1] == {"max_instances": None, "multiplier": 2.0}


def test_methodology_changelog_is_dated_and_newest_first() -> None:
    """RESEARCH-ROADMAP R9: a methodology changelog with effective dates, so a
    score change is never a silent rule change and is published in scoring.json."""
    from scorecard_pipeline import RUBRIC_VERSION
    from scorecard_pipeline.score import methodology, methodology_changelog

    log = methodology_changelog()
    assert len(log) >= 2
    for entry in log:
        assert entry["rubric_version"]
        # Effective dates are ISO yyyy-mm-dd.
        assert entry["effective_date"][:4].isdigit() and entry["effective_date"].count("-") == 2
        assert entry["summary"]
    # Newest first, and the top entry is the current rubric version.
    dates = [e["effective_date"] for e in log]
    assert dates == sorted(dates, reverse=True)
    assert log[0]["rubric_version"] == RUBRIC_VERSION
    # Returned copies; mutating one must not change the next call.
    log[0]["summary"] = "tampered"
    assert methodology_changelog()[0]["summary"] != "tampered"
    # Published as part of the machine-readable methodology.
    assert methodology()["changelog"] == methodology_changelog()


def test_count_multiplier_matches_published_tiers() -> None:
    from scorecard_pipeline.metrics import _count_multiplier

    assert _count_multiplier(1) == 1.0
    assert _count_multiplier(5) == 1.0
    assert _count_multiplier(6) == 1.5
    assert _count_multiplier(50) == 1.5
    assert _count_multiplier(51) == 2.0


def test_letter_grade_below_zero_is_f() -> None:
    # A negative score can't occur from the rubric, but the grade ladder must
    # still degrade to F rather than fall through to an undefined letter.
    assert letter_grade(-5.0) == "F"


def test_info_finding_is_the_lowest_fix_priority() -> None:
    # Tier ordering must keep an error above an informational note even when the
    # info note carries a (small) deduction, so "fix this first" stays honest.
    card = build_scorecard(
        [
            category(
                "correctness",
                95.0,
                [
                    finding("err", deduction=12.0, severity="ERROR"),
                    finding("info", deduction=0.5, severity="INFO"),
                ],
            )
        ]
    )
    assert [f.code for f in card.top_fixes] == ["err", "info"]


def test_operational_finding_outranks_a_heavier_warning() -> None:
    # An expired feed makes the agency vanish from trip planners; that must be
    # the top fix even when a completeness warning deducts more points.
    card = build_scorecard(
        [
            category(
                "freshness",
                40.0,
                [finding("scorecard_feed_expired", deduction=8.0, severity="WARNING")],
            ),
            category(
                "correctness",
                60.0,
                [finding("big_warning", deduction=24.0, severity="WARNING")],
            ),
        ]
    )
    assert card.top_fixes[0].code == "scorecard_feed_expired"


def test_duplicate_category_name_rejected() -> None:
    with pytest.raises(ValueError):
        build_scorecard([category("correctness", 90.0), category("correctness", 50.0)])


# The tests below were added to kill surviving mutants from the advisory mutmut
# run on score.py (docs/mutation-testing.md). Line/branch coverage was already
# 100%; these pin behaviour the assertions were letting slip.


def test_build_scorecard_sets_the_letter_grade() -> None:
    # letter_grade() is tested in isolation, but nothing asserted that the
    # Scorecard actually carries the grade for its own overall score. A single
    # measured category scoring 85 renormalizes to 85 overall, which is a "B".
    card = build_scorecard([category("correctness", 85.0)])
    assert card.overall_score == pytest.approx(85.0)
    assert card.grade == "B"


def test_zero_deduction_finding_is_never_a_top_fix() -> None:
    # A finding that costs no points (a pure note) must not be offered as one of
    # the "top 3 things to fix", even when it is the only other candidate. This
    # pins the deduction > 0 filter, not merely deduction >= 0.
    card = build_scorecard(
        [
            category(
                "correctness",
                95.0,
                [finding("real", deduction=12.0), finding("note", deduction=0.0)],
            )
        ]
    )
    assert [f.code for f in card.top_fixes] == ["real"]


def test_error_severity_outranks_a_heavier_lower_tier_fix() -> None:
    # An ERROR-severity finding is tier 0 and must be the first fix even when a
    # warning that costs more points is present. Pins the severity == "ERROR"
    # check itself: on points alone the heavier warning would win.
    card = build_scorecard(
        [
            category(
                "correctness",
                50.0,
                [
                    finding("blocking", deduction=4.0, severity="ERROR"),
                    finding("heavy_warning", deduction=24.0, severity="WARNING"),
                ],
            )
        ]
    )
    assert card.top_fixes[0].code == "blocking"


def test_warning_outranks_a_heavier_informational_fix() -> None:
    # A WARNING is tier 1 and must rank above an informational finding (tier 2),
    # even when the info note is (implausibly) assigned more points. Pins the
    # WARNING branch of the tier ladder, which point-ordering alone hid.
    card = build_scorecard(
        [
            category(
                "completeness",
                60.0,
                [
                    finding("warn", deduction=4.0, severity="WARNING"),
                    finding("note", deduction=24.0, severity="INFO"),
                ],
            )
        ]
    )
    assert card.top_fixes[0].code == "warn"


def test_grade_margins_at_the_band_edges() -> None:
    """FIX-07: every scorecard publishes its distance to the grade-band edges,
    so a near-boundary letter reads as "a B, 0.1 points from an A", not a verdict."""
    from scorecard_pipeline.score import grade_margins

    assert grade_margins(89.9) == (0.1, 9.9)
    # An A has no higher band: the upward margin is None (null in JSON).
    assert grade_margins(95) == (None, 5.0)
    # The boundary itself belongs to the upper band, same as letter_grade.
    assert letter_grade(90.0) == "A"
    assert grade_margins(90.0) == (None, 0.0)
    # The F band's next band up is D at 60.
    assert grade_margins(12) == (48.0, 12.0)


def test_grade_margins_are_published_to_one_decimal() -> None:
    # Margins are rounded like the published score, so a card never shows more
    # precision than the number it sits next to.
    from scorecard_pipeline.score import grade_margins

    assert grade_margins(84.26) == (5.7, 4.3)


def test_grade_margins_below_every_band_degrade_to_the_f_band() -> None:
    # A negative score can't come out of the rubric, but grade_margins must
    # degrade the same way letter_grade does rather than fall off the ladder:
    # measure up to the D floor above F, and down to F's own floor.
    from scorecard_pipeline.score import grade_margins

    assert letter_grade(-5.25) == "F"
    assert grade_margins(-5.25) == (65.2, -5.2)


def test_to_json_carries_grade_margins() -> None:
    # A single measured category renormalizes to its own score, so 89.9 overall.
    overall = build_scorecard([category("correctness", 89.9)]).to_json()["overall"]
    assert overall["grade"] == "B"
    assert overall["margin_to_next_band"] == 0.1
    assert overall["margin_to_lower_band"] == 9.9
    # An A's upward margin is published as an explicit null, never omitted.
    top = build_scorecard([category("correctness", 95.0)]).to_json()["overall"]
    assert top["margin_to_next_band"] is None
    assert top["margin_to_lower_band"] == 5.0


def test_published_letter_agrees_with_the_published_score() -> None:
    """The letter a reader sees must be the letter the printed score earns.

    Real regression: five agencies published "Grade C * 80.0 / 100" because the
    raw score was 79.96875 -- rounded up for display, graded down. A consumer
    applying the bands in the published scoring.json to the published score got
    a different letter than the artifact carried.
    """
    from scorecard_pipeline.score import GRADE_BANDS

    # Category scores chosen so the weighted overall lands just under a band
    # floor and rounds onto it: 35% * 79.9 + 20% * 80.1 + 25% * 80.0 + 20% * 80.0
    # = 79.965, which prints as 80.0.
    card = build_scorecard(
        [
            category("correctness", 79.9),
            category("freshness", 80.1),
            category("completeness", 80.0),
            category("realtime", 80.0),
        ]
    )
    assert card.overall_score < 80.0
    payload = card.to_json()["overall"]
    assert payload["score"] == 80.0
    assert payload["grade"] == "B"
    # And the margins are measured from the same number, so a grade is never
    # reported as sitting 0.0 points from the band it is already in.
    assert payload["margin_to_lower_band"] == 0.0
    assert payload["margin_to_next_band"] == pytest.approx(10.0)

    # The property, stated generally: applying the published bands to the
    # published score always reproduces the published letter.
    for raw in (59.96, 59.999, 69.98, 79.96875, 89.97, 90.04, 100.0, 0.0, 42.42):
        one = build_scorecard([category("correctness", raw)]).to_json()["overall"]
        expected = next(letter for floor, letter in GRADE_BANDS if one["score"] >= floor)
        assert one["grade"] == expected, (raw, one)
