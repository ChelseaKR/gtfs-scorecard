"""Tests for the snapshot-to-snapshot feed diff."""

from __future__ import annotations

from typing import Any

import pytest

from scorecard_pipeline.feeddiff import (
    compare_contract,
    diff_artifacts,
    diff_json,
    findings_no_longer_measured,
    render_diff_markdown,
    render_diff_text,
)


def _artifact(
    *,
    date: str = "2026-06-12",
    grade: str = "B",
    score: float = 82.0,
    findings: list[dict[str, Any]] | None = None,
    sha256: str = "aaa",
    size_bytes: int = 1000,
    days_until_expiry: int | None = 90,
) -> dict[str, Any]:
    return {
        "snapshot_date": date,
        "overall": {"grade": grade, "score": score},
        "feed": {"sha256": sha256, "size_bytes": size_bytes},
        "categories": {
            "correctness": {
                "status": "measured",
                "score": 90.0,
                "findings": findings or [],
            },
            "freshness": {
                "status": "measured",
                "score": 80.0,
                "details": {"days_until_expiry": days_until_expiry},
                "findings": [],
            },
        },
    }


def _finding(code: str, count: int, severity: str = "WARNING", what: str = "") -> dict[str, Any]:
    return {"code": code, "count": count, "severity": severity, "what": what or f"{code} happened"}


def test_new_finding_is_detected() -> None:
    prev = _artifact(findings=[])
    curr = _artifact(findings=[_finding("stop_too_far", 3)])
    diff = diff_artifacts(prev, curr)
    assert [c.code for c in diff.new] == ["stop_too_far"]
    assert diff.new[0].curr_count == 3
    assert diff.new[0].prev_count is None
    assert not diff.resolved


def test_resolved_finding_is_detected() -> None:
    prev = _artifact(findings=[_finding("missing_headsign", 5)])
    curr = _artifact(findings=[])
    diff = diff_artifacts(prev, curr)
    assert [c.code for c in diff.resolved] == ["missing_headsign"]
    assert diff.resolved[0].prev_count == 5
    assert diff.resolved[0].curr_count is None
    assert not diff.new


def test_changed_count_is_detected() -> None:
    prev = _artifact(findings=[_finding("stop_too_far", 3)])
    curr = _artifact(findings=[_finding("stop_too_far", 8)])
    diff = diff_artifacts(prev, curr)
    assert not diff.new and not diff.resolved
    assert len(diff.changed) == 1
    assert (diff.changed[0].prev_count, diff.changed[0].curr_count) == (3, 8)


def test_unchanged_count_is_not_reported() -> None:
    f = [_finding("stop_too_far", 3)]
    diff = diff_artifacts(_artifact(findings=f), _artifact(findings=list(f)))
    assert not diff.changed and not diff.new and not diff.resolved


def test_feed_bytes_change_detected_from_sha() -> None:
    prev = _artifact(sha256="aaa", size_bytes=1000)
    curr = _artifact(sha256="bbb", size_bytes=2024)
    diff = diff_artifacts(prev, curr)
    assert diff.feed_bytes_changed is True
    assert diff.size_delta == 1024


def test_same_sha_is_not_a_feed_change() -> None:
    diff = diff_artifacts(_artifact(sha256="aaa"), _artifact(sha256="aaa"))
    assert diff.feed_bytes_changed is False


def test_grade_drop_and_score_delta() -> None:
    prev = _artifact(grade="B", score=82.0)
    curr = _artifact(grade="C", score=74.5)
    diff = diff_artifacts(prev, curr)
    assert diff.grade_moved is True
    assert diff.grade_dropped is True
    assert diff.score_delta == -7.5


def test_grade_rise_is_not_a_drop() -> None:
    diff = diff_artifacts(_artifact(grade="C", score=72.0), _artifact(grade="B", score=83.0))
    assert diff.grade_moved is True
    assert diff.grade_dropped is False
    assert diff.score_delta == 11.0


def test_expiry_delta() -> None:
    diff = diff_artifacts(_artifact(days_until_expiry=40), _artifact(days_until_expiry=10))
    assert diff.expiry_delta == -30


def test_identical_snapshots_have_no_changes() -> None:
    a = _artifact(findings=[_finding("x", 1)])
    diff = diff_artifacts(a, dict(a))
    assert diff.has_changes is False


def test_new_findings_sorted_by_severity() -> None:
    curr = _artifact(
        findings=[
            _finding("info_one", 100, severity="INFO"),
            _finding("err_one", 1, severity="ERROR"),
            _finding("warn_one", 2, severity="WARNING"),
        ]
    )
    diff = diff_artifacts(_artifact(findings=[]), curr)
    assert [c.code for c in diff.new] == ["err_one", "warn_one", "info_one"]


