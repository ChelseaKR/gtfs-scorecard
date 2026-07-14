"""Tests for the national problem-prevalence rollup (findings_national.py)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.findings_national import agency_findings, national_problems


def _artifact(*finding_codes: str, status: str = "measured") -> dict[str, Any]:
    findings = [
        {"code": c, "severity": "WARNING", "count": 5, "what": f"what {c}", "fix": f"fix {c}"}
        for c in finding_codes
    ]
    return {"categories": {"correctness": {"status": status, "findings": findings}}}


def test_agency_findings_dedupes_by_code_across_categories() -> None:
    art = {
        "categories": {
            "correctness": {"status": "measured", "findings": [{"code": "x", "count": 3}]},
            "completeness": {
                "status": "measured",
                "findings": [{"code": "x", "count": 9}, {"code": "y", "count": 1}],
            },
        }
    }
    codes = {f["code"] for f in agency_findings(art)}
    assert codes == {"x", "y"}


def test_agency_findings_skips_unmeasured() -> None:
    assert agency_findings(_artifact("a", status="not_yet_measured")) == []


def test_national_problems_counts_and_prevalence() -> None:
    per_agency = [
        agency_findings(_artifact("common", "rare")),
        agency_findings(_artifact("common")),
        agency_findings(_artifact("common")),
        agency_findings(_artifact("scorecard_thing")),
    ]
    nat = national_problems(per_agency, total_feed_records=4)
    by_code = {p["code"]: p for p in nat["problems"]}
    assert by_code["common"]["agencies"] == 3
    assert by_code["common"]["feed_records"] == 3
    assert by_code["common"]["prevalence_pct"] == 75.0
    assert by_code["common"]["instances"] == 15  # 5 per agency x 3
    assert by_code["rare"]["agencies"] == 1
    # Most widespread ranks first.
    assert nat["problems"][0]["code"] == "common"
    assert nat["distinct_problems"] == 3
    assert nat["comparison_feed_record_count"] == 4


def test_source_classification() -> None:
    nat = national_problems([agency_findings(_artifact("scorecard_x", "E002"))], total_agencies=1)
    src = {p["code"]: p["source"] for p in nat["problems"]}
    assert src["scorecard_x"] == "scorecard"
    assert src["E002"] == "validator"


def test_prevalence_uses_total_agencies_not_only_affected() -> None:
    # 1 agency has the problem out of 10 tracked -> 10%, not 100%.
    nat = national_problems([agency_findings(_artifact("x"))], total_agencies=10)
    assert nat["problems"][0]["prevalence_pct"] == 10.0
    assert nat["prevalence_by_code"]["x"]["prevalence_pct"] == 10.0


def test_top_caps_problem_list_but_not_prevalence_map() -> None:
    per_agency = [agency_findings(_artifact(*[f"c{i}" for i in range(30)]))]
    nat = national_problems(per_agency, total_agencies=1, top=5)
    assert len(nat["problems"]) == 5
    assert len(nat["prevalence_by_code"]) == 30


def test_empty_input_is_safe() -> None:
    nat = national_problems([], total_agencies=0)
    assert nat["distinct_problems"] == 0
    assert nat["problems"] == []
    assert nat["prevalence_by_code"] == {}
    # This input has findings only, with no agency identity/location to group.
    assert "countries" not in nat
