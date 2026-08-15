"""Tests for the consequence layer: what a finding costs, and what it refuses to guess."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.consequence import (
    BOARDABLE_STOPS,
    COUNT_MISSING,
    DENOMINATOR_MISSING,
    DUPLICATE_NTD_REPORTER,
    FEED_LEVEL,
    FINDING_BASIS,
    INCONSISTENT_COUNTS,
    NO_BASIS,
    NO_NTD_ID,
    NO_RIDERSHIP_DATA,
    NO_SERVED_AREA_DATA,
    NOT_NETWORK_COUNTABLE,
    OUTSIDE_NEED_SCOPE,
    OUTSIDE_RIDERSHIP_SCOPE,
    ROUTES,
    SAMPLED_WINDOW,
    STOPS,
    TRIPS,
    UNKNOWN_TIER,
    UNMAPPED_FINDING,
    UNMATCHED_NTD_ID,
    VALIDATOR_NOTICE,
    Consequence,
    basis_for,
    consequence_for,
    reach_for,
    ridership_for,
    served_area_need_for,
)
from scorecard_pipeline.equity import EquityIndicators


def finding(code: str, count: int | None = 1) -> dict[str, Any]:
    """A finding dict in the shape ``Finding.to_json`` publishes."""
    return {
        "code": code,
        "severity": "WARNING",
        "count": count,
        "what": "something to fix",
        "why": "riders are affected",
        "fix": "do the thing",
        "effort": "one export setting",
        "points": 4.0,
        "owner": "",
    }


def artifact(
    *,
    country: str | None = None,
    stop_count: int | None = 296,
    boardable_stops: int | None = 274,
    trips_total: int | None = 1794,
    route_count: int | None = 20,
    ntd_id: str | None = "90142",
) -> dict[str, Any]:
    """An artifact carrying only the fields the consequence layer reads."""
    agency: dict[str, Any] = {"id": "unitrans", "name": "Unitrans"}
    if country is not None:
        agency["country"] = country
    out: dict[str, Any] = {"agency": agency}
    if stop_count is not None:
        out["geo"] = {"stop_count": stop_count}
    if boardable_stops is not None or trips_total is not None:
        routability: dict[str, Any] = {}
        if boardable_stops is not None:
            routability["boardable_stops"] = boardable_stops
        if trips_total is not None:
            routability["trips_total"] = trips_total
        out["routability"] = routability
    if route_count is not None:
        out["mode_profile"] = {"route_count": route_count, "trip_count": trips_total or 0}
    if ntd_id is not None:
        out["ntd_id_alignment"] = {"ntd_id": ntd_id, "status": "mismatch"}
    return out


# --- the code-to-basis mapping ----------------------------------------------


def test_basis_matches_how_each_finding_is_produced() -> None:
    # completeness.py divides by every row of stops.txt / trips.txt.
    assert basis_for("scorecard_wheelchair_boarding_unknown") == STOPS
    assert basis_for("scorecard_stop_names_all_caps") == STOPS
    assert basis_for("scorecard_wheelchair_accessible_unknown") == TRIPS
    assert basis_for("scorecard_missing_headsigns") == TRIPS
    # routability.py divides orphan stops by the boardable subset, not by stops.
    assert basis_for("scorecard_orphan_stops") == BOARDABLE_STOPS
    assert basis_for("scorecard_single_stop_trips") == TRIPS
    # accessibility.py counts route badges per route.
    assert basis_for("scorecard_route_color_low_contrast") == ROUTES
    assert basis_for("scorecard_stop_name_needs_tts") == STOPS


def test_findings_without_an_honest_denominator_have_no_basis() -> None:
    for code in (
        "scorecard_feed_expired",  # one fact about the calendar
        "scorecard_no_fare_data",  # one fact about the feed
        "scorecard_station_missing_step_free_data",  # counts files, not stops
        "scorecard_station_pathways",  # counts pathways
        "scorecard_flex_booking_unreachable",  # counts booking rules
        "scorecard_fares_published_not_applied",  # counts fare products
        "scorecard_rt_trip_coverage",  # window-scoped, not feed-wide
        "scorecard_rt_vehicles_off_route",  # sampled vehicles
    ):
        assert basis_for(code) == NO_BASIS, code


def test_orphan_stops_never_borrows_the_all_stops_denominator() -> None:
    # A feed that models stations has more located stops than boardable ones.
    # Reading orphan stops against geo.stop_count would understate the share.
    art = artifact(stop_count=400, boardable_stops=274)
    reach = reach_for(finding("scorecard_orphan_stops", 137), art)
    assert reach.total == 274
    assert reach.total_source == "routability.boardable_stops"
    assert reach.share == 0.5


def test_all_stops_findings_use_the_published_stop_count() -> None:
    art = artifact(stop_count=296, boardable_stops=274)
    reach = reach_for(finding("scorecard_wheelchair_boarding_unknown", 296), art)
    assert reach.total == 296
    assert reach.total_source == "geo.stop_count"
    assert reach.share == 1.0


def test_stops_basis_falls_back_to_boardable_when_geo_is_absent() -> None:
    art = artifact(stop_count=None, boardable_stops=274)
    reach = reach_for(finding("scorecard_stop_names_all_caps", 137), art)
    assert reach.total_source == "routability.boardable_stops"
    assert reach.share == 0.5


def test_trips_basis_prefers_routability_then_mode_profile() -> None:
    art = artifact(trips_total=1794)
    assert reach_for(finding("scorecard_missing_headsigns", 897), art).total_source == (
        "routability.trips_total"
    )
    art_without_routability = artifact(boardable_stops=None, trips_total=None)
    art_without_routability["mode_profile"] = {"route_count": 20, "trip_count": 1000}
    reach = reach_for(finding("scorecard_missing_headsigns", 250), art_without_routability)
    assert reach.total_source == "mode_profile.trip_count"
    assert reach.share == 0.25


def test_routes_basis_reads_the_mode_profile() -> None:
    reach = reach_for(finding("scorecard_route_color_low_contrast", 5), artifact())
    assert (reach.total, reach.total_source, reach.share) == (20, "mode_profile.route_count", 0.25)


# --- refusing to fabricate ---------------------------------------------------


def test_validator_notices_get_an_explicit_unknown() -> None:
    reach = reach_for(finding("stop_too_far_from_shape", 40), artifact())
    assert reach.basis == NO_BASIS
    assert reach.reason == VALIDATOR_NOTICE
    assert reach.share is None
    assert reach.total is None


def test_unclassified_scorecard_finding_is_flagged_not_guessed() -> None:
    reach = reach_for(finding("scorecard_something_new", 12), artifact())
    assert reach.reason == UNMAPPED_FINDING
    assert reach.share is None


def test_feed_level_and_window_findings_name_their_own_reason() -> None:
    assert reach_for(finding("scorecard_feed_expired"), artifact()).reason == FEED_LEVEL
    assert reach_for(finding("scorecard_rt_stale"), artifact()).reason == SAMPLED_WINDOW
    assert (
        reach_for(finding("scorecard_station_no_pathways"), artifact()).reason
        == NOT_NETWORK_COUNTABLE
    )


def test_count_larger_than_the_denominator_is_reported_as_unknown() -> None:
    # Twelve published feeds have more stops missing wheelchair_boarding than
    # they have located stops, because geo.stop_count drops stops without
    # coordinates. A share above 100% would be worse than no share.
    reach = reach_for(finding("scorecard_wheelchair_boarding_unknown", 310), artifact())
    assert reach.reason == INCONSISTENT_COUNTS
    assert reach.share is None
    assert (reach.affected, reach.total) == (310, 296)


def test_missing_denominator_is_unknown_not_zero() -> None:
    art = artifact(stop_count=None, boardable_stops=None)
    reach = reach_for(finding("scorecard_wheelchair_boarding_unknown", 296), art)
    assert reach.reason == DENOMINATOR_MISSING
    assert reach.total is None
    assert reach.share is None
    assert reach.affected == 296


def test_zero_or_malformed_denominators_are_skipped() -> None:
    art = artifact(stop_count=0, boardable_stops=0)
    assert reach_for(finding("scorecard_orphan_stops", 3), art).reason == DENOMINATOR_MISSING
    art_bad = artifact()
    art_bad["mode_profile"] = {"route_count": "twenty"}
    assert (
        reach_for(finding("scorecard_route_color_low_contrast", 2), art_bad).reason
        == DENOMINATOR_MISSING
    )


@pytest.mark.parametrize("count", [None, True, -3, "12"])
def test_unusable_counts_are_reported_as_missing(count: Any) -> None:
    reach = reach_for(finding("scorecard_missing_headsigns", count), artifact())
    assert reach.reason == COUNT_MISSING
    assert reach.share is None


def test_a_zero_count_is_a_real_zero_share() -> None:
    reach = reach_for(finding("scorecard_stop_names_all_caps", 0), artifact())
    assert reach.share == 0.0
    assert reach.known


def test_reach_survives_a_missing_or_malformed_section() -> None:
    reach = reach_for(finding("scorecard_orphan_stops", 5), {"routability": "not a dict"})
    assert reach.reason == DENOMINATOR_MISSING


# --- ridership ---------------------------------------------------------------


def test_ridership_matches_an_unambiguous_reporter() -> None:
    result = ridership_for(artifact(), {"90142": 1_234_567})
    assert result.annual_rider_trips == 1_234_567
    assert result.ntd_id == "90142"
    assert result.reason == ""


def test_ridership_normalizes_a_zero_padded_reporter_id() -> None:
    result = ridership_for(artifact(ntd_id="0090142"), {"90142": 42})
    assert result.annual_rider_trips == 42


def test_a_duplicate_reporter_is_never_credited_to_one_feed() -> None:
    result = ridership_for(
        artifact(),
        {"90142": 1_234_567},
        quarantined_ntd_ids=["0090142"],
    )
    assert result.annual_rider_trips is None
    assert result.reason == DUPLICATE_NTD_REPORTER


def test_ridership_outside_the_united_states_is_absent_not_zero() -> None:
    result = ridership_for(artifact(country="IT", ntd_id=None), {"90142": 10})
    assert result.annual_rider_trips is None
    assert result.reason == OUTSIDE_RIDERSHIP_SCOPE


def test_ridership_absence_reasons_stay_distinct() -> None:
    assert ridership_for(artifact(), None).reason == NO_RIDERSHIP_DATA
    assert ridership_for(artifact(ntd_id=None), {"90142": 5}).reason == NO_NTD_ID
    assert ridership_for(artifact(), {"11111": 5}).reason == UNMATCHED_NTD_ID


def test_an_artifact_without_agency_country_is_read_as_united_states() -> None:
    # agency.country is additive; US artifacts published before it omit it.
    assert ridership_for(artifact(country=None), {"90142": 7}).annual_rider_trips == 7


def test_a_missing_or_malformed_agency_block_does_not_raise() -> None:
    assert ridership_for({"ntd_id_alignment": {"ntd_id": "90142"}}, {"90142": 7}).known
    assert ridership_for({"agency": "Unitrans"}, {"90142": 7}).reason == NO_NTD_ID
    assert ridership_for({"agency": {}, "ntd_id_alignment": []}, {}).reason == NO_NTD_ID


# --- served-area need --------------------------------------------------------


def test_need_accepts_a_tier_string_or_indicators() -> None:
    assert served_area_need_for(artifact(), "high").tier == "high"
    indicators = EquityIndicators(poverty_pct=25.0, zero_vehicle_pct=20.0, disability_pct=5.0)
    result = served_area_need_for(artifact(), indicators)
    assert result.tier == "high"
    assert result.scale == "us_acs"


def test_canadian_need_carries_its_own_scale() -> None:
    result = served_area_need_for(artifact(country="CA"), "moderate")
    assert (result.tier, result.scale) == ("moderate", "ca_cimd")


def test_need_outside_north_america_is_absent_not_lower() -> None:
    result = served_area_need_for(artifact(country="NZ"), "high")
    assert result.tier is None
    assert result.scale == ""
    assert result.reason == OUTSIDE_NEED_SCOPE


def test_need_absence_reasons_stay_distinct() -> None:
    assert served_area_need_for(artifact(), None).reason == NO_SERVED_AREA_DATA
    assert served_area_need_for(artifact(), "not a tier").reason == NO_SERVED_AREA_DATA
    assert served_area_need_for(artifact(), "unknown").reason == UNKNOWN_TIER
    assert served_area_need_for(artifact(), EquityIndicators()).reason == UNKNOWN_TIER


# --- the whole picture and its copy ------------------------------------------


def test_consequence_reads_like_the_agency_page_copy() -> None:
    result = consequence_for(
        finding("scorecard_wheelchair_boarding_unknown", 296),
        artifact(),
        ridership={"90142": 1_234_567},
        served_area="high",
    )
    assert result.line == (
        "Fixing this covers all 296 stops in the feed. This feed's National Transit "
        "Database reporter recorded 1,234,567 annual rider-trips. The area this feed "
        "serves measures high on transit need."
    )
    assert result.absences == []


def test_a_partial_share_reads_as_a_rounded_percentage() -> None:
    result = consequence_for(finding("scorecard_orphan_stops", 22), artifact(boardable_stops=296))
    assert result.line.startswith("Fixing this covers 22 of 296 boardable stops, about 7% of them.")


def test_a_very_small_share_does_not_round_to_zero_percent() -> None:
    result = consequence_for(finding("scorecard_missing_headsigns", 3), artifact(trips_total=1794))
    assert "under 1% of them" in result.line


def test_an_almost_complete_share_does_not_round_up_to_all_of_them() -> None:
    art = artifact(stop_count=9850)
    result = consequence_for(finding("scorecard_wheelchair_boarding_unknown", 9847), art)
    assert result.line == "Fixing this covers 9,847 of 9,850 stops, nearly all of them."


def test_a_zero_share_says_so_plainly() -> None:
    result = consequence_for(finding("scorecard_stop_names_all_caps", 0), artifact())
    assert result.line.startswith("None of the feed's 296 stops are affected.")


def test_the_line_states_an_unknown_reach_rather_than_going_quiet() -> None:
    result = consequence_for(finding("scorecard_feed_expired"), artifact())
    assert result.line.startswith("This one is about the feed as a whole")


def test_absences_are_stated_for_every_missing_number() -> None:
    result = consequence_for(finding("scorecard_orphan_stops", 22), artifact(country="IT"))
    assert result.ridership.reason == OUTSIDE_RIDERSHIP_SCOPE
    assert result.need.reason == OUTSIDE_NEED_SCOPE
    notes = result.absences
    assert len(notes) == 2
    assert any("does not cover this feed's country" in note for note in notes)
    assert any("United States and Canada" in note for note in notes)
    # Nothing in the line implies the feed has no riders or no need.
    assert "0 annual rider-trips" not in result.line


def test_a_bare_artifact_still_yields_reach_plus_two_absences() -> None:
    result = consequence_for(finding("scorecard_single_stop_trips", 12), artifact())
    assert result.reach.known
    assert not result.ridership.known
    assert not result.need.known
    assert len(result.absences) == 2


def test_to_json_is_serializable_and_complete() -> None:
    result = consequence_for(
        finding("scorecard_orphan_stops", 22),
        artifact(),
        ridership={"90142": 900},
        served_area="lower",
    )
    payload = result.to_json()
    assert payload["code"] == "scorecard_orphan_stops"
    assert payload["reach"]["basis"] == BOARDABLE_STOPS
    assert payload["reach"]["basis_label"] == "boardable stops"
    assert payload["ridership"]["annual_rider_trips"] == 900
    assert payload["served_area_need"] == {"tier": "lower", "scale": "us_acs", "reason": ""}
    assert payload["absences"] == []
    assert isinstance(payload["line"], str)


def test_reach_reports_a_basis_label_a_reader_can_use() -> None:
    reach = reach_for(finding("scorecard_orphan_stops", 1), artifact())
    assert reach.basis_label == "boardable stops"
    assert reach_for(finding("scorecard_feed_expired"), artifact()).basis_label == ""


def test_unknown_reach_falls_back_to_a_readable_sentence() -> None:
    # A reason with no curated sentence still produces plain language rather
    # than an empty line.
    from scorecard_pipeline.consequence import Reach, reach_sentence

    sentence = reach_sentence(Reach(basis=STOPS, basis_label="stops", reason="something_new"))
    assert sentence == "The feed's stops count is not published here, so no share is reported."


def test_absence_notes_skip_reasons_with_no_curated_sentence() -> None:
    from scorecard_pipeline.consequence import Reach, Ridership, ServedAreaNeed, absence_notes

    result = Consequence(
        code="x",
        reach=Reach(basis=NO_BASIS, basis_label=""),
        ridership=Ridership(reason="unexpected"),
        need=ServedAreaNeed(reason="unexpected"),
    )
    assert absence_notes(result) == []


# --- the mapping stays complete as findings are added ------------------------


def _package_dir() -> Path:
    import scorecard_pipeline

    return Path(scorecard_pipeline.__file__).parent


def test_every_scorecard_finding_code_in_the_package_has_a_reviewed_basis() -> None:
    """A new finding must be classified deliberately, not fall through to unknown.

    Scans the package for literal ``code="scorecard_..."`` arguments. The one
    finding built from an f-string (the per-kind realtime unreachable code) is
    checked separately below, since no literal exists to scan.
    """
    pattern = re.compile(r'code=(?:f)?"(scorecard_[a-z0-9_]+)"')
    found: set[str] = set()
    for path in sorted(_package_dir().glob("*.py")):
        found.update(pattern.findall(path.read_text()))
    assert found, "expected to find scorecard finding codes in the package"
    missing = sorted(code for code in found if code not in FINDING_BASIS)
    assert missing == []


def test_the_per_kind_realtime_codes_are_mapped() -> None:
    # Built as f"scorecard_rt_{kind}_unreachable" in rt.py, for the three
    # configured realtime kinds.
    for kind in ("trip_updates", "vehicle_positions", "service_alerts"):
        assert f"scorecard_rt_{kind}_unreachable" in FINDING_BASIS


def test_every_mapped_basis_is_a_known_basis() -> None:
    from scorecard_pipeline.consequence import BASIS_LABEL

    assert set(FINDING_BASIS.values()) <= set(BASIS_LABEL)