def test_unmeasured_category_findings_are_ignored() -> None:
    prev = _artifact(findings=[])
    curr = _artifact(findings=[])
    curr["categories"]["realtime"] = {
        "status": "not_yet_measured",
        "findings": [_finding("rt_problem", 9)],
    }
    diff = diff_artifacts(prev, curr)
    assert diff.new == []


def _contract_artifact(
    *,
    rubric: str = "1.3",
    profile_id: str = "gtfs-scorecard-1.3",
    validator: str = "8.0.1",
    reader_profile: str = "raw-v1",
    realtime_status: str | None = None,
    realtime_findings: list[dict[str, Any]] | None = None,
    findings: list[dict[str, Any]] | None = None,
    grade: str = "B",
    score: float = 82.0,
    date: str = "2026-06-12",
) -> dict[str, Any]:
    """An artifact carrying the full producer contract the diff gates on."""
    categories: dict[str, Any] = {
        "correctness": {"status": "measured", "score": 90.0, "findings": findings or []},
        "freshness": {
            "status": "measured",
            "score": 80.0,
            "details": {"days_until_expiry": 90},
            "findings": [],
        },
        "completeness": {"status": "measured", "score": 75.0, "findings": []},
    }
    if realtime_status is not None:
        categories["realtime"] = {
            "status": realtime_status,
            "score": 40.0,
            "findings": realtime_findings or [],
        }
    return {
        "snapshot_date": date,
        "overall": {"grade": grade, "score": score},
        "feed": {"sha256": "aaa", "size_bytes": 1000},
        "rubric_version": rubric,
        "validator_version": validator,
        "scoring_profile": {"id": profile_id, "rubric_version": rubric},
        "fetch": {"reader_archive_profile": reader_profile},
        "categories": categories,
    }


# --- the comparability contract ------------------------------------------------


def test_identical_contracts_are_comparable() -> None:
    check = compare_contract(_contract_artifact(), _contract_artifact())
    assert check.comparable
    assert check.reasons == ()


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        pytest.param({"rubric": "1.2"}, "rubric_version_mismatch", id="rubric"),
        pytest.param({"profile_id": "other-1.0"}, "scoring_profile_id_mismatch", id="profile"),
        pytest.param({"validator": "7.0.0"}, "validator_version_mismatch", id="validator"),
        pytest.param(
            {"reader_profile": "flat-single-root-v1"},
            "reader_archive_profile_mismatch",
            id="reader-profile",
        ),
    ],
)
def test_each_contract_field_is_named_when_it_differs(kwargs: dict[str, Any], reason: str) -> None:
    check = compare_contract(_contract_artifact(), _contract_artifact(**kwargs))
    assert not check.comparable
    assert reason in check.reasons
    # Every reason must have a sentence: a bare enum name in a CI log is not an
    # explanation, and the reason table is what makes the refusal actionable.
    assert all(text and not text.endswith("_mismatch") for text in check.explanations)


def test_a_changed_measured_category_set_is_not_comparable() -> None:
    """Three categories and four categories are different denominators."""
    prev = _contract_artifact(realtime_status="measured")
    curr = _contract_artifact()
    check = compare_contract(prev, curr)
    assert not check.comparable
    assert "measured_category_set_mismatch" in check.reasons


def test_an_unstated_contract_field_is_not_treated_as_a_match() -> None:
    """An artifact that does not say which validator scored it is not comparable.

    Absent is not equal. Reading a missing field as agreement is how a
    methodology change gets published as a change in a feed.
    """
    curr = _contract_artifact()
    del curr["validator_version"]
    check = compare_contract(_contract_artifact(), curr)
    assert not check.comparable
    assert "validator_version_missing" in check.reasons


# --- a category going dark is not a cleared finding ----------------------------


def test_a_finding_whose_category_stopped_being_measured_is_not_cleared() -> None:
    """The absence-rendered-as-a-value case, in the diff.

    Realtime is optional and its measurement depends on an endpoint answering.
    When it stops answering the category is no longer measured and its findings
    vanish from the artifact — which is not the same as those findings being
    fixed. They are reported separately, and never as cleared.
    """
    rt_finding = _finding("scorecard_rt_trip_updates_unreachable", 1, severity="ERROR")
    prev = _contract_artifact(realtime_status="measured", realtime_findings=[rt_finding])
    curr = _contract_artifact(realtime_status="not_yet_measured", realtime_findings=[])
    diff = diff_artifacts(prev, curr)
    assert [c.code for c in diff.resolved] == []
    assert [c.code for c in diff.unmeasured] == ["scorecard_rt_trip_updates_unreachable"]
    assert diff.has_changes
    # And it is not a regression either: nothing was observed to get worse.
    assert not diff.regressed


def test_a_finding_that_really_cleared_is_still_reported_as_cleared() -> None:
    """The negative control for the test above: the guard must not swallow a real clearance."""
    rt_finding = _finding("scorecard_rt_trip_updates_unreachable", 1, severity="ERROR")
    prev = _contract_artifact(realtime_status="measured", realtime_findings=[rt_finding])
    curr = _contract_artifact(realtime_status="measured", realtime_findings=[])
    diff = diff_artifacts(prev, curr)
    assert [c.code for c in diff.resolved] == ["scorecard_rt_trip_updates_unreachable"]
    assert diff.unmeasured == []


