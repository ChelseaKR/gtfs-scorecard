"""Tests for the weekly cohort ("portfolio") digest for liaisons."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import pytest

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.config import artifacts_dir
from scorecard_pipeline.metrics import expiry_status
from scorecard_pipeline.portfolio_digest import (
    build_portfolio_digest,
    load_snapshot,
    render_portfolio_digest,
    save_snapshot,
)
from scorecard_pipeline.rollups import Rollup
from scorecard_pipeline.validate import VALIDATOR_VERSION

TODAY = dt.date(2026, 6, 19)


def write_latest(
    agency_id: str,
    name: str,
    score: float,
    grade: str,
    days: int | None = None,
    *,
    rubric_version: str = RUBRIC_VERSION,
    scoring_profile_id: str = SCORING_PROFILE_ID,
    scoring_profile_rubric_version: str = RUBRIC_VERSION,
    validator_version: str = VALIDATOR_VERSION,
    measured_categories: tuple[str, ...] = ("correctness", "freshness", "completeness"),
) -> None:
    path = artifacts_dir() / agency_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "latest.json").write_text(
        json.dumps(
            {
                "agency": {"id": agency_id, "name": name},
                "snapshot_date": "2026-06-19",
                "rubric_version": rubric_version,
                "scoring_profile": {
                    "id": scoring_profile_id,
                    "rubric_version": scoring_profile_rubric_version,
                },
                "validator_version": validator_version,
                "overall": {"score": score, "grade": grade},
                "categories": {
                    "correctness": {
                        "status": (
                            "measured" if "correctness" in measured_categories else "not_measured"
                        )
                    },
                    "freshness": {
                        "status": (
                            "measured" if "freshness" in measured_categories else "not_measured"
                        ),
                        "details": {"days_until_expiry": days},
                    },
                    "completeness": {
                        "status": (
                            "measured" if "completeness" in measured_categories else "not_measured"
                        )
                    },
                    "realtime": {
                        "status": (
                            "measured" if "realtime" in measured_categories else "not_yet_published"
                        )
                    },
                },
                "top_fixes": [],
            }
        )
    )


def snap(
    score: float,
    grade: str,
    days: int | None,
    *,
    rubric_version: str = RUBRIC_VERSION,
    scoring_profile_id: str = SCORING_PROFILE_ID,
    scoring_profile_rubric_version: str = RUBRIC_VERSION,
    validator_version: str = VALIDATOR_VERSION,
    measured_categories: tuple[str, ...] = ("correctness", "freshness", "completeness"),
) -> dict[str, Any]:
    """A prior-week member state in the shape the digest persists."""
    return {
        "score": score,
        "grade": grade,
        "days_until_expiry": days,
        "expiry_status": expiry_status(days),
        "producer_contract": {
            "rubric_version": rubric_version,
            "scoring_profile_id": scoring_profile_id,
            "scoring_profile_rubric_version": scoring_profile_rubric_version,
            "validator_version": validator_version,
            "measured_categories": list(measured_categories),
        },
    }


ALL = Rollup(id="all", name="All tracked agencies", member_ids=())


def test_first_run_captures_snapshot_without_movement() -> None:
    write_latest("a", "A Transit", 80.0, "B", days=120)
    write_latest("b", "B Transit", 70.0, "C", days=90)
    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot=None)
    assert digest.first_run is True
    assert digest.movements == []
    assert digest.member_count == 2
    # The current state is captured so next week has something to diff against.
    assert set(digest.snapshot) == {"a", "b"}
    text = render_portfolio_digest(digest)
    assert "First digest" in text
    assert "2 feed(s) tracked" in text


def test_score_improvement_is_a_fix_on_second_run() -> None:
    write_latest("a", "A Transit", 78.0, "C", days=120)
    previous = {"a": snap(70.0, "C", 120)}
    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot=previous)
    assert digest.first_run is False
    kinds = [m.kind for m in digest.movements]
    assert kinds == ["improved"]
    text = render_portfolio_digest(digest)
    assert "## Fixed this week" in text
    assert "A Transit" in text


def test_newly_lapsed_feed_is_flagged() -> None:
    write_latest("a", "A Transit", 60.0, "D", days=-5)  # expired since last week
    previous = {"a": snap(62.0, "D", 120)}
    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot=previous)
    lapsed = [m for m in digest.movements if m.kind == "newly_lapsed"]
    assert lapsed and lapsed[0].agency_id == "a"
    text = render_portfolio_digest(digest)
    assert "## Worth a look" in text
    assert "expired this week" in text.lower()


def test_cleared_feed_reads_as_fixed() -> None:
    write_latest("a", "A Transit", 88.0, "B", days=150)  # re-exported, current again
    previous = {"a": snap(50.0, "F", -20)}  # was lapsed last week
    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot=previous)
    cleared = [m for m in digest.movements if m.kind == "cleared"]
    assert cleared and cleared[0].agency_id == "a"
    text = render_portfolio_digest(digest)
    # A cleared feed is a fix, so it leads the digest and is framed positively.
    assert "## Fixed this week" in text
    assert "current again" in text.lower()


def test_steady_week_is_empty_all_clear() -> None:
    write_latest("a", "A Transit", 90.0, "A", days=120)
    previous = {"a": snap(90.0, "A", 120)}
    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot=previous)
    assert digest.movements == []
    text = render_portfolio_digest(digest)
    assert "held steady" in text
    assert "Nothing newly expired" in text


def test_malformed_row_is_dropped_not_fatal() -> None:
    write_latest("good", "Good Transit", 82.0, "B", days=120)
    # A partial artifact with no "overall" block must not crash the cohort digest.
    broken = artifacts_dir() / "broken"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "latest.json").write_text(json.dumps({"agency": {"id": "broken", "name": "Broken"}}))
    previous = {"good": snap(80.0, "B", 120), "broken": snap(40.0, "F", -3)}
    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot=previous)
    assert digest.member_count == 1
    assert set(digest.snapshot) == {"good"}
    assert all(m.agency_id == "good" for m in digest.movements)


def test_no_shaming_rendering_leads_with_fixes() -> None:
    write_latest("up", "Up Transit", 82.0, "B", days=120)  # grade rose C -> B
    write_latest("down", "Down Transit", 80.0, "B", days=120)  # grade slipped A -> B
    previous = {"up": snap(70.0, "C", 120), "down": snap(92.0, "A", 120)}
    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot=previous)
    text = render_portfolio_digest(digest)
    # Fixes are reported before the feeds that need a look.
    assert text.index("## Fixed this week") < text.index("## Worth a look")
    # No shaming vocabulary.
    lowered = text.lower()
    for word in ("fail", "failing", "worst", "bad", "shame"):
        assert word not in lowered


def test_explicit_membership_scopes_the_digest() -> None:
    write_latest("x", "X Transit", 75.0, "C", days=120)
    write_latest("y", "Y Transit", 65.0, "D", days=120)
    previous = {"x": snap(70.0, "C", 120), "y": snap(60.0, "D", 120)}
    digest = build_portfolio_digest(
        Rollup(id="just-x", name="Just X", member_ids=("x",)),
        today=TODAY,
        previous_snapshot=previous,
    )
    assert digest.member_count == 1
    assert set(digest.snapshot) == {"x"}


def test_snapshot_round_trip_persists_members() -> None:
    write_latest("a", "A Transit", 80.0, "B", days=120)
    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot=None)
    path = save_snapshot(ALL, digest.snapshot, digest.as_of)
    assert path.exists()
    reloaded = load_snapshot(ALL)
    assert reloaded == digest.snapshot
    assert reloaded["a"]["producer_contract"] == {
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": RUBRIC_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "measured_categories": ["correctness", "freshness", "completeness"],
    }
    # An absent state file is a first run, not an error.
    assert load_snapshot(Rollup(id="never", name="Never", member_ids=())) == {}


def test_legacy_snapshot_restarts_baseline_without_claiming_movement() -> None:
    write_latest("a", "A Transit", 90.0, "A", days=-5)
    legacy = snap(40.0, "F", 120)
    legacy.pop("producer_contract")

    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot={"a": legacy})

    assert digest.first_run is False
    assert digest.baseline_restarted is True
    assert digest.baseline_reset_count == 1
    assert digest.compared_member_count == 0
    assert digest.movements == []
    text = render_portfolio_digest(digest)
    assert "Baseline restarted" in text
    assert "No week-over-week changes are claimed" in text
    assert "held steady" not in text
    assert "expired this week" not in text.lower()


@pytest.mark.parametrize(
    ("field", "incompatible_value"),
    [
        ("rubric_version", "0.9"),
        ("scoring_profile_id", "another-profile"),
        ("scoring_profile_rubric_version", "0.9"),
        ("validator_version", "7.0.0"),
        ("measured_categories", ["correctness", "freshness"]),
    ],
)
def test_changed_producer_contract_restarts_baseline(
    field: str, incompatible_value: str | list[str]
) -> None:
    write_latest("a", "A Transit", 90.0, "A", days=120)
    previous_state = snap(40.0, "F", -5)
    previous_state["producer_contract"][field] = incompatible_value

    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot={"a": previous_state})

    assert digest.baseline_restarted is True
    assert digest.baseline_reset_count == 1
    assert digest.movements == []


def test_partial_contract_reset_only_claims_over_comparable_members() -> None:
    write_latest("a", "A Transit", 80.0, "B", days=120)
    write_latest("b", "B Transit", 90.0, "A", days=120)
    legacy_b = snap(40.0, "F", -5)
    legacy_b.pop("producer_contract")
    previous = {
        "a": snap(80.0, "B", 120),
        "b": legacy_b,
    }

    digest = build_portfolio_digest(ALL, today=TODAY, previous_snapshot=previous)

    assert digest.baseline_restarted is False
    assert digest.compared_member_count == 1
    assert digest.baseline_reset_count == 1
    assert digest.movements == []
    text = render_portfolio_digest(digest)
    assert "All 1 comparable feed(s)" in text
    assert "All 2 feed(s)" not in text
    assert "1 other feed(s) started a new baseline" in text
