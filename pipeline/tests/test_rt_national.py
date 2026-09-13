"""Tests for the national realtime-reliability rollup (rt_national.py)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from scorecard_pipeline.config import AGENCIES, Agency
from scorecard_pipeline.rt_national import national_rt, observed_vintage, reliability_band


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


def test_retired_alias_health_is_not_counted_as_current(
    monkeypatch: Any,
) -> None:
    live = Agency("live", "Live Transit", "https://example.org/live.zip")
    retired = Agency(
        "retired",
        "Retired Transit export",
        "https://archive.example.org/retired.zip",
        alias_of=live.id,
        feed_status="deprecated",
    )
    monkeypatch.setitem(AGENCIES, live.id, live)
    monkeypatch.setitem(AGENCIES, retired.id, retired)

    nat = national_rt([_summary(retired.id, uptime=10.0), _summary(live.id, uptime=100.0)])

    assert nat["monitored_feed_record_count"] == 1
    assert [record["id"] for record in nat["most_reliable"]] == [live.id]


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


# --- the vintage of the inputs (#389) -------------------------------------------------------


def _at(day: str) -> int:
    """Midday UTC on a date, as the monitor records timestamps."""
    return int(dt.datetime.fromisoformat(f"{day}T12:00:00+00:00").timestamp())


def test_observed_vintage_reports_the_spread_not_one_date() -> None:
    """A rollup has as many vintages as members; one date would hide the tail."""
    vintage = observed_vintage(
        [
            {"id": "fresh", "last_ts": _at("2026-09-12")},
            {"id": "middle", "last_ts": _at("2026-09-05")},
            {"id": "stale", "last_ts": _at("2026-06-30")},
        ]
    )
    assert vintage["newest_last_observation"] == "2026-09-12"
    assert vintage["median_last_observation"] == "2026-09-05"
    assert vintage["oldest_last_observation"] == "2026-06-30"
    assert vintage["feed_records_dated"] == 3
    assert vintage["feed_records_undated"] == 0


def test_observed_vintage_counts_undated_members_instead_of_dropping_them() -> None:
    """A member with no recorded date is absence, and the payload says so.

    Dropping it would shrink the denominator silently and leave three dates
    describing a corpus larger than the one they were computed over.
    """
    vintage = observed_vintage(
        [
            {"id": "dated", "last_ts": _at("2026-09-12")},
            {"id": "undated", "last_ts": None},
            {"id": "missing-key"},
        ]
    )
    assert vintage["feed_records_dated"] == 1
    assert vintage["feed_records_undated"] == 2
    assert vintage["newest_last_observation"] == "2026-09-12"


def test_observed_vintage_publishes_no_date_when_nobody_recorded_one() -> None:
    """Never the build date, and never a zero: the fields are null and counted."""
    vintage = observed_vintage([{"id": "a"}, {"id": "b", "last_ts": None}])
    assert vintage["feed_records_dated"] == 0
    assert vintage["feed_records_undated"] == 2
    assert vintage["oldest_last_observation"] is None
    assert vintage["median_last_observation"] is None
    assert vintage["newest_last_observation"] is None


def test_national_rt_carries_the_vintage_of_its_inputs(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The rollup the API and the page both read states when it was gathered."""
    monkeypatch.setitem(AGENCIES, "a", Agency(id="a", name="A", static_gtfs_url="https://a.test"))
    monkeypatch.setitem(AGENCIES, "b", Agency(id="b", name="B", static_gtfs_url="https://b.test"))
    nat = national_rt(
        [
            {**_summary("a", uptime=100.0), "last_ts": _at("2026-09-12")},
            {**_summary("b", uptime=95.0), "last_ts": _at("2026-09-05")},
        ]
    )
    assert nat["observed"] == {
        "feed_records_dated": 2,
        "feed_records_undated": 0,
        "oldest_last_observation": "2026-09-05",
        "median_last_observation": "2026-09-05",
        "newest_last_observation": "2026-09-12",
    }
