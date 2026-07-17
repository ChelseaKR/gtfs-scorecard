"""Tests for agency-scoped vendor remediation evidence packets."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from scorecard_pipeline.cli import main
from scorecard_pipeline.evidence_packet import (
    acceptance_test_passes,
    build_evidence_packet,
    render_evidence_packet_markdown,
)


def _artifact() -> dict[str, Any]:
    return {
        "schema_version": "1.5",
        "snapshot_date": "2026-07-02",
        "generated_at": "2026-07-02T13:00:00+00:00",
        "rubric_version": "1.1",
        "scoring_profile": {"id": "gtfs-scorecard-1.1", "rubric_version": "1.1"},
        "validator_version": "8.0.1",
        "agency": {"id": "small-town", "name": "Small Town Transit"},
        "feed": {
            "static_url": "https://transit.example/gtfs.zip",
            "sha256": "a" * 64,
        },
        "overall": {"grade": "C", "score": 74.2},
        "categories": {
            "correctness": {
                "status": "measured",
                "score": 74.2,
                "findings": [{"code": "missing_trip_headsign", "count": 12}],
            }
        },
        "top_fixes": [
            {
                "rank": 1,
                "code": "missing_trip_headsign",
                "count": 12,
                "severity": "WARNING",
                "what": "Twelve trips have no rider-facing destination.",
                "why": "Riders cannot tell which direction the bus is going.",
                "fix": "Export a trip_headsign for every trip.",
                "effort": "Usually one export mapping.",
                "owner": "Likely your export tool",
            }
        ],
    }


def test_packet_is_deterministic_and_carries_reproducibility_evidence() -> None:
    first = build_evidence_packet(_artifact())
    second = build_evidence_packet(_artifact())

    assert first == second
    assert first["schema_version"] == "1.1"
    assert first["packet_id"] == second["packet_id"]
    assert first["baseline"]["feed_sha256"] == "a" * 64
    assert first["baseline"]["validator_version"] == "8.0.1"
    assert first["baseline"]["scoring_profile_id"] == "gtfs-scorecard-1.1"
    assert first["baseline"]["reader_archive_profile"] == "raw-v1"
    assert first["baseline"]["measured_categories"] == ["correctness"]
    acceptance = first["work_items"][0]["acceptance_test"]
    assert acceptance["expected_instances"] == 0
    assert acceptance["category"] == "correctness"
    assert acceptance["required_category_status"] == "measured"
    assert acceptance["rubric_version"] == "1.1"
    assert acceptance["scoring_profile_id"] == "gtfs-scorecard-1.1"
    assert acceptance["scoring_profile_rubric_version"] == "1.1"
    assert acceptance["validator_version"] == "8.0.1"
    assert acceptance["reader_archive_profile"] == "raw-v1"
    assert acceptance["measured_categories"] == ["correctness"]
    assert "not a vendor ranking" in first["completion"]["note"]


def test_packet_identity_changes_with_reader_archive_profile() -> None:
    raw = _artifact()
    normalized = _artifact()
    normalized["fetch"] = {"reader_archive_profile": "flat-single-root-v1"}

    raw_packet = build_evidence_packet(raw)
    normalized_packet = build_evidence_packet(normalized)

    assert raw_packet["packet_id"] != normalized_packet["packet_id"]
    assert normalized_packet["baseline"]["reader_archive_profile"] == ("flat-single-root-v1")


def test_packet_identity_covers_scoring_profile_and_measured_categories() -> None:
    baseline = _artifact()
    different_profile = _artifact()
    different_profile["scoring_profile"] = {
        "id": "gtfs-scorecard-experimental",
        "rubric_version": "1.1",
    }
    different_profile_rubric = _artifact()
    different_profile_rubric["scoring_profile"] = {
        "id": "gtfs-scorecard-1.1",
        "rubric_version": "1.2",
    }
    realtime_measured = _artifact()
    realtime_measured["categories"]["realtime"] = {
        "status": "measured",
        "score": 90.0,
        "findings": [],
    }

    baseline_packet = build_evidence_packet(baseline)
    assert build_evidence_packet(different_profile)["packet_id"] != baseline_packet["packet_id"]
    assert (
        build_evidence_packet(different_profile_rubric)["packet_id"] != baseline_packet["packet_id"]
    )
    realtime_packet = build_evidence_packet(realtime_measured)
    assert realtime_packet["packet_id"] != baseline_packet["packet_id"]
    assert realtime_packet["baseline"]["measured_categories"] == [
        "correctness",
        "realtime",
    ]


def test_acceptance_fails_closed_if_finding_category_becomes_unmeasured() -> None:
    baseline = _artifact()
    acceptance = build_evidence_packet(baseline)["work_items"][0]["acceptance_test"]

    corrected = deepcopy(baseline)
    corrected["categories"]["correctness"]["findings"] = []
    corrected["top_fixes"] = []
    assert acceptance_test_passes(acceptance, corrected)

    no_longer_measured = deepcopy(corrected)
    no_longer_measured["categories"]["correctness"] = {
        "status": "not_yet_measured",
        "findings": [],
    }
    assert not acceptance_test_passes(acceptance, no_longer_measured)


def test_acceptance_requires_the_full_baseline_producer_contract() -> None:
    baseline = _artifact()
    acceptance = build_evidence_packet(baseline)["work_items"][0]["acceptance_test"]
    corrected = deepcopy(baseline)
    corrected["categories"]["correctness"]["findings"] = []
    corrected["scoring_profile"] = {
        "id": "gtfs-scorecard-experimental",
        "rubric_version": "1.1",
    }

    assert not acceptance_test_passes(acceptance, corrected)


def test_markdown_is_forwardable_and_names_exact_acceptance_test() -> None:
    out = render_evidence_packet_markdown(build_evidence_packet(_artifact()))
    assert "# GTFS remediation packet: Small Town Transit" in out
    assert "`missing_trip_headsign` has 0 instances" in out
    assert "Feed SHA-256" in out
    assert "Reader archive profile: raw-v1" in out
    assert "Measured categories: correctness" in out
    assert "`correctness` remains measured" in out
    assert "baseline rubric, scoring profile, validator" in out
    assert "- [ ] Publish corrected GTFS" in out


def test_cli_writes_json_packet(tmp_path: Path, isolated_repo_root: Path) -> None:
    isolated_repo_root.mkdir(parents=True, exist_ok=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: small-town\n"
        "    name: Small Town Transit\n"
        "    static_gtfs_url: https://transit.example/gtfs.zip\n"
    )
    source = tmp_path / "artifact.json"
    output = tmp_path / "packet.json"
    source.write_text(json.dumps(_artifact()))

    assert main(["evidence-packet", str(source), "--out", str(output)]) == 0
    packet = json.loads(output.read_text())
    assert packet["agency"]["id"] == "small-town"
    assert packet["status"] == "open"
