"""Tests for the export content diff (EXP-18): fingerprint, diff, memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scorecard_pipeline import exportdiff
from scorecard_pipeline.config import artifacts_dir

FIXTURE_ZIP = str(Path(__file__).resolve().parent / "fixtures" / "unitrans_trimmed.zip")


def _structure(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "structure_schema": exportdiff.STRUCTURE_SCHEMA,
        "feed_sha256": "aaa",
        "routes": {"r5": "5 (E Street Express)", "r7": "7"},
        "stops": {"s1": [38.54, -121.74], "s2": [38.55, -121.73]},
        "trip_count": 100,
        "service_end": "2026-08-31",
    }
    base.update(overrides)
    return base


# ---- fingerprinting ----------------------------------------------------------


def test_summarize_reads_the_real_fixture_feed() -> None:
    structure = exportdiff.summarize_structure(FIXTURE_ZIP, "abc123")
    assert structure["feed_sha256"] == "abc123"
    assert structure["structure_schema"] == exportdiff.STRUCTURE_SCHEMA
    assert structure["routes"], "the trimmed Unitrans feed declares routes"
    assert structure["stops"], "the trimmed Unitrans feed declares located stops"
    assert structure["trip_count"] > 0
    assert structure["service_end"], "the fixture calendar has an end date"
    # Positions round to 5 decimal places so the fingerprint is byte-stable.
    lat, lon = next(iter(structure["stops"].values()))
    assert lat == round(lat, 5) and lon == round(lon, 5)


# ---- diff sentences ----------------------------------------------------------


def test_identical_structures_report_nothing() -> None:
    assert exportdiff.diff_structures(_structure(), _structure(feed_sha256="bbb")) == []


def test_removed_and_added_routes_are_named() -> None:
    prev = _structure()
    curr = _structure(routes={"r7": "7", "r9": "9 (New Crosstown)"})
    changes = exportdiff.diff_structures(prev, curr)
    assert "Route 5 (E Street Express) is no longer in the export." in changes
    assert "Route 9 (New Crosstown) is new in this export." in changes


def test_many_route_changes_are_bounded_not_flooded() -> None:
    prev = _structure(routes={f"r{i}": f"Route {i:02d}" for i in range(10)})
    curr = _structure(routes={})
    (sentence,) = exportdiff.diff_structures(prev, curr)
    assert "and 5 more" in sentence


def test_stop_moves_additions_and_removals_are_counted() -> None:
    prev = _structure()
    curr = _structure(
        stops={
            "s1": [38.54, -121.74],  # unchanged
            "s2": [38.56, -121.73],  # ~1.1 km north: moved
            "s3": [38.55, -121.75],  # new
        }
    )
    changes = exportdiff.diff_structures(prev, curr)
    assert "1 new stop appeared." in changes
    assert "1 stop moved more than 100 m." in changes
    prev_two = _structure()
    gone = exportdiff.diff_structures(prev_two, _structure(stops={"s1": [38.54, -121.74]}))
    assert "1 stop left the export." in gone


def test_small_position_noise_is_not_a_move() -> None:
    prev = _structure()
    curr = _structure(stops={"s1": [38.5401, -121.74], "s2": [38.55, -121.73]})  # ~11 m
    assert exportdiff.diff_structures(prev, curr) == []


def test_trip_count_needs_a_tenth_to_speak() -> None:
    prev = _structure(trip_count=100)
    assert exportdiff.diff_structures(prev, _structure(trip_count=95)) == []
    (sentence,) = exportdiff.diff_structures(prev, _structure(trip_count=80))
    assert sentence == "The export now has 80 trips, 20 fewer than before."


def test_service_end_change_names_both_dates() -> None:
    changes = exportdiff.diff_structures(_structure(), _structure(service_end="2026-12-31"))
    assert changes == ["Service now runs through 2026-12-31 (was 2026-08-31)."]


# ---- memory and the per-run entry point --------------------------------------


def test_first_run_bootstraps_memory_without_a_diff() -> None:
    assert exportdiff.export_diff("acme", FIXTURE_ZIP, "sha-one") is None
    saved = exportdiff.load_structure("acme")
    assert saved is not None and saved["feed_sha256"] == "sha-one"


def test_unchanged_feed_reports_nothing() -> None:
    exportdiff.export_diff("acme", FIXTURE_ZIP, "sha-one")
    assert exportdiff.export_diff("acme", FIXTURE_ZIP, "sha-one") is None


def test_changed_feed_with_structural_moves_returns_the_block() -> None:
    exportdiff.export_diff("acme", FIXTURE_ZIP, "sha-one")
    # Simulate yesterday's export having had one more route than the fixture.
    remembered = exportdiff.load_structure("acme")
    assert remembered is not None
    remembered["routes"] = {**remembered["routes"], "ghost": "99 (Discontinued)"}
    exportdiff.save_structure("acme", remembered)

    block = exportdiff.export_diff("acme", FIXTURE_ZIP, "sha-two")
    assert block is not None
    assert block["from_sha256"] == "sha-one" and block["to_sha256"] == "sha-two"
    assert block["changes"] == ["Route 99 (Discontinued) is no longer in the export."]
    # Memory advanced, so the same export tomorrow is quiet again.
    assert exportdiff.export_diff("acme", FIXTURE_ZIP, "sha-two") is None


def test_changed_bytes_with_identical_structure_stay_quiet() -> None:
    exportdiff.export_diff("acme", FIXTURE_ZIP, "sha-one")
    assert exportdiff.export_diff("acme", FIXTURE_ZIP, "sha-two") is None


def test_foreign_or_corrupt_memory_is_discarded_not_trusted() -> None:
    path = artifacts_dir() / "acme" / "structure.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert exportdiff.load_structure("acme") is None
    path.write_text('{"structure_schema": 999, "feed_sha256": "x"}')
    assert exportdiff.load_structure("acme") is None
    # A run over corrupt memory bootstraps cleanly instead of diffing lies.
    assert exportdiff.export_diff("acme", FIXTURE_ZIP, "sha-one") is None