def test_regressed_is_true_for_a_new_finding_and_for_a_grade_drop() -> None:
    grew = diff_artifacts(
        _contract_artifact(findings=[_finding("unused_shape", 2)]),
        _contract_artifact(findings=[_finding("unused_shape", 9)]),
    )
    assert grew.regressed
    appeared = diff_artifacts(
        _contract_artifact(), _contract_artifact(findings=[_finding("unused_shape", 1)])
    )
    assert appeared.regressed
    dropped = diff_artifacts(
        _contract_artifact(grade="B", score=82.0), _contract_artifact(grade="C", score=71.0)
    )
    assert dropped.regressed
    improved = diff_artifacts(
        _contract_artifact(findings=[_finding("unused_shape", 9)]),
        _contract_artifact(findings=[_finding("unused_shape", 2)]),
    )
    assert not improved.regressed


# --- the JSON payload refuses to carry a change claim across a boundary --------


def test_diff_json_carries_no_change_claim_when_not_comparable() -> None:
    payload = diff_json(_contract_artifact(), _contract_artifact(validator="7.0.0"))
    assert payload["comparable"] is False
    assert payload["reasons"] == ["validator_version_mismatch"]
    # Absent, not empty. An empty findings object reads as "nothing changed",
    # which is the one thing that must not be said across a contract boundary.
    assert "findings" not in payload
    assert "overall" not in payload
    assert "regressed" not in payload
    assert payload["prev"]["contract"]["validator_version"] == "8.0.1"
    assert payload["curr"]["contract"]["validator_version"] == "7.0.0"


def test_diff_json_carries_the_change_when_comparable() -> None:
    payload = diff_json(
        _contract_artifact(), _contract_artifact(findings=[_finding("unused_shape", 3)])
    )
    assert payload["comparable"] is True
    assert [f["code"] for f in payload["findings"]["new"]] == ["unused_shape"]
    assert payload["regressed"] is True
    # A comparable pair measured the same categories by construction, so there
    # is no "no_longer_measured" key to read as an empty reassurance.
    assert "no_longer_measured" not in payload


# --- rendering -----------------------------------------------------------------


def test_text_render_refuses_across_a_boundary_and_names_the_field() -> None:
    text = render_diff_text(_contract_artifact(), _contract_artifact(rubric="1.2"))
    assert "NOT COMPARABLE" in text
    assert "rubric_version_mismatch" in text
    for forbidden in ("New findings", "Cleared findings", "Nothing changed"):
        assert forbidden not in text


def test_markdown_render_refuses_across_a_boundary() -> None:
    md = render_diff_markdown(_contract_artifact(), _contract_artifact(rubric="1.2"))
    assert "Not comparable" in md
    assert "Cleared findings" not in md


def test_a_refusal_says_which_findings_stopped_being_measured() -> None:
    """A bare refusal would read as a clean bill of health. It must not.

    Realtime going dark is itself a contract change, so the pair is refused —
    and the reader still has to be told that the realtime findings did not go
    away, we simply stopped looking at them.
    """
    rt_finding = _finding("scorecard_rt_trip_updates_unreachable", 1, severity="ERROR")
    prev = _contract_artifact(realtime_status="measured", realtime_findings=[rt_finding])
    curr = _contract_artifact(realtime_status="not_yet_measured")
    assert [c.code for c in findings_no_longer_measured(prev, curr)] == [
        "scorecard_rt_trip_updates_unreachable"
    ]

    text = render_diff_text(prev, curr)
    assert "NOT COMPARABLE" in text
    assert "Not measured in the newer artifact (1)" in text
    assert "These did not clear" in text
    assert "Cleared findings" not in text

    md = render_diff_markdown(prev, curr)
    assert "Not measured in the newer artifact (1)" in md
    assert "did not clear" in md
    assert "Cleared findings" not in md

    payload = diff_json(prev, curr)
    assert payload["comparable"] is False
    assert [f["code"] for f in payload["no_longer_measured"]] == [
        "scorecard_rt_trip_updates_unreachable"
    ]
    # Still no change claim anywhere in the payload.
    assert "findings" not in payload
    assert "overall" not in payload


def test_markdown_reports_a_real_clearance_within_a_stable_contract() -> None:
    prev = _contract_artifact(
        realtime_status="measured",
        realtime_findings=[_finding("scorecard_rt_trip_updates_unreachable", 1, severity="ERROR")],
        findings=[_finding("unused_shape", 4)],
    )
    curr = _contract_artifact(realtime_status="measured", realtime_findings=[])
    md = render_diff_markdown(prev, curr)
    assert "Cleared findings (2)" in md
    assert "Not measured in the newer artifact" not in md
