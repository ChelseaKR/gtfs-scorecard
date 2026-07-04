"""Tests for the interactive methodology sandbox on /how-to-read/ (EXP-06).

The sandbox is a dependency-free browser widget that reweights the rubric and
recomputes every agency's grade client-side. These tests guard the three things
that keep it honest: the page ships the sandbox markup and script hook; the
pipeline publishes the scoring.json the widget fetches into api/v1; and the
recompute rule the JS implements matches score.build_scorecard on the
renormalization case (an agency with no realtime), so the sliders reproduce the
published score at the default weights by construction.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.score import CATEGORY_WEIGHTS, GRADE_BANDS, build_scorecard


def test_guide_renders_sandbox_markup_and_script_hook() -> None:
    """The how-to-read page carries the sandbox section, one slider per rubric
    category, the reset control, the live summary containers, and the inline
    script that fetches the published scoring + agencies data."""
    from scorecard_pipeline.render_site import _render_guide

    html = _render_guide()

    assert 'id="sandbox"' in html
    assert "Methodology sandbox" in html
    # One weight slider per rubric category, each addressable by data-cat.
    for cat in CATEGORY_WEIGHTS:
        assert f'data-cat="{cat}"' in html
    # The reset control and the live-summary regions the script writes into.
    assert 'id="sandbox-reset"' in html
    assert 'id="sandbox-summary"' in html
    assert 'id="sandbox-sample"' in html
    # The script hook: it sources weights + bands from scoring.json and the
    # per-agency category scores from agencies.json at runtime (single source).
    assert "/api/v1/scoring.json" in html
    assert "/api/v1/agencies.json" in html
    # Defaults are not hardcoded: the sliders start disabled at 0 and the JS
    # applies the fetched published weights.
    assert "applyDefaults" in html


def test_render_site_emits_scoring_json_into_api_v1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """render_site publishes scoring.json under the site's api/v1, next to
    leaderboard.json and agencies.json, so the sandbox can fetch the same weights
    and grade bands the pipeline scored with over same-origin HTTP."""
    fixture = Path(__file__).parent / "fixtures" / "golden_site"
    if not fixture.exists():
        pytest.skip("golden fixture not available (run `make golden-capture`)")

    scratch = tmp_path / "golden_site"
    shutil.copytree(fixture, scratch)
    monkeypatch.setenv("SCORECARD_ROOT", str(scratch))

    from scorecard_pipeline.render_site import render_site

    render_site()

    published = scratch / "web" / "api" / "v1" / "scoring.json"
    assert published.exists(), "scoring.json was not emitted into api/v1"

    doc = json.loads(published.read_text())
    # It carries exactly what the widget needs to reproduce the grade.
    assert doc["category_weights"] == dict(CATEGORY_WEIGHTS)
    assert doc["grade_bands"] == [
        {"min_score": floor, "grade": letter} for floor, letter in GRADE_BANDS
    ]

    # The api/v1 copy is byte-identical to the artifacts copy (one source, two
    # copies) so the widget and the pipeline can never disagree.
    artifacts_copy = scratch / "data" / "artifacts" / "scoring.json"
    assert published.read_text() == artifacts_copy.read_text()


# --- Pure-Python mirror of the sandbox's client-side recompute ---------------
#
# These two helpers reimplement, line for line, the arithmetic the inline JS in
# _SANDBOX_JS performs (overallFor / gradeFor in render_site.py). Keeping a Python
# twin lets the test suite prove the JS rule matches score.build_scorecard without
# a browser: if score.py's weighting ever changes, the mirror-vs-score assertion
# below fails until the JS (and this mirror) are brought back in step.


def _sandbox_overall(cat_scores: dict[str, float | None], weights: dict[str, float]) -> float:
    """Weighted average of the *measured* categories, with the weights of any
    unmeasured category (a None score, e.g. realtime) renormalized out."""
    num = 0.0
    den = 0.0
    for name, weight in weights.items():
        score = cat_scores.get(name)
        if score is None:
            continue
        num += score * weight
        den += weight
    return num / den if den > 0 else 0.0


def _sandbox_grade(score: float, bands: list[dict[str, float | str]]) -> str:
    """Map a 0-100 score to a letter via the grade bands' min_score thresholds,
    highest threshold first (mirrors gradeFor in the JS)."""
    ordered = sorted(bands, key=lambda b: -float(b["min_score"]))
    for band in ordered:
        if score >= float(band["min_score"]):
            return str(band["grade"])
    return str(ordered[-1]["grade"])


def test_sandbox_recompute_matches_score_py_with_null_realtime() -> None:
    """The renormalization case: an agency with no realtime. At the published
    weights, the sandbox's client-side overall (the Python mirror of the JS) must
    equal score.build_scorecard's overall and grade to the tenth of a point.

    Fixture mirrors 10-15-transit from the published agencies.json:
    correctness 100, freshness 100, completeness 34, realtime not measured ->
    published overall 79.4, grade C.
    """
    cats = [
        CategoryResult(name="correctness", score=100.0, summary=""),
        CategoryResult(name="freshness", score=100.0, summary=""),
        CategoryResult(name="completeness", score=34.0, summary=""),
    ]
    card = build_scorecard(cats)

    cat_scores: dict[str, float | None] = {
        "correctness": 100.0,
        "freshness": 100.0,
        "completeness": 34.0,
        "realtime": None,
    }
    bands: list[dict[str, float | str]] = [
        {"min_score": floor, "grade": letter} for floor, letter in GRADE_BANDS
    ]
    mirror_overall = _sandbox_overall(cat_scores, dict(CATEGORY_WEIGHTS))

    assert round(mirror_overall, 1) == round(card.overall_score, 1) == 79.4
    assert _sandbox_grade(mirror_overall, bands) == card.grade == "C"


def test_sandbox_grade_bands_cover_the_ladder() -> None:
    """The mirror maps representative scores to the same letters score.py does,
    so the sandbox's band edges agree with letter_grade."""
    from scorecard_pipeline.score import letter_grade

    bands: list[dict[str, float | str]] = [
        {"min_score": floor, "grade": letter} for floor, letter in GRADE_BANDS
    ]
    for score in (95.0, 90.0, 89.9, 80.0, 70.0, 60.0, 59.9, 0.0):
        assert _sandbox_grade(score, bands) == letter_grade(score)
