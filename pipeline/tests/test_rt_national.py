"""Tests for the national realtime-reliability rollup (rt_national.py)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.config import AGENCIES, Agency
from scorecard_pipeline.rt_national import national_rt, reliability_band


def _summary(
    agency_id: str,
    *,
    name: str | None = None,
    state: str = "CA",
    observations: int = 5,
    uptime: float = 100.0,
    lag: int | None = 5,
    country: str | None = None,
    subdivision_code: str = "",
    subdivision_name: str = "",
) -> dict[str, Any]:
    summary = {
        "id": agency_id,
        "name": name or agency_id,
        "state": state,
        "observations": observations,
        "uptime_pct": uptime,
        "median_lag_seconds": lag,
    }
    if country is not None:
        summary.update(
            {
                "country": country,
                "subdivision_code": subdivision_code,
                "subdivision_name": subdivision_name,
            }
        )
    return summary


def test_reliability_bands() -> None:
    assert reliability_band(100.0) == "reliable"
    assert reliability_band(99.0) == "reliable"
    assert reliability_band(98.9) == "mostly"
    assert reliability_band(90.0) == "mostly"
    assert reliability_band(89.9) == "spotty"


def test_national_rt_bands_and_medians() -> None:
    summaries = [
        _summary("a", uptime=100.0, lag=4, state="CA"),
        _summary("b", uptime=95.0, lag=10, state="CA"),
        _summary("c", uptime=80.0, lag=30, state="OR"),
    ]
    nat = national_rt(summaries)
    assert nat["monitored_feed_record_count"] == 3
    assert nat["monitored_count"] == 3
    assert nat["bands"] == {"reliable": 1, "mostly": 1, "spotty": 1}
    assert nat["median_uptime_pct"] == 95.0
    assert nat["median_lag_seconds"] == 10
    assert [m["id"] for m in nat["most_reliable"]] == ["a", "b", "c"]


def test_unmonitored_agencies_dropped() -> None:
    summaries = [
        _summary("a", observations=5, uptime=100.0),
        _summary("never", observations=0, uptime=0.0),
    ]
    nat = national_rt(summaries)
    assert nat["monitored_count"] == 1
    assert nat["bands"]["reliable"] == 1


def test_ranking_requires_minimum_observations() -> None:
    # A one-sample 100% feed must not outrank a well-observed feed.
    summaries = [
        _summary("lucky", observations=1, uptime=100.0, lag=1),
        _summary("proven", observations=50, uptime=99.5, lag=8),
    ]
    nat = national_rt(summaries)
    ids = [m["id"] for m in nat["most_reliable"]]
    assert "lucky" not in ids
    assert ids == ["proven"]


def test_per_state_rollup_and_tiebreak_lag() -> None:
    summaries = [
        _summary("ca1", state="CA", uptime=100.0, lag=20),
        _summary("ca2", state="CA", uptime=100.0, lag=5),
        _summary("or1", state="OR", uptime=92.0, lag=5),
    ]
    nat = national_rt(summaries)
    states = nat["states"]
    assert states[0]["state"] == "CA"
    assert states[0]["agencies"] == 2
    assert states[0]["reliable"] == 2
    # Equal uptime -> the fresher (lower lag) feed ranks first.
    assert [m["id"] for m in nat["most_reliable"][:2]] == ["ca2", "ca1"]


def test_missing_lag_does_not_crash_ranking() -> None:
    summaries = [
        _summary("a", uptime=100.0, lag=None),
        _summary("b", uptime=100.0, lag=3),
    ]
    nat = national_rt(summaries)
    # b (has lag) ranks above a (no lag, sorts last on the freshness key).
    assert [m["id"] for m in nat["most_reliable"]] == ["b", "a"]
    assert nat["median_lag_seconds"] == 3


def test_empty_input_is_safe() -> None:
    nat = national_rt([])
    assert nat["monitored_count"] == 0
    assert nat["bands"] == {"reliable": 0, "mostly": 0, "spotty": 0}
    assert nat["median_uptime_pct"] is None
    assert nat["states"] == []
    assert nat["countries"] == []
    assert nat["most_reliable"] == []


def test_portable_country_and_subdivision_realtime_rollups() -> None:
    summaries = [
        _summary("us", state="California", uptime=99.0),
        _summary(
            "ca-on",
            state="",
            country="CA",
            subdivision_code="CA-ON",
            subdivision_name="Ontario",
            uptime=100.0,
        ),
        _summary("ca-any", state="", country="CA", uptime=90.0),
    ]
    nat = national_rt(summaries)
    assert [state["state"] for state in nat["states"]] == ["California"]
    countries = {row["country_code"]: row for row in nat["countries"]}
    assert countries["CA"]["feed_records"] == 2
    assert countries["US"]["reliable"] == 1
    assert countries["CA"]["agencies"] == 2
    assert countries["CA"]["median_uptime_pct"] == 95.0
    subdivisions = {row["subdivision_code"]: row for row in countries["CA"]["subdivisions"]}
    assert subdivisions["CA-ON"]["reliable"] == 1
    assert subdivisions[None]["subdivision_name"] == "Unlocated"


def test_realtime_uses_registry_location_for_legacy_health_summary(
    monkeypatch: Any,
) -> None:
    agency = Agency(
        id="registry-ca",
        name="Registry Canada",
        static_gtfs_url="https://example.ca/gtfs.zip",
        country="CA",
        subdivision_code="CA-ON",
        subdivision_name="Ontario",
    )
    monkeypatch.setitem(AGENCIES, agency.id, agency)
    nat = national_rt([_summary(agency.id, state="")])
    assert nat["states"] == []
    assert nat["countries"][0]["country_code"] == "CA"
    assert nat["countries"][0]["subdivisions"][0]["subdivision_code"] == "CA-ON"
