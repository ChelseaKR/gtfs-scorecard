"""Tests for plain-language coverage governance: the coverage metric over the
national rollup (findings_national.plain_language_coverage) and the readability
gate script (pipeline/scripts/check_readability.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from scorecard_pipeline.findings_national import (
    agency_findings,
    national_problems,
    plain_language_coverage,
)
from scorecard_pipeline.notices import TRANSLATIONS, Translation


def _load_readability() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_readability.py"
    spec = importlib.util.spec_from_file_location("check_readability", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


readability = _load_readability()


def _artifact(*findings: tuple[str, int]) -> dict[str, Any]:
    return {
        "categories": {
            "correctness": {
                "status": "measured",
                "findings": [{"code": c, "count": n} for c, n in findings],
            }
        }
    }


CURATED = "unused_stop"  # a code with an entry in notices.TRANSLATIONS
assert CURATED in TRANSLATIONS


# ---- coverage metric ---------------------------------------------------------


def test_coverage_counts_curated_and_uncurated() -> None:
    rollup = national_problems(
        [
            agency_findings(_artifact((CURATED, 3), ("made_up_notice", 6))),
            agency_findings(_artifact(("made_up_notice", 1))),
        ],
        total_agencies=2,
    )
    cov = plain_language_coverage(rollup)
    assert cov["total_codes"] == 2
    assert cov["curated_codes"] == 1
    assert cov["distinct_code_coverage"] == 50.0
    # 3 curated instances of 10 total.
    assert cov["instance_weighted_coverage"] == 30.0


def test_scorecard_prefix_counts_as_curated() -> None:
    rollup = national_problems(
        [agency_findings(_artifact(("scorecard_no_rt_feed", 4)))], total_agencies=1
    )
    cov = plain_language_coverage(rollup)
    assert cov["curated_codes"] == 1
    assert cov["distinct_code_coverage"] == 100.0
    assert cov["instance_weighted_coverage"] == 100.0
    assert cov["uncurated_queue"] == []


def test_uncurated_queue_ranked_by_instances_with_agencies() -> None:
    rollup = national_problems(
        [
            agency_findings(_artifact(("rare_notice", 2), ("loud_notice", 50))),
            agency_findings(_artifact(("loud_notice", 50), (CURATED, 9))),
        ],
        total_agencies=2,
    )
    queue = plain_language_coverage(rollup)["uncurated_queue"]
    assert queue == [
        {"code": "loud_notice", "instances": 100, "agencies": 2},
        {"code": "rare_notice", "instances": 2, "agencies": 1},
    ]


def test_queue_ties_break_by_agencies_then_code() -> None:
    rollup = national_problems(
        [
            agency_findings(_artifact(("b_notice", 5), ("a_notice", 5))),
            agency_findings(_artifact(("b_notice", 5))),
            agency_findings(_artifact(("a_notice", 5))),
        ],
        total_agencies=3,
    )
    queue = plain_language_coverage(rollup)["uncurated_queue"]
    # Equal instances (10 each) and equal agencies (2 each): code order decides.
    assert [q["code"] for q in queue] == ["a_notice", "b_notice"]


def test_empty_rollup_is_vacuously_covered() -> None:
    cov = plain_language_coverage(national_problems([], total_agencies=0))
    assert cov["total_codes"] == 0
    assert cov["curated_codes"] == 0
    assert cov["distinct_code_coverage"] == 100.0
    assert cov["instance_weighted_coverage"] == 100.0
    assert cov["uncurated_queue"] == []


def test_rollup_missing_prevalence_map_is_safe() -> None:
    cov = plain_language_coverage({})
    assert cov["total_codes"] == 0
    assert cov["uncurated_queue"] == []


def test_prevalence_map_carries_instances_for_weighting() -> None:
    rollup = national_problems([agency_findings(_artifact((CURATED, 7)))], total_agencies=1)
    assert rollup["prevalence_by_code"][CURATED]["instances"] == 7


# ---- readability gate --------------------------------------------------------


def test_readability_passes_plain_text() -> None:
    assert readability.check_text("t", "The feed ends soon. Publish a new one now.") == []


def test_readability_flags_long_sentences() -> None:
    text = " ".join(["word"] * 30) + "."
    fails = readability.check_text("t.what", text)
    assert any("average sentence length" in f for f in fails)
    assert all(f.startswith("t.what:") for f in fails)


def test_readability_flags_dense_polysyllabic_prose() -> None:
    text = (
        "Organizational normalization of interoperability documentation "
        "necessitates comprehensive administrative reconciliation."
    )
    fails = readability.check_text("t.why", text)
    assert any("Flesch reading ease" in f for f in fails)


def test_syllable_heuristic_basics() -> None:
    assert readability.syllables("bus") == 1
    assert readability.syllables("rider") == 2
    # Silent final e is not counted as its own syllable.
    assert readability.syllables("time") == 1
    # Never below one, even with no vowels.
    assert readability.syllables("txt") == 1


def test_empty_text_never_fails_thresholds() -> None:
    assert readability.flesch("") == 100.0
    assert readability.avg_sentence_words("") == 0.0
    assert readability.check_text("t", "") == []


def test_shipped_translations_clear_the_gate(capsys: pytest.CaptureFixture[str]) -> None:
    assert readability.main() == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out


def test_gate_exits_nonzero_with_diagnostics(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = Translation(
        what=(
            "Institutionalized organizational interoperability necessitates "
            "extraordinarily comprehensive documentation harmonization"
        ),
        why="ok",
        fix="ok",
        effort="ok",
    )
    monkeypatch.setattr(readability, "TRANSLATIONS", {"bad_code": bad})
    assert readability.main() == 1
    out = capsys.readouterr().out
    assert "bad_code.what" in out
    assert "FAILURES" in out


# ---- weekly coverage-drop advisory (FIX-08) ---------------------------------


def _coverage(instance_weighted: float) -> dict[str, Any]:
    return {
        "distinct_code_coverage": 50.0,
        "instance_weighted_coverage": instance_weighted,
        "curated_codes": 1,
        "total_codes": 2,
        "uncurated_queue": [],
    }


def test_regression_is_silent_with_no_baseline() -> None:
    from scorecard_pipeline.findings_national import coverage_regression

    assert coverage_regression(None, _coverage(33.3)) is None


def test_regression_is_silent_when_coverage_holds_or_rises() -> None:
    from scorecard_pipeline.findings_national import coverage_regression

    baseline = {"instance_weighted_coverage": 33.3, "as_of": "2026-07-06"}
    assert coverage_regression(baseline, _coverage(33.3)) is None
    assert coverage_regression(baseline, _coverage(40.0)) is None


def test_regression_names_both_numbers_and_the_baseline_date() -> None:
    from scorecard_pipeline.findings_national import coverage_regression

    message = coverage_regression(
        {"instance_weighted_coverage": 40.0, "as_of": "2026-07-06"}, _coverage(33.3)
    )
    assert message is not None
    assert message.startswith("COVERAGE DROP")
    assert "33.3%" in message and "40.0%" in message and "2026-07-06" in message


def _write_latest(agency_id: str, *findings: tuple[str, int]) -> None:
    from scorecard_pipeline.config import artifacts_dir

    agency_dir = artifacts_dir() / agency_id
    agency_dir.mkdir(parents=True, exist_ok=True)
    (agency_dir / "latest.json").write_text(
        __import__("json").dumps(
            {"agency": {"id": agency_id, "name": agency_id}, **_artifact(*findings)}
        )
    )


def _write_registry() -> None:
    from scorecard_pipeline.config import repo_root

    repo_root().mkdir(parents=True, exist_ok=True)
    (repo_root() / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: a-one\n"
        "    name: A One\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )


def test_coverage_check_saves_a_baseline_and_warns_on_a_drop(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End to end through the CLI: an all-curated corpus saves a 100% baseline,
    then an uncurated flood in the next run trips the advisory (exit stays 0 —
    the check warns, it never blocks)."""
    import json

    from scorecard_pipeline.cli import main
    from scorecard_pipeline.config import artifacts_dir

    _write_registry()
    _write_latest("a-one", (CURATED, 5))
    assert main(["coverage-check", "--save", "--date", "2026-07-06"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("OK")
    baseline = json.loads((artifacts_dir() / "coverage-baseline.json").read_text())
    assert baseline == {
        "as_of": "2026-07-06",
        "distinct_code_coverage": 100.0,
        "instance_weighted_coverage": 100.0,
    }

    _write_latest("b-two", ("made_up_notice", 50))
    assert main(["coverage-check", "--date", "2026-07-13"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("COVERAGE DROP")
    assert "2026-07-06" in out
    # Preview mode did not consume the baseline.
    assert json.loads((artifacts_dir() / "coverage-baseline.json").read_text()) == baseline


def test_coverage_check_skips_reserved_dirs_and_unreadable_artifacts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scorecard_pipeline.cli import main
    from scorecard_pipeline.config import artifacts_dir

    _write_registry()
    _write_latest("a-one", (CURATED, 2))
    (artifacts_dir() / "rollups").mkdir(parents=True, exist_ok=True)
    (artifacts_dir() / "rollups" / "latest.json").write_text("{}")
    broken = artifacts_dir() / "b-two"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "latest.json").write_text("{not json")
    assert main(["coverage-check"]) == 0
    out = capsys.readouterr().out
    assert "1 scored agencies" in out
