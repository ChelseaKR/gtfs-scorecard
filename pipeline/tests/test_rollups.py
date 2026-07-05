"""Tests for program rollup artifacts."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from scorecard_pipeline.config import artifacts_dir
from scorecard_pipeline.rollups import (
    Rollup,
    build_rollup,
    load_rollups,
    publish_rollups,
    rollup_csv,
)

WHEN = dt.datetime(2026, 6, 12, 12, 0, tzinfo=dt.UTC)


def write_latest(
    agency_id: str,
    name: str,
    score: float,
    grade: str,
    fixes: list[dict[str, str]] | None = None,
    days: int | None = None,
    state: str | None = None,
    country: str | None = None,
    shapes: tuple[int, int] | None = None,
    ntd_id: str | None = None,
) -> None:
    agency: dict[str, object] = {"id": agency_id, "name": name}
    if state:
        agency["state"] = state
    if country:
        agency["country"] = country
    payload: dict[str, object] = {
        "agency": agency,
        "snapshot_date": "2026-06-12",
        "overall": {"score": score, "grade": grade},
        "categories": {"freshness": {"details": {"days_until_expiry": days}}},
        "top_fixes": fixes or [],
    }
    if shapes is not None:
        total_trips, trips_with_shape = shapes
        payload["shapes_readiness"] = {
            "total_trips": total_trips,
            "trips_with_shape": trips_with_shape,
        }
    if ntd_id is not None:
        payload["ntd_id_alignment"] = {"ntd_id": ntd_id, "status": "aligned"}
    path = artifacts_dir() / agency_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "latest.json").write_text(json.dumps(payload))


def test_rollup_csv_has_header_and_rows_with_blanks_for_none() -> None:
    payload = {
        "members": [
            {
                "id": "b",
                "name": "B Transit",
                "grade": "F",
                "score": 40.0,
                "snapshot_date": "2026-06-12",
                "expiry_status": "lapsed",
                "days_until_expiry": -5,
                "needs_attention": True,
                "attention_reason": "Feed expired",
                "top_fix": "Re-export your feed",
                "shapes_status": "not_ready",
            },
            {
                "id": "a",
                "name": "A Transit",
                "grade": "A",
                "score": 95.0,
                "snapshot_date": "2026-06-12",
                "expiry_status": "current",
                "days_until_expiry": 200,
                "needs_attention": False,
                "attention_reason": None,
                "top_fix": None,
                "shapes_status": None,
            },
        ]
    }
    lines = rollup_csv(payload).splitlines()
    assert lines[0] == (
        "agency_id,agency_name,grade,score,checked,expiry_status,"
        "days_until_expiry,needs_attention,attention_reason,top_fix,shapes_txt_status"
    )
    assert lines[1].startswith("b,B Transit,F,40.0,")
    assert lines[1].endswith(",yes,Feed expired,Re-export your feed,not_ready")
    # None reason, top_fix, and shapes_status render as empty cells, not "None".
    assert lines[2].endswith(",no,,,")


def test_state_rollup_auto_includes_agencies_by_persisted_state() -> None:
    write_latest("ca1", "CA One", 80.0, "B", state="CA")
    write_latest("ca2", "CA Two", 70.0, "C", state="ca")  # case-insensitive
    write_latest("nv1", "NV One", 90.0, "A", state="NV")
    write_latest("unl", "Unlocated", 85.0, "B")  # no state
    rollup = Rollup(id="california", name="California", member_ids=(), state="CA")
    payload = build_rollup(rollup, WHEN)
    assert payload["agency_count"] == 2
    assert sorted(m["id"] for m in payload["members"]) == ["ca1", "ca2"]


def test_load_rollups_parses_state_selector(tmp_path: Path) -> None:
    config = tmp_path / "rollups.yaml"
    config.write_text("rollups:\n  - id: ca\n    name: California\n    state: CA\n")
    (rollup,) = load_rollups(config)
    assert rollup.state == "CA"
    assert rollup.member_ids == ()


def test_reserved_dirs_are_not_treated_as_agencies() -> None:
    write_latest("a", "A Transit", 70.0, "C")
    # The changes feed lives under artifacts/changes/latest.json and has no
    # "overall"; it must not be mistaken for an agency.
    changes = artifacts_dir() / "changes"
    changes.mkdir(parents=True, exist_ok=True)
    (changes / "latest.json").write_text(json.dumps({"schema_version": 1, "changes": []}))
    payload = build_rollup(load_rollups()[0], WHEN)
    assert payload["agency_count"] == 1
    assert [m["id"] for m in payload["members"]] == ["a"]


def test_publish_rollups_writes_a_csv_next_to_each_json() -> None:
    write_latest("a", "A Transit", 70.0, "C")
    write_latest("b", "B Transit", 92.0, "A")
    publish_rollups(WHEN)
    out = artifacts_dir() / "rollups"
    assert (out / "all.json").exists()
    assert (out / "all.csv").exists()
    csv_text = (out / "all.csv").read_text()
    assert csv_text.startswith("agency_id,agency_name,grade,score,")
    assert "A Transit" in csv_text and "B Transit" in csv_text


def test_default_rollup_covers_all_agencies_with_artifacts() -> None:
    write_latest("a", "A Transit", 70.0, "C")
    write_latest("b", "B Transit", 92.0, "A")
    rollups = load_rollups()
    assert [r.id for r in rollups] == ["all"]
    payload = build_rollup(rollups[0], WHEN)
    assert payload["agency_count"] == 2


def test_attention_flagged_agencies_sort_first_with_reason() -> None:
    write_latest("good", "Good Transit", 92.0, "A")
    write_latest("weak", "Weak Transit", 64.0, "D")
    # "Needs attention" is an injected expiry/regression signal, not low score.
    # Flagging the higher-scoring agency proves the flag (not score) drives the
    # ordering and the count.
    payload = build_rollup(
        Rollup("all", "All", ()), WHEN, {"good": "Service data expires in 5 days"}
    )
    assert payload["members"][0]["id"] == "good"
    assert payload["members"][0]["needs_attention"] is True
    assert payload["members"][0]["attention_reason"] == "Service data expires in 5 days"
    assert payload["members"][1]["id"] == "weak"
    assert payload["members"][1]["needs_attention"] is False
    assert payload["needs_attention"] == 1
    assert payload["average_score"] == 78.0


def test_ridership_weights_attention_order_high_ridership_first() -> None:
    # Two attention-flagged feeds: the big one scores slightly *better* but must
    # still rank first once ridership weights the list (ADR 0021).
    write_latest("big", "Big Transit", 66.0, "D", ntd_id="90001")
    write_latest("tiny", "Tiny Transit", 64.0, "D", ntd_id="90002")
    attention = {"big": "Feed expires in 5 days", "tiny": "Feed expires in 3 days"}
    ridership = {"90001": 5_000_000, "90002": 10_000}
    payload = build_rollup(Rollup("all", "All", ()), WHEN, attention, ridership)
    assert [m["id"] for m in payload["members"]] == ["big", "tiny"]
    assert payload["members"][0]["annual_trips"] == 5_000_000
    assert payload["members"][1]["annual_trips"] == 10_000


def test_ridership_none_leaves_order_unchanged() -> None:
    # Same feeds, no ridership map: falls back to worst-score-first, so the
    # lower-scoring "tiny" leads despite carrying fewer riders.
    write_latest("big", "Big Transit", 66.0, "D", ntd_id="90001")
    write_latest("tiny", "Tiny Transit", 64.0, "D", ntd_id="90002")
    attention = {"big": "Feed expires in 5 days", "tiny": "Feed expires in 3 days"}
    payload = build_rollup(Rollup("all", "All", ()), WHEN, attention, None)
    assert [m["id"] for m in payload["members"]] == ["tiny", "big"]
    # With no snapshot the trips field is present but None, never a guessed 0.
    assert payload["members"][0]["annual_trips"] is None


def test_ridership_only_reorders_within_attention_group() -> None:
    # A high-ridership feed that is *not* flagged stays below the attention group,
    # so ridership never promotes a feed past the "needs a call" line.
    write_latest("huge-ok", "Huge OK", 95.0, "A", ntd_id="90001")
    write_latest("small-flag", "Small Flagged", 60.0, "D", ntd_id="90002")
    attention = {"small-flag": "Feed expired"}
    ridership = {"90001": 9_000_000, "90002": 1_000}
    payload = build_rollup(Rollup("all", "All", ()), WHEN, attention, ridership)
    assert payload["members"][0]["id"] == "small-flag"
    assert payload["members"][0]["needs_attention"] is True
    assert payload["members"][1]["id"] == "huge-ok"


def test_common_fixes_counts_shared_codes() -> None:
    shared = {
        "code": "scorecard_wheelchair_boarding_unknown",
        "fix": "Set wheelchair_boarding on every stop.",
    }
    write_latest("a", "A", 70.0, "C", fixes=[shared])
    write_latest("b", "B", 72.0, "C", fixes=[shared])
    write_latest("c", "C", 75.0, "C", fixes=[{"code": "other", "fix": "Other fix."}])
    payload = build_rollup(Rollup("all", "All", ()), WHEN)
    common = payload["common_fixes"]
    assert len(common) == 1
    assert common[0]["agencies"] == 2
    assert common[0]["code"] == "scorecard_wheelchair_boarding_unknown"


def test_explicit_membership_limits_the_rollup() -> None:
    write_latest("x", "X", 80.0, "B")
    write_latest("y", "Y", 60.0, "D")
    payload = build_rollup(Rollup("just-x", "Just X", ("x",)), WHEN)
    assert payload["agency_count"] == 1
    assert payload["members"][0]["id"] == "x"


def test_publish_rollups_writes_index_and_files() -> None:
    write_latest("a", "A Transit", 70.0, "C")
    paths = publish_rollups(generated_at=WHEN)
    names = {p.name for p in paths}
    assert "all.json" in names
    assert "index.json" in names
    index = json.loads((artifacts_dir() / "rollups" / "index.json").read_text())
    assert index["rollups"][0]["id"] == "all"


def test_rollup_splits_expired_into_lapsed_and_stale() -> None:
    write_latest("current", "Current Transit", 90.0, "A", days=120)
    write_latest("soon", "Soon Transit", 80.0, "B", days=10)
    write_latest("lapsed", "Lapsed Transit", 40.0, "F", days=-30)
    write_latest("stale", "Stale Transit", 30.0, "F", days=-1000)
    payload = build_rollup(Rollup("all", "All", ()), WHEN)

    assert payload["expired"] == {"lapsed": 1, "stale": 1, "total": 2}
    status = {m["id"]: m["expiry_status"] for m in payload["members"]}
    assert status == {
        "current": "current",
        "soon": "expiring_soon",
        "lapsed": "lapsed",
        "stale": "stale",
    }


def test_rollup_expired_count_zero_when_all_current() -> None:
    write_latest("a", "A Transit", 90.0, "A", days=200)
    write_latest("b", "B Transit", 85.0, "B", days=None)  # no expiry date -> unknown
    payload = build_rollup(Rollup("all", "All", ()), WHEN)
    assert payload["expired"]["total"] == 0


def test_rollup_aggregates_shapes_readiness_across_members() -> None:
    write_latest("ready1", "Ready Transit", 90.0, "A", shapes=(10, 10))
    write_latest("risk1", "At-Risk Transit", 80.0, "B", shapes=(10, 6))
    write_latest("notready1", "Not-Ready Transit", 70.0, "C", shapes=(10, 0))
    write_latest("unmeasured1", "Unmeasured Transit", 85.0, "B")  # no shapes_readiness at all
    write_latest("ca1", "Canadian Transit", 88.0, "A", country="CA", shapes=(10, 10))
    payload = build_rollup(Rollup("all", "All", ()), WHEN)

    assert payload["shapes_readiness"] == {
        "ready": 1,
        "at_risk": 1,
        "not_ready": 1,
        "not_measured": 2,  # the un-checked artifact and the non-US agency
        "total": 5,
    }
    statuses = {m["id"]: m["shapes_status"] for m in payload["members"]}
    assert statuses == {
        "ready1": "ready",
        "risk1": "at_risk",
        "notready1": "not_ready",
        "unmeasured1": None,
        "ca1": None,
    }


def test_rollup_shapes_readiness_all_zero_when_nothing_measured() -> None:
    write_latest("a", "A Transit", 90.0, "A")
    payload = build_rollup(Rollup("all", "All", ()), WHEN)
    assert payload["shapes_readiness"] == {
        "ready": 0,
        "at_risk": 0,
        "not_ready": 0,
        "not_measured": 1,
        "total": 1,
    }
