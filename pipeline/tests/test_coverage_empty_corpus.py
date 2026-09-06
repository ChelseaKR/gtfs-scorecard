"""An empty corpus is not fully covered; it is not measured.

``plain_language_coverage`` computed both shares with ``round(part / whole * 100,
1) if whole else 100.0``, and its docstring called that "vacuously fully
covered". 100.0% is the answer a fully curated corpus gives. It was also the
answer for a corpus with no codes in it, and for a corpus whose codes reported
no instances — and ``scorecard coverage --save`` then wrote that 100.0 to
``coverage-baseline.json`` as the number every later week is compared against,
so the first real measurement reads as a drop from a figure nobody measured.
"""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.findings_national import coverage_regression, plain_language_coverage


def _rollup(by_code: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"prevalence_by_code": by_code}


def test_an_empty_corpus_has_no_coverage_to_report() -> None:
    coverage = plain_language_coverage(_rollup({}))
    assert coverage["distinct_code_coverage"] is None
    assert coverage["instance_weighted_coverage"] is None
    assert coverage["total_codes"] == 0
    assert coverage["curated_codes"] == 0


def test_codes_with_no_instances_have_no_instance_weighted_share() -> None:
    """Distinct-code coverage is measurable here; the instance share is not."""
    coverage = plain_language_coverage(
        _rollup({"scorecard_expired_calendar": {"instances": 0, "agencies": 0}})
    )
    assert coverage["distinct_code_coverage"] == 100.0
    assert coverage["instance_weighted_coverage"] is None


def test_a_measured_corpus_is_unchanged() -> None:
    """The narrowness test: real shares still come out the same."""
    coverage = plain_language_coverage(
        _rollup(
            {
                "scorecard_expired_calendar": {"instances": 30, "agencies": 3},
                "some_uncurated_code": {"instances": 10, "agencies": 1},
            }
        )
    )
    assert coverage["distinct_code_coverage"] == 50.0
    assert coverage["instance_weighted_coverage"] == 75.0
    assert [q["code"] for q in coverage["uncurated_queue"]] == ["some_uncurated_code"]


def test_a_regression_is_never_reported_against_an_unmeasured_number() -> None:
    measured = {"instance_weighted_coverage": 80.0}
    unmeasured = {"instance_weighted_coverage": None}

    # Nothing measured now: there is no current reading to call a drop.
    assert coverage_regression(measured, unmeasured) is None
    # Nothing measured then: the baseline is not a bar to fall below.
    assert coverage_regression(unmeasured, measured) is None
    # A baseline that never carried the field is not a baseline of zero.
    assert coverage_regression({"as_of": "2026-01-01"}, measured) is None


def test_a_real_drop_is_still_reported() -> None:
    """The narrowness test: the governance loop still fires when it should."""
    message = coverage_regression(
        {"instance_weighted_coverage": 90.0, "as_of": "2026-08-01"},
        {"instance_weighted_coverage": 80.0},
    )
    assert message is not None
    assert "COVERAGE DROP" in message
    assert "80.0" in message and "90.0" in message


# ------------------------------------------------- what the page and CLI say


def test_the_problems_page_does_not_print_a_share_it_does_not_have() -> None:
    from scorecard_pipeline.render_site import _coverage_shares

    measured = _coverage_shares(
        {"distinct_code_coverage": 50.0, "instance_weighted_coverage": 75.0}
    )
    assert "<strong>50.0%</strong> of codes and <strong>75.0%</strong> of all finding" in measured

    partly = _coverage_shares({"distinct_code_coverage": 100.0, "instance_weighted_coverage": None})
    assert "not measured" in partly
    assert "None%" not in partly


def test_the_baseline_is_never_overwritten_with_an_unmeasured_reading(
    tmp_path: Any, capsys: Any, monkeypatch: Any
) -> None:
    """--save must not replace a real bar with a reading nobody took."""
    import argparse
    import datetime as dt
    import json

    from scorecard_pipeline import cli, config

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    baseline = artifacts / "coverage-baseline.json"
    baseline.write_text(json.dumps({"as_of": "2026-08-01", "instance_weighted_coverage": 90.0}))
    monkeypatch.setattr(config, "artifacts_dir", lambda: artifacts)

    args = argparse.Namespace(save=True, date=dt.date(2026, 9, 5))
    assert cli._cmd_coverage_check(args, argparse.ArgumentParser()) == 0
    out = capsys.readouterr().out
    assert "NOT MEASURED" in out
    assert "NOT SAVED" in out
    assert json.loads(baseline.read_text())["instance_weighted_coverage"] == 90.0
