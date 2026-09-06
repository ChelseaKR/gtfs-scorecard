"""Tests for the NTD readiness portfolio roll-up (pure)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.ntd import (
    portfolio_summary,
    render_portfolio,
    shapes_portfolio_summary,
    shapes_status,
)


def _artifact(
    *,
    state: str = "",
    country: str = "US",
    reachable: bool = True,
    url: str = "https://ex.org/g.zip",
    errors: int = 0,
    days: int | None = 90,
) -> dict[str, Any]:
    findings = [{"severity": "ERROR", "code": f"e{i}"} for i in range(errors)]
    findings.append({"severity": "WARNING", "code": "w"})
    return {
        "agency": {"state": state, "country": country},
        "feed": {"reachable": reachable, "static_url": url},
        "ntd_id_alignment": {
            "status": "unknown",
            "detail": "",
            "feed_agency_ids": ["TEST"],
        },
        "categories": {
            "correctness": {"status": "measured", "findings": findings},
            "freshness": {"status": "measured", "details": {"days_until_expiry": days}},
        },
    }


def test_non_us_feeds_excluded_from_portfolio() -> None:
    # NTD is a US-federal (FTA) requirement, so a Canadian feed must not count
    # toward a "% ready to certify" figure it cannot meet (ADR 0026).
    artifacts = [
        _artifact(state="OR", days=90),  # US (Oregon), ready
        _artifact(country="CA", days=90),  # Canada: would score "ready", but excluded
    ]
    s = portfolio_summary(artifacts)
    assert s.total == 1  # only the US feed counts
    assert s.ready == 1
    assert set(s.by_state) == {"OR"}  # the Canadian feed created no state bucket


def test_mixed_portfolio_across_two_states() -> None:
    artifacts = [
        _artifact(state="CA", days=90),  # ready
        _artifact(state="CA", days=20),  # at_risk (expiring soon)
        _artifact(state="CA", reachable=False),  # not_ready
        _artifact(state="OR", days=90),  # ready
        _artifact(state="OR", errors=2, days=-10),  # not_ready (lapsed + errors)
    ]
    s = portfolio_summary(artifacts)

    assert s.total == 5
    assert s.ready == 2
    assert s.at_risk == 1
    assert s.not_ready == 2
    assert s.pct_ready == 40.0

    assert s.by_state["CA"] == {
        "ready": 1,
        "at_risk": 1,
        "not_ready": 1,
        "total": 3,
    }
    assert s.by_state["OR"] == {
        "ready": 1,
        "at_risk": 0,
        "not_ready": 1,
        "total": 2,
    }


def test_missing_state_buckets_under_unlocated() -> None:
    s = portfolio_summary([_artifact(days=90), _artifact(state="  ")])
    assert set(s.by_state) == {"Unlocated"}
    assert s.by_state["Unlocated"]["total"] == 2


def test_empty_portfolio_is_all_zeros() -> None:
    s = portfolio_summary([])
    assert s.total == 0
    assert s.ready == 0
    assert s.at_risk == 0
    assert s.not_ready == 0
    assert s.pct_ready == 0.0
    assert s.by_state == {}


def test_render_includes_headline_counts_and_sorted_states() -> None:
    s = portfolio_summary(
        [
            _artifact(state="OR", days=90),
            _artifact(state="CA", days=90),
            _artifact(state="CA", reachable=False),
        ]
    )
    md = render_portfolio(s)

    assert "66.7% of 3 feeds are ready to certify" in md
    assert "Ready: 2" in md
    assert "At risk: 0" in md
    assert "Not ready: 1" in md
    assert "D-10" in md
    assert "P-50" in md
    # States sorted alphabetically: CA row precedes OR row.
    assert md.index("| CA |") < md.index("| OR |")


def test_render_empty_portfolio() -> None:
    md = render_portfolio(portfolio_summary([]))
    assert "No agency feeds were assessed yet." in md


# --- shapes.txt portfolio roll-up (FTA RY2025/26 phase-in) ---


def _shapes_artifact(
    *,
    state: str = "",
    country: str = "US",
    total_trips: int | None = 10,
    trips_with_shape: int | None = 10,
    stored_status: str | None = None,
) -> dict[str, Any]:
    shapes: dict[str, Any] = {}
    if total_trips is not None:
        shapes["total_trips"] = total_trips
    if trips_with_shape is not None:
        shapes["trips_with_shape"] = trips_with_shape
    if stored_status is not None:
        shapes["status"] = stored_status
    return {"agency": {"state": state, "country": country}, "shapes_readiness": shapes}


def test_shapes_status_recomputed_from_stored_counts() -> None:
    # A stale stored verdict loses to the counts, the same recompute-at-read
    # pattern the per-page renderer uses, so a threshold change needs no rescore.
    art = _shapes_artifact(total_trips=10, trips_with_shape=4, stored_status="ready")
    assert shapes_status(art) == "at_risk"


def test_shapes_status_falls_back_to_stored_verdict() -> None:
    # An older artifact that kept only the verdict still counts; an unknown
    # verdict (or no shapes block at all) is skipped rather than guessed.
    assert shapes_status(_shapes_artifact(total_trips=None, stored_status="ready")) == "ready"
    assert shapes_status(_shapes_artifact(total_trips=None, stored_status="bogus")) is None
    assert shapes_status({"agency": {}}) is None


def test_shapes_portfolio_counts_and_states() -> None:
    artifacts = [
        _shapes_artifact(state="CA"),  # ready (10/10)
        _shapes_artifact(state="CA", trips_with_shape=4),  # at_risk
        _shapes_artifact(state="OR", trips_with_shape=0),  # not_ready
        # No trips: no coverage denominator, so the check could not run and the
        # feed is out of the population rather than counted as a failure.
        _shapes_artifact(state="OR", total_trips=0, trips_with_shape=0),
    ]
    s = shapes_portfolio_summary(artifacts)
    assert (s.total, s.ready, s.at_risk, s.not_ready) == (3, 1, 1, 1)
    assert s.pct_ready == 33.3
    assert s.by_state["CA"] == {"ready": 1, "at_risk": 1, "not_ready": 0, "total": 2}
    assert s.by_state["OR"] == {"ready": 0, "at_risk": 0, "not_ready": 1, "total": 1}


def test_shapes_portfolio_skips_non_us_and_unchecked_feeds() -> None:
    artifacts = [
        _shapes_artifact(state="WA"),  # counts
        _shapes_artifact(country="CA"),  # non-US: the FTA requirement has no meaning
        {"agency": {"state": "WA"}},  # check never ran: skipped, not "not ready"
    ]
    s = shapes_portfolio_summary(artifacts)
    assert s.total == 1
    assert s.ready == 1
    assert set(s.by_state) == {"WA"}


def test_shapes_portfolio_empty_and_unlocated() -> None:
    empty = shapes_portfolio_summary([])
    assert empty.total == 0
    assert empty.pct_ready == 0.0
    assert empty.by_state == {}
    s = shapes_portfolio_summary([_shapes_artifact(state="  ")])
    assert set(s.by_state) == {"Unlocated"}
