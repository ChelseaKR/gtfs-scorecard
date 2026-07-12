"""Tests for the national accessibility-coverage rollup (access.py)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.access import band_for, coverage_record, national_coverage


def _artifact(
    agency_id: str,
    *,
    name: str | None = None,
    state: str = "CA",
    boarding: float | None = 50.0,
    accessible: float | None = 40.0,
    stops: int | None = 100,
    status: str = "measured",
    country: str | None = None,
    subdivision_code: str = "",
    subdivision_name: str = "",
) -> dict[str, Any]:
    details: dict[str, Any] = {"stops": stops}
    if boarding is not None:
        details["wheelchair_boarding_pct"] = boarding
    if accessible is not None:
        details["wheelchair_accessible_pct"] = accessible
    details["accessibility"] = {"score": 50.0}
    agency = {
        "id": agency_id,
        "name": name or agency_id,
        "state": state,
        "subdivision_code": subdivision_code,
        "subdivision_name": subdivision_name,
    }
    if country is not None:
        agency["country"] = country
    return {
        "agency": agency,
        "categories": {"completeness": {"status": status, "details": details}},
    }


def test_band_thresholds() -> None:
    assert band_for(0.0) == "none"
    assert band_for(0.1) == "some"
    assert band_for(94.9) == "some"
    assert band_for(95.0) == "most"
    assert band_for(100.0) == "most"


def test_coverage_record_extracts_fields() -> None:
    rec = coverage_record(_artifact("a", name="Agency A", boarding=60.0, accessible=30.0))
    assert rec is not None
    assert rec["id"] == "a"
    assert rec["name"] == "Agency A"
    assert rec["wheelchair_boarding_pct"] == 60.0
    assert rec["wheelchair_accessible_pct"] == 30.0
    assert rec["country"] == "US"


def test_coverage_record_promotes_legacy_us_state_to_iso_subdivision() -> None:
    full_name = coverage_record(_artifact("full", state="California"))
    abbreviation = coverage_record(_artifact("abbr", state="CA"))

    assert full_name is not None
    assert abbreviation is not None
    assert (full_name["subdivision_code"], full_name["subdivision_name"]) == (
        "US-CA",
        "California",
    )
    assert (abbreviation["subdivision_code"], abbreviation["subdivision_name"]) == (
        "US-CA",
        "California",
    )


def test_coverage_record_skips_unmeasured_or_missing() -> None:
    # Not measured (no feed scored yet).
    assert coverage_record(_artifact("a", status="not_yet_measured")) is None
    # Measured but no stop count recorded.
    assert coverage_record(_artifact("b", stops=None)) is None
    # Measured but the boarding field is absent (older artifact).
    assert coverage_record(_artifact("c", boarding=None)) is None


def test_unlocated_state_falls_back() -> None:
    rec = coverage_record(_artifact("a", state=""))
    assert rec is not None
    assert rec["state"] == "Unlocated"


def test_national_coverage_bands_and_averages() -> None:
    raw = [
        coverage_record(_artifact("none1", boarding=0.0, state="CA")),
        coverage_record(_artifact("some1", boarding=50.0, state="CA")),
        coverage_record(_artifact("most1", boarding=100.0, state="OR")),
        coverage_record(_artifact("most2", boarding=96.0, state="OR")),
    ]
    records: list[dict[str, Any]] = [r for r in raw if r is not None]
    cov = national_coverage(records)
    assert cov["agency_count"] == 4
    assert cov["bands"] == {"none": 1, "some": 1, "most": 2}
    # (0 + 50 + 100 + 96) / 4 = 61.5
    assert cov["average_boarding_pct"] == 61.5
    # Most-complete list excludes the zero-coverage feed and is ranked desc.
    assert [m["id"] for m in cov["most_complete"]] == ["most1", "most2", "some1"]
    # The no-data feed is counted and sampled for follow-up.
    assert cov["no_data_count"] == 1
    assert [t["id"] for t in cov["to_improve_sample"]] == ["none1"]


def test_per_state_rollup_sorted_by_count() -> None:
    raw = [coverage_record(_artifact(f"ca{i}", state="CA", boarding=100.0)) for i in range(3)] + [
        coverage_record(_artifact("or1", state="OR", boarding=0.0))
    ]
    records: list[dict[str, Any]] = [r for r in raw if r is not None]
    cov = national_coverage(records)
    states = cov["states"]
    assert states[0]["state"] == "CA"
    assert states[0]["agencies"] == 3
    assert states[0]["most"] == 3
    assert states[1]["state"] == "OR"
    assert states[1]["none"] == 1


def test_empty_input_is_safe() -> None:
    cov = national_coverage([])
    assert cov["agency_count"] == 0
    assert cov["bands"] == {"none": 0, "some": 0, "most": 0}
    assert cov["average_boarding_pct"] is None
    assert cov["states"] == []
    assert cov["countries"] == []


def test_portable_country_and_subdivision_accessibility_rollups() -> None:
    raw = [
        coverage_record(_artifact("us", state="California", boarding=100.0)),
        coverage_record(
            _artifact(
                "ca-on",
                state="",
                country="CA",
                subdivision_code="CA-ON",
                subdivision_name="Ontario",
                boarding=50.0,
            )
        ),
        coverage_record(_artifact("ca-any", state="", country="CA", boarding=0.0)),
    ]
    records = [record for record in raw if record is not None]
    cov = national_coverage(records)
    assert [state["state"] for state in cov["states"]] == ["California"]
    countries = {row["country_code"]: row for row in cov["countries"]}
    assert countries["US"]["most"] == 1
    assert countries["US"]["subdivisions"][0]["subdivision_code"] == "US-CA"
    assert countries["CA"]["agencies"] == 2
    assert countries["CA"]["average_boarding_pct"] == 25.0
    subdivisions = {row["subdivision_code"]: row for row in countries["CA"]["subdivisions"]}
    assert subdivisions["CA-ON"]["average_boarding_pct"] == 50.0
    assert subdivisions[None]["none"] == 1
