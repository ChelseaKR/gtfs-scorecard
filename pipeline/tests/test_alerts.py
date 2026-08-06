"""Tests for the expiry/regression alert digest."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.alerts import build_digest, render_digest
from scorecard_pipeline.config import artifacts_dir
from scorecard_pipeline.validate import VALIDATOR_VERSION


def comparable_history_point(
    date: str,
    score: float,
    grade: str,
    *,
    validator_version: str = VALIDATOR_VERSION,
) -> dict[str, Any]:
    return {
        "date": date,
        "score": score,
        "grade": grade,
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": RUBRIC_VERSION,
        "validator_version": validator_version,
        "categories": {
            "correctness": 80.0,
            "freshness": 80.0,
            "completeness": 80.0,
        },
    }


def write_latest(
    agency_id: str,
    name: str,
    score: float,
    grade: str,
    days_until_expiry: int | None,
    *,
    export_diff: dict[str, Any] | None = None,
) -> None:
    path = artifacts_dir() / agency_id
    path.mkdir(parents=True, exist_ok=True)
    artifact: dict[str, Any] = {
        "agency": {"id": agency_id, "name": name},
        "snapshot_date": "2026-06-12",
        "overall": {"score": score, "grade": grade},
        "categories": {
            "freshness": {"details": {"days_until_expiry": days_until_expiry}},
        },
        "top_fixes": [],
    }
    if export_diff is not None:
        artifact["export_diff"] = export_diff
    (path / "latest.json").write_text(json.dumps(artifact))


def write_index(entries: dict[str, dict]) -> None:  # type: ignore[type-arg]
    path = artifacts_dir() / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1.1", "agencies": entries}))


def test_flags_feed_expiring_within_window() -> None:
    write_latest("soon", "Soon Transit", 90.0, "A", days_until_expiry=10)
    write_index(
        {
            "soon": {
                "name": "Soon Transit",
                "history": [
                    {"date": "2026-06-12", "score": 90.0, "grade": "A"},
                ],
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12), expiry_days=21)
    kinds = {(i.agency_id, i.kind) for i in digest.items}
    assert ("soon", "expiry") in kinds


def test_healthy_feed_produces_no_items() -> None:
    write_latest("ok", "OK Transit", 90.0, "A", days_until_expiry=120)
    write_index(
        {
            "ok": {
                "name": "OK Transit",
                "history": [
                    {"date": "2026-06-11", "score": 90.0, "grade": "A"},
                    {"date": "2026-06-12", "score": 90.0, "grade": "A"},
                ],
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    assert digest.items == []
    assert "No feeds need attention" in render_digest(digest)


def test_grade_drop_is_a_regression() -> None:
    write_latest("slip", "Slip Transit", 78.0, "C", days_until_expiry=200)
    write_index(
        {
            "slip": {
                "name": "Slip Transit",
                "history": [
                    comparable_history_point("2026-06-11", 84.0, "B"),
                    comparable_history_point("2026-06-12", 78.0, "C"),
                ],
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    regressions = [i for i in digest.items if i.kind == "regression"]
    assert regressions and regressions[0].agency_id == "slip"


def test_small_wobble_is_not_a_regression() -> None:
    write_latest("steady", "Steady Transit", 83.0, "B", days_until_expiry=200)
    write_index(
        {
            "steady": {
                "name": "Steady Transit",
                "history": [
                    comparable_history_point("2026-06-11", 84.0, "B"),
                    comparable_history_point("2026-06-12", 83.0, "B"),
                ],
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    assert [i for i in digest.items if i.kind == "regression"] == []


def test_producer_change_is_not_a_regression() -> None:
    write_latest("changed", "Changed Transit", 60.0, "D", days_until_expiry=200)
    write_index(
        {
            "changed": {
                "name": "Changed Transit",
                "history": [
                    comparable_history_point(
                        "2026-06-11", 90.0, "A", validator_version="different-validator"
                    ),
                    comparable_history_point("2026-06-12", 60.0, "D"),
                ],
            }
        }
    )

    digest = build_digest(today=dt.date(2026, 6, 12))

    assert [i for i in digest.items if i.kind in {"regression", "anomaly"}] == []


def test_changed_export_produces_an_export_change_item() -> None:
    write_latest(
        "moved",
        "Moved Transit",
        88.0,
        "B",
        days_until_expiry=200,
        export_diff={
            "from_sha256": "a" * 64,
            "to_sha256": "b" * 64,
            "changes": ["Route 5 (E Street Express) is no longer in the export."],
        },
    )
    write_index({"moved": {"name": "Moved Transit", "history": []}})
    digest = build_digest(today=dt.date(2026, 6, 12))
    export_changes = [i for i in digest.items if i.kind == "export_change"]
    assert len(export_changes) == 1
    assert export_changes[0].agency_id == "moved"
    assert "Route 5" in export_changes[0].detail


def test_export_diff_with_no_changes_produces_no_item() -> None:
    # The schema requires a non-empty changes list, but a defensively-empty
    # block should not fabricate an alert either.
    write_latest(
        "quiet",
        "Quiet Transit",
        88.0,
        "B",
        days_until_expiry=200,
        export_diff={"from_sha256": "a" * 64, "to_sha256": "b" * 64, "changes": []},
    )
    write_index({"quiet": {"name": "Quiet Transit", "history": []}})
    digest = build_digest(today=dt.date(2026, 6, 12))
    assert [i for i in digest.items if i.kind == "export_change"] == []


def test_export_change_item_coexists_with_a_regression() -> None:
    # A structural export change and a grade drop can happen the same run;
    # both should surface, not just one.
    write_latest(
        "both",
        "Both Transit",
        70.0,
        "C",
        days_until_expiry=200,
        export_diff={
            "from_sha256": "a" * 64,
            "to_sha256": "b" * 64,
            "changes": ["12 stops moved more than 100 m."],
        },
    )
    write_index(
        {
            "both": {
                "name": "Both Transit",
                "history": [
                    comparable_history_point("2026-06-11", 90.0, "A"),
                    comparable_history_point("2026-06-12", 70.0, "C"),
                ],
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    kinds = {i.kind for i in digest.items if i.agency_id == "both"}
    assert {"regression", "export_change"} <= kinds


def test_export_change_renders_in_its_own_digest_section() -> None:
    write_latest(
        "moved",
        "Moved Transit",
        88.0,
        "B",
        days_until_expiry=200,
        export_diff={
            "from_sha256": "a" * 64,
            "to_sha256": "b" * 64,
            "changes": ["Route 5 (E Street Express) is no longer in the export."],
        },
    )
    write_index({"moved": {"name": "Moved Transit", "history": []}})
    text = render_digest(build_digest(today=dt.date(2026, 6, 12)))
    assert "## What changed inside the export" in text
    assert "Route 5" in text


def test_export_change_section_does_not_claim_the_grade_held() -> None:
    # An export can change structurally on the same run the grade drops, and
    # both sections then render in one digest. Section copy asserting the grade
    # did not move would be false in exactly that case, so it says a structural
    # change "does not have to" move the grade instead.
    write_latest(
        "both",
        "Both Transit",
        70.0,
        "C",
        days_until_expiry=200,
        export_diff={
            "from_sha256": "a" * 64,
            "to_sha256": "b" * 64,
            "changes": ["12 stops moved more than 100 m."],
        },
    )
    write_index(
        {
            "both": {
                "name": "Both Transit",
                "history": [
                    comparable_history_point("2026-06-11", 90.0, "A"),
                    comparable_history_point("2026-06-12", 70.0, "C"),
                ],
            }
        }
    )
    text = render_digest(build_digest(today=dt.date(2026, 6, 12)))
    assert "## Grade changes" in text
    assert "## What changed inside the export" in text
    assert "does not have to move the grade" in text
    assert "didn't move the grade" not in text


def test_render_includes_fix_language() -> None:
    write_latest("soon", "Soon Transit", 90.0, "A", days_until_expiry=3)
    write_index({"soon": {"name": "Soon Transit", "history": []}})
    text = render_digest(build_digest(today=dt.date(2026, 6, 12)))
    assert "Fix:" in text
    assert "Soon Transit" in text


def test_expiry_item_links_to_the_send_note_block() -> None:
    write_latest("soon", "Soon Transit", 90.0, "A", days_until_expiry=5)
    write_index({"soon": {"name": "Soon Transit", "history": []}})
    digest = build_digest(today=dt.date(2026, 6, 12))
    (item,) = [i for i in digest.items if i.kind == "expiry"]
    assert item.scorecard_url == "https://gtfsscorecard.org/agency/soon/#send-note"
    text = render_digest(digest)
    assert "Copy a note to send the agency" in text
    assert "https://gtfsscorecard.org/agency/soon/#send-note" in text


def test_alert_link_preserves_the_published_top_finding() -> None:
    write_latest("soon", "Soon Transit", 90.0, "A", days_until_expiry=5)
    latest = artifacts_dir() / "soon" / "latest.json"
    payload = json.loads(latest.read_text())
    payload["categories"]["freshness"]["findings"] = [{"code": "scorecard_feed_expiring_soon"}]
    payload["top_fixes"] = [
        {
            "code": "scorecard_feed_expiring_soon",
            "fix": "Publish a longer service calendar.",
        }
    ]
    latest.write_text(json.dumps(payload))
    write_index({"soon": {"name": "Soon Transit", "history": []}})

    digest = build_digest(today=dt.date(2026, 6, 12))
    (item,) = [i for i in digest.items if i.kind == "expiry"]

    assert item.scorecard_url == (
        "https://gtfsscorecard.org/agency/soon/"
        "?finding=scorecard_feed_expiring_soon#finding-handoff"
    )
    assert "Open the finding handoff" in render_digest(digest)


def test_sixty_day_feed_gets_a_first_heads_up() -> None:
    # Default window is now 60 days, so a feed two months out is flagged early.
    write_latest("ramp", "Ramp Transit", 90.0, "A", days_until_expiry=58)
    write_index({"ramp": {"name": "Ramp Transit", "history": []}})
    digest = build_digest(today=dt.date(2026, 6, 12))
    (item,) = [i for i in digest.items if i.kind == "expiry"]
    assert item.days_until_expiry == 58


def test_expiring_feeds_grouped_by_lead_time_tier() -> None:
    write_latest("week", "Week Transit", 90.0, "A", days_until_expiry=5)
    write_latest("month", "Month Transit", 90.0, "A", days_until_expiry=25)
    write_latest("dead", "Dead Transit", 40.0, "F", days_until_expiry=-3)
    write_index(
        {
            "week": {"name": "Week Transit", "history": []},
            "month": {"name": "Month Transit", "history": []},
            "dead": {"name": "Dead Transit", "history": []},
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    # Soonest (most overdue) first.
    expiry_ids = [i.agency_id for i in digest.items if i.kind == "expiry"]
    assert expiry_ids == ["dead", "week", "month"]

    text = render_digest(digest)
    assert "Already expired" in text
    assert "Expires within a week" in text
    assert "Expires within a month" in text
    # the expired tier heading precedes the week tier heading in the output
    assert text.index("Already expired") < text.index("Expires within a week")


def _lapse_series(base_date: dt.date, days_series: list[int]) -> list[dict]:  # type: ignore[type-arg]
    """A history list (EXP-13 lapse_risk shape) from a series of days_until_expiry."""
    return [
        {
            "date": (base_date + dt.timedelta(days=i)).isoformat(),
            "days_until_expiry": d,
            "rubric_version": RUBRIC_VERSION,
            "scoring_profile_id": SCORING_PROFILE_ID,
            "scoring_profile_rubric_version": RUBRIC_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "categories": {
                "correctness": 80.0,
                "freshness": 80.0,
                "completeness": 80.0,
            },
        }
        for i, d in enumerate(days_series)
    ]


def test_far_out_feed_with_risky_renewal_history_gets_lapse_risk_item() -> None:
    # Well outside the deterministic expiry window, but its history shows a
    # lapse-and-late-renewal pattern -- the behavioral signal should fire.
    write_latest("risky", "Risky Transit", 90.0, "A", days_until_expiry=200)
    series = [5, 4, 3, 2, 1, 0, -1, -2, 50, 49, 48, 47]
    write_index(
        {
            "risky": {
                "name": "Risky Transit",
                "history": _lapse_series(dt.date(2026, 5, 1), series),
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    lapse_items = [i for i in digest.items if i.kind == "lapse_risk"]
    assert lapse_items and lapse_items[0].agency_id == "risky"
    text = render_digest(digest)
    assert "early lapse-risk signals" in text.lower()


def test_deterministic_expiry_item_suppresses_lapse_risk_duplicate() -> None:
    # A feed already inside the expiry window should not also get a lapse_risk
    # item, even if its history would otherwise flag one -- the deterministic
    # alert is already more urgent and covers the same ground.
    write_latest("close", "Close Transit", 60.0, "C", days_until_expiry=10)
    series = [5, 4, 3, 2, 1, 0, -1, -2, 50, 49, 48, 47]
    write_index(
        {
            "close": {
                "name": "Close Transit",
                "history": _lapse_series(dt.date(2026, 5, 1), series),
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    kinds = {i.kind for i in digest.items if i.agency_id == "close"}
    assert "expiry" in kinds
    assert "lapse_risk" not in kinds


def test_healthy_far_out_feed_produces_no_lapse_risk_item() -> None:
    write_latest("ok", "OK Transit", 90.0, "A", days_until_expiry=200)
    series = list(range(80, 60, -1))  # steady decline, never lapses
    write_index(
        {
            "ok": {
                "name": "OK Transit",
                "history": _lapse_series(dt.date(2026, 5, 1), series),
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    assert digest.items == []


def test_reader_profile_change_does_not_fabricate_lapse_risk() -> None:
    write_latest("profile-change", "Profile Change", 90.0, "A", days_until_expiry=200)
    history = _lapse_series(
        dt.date(2026, 5, 1),
        [5, 4, 3, 2, 1, 0, -1, -2, 50, 49, 48, 47],
    )
    for point in history[-4:]:
        point["reader_archive_profile"] = "flat-single-root-v1"
    write_index({"profile-change": {"name": "Profile Change", "history": history}})

    digest = build_digest(today=dt.date(2026, 6, 12))

    assert [item for item in digest.items if item.kind == "lapse_risk"] == []
