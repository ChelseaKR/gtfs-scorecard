"""Tests for bounded cohort support campaigns."""

from __future__ import annotations

import datetime as dt

import pytest

from scorecard_pipeline.campaigns import (
    build_program_campaign,
    render_program_campaign_markdown,
)


def _artifact(agency_id: str, code: str | None, *, days: int = 90) -> dict[str, object]:
    findings = (
        [{"code": code, "count": 3, "what": "Fields are unknown.", "fix": "Export values."}]
        if code
        else []
    )
    return {
        "snapshot_date": "2026-07-01",
        "agency": {"id": agency_id, "name": agency_id.title()},
        "overall": {"grade": "F", "score": 20},
        "categories": {
            "completeness": {"status": "measured", "findings": findings},
            "freshness": {
                "status": "measured",
                "details": {"days_until_expiry": days},
                "findings": [],
            },
        },
    }


def test_campaign_targets_one_theme_without_scores_or_ranking() -> None:
    plan = build_program_campaign(
        rollup_id="district",
        rollup_name="District",
        kind="accessibility-fields",
        artifacts=[
            _artifact("alpha", "scorecard_wheelchair_boarding_unknown"),
            _artifact("beta", None),
        ],
        as_of=dt.date(2026, 7, 2),
    )
    assert plan["baseline"] == {
        "as_of": "2026-07-02",
        "agencies_checked": 2,
        "agencies_targeted": 1,
        "agencies_already_clear": 1,
    }
    assert [target["agency_id"] for target in plan["targets"]] == ["alpha"]
    assert "score" not in plan["targets"][0]
    assert "ranking" in plan["fairness_note"]


def test_calendar_campaign_uses_coverage_even_without_notice_code() -> None:
    plan = build_program_campaign(
        rollup_id="r",
        rollup_name="Region",
        kind="calendar-renewal",
        artifacts=[_artifact("soon", None, days=12), _artifact("current", None, days=60)],
        as_of=dt.date(2026, 7, 2),
    )
    assert [target["agency_id"] for target in plan["targets"]] == ["soon"]
    assert plan["targets"][0]["findings"][0]["code"] == "calendar_coverage_below_30_days"


def test_markdown_leads_with_goal_and_closeout() -> None:
    plan = build_program_campaign(
        rollup_id="r",
        rollup_name="Region",
        kind="rider-information",
        artifacts=[_artifact("one", "missing_trip_headsign")],
        as_of=dt.date(2026, 7, 2),
    )
    markdown = render_program_campaign_markdown(plan)
    assert "**Goal:**" in markdown
    assert "## Agency worklist" in markdown
    assert "## Closeout" in markdown
    assert "not an agency ranking" in markdown


def test_unknown_campaign_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown campaign kind"):
        build_program_campaign(
            rollup_id="r",
            rollup_name="Region",
            kind="leaderboard",
            artifacts=[],
            as_of=dt.date(2026, 7, 2),
        )
