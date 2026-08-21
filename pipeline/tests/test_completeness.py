"""Tests for the rider experience completeness category."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from scorecard_pipeline.completeness import WEIGHTS, _is_shouty, completeness
from scorecard_pipeline.gtfs import TableTooLargeError

COMPLETE_FEED = {
    "agency.txt": (
        "agency_id,agency_name,agency_url,agency_timezone\n"
        "yolo,Yolobus,https://yolobus.com,America/Los_Angeles\n"
    ),
    "feed_info.txt": (
        "feed_publisher_name,feed_publisher_url,feed_lang,feed_contact_email\n"
        "Yolobus,https://yolobus.com,en,data@yctd.org\n"
    ),
    "stops.txt": (
        "stop_id,stop_name,wheelchair_boarding\n"
        "S1,Main St & 2nd Ave,1\n"
        "S2,County Rd 98 & Russell Blvd,2\n"
    ),
    "trips.txt": (
        "route_id,service_id,trip_id,trip_headsign,wheelchair_accessible\n"
        "R1,WK,T1,Downtown,1\n"
        "R1,WK,T2,Campus,1\n"
    ),
    "fare_attributes.txt": "fare_id,price,currency_type\nbase,2.25,USD\n",
}


def test_complete_feed_scores_100(make_gtfs_zip: Callable[..., Path]) -> None:
    result = completeness(str(make_gtfs_zip(COMPLETE_FEED)))
    assert result.score == 100.0
    assert result.findings == []
    assert result.details["translations"]["has_translations"] is False


def test_bare_feed_scores_low_with_findings(make_gtfs_zip: Callable[..., Path]) -> None:
    path = make_gtfs_zip(
        {
            "agency.txt": "agency_id,agency_name\nx,X\n",
            "stops.txt": "stop_id,stop_name\nS1,MAIN ST & 2ND AVE\n",
            "trips.txt": "route_id,service_id,trip_id\nR1,WK,T1\n",
        }
    )
    result = completeness(str(path))
    assert result.score == 0.0
    codes = {f.code for f in result.findings}
    assert "scorecard_wheelchair_boarding_unknown" in codes
    assert "scorecard_wheelchair_accessible_unknown" in codes
    assert "scorecard_no_fare_data" in codes
    assert "scorecard_stop_names_all_caps" in codes
    assert "scorecard_missing_headsigns" in codes
    assert "scorecard_no_feed_contact" in codes
    assert "scorecard_bad_agency_url" in codes


def test_null_feed_contact_values_are_treated_as_missing(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {
        **COMPLETE_FEED,
        "feed_info.txt": (
            "feed_publisher_name,feed_publisher_url,feed_lang,feed_contact_email,"
            "feed_contact_url\n"
            "Kagoshima City,https://example.jp,ja\n"
        ),
    }

    result = completeness(str(make_gtfs_zip(feed)))

    assert any(f.code == "scorecard_no_feed_contact" for f in result.findings)
    assert result.details["components"]["contact"] == WEIGHTS["contact"] * 0.5


def test_single_pattern_one_direction_loop_does_not_invent_a_headsign_fix(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {
        **COMPLETE_FEED,
        "trips.txt": (
            "route_id,service_id,trip_id,trip_headsign,direction_id,shape_id,"
            "wheelchair_accessible\n"
            "A,WK,T1,,0,loop,1\n"
            "A,SA,T2,,0,loop,1\n"
        ),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T1,08:00:00,08:00:00,S1,1\n"
            "T1,08:10:00,08:10:00,S2,2\n"
            "T1,08:20:00,08:20:00,S1,3\n"
            "T2,09:00:00,09:00:00,S1,1\n"
            "T2,09:10:00,09:10:00,S2,2\n"
            "T2,09:20:00,09:20:00,S1,3\n"
        ),
    }

    result = completeness(str(make_gtfs_zip(feed)))

    assert result.score == 100.0
    assert not any(f.code == "scorecard_missing_headsigns" for f in result.findings)
    assert result.details["headsign_pct"] == 0.0
    assert result.details["headsign_scored_pct"] == 100.0
    assert result.details["headsign_applicable_trips"] == 0
    assert result.details["headsign_loop_exempt_trips"] == 2


def test_linear_or_distinct_loop_patterns_still_need_headsigns(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {
        **COMPLETE_FEED,
        "trips.txt": (
            "route_id,service_id,trip_id,trip_headsign,direction_id,shape_id,"
            "wheelchair_accessible\n"
            "L,WK,LINEAR,,0,line,1\n"
            "B,WK,CLOCKWISE,,0,cw,1\n"
            "B,WK,COUNTERCLOCKWISE,,1,ccw,1\n"
        ),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "LINEAR,08:00:00,08:00:00,S1,1\n"
            "LINEAR,08:10:00,08:10:00,S2,2\n"
            "CLOCKWISE,09:00:00,09:00:00,S1,1\n"
            "CLOCKWISE,09:10:00,09:10:00,S2,2\n"
            "CLOCKWISE,09:20:00,09:20:00,S1,3\n"
            "COUNTERCLOCKWISE,10:00:00,10:00:00,S1,1\n"
            "COUNTERCLOCKWISE,10:10:00,10:10:00,S2,2\n"
            "COUNTERCLOCKWISE,10:20:00,10:20:00,S1,3\n"
        ),
    }

    result = completeness(str(make_gtfs_zip(feed)))
    finding = next(f for f in result.findings if f.code == "scorecard_missing_headsigns")

    assert finding.count == 3
    assert "Do not copy the route name" in finding.fix
    assert result.details["headsign_scored_pct"] == 0.0
    assert result.details["headsign_loop_exempt_trips"] == 0


def test_out_and_back_pattern_still_needs_a_headsign(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {
        **COMPLETE_FEED,
        "trips.txt": (
            "route_id,service_id,trip_id,trip_headsign,direction_id,shape_id,"
            "wheelchair_accessible\n"
            "L,WK,T1,,0,lollipop,1\n"
        ),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T1,08:00:00,08:00:00,S1,1\n"
            "T1,08:10:00,08:10:00,S2,2\n"
            "T1,08:20:00,08:20:00,S3,3\n"
            "T1,08:30:00,08:30:00,S2,4\n"
            "T1,08:40:00,08:40:00,S1,5\n"
        ),
    }

    result = completeness(str(make_gtfs_zip(feed)))

    finding = next(f for f in result.findings if f.code == "scorecard_missing_headsigns")
    assert finding.count == 1
    assert result.details["headsign_loop_exempt_trips"] == 0


def test_malformed_stop_times_cannot_earn_a_loop_exemption(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {
        **COMPLETE_FEED,
        "trips.txt": (
            "route_id,service_id,trip_id,trip_headsign,direction_id,shape_id,"
            "wheelchair_accessible\n"
            "A,WK,T1,,0,loop,1\n"
        ),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T1,08:00:00,08:00:00,S1,1\n"
            "T1,08:10:00,08:10:00,,2\n"
            "T1,08:20:00,08:20:00,S1,not-a-sequence\n"
        ),
    }

    result = completeness(str(make_gtfs_zip(feed)))

    assert any(f.code == "scorecard_missing_headsigns" for f in result.findings)
    assert result.details["headsign_loop_exempt_trips"] == 0


def test_oversized_stop_times_falls_back_to_the_ordinary_headsign_check(
    make_gtfs_zip: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed = {
        **COMPLETE_FEED,
        "trips.txt": (
            "route_id,service_id,trip_id,trip_headsign,direction_id,shape_id,"
            "wheelchair_accessible\n"
            "A,WK,T1,,0,loop,1\n"
        ),
    }
    path = make_gtfs_zip(feed)

    def oversized_stop_times(
        gtfs_zip_path: str,
        name: str,
        *,
        max_member_bytes: int,
    ) -> list[dict[str, str]]:
        raise TableTooLargeError("stop_times.txt exceeds the analysis cap")

    monkeypatch.setattr(
        "scorecard_pipeline.completeness.iter_table_rows",
        oversized_stop_times,
    )

    result = completeness(str(path))

    assert any(f.code == "scorecard_missing_headsigns" for f in result.findings)
    assert result.details["headsign_loop_exempt_trips"] == 0


def test_uncased_scripts_are_not_misread_as_all_caps() -> None:
    assert not _is_shouty("那須町役場前")
    assert not _is_shouty("محطة الحافلات المركزية")
    assert _is_shouty("ЦЕНТРАЛЬНЫЙ ВОКЗАЛ")
    assert _is_shouty("CENTRAL STATION")
    assert not _is_shouty("Central Station")


def test_accessibility_sub_score_is_published(make_gtfs_zip: Callable[..., Path]) -> None:
    full = completeness(str(make_gtfs_zip(COMPLETE_FEED)))
    acc = full.details["accessibility"]
    # A fully accessible feed earns the whole accessibility sub-score.
    assert acc["score"] == 100.0
    assert acc["measures"] == "presence_not_usability"
    assert acc["stops_stated_pct"] == 100.0

    bare = make_gtfs_zip(
        {
            "agency.txt": "agency_id,agency_name\nx,X\n",
            "stops.txt": "stop_id,stop_name\nS1,Main St\n",
            "trips.txt": "route_id,service_id,trip_id\nR1,WK,T1\n",
        }
    )
    assert completeness(str(bare)).details["accessibility"]["score"] == 0.0


def test_fares_published_not_applied_is_surfaced_without_changing_score(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    # COMPLETE_FEED ships legacy fare_attributes; swap in v2 products with no
    # leg rules: published, but not applied to any trip.
    feed = {k: v for k, v in COMPLETE_FEED.items() if k != "fare_attributes.txt"}
    feed["fare_products.txt"] = (
        "fare_product_id,fare_product_name,amount,currency\np1,Single,2.5,USD\n"
    )
    result = completeness(str(make_gtfs_zip(feed)))

    assert result.details["fares"]["model"] == "v2"
    assert result.details["fares"]["applied"] is False
    codes = {f.code for f in result.findings}
    assert "scorecard_fares_published_not_applied" in codes
    # Still credited as having fares (the binary component is unchanged), and the
    # new finding carries no deduction.
    assert result.details["components"]["fares"] == WEIGHTS["fares"]
    finding = next(f for f in result.findings if f.code == "scorecard_fares_published_not_applied")
    assert finding.deduction == 0.0


def test_pathways_surfaced_for_stations_without_changing_score(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    # A flat feed (COMPLETE_FEED's stops have no stations) is not flagged.
    plain = completeness(str(make_gtfs_zip(COMPLETE_FEED)))
    assert plain.details["pathways"]["has_stations"] is False
    assert not any(f.code.startswith("scorecard_station") for f in plain.findings)

    # Same feed, but the stops model a station. Every stop stays fully complete
    # (wheelchair set, mixed-case names), so only the pathways signal differs and
    # the completeness score is unchanged.
    station_feed = {
        **COMPLETE_FEED,
        "stops.txt": (
            "stop_id,stop_name,wheelchair_boarding,location_type\n"
            "S1,Main St & 2nd Ave,1,0\n"
            "S2,County Rd 98 & Russell Blvd,2,0\n"
            "STA,Transit Center,1,1\n"
        ),
    }
    station = completeness(str(make_gtfs_zip(station_feed)))
    assert station.details["pathways"]["has_stations"] is True
    assert any(f.code == "scorecard_station_no_pathways" for f in station.findings)
    # Representation, not a penalty: modeling a station does not lower the score.
    assert station.score == plain.score


def test_flex_is_surfaced_without_changing_the_score(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    plain = completeness(str(make_gtfs_zip(COMPLETE_FEED)))
    flex_feed = {
        **COMPLETE_FEED,
        "locations.geojson": '{"type":"FeatureCollection","features":[]}',
        "booking_rules.txt": "booking_rule_id,booking_type,phone_number\nBR1,1,530-555-0100\n",
    }
    flex = completeness(str(make_gtfs_zip(flex_feed)))

    assert flex.details["flex"]["has_flex"] is True
    assert plain.details["flex"]["has_flex"] is False
    # Representation, not a penalty: the same feed plus flex files scores the same.
    assert flex.score == plain.score
    assert any(f.code == "scorecard_flex_service" for f in flex.findings)


def test_translations_are_surfaced_without_changing_the_score(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    plain = completeness(str(make_gtfs_zip(COMPLETE_FEED)))
    translated_feed = {
        **COMPLETE_FEED,
        "translations.txt": (
            "table_name,field_name,language,translation,record_id\n"
            "stops,stop_name,es,Estación principal,S1\n"
        ),
    }
    translated = completeness(str(make_gtfs_zip(translated_feed)))

    assert translated.details["translations"]["has_translations"] is True
    assert translated.details["translations"]["languages"] == ["es"]
    assert translated.score == plain.score
    assert translated.findings == plain.findings


def test_fare_free_credits_fares_and_drops_the_penalty(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {k: v for k, v in COMPLETE_FEED.items() if k != "fare_attributes.txt"}
    path = make_gtfs_zip(feed)

    docked = completeness(str(path))
    credited = completeness(str(path), fare_free=True)

    # The fares component is restored, so a fare-free agency is not docked.
    assert credited.details["components"]["fares"] == WEIGHTS["fares"]
    assert docked.details["components"]["fares"] == 0.0
    assert credited.score > docked.score

    docked_codes = {f.code for f in docked.findings}
    credited_codes = {f.code for f in credited.findings}
    assert "scorecard_no_fare_data" in docked_codes
    assert "scorecard_no_fare_data" not in credited_codes
    # The policy is surfaced as a neutral, zero-deduction note, not hidden.
    note = next(f for f in credited.findings if f.code == "scorecard_fare_free")
    assert note.severity == "INFO"
    assert note.deduction == 0.0
    assert credited.details["fare_free"] is True
    assert "fare-free" in credited.summary


def test_partial_wheelchair_coverage_scales(make_gtfs_zip: Callable[..., Path]) -> None:
    feed = dict(COMPLETE_FEED)
    feed["stops.txt"] = (
        "stop_id,stop_name,wheelchair_boarding\n"
        "S1,Main St,1\n"
        "S2,Oak Ave,\n"  # unknown
    )
    result = completeness(str(make_gtfs_zip(feed)))
    # half of the 25 wheelchair-stop points lost
    assert result.score == 87.5
    finding = next(f for f in result.findings if f.code == "scorecard_wheelchair_boarding_unknown")
    assert finding.count == 1


def test_accessibility_is_prominent_in_summary(make_gtfs_zip: Callable[..., Path]) -> None:
    result = completeness(str(make_gtfs_zip(COMPLETE_FEED)))
    assert "wheelchair" in result.summary.lower()
    assert result.details["wheelchair_boarding_pct"] == 100.0


def test_summary_states_presence_not_usability(make_gtfs_zip: Callable[..., Path]) -> None:
    # The accessibility number is presence, not a usability check; say so, and
    # never collapse "marked not accessible" into the populated share.
    result = completeness(str(make_gtfs_zip(COMPLETE_FEED)))
    assert "not whether a stop is physically usable" in result.summary
    assert result.details["accessibility_measures"] == "presence_not_usability"
    assert "wheelchair_marked_not_accessible_pct" in result.details


def test_not_accessible_stops_reported_separately(make_gtfs_zip: Callable[..., Path]) -> None:
    feed = dict(COMPLETE_FEED)
    # Two stops: one accessible (1), one explicitly not accessible (2).
    feed["stops.txt"] = "stop_id,stop_name,wheelchair_boarding\nS1,Main St,1\nS2,Oak Ave,2\n"
    result = completeness(str(make_gtfs_zip(feed)))
    assert result.details["wheelchair_boarding_pct"] == 100.0  # both populated
    assert result.details["wheelchair_marked_accessible_pct"] == 50.0
    assert result.details["wheelchair_marked_not_accessible_pct"] == 50.0


def test_no_stops_feed_is_not_measured_not_scored_as_failure(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    """issue #286: a demand-response/Flex-only feed with zero stops must not
    be scored as if it had 0 stops all failing wheelchair_boarding/stop_name
    checks. Everything else on this feed is complete, so reweighting over
    only the measurable components should still earn 100."""
    feed = {
        "agency.txt": (
            "agency_id,agency_name,agency_url,agency_timezone\n"
            "yolo,Yolobus,https://yolobus.com,America/Los_Angeles\n"
        ),
        "feed_info.txt": (
            "feed_publisher_name,feed_publisher_url,feed_lang,feed_contact_email\n"
            "Yolobus,https://yolobus.com,en,data@yctd.org\n"
        ),
        "stops.txt": "stop_id,stop_name,wheelchair_boarding\n",
        "trips.txt": (
            "route_id,service_id,trip_id,trip_headsign,wheelchair_accessible\n"
            "R1,WK,T1,Anywhere in zone,1\n"
        ),
        "fare_attributes.txt": "fare_id,price,currency_type\nbase,2.25,USD\n",
    }
    result = completeness(str(make_gtfs_zip(feed)))

    assert result.score == 100.0
    codes = {f.code for f in result.findings}
    assert "scorecard_wheelchair_boarding_unknown" not in codes
    assert "scorecard_stop_names_all_caps" not in codes

    assert result.details["components"]["wheelchair_stops"] is None
    assert result.details["components"]["stop_names"] is None
    assert result.details["unmeasured_components"] == ["stop_names", "wheelchair_stops"]
    assert result.details["wheelchair_boarding_pct"] is None
    assert result.details["wheelchair_marked_accessible_pct"] is None
    assert result.details["wheelchair_marked_not_accessible_pct"] is None
    assert result.details["mixed_case_stop_name_pct"] is None
    # wheelchair_trips is still measurable (there are trips), so the
    # accessibility sub-score reweights over just that, not a fabricated 0.
    assert result.details["accessibility"]["score"] == 100.0
    assert result.details["accessibility"]["stops_stated_pct"] is None

    assert "no stops to state wheelchair accessibility for" in result.summary


def test_no_stops_feed_with_gaps_elsewhere_still_deducts_for_what_is_measurable(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    """The reweight must not become a loophole: a stopless feed that also
    fails a real, measurable check (no fare data) still loses those points."""
    feed = {
        "agency.txt": "agency_id,agency_name\nx,X\n",
        "stops.txt": "stop_id,stop_name,wheelchair_boarding\n",
        "trips.txt": (
            "route_id,service_id,trip_id,trip_headsign,wheelchair_accessible\nR1,WK,T1,Anywhere,1\n"
        ),
    }
    result = completeness(str(make_gtfs_zip(feed)))
    assert result.score < 100.0
    codes = {f.code for f in result.findings}
    assert "scorecard_no_fare_data" in codes
    assert "scorecard_no_feed_contact" in codes
    assert "scorecard_bad_agency_url" in codes
    # Still no fabricated wheelchair/stop-name findings for the 0 stops.
    assert "scorecard_wheelchair_boarding_unknown" not in codes
    assert "scorecard_stop_names_all_caps" not in codes


def test_unmeasured_components_empty_on_a_complete_feed(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    result = completeness(str(make_gtfs_zip(COMPLETE_FEED)))
    assert result.details["unmeasured_components"] == []


def test_no_trips_feed_does_not_fabricate_headsign_or_wheelchair_trip_failures(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = {
        "agency.txt": (
            "agency_id,agency_name,agency_url,agency_timezone\n"
            "yolo,Yolobus,https://yolobus.com,America/Los_Angeles\n"
        ),
        "feed_info.txt": (
            "feed_publisher_name,feed_publisher_url,feed_lang,feed_contact_email\n"
            "Yolobus,https://yolobus.com,en,data@yctd.org\n"
        ),
        "stops.txt": "stop_id,stop_name,wheelchair_boarding\nS1,Main St,1\n",
        "trips.txt": "route_id,service_id,trip_id,trip_headsign,wheelchair_accessible\n",
        "fare_attributes.txt": "fare_id,price,currency_type\nbase,2.25,USD\n",
    }
    result = completeness(str(make_gtfs_zip(feed)))
    codes = {f.code for f in result.findings}
    assert "scorecard_wheelchair_accessible_unknown" not in codes
    assert "scorecard_missing_headsigns" not in codes
    assert result.details["components"]["wheelchair_trips"] is None
    assert result.details["components"]["headsigns"] is None
    assert result.details["headsign_pct"] is None
    assert result.details["headsign_scored_pct"] is None
    assert result.score == 100.0


def test_numbers_and_punctuation_names_not_flagged_as_caps(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    feed = dict(COMPLETE_FEED)
    feed["stops.txt"] = "stop_id,stop_name,wheelchair_boarding\nS1,4 & B,1\n"
    result = completeness(str(make_gtfs_zip(feed)))
    assert "scorecard_stop_names_all_caps" not in {f.code for f in result.findings}
