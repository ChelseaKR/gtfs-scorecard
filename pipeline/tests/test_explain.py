"""`scorecard explain` shows the arithmetic, and says so when it does not add up.

Issue #364. The value of a printed audit trail is entirely in whether a reader
can trust it, so these tests are mostly about the trail's honesty rather than
its formatting: it must refuse a rubric it has no constants for, it must never
silently absorb a leftover, and it must not claim the published overall score
is reproducible from the published category scores when it is not.

Every expected number here is written as a literal. Importing the weights and
bands from `score.py` would make a test that passes whatever those constants
become, which is the opposite of a gate.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.cli import main
from scorecard_pipeline.explain import (
    UnknownRubricVersion,
    build_trail,
    render_json,
    render_markdown,
    render_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "data" / "artifacts"


def _artifact(**overrides: Any) -> dict[str, Any]:
    """A minimal rubric-1.3 artifact whose numbers are checkable by hand.

    correctness 80.0 x (0.35/0.80) + freshness 90.0 x (0.20/0.80)
    + completeness 64.0 x (0.25/0.80)
    = 35.0 + 22.5 + 20.0 = 77.5 exactly, so the fixture never leans on how
    Python rounds a value sitting halfway between two published decimals.
    """
    base: dict[str, Any] = {
        "rubric_version": "1.3",
        "validator_version": "8.0.1",
        "snapshot_date": "2026-09-01",
        "agency": {"id": "example-transit"},
        "scoring_profile": {"id": "gtfs-scorecard-1.3"},
        "overall": {
            "score": 77.5,
            "grade": "C",
            "margin_to_next_band": 2.5,
            "margin_to_lower_band": 7.5,
        },
        "categories": {
            "correctness": {
                "name": "correctness",
                "status": "measured",
                "score": 80.0,
                "weight": 0.35,
                "findings": [
                    {"code": "unused_shape", "severity": "WARNING", "count": 9, "points": 20.0}
                ],
                "details": {"distinct_codes": 1, "instances_by_severity": {"WARNING": 9}},
            },
            "freshness": {
                "name": "freshness",
                "status": "measured",
                "score": 90.0,
                "weight": 0.20,
                "findings": [],
                "details": {"days_until_expiry": 120, "effective_expiry_date": "2027-01-01"},
            },
            "completeness": {
                "name": "completeness",
                "status": "measured",
                "score": 64.0,
                "weight": 0.25,
                "findings": [
                    {
                        "code": "scorecard_wheelchair_boarding_unknown",
                        "severity": "WARNING",
                        "count": 40,
                        "points": 36.0,
                    }
                ],
                "details": {"components": {"contact": 15.0, "wheelchair_stops": 0.0}},
            },
            "realtime": {"name": "realtime", "status": "not_yet_measured", "weight": 0.20},
        },
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# The refusal. This is the criterion the whole module exists to protect.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("declared", ["1.1", "1.2", "0.9", "2.0", ""])
def test_an_artifact_from_another_rubric_is_refused(declared: str) -> None:
    """No fallback to today's constants, for any other version."""
    art = _artifact()
    art["rubric_version"] = declared
    with pytest.raises(UnknownRubricVersion):
        build_trail(art)


def test_the_refusal_names_both_versions() -> None:
    art = _artifact()
    art["rubric_version"] = "1.1"
    with pytest.raises(UnknownRubricVersion, match=r"1\.1"):
        build_trail(art)


def test_the_cli_refuses_an_old_rubric_with_exit_2(tmp_path: Path) -> None:
    """Exit 2 is "could not judge", distinct from a real disagreement."""
    art = _artifact()
    art["rubric_version"] = "1.1"
    path = tmp_path / "old.json"
    path.write_text(json.dumps(art))
    assert main(["explain", str(path)]) == 2


