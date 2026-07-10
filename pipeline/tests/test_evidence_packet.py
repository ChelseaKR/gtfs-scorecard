"""Tests for agency-scoped vendor remediation evidence packets."""

from __future__ import annotations

import json
from pathlib import Path

from scorecard_pipeline.cli import main
from scorecard_pipeline.evidence_packet import (
    build_evidence_packet,
    render_evidence_packet_markdown,
)


def _artifact() -> dict[str, object]:
    return {
        "schema_version": "1.5",
        "snapshot_date": "2026-07-02",
        "generated_at": "2026-07-02T13:00:00+00:00",
        "rubric_version": "1.1",
        "validator_version": "8.0.1",
        "agency": {"id": "small-town", "name": "Small Town Transit"},
        "feed": {
            "static_url": "https://transit.example/gtfs.zip",
            "sha256": "a" * 64,
        },
        "overall": {"grade": "C", "score": 74.2},
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
    assert first["packet_id"] == second["packet_id"]
    assert first["baseline"]["feed_sha256"] == "a" * 64
    assert first["baseline"]["validator_version"] == "8.0.1"
    assert first["work_items"][0]["acceptance_test"]["expected_instances"] == 0
    assert "not a vendor ranking" in first["completion"]["note"]


def test_markdown_is_forwardable_and_names_exact_acceptance_test() -> None:
    out = render_evidence_packet_markdown(build_evidence_packet(_artifact()))
    assert "# GTFS remediation packet: Small Town Transit" in out
    assert "`missing_trip_headsign` has 0 instances" in out
    assert "Feed SHA-256" in out
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
