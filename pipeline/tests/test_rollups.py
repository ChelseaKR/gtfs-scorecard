"""Tests for program rollup artifacts."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.config import Agency, artifacts_dir, register, repo_root
from scorecard_pipeline.rollups import (
    Rollup,
    build_rollup,
    load_rollups,
    publish_rollups,
    rollup_csv,
)
from scorecard_pipeline.validate import VALIDATOR_VERSION

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
    scoring_profile_id: str = SCORING_PROFILE_ID,
    validator_version: str = VALIDATOR_VERSION,
    reader_archive_profile: str | None = None,
) -> None:
    agency: dict[str, object] = {"id": agency_id, "name": name}
    if state:
        agency["state"] = state
    if country:
        agency["country"] = country
    payload: dict[str, object] = {
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile": {
            "id": scoring_profile_id,
            "rubric_version": RUBRIC_VERSION,
        },
        "validator_version": validator_version,
        "agency": agency,
        "snapshot_date": "2026-06-12",
        "overall": {"score": score, "grade": grade},
        "feed": {"sha256": f"sha-{agency_id}"},
        "categories": {
            "correctness": {"status": "measured", "score": score},
            "freshness": {
                "status": "measured",
                "score": score,
                "details": {"days_until_expiry": days},
            },
            "completeness": {"status": "measured", "score": score},
            "realtime": {"status": "not_yet_measured"},
        },
        "top_fixes": fixes or [],
    }
    if reader_archive_profile is not None:
        payload["fetch"] = {"reader_archive_profile": reader_archive_profile}
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


def test_country_rollup_auto_includes_agencies_by_artifact_country() -> None:
    write_latest("on1", "Ontario One", 80.0, "B", country="CA")
    write_latest("bc1", "BC One", 70.0, "C", country="ca")  # case-insensitive
    write_latest("gb1", "GB One", 90.0, "A", country="GB")
    write_latest("legacy", "Legacy US", 85.0, "B")  # no country: a US record by contract
    rollup = Rollup(id="country-ca", name="Canada", member_ids=(), country="CA")
    payload = build_rollup(rollup, WHEN)
    assert payload["agency_count"] == 2
    assert sorted(m["id"] for m in payload["members"]) == ["bc1", "on1"]


def test_country_rollup_treats_legacy_artifacts_as_us_records() -> None:
    write_latest("legacy", "Legacy US", 85.0, "B")  # predates the country field
    write_latest("ca1", "Canada One", 80.0, "B", country="CA")
    rollup = Rollup(id="country-us", name="United States", member_ids=(), country="US")
    payload = build_rollup(rollup, WHEN)
    assert [m["id"] for m in payload["members"]] == ["legacy"]


def test_country_rollup_prefers_registry_country_over_artifact() -> None:
    # The curated registry is the authoritative location; a stale artifact
    # country must not move an agency between country cohorts.
    register(Agency("moved", "Moved", "https://example.com/moved.zip", country="CA"))
    register(Agency("stays", "Stays", "https://example.com/stays.zip"))
    write_latest("moved", "Moved", 80.0, "B", country="US")
    write_latest("stays", "Stays", 75.0, "C")
    rollup = Rollup(id="country-ca", name="Canada", member_ids=(), country="CA")
    payload = build_rollup(rollup, WHEN)
    assert [m["id"] for m in payload["members"]] == ["moved"]


def test_load_rollups_parses_country_selector(tmp_path: Path) -> None:
    config = tmp_path / "rollups.yaml"
    config.write_text("rollups:\n  - id: country-ca\n    name: Canada\n    country: ca\n")
    (rollup,) = load_rollups(config)
    assert rollup.country == "CA"
    assert rollup.state is None
    assert rollup.member_ids == ()


def test_load_rollups_rejects_state_and_country_together(tmp_path: Path) -> None:
    config = tmp_path / "rollups.yaml"
    config.write_text("rollups:\n  - id: bad\n    name: Bad\n    state: CA\n    country: CA\n")
    with pytest.raises(ValueError, match="state or country, not both"):
        load_rollups(config)


def test_load_rollups_rejects_unassigned_country_code(tmp_path: Path) -> None:
    config = tmp_path / "rollups.yaml"
    config.write_text("rollups:\n  - id: bad\n    name: Bad\n    country: XX\n")
    with pytest.raises(ValueError, match="ISO 3166-1"):
        load_rollups(config)


def test_country_rollup_payload_carries_iso_identity() -> None:
    write_latest("ca1", "Canada One", 80.0, "B", country="CA")
    rollup = Rollup(id="country-ca", name="Canada", member_ids=(), country="CA")
    payload = build_rollup(rollup, WHEN)
    assert payload["rollup"]["country_code"] == "CA"
    assert payload["rollup"]["country_name"] == "Canada"
    # Non-country rollups keep their exact prior shape: no country keys at all.
    plain = build_rollup(Rollup(id="all", name="All tracked agencies", member_ids=()), WHEN)
    assert "country_code" not in plain["rollup"]
    assert "country_name" not in plain["rollup"]


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
    # Same feeds, no ridership map: falls back to alphabetical attention order.
    write_latest("big", "Big Transit", 66.0, "D", ntd_id="90001")
    write_latest("tiny", "Tiny Transit", 64.0, "D", ntd_id="90002")
    attention = {"big": "Feed expires in 5 days", "tiny": "Feed expires in 3 days"}
    payload = build_rollup(Rollup("all", "All", ()), WHEN, attention, None)
    assert [m["id"] for m in payload["members"]] == ["big", "tiny"]
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


def test_duplicate_ntd_reporter_ids_are_quarantined_from_ridership_ordering() -> None:
    write_latest("first", "First", 70.0, "C", ntd_id="90001")
    write_latest("second", "Second", 72.0, "C", ntd_id="90001")
    write_latest("unique", "Unique", 74.0, "C", ntd_id="90002")
    attention = {member: "Feed expires soon" for member in ("first", "second", "unique")}
    payload = build_rollup(
        Rollup("all", "All", ()),
        WHEN,
        attention,
        {"90001": 9_000_000, "90002": 1_000},
    )

    members = {member["id"]: member for member in payload["members"]}
    assert members["first"]["annual_trips"] is None
    assert members["second"]["annual_trips"] is None
    assert members["unique"]["annual_trips"] == 1_000


def test_registry_duplicate_is_quarantined_when_sibling_has_no_rollup_artifact() -> None:
    register(Agency("visible", "Visible", "https://example.com/visible.zip", ntd_id="00007"))
    register(Agency("hidden", "Hidden", "https://example.com/hidden.zip", ntd_id="00007"))
    write_latest("visible", "Visible", 90.0, "A", ntd_id="00007")

    payload = build_rollup(
        Rollup("all", "All", ()),
        WHEN,
        {"visible": "Feed expires soon"},
        {"7": 1_000_000},
    )

    assert payload["members"][0]["annual_trips"] is None


def test_common_fixes_counts_shared_codes() -> None:
    shared = {
        "code": "scorecard_wheelchair_boarding_unknown",
        "fix": "Set wheelchair_boarding on every stop.",
    }
    write_latest("a", "A", 70.0, "C", fixes=[shared])
    write_latest("b", "B", 72.0, "C", fixes=[shared])
    write_latest(
        "old-validator",
        "Old validator",
        74.0,
        "C",
        fixes=[shared],
        validator_version="7.0.0",
    )
    write_latest("c", "C", 75.0, "C", fixes=[{"code": "other", "fix": "Other fix."}])
    payload = build_rollup(Rollup("all", "All", ()), WHEN)
    common = payload["common_fixes"]
    assert len(common) == 1
    assert common[0]["agencies"] == 2
    assert common[0]["code"] == "scorecard_wheelchair_boarding_unknown"
    assert payload["comparison"]["exclusion_counts"]["validator_version_mismatch"] == 1


def test_rollup_members_carry_the_top_finding_code_for_handoff_links() -> None:
    finding = {
        "code": "scorecard_wheelchair_boarding_unknown",
        "fix": "Set wheelchair_boarding on every stop.",
    }
    write_latest("a", "A", 70.0, "C", fixes=[finding])

    payload = build_rollup(Rollup("all", "All", ()), WHEN)

    assert payload["members"][0]["top_fix"] == finding["fix"]
    assert payload["members"][0]["top_fix_code"] == finding["code"]


def test_rollup_excludes_a_normalized_reader_profile_from_aggregates() -> None:
    write_latest("raw", "Raw", 80.0, "B")
    write_latest(
        "normalized",
        "Normalized",
        100.0,
        "A",
        reader_archive_profile="flat-single-root-v1",
    )

    payload = build_rollup(Rollup("all", "All", ()), WHEN)

    assert payload["agency_count"] == 2
    assert payload["average_score"] == 80.0
    assert payload["comparison"]["eligible_count"] == 1
    assert payload["comparison"]["required_reader_archive_profile"] == "raw-v1"
    assert payload["comparison"]["exclusion_counts"] == {"reader_archive_profile_mismatch": 1}


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


def test_state_rollups_do_not_publish_percentiles() -> None:
    write_latest("hi1", "HI One", 95.0, "A", state="HI")
    write_latest("mid1", "MID One", 60.0, "D", state="MID")
    write_latest("lo1", "LO One", 20.0, "F", state="LO")
    config = repo_root() / "rollups.yaml"
    config.write_text(
        "rollups:\n"
        "  - id: all\n    name: All\n    all: true\n"
        "  - id: hi\n    name: HI\n    state: HI\n"
        "  - id: mid\n    name: MID\n    state: MID\n"
        "  - id: lo\n    name: LO\n    state: LO\n"
    )
    publish_rollups(generated_at=WHEN)
    out = artifacts_dir() / "rollups"
    hi = json.loads((out / "hi.json").read_text())
    mid = json.loads((out / "mid.json").read_text())
    lo = json.loads((out / "lo.json").read_text())
    all_ = json.loads((out / "all.json").read_text())
    for payload in (hi, mid, lo, all_):
        assert payload["state_percentile"] is None
        assert payload["comparison"]["individual_percentiles_published"] is False


def test_state_percentile_absent_with_no_state_rollups() -> None:
    write_latest("a", "A Transit", 70.0, "C")
    publish_rollups(generated_at=WHEN)
    payload = json.loads((artifacts_dir() / "rollups" / "all.json").read_text())
    assert payload["state_percentile"] is None


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