def test_the_cli_refuses_an_unreadable_file_with_exit_2(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    assert main(["explain", str(missing)]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert main(["explain", str(broken)]) == 2


def test_the_cli_prints_a_trail_and_exits_0(tmp_path: Path, capsys: Any) -> None:
    path = tmp_path / "ok.json"
    path.write_text(json.dumps(_artifact()))
    assert main(["explain", str(path)]) == 0
    out = capsys.readouterr().out
    assert "77.5" in out
    assert "example-transit" in out


# --------------------------------------------------------------------------
# The arithmetic.
# --------------------------------------------------------------------------


def test_renormalised_weights_sum_to_one_when_realtime_is_unmeasured() -> None:
    trail = build_trail(_artifact())
    applied = [c.applied_weight for c in trail.categories if c.measured]
    assert len(applied) == 3
    assert round(sum(a for a in applied if a is not None), 6) == 1.0
    assert trail.renormalised is True
    # 0.35 / 0.80, 0.20 / 0.80, 0.25 / 0.80 written out.
    by_name = {c.name: c.applied_weight for c in trail.categories if c.measured}
    assert by_name["correctness"] == pytest.approx(0.4375)
    assert by_name["freshness"] == pytest.approx(0.25)
    assert by_name["completeness"] == pytest.approx(0.3125)


def test_the_unmeasured_category_is_named_and_costs_nothing() -> None:
    trail = build_trail(_artifact())
    realtime = next(c for c in trail.categories if c.name == "realtime")
    assert realtime.measured is False
    assert realtime.applied_weight is None
    assert realtime.contribution is None
    assert any("never counts against the grade" in n for n in realtime.notes)


def test_the_recomputed_total_matches_the_published_score() -> None:
    trail = build_trail(_artifact())
    assert trail.recomputed_score == pytest.approx(77.5)
    assert trail.recomputed_published == 77.5
    assert trail.published_overall_score == 77.5
    assert trail.reconciles is True


def test_all_four_measured_weights_sum_to_one_when_nothing_is_dropped() -> None:
    art = _artifact()
    art["categories"]["realtime"] = {
        "name": "realtime",
        "status": "measured",
        "score": 50.0,
        "weight": 0.20,
        "findings": [],
        "details": {},
    }
    # 80.0*0.35 + 90.0*0.20 + 64.0*0.25 + 50.0*0.20 = 28 + 18 + 16 + 10 = 72.0
    art["overall"]["score"] = 72.0
    trail = build_trail(art)
    assert trail.renormalised is False
    assert trail.recomputed_published == 72.0
    assert trail.reconciles is True


# --------------------------------------------------------------------------
# The residual. A trail that always balances cannot be used to find a defect.
# --------------------------------------------------------------------------


def test_a_category_whose_points_add_up_reports_no_leftover() -> None:
    trail = build_trail(_artifact())
    correctness = next(c for c in trail.categories if c.name == "correctness")
    assert correctness.points_total == 20.0
    assert correctness.score_delta == 20.0
    assert correctness.residual == 0.0
    assert correctness.residual_reason == ""


def test_a_leftover_is_reported_and_never_absorbed() -> None:
    """Sabotage one published point and the trail must show the gap."""
    art = _artifact()
    art["categories"]["correctness"]["findings"][0]["points"] = 12.0
    trail = build_trail(art)
    correctness = next(c for c in trail.categories if c.name == "correctness")
    assert correctness.points_total == 12.0
    assert correctness.score_delta == 20.0
    assert correctness.residual == -8.0
    assert correctness.residual_reason == "unexplained"
    assert "-8.0" in render_text(trail)


def test_freshness_says_it_is_a_curve_rather_than_claiming_a_sum() -> None:
    trail = build_trail(_artifact())
    freshness = next(c for c in trail.categories if c.name == "freshness")
    assert freshness.score_delta == 10.0
    assert freshness.points_total == 0.0
    assert freshness.residual == -10.0
    assert "curve" in freshness.residual_reason


def test_a_small_leftover_is_attributed_to_rounding_not_called_unexplained() -> None:
    art = _artifact()
    art["categories"]["correctness"]["findings"][0]["points"] = 20.1
    trail = build_trail(art)
    correctness = next(c for c in trail.categories if c.name == "correctness")
    assert correctness.residual == pytest.approx(0.1)
    assert correctness.residual_reason == "rounding of each published point to one decimal"


def test_a_correctness_floor_at_zero_is_named_as_the_reason() -> None:
    art = _artifact()
    art["categories"]["correctness"]["score"] = 0.0
    art["categories"]["correctness"]["findings"][0]["points"] = 140.0
    trail = build_trail(art)
    correctness = next(c for c in trail.categories if c.name == "correctness")
    assert correctness.residual == 40.0
    assert "floors at 0" in correctness.residual_reason


# --------------------------------------------------------------------------
# The reconciliation between published category scores and the published total.
# --------------------------------------------------------------------------


def test_a_score_that_cannot_be_rebuilt_from_its_categories_says_so() -> None:
    art = _artifact()
    art["overall"]["score"] = 77.4  # the categories produce 77.5
    trail = build_trail(art)
    assert trail.reconciles is False
    assert "77.5" in trail.reconciliation_note
    assert "77.4" in trail.reconciliation_note
    assert "unrounded category scores" in trail.reconciliation_note
    assert "Recomputing" in render_text(trail)


def test_a_reconciliation_gap_across_a_band_is_called_out() -> None:
    """The case worth shouting about: the two numbers read as different grades."""
    art = _artifact()
    art["categories"]["correctness"]["score"] = 92.0  # 92.0 * 0.4375 = 40.25
    art["categories"]["freshness"]["score"] = 95.0  # 95.0 * 0.25 = 23.75
    art["categories"]["completeness"]["score"] = 51.3  # 51.3 * 0.3125 = 16.03125
    art["overall"]["score"] = 79.9  # the sum is 80.03125, which publishes as 80.0
    art["overall"]["grade"] = "C"
    trail = build_trail(art)
    assert trail.recomputed_published == 80.0
    assert trail.reconciles is False
    assert "crosses a grade band" in trail.reconciliation_note


def test_a_reconciling_artifact_makes_no_band_crossing_claim() -> None:
    """Proof the previous assertion bites: the phrase is not boilerplate."""
    trail = build_trail(_artifact())
    assert trail.reconciles is True
    assert "crosses a grade band" not in trail.reconciliation_note
    assert "crosses a grade band" not in render_text(trail)
    assert "crosses a grade band" not in render_markdown(trail)


# --------------------------------------------------------------------------
# Malformed input fails closed rather than inventing a number.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a.pop("overall"),
        lambda a: a.__setitem__("overall", {"grade": "C"}),
        lambda a: a.__setitem__("overall", []),
        lambda a: a.__setitem__("categories", {}),
        lambda a: a.__setitem__(
            "categories", {"correctness": {"status": "not_yet_measured", "weight": 0.35}}
        ),
        lambda a: a.__setitem__("overall", {"score": None}),
    ],
)
def test_an_artifact_with_nothing_to_explain_is_refused(mutate: Any) -> None:
    art = _artifact()
    mutate(art)
    with pytest.raises(UnknownRubricVersion):
        build_trail(art)


