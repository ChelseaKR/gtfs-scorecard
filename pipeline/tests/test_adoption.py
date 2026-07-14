"""Tests for the national GTFS-capability adoption rollup (adoption.py)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.adoption import adoption_record, national_adoption


def _art(
    aid: str,
    name: str,
    state: str,
    *,
    measured: bool = True,
    fares: str = "none",
    flex: bool = False,
    pathways: bool = False,
    step_free: bool = False,
    no_details: bool = False,
    country: str | None = None,
    subdivision_code: str = "",
    subdivision_name: str = "",
) -> dict[str, Any]:
    comp: dict[str, Any] = {"status": "measured" if measured else "not_measured", "details": {}}
    if measured and not no_details:
        comp["details"] = {
            "fares": {"model": fares},
            "flex": {"has_flex": flex},
            "pathways": {"has_pathways": pathways, "has_step_free": step_free},
        }
    agency = {
        "id": aid,
        "name": name,
        "state": state,
        "subdivision_code": subdivision_code,
        "subdivision_name": subdivision_name,
    }
    if country is not None:
        agency["country"] = country
    return {
        "agency": agency,
        "categories": {"completeness": comp},
    }


def test_record_extracts_capabilities() -> None:
    r = adoption_record(_art("a", "A", "CA", fares="v2", flex=True, pathways=True, step_free=True))
    assert r is not None
    assert r["has_flex"] and r["has_fares"] and r["has_fares_v2"]
    assert r["has_pathways"] and r["has_step_free"]
    assert r["fare_model"] == "v2" and r["state"] == "CA"
    assert r["country"] == "US"  # omitted historical country keeps the API default


def test_record_skips_unmeasured_or_missing_details() -> None:
    assert adoption_record(_art("a", "A", "CA", measured=False)) is None
    assert adoption_record(_art("a", "A", "CA", no_details=True)) is None


def test_legacy_fares_is_not_v2() -> None:
    r = adoption_record(_art("a", "A", "CA", fares="legacy"))
    assert r is not None
    assert r["has_fares"] and not r["has_fares_v2"] and r["fare_model"] == "legacy"


def test_national_adoption_counts_shares_and_state_split() -> None:
    raw = [
        adoption_record(_art("a", "A", "CA", fares="v2", flex=True, pathways=True)),
        adoption_record(_art("b", "B", "CA", fares="legacy")),
        adoption_record(_art("c", "C", "NY")),  # publishes nothing new
        adoption_record(_art("d", "D", "", flex=True)),  # empty state -> Unlocated
    ]
    records: list[dict[str, Any]] = [r for r in raw if r is not None]
    nat = national_adoption(records, top=5)
    assert nat["agency_count"] == 4
    assert nat["flex"] == {"count": 2, "pct": 50.0}
    assert nat["fares"]["count"] == 2  # v2 + legacy
    assert nat["fares_v2"]["count"] == 1
    assert nat["pathways"]["count"] == 1
    assert nat["fare_models"] == {"none": 2, "legacy": 1, "v2": 1}
    ca = next(s for s in nat["states"] if s["state"] == "CA")
    assert ca["agencies"] == 2 and ca["flex"] == 1 and ca["fares"] == 2 and ca["fares_v2"] == 1
    assert any(s["state"] == "Unlocated" for s in nat["states"])
    assert {m["id"] for m in nat["flex_sample"]} == {"a", "d"}
    assert [m["id"] for m in nat["fares_v2_sample"]] == ["a"]


def test_empty_input() -> None:
    nat = national_adoption([])
    assert nat["measured_feed_record_count"] == 0
    assert nat["agency_count"] == 0 and nat["flex"]["pct"] == 0.0


def test_portable_country_and_subdivision_adoption_rollups() -> None:
    raw = [
        adoption_record(_art("us", "US", "California", flex=True)),
        adoption_record(
            _art(
                "ca-on",
                "Ontario",
                "",
                country="CA",
                subdivision_code="CA-ON",
                subdivision_name="Ontario",
                fares="v2",
            )
        ),
        adoption_record(_art("ca-any", "Canada", "", country="CA", pathways=True)),
    ]
    records = [record for record in raw if record is not None]
    nat = national_adoption(records)
    assert [state["state"] for state in nat["states"]] == ["California"]
    countries = {row["country_code"]: row for row in nat["countries"]}
    assert countries["CA"]["feed_records"] == 2
    assert countries["US"]["flex"] == 1
    assert countries["CA"]["agencies"] == 2
    assert countries["CA"]["fares_v2"] == 1
    subdivisions = {row["subdivision_code"]: row for row in countries["CA"]["subdivisions"]}
    assert subdivisions["CA-ON"]["subdivision_name"] == "Ontario"
    assert subdivisions[None]["subdivision_name"] == "Unlocated"
