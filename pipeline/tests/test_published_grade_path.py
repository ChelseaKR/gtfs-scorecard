"""Every letter grade outside score.py is derived from the published score.

`score.py` records the bug this exists to prevent, in its own words: a raw
79.96875 publishes as "80.0", and grading the raw value labelled it C while
`docs/rubric.md` and the published `scoring.json` both say 80 is a B. Nine live
artifacts carried a letter that contradicted their own printed score.

`publish._validate_published_overall` refuses to write a per-agency artifact
whose letter disagrees with its score. That guard is real and it is narrow: it
runs inside `publish()`. `sensitivity.py` reimplements its own scoring and
grading path and `cli._cmd_sensitivity` writes `sensitivity.json` directly, so
the published weight-sensitivity study graded the raw weighted average and the
guard never saw it (#310).

Two checks here, because the arithmetic fix alone leaves the shape intact:

* an arithmetic one, that the study's letters agree with what publish would
  validate at a band edge;
* a structural one, that no module outside `score.py` calls `letter_grade` on
  anything but a `published_score(...)` result, so the next module to grade a
  score cannot reintroduce the split quietly.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scorecard_pipeline.score import (
    CATEGORY_WEIGHTS,
    letter_grade,
    published_overall,
    published_score,
)
from scorecard_pipeline.sensitivity import published_letter, rescore, weight_sensitivity

SRC = Path(__file__).resolve().parents[1] / "src" / "scorecard_pipeline"

# A raw score that publishes as 80.0 and grades as C before rounding. score.py
# names this exact value as the one that shipped nine contradictory artifacts.
BAND_EDGE = 79.96875


def test_the_band_edge_value_still_splits_the_two_paths() -> None:
    """Guard the guard: if this stops splitting, the tests below prove nothing."""
    assert letter_grade(BAND_EDGE) == "C"
    assert published_overall(BAND_EDGE)["grade"] == "B"


def test_published_letter_grades_what_the_reader_sees() -> None:
    assert published_letter({"correctness": BAND_EDGE}, CATEGORY_WEIGHTS) == "B"
    assert (
        published_letter({"correctness": BAND_EDGE}, CATEGORY_WEIGHTS)
        == (published_overall(published_score(BAND_EDGE))["grade"])
    )


def test_the_study_counts_churn_against_the_published_baseline() -> None:
    """A feed sitting on a band edge is compared from the letter it publishes.

    correctness 91.379…, freshness 60 renormalizes to exactly 79.96875, which
    publishes as 80.0 / B. Moving the correctness weight up takes it to 81.3,
    still a B, so nothing changed. Moving it down takes it to 78.3, a C, so
    that one changed. Grading the raw baseline as C reverses both answers.
    """
    per_agency = {"edge-case-transit": {"correctness": 91.37946428571429, "freshness": 60.0}}
    assert rescore(per_agency["edge-case-transit"], CATEGORY_WEIGHTS) == BAND_EDGE

    study = weight_sensitivity(per_agency)
    by_key = {
        (p["category"], p["direction"]): p["agencies_changed"] for p in study["perturbations"]
    }
    assert by_key[("correctness", "up")] == 0
    assert by_key[("correctness", "down")] == 1


def _letter_grade_calls(path: Path) -> list[tuple[int, ast.expr | None]]:
    """Every ``letter_grade(...)`` call in a module, with its first argument."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls: list[tuple[int, ast.expr | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "letter_grade":
            continue
        calls.append((node.lineno, node.args[0] if node.args else None))
    return calls


def _grades_a_raw_score(argument: ast.expr | None) -> bool:
    """True unless the argument is a ``published_score(...)`` result."""
    if argument is None:
        return True
    return not (
        isinstance(argument, ast.Call)
        and isinstance(argument.func, ast.Name)
        and argument.func.id == "published_score"
    )


def test_no_module_outside_score_grades_a_raw_score() -> None:
    """The structural half: the split cannot be reintroduced silently."""
    offenders = [
        f"{path.name}:{line}"
        for path in sorted(SRC.glob("*.py"))
        if path.name != "score.py"
        for line, argument in _letter_grade_calls(path)
        if _grades_a_raw_score(argument)
    ]
    assert not offenders, (
        "letter_grade() called on something other than published_score(...) at "
        + ", ".join(offenders)
        + ". Round through published_score first, or the letter can contradict "
        "the score printed beside it."
    )


def test_the_structural_check_recognises_a_raw_call(tmp_path: Path) -> None:
    """Proof it bites: a raw call is reported, a published one is not."""
    raw = tmp_path / "raw.py"
    raw.write_text("x = letter_grade(rescore(cats, weights))\n", encoding="utf-8")
    wrapped = tmp_path / "wrapped.py"
    wrapped.write_text(
        "x = letter_grade(published_score(rescore(cats, weights)))\n", encoding="utf-8"
    )
    assert [_grades_a_raw_score(a) for _, a in _letter_grade_calls(raw)] == [True]
    assert [_grades_a_raw_score(a) for _, a in _letter_grade_calls(wrapped)] == [False]


def test_a_bare_letter_grade_call_is_reported(tmp_path: Path) -> None:
    module = tmp_path / "bare.py"
    module.write_text("x = letter_grade()\n", encoding="utf-8")
    assert [_grades_a_raw_score(a) for _, a in _letter_grade_calls(module)] == [True]
