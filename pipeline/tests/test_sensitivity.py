"""Tests for the rubric weight-sensitivity study (FIX-07): perturbed weights,
renormalized rescoring, the grade-churn summary, and the how-to-read surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scorecard_pipeline.score import CATEGORY_WEIGHTS
from scorecard_pipeline.sensitivity import (
    latest_category_scores,
    perturbed_weights,
    rescore,
    weight_sensitivity,
)


def test_perturbed_weights_are_one_at_a_time_and_renormalized() -> None:
    entries = perturbed_weights(0.2)
    # One up and one down perturbation per rubric category.
    assert len(entries) == 2 * len(CATEGORY_WEIGHTS)
    for entry in entries:
        assert sum(entry["weights"].values()) == pytest.approx(1.0, abs=1e-3)
    up = next(e for e in entries if e["category"] == "correctness" and e["direction"] == "up")
    # correctness 0.35 * 1.2 = 0.42, renormalized over the new total 1.07.
    assert up["weights"]["correctness"] == pytest.approx(0.42 / 1.07, abs=1e-4)
    # The other categories move only through renormalization.
    assert up["weights"]["freshness"] == pytest.approx(0.20 / 1.07, abs=1e-4)


def test_rescore_renormalizes_over_measured_categories() -> None:
    # Mirrors build_scorecard: correctness 100 and freshness 0 renormalize to
    # 35/55 and 20/55, so an agency is never punished for an unmeasured category.
    score = rescore({"correctness": 100.0, "freshness": 0.0}, CATEGORY_WEIGHTS)
    assert score == pytest.approx(100 * 35 / 55)


def test_latest_category_scores_takes_newest_entry_and_skips_unscored() -> None:
    index = {
        "agencies": {
            # Histories are not guaranteed sorted on disk; the newest entry wins.
            "a": {
                "history": [
                    {"date": "2026-07-02", "categories": {"correctness": 90.0}},
                    {"date": "2026-07-01", "categories": {"correctness": 10.0}},
                ]
            },
            "never-scored": {"history": []},
            "no-categories": {"history": [{"date": "2026-07-02"}]},
            "unknown-category": {"history": [{"date": "2026-07-02", "categories": {"x": 5.0}}]},
        }
    }
    assert latest_category_scores(index) == {"a": {"correctness": 90.0}}


def test_weight_sensitivity_counts_grade_churn() -> None:
    """A near-boundary agency flips letter under the perturbations that shift
    the balance between its measured categories; a solid-A agency never moves,
    and perturbing an unmeasured category renormalizes away to zero churn."""
    per_agency = {
        # Baseline 100*(35/60) + 50*(25/60) = 79.2, a C sitting near the B edge.
        "edge": {"correctness": 100.0, "completeness": 50.0},
        # A perfect score cannot churn under any renormalized weights.
        "solid": {"correctness": 100.0, "completeness": 100.0},
    }
    study = weight_sensitivity(per_agency, factor=0.2)
    assert study["agency_count"] == 2
    assert len(study["perturbations"]) == 2 * len(CATEGORY_WEIGHTS)
    by = {(p["category"], p["direction"]): p for p in study["perturbations"]}
    # Up-weighting correctness (or down-weighting completeness) lifts "edge"
    # over the B floor: one of two agencies changes letter.
    assert by[("correctness", "up")]["agencies_changed"] == 1
    assert by[("correctness", "up")]["grade_change_pct"] == 50.0
    assert by[("completeness", "down")]["agencies_changed"] == 1
    # The opposite perturbations leave it a C.
    assert by[("correctness", "down")]["agencies_changed"] == 0
    assert by[("completeness", "up")]["agencies_changed"] == 0
    # Freshness is unmeasured for both agencies: its weight renormalizes away,
    # so perturbing it can never change a letter.
    assert by[("freshness", "up")]["agencies_changed"] == 0
    assert by[("freshness", "down")]["agencies_changed"] == 0
    assert study["max_grade_change_pct"] == 50.0


def test_weight_sensitivity_over_no_agencies_is_unavailable() -> None:
    study = weight_sensitivity({})
    assert study["agency_count"] == 0
    assert study["max_grade_change_pct"] is None
    assert study["perturbations"] == []


def test_cli_sensitivity_publishes_the_study(isolated_repo_root: Path) -> None:
    """`scorecard sensitivity` publishes data/artifacts/sensitivity.json with the
    same provenance envelope the other national artifacts carry."""
    import argparse

    from scorecard_pipeline import (
        DATA_LICENSE,
        RUBRIC_VERSION,
        SCHEMA_VERSION,
        SCORING_PROFILE_ID,
    )
    from scorecard_pipeline.cli import _cmd_sensitivity
    from scorecard_pipeline.validate import VALIDATOR_VERSION

    art = isolated_repo_root / "data" / "artifacts"
    art.mkdir(parents=True)
    current = {
        "date": "2026-07-02",
        "score": 79.4,
        "grade": "C",
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": RUBRIC_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "feed_sha256": "sha-edge",
        "categories": {"correctness": 100.0, "freshness": 80.0, "completeness": 50.0},
        "days_until_expiry": 100,
    }
    stale = {**current, "rubric_version": "0.9", "feed_sha256": "sha-stale"}
    (art / "index.json").write_text(
        json.dumps(
            {
                "agencies": {
                    "edge": {"history": [current]},
                    "stale": {"history": [stale]},
                }
            }
        )
    )

    args = argparse.Namespace(factor=0.2, out=None)
    assert _cmd_sensitivity(args, argparse.ArgumentParser()) == 0
    payload = json.loads((art / "sensitivity.json").read_text())
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["rubric_version"] == RUBRIC_VERSION
    assert payload["license"] == DATA_LICENSE
    assert payload["generated_at"]
    assert payload["agency_count"] == 1
    assert payload["comparison"]["eligible_count"] == 1
    assert payload["comparison"]["exclusion_counts"]["rubric_version_mismatch"] == 1
    # The lone near-boundary agency flips under the correctness-up perturbation.
    assert payload["max_grade_change_pct"] == 100.0
    assert len(payload["perturbations"]) == 8


def test_cli_sensitivity_publishes_guarded_empty_study_without_current_cohort(
    isolated_repo_root: Path,
) -> None:
    import argparse

    from scorecard_pipeline.cli import _cmd_sensitivity

    art = isolated_repo_root / "data" / "artifacts"
    art.mkdir(parents=True)
    (art / "index.json").write_text(
        json.dumps(
            {
                "agencies": {
                    "legacy": {
                        "history": [
                            {
                                "date": "2026-07-01",
                                "score": 80,
                                "grade": "B",
                                "categories": {
                                    "correctness": 80,
                                    "freshness": 80,
                                    "completeness": 80,
                                },
                            }
                        ]
                    }
                }
            }
        )
    )

    assert (
        _cmd_sensitivity(argparse.Namespace(factor=0.2, out=None), argparse.ArgumentParser()) == 0
    )
    payload = json.loads((art / "sensitivity.json").read_text())
    assert payload["agency_count"] == 0
    assert payload["comparison"]["eligible_count"] == 0
    assert payload["comparison"]["excluded_count"] == 1
    assert payload["max_grade_change_pct"] is None
    assert payload["perturbations"] == []


def test_guide_sensitivity_note_reads_the_published_study(isolated_repo_root: Path) -> None:
    """The how-to-read page's headline comes from the published sensitivity.json
    (same artifact base the other national data is served from) and degrades to a
    placeholder before the first study has run."""
    from scorecard_pipeline import RUBRIC_VERSION
    from scorecard_pipeline.render_site import _sensitivity_note

    # No study published yet: the placeholder still links the artifact URL.
    note = _sensitivity_note()
    assert "not been published yet" in note
    assert "/data/artifacts/sensitivity.json" in note

    art = isolated_repo_root / "data" / "artifacts"
    art.mkdir(parents=True)
    (art / "sensitivity.json").write_text(
        json.dumps(
            {
                "agency_count": 1200,
                "factor": 0.2,
                "max_grade_change_pct": 3.4,
                "generated_at": "2026-07-02T00:00:00+00:00",
                "comparison": {
                    "eligible_count": 1200,
                    "required_rubric_version": RUBRIC_VERSION,
                    "required_measured_categories": [
                        "correctness",
                        "freshness",
                        "completeness",
                    ],
                },
            }
        )
    )
    note = _sensitivity_note()
    assert "1200 comparison-eligible feed records" in note
    assert "3.4% of letter grades move" in note
    assert "studied 2026-07-02" in note
    assert "/data/artifacts/sensitivity.json" in note
