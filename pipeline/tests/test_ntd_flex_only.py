"""Flex-only feeds: a trip-level classification, kept out of the shapes headline.

A feed whose every trip is GTFS-Flex demand-response service has no fixed path to
trace, and FTA's July 2025 notice does not say whether such a feed is expected to
carry shapes.txt. These tests defend three properties: the classification is
per-trip (a feed that merely ships Flex files, or runs some fixed-route trips, is
NOT Flex-only); a Flex-only feed is reported on its own row and in no headline
count; and an artifact scored before this existed reads exactly as it did.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.gtfs import is_demand_response_row, read_shapes_coverage
from scorecard_pipeline.ntd import (
    FLEX_ONLY,
    assess_shapes_readiness,
    shapes_portfolio_summary,
    shapes_status,
    state_pages,
)
from scorecard_pipeline.render_site import _render_ntd_state_page, _render_shapes_page

_ST_HEAD = (
    "trip_id,stop_id,location_id,location_group_id,start_pickup_drop_off_window,stop_sequence\n"
)


def _zip(
    tmp_path: Path, name: str, stop_times: list[str], trips: list[str], *, flex_files: bool
) -> str:
    path = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("trips.txt", "route_id,service_id,trip_id,shape_id\n" + "\n".join(trips) + "\n")
        zf.writestr("shapes.txt", "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n")
        zf.writestr("stop_times.txt", _ST_HEAD + "\n".join(stop_times) + "\n")
        if flex_files:
            zf.writestr("booking_rules.txt", "booking_rule_id,booking_type\nb1,1\n")
    return str(path)


def _trips(*ids: str) -> list[str]:
    return [f"r,s,{i}," for i in ids]


ZONE = "{t},,zone1,,,1"
WINDOW = "{t},,,,08:00:00,1"
FIXED = "{t},stopA,,,,1"


def test_a_feed_of_only_zone_and_window_trips_is_flex_only(tmp_path: Path) -> None:
    path = _zip(
        tmp_path,
        "all-dr",
        [ZONE.format(t="t1"), WINDOW.format(t="t2")],
        _trips("t1", "t2"),
        flex_files=True,
    )
    cov = read_shapes_coverage(path)
    assert (cov.total_trips, cov.trips_with_shape) == (2, 0)
    assert cov.flex_only is True and cov.demand_response_trips == 2


def test_has_flex_files_alone_does_not_make_a_fixed_route_feed_flex_only(tmp_path: Path) -> None:
    # The 374 ordinary feeds that carry a booking_rules.txt: every trip is timed stops.
    path = _zip(
        tmp_path,
        "fixed",
        [FIXED.format(t="t1"), FIXED.format(t="t2")],
        _trips("t1", "t2"),
        flex_files=True,
    )
    cov = read_shapes_coverage(path)
    assert cov.flex_only is False and cov.demand_response_trips == 0


def test_a_mixed_feed_stays_in_the_count(tmp_path: Path) -> None:
    path = _zip(
        tmp_path,
        "mixed",
        [ZONE.format(t="t1"), FIXED.format(t="t2")],
        _trips("t1", "t2"),
        flex_files=True,
    )
    cov = read_shapes_coverage(path)
    assert cov.flex_only is False and cov.demand_response_trips == 1


def test_one_fixed_stop_time_row_makes_the_whole_trip_fixed(tmp_path: Path) -> None:
    path = _zip(
        tmp_path,
        "partial-trip",
        [ZONE.format(t="t1"), FIXED.format(t="t1")],
        _trips("t1"),
        flex_files=True,
    )
    assert read_shapes_coverage(path).flex_only is False


def test_a_trip_with_no_stop_times_is_not_demand_response(tmp_path: Path) -> None:
    path = _zip(tmp_path, "orphan", [ZONE.format(t="t1")], _trips("t1", "t2"), flex_files=True)
    cov = read_shapes_coverage(path)
    assert cov.flex_only is False and cov.demand_response_trips == 1


def test_stop_times_are_not_classified_without_flex_files(tmp_path: Path) -> None:
    # Zone-looking rows in a feed that ships no Flex files are not trusted.
    path = _zip(tmp_path, "no-flex", [ZONE.format(t="t1")], _trips("t1"), flex_files=False)
    cov = read_shapes_coverage(path)
    assert cov.flex_only is False and cov.demand_response_trips == 0


def test_an_empty_trips_table_is_never_flex_only(tmp_path: Path) -> None:
    path = _zip(tmp_path, "empty", [], [], flex_files=True)
    assert read_shapes_coverage(path).flex_only is False


def test_row_classifier() -> None:
    assert is_demand_response_row({"location_id": "z"})
    assert is_demand_response_row({"location_group_id": "g"})
    assert is_demand_response_row({"end_pickup_drop_off_window": "10:00:00"})
    # The earlier draft's spelling of the window columns is still published.
    assert is_demand_response_row({"start_pickup_dropoff_window": "06:00:00"})
    assert not is_demand_response_row({"stop_id": "s", "location_id": " "})


def test_assessment_marks_flex_only_and_leaves_other_artifacts_untouched() -> None:
    flex = assess_shapes_readiness(5, 0, flex_only=True)
    assert flex.status == FLEX_ONLY and flex.to_dict()["flex_only"] is True
    assert "not counted in the shapes.txt totals" in flex.detail
    # Undated data unchanged: no key for a fixed-route feed, same dict as before.
    plain = assess_shapes_readiness(5, 0).to_dict()
    assert "flex_only" not in plain and plain["status"] == "not_ready"
    assert assess_shapes_readiness(5, 0, flex_only=False).to_dict() == plain


def _art(
    agency_id: str,
    total: int,
    with_shape: int,
    *,
    state: str = "Iowa",
    flex_only: bool | None = None,
    has_flex: bool = False,
) -> dict[str, Any]:
    shapes: dict[str, Any] = {"total_trips": total, "trips_with_shape": with_shape}
    if flex_only is not None:
        shapes["flex_only"] = flex_only
    return {
        "agency": {"id": agency_id, "name": f"Agency {agency_id}", "state": state},
        "feed": {"reachable": True, "static_url": "https://ex.org/g.zip"},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "freshness": {"status": "measured", "details": {"days_until_expiry": 90}},
            "completeness": {"details": {"flex": {"has_flex": has_flex}}},
        },
        "ntd_id_alignment": {"status": "unknown", "detail": "", "feed_agency_ids": ["x"]},
        "shapes_readiness": shapes,
    }


def _population() -> list[dict[str, Any]]:
    arts = [_art(f"ok{i}", 10, 10) for i in range(5)]
    arts.append(_art("partial", 10, 4, has_flex=True))  # has_flex, fixed-route: stays counted
    arts.append(_art("zone1", 3, 0, flex_only=True, has_flex=True))
    arts.append(_art("zone2", 2, 0, flex_only=True, has_flex=True))
    return arts


def test_flex_only_feeds_are_in_no_headline_count() -> None:
    summary = shapes_portfolio_summary(_population())
    assert (summary.total, summary.ready, summary.at_risk, summary.not_ready) == (6, 5, 1, 0)
    assert summary.flex_only == 2 and summary.flex_only_by_state == {"Iowa": 2}
    # by_state is a published format contract: its key set must not grow.
    assert set(summary.by_state["Iowa"]) == {"ready", "at_risk", "not_ready", "total"}


def test_negative_control_a_flex_only_feed_counted_in_the_headline_fails() -> None:
    arts = _population()
    sabotaged = [dict(a, shapes_readiness=dict(a["shapes_readiness"])) for a in arts]
    for art in sabotaged:
        art["shapes_readiness"].pop("flex_only", None)
    assert sabotaged != arts  # the sabotage applied
    summary = shapes_portfolio_summary(sabotaged)
    # Without the flag the two zone feeds read as "No shapes yet" in the headline.
    assert summary.not_ready == 2 and summary.total == 8 and summary.flex_only == 0
    honest = shapes_portfolio_summary(arts)
    assert honest.not_ready == 0 and honest.total == 6


def test_a_fixed_route_feed_with_has_flex_set_stays_in_the_headline() -> None:
    art = _art("fixed", 10, 0, has_flex=True)
    assert shapes_status(art) == "not_ready"
    assert shapes_portfolio_summary([art]).not_ready == 1


def test_an_artifact_scored_before_the_flag_existed_reads_as_before() -> None:
    old = _art("old", 10, 4)
    assert "flex_only" not in old["shapes_readiness"]
    assert shapes_status(old) == "at_risk"


def test_state_page_lists_flex_only_on_its_own_row_and_outside_the_headline() -> None:
    rows = state_pages(_population())["Iowa"]
    html = _render_ntd_state_page("Iowa", rows)
    assert "Of the 6 Iowa feeds" in html
    assert "<strong>5 carry a shape for every trip</strong>" in html
    assert "2 more are Flex-only feeds" in html and "not counted in these numbers" in html
    assert "Flex-only feed (0 of 3 trips have a shape)" in html
    assert "No shapes yet" not in html
    # Negative control: the same two feeds with the flag lost land in the headline.
    sabotaged_rows = [
        r if r.shapes != FLEX_ONLY else type(r)(r.id, r.name, "not_ready", 0, r.total_trips, None)
        for r in rows
    ]
    assert sabotaged_rows != rows  # the sabotage applied
    bad = _render_ntd_state_page("Iowa", sabotaged_rows)
    assert "Of the 8 Iowa feeds" in bad and "2 have no shapes yet" in bad


def test_flex_only_feeds_do_not_open_a_state_page() -> None:
    arts = [_art(f"z{i}", 2, 0, flex_only=True) for i in range(6)]
    assert state_pages(arts) == {}


def test_explainer_reports_the_flex_only_row_and_column() -> None:
    shapes = {
        "total": 6,
        "ready": 5,
        "at_risk": 1,
        "not_ready": 0,
        "pct_ready": 83.3,
        "flex_only": 2,
        "flex_only_by_state": {"Iowa": 2},
        "by_state": {"Iowa": {"ready": 5, "at_risk": 1, "not_ready": 0, "total": 6}},
    }
    html = _render_shapes_page(shapes)
    assert "Flex-only feed (not counted above)" in html
    assert "<th>Flex-only</th>" in html
    assert "A further 2 Flex-only feeds are reported separately below." in html
    assert "<td>6</td><td>2</td>" in html


@pytest.mark.parametrize("flex_only", [None, False])
def test_explainer_without_flex_data_renders_a_zero_row(flex_only: Any) -> None:
    shapes: dict[str, Any] = {
        "total": 1,
        "ready": 1,
        "at_risk": 0,
        "not_ready": 0,
        "pct_ready": 100.0,
        "by_state": {"Iowa": {"ready": 1, "at_risk": 0, "not_ready": 0, "total": 1}},
    }
    if flex_only is not None:
        shapes["flex_only"] = 0
    html = _render_shapes_page(shapes)
    assert "Flex-only feed (not counted above)</td><td>0</td>" in html
    assert "A further" not in html