def test_a_finding_without_points_is_skipped_not_scored_as_zero() -> None:
    art = _artifact()
    art["categories"]["correctness"]["findings"].append(
        {"code": "no_points_published", "severity": "INFO", "count": 2}
    )
    trail = build_trail(art)
    correctness = next(c for c in trail.categories if c.name == "correctness")
    labels = [d.label for d in correctness.deductions]
    assert "no_points_published" not in labels
    assert correctness.points_total == 20.0


# --------------------------------------------------------------------------
# Renderers.
# --------------------------------------------------------------------------


def test_every_renderer_produces_the_same_numbers() -> None:
    trail = build_trail(_artifact())
    payload = json.loads(render_json(trail))
    assert payload["overall"]["published"] == 77.5
    assert payload["overall"]["recomputed_published"] == 77.5
    assert payload["overall"]["reconciles"] is True
    for text in (render_text(trail), render_markdown(trail)):
        assert "77.5" in text
        assert "unused_shape" in text
        assert "realtime" in text


def test_the_trail_is_deterministic() -> None:
    art = _artifact()
    assert render_json(build_trail(art)) == render_json(build_trail(copy.deepcopy(art)))


# --------------------------------------------------------------------------
# The published corpus. These are the criteria from the issue, run for real.
# --------------------------------------------------------------------------


