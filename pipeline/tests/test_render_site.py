"""Tests for static-site rendering helpers (pure, no file I/O)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.render_site import (
    _accessibility_score,
    _accessibility_substat,
    _canonical_state,
    _changes_sections,
    _equity_choropleth,
    _fares_substat,
    _map_feature,
    _outreach_note,
    _outreach_section,
    _peer_context,
    _render_board_page,
    _render_equity_page,
    _render_map_page,
    _route_map_section,
    _standards_section,
    _vendor_request,
    _vendor_section,
    compute_changes,
)


def _artifact_with_route_map(**route_map: object) -> dict[str, object]:
    return {"agency": {"id": "demo", "name": "Demo Transit"}, "route_map": route_map}


def test_route_map_section_builds_accessible_table_and_skip_link() -> None:
    artifact = _artifact_with_route_map(
        routes=[
            {
                "id": "A",
                "label": "A",
                "long": "Main Line",
                "type_label": "Bus",
                "color": "0E6734",
                "color_name": "green",
                "has_shape": True,
            }
        ],
        route_count=1,
        drawn_route_count=1,
        stop_count=2,
        has_shapes=True,
        path="data/artifacts/demo/geometry.geojson",
    )
    html = _route_map_section(artifact, "demo", stop_names=["First Stop", "Second Stop"])
    # Bypass link before the map, targeting the data region.
    assert 'href="#route-data"' in html and "Skip to route and stop data" in html
    # The map canvas is the enhancement: aria-hidden so the table is the primary.
    assert 'id="route-map"' in html and 'aria-hidden="true"' in html
    # Accessible route table with scoped headers and color described in words.
    assert '<th scope="col">Route</th>' in html
    assert "Bus" in html and "green" in html and "Main Line" in html
    # Stop summary carries the count and the stop names.
    assert "2</strong>" in html and "First Stop" in html and "Second Stop" in html
    # MapLibre is wired up for the enhancement.
    assert "maplibregl" in html and "geometry.geojson" in html


def test_route_map_section_falls_back_to_stops_only_without_shapes() -> None:
    artifact = _artifact_with_route_map(
        routes=[
            {
                "id": "A",
                "label": "A",
                "type_label": "Bus",
                "color": "1A7A46",
                "color_name": "green",
                "has_shape": False,
            }
        ],
        route_count=1,
        drawn_route_count=0,
        stop_count=1,
        has_shapes=False,
        path="data/artifacts/demo/geometry.geojson",
    )
    html = _route_map_section(artifact, "demo", stop_names=["Only Stop"])
    assert "no route shapes" in html
    assert "Only Stop" in html
    # No legend when nothing is drawn.
    assert 'class="map-legend"' not in html


def test_route_map_section_empty_when_no_geometry() -> None:
    assert _route_map_section({"agency": {"id": "x", "name": "X"}}, "x") == ""
    assert _route_map_section(_artifact_with_route_map(routes=[], stop_count=0), "x") == ""


def test_ntd_section_is_us_only() -> None:
    from scorecard_pipeline.render_site import _ntd_section

    base: dict[str, Any] = {
        "feed": {"reachable": True, "static_url": "https://ex.org/g.zip"},
        "categories": {
            "correctness": {
                "status": "measured",
                "findings": [{"severity": "WARNING", "code": "w"}],
            },
            "freshness": {"status": "measured", "details": {"days_until_expiry": 90}},
        },
    }
    us = {**base, "agency": {"id": "d", "name": "D"}}  # no country -> US default
    ca = {**base, "agency": {"id": "wh", "name": "Whitehorse Transit", "country": "CA"}}
    assert "NTD" in _ntd_section(us)  # US agency gets the certification-readiness surface
    assert _ntd_section(ca) == ""  # non-US agency skips it (ADR 0026)


def test_canada_equity_section_is_canada_only() -> None:
    from scorecard_pipeline.render_site import _canada_equity_section

    assert _canada_equity_section({"agency": {"country": "US"}}) == ""  # US never shows it
    high = {"agency": {"country": "CA"}, "canada_equity": {"need_tier": "high"}}
    html = _canada_equity_section(high)
    assert "higher need" in html and "within-Canada" in html
    assert "National Transit Database" not in html  # Canadian, not US framing
    # A territory feed (computed, no CIMD coverage) shows a neutral note.
    territory = {"agency": {"country": "CA"}, "canada_equity": {"need_tier": "unknown"}}
    assert "does not cover the territories" in _canada_equity_section(territory)
    # A CA agency not yet computed (no record) shows nothing, NOT a false
    # territories note (reserved for feeds actually queried and out of coverage).
    assert _canada_equity_section({"agency": {"country": "CA"}}) == ""
    assert _canada_equity_section({"agency": {"country": "CA"}, "canada_equity": None}) == ""


def test_accessibility_score_prefers_structured_block() -> None:
    cat = {"status": "measured", "details": {"accessibility": {"score": 82.0}}}
    assert _accessibility_score(cat) == 82.0


def test_accessibility_score_derives_from_components_in_old_artifacts() -> None:
    # Artifacts published before ADR 0006 carry no accessibility block, only the
    # wheelchair components; the sub-score must still be derivable from them.
    cat = {
        "status": "measured",
        "details": {"components": {"wheelchair_stops": 25.0, "wheelchair_trips": 15.0}},
    }
    assert _accessibility_score(cat) == 100.0
    half = {"status": "measured", "details": {"components": {"wheelchair_stops": 12.5}}}
    assert _accessibility_score(half) == round(12.5 / 40 * 100, 1)


def test_fares_substat_reports_model_and_applied_state() -> None:
    applied = {"status": "measured", "details": {"fares": {"model": "v2", "applied": True}}}
    html = _fares_substat(applied)
    assert "Fares v2" in html and "applied to trips" in html

    unapplied = {"status": "measured", "details": {"fares": {"model": "v2", "applied": False}}}
    assert "not applied to any trip" in _fares_substat(unapplied)

    # Absent and fare-free render nothing here; the summary and findings cover them.
    assert _fares_substat({"status": "measured", "details": {"fares": {"model": "none"}}}) == ""
    assert (
        _fares_substat(
            {"status": "measured", "details": {"fares": {"model": "v2", "fare_free": True}}}
        )
        == ""
    )


def test_changes_page_splits_improved_and_declined() -> None:
    changes = [
        {
            "id": "up1",
            "name": "Up Transit",
            "from_grade": "C",
            "to_grade": "B",
            "from_score": 72,
            "to_score": 81,
            "score_delta": 9.0,
            "regressed": False,
            "since": "2026-06-10",
            "date": "2026-06-12",
        },
        {
            "id": "dn1",
            "name": "Down Transit",
            "from_grade": "B",
            "to_grade": "D",
            "from_score": 80,
            "to_score": 62,
            "score_delta": -18.0,
            "regressed": True,
            "since": "2026-06-10",
            "date": "2026-06-12",
        },
    ]
    html = _changes_sections(changes)
    assert "Most improved" in html and "Needs attention" in html
    assert "/agency/up1/" in html and "Up Transit" in html
    assert "/agency/dn1/" in html and "Down Transit" in html
    assert "C &rarr; B" in html  # grade transition shown
    # Direction is conveyed in text, not color alone.
    assert "up 9" in html and "down 18" in html


def test_changes_page_has_friendly_empty_states() -> None:
    html = _changes_sections([])
    assert "No agencies improved" in html
    assert "good day" in html


def test_standards_section_is_us_only() -> None:
    art = {
        "agency": {"country": "CA"},
        "categories": {"correctness": {"status": "measured", "score": 90}},
    }
    # The US-standards lens (FTA NTD, US state guidelines) is omitted for a non-US
    # agency until Tier 2 localizes it (ADR 0026); no US-federal framing leaks in.
    assert _standards_section(art, "") == ""


def test_standards_section_is_state_aware() -> None:
    art = {"categories": {"correctness": {"status": "measured", "score": 90}}}
    # The universal standards show for everyone.
    for state in ("California", "Texas", "Minnesota", ""):
        html = _standards_section(art, state)
        assert "National Transit Database" in html
        assert "MobilityData grading scheme" in html
    # California's published guideline (a quality rubric the score maps to).
    ca = _standards_section(art, "California")
    assert "California Transit Data Guidelines" in ca
    assert "published guideline" in ca
    # A program state is framed as a support program, not a guideline.
    mn = _standards_section(art, "Minnesota")
    assert "MnDOT Transit" in mn
    assert "transit-data program" in mn
    assert "published guideline" not in mn
    # A program state is told plainly which bars its score does map to (C2).
    assert "no quality rubric of its own" in mn
    # A state with no entry shows neither, only the universal standards.
    tx = _standards_section(art, "Texas")
    assert "California Transit Data Guidelines" not in tx
    assert "transit-data program" not in tx


def test_accessibility_score_none_when_not_measured() -> None:
    assert _accessibility_score({"status": "not_yet_measured"}) is None
    assert _accessibility_score({"status": "measured", "details": {}}) is None


def test_accessibility_substat_renders_meter_and_caveat() -> None:
    cat = {
        "status": "measured",
        "details": {
            "accessibility": {
                "score": 40.0,
                "stops_stated_pct": 40.0,
                "stops_marked_accessible_pct": 35.0,
            }
        },
    }
    html = _accessibility_substat(cat)
    assert 'role="meter"' in html and 'aria-valuenow="40"' in html
    assert "not verified physical usability" in html
    assert _accessibility_substat({"status": "not_yet_measured"}) == ""


def test_guide_shows_validator_stamp_and_methodology_changelog() -> None:
    """RESEARCH-ROADMAP R9: the how-to-read page surfaces the validator + rubric
    version stamp and the dated methodology changelog, not only the artifact JSON."""
    from scorecard_pipeline import RUBRIC_VERSION
    from scorecard_pipeline.render_site import _render_guide
    from scorecard_pipeline.score import methodology_changelog
    from scorecard_pipeline.validate import VALIDATOR_VERSION

    html = _render_guide()
    assert "Methodology and versions" in html
    assert VALIDATOR_VERSION in html
    assert f"v{RUBRIC_VERSION}" in html
    # Every changelog entry, with its effective date, is rendered.
    for entry in methodology_changelog():
        assert f"Effective {entry['effective_date']}" in html
        assert f"Rubric v{entry['rubric_version']}" in html


def test_guide_explains_grade_margins_and_weight_sensitivity() -> None:
    """FIX-07: the how-to-read page names the margin fields, frames a
    near-boundary grade as encouragement (never "almost failing"), and carries
    the weight-sensitivity summary (placeholder until the first study runs)."""
    from scorecard_pipeline.render_site import _render_guide

    html = _render_guide()
    assert "Grade margins and weight sensitivity" in html
    assert "margin_to_next_band" in html
    assert "margin_to_lower_band" in html
    # The no-shaming check: near-boundary framing is upward-looking.
    assert "0.4 points from an A" in html
    assert "encouragement, not a warning" in html
    # The study artifact is linked either way; with no published study (the
    # isolated test repo root has none) the placeholder branch renders.
    assert "/data/artifacts/sensitivity.json" in html


def test_vendor_request_lists_fixes_with_notice_codes() -> None:
    artifact = {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "overall": {"grade": "C", "score": 72.0},
        "top_fixes": [
            {
                "fix": "Set wheelchair_boarding on every stop.",
                "what": "12 stops blank.",
                "code": "scorecard_wheelchair_boarding_unknown",
            },
            {
                "fix": "Re-export with a longer calendar.",
                "what": "Expired 3 days ago.",
                "code": "scorecard_feed_expired",
            },
        ],
    }
    note = _vendor_request(artifact, CANONICAL)
    assert note is not None
    assert "Demo Transit" in note and "C (72.0 out of 100)" in note
    assert "Set wheelchair_boarding on every stop." in note
    assert "Validator notice: scorecard_feed_expired" in note
    assert CANONICAL in note


def test_vendor_request_none_without_fixes() -> None:
    artifact = {
        "agency": {"id": "d", "name": "D"},
        "overall": {"grade": "A", "score": 95},
        "top_fixes": [],
    }
    assert _vendor_request(artifact, CANONICAL) is None


def _fixable_artifact(static_url: str) -> dict:  # type: ignore[type-arg]
    return {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "overall": {"grade": "C", "score": 72.0},
        "feed": {"static_url": static_url},
        "top_fixes": [
            {"fix": "Re-export with a longer calendar.", "what": "Expired.", "code": "x"}
        ],
    }


def test_vendor_section_names_hosted_tool() -> None:
    # A Trillium-hosted feed: the heading and lede name Trillium, so the manager
    # knows the request goes to the service that produces the feed (R5).
    art = _fixable_artifact("https://data.trilliumtransit.com/gtfs/demo.zip")
    html = _vendor_section(art, CANONICAL)
    assert "Send Trillium a fix request" in html
    assert "produced and hosted by Trillium" in html
    assert "whoever runs your scheduling software export" not in html


def test_vendor_section_self_edit_tool_keeps_generic_heading() -> None:
    # GTFS Builder agencies usually make the change themselves; the heading stays
    # generic but the lede names the tool and the free help desk path.
    html = _vendor_section(_fixable_artifact("https://rapid.nationalrtap.org/file?id=1"), CANONICAL)
    assert "Send your vendor a fix request" in html
    assert "GTFS Builder" in html


def test_vendor_section_unknown_host_stays_generic() -> None:
    html = _vendor_section(_fixable_artifact("https://s3.amazonaws.com/bucket/gtfs.zip"), CANONICAL)
    assert "Send your vendor a fix request" in html
    assert "whoever runs your scheduling software export" in html


CANONICAL = "https://gtfsscorecard.org/agency/demo/"


def _idx(*entries: dict) -> dict:  # type: ignore[type-arg]
    return {"agencies": {e["id"]: e for e in entries}}


def test_compute_changes_flags_moves_and_sorts_regressions_first() -> None:
    index = _idx(
        {
            "id": "drop",
            "name": "Drop Transit",
            "history": [
                {"date": "2026-06-18", "grade": "B", "score": 85.0},
                {"date": "2026-06-19", "grade": "D", "score": 62.0},
            ],
        },
        {
            "id": "rise",
            "name": "Rise Transit",
            "history": [
                {"date": "2026-06-18", "grade": "C", "score": 74.0},
                {"date": "2026-06-19", "grade": "B", "score": 81.0},
            ],
        },
        {
            "id": "flat",
            "name": "Flat Transit",
            "history": [
                {"date": "2026-06-18", "grade": "A", "score": 92.0},
                {"date": "2026-06-19", "grade": "A", "score": 92.3},
            ],
        },
        {
            "id": "new",
            "name": "New Transit",
            "history": [{"date": "2026-06-19", "grade": "C", "score": 70.0}],
        },
    )
    changes = compute_changes(index)
    # flat (sub-threshold move) and new (single check) are excluded.
    assert [c["id"] for c in changes] == ["drop", "rise"]
    assert changes[0]["regressed"] is True  # the regression sorts first
    assert changes[0]["from_grade"] == "B" and changes[0]["to_grade"] == "D"
    assert changes[1]["regressed"] is False


def test_canonical_state_keeps_real_states_and_remaps_known_quirks() -> None:
    assert _canonical_state("California") == "California"
    assert _canonical_state("District of Columbia") == "District of Columbia"
    # Known Mobility Database mislabels remap to the right state.
    assert _canonical_state("Chicago") == "Illinois"
    assert _canonical_state("Lake Tahoe") == "California"
    # Anything else that isn't a recognized state drops to unlocated.
    assert _canonical_state("Some County") == ""
    assert _canonical_state("") == ""


def test_peer_context_renders_national_and_size_peer_and_state() -> None:
    html = _peer_context(
        {
            "national_percentile": 53,
            "peer_percentile": 68,
            "size_tier": "large",
            "state": "New Mexico",
        }
    )
    assert "Ahead of 53% of all tracked agencies" in html
    assert "68% of large agencies" in html
    assert "Operates in New Mexico." in html


def test_peer_context_omits_size_part_when_tier_unknown() -> None:
    html = _peer_context(
        {"national_percentile": 40, "peer_percentile": None, "size_tier": "unknown", "state": ""}
    )
    assert "Ahead of 40% of all tracked agencies." in html
    assert "agencies and" not in html  # no size-peer clause
    assert "Operates in" not in html


def test_peer_context_empty_without_record_or_percentile() -> None:
    assert _peer_context(None) == ""
    assert _peer_context({"national_percentile": None}) == ""


def _artifact(*findings: dict[str, str]) -> dict:  # type: ignore[type-arg]
    return {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "categories": {"freshness": {"findings": list(findings)}},
    }


def test_outreach_note_built_from_expiry_finding() -> None:
    art = _artifact(
        {
            "code": "scorecard_feed_expired",
            "what": "Service data ended 12 day(s) ago.",
            "why": "Trip planners stop showing this agency.",
            "fix": "Re-export with a longer calendar.",
        }
    )
    note = _outreach_note(art, CANONICAL)
    assert note is not None
    assert note.startswith("Hi Demo Transit team,")
    assert "Service data ended 12 day(s) ago." in note
    assert "Re-export with a longer calendar." in note
    assert CANONICAL in note


def _board_artifact() -> dict:  # type: ignore[type-arg]
    return {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "overall": {"grade": "B", "score": 84.0},
        "snapshot_date": "2026-07-01",
        "rubric_version": "1.4",
        "validator_version": "7.0.0",
        "feed": {"static_url": "https://data.trilliumtransit.com/gtfs/demo.zip"},
        "top_fixes": [
            {
                "fix": "Set wheelchair_boarding on every stop.",
                "what": "12 stops blank.",
                "why": "Riders using wheelchairs cannot plan trips.",
                "effort": "Usually one export setting.",
            }
        ],
        "categories": {"freshness": {"findings": []}},
    }


def test_board_page_leads_with_progress_and_frames_fixes_as_asks() -> None:
    prev = {
        "categories": {
            "freshness": {
                "status": "measured",
                "findings": [{"code": "expired_calendar", "what": "3 calendars expired."}],
            }
        }
    }
    html = _render_board_page(_board_artifact(), history=None, prev_artifact=prev)
    assert "Board packet" in html
    assert "Grade B" in html
    # The cleared finding reads as verified progress, before the asks.
    assert "fixed and verified" in html and "3 calendars expired." in html
    assert "What needs attention next" in html
    assert "Set wheelchair_boarding on every stop." in html
    # The producing tool is named so the board sees who does the work (R5).
    assert "Trillium" in html
    # It says what the grade does and does not measure.
    assert "not service" in html


def test_board_page_peer_standing_only_with_percentiles() -> None:
    record = {"national_percentile": 76, "peer_percentile": 88, "size_tier": "small"}
    html = _render_board_page(_board_artifact(), dir_record=record)
    assert "Where this agency stands" in html
    assert "76%" in html and "88%" in html and "small" in html
    plain = _render_board_page(_board_artifact(), dir_record={"state": "CA"})
    assert "Where this agency stands" not in plain


def test_board_page_without_fixes_asks_for_upkeep() -> None:
    art = _board_artifact()
    art["top_fixes"] = []
    html = _render_board_page(art)
    assert "continued upkeep" in html
    assert "No newly cleared items" in html


def test_fixlog_page_entries_are_dated_and_linkable() -> None:
    from scorecard_pipeline.render_site import _render_fixlog_page

    receipts = [
        {
            "code": "expired_calendar",
            "what": "3 calendars expired.",
            "last_seen": "2026-06-30",
            "cleared": "2026-07-01",
        },
        {
            "code": "unused_shape",
            "what": "54 unused shapes.",
            "last_seen": "2026-06-10",
            "cleared": "2026-06-11",
        },
    ]
    art = {"agency": {"id": "demo", "name": "Demo Transit"}}
    html = _render_fixlog_page(art, receipts)
    assert "2 verified fixes" in html
    # Every receipt is its own anchor with a self-link, newest first.
    assert 'id="r-2026-07-01-expired_calendar"' in html
    assert '"#r-2026-06-11-unused_shape"' in html
    assert html.index("expired_calendar") < html.index("unused_shape")
    assert "Reported through 2026-06-30" in html
    assert "the 2026-07-01 check verified it gone" in html


def test_outreach_note_names_hosted_tool() -> None:
    art = _artifact(
        {
            "code": "scorecard_feed_expired",
            "what": "Service data ended 12 day(s) ago.",
            "why": "Trip planners stop showing this agency.",
            "fix": "Re-export with a longer calendar.",
        }
    )
    art["feed"] = {"static_url": "https://data.trilliumtransit.com/gtfs/demo.zip"}
    note = _outreach_note(art, CANONICAL)
    assert note is not None
    assert "Your feed is produced by Trillium" in note


def test_no_outreach_note_without_expiry_finding() -> None:
    art = _artifact(
        {"code": "scorecard_missing_feed_info_dates", "what": "x", "why": "y", "fix": "z"}
    )
    assert _outreach_note(art, CANONICAL) is None
    assert _outreach_section(art, CANONICAL) == ""


def test_outreach_section_has_anchor_and_copy_button() -> None:
    art = _artifact(
        {
            "code": "scorecard_feed_expiring_soon",
            "what": "Runs out in 5 days.",
            "why": "w",
            "fix": "f",
        }
    )
    html = _outreach_section(art, CANONICAL)
    assert 'id="send-note"' in html
    assert "copy-btn" in html
    assert "<textarea" in html


def _measured(*findings: dict[str, str]) -> dict:  # type: ignore[type-arg]
    return {"categories": {"correctness": {"status": "measured", "findings": list(findings)}}}


def test_rule_ref_link_points_to_validator_rule_for_a_notice() -> None:
    from scorecard_pipeline.render_site import _rule_ref_link

    html = _rule_ref_link("expired_calendar")
    assert 'href="https://gtfs-validator.mobilitydata.org/rules.html#expired_calendar-rule"' in html
    assert "MobilityData GTFS Validator rules" in html
    # Descriptive, not "click here"; external destination announced for SR users.
    assert "click here" not in html.lower()
    assert "external site" in html


def test_rule_ref_link_uses_best_practice_for_completeness_code() -> None:
    from scorecard_pipeline.render_site import _rule_ref_link

    html = _rule_ref_link("scorecard_no_fare_data")
    assert "gtfs.org/schedule/best-practices/#fare_attributestxt" in html
    assert "GTFS Best Practices" in html


def test_rule_ref_link_empty_for_unmapped_scorecard_code() -> None:
    from scorecard_pipeline.render_site import _rule_ref_link

    assert _rule_ref_link("scorecard_flex_service") == ""


def test_fix_rule_reference_names_canonical_alias_for_scorecard_code() -> None:
    from scorecard_pipeline.render_site import _fix_rule_reference

    html = _fix_rule_reference("scorecard_missing_feed_info_dates")
    assert "Authoritative rule" in html
    # The reader sees the canonical validator notice they recognise.
    assert "missing_feed_info_date" in html
    assert "#missing_feed_info_date-rule" in html


def test_fix_rule_reference_for_direct_validator_notice() -> None:
    from scorecard_pipeline.render_site import _fix_rule_reference

    html = _fix_rule_reference("route_color_contrast")
    assert "canonical MobilityData GTFS Validator notice" in html
    assert "#route_color_contrast-rule" in html


def test_cleared_findings_lists_codes_gone_since_last_run() -> None:
    from scorecard_pipeline.render_site import _cleared_findings

    prev = _measured(
        {"code": "missing_trip_headsign", "what": "3 trips lack a headsign."},
        {"code": "stop_too_far_from_shape", "what": "A stop is far from its route."},
    )
    cur = _measured({"code": "stop_too_far_from_shape", "what": "A stop is far from its route."})
    cleared = _cleared_findings(prev, cur)
    assert cleared == [("missing_trip_headsign", "3 trips lack a headsign.")]


def test_no_cleared_without_previous_artifact() -> None:
    from scorecard_pipeline.render_site import _cleared_findings

    assert _cleared_findings(None, _measured({"code": "x", "what": "y"})) == []


def test_trend_section_shows_score_trend_and_category_deltas() -> None:
    from scorecard_pipeline.render_site import _trend_section

    history = [
        {"date": "2026-06-10", "score": 70.0, "grade": "C", "categories": {"correctness": 80.0}},
        {"date": "2026-06-11", "score": 75.0, "grade": "C", "categories": {"correctness": 90.0}},
    ]
    html = _trend_section(history)
    assert "Over time" in html
    assert "up 5.0" in html
    assert "trend-spark" in html
    # Finding-level change (cleared/new) is the feed-diff section's job now.
    assert "Fixed since your last check" not in html


def test_spark_svg_is_the_shared_accessible_sparkline() -> None:
    """The shared helper carries the three-part pattern: per-point hover titles,
    the full series in the aria-label, and an emphasised last dot."""
    from scorecard_pipeline.render_site import _spark_svg

    svg = _spark_svg(
        [("2026-06-10", 70.0), ("2026-06-11", 75.5), ("2026-06-12", 75.5)],
        aria_label="Overall score across 3 checks",
    )
    assert svg.startswith('<svg class="trend-spark"')
    assert 'role="img"' in svg
    assert 'aria-label="Overall score across 3 checks: ' in svg
    assert "2026-06-10 70.0; 2026-06-11 75.5; 2026-06-12 75.5" in svg
    # Every check gets a hover/long-press readout; the last dot is emphasised.
    assert svg.count("<title>") == 3
    assert "<title>2026-06-11: 75.5</title>" in svg
    assert svg.count('r="2.5"') == 2 and svg.count('r="4"') == 1
    assert "<polyline points=" in svg


def test_spark_svg_autoscales_to_a_supplied_y_range() -> None:
    from scorecard_pipeline.render_site import _spark_svg

    svg = _spark_svg(
        [("2026-06-01", 70.0), ("2026-07-01", 71.0)],
        aria_label="National average score by date (axis 70.0 to 71.0)",
        w=640,
        h=120,
        pad=12,
        y_min=70.0,
        y_max=71.0,
    )
    # With the data's own min/max as the axis, the two points span the full
    # drawable height: first at the bottom (h - pad), last at the top (pad).
    assert 'viewBox="0 0 640 120"' in svg
    assert '<polyline points="12.0,108.0 628.0,12.0"' in svg
    assert "(axis 70.0 to 71.0)" in svg


def test_spark_mini_renders_compact_or_em_dash() -> None:
    from scorecard_pipeline.render_site import _spark_mini

    history = [
        {"date": "2026-06-10", "score": 70.0, "grade": "C"},
        {"date": "2026-06-11", "score": 75.0, "grade": "C"},
    ]
    mini = _spark_mini(history, "Acme Transit")
    assert 'class="trend-spark spark-mini"' in mini
    assert 'aria-label="Score trend for Acme Transit: 2026-06-10 70.0; 2026-06-11 75.0"' in mini
    assert "<title>2026-06-11: 75.0</title>" in mini
    # A single check (or no history) is an em dash, never an empty chart.
    assert _spark_mini(history[:1], "Acme Transit") == '<span class="spark-none">&mdash;</span>'
    assert _spark_mini(None, "Acme Transit") == '<span class="spark-none">&mdash;</span>'


def test_leaderboard_rows_carry_mini_sparklines() -> None:
    from scorecard_pipeline.render_site import _leaderboard_sections

    board = {
        "top": [{"id": "a-t", "name": "Alpha", "grade": "A", "score": 95}],
        "bottom": [{"id": "z-t", "name": "Zulu", "grade": "F", "score": 20}],
        "most_improved": [
            {"id": "a-t", "name": "Alpha", "grade": "A", "score": 95, "score_delta": 2.0}
        ],
        "most_declined": [],
    }
    histories = {
        "a-t": [
            {"date": "2026-06-10", "score": 93.0, "grade": "A"},
            {"date": "2026-06-11", "score": 95.0, "grade": "A"},
        ]
    }
    html = _leaderboard_sections(board, histories)
    assert "<th>Trend</th>" in html
    assert 'aria-label="Score trend for Alpha: 2026-06-10 93.0; 2026-06-11 95.0"' in html
    assert "spark-mini" in html
    # Zulu has no history yet: its trend cell is an em dash, not an empty chart.
    assert '<span class="spark-none">&mdash;</span>' in html
    # Without histories at all, every trend cell degrades to the em dash.
    assert "spark-mini" not in _leaderboard_sections(board)


def test_leaderboard_sections_omit_trips_column_without_ridership() -> None:
    from scorecard_pipeline.render_site import _leaderboard_sections

    board = {
        "top": [{"id": "a", "name": "A Transit", "grade": "A", "score": 90}],
        "bottom": [{"id": "z", "name": "Z Transit", "grade": "F", "score": 40}],
        "most_improved": [],
        "most_declined": [],
    }
    html = _leaderboard_sections(board)
    assert "Riders/yr" not in html
    assert "Lowest scoring" in html


def test_leaderboard_sections_show_trips_column_when_present() -> None:
    from scorecard_pipeline.render_site import _leaderboard_sections

    board = {
        "top": [{"id": "a", "name": "A Transit", "grade": "A", "score": 90}],
        "bottom": [
            {
                "id": "big",
                "name": "Big Transit",
                "grade": "F",
                "score": 40,
                "annual_trips": 5000000,
            },
            {"id": "tiny", "name": "Tiny Transit", "grade": "F", "score": 40},
        ],
        "most_improved": [],
        "most_declined": [
            {
                "id": "dn",
                "name": "Down Transit",
                "grade": "D",
                "score": 60,
                "score_delta": -12.0,
                "annual_trips": 250000,
            }
        ],
    }
    html = _leaderboard_sections(board)
    assert "Riders/yr" in html
    # Human-formatted with thousands separators, matching the impact line.
    assert "5,000,000" in html
    assert "250,000" in html
    # A row without a matched ridership record renders an empty cell, not "None".
    assert ">None<" not in html
    # The unweighted "top" table (no trips on any row) keeps its column shape.
    assert html.count("Riders/yr") == 2


def _diff_artifact(
    *,
    date: str,
    grade: str,
    score: float,
    findings: list[dict] | None = None,  # type: ignore[type-arg]
    sha256: str = "aaa",
) -> dict:  # type: ignore[type-arg]
    return {
        "snapshot_date": date,
        "overall": {"grade": grade, "score": score},
        "feed": {"sha256": sha256, "size_bytes": 1000},
        "categories": {
            "correctness": {
                "status": "measured",
                "score": score,
                "findings": findings or [],
            },
        },
    }


def test_feeddiff_section_empty_without_previous_snapshot() -> None:
    from scorecard_pipeline.render_site import _feeddiff_section

    cur = _diff_artifact(date="2026-06-12", grade="B", score=82.0)
    assert _feeddiff_section(None, cur, "acme") == ""


def test_feeddiff_section_lists_new_and_resolved_findings() -> None:
    from scorecard_pipeline.render_site import _feeddiff_section

    prev = _diff_artifact(
        date="2026-06-11",
        grade="B",
        score=82.0,
        findings=[{"code": "old_one", "count": 2, "severity": "WARNING", "what": "an old issue"}],
    )
    cur = _diff_artifact(
        date="2026-06-12",
        grade="C",
        score=74.0,
        sha256="bbb",
        findings=[{"code": "new_one", "count": 4, "severity": "ERROR", "what": "a new issue"}],
    )
    html = _feeddiff_section(prev, cur, "acme")
    assert "What changed in this feed" in html
    assert "New since 2026-06-11" in html
    assert "a new issue" in html
    assert "Resolved since 2026-06-11" in html
    assert "an old issue" in html
    # The feed-bytes change and the grade drop are both stated in words.
    assert "re-published" in html
    assert "dropped" in html
    # The per-agency Atom feed is offered for subscription.
    assert "/agency/acme/feed.xml" in html


def test_feeddiff_section_reports_no_change_when_identical() -> None:
    from scorecard_pipeline.render_site import _feeddiff_section

    art = _diff_artifact(
        date="2026-06-12",
        grade="B",
        score=82.0,
        findings=[{"code": "x", "count": 1, "severity": "INFO", "what": "y"}],
    )
    prev = _diff_artifact(
        date="2026-06-11",
        grade="B",
        score=82.0,
        findings=[{"code": "x", "count": 1, "severity": "INFO", "what": "y"}],
    )
    html = _feeddiff_section(prev, art, "acme")
    assert "Nothing changed since 2026-06-11" in html


def test_history_section_narrates_changes_and_is_empty_when_steady() -> None:
    from scorecard_pipeline.render_site import _history_section

    history = [
        {
            "date": "2026-06-10",
            "score": 84.0,
            "grade": "B",
            "days_until_expiry": 80,
            "categories": {"freshness": 85.0},
        },
        {
            "date": "2026-06-14",
            "score": 70.0,
            "grade": "C",
            "days_until_expiry": 78,
            "categories": {"freshness": 40.0},
        },
    ]
    html = _history_section(history)
    assert "What changed over time" in html
    assert "2026-06-14" in html and "Grade went B to C" in html
    # A flat feed gets nothing.
    steady = [
        {
            "date": "2026-06-10",
            "score": 84.0,
            "grade": "B",
            "days_until_expiry": 80,
            "categories": {},
        },
        {
            "date": "2026-06-11",
            "score": 84.2,
            "grade": "B",
            "days_until_expiry": 79,
            "categories": {},
        },
    ]
    assert _history_section(steady) == ""
    assert _history_section(None) == ""


def test_embed_section_offers_a_live_badge_and_copyable_markdown() -> None:
    from scorecard_pipeline.render_site import _embed_section

    html = _embed_section("demo-transit", "Demo Transit")
    assert "Show your grade" in html
    # A live badge preview and a copyable Markdown snippet pointing at the
    # published badge.svg and the agency page.
    assert "/data/artifacts/demo-transit/badge.svg" in html
    assert "https://gtfsscorecard.org/agency/demo-transit/" in html
    assert 'class="copy-btn"' in html and 'data-copy="embed-md"' in html
    # The shields.io endpoint alternative points at badge.json.
    assert "img.shields.io/endpoint" in html and "badge.json" in html
    assert "Demo Transit" in html  # alt text names the agency


def test_recommendations_section_lists_items_and_is_empty_without_any() -> None:
    from scorecard_pipeline.render_site import _recommendations_section

    art = {
        "recommendations": [
            {
                "code": "scorecard_fares_v2_rider_categories",
                "what": "No rider categories.",
                "fix": "Add rider_categories.txt so apps can show senior and youth fares.",
            }
        ]
    }
    html = _recommendations_section(art)
    assert "Beyond the grade" in html
    assert "rider_categories" in html and "Consider:" in html
    assert _recommendations_section({"recommendations": []}) == ""
    assert _recommendations_section({}) == ""


def test_anomaly_note_flags_a_transient_dip_and_is_empty_when_steady() -> None:
    from scorecard_pipeline.render_site import _anomaly_note

    dip = [
        {"date": "2026-06-16", "score": 80.0, "grade": "B", "days_until_expiry": 83},
        {"date": "2026-06-19", "score": 44.0, "grade": "F", "days_until_expiry": -138},
        {"date": "2026-06-20", "score": 83.0, "grade": "B", "days_until_expiry": 79},
    ]
    html = _anomaly_note(dip)
    assert "Heads-up" in html and "anomaly-note" in html
    steady = [
        {"date": "2026-06-19", "score": 82.0, "grade": "B", "days_until_expiry": 80},
        {"date": "2026-06-20", "score": 83.0, "grade": "B", "days_until_expiry": 79},
    ]
    assert _anomaly_note(steady) == ""
    assert _anomaly_note([]) == ""


def test_google_gate_line_reports_coverage_status() -> None:
    from scorecard_pipeline.render_site import _google_gate_line

    ok = {"categories": {"freshness": {"details": {"last_service_date": "2027-01-01"}}}}
    assert "Clears" in _google_gate_line(ok)
    expired = {"categories": {"freshness": {"details": {"last_service_date": "2020-01-01"}}}}
    assert "Below" in _google_gate_line(expired)


def test_google_gate_line_answers_will_riders_see_me_for_low_grades() -> None:
    # A warning-heavy, error-free feed reads as visible to riders: the grade is
    # low here, but Maps does not drop it (review finding, A1).
    from scorecard_pipeline.render_site import _google_gate_line

    warned = {
        "categories": {
            "freshness": {"details": {"last_service_date": "2027-01-01"}},
            "correctness": {
                "status": "measured",
                "findings": [{"severity": "WARNING", "count": 96, "code": "w"}],
            },
        }
    }
    line = _google_gate_line(warned)
    assert "No validator errors" in line
    assert "do not remove a feed" in line
    # Real errors are named, with the pointer to the fixes below.
    errored = {
        "categories": {
            "freshness": {"details": {"last_service_date": "2027-01-01"}},
            "correctness": {
                "status": "measured",
                "findings": [{"severity": "ERROR", "count": 3, "code": "e"}],
            },
        }
    }
    line = _google_gate_line(errored)
    assert "3 validator errors" in line


def test_brief_carries_outreach_standards_and_portfolio_link() -> None:
    from scorecard_pipeline.render_site import _render_brief

    lapsed = {
        "agency": {"id": "demo-t", "name": "Demo Transit"},
        "overall": {"grade": "D", "score": 61.0},
        "snapshot_date": "2026-07-01",
        "feed": {"static_url": "https://ex.org/gtfs.zip"},
        "categories": {
            "freshness": {
                "status": "measured",
                "details": {"days_until_expiry": -30, "last_service_date": "2026-06-01"},
                "findings": [
                    {
                        "code": "scorecard_feed_expired",
                        "what": "The feed's service data ran out 30 days ago.",
                        "why": "Trip planners drop an expired agency.",
                        "fix": "Re-export with a current calendar.",
                    }
                ],
            },
        },
        "top_fixes": [],
    }
    html = _render_brief(
        lapsed,
        dir_record={"state": "California"},
        program_ids={"california"},
    )
    # The lapsed feed's outreach note rides on the brief itself, printably.
    assert "Ready to send to the agency" in html
    assert "brief-outreach" in html
    # The state guideline the score answers to is cited on-page.
    assert "California Transit Data Guidelines" in html
    # The portfolio backlink renders only when the rollup page exists.
    assert 'href="/program/california/"' in html
    no_rollup = _render_brief(lapsed, dir_record={"state": "California"}, program_ids=set())
    assert 'href="/program/california/"' not in no_rollup


def test_ntd_section_maps_pillars_and_labels_status_in_text() -> None:
    from scorecard_pipeline.render_site import _ntd_section

    art = {
        "feed": {"reachable": True, "static_url": "https://ex.org/g.zip"},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "freshness": {"status": "measured", "details": {"days_until_expiry": 90}},
        },
    }
    html = _ntd_section(art)
    # The NTD abbreviation is wrapped for 3.1.4, so the heading reads
    # "<abbr ...>NTD</abbr> certification readiness".
    assert "certification readiness" in html
    assert ">NTD</abbr>" in html
    assert "Published" in html and "Valid" in html and "Current" in html
    assert "Ready" in html  # status is conveyed in text, not color alone
    assert "D-10" in html
    assert "National Transit Database" in html

    expired = {
        "feed": {"reachable": True, "static_url": "https://ex.org/g.zip"},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "freshness": {"status": "measured", "details": {"days_until_expiry": -200}},
        },
    }
    assert "Not ready" in _ntd_section(expired)


def test_ntd_section_renders_id_alignment_when_present() -> None:
    from scorecard_pipeline.render_site import _ntd_section

    base = {
        "feed": {"reachable": True, "static_url": "https://ex.org/g.zip"},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "freshness": {"status": "measured", "details": {"days_until_expiry": 90}},
        },
    }
    # A mismatch shows the optional alignment as a neutral "Not aligned", never as
    # a required change (RESEARCH-ROADMAP R7).
    mismatch = {
        **base,
        "ntd_id_alignment": {
            "status": "mismatch",
            "detail": "Your feed uses agency_id UNITRANS.",
            "fix": "Optionally set the agency_id to 90142 in agency.txt.",
            "ntd_id": "90142",
            "feed_agency_ids": ["UNITRANS"],
        },
    }
    html = _ntd_section(mismatch)
    assert "agency_id matches your NTD ID" in html
    assert "Not aligned" in html
    assert "Needs attention" not in html
    # The wording is recomputed at render time from the stored inputs, so a
    # stale artifact can never resurface pre-final-rule prescriptive copy: the
    # fixture's baked-in strings are ignored in favour of the current ones.
    assert "Optionally set the agency_id for your service to 90142" in html
    assert "Your feed uses agency_id UNITRANS." not in html
    # The fineprint cites the final rule and the P-50 crosswalk, not a feed mandate.
    assert "P-50 form" in html
    assert "final rule" in html

    # Absent block (older artifacts) renders no alignment row.
    assert "agency_id matches your NTD ID" not in _ntd_section(base)


def test_ntd_section_renders_shapes_readiness_when_present() -> None:
    from scorecard_pipeline.render_site import _ntd_section

    base = {
        "feed": {"reachable": True, "static_url": "https://ex.org/g.zip"},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "freshness": {"status": "measured", "details": {"days_until_expiry": 90}},
        },
    }
    partial = {
        **base,
        "shapes_readiness": {
            "status": "at_risk",
            "detail": "stale detail baked into the fixture",
            "fix": "stale fix baked into the fixture",
            "total_trips": 10,
            "trips_with_shape": 6,
        },
    }
    html = _ntd_section(partial)
    assert "shapes.txt covers your trips" in html
    assert "Needs attention" in html
    # Recomputed at render time from the stored counts, so wording fixes reach
    # every page without a rescore (same pattern as agency_id alignment).
    assert "6 of 10 trips have a shape" in html
    assert "stale detail baked into the fixture" not in html
    # The fineprint cites the RY2025/26 shapes.txt requirement.
    assert "Report Year 2026" in html and "Report Year 2025" in html

    # Absent block (older artifacts, or a feed scored before this check shipped)
    # renders no shapes row.
    assert "shapes.txt covers your trips" not in _ntd_section(base)


def _member(agency_id: str, shapes_status: str | None, grade: str = "C") -> dict[str, Any]:
    return {
        "id": agency_id,
        "name": f"{agency_id.title()} Transit",
        "grade": grade,
        "score": 75.0,
        "snapshot_date": "2026-06-12",
        "shapes_status": shapes_status,
    }


def test_rollup_shapes_section_lists_gaps_not_ready_first() -> None:
    from scorecard_pipeline.render_site import _rollup_shapes_section

    rollup = {
        "members": [
            _member("ready1", "ready"),
            _member("risk1", "at_risk"),
            _member("notready1", "not_ready"),
        ],
        "shapes_readiness": {
            "ready": 1,
            "at_risk": 1,
            "not_ready": 1,
            "not_measured": 0,
            "total": 3,
        },
    }
    html = _rollup_shapes_section(rollup)
    assert "shapes.txt coverage" in html
    assert "1 of 3" in html
    assert "Notready1 Transit" in html and "Risk1 Transit" in html
    assert "Ready1 Transit" not in html  # only the gaps are listed
    # not_ready sorts ahead of at_risk in the worklist.
    assert html.index("Notready1 Transit") < html.index("Risk1 Transit")


def test_rollup_shapes_section_empty_when_all_ready() -> None:
    from scorecard_pipeline.render_site import _rollup_shapes_section

    rollup = {
        "members": [_member("a", "ready")],
        "shapes_readiness": {
            "ready": 1,
            "at_risk": 0,
            "not_ready": 0,
            "not_measured": 0,
            "total": 1,
        },
    }
    assert _rollup_shapes_section(rollup) == ""


def test_rollup_shapes_section_empty_when_nothing_measured() -> None:
    from scorecard_pipeline.render_site import _rollup_shapes_section

    rollup = {
        "members": [_member("a", None)],
        "shapes_readiness": {
            "ready": 0,
            "at_risk": 0,
            "not_ready": 0,
            "not_measured": 1,
            "total": 1,
        },
    }
    assert _rollup_shapes_section(rollup) == ""


def test_liveness_note_shows_checked_and_changed_freshness() -> None:
    import datetime as dt

    from scorecard_pipeline.render_site import _liveness_note

    now = dt.datetime(2026, 6, 20, 12, 0, tzinfo=dt.UTC)
    rec = {
        "checked_at": "2026-06-20T09:00:00+00:00",  # 3 hours before now
        "changed_at": "2026-06-18T12:00:00+00:00",  # 2 days before now
        "status": 200,
    }
    html = _liveness_note(rec, now)
    assert "Checked for changes 3 hours ago" in html
    assert "last changed 2 days ago" in html
    assert "monitoring-note" in html
    # An outage status is surfaced.
    down = _liveness_note({"checked_at": "2026-06-20T11:30:00+00:00", "status": 403}, now)
    assert "HTTP 403" in down
    # Not yet checked: nothing rather than a blank claim.
    assert _liveness_note(None, now) == ""
    assert _liveness_note({"status": 200}, now) == ""


def test_standards_section_is_per_agency_and_includes_google() -> None:
    from scorecard_pipeline.render_site import _standards_section

    art = {
        "categories": {
            "correctness": {"status": "measured", "score": 82.0},
            "freshness": {"status": "measured", "score": 40.0},
            "completeness": {"status": "measured", "score": 60.0},
            "realtime": {"status": "not_yet_measured"},
        }
    }
    html = _standards_section(art)
    assert "How this agency maps to the standards" in html
    assert "82 / 100" in html  # the agency's own correctness score
    assert "Not yet published" in html  # realtime not measured
    assert "Google Transit" in html
    assert "not a compliance determination" in html


# ---- national grade map (/map/) ----


def _sample_artifact(grade: str = "C", lon: float = -96.0, lat: float = 39.0) -> dict[str, Any]:
    return {
        "agency": {"name": "Test Transit"},
        "overall": {"grade": grade, "score": 71.5},
        "geo": {"lon": lon, "lat": lat},
    }


def test_map_feature_carries_grade_state_and_letter_color() -> None:
    feat = _map_feature("test-transit", _sample_artifact("B"), "Iowa")
    assert feat is not None
    props = feat["properties"]
    assert props["grade"] == "B"
    assert props["state"] == "Iowa"
    assert props["score"] == 71.5
    assert props["url"] == "/agency/test-transit/"
    # Colour is reinforcement only; the grade letter itself rides in the feature.
    assert props["color"].startswith("#")


def test_map_feature_none_without_geometry() -> None:
    assert _map_feature("x", {"agency": {"name": "X"}, "overall": {"grade": "A"}}) is None


def _map_features() -> list[dict[str, Any]]:
    feats = [
        _map_feature("alpha-transit", _sample_artifact("A", -97.0, 40.0), "Iowa"),
        _map_feature("bravo-transit", _sample_artifact("F", -80.0, 35.0), "Ohio"),
    ]
    return [f for f in feats if f is not None]


def test_render_map_page_has_accessible_table_and_skip_link() -> None:
    html = _render_map_page(_map_features())
    # The conformant primary: a bypass link and a real table of every agency.
    assert 'href="#agency-list"' in html
    assert "Skip to the agency list" in html
    assert 'id="agency-list"' in html
    assert '<table class="leaderboard map-table">' in html
    # Each row carries grade, state, score, and a scorecard link as text.
    assert 'href="/agency/alpha-transit/"' in html
    assert 'data-grade="A"' in html and 'data-state="Iowa"' in html
    assert 'data-grade="F"' in html and 'data-state="Ohio"' in html


def test_render_map_page_filters_cover_grade_and_state() -> None:
    html = _render_map_page(_map_features())
    assert 'id="map-grade"' in html and 'id="map-state"' in html
    # State options are derived from the agencies actually on the map.
    assert '<option value="Iowa">Iowa</option>' in html
    assert '<option value="Ohio">Ohio</option>' in html


def test_map_feature_reads_flex_from_completeness_details() -> None:
    art = _sample_artifact("B")
    art["categories"] = {
        "completeness": {"details": {"flex": {"has_flex": True, "bookable": False}}}
    }
    feat = _map_feature("flex-transit", art, "Iowa")
    assert feat is not None
    assert feat["properties"]["has_flex"] is True
    # Absent flex details read as no flex, never an error.
    plain = _map_feature("plain-transit", _sample_artifact("B"), "Ohio")
    assert plain is not None
    assert plain["properties"]["has_flex"] is False


def test_render_map_page_flex_filter_rides_on_rows_and_checkbox() -> None:
    art = _sample_artifact("A", -97.0, 40.0)
    art["categories"] = {"completeness": {"details": {"flex": {"has_flex": True}}}}
    feats = [
        _map_feature("flex-transit", art, "Iowa"),
        _map_feature("plain-transit", _sample_artifact("F", -80.0, 35.0), "Ohio"),
    ]
    html = _render_map_page([f for f in feats if f is not None])
    assert 'id="map-flex"' in html
    assert "GTFS-Flex" in html
    assert 'data-has-flex="true"' in html
    assert 'data-has-flex="false"' in html


def test_otp_section_gated_on_routing_qa() -> None:
    from scorecard_pipeline.render_site import _otp_section

    # No block, or an unmeasured one: the page renders exactly as before.
    assert _otp_section({}) == ""
    assert _otp_section({"routing_qa": {"status": "pending"}}) == ""
    assert _otp_section({"routing_qa": {"status": "measured", "details": {}}}) == ""
    art = {
        "routing_qa": {
            "status": "measured",
            "score": 98.4,
            "details": {
                "total_sampled": 125,
                "routable_trips": 123,
                "notes": "Two late-night trips fell outside the service window.",
            },
        }
    }
    html = _otp_section(art)
    assert "123 of 125" in html
    assert "OpenTripPlanner" in html
    assert "does not change the grade" in html
    assert "late-night" in html


def test_render_compare_page_form_is_shareable_and_neutral() -> None:
    from scorecard_pipeline.pages_tools import _render_compare_page

    catalog = [
        {"id": "bravo-transit", "name": "Bravo Transit", "state": "Ohio"},
        {"id": "alpha-transit", "name": "Alpha Transit", "state": "Iowa"},
    ]
    html = _render_compare_page(catalog)
    # A GET form: choosing agencies works without JS and every comparison is a URL.
    assert 'method="get"' in html and 'action="/compare/"' in html
    assert 'id="compare-a"' in html and 'id="compare-b"' in html
    # Options are sorted by name and carry the state as a disambiguator.
    a = html.index("Alpha Transit")
    b = html.index("Bravo Transit")
    assert a < b
    assert '<option value="alpha-transit">Alpha Transit &mdash; Iowa</option>' in html
    # A missing realtime feed reads as not yet published, never as a zero.
    assert "Not yet published" in html
    # Loading and errors are announced, and the no-JS path is honest.
    assert 'role="status"' in html
    assert "<noscript>" in html
    # The result table is emphasised in text, never colour alone.
    assert "visually-hidden" in html and "(higher)" in html


def test_render_map_page_marker_shows_grade_not_color_only() -> None:
    html = _render_map_page(_map_features())
    # A symbol layer draws the grade letter on every point (WCAG 1.4.1).
    assert '"text-field": ["get", "grade"]' in html
    # Clustering at low zoom, and reduced-motion is honoured for the cluster zoom.
    assert "cluster: true" in html
    assert "prefers-reduced-motion" in html
    # The canvas is an enhancement: aria-hidden, no on-canvas controls.
    assert 'id="map" class="national-map" aria-hidden="true"' in html
    assert "NavigationControl" not in html
    assert "attributionControl: false" in html


# ---- equity choropleth (/equity/) ----


_EQUITY: dict[str, Any] = {
    "priority": [
        {
            "state": "Louisiana",
            "low_grade_share": 100.0,
            "agency_count": 3,
            "median_score": 37.4,
            "need_tier": "high",
        }
    ],
    "states": [
        {
            "state": "Louisiana",
            "low_grade_share": 100.0,
            "agency_count": 3,
            "median_score": 37.4,
            "need_tier": "high",
        },
        {
            "state": "Iowa",
            "low_grade_share": 20.0,
            "agency_count": 10,
            "median_score": 78.0,
            "need_tier": "lower",
        },
    ],
}

_GEO: dict[str, Any] = {
    "viewBox": "0 0 960 600",
    "states": {
        "Louisiana": "M0,0L10,0L10,10Z",
        "Iowa": "M20,20L30,20L30,30Z",
        "Nowhere": "M40,40L50,40L50,50Z",
    },
}


def test_equity_choropleth_encodes_tier_with_text_and_pattern() -> None:
    by_state: dict[str, dict[str, Any]] = {s["state"]: s for s in _EQUITY["states"]}
    svg = _equity_choropleth(_GEO, by_state)
    # High tier gets its colour class and a hatch pattern overlay (not colour only).
    assert "need-high" in svg and 'fill="url(#needHatchDense)"' in svg
    # Each state names its tier and numbers in title text for AT and hover.
    assert "Louisiana: High need, 100.0% of feeds on D or F, 3 agencies" in svg
    # A state with no overlay row renders faint and inert.
    assert 'class="need-state need-empty" aria-hidden="true"' in svg
    # The legend reinforces colour with words.
    assert "High need" in svg and "Lower need" in svg


def test_render_equity_page_pairs_map_with_full_state_table() -> None:
    html = _render_equity_page(_EQUITY, _GEO)
    # The map plus the bypass to the tables that carry the same numbers.
    assert "Skip to the state tables" in html
    assert 'class="us-map-svg"' in html
    # The full per-state table carries every number the map encodes.
    assert "Every state" in html
    assert "Iowa" in html and "20.0%" in html
    # The priority table is kept.
    assert "High-need states" in html


def test_render_equity_page_without_overlay_is_neutral_and_mapless() -> None:
    html = _render_equity_page({}, _GEO)
    assert "us-map-svg" not in html  # no map without overlay data
    assert "Skip to the state tables" not in html
    assert "No state currently meets the high-need threshold" in html


def test_render_equity_page_without_geometry_keeps_tables() -> None:
    html = _render_equity_page(_EQUITY, None)
    assert "us-map-svg" not in html
    assert "High-need states" in html and "Every state" in html


def test_ntd_page_carries_ry2026_and_one_fix_table() -> None:
    from scorecard_pipeline.render_site import _render_ntd_page

    payload = {
        "total": 2,
        "ready": 1,
        "at_risk": 1,
        "not_ready": 0,
        "pct_ready": 50.0,
        "by_state": {"Iowa": {"ready": 1, "at_risk": 1, "not_ready": 0, "total": 2}},
        "one_fix_from_ready": [
            {
                "id": "close-t",
                "name": "Close Transit",
                "state": "Iowa",
                "pillar": "current",
                "fix": "Service data runs out in 12 days; renew before you certify.",
                "status": "at_risk",
            }
        ],
        "one_fix_total": 1,
    }
    histories = {
        "close-t": [
            {"date": "2026-06-10", "score": 71.0, "grade": "C"},
            {"date": "2026-06-11", "score": 72.0, "grade": "C"},
        ]
    }
    html = _render_ntd_page(payload, histories)
    # The RY2026 wave and the waiver path are named, with the rule cited.
    assert "Report year 2026" in html
    assert "waiver" in html
    assert "federalregister.gov" in html
    # The triage list renders with the forwardable fix text.
    assert "One fix from ready" in html
    assert 'href="/agency/close-t/"' in html
    assert "renew before you certify" in html
    # Each row carries a small score sparkline in the same accessible pattern.
    assert "<th>Trend</th>" in html
    assert 'aria-label="Score trend for Close Transit: ' in html
    assert "spark-mini" in html
    # Without histories the trend cell degrades to an em dash, never breaks.
    assert '<span class="spark-none">&mdash;</span>' in _render_ntd_page(payload)


def test_rt_page_most_reliable_rows_carry_mini_sparklines() -> None:
    from scorecard_pipeline.render_site import _render_rt_page

    nat = {
        "monitored_count": 1,
        "median_uptime_pct": 99.0,
        "median_lag_seconds": 12,
        "bands": {"reliable": 1, "mostly": 0, "spotty": 0},
        "most_reliable": [
            {
                "id": "steady-t",
                "name": "Steady Transit",
                "state": "Iowa",
                "uptime_pct": 99.0,
                "median_lag_seconds": 12,
            }
        ],
        "states": [],
    }
    histories = {
        "steady-t": [
            {"date": "2026-06-10", "score": 88.0, "grade": "B"},
            {"date": "2026-06-11", "score": 90.0, "grade": "A"},
        ]
    }
    html = _render_rt_page(nat, histories)
    assert "Most reliable" in html
    assert "<th>Score trend</th>" in html
    assert 'aria-label="Score trend for Steady Transit: 2026-06-10 88.0; 2026-06-11 90.0"' in html
    assert "spark-mini" in html
    # Without histories the trend cell degrades to an em dash, never breaks.
    assert '<span class="spark-none">&mdash;</span>' in _render_rt_page(nat)


def test_query_page_is_lazy_local_and_honest_about_frame() -> None:
    from scorecard_pipeline.pages_tools import _render_query_page

    html = _render_query_page()
    # The engine loads only on Run; page load stays light.
    assert "downloads the" in html and "first time you press Run" in html
    # Queries never leave the browser, and the file downloads are offered.
    assert "Nothing is sent to a server" in html
    assert "/api/v1/agencies.parquet" in html and "/catalog.csv" in html
    # Working controls: labeled textarea, examples, announced status.
    assert 'for="query-sql"' in html and 'id="query-sql"' in html
    assert 'class="copy-btn query-example"' in html
    assert 'role="status"' in html
    assert "<noscript>" in html
    # The sampling-frame caveat rides on the page (absence means not covered).
    assert "never failing" in html


def test_check_page_is_private_accessible_and_defers_to_validator() -> None:
    from scorecard_pipeline.pages_tools import _render_check_page

    html = _render_check_page()
    # Privacy is the headline promise: the zip is read in the browser only.
    assert "never leaves this page" in html
    assert "nothing is uploaded" in html.lower()
    # The accessible primary is a labeled file input; the drop zone enhances it.
    assert 'for="check-file"' in html and 'type="file"' in html
    assert 'id="check-drop"' in html
    # The five questions are all asked.
    for q in (
        "required files",
        "service data run out",
        "wheelchair accessibility",
        "fare data",
        "stop names readable",
    ):
        assert q in html, q
    # Status is announced, statuses are text (never colour), no-JS path exists.
    assert 'role="status"' in html
    assert "Needs attention" in html and "Looks good" in html
    assert "<noscript>" in html
    # The canonical validator stays the authority, and the full check is linked.
    assert "MobilityData validator" in html
    assert "/try.html" in html
    # The pinned unzip library is actually interpolated, not the placeholder.
    assert "__FFLATE__" not in html and "fflate@0.8.2" in html


def test_page_shell_keeps_nav_reachable_without_js() -> None:
    from scorecard_pipeline.site_shell import _page

    html = _page(
        title="t",
        description="d",
        canonical="https://gtfsscorecard.org/x/",
        body="<p>hi</p>",
    )
    # Without JS the collapsed mobile nav is shown permanently (review
    # finding: navigation was unreachable below 1240px with scripts off).
    assert "<noscript><style>" in html
    assert ".nav-cluster { display: flex !important" in html


def test_map_page_names_its_cdn_fallback() -> None:
    html = _render_map_page(_map_features())
    assert "map-fallback" in html
    assert "the agency list below carries everything" in html


def test_ntd_section_carries_curator_reporting_context() -> None:
    from scorecard_pipeline.render_site import _ntd_section

    art = {
        "agency": {
            "id": "trib",
            "name": "Tribal Transit",
            "ntd_note": "Reports under the shared regional feed operated by the county.",
        },
        "feed": {"reachable": True, "static_url": "https://ex.org/g.zip"},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "freshness": {"status": "measured", "details": {"days_until_expiry": 90}},
        },
    }
    html = _ntd_section(art)
    # The shared-feed/waiver context leads the box, so the reader never takes
    # an identity flag as the agency's fault (R15).
    assert "shared regional feed operated by the county" in html


def test_tools_page_lists_every_self_serve_tool() -> None:
    from scorecard_pipeline.pages_tools import _render_tools_page

    html = _render_tools_page()
    for href in (
        "/app/",
        "/compare/",
        "/check/",
        "/try.html",
        "/query/",
        "/subscribe.html",
        "/submit.html",
        "/procurement/",
    ):
        assert f'href="{href}"' in html, href


def test_nav_is_six_hubs_and_sections_light_their_hub() -> None:
    # Design audit: the nav is six question-shaped hubs, not a flat list of
    # every page. Absorbed pages still light up their hub's stop, and the app
    # stays one click away inside the Agencies hub (plus the footer).
    from scorecard_pipeline.site_shell import _NAV_ITEMS, _nav_active

    hrefs = [href for _, href in _NAV_ITEMS]
    assert len(hrefs) == 6
    assert hrefs == ["/agencies/", "/pulse/", "/focus/", "/tools/", "/how-to-read/", "/about/"]
    assert _nav_active("/app/") == "/agencies/"
    assert _nav_active("/map/") == "/agencies/"
    assert _nav_active("/ntd/") == "/focus/"
    assert _nav_active("/problems/") == "/pulse/"
    assert _nav_active("/check/") == "/tools/"
    assert _nav_active("/agency/unitrans/") == "/agencies/"


def test_footer_is_single_sourced_in_page_shell() -> None:
    from scorecard_pipeline.site_shell import FOOTER_HTML, _page

    html = _page(
        title="t", description="d", canonical="https://gtfsscorecard.org/x/", body="<p>x</p>"
    )
    assert FOOTER_HTML in html
    assert 'href="/pulse/"' in FOOTER_HTML and 'href="/app/"' in FOOTER_HTML


def test_pulse_page_combines_rankings_changes_and_trend() -> None:
    from scorecard_pipeline.render_site import _render_pulse_page

    board = {
        "top": [{"id": "a-t", "name": "Alpha", "grade": "A", "score": 95}],
        "bottom": [{"id": "z-t", "name": "Zulu", "grade": "F", "score": 20}],
        "most_improved": [],
        "most_declined": [],
    }
    changes = [
        {
            "id": "up1",
            "name": "Up Transit",
            "from_grade": "C",
            "to_grade": "B",
            "from_score": 72,
            "to_score": 81,
            "score_delta": 9.0,
            "regressed": False,
            "since": "2026-06-10",
            "date": "2026-06-12",
        }
    ]
    points = [
        {"date": "2026-06-01", "average_score": 70.0, "agency_count": 10, "expired_pct": 5},
        {"date": "2026-07-01", "average_score": 71.0, "agency_count": 10, "expired_pct": 4},
    ]
    summary = {
        "score_delta": 1.0,
        "first": {"date": "2026-06-01"},
        "last": {"date": "2026-07-01", "average_score": 71.0},
    }
    html = _render_pulse_page(board, changes, points, summary, [])
    # One page, three anchored sections, reached by a plain jump nav (no JS).
    for anchor in ('id="rankings"', 'id="changes"', 'id="trend"'):
        assert anchor in html, anchor
    assert 'href="#rankings"' in html and 'href="#trend"' in html
    # The absorbed pages' content is all present.
    assert "Highest scoring" in html and "Alpha" in html
    assert "Up Transit" in html and "up 9" in html
    # Common problems stays its own page, linked from here.
    assert 'href="/problems/"' in html
    # The covered-set framing survives the merge, and the page renders wide.
    assert "not covered yet" in html.replace("\n    ", " ")
    assert 'class="wrap wrap-wide"' in html


def test_retired_urls_render_redirects() -> None:
    from scorecard_pipeline.site_shell import _redirect_page

    html = _redirect_page("/pulse/#changes", "What changed")
    assert 'http-equiv="refresh"' in html
    assert "url=/pulse/#changes" in html
    assert 'rel="canonical"' in html
    # A no-JS, no-meta fallback link is always present.
    assert '<a href="/pulse/#changes">' in html


def test_adoption_page_absorbs_access_coverage() -> None:
    from scorecard_pipeline.render_site import _render_adoption_page

    adoption = {
        "agency_count": 10,
        "flex": {"count": 4, "pct": 40.0},
        "fares": {"count": 6, "pct": 60.0},
        "fares_v2": {"count": 2, "pct": 20.0},
        "pathways": {"count": 1, "pct": 10.0},
        "step_free": {"count": 1, "pct": 10.0},
        "flex_sample": [],
        "states": [],
    }
    coverage = {
        "agency_count": 10,
        "average_boarding_pct": 25.0,
        "bands": {"most": 2, "some": 3, "none": 5},
        "most_complete": [],
        "states": [],
    }
    html = _render_adoption_page(adoption, coverage)
    assert "What feeds publish." in html
    # Both former pages live here as anchored sections.
    assert 'id="features"' in html and 'id="access"' in html
    assert "wheelchair-access information" in html
    # The no-shaming framings survive: optional features, publish-not-usability.
    assert "early, not failing" in html
    assert "physically usable" in html


def test_ridership_impact_line_states_coverage_and_never_ranks() -> None:
    from scorecard_pipeline.render_site import _ridership_impact_line

    impact = {
        "matched_agencies": 120,
        "total_agencies": 1400,
        "total_annual_trips": 250_000_000,
        "expired_trips_pct": 7.5,
    }
    line = _ridership_impact_line(impact)
    assert "250,000,000" in line
    assert "120 of 1400" in line  # coverage is always stated
    assert "7.5%" in line
    # Absent or empty data renders nothing rather than a fabricated number.
    assert _ridership_impact_line(None) == ""
    assert _ridership_impact_line({"matched_agencies": 0}) == ""


def test_press_page_guards_the_no_shaming_line() -> None:
    from scorecard_pipeline.render_site import _render_press_page

    html = _render_press_page()
    assert "Claims the data supports" in html
    assert "Claims it does not support" in html
    assert "worst transit agency" in html  # the unfair claim is named and refused
    assert "not covered, never failing" in html.replace("\n      ", " ")
    assert "CC BY 4.0" in html


def _confidence_artifact(**overrides: Any) -> dict[str, Any]:
    conf: dict[str, Any] = {
        "level": "medium",
        "measured_categories": 3,
        "total_categories": 4,
        "fetch_source": "origin",
        "rt_windows": 0,
        "feed_age_days": 0,
        "notes": [
            "Realtime quality was not measured this run. It does not count against the grade.",
            "The feed was downloaded from the agency's own URL.",
        ],
    }
    conf.update(overrides)
    return {"confidence": conf}


def test_confidence_section_renders_quiet_line_and_breakdown() -> None:
    from scorecard_pipeline.render_site import _confidence_section

    html = _confidence_section(_confidence_artifact())
    assert "Measured 3 of 4 score categories from the agency" in html
    assert "How we measured this" in html
    assert "Confidence in this measurement: medium." in html
    assert "Realtime quality was not measured this run." in html
    # A legibility layer, never a second grade: no letter reel, no score bar.
    assert "var(--grade" not in html and "/ 100" not in html
    assert "It never changes the grade." in html


def test_confidence_section_names_the_mirror_source() -> None:
    from scorecard_pipeline.render_site import _confidence_section

    html = _confidence_section(_confidence_artifact(fetch_source="mirror"))
    assert "from the Mobility Database" in html


def test_confidence_section_names_the_unknown_source() -> None:
    from scorecard_pipeline.render_site import _confidence_section

    html = _confidence_section(_confidence_artifact(fetch_source="unknown"))
    assert "original source was not recorded" in html


def test_confidence_section_empty_for_pre_1_5_artifacts() -> None:
    # Artifacts published before schema 1.5 carry no confidence block; the page
    # must render exactly as it did before the feature.
    from scorecard_pipeline.render_site import _confidence_section

    assert _confidence_section({}) == ""
    assert _confidence_section({"confidence": {}}) == ""


def test_agency_page_carries_the_confidence_line() -> None:
    import datetime as dt
    from pathlib import Path

    from scorecard_pipeline.config import Agency
    from scorecard_pipeline.fetch import FetchResult
    from scorecard_pipeline.metrics import CategoryResult
    from scorecard_pipeline.publish import build_artifact
    from scorecard_pipeline.render_site import _render_agency
    from scorecard_pipeline.score import build_scorecard

    agency = Agency(id="demo", name="Demo Transit", static_gtfs_url="https://ex.org/g.zip")
    fetch = FetchResult(
        agency_id="demo",
        path=Path("/tmp/g.zip"),
        url=agency.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256="abc",
        size_bytes=1,
        reused=False,
        source="origin",
    )
    card = build_scorecard(
        [
            CategoryResult(name="correctness", score=90.0, summary="s"),
            CategoryResult(name="freshness", score=90.0, summary="s"),
        ]
    )
    artifact = build_artifact(agency, fetch, card, dt.datetime(2026, 6, 11, tzinfo=dt.UTC))
    html = _render_agency(artifact)
    assert "Measured 2 of 4 score categories from the agency" in html
    assert "How we measured this" in html
def _guided_flow_artifact() -> dict[str, Any]:
    return {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "feed": {"static_url": "https://data.trilliumtransit.com/gtfs/demo.zip"},
        "top_fixes": [
            {"code": "expired_calendar", "fix": "Re-export with a longer calendar."},
            {"code": "autofix_trim_whitespace", "fix": "Trim whitespace in stop names."},
        ],
        "autofix": {
            "available": True,
            "download_url": "https://cdn.example.com/demo/corrected.zip",
            "fixes": [
                {"code": "autofix_trim_whitespace", "label": "Trimmed whitespace", "count": 3}
            ],
        },
    }


def test_guided_fix_flow_stitches_three_steps_and_links() -> None:
    from scorecard_pipeline import render_site
    from scorecard_pipeline.render_site import _guided_fix_flow

    # The /fix/<code>/ guide link only shows for codes that have a generated page;
    # register one so the step-1 guide link is deterministic in isolation.
    render_site.FIX_CODES_WITH_PAGES.add("expired_calendar")
    try:
        html = _guided_fix_flow(_guided_flow_artifact(), "demo", has_fixlog=True)
    finally:
        render_site.FIX_CODES_WITH_PAGES.discard("expired_calendar")

    # (1) the plain-language finding with its /fix/<code>/ guide.
    assert "Re-export with a longer calendar." in html
    assert 'href="/fix/expired_calendar/"' in html
    # (2) "Make the change": the tool-specific fix path (Trillium, hosted) and, for
    # the finding an autofix covers, the corrected-feed download.
    assert "Make the change." in html
    assert "Trillium" in html
    assert 'href="https://cdn.example.com/demo/corrected.zip"' in html
    assert "Download the corrected feed for this fix" in html
    # (3) "Prove it cleared": the receipt copy and the dated fix log link.
    assert "Prove it cleared." in html
    assert "mints a dated receipt" in html
    assert 'href="/agency/demo/fixes/"' in html
    # The explicit boundary copy.
    assert "the scorecard shows the fix; the agency publishes it." in html


def test_guided_fix_flow_points_to_self_check_without_a_fixlog() -> None:
    from scorecard_pipeline.render_site import _guided_fix_flow

    html = _guided_fix_flow(_guided_flow_artifact(), "demo", has_fixlog=False)
    assert 'href="/check/"' in html
    assert 'href="/agency/demo/fixes/"' not in html


def test_guided_fix_flow_empty_without_fixes() -> None:
    from scorecard_pipeline.render_site import _guided_fix_flow

    art = _guided_flow_artifact()
    art["top_fixes"] = []
    assert _guided_fix_flow(art, "demo", has_fixlog=True) == ""


def test_fix_guide_page_closes_the_loop_with_after_you_republish() -> None:
    from scorecard_pipeline.render_site import _render_fix

    html = _render_fix("expired_calendar", "# Fix expired calendars\n\nRe-export the feed.\n")
    assert "After you republish" in html
    assert "dated receipt" in html
    assert "the scorecard shows the fix; the agency publishes it." in html


def test_fixlog_page_frames_receipts_as_the_end_of_the_loop() -> None:
    from scorecard_pipeline.render_site import _render_fixlog_page

    art = {"agency": {"id": "demo", "name": "Demo Transit"}}
    receipts = [
        {
            "code": "expired_calendar",
            "what": "3 calendars expired.",
            "last_seen": "2026-06-30",
            "cleared": "2026-07-01",
        }
    ]
    html = _render_fixlog_page(art, receipts)
    assert "end of the guided fix loop" in html
    assert "linkable proof for a board packet or NTD" in html
    assert 'href="/agency/demo/"' in html
