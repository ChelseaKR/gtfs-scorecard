"""Tests for the FTA NTD GTFS-readiness assessment (pure)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.ntd import (
    ALIGNED,
    AT_RISK,
    MISMATCH,
    MISSING,
    NOT_READY,
    READY,
    UNKNOWN,
    assess,
    assess_id_alignment,
    assess_shapes_readiness,
)


def _artifact(
    *,
    reachable: bool = True,
    url: str = "https://ex.org/g.zip",
    errors: int = 0,
    days: int | None = 90,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = [{"severity": "ERROR", "code": f"e{i}"} for i in range(errors)]
    findings.append({"severity": "WARNING", "code": "w"})
    return {
        "feed": {"reachable": reachable, "static_url": url},
        "categories": {
            "correctness": {"status": "measured", "findings": findings},
            "freshness": {"status": "measured", "details": {"days_until_expiry": days}},
        },
    }


def _status(artifact: dict[str, Any]) -> str:
    return assess(artifact).status


def _pillar(artifact: dict[str, Any], key: str) -> str:
    return {p.key: p.status for p in assess(artifact).pillars}[key]


def test_clean_current_feed_is_ready() -> None:
    a = _artifact(errors=0, days=90)
    r = assess(a)
    assert r.status == READY
    assert all(p.status == READY for p in r.pillars)
    # The summary never leads with a compliance-sounding claim; the caveat is
    # part of the sentence, not a trailing footnote (review finding, E1).
    assert "heads-up, not a determination" in r.summary
    assert "D-10" in r.summary


def test_expired_feed_is_not_ready_on_currency() -> None:
    a = _artifact(days=-200)  # lapsed
    assert _status(a) == NOT_READY
    assert _pillar(a, "current") == NOT_READY
    assert "expired" in assess(a).summary
    assert assess(a).summary.startswith("Resolve this before you certify")


def test_expiring_soon_is_at_risk_not_blocking() -> None:
    a = _artifact(days=20)
    assert _status(a) == AT_RISK
    assert _pillar(a, "current") == AT_RISK
    assert "renew before you certify" in assess(a).summary


def test_validator_errors_make_validity_at_risk() -> None:
    a = _artifact(errors=3, days=90)
    assert _pillar(a, "valid") == AT_RISK
    assert _status(a) == AT_RISK
    assert "3 validator errors" in assess(a).summary


def test_unreachable_feed_is_not_published() -> None:
    a = _artifact(reachable=False)
    assert _pillar(a, "published") == NOT_READY
    assert _status(a) == NOT_READY


def test_worst_pillar_drives_overall_status() -> None:
    # Errors (at_risk) plus an expired calendar (not_ready) -> not_ready overall.
    a = _artifact(errors=2, days=-10)
    assert _status(a) == NOT_READY


def test_no_expiry_date_cannot_confirm_currency() -> None:
    a = _artifact(days=None)
    assert _pillar(a, "current") == NOT_READY
    assert "currency is unknown" in assess(a).summary


# --- NTD ID alignment (agency_id vs. the agency's NTD ID) ---


def test_alignment_matches_when_agency_id_equals_ntd_id() -> None:
    r = assess_id_alignment(["90142"], "90142")
    assert r.status == ALIGNED
    assert not r.fix
    assert "90142" in r.detail
    assert r.to_dict() == {
        "status": "aligned",
        "detail": r.detail,
        "feed_agency_ids": ["90142"],
        "ntd_id": "90142",
    }


def test_alignment_mismatch_names_the_fix() -> None:
    r = assess_id_alignment(["UNITRANS"], "90142")
    assert r.status == MISMATCH
    assert "UNITRANS" in r.detail
    assert "90142" in r.fix
    assert "agency_id" in r.fix


def test_alignment_missing_when_no_agency_id() -> None:
    r = assess_id_alignment([], "90090")
    assert r.status == MISSING
    assert "90090" in r.fix


def test_alignment_unknown_without_an_ntd_id_on_file() -> None:
    r = assess_id_alignment(["WHATEVER"], "")
    assert r.status == UNKNOWN
    assert not r.fix  # never a penalty when we cannot check
    d = r.to_dict()
    assert "ntd_id" not in d and "fix" not in d
    assert d["feed_agency_ids"] == ["WHATEVER"]


def test_alignment_tolerates_whitespace_and_blanks() -> None:
    assert assess_id_alignment(["  90142  "], "  90142  ").status == ALIGNED
    assert assess_id_alignment(["", "  "], "90142").status == MISSING


def test_alignment_copy_is_optional_not_a_mandated_feed_change() -> None:
    """RESEARCH-ROADMAP R7: the July 2025 NTD final rule did not adopt the proposed
    agency_id-to-NTD-ID mandate (FTA links them on the P-50 form), so the copy must
    never tell an agency it is *required* to change its feed."""
    for result in (
        assess_id_alignment(["WHATEVER"], ""),  # unknown
        assess_id_alignment([], "90090"),  # missing
        assess_id_alignment(["UNITRANS"], "90142"),  # mismatch
    ):
        text = f"{result.detail} {result.fix}".lower()
        # No affirmative language implying FTA mandates the feed-side change.
        # ("not a required feed change" is allowed; it negates the obligation.)
        for mandate in (
            "fta requires",
            "ntd requires",
            "requires the",
            "requires your",
            "you must",
            "must change",
            "must set",
            "you have to",
            "asks that agency_id",
            "should be your",
        ):
            assert mandate not in text, f"mandate phrasing leaked: {mandate!r}"
        # The final-rule framing is present: optional, and FTA's own P-50 form.
        assert "p-50" in text
        assert "optional" in text or "convenience" in text


def test_alignment_mismatch_acknowledges_shared_regional_feeds() -> None:
    """A feed serving several agencies legitimately carries multiple agency_ids,
    so a mismatch is framed as a heads-up, not an error (R7)."""
    result = assess_id_alignment(["AGENCY_A", "AGENCY_B"], "90142")
    assert result.status == MISMATCH
    assert "shared regional feed" in result.detail.lower()
    assert "not an error" in result.detail.lower()


def test_one_fix_from_ready_keeps_only_single_pillar_misses() -> None:
    from scorecard_pipeline.ntd import one_fix_from_ready

    ready = _artifact(errors=0, days=90)
    ready["agency"] = {"id": "ready-t", "name": "Ready Transit", "state": "Iowa"}
    one_short = _artifact(errors=2, days=90)  # valid pillar only
    one_short["agency"] = {"id": "close-t", "name": "Close Transit", "state": "Ohio"}
    two_short = _artifact(errors=2, days=-40)  # valid and current both fail
    two_short["agency"] = {"id": "far-t", "name": "Far Transit", "state": "Ohio"}
    lapsed = _artifact(errors=0, days=-10)  # current pillar only, not_ready
    lapsed["agency"] = {"id": "lapsed-t", "name": "Lapsed Transit", "state": "Iowa"}

    rows = one_fix_from_ready([ready, one_short, two_short, lapsed])
    assert [r["id"] for r in rows] == ["lapsed-t", "close-t"]  # worst status first
    assert rows[0]["pillar"] == "current"
    assert "expired" in rows[0]["fix"]
    assert rows[1]["pillar"] == "valid"
    assert "error" in rows[1]["fix"]


# --- Shapes readiness (shapes.txt coverage of trips.txt, FTA RY2025/26) ---


def test_shapes_ready_when_every_trip_has_a_shape() -> None:
    r = assess_shapes_readiness(total_trips=40, trips_with_shape=40)
    assert r.status == READY
    assert not r.fix
    assert "40" in r.detail
    assert r.to_dict() == {
        "status": "ready",
        "detail": r.detail,
        "total_trips": 40,
        "trips_with_shape": 40,
    }


def test_shapes_not_ready_when_no_trip_has_a_shape() -> None:
    r = assess_shapes_readiness(total_trips=12, trips_with_shape=0)
    assert r.status == NOT_READY
    assert "Report Year 2026" in r.fix
    assert "Report Year 2025" in r.fix


def test_shapes_not_ready_when_feed_has_no_trips() -> None:
    r = assess_shapes_readiness(total_trips=0, trips_with_shape=0)
    assert r.status == NOT_READY
    assert not r.fix
    assert "can't be checked" in r.detail


def test_shapes_at_risk_when_partially_covered() -> None:
    r = assess_shapes_readiness(total_trips=10, trips_with_shape=6)
    assert r.status == AT_RISK
    assert "6 of 10" in r.detail
    assert "4" in r.detail


def test_shapes_readiness_never_claims_current_noncompliance() -> None:
    """The RY2026 requirement phases in by reporter type we do not curate per
    agency, so the copy must read as a heads-up against a future deadline, never
    a claim that the agency is out of compliance today."""
    for result in (
        assess_shapes_readiness(0, 0),
        assess_shapes_readiness(10, 0),
        assess_shapes_readiness(10, 5),
    ):
        text = f"{result.detail} {result.fix}".lower()
        for mandate in ("you are not compliant", "you are in violation", "you must"):
            assert mandate not in text, f"mandate phrasing leaked: {mandate!r}"