def _published_artifacts(limit: int = 400) -> list[Path]:
    if not ARTIFACTS.is_dir():  # pragma: no cover - corpus absent in a slim checkout
        return []
    return sorted(ARTIFACTS.glob("*/latest.json"))[:limit]


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason="published corpus not in this checkout")
def test_the_corpus_is_either_reproducible_or_says_it_is_not() -> None:
    """Never a trail whose bottom line silently disagrees with the artifact.

    Measured on 2026-09-06: 36 of 2,166 rubric-1.3 artifacts (1.66%) do not
    reproduce, every one of them by exactly one rounding step. The point of
    this test is not the count; it is that a non-reproducing artifact is
    reported as such rather than printed as if it added up.
    """
    checked = skipped = flagged = 0
    for path in _published_artifacts():
        try:
            artifact = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):  # pragma: no cover
            continue
        try:
            trail = build_trail(artifact)
        except UnknownRubricVersion:
            skipped += 1
            continue
        checked += 1
        if trail.reconciles:
            assert trail.recomputed_published == trail.published_overall_score
        else:
            flagged += 1
            assert trail.recomputed_published != trail.published_overall_score
            assert "unrounded category scores" in trail.reconciliation_note
            # A gap wider than one rounding step is not this known cause.
            # Rounded before comparing: 57.0 and 57.1 are 0.10000000000000142
            # apart in binary floating point, which is not a wider gap.
            gap = round(abs(trail.recomputed_published - trail.published_overall_score), 6)
            assert gap <= 0.1, f"{path.parent.name} is {gap} away, wider than one rounding step"
    assert checked > 0, "no rubric-1.3 artifact was explained"
    assert skipped > 0, "the refusal path was never exercised against the corpus"
    assert flagged > 0, (
        "no non-reproducing artifact was seen, so the branch that reports one never ran"
    )


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason="published corpus not in this checkout")
def test_no_published_category_leaves_an_unexplained_residual() -> None:
    """Every leftover in the real corpus matches a documented cause.

    This is the property test from the issue, stated so it can fail: if a
    category's published points stop matching its score for a reason this
    module does not know about, the trail says `unexplained` and this fails
    rather than quietly printing a number.
    """
    offenders: list[str] = []
    for path in _published_artifacts():
        try:
            artifact = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):  # pragma: no cover
            continue
        try:
            trail = build_trail(artifact)
        except UnknownRubricVersion:
            continue
        for category in trail.categories:
            if category.residual_reason == "unexplained":
                offenders.append(f"{path.parent.name}/{category.name} left {category.residual}")
    assert not offenders, "unexplained residuals: " + "; ".join(offenders[:10])


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason="published corpus not in this checkout")
def test_every_explained_artifact_renders_in_all_three_formats() -> None:
    rendered = 0
    for path in _published_artifacts(limit=60):
        try:
            trail = build_trail(json.loads(path.read_text()))
        except (UnknownRubricVersion, OSError, json.JSONDecodeError):
            continue
        assert render_text(trail)
        assert render_markdown(trail)
        json.loads(render_json(trail))
        rendered += 1
    assert rendered > 0
