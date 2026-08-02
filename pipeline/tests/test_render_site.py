"""Tests for static-site rendering helpers (pure, no file I/O)."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import RUBRIC_VERSION
from scorecard_pipeline.render_site import (
    _accessibility_depth_signals,
    _accessibility_score,
    _accessibility_substat,
    _board_hero,
    _california_guideline_checklist,
    _california_guideline_html,
    _canonical_state,
    _changes_sections,
    _equity_choropleth,
    _fares_substat,
    _ferry_profile_section,
    _grade_distribution_bar,
    _map_feature,
    _numeric_percent,
    _outreach_note,
    _outreach_section,
    _peer_context,
    _remove_stale_agency_index_pages,
    _remove_unlisted_agency_pages,
    _render_agency_index,
    _render_board_page,
    _render_claim_page,
    _render_equity_page,
    _render_map_page,
    _render_spanish_rider_page,
    _rider_impact_section,
    _rollup_percentile_context,
    _route_map_section,
    _rt_accuracy_section,
    _standards_section,
    _states_by_agency,
    _vendor_request,
    _vendor_section,
    compute_changes,
)


def _jsonld_documents(html: str) -> list[dict[str, Any]]:
    return [
        json.loads(payload)
        for payload in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            html,
            flags=re.DOTALL,
        )
    ]


def _assert_tech_article_identity(document: dict[str, Any], canonical: str) -> None:
    organization = {
        "@type": "Organization",
        "name": "GTFS Scorecard",
        "url": "https://gtfsscorecard.org",
    }
    assert document["@context"] == "https://schema.org"
    assert document["@type"] == "TechArticle"
    assert document["url"] == canonical
    assert document["mainEntityOfPage"] == canonical
    assert document["headline"]
    assert document["description"]
    assert document["image"] == {
        "@type": "ImageObject",
        "url": "https://gtfsscorecard.org/og.png",
        "width": 1200,
        "height": 630,
    }
    assert document["author"] == organization
    assert document["publisher"] == organization


def _authored_markdown(
    body: str,
    *,
    date_published: str = "2026-07-03",
    date_modified: str = "2026-07-08",
) -> Any:
    from scorecard_pipeline.render_site import _parse_authored_markdown

    return _parse_authored_markdown(
        f'---\ndate_published: "{date_published}"\ndate_modified: "{date_modified}"\n---\n{body}',
        "test.md",
    )


def test_generated_agency_pages_are_bounded_to_published_index(tmp_path: Path) -> None:
    pages = tmp_path / "agency"
    (pages / "kept").mkdir(parents=True)
    (pages / "delisted").mkdir()
    (pages / "README.txt").write_text("not a generated directory")

    _remove_unlisted_agency_pages(pages, {"kept"})

    assert (pages / "kept").is_dir()
    assert not (pages / "delisted").exists()
    assert (pages / "README.txt").exists()


def test_stale_paginated_directory_cleanup_preserves_non_generated_files(
    tmp_path: Path,
) -> None:
    pages = tmp_path / "agencies" / "page"
    (pages / "2").mkdir(parents=True)
    (pages / "99").mkdir()
    (pages / "notes").mkdir()
    (pages / "README.txt").write_text("keep")

    _remove_stale_agency_index_pages(pages)

    assert not (pages / "2").exists()
    assert not (pages / "99").exists()
    assert (pages / "notes").is_dir()
    assert (pages / "README.txt").is_file()


def test_liveness_status_is_bounded_to_current_published_ids() -> None:
    from scorecard_pipeline.render_site import _scope_liveness_state

    state = {
        "kept": {"checked_at": "2026-07-14T00:00:00+00:00"},
        "removed": {"checked_at": "2026-07-10T00:00:00+00:00"},
    }

    assert _scope_liveness_state(state, {"kept"}) == {"kept": state["kept"]}


def test_spanish_rider_page_is_localized_accessible_and_scoped() -> None:
    html = _render_spanish_rider_page()

    assert '<html lang="es">' in html
    assert html.count("<h1") == 1
    assert "¿Verán los pasajeros mi servicio de transporte?" in html
    assert 'class="skip-link"' in html and "Saltar al contenido principal" in html
    assert '<form id="agency-search-es"' in html
    assert '<datalist id="agency-options-es">' in html
    assert 'id="agency-status-es" class="form-status" role="status"' in html
    assert 'src="/src/es.js"' in html
    alternates = re.findall(
        r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">',
        html,
    )
    assert alternates == [
        ("en", "https://gtfsscorecard.org/"),
        ("es", "https://gtfsscorecard.org/es/"),
    ]
    assert "No certifica la calidad del servicio" in html


def test_rt_schedule_deviation_is_not_labeled_prediction_accuracy() -> None:
    html = _rt_accuracy_section(
        {
            "categories": {
                "realtime": {
                    "status": "measured",
                    "details": {
                        "drift": {
                            "median_seconds": 17,
                            "p90_abs_seconds": 166,
                            "on_time_share_pct": 93.6,
                        },
                        "vehicles_on_route_pct": 100.0,
                    },
                }
            }
        }
    )

    assert "Live predictions vs schedule" in html
    assert "Prediction accuracy" not in html


def test_claim_page_requires_reviewed_evidence_and_protects_private_data() -> None:
    html = _render_claim_page()
    assert "A request is not treated as proof by itself" in html
    assert "Official webpage" in html
    assert "Feed-host proof" in html
    assert "Official-domain email" in html
    assert "Do not put private email addresses, access" in html
    assert "template=claim-agency.yml" in html
    assert '<link rel="canonical" href="https://gtfsscorecard.org/claim/">' in html


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
    # MapLibre is wired up for the enhancement, but only after an explicit request.
    assert "maplibregl" in html and "geometry.geojson" in html
    assert 'id="route-map-load"' in html
    assert '<script src="https://unpkg.com/maplibre-gl' not in html
    assert 'script.src = "https://unpkg.com/maplibre-gl' in html
    assert 'css.href = "https://unpkg.com/maplibre-gl' in html


def test_route_map_section_limits_data_nosnippet_to_utility_details() -> None:
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

    assert html.count("data-nosnippet") == 1
    boundary_start = html.index("<div data-nosnippet>")
    boundary_end = html.index("</div></section>")
    eligible_copy = html[:boundary_start]
    utility_details = html[boundary_start:boundary_end]

    assert 'id="map-h"' in eligible_copy
    assert "Each route is drawn once" in eligible_copy
    assert "This feed has <strong>2</strong> stops." in eligible_copy

    assert 'id="route-map-load"' in utility_details
    assert "Basemap: OpenFreeMap" in utility_details
    assert 'class="map-legend"' in utility_details
    assert 'class="route-table"' in utility_details
    assert 'class="stop-list-wrap"' in utility_details
    assert "First Stop" in utility_details and "Second Stop" in utility_details

    # The optional MapLibre bootstrap remains lazy and outside the static
    # no-snippet boundary.
    assert html.index("<script>") > boundary_end


def test_route_map_section_keyboard_model_rides_on_the_table() -> None:
    artifact = _artifact_with_route_map(
        routes=[
            {
                "id": "A",
                "label": "A",
                "type_label": "Bus",
                "color": "0E6734",
                "color_name": "green",
                "has_shape": True,
            }
        ],
        route_count=1,
        drawn_route_count=1,
        stop_count=1,
        has_shapes=True,
        path="data/artifacts/demo/geometry.geojson",
    )
    html = _route_map_section(artifact, "demo", stop_names=["Only Stop"])
    # The script (not the markup) makes each drawable route's row focusable, so
    # a page without the script gains no inert tab stops.
    assert 'data-route-key="A"' in html
    assert 'tabindex="0"' not in html.split("<script>")[0]
    assert 'tr.setAttribute("tabindex", "0")' in html
    # Focus brushes the row's line; blur falls back to the pinned selection.
    assert 'tr.addEventListener("focus"' in html
    assert 'tr.addEventListener("blur"' in html
    # Enter or Space pins, and Space never scrolls the page.
    assert 'tr.addEventListener("keydown"' in html
    assert 'e.key !== "Enter" && e.key !== " "' in html
    assert "e.preventDefault()" in html
    # The canvas stays aria-hidden and out of the tab order.
    assert 'aria-hidden="true"' in html
    assert 'setAttribute("tabindex", "-1")' in html


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


def test_route_map_section_caps_aggregate_route_tables() -> None:
    routes = [
        {
            "id": f"R{i}",
            "label": f"Route {i}",
            "type_label": "Bus",
            "color": "1A7A46",
            "color_name": "green",
            "has_shape": False,
        }
        for i in range(502)
    ]
    artifact = _artifact_with_route_map(
        routes=routes,
        route_count=len(routes),
        drawn_route_count=0,
        stop_count=1,
        has_shapes=False,
        path="data/artifacts/demo/geometry.geojson",
    )

    html = _route_map_section(artifact, "demo", stop_names=["Only Stop"])

    assert html.count('<th scope="row">') == 500
    assert "First 500 of 502 routes" in html
    assert "Showing 500 of 502 routes" in html
    assert 'href="/data/artifacts/demo/latest.json"' in html
    assert "Route 499" in html
    assert "Route 500" not in html


def test_route_map_section_empty_when_no_geometry() -> None:
    assert _route_map_section({"agency": {"id": "x", "name": "X"}}, "x") == ""
    assert _route_map_section(_artifact_with_route_map(routes=[], stop_count=0), "x") == ""


def test_ferry_route_map_uses_terminal_language() -> None:
    artifact = _artifact_with_route_map(
        routes=[
            {
                "id": "F1",
                "label": "F1",
                "type_label": "Ferry",
                "color": "0E6734",
                "color_name": "green",
                "has_shape": True,
            }
        ],
        stop_count=2,
        has_shapes=True,
        path="data/artifacts/demo/geometry.geojson",
    )
    artifact["mode_profile"] = {"ferry_only": True}

    html = _route_map_section(artifact, "demo", stop_names=["Pier One", "Island Terminal"])

    assert "Routes and terminals" in html
    assert "terminals are the dots" in html
    assert "List every terminal" in html
    assert "Skip to route and terminal data" in html
    assert "Routes and stops" not in html


def test_status_board_identifies_ungraded_ferry_mode() -> None:
    artifact: dict[str, Any] = {
        "overall": {"grade": "B", "score": 84.0},
        "snapshot_date": "2026-07-16",
        "categories": {
            "freshness": {"details": {}},
            "completeness": {"details": {}},
            "realtime": {"status": "not_measured", "summary": "Not measured."},
        },
        "mode_profile": {
            "measured": True,
            "graded": False,
            "modes": [{"key": "ferry", "label": "Ferry"}],
        },
    }

    html = _board_hero("Demo Ferry", "demo-ferry", artifact, [])

    assert '<p class="board-mode"><span>Service mode</span> Ferry</p>' in html
    assert "Overall grade B" in html


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
    assert 'class="movement-chart"' in html
    assert "1</strong> improved" in html and "1</strong> slipped" in html
    assert "significant movers, not every quiet feed" in html


def test_changes_page_has_friendly_empty_states() -> None:
    html = _changes_sections([])
    assert "No material score or grade changes were detected" in html
    assert "No comparable upward moves" in html
    assert "No comparable downward moves" in html


def test_rollup_suppresses_stale_aggregates_without_a_guarded_cohort() -> None:
    from scorecard_pipeline.render_site import _render_rollup

    html = _render_rollup(
        {
            "rollup": {"id": "all", "name": "All tracked agencies"},
            "agency_count": 10,
            "average_score": 60.9,
            "grade_distribution": {"A": 4, "B": 6},
            "comparison": {"eligible_count": 0},
            "needs_attention": 2,
            "expired": {"lapsed": 0, "stale": 0, "total": 0},
            "shapes_readiness": {
                "ready": 0,
                "at_risk": 0,
                "not_ready": 0,
                "not_measured": 10,
                "total": 10,
            },
            "members": [],
            "common_fixes": [{"code": "old", "fix": "Stale shared fix.", "agencies": 8}],
        }
    )

    assert "average unavailable" in html
    assert "60.9" not in html
    assert "Grade distribution" not in html
    assert "Stale shared fix" not in html
    assert "complete guarded summary" in html
    # Only country rollups carry the reviewed-feed-record scope note.
    assert "reviewed feed record" not in html


def test_country_rollup_page_states_reviewed_feed_record_scope() -> None:
    from scorecard_pipeline.render_site import _render_rollup

    html = _render_rollup(
        {
            "rollup": {
                "id": "country-ca",
                "name": "Canada",
                "country_code": "CA",
                "country_name": "Canada",
            },
            "agency_count": 2,
            "average_score": None,
            "grade_distribution": {},
            "comparison": {"eligible_count": 0},
            "needs_attention": 0,
            "expired": {"lapsed": 0, "stale": 0, "total": 0},
            "shapes_readiness": {
                "ready": 0,
                "at_risk": 0,
                "not_ready": 0,
                "not_measured": 2,
                "total": 2,
            },
            "members": [
                {
                    "id": "barrie-transit",
                    "name": "Barrie Transit",
                    "score": 82.0,
                    "grade": "B",
                    "snapshot_date": "2026-07-16",
                    "needs_attention": False,
                    "attention_reason": None,
                    "days_until_expiry": 120,
                    "expiry_status": "current",
                    "top_fix": None,
                    "shapes_status": None,
                    "annual_trips": None,
                },
                {
                    "id": "brampton-transit",
                    "name": "Brampton Transit",
                    "score": 88.0,
                    "grade": "B",
                    "snapshot_date": "2026-07-16",
                    "needs_attention": False,
                    "attention_reason": None,
                    "days_until_expiry": 90,
                    "expiry_status": "current",
                    "top_fix": None,
                    "shapes_status": None,
                    "annual_trips": None,
                },
            ],
            "common_fixes": [],
        }
    )

    # Scope-honest denominator: reviewed feed records, never country coverage.
    assert "Scope: 2 reviewed feed records tracked in Canada." in html
    assert "not a claim that GTFS Scorecard covers Canada" in html
    assert "measures those records, not operators, routes, or all public transport" in html
    # The page itself is the ordinary rollup surface: member links, no ranking.
    assert '<a href="/agency/barrie-transit/">' in html
    assert "attention first, then alphabetical" in html
    assert "https://gtfsscorecard.org/program/country-ca/" in html


def test_static_directory_card_isolates_international_agency_name() -> None:
    from scorecard_pipeline.render_site import _index_card

    html = _index_card(
        "example-global",
        {
            "name": "هيئة النقل",
            "history": [{"grade": "A", "score": 91.0, "date": "2026-07-12"}],
        },
    )

    assert '<a href="/agency/example-global/"><bdi>هيئة النقل</bdi></a>' in html


def test_grade_distribution_bar_renders_only_nonzero_grades() -> None:
    html = _grade_distribution_bar({"A": 2, "B": 0, "C": "3", "F": None}, 5)
    assert "grade-seg grade-a" in html
    assert "2 graded A" in html
    # A non-int count (a hand-edited or malformed rollup file) is treated as
    # zero rather than crashing or rendering a bogus segment.
    assert "grade-seg grade-c" not in html
    assert "grade-seg grade-b" not in html
    assert "grade-seg grade-f" not in html


def test_grade_distribution_bar_empty_when_no_total() -> None:
    assert _grade_distribution_bar({"A": 3}, 0) == ""


def test_rollup_percentile_context_ignores_retired_field() -> None:
    assert _rollup_percentile_context({"state_percentile": 48}) == ""


def test_rollup_percentile_context_empty_when_absent_or_none() -> None:
    assert _rollup_percentile_context({"state_percentile": None}) == ""
    assert _rollup_percentile_context({}) == ""


def test_standards_section_gives_canada_only_universal_guidance() -> None:
    art = {
        "agency": {"country": "CA"},
        "categories": {"correctness": {"status": "measured", "score": 90}},
    }
    html = _standards_section(art, "Ontario", "CA-ON")
    assert "GTFS Schedule Best Practices" in html
    assert "MobilityData grading scheme" in html
    assert "National Transit Database" not in html
    assert "California Transit Data Guidelines" not in html


def test_standards_section_is_state_aware() -> None:
    art = {"categories": {"correctness": {"status": "measured", "score": 90}}}
    # US agencies receive the universal references plus the US NTD overlay.
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
    assert "support resource" in mn
    assert "published guideline" not in mn
    assert "not a scoring authority" in mn
    # A state with no entry shows neither, only the universal standards.
    tx = _standards_section(art, "Texas")
    assert "California Transit Data Guidelines" not in tx
    assert "transit-data program" not in tx
    # The California guideline checklist (E11) is California-only.
    assert "Minimum GTFS Guidelines checklist" in ca
    assert "Minimum GTFS Guidelines checklist" not in mn
    assert "Minimum GTFS Guidelines checklist" not in tx


def test_subdivision_code_selects_guidance_without_state_name() -> None:
    art = {"agency": {"country": "US"}, "categories": {}}
    ca = _standards_section(art, subdivision_code="US-CA")
    assert "California Transit Data Guidelines" in ca
    mn = _standards_section(art, subdivision_code="US-MN")
    assert "MnDOT Transit" in mn


def test_numeric_percent_excludes_bool() -> None:
    assert _numeric_percent(95) == 95.0
    assert _numeric_percent(95.5) == 95.5
    assert _numeric_percent(None) is None
    assert _numeric_percent("95") is None
    # isinstance(True, int) is True in Python; a stray boolean under a details
    # key this reads must not be treated as a percentage.
    assert _numeric_percent(True) is None
    assert _numeric_percent(False) is None
    assert _numeric_percent(float("inf")) is None
    assert _numeric_percent(float("nan")) is None


def test_rider_impact_disclosure_uses_measured_fields_without_rating_service() -> None:
    artifact = {
        "categories": {
            "freshness": {"status": "measured", "details": {"days_until_expiry": 67}},
            "completeness": {
                "status": "measured",
                "details": {
                    "accessibility": {"stops_stated_pct": 99.5, "trips_stated_pct": 42},
                    "has_fares": True,
                    "fare_free": False,
                    "fares": {"model": "v2"},
                },
            },
            "realtime": {
                "status": "measured",
                "details": {"coverage_pct": 77.8, "kinds_reachable": 3},
            },
        }
    }

    html = _rider_impact_section(artifact)
    assert html.startswith('<details class="rider-impact" id="rider-impact">')
    assert " open" not in html  # preserve grade -> fixes as the primary workflow
    assert "last published service date is in 67 days" in html
    assert "99.5% of stops" in html and "42% of trips" in html
    assert "published data, not whether stops or vehicles are physically usable" in html
    assert "GTFS Fares v2" in html
    assert "covered 77.8% of scheduled trips" in html
    assert "does not rate service reliability" in html
    assert "confirm current service alerts, fares, and accessibility accommodations" in html


def test_ferry_rider_impact_uses_terminal_and_vessel_language() -> None:
    artifact = {
        "mode_profile": {
            "measured": True,
            "ferry_only": True,
            "is_multimodal": False,
            "primary_mode": "ferry",
        },
        "categories": {
            "completeness": {
                "status": "measured",
                "details": {"accessibility": {"stops_stated_pct": 80, "trips_stated_pct": 90}},
            }
        },
    }

    html = _rider_impact_section(artifact)

    assert "80% of terminals" in html
    assert "whether terminals or vessels are physically usable" in html
    assert "% of stops" not in html


def test_ferry_profile_is_ungraded_scoped_and_preserves_unknowns() -> None:
    artifact = {
        "ferry_profile": {
            "measured": True,
            "graded": False,
            "route_count": 3,
            "trip_count": 120,
            "terminal_hierarchy": {
                "boarding_location_count": 6,
                "parented_boarding_location_count": 4,
                "referenced_station_count": 2,
            },
            "stop_access": {
                "eligible_terminal_count": 4,
                "stated_count": 2,
                "stated_pct": 50.0,
                "direct_count": 1,
                "through_station_count": 1,
            },
            "accessibility": {
                "terminals": {
                    "total_count": 6,
                    "stated_count": 3,
                    "stated_pct": 50.0,
                    "allowed_count": 2,
                    "allowed_pct": 33.3,
                },
                "trips": {
                    "total_count": 120,
                    "stated_count": 0,
                    "stated_pct": 0.0,
                    "allowed_count": 0,
                    "allowed_pct": 0.0,
                },
            },
            "bikes": {
                "total_count": 120,
                "stated_count": 90,
                "stated_pct": 75.0,
                "allowed_count": 60,
                "allowed_pct": 50.0,
            },
            "cars": {
                "total_count": 120,
                "stated_count": 0,
                "stated_pct": 0.0,
                "allowed_count": 0,
                "allowed_pct": 0.0,
            },
            "fares": {"scope": "whole_feed", "fare_free": False, "model": "none"},
            "realtime": {
                "scope": "whole_feed",
                "configured_kinds": ["trip_updates", "service_alerts"],
            },
        }
    }

    html = _ferry_profile_section(artifact)

    assert 'id="ferry-profile-h"' in html
    assert "Ungraded capability read" in html
    assert "3 routes · 120 trips" in html
    assert "50% of eligible child terminal locations" in html
    assert "Unknown: none of the 120 ferry trips publish wheelchair_accessible" in html
    assert "75% of ferry trips publish a value" in html
    assert "Unknown: none of the 120 ferry trips publish cars_allowed" in html
    assert "not evidence that ferry service is free" in html
    assert "Trip Updates, Service Alerts" in html
    assert "does not change the grade" in html


def test_ferry_profile_is_absent_when_not_measured() -> None:
    assert _ferry_profile_section({}) == ""


def test_rider_impact_disclosure_keeps_unknowns_neutral_and_escapes_model() -> None:
    unknown = _rider_impact_section({"categories": {}})
    assert "Schedule visibility is not known" in unknown
    assert "Published accessibility-data coverage is not known" in unknown
    assert "Fare-information availability is not known" in unknown
    assert "Realtime-feed availability and live-arrival coverage are not known" in unknown

    malicious = _rider_impact_section(
        {
            "categories": {
                "completeness": {
                    "status": "measured",
                    "details": {
                        "has_fares": True,
                        "fare_free": False,
                        "fares": {"model": '"><script>alert(1)</script>'},
                    },
                }
            }
        }
    )
    assert "<script>" not in malicious
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in malicious


def test_rider_impact_does_not_overstate_schedule_or_realtime_evidence() -> None:
    reachable = _rider_impact_section(
        {
            "categories": {
                "freshness": {"status": "measured", "details": {"days_until_expiry": 30}},
                "realtime": {
                    "status": "measured",
                    "details": {"coverage_pct": None, "kinds_reachable": 1},
                },
            }
        }
    )
    assert "last published service date is in 30 days" in reachable
    assert "covers the next" not in reachable
    assert "One or more realtime feeds were reachable" in reachable
    assert "Live-arrival feeds were reachable" not in reachable

    unreachable = _rider_impact_section(
        {
            "categories": {
                "realtime": {
                    "status": "measured",
                    "details": {"coverage_pct": None, "kinds_reachable": 0},
                }
            }
        }
    )
    assert "No realtime feed was reachable" in unreachable
    assert "No live-arrival feed" not in unreachable


def test_distant_service_horizon_uses_review_copy_instead_of_huge_day_claim() -> None:
    from scorecard_pipeline.render_site import _render_agency, _render_brief

    freshness = {
        "status": "measured",
        "score": 100.0,
        "summary": "Service data covers the next 26834 days.",
        "findings": [],
        "details": {
            "days_until_expiry": 26_834,
            "last_service_date": "2099-12-31",
        },
    }
    artifact = {
        "agency": {"id": "demo", "name": "Demo Transit", "country": "US"},
        "overall": {"grade": "A", "score": 95.0},
        "snapshot_date": "2026-07-13",
        "feed": {"static_url": "https://example.org/gtfs.zip", "reachable": True},
        "categories": {
            "correctness": {
                "status": "measured",
                "score": 100.0,
                "summary": "No validator errors.",
                "findings": [],
            },
            "freshness": freshness,
            "completeness": {
                "status": "measured",
                "score": 100.0,
                "summary": "Rider fields are complete.",
                "findings": [],
                "details": {"accessibility": {"stops_stated_pct": 100, "trips_stated_pct": 100}},
            },
        },
        "top_fixes": [],
        "ntd_readiness": {
            "status": "ready",
            "summary": "Ready.",
            "pillars": [
                {
                    "key": "current",
                    "status": "ready",
                    "detail": "Service data covers the next 26834 days.",
                }
            ],
        },
        "conformance": {
            "awarded": True,
            "summary": "Awarded.",
            "criteria": [
                {
                    "key": "current",
                    "met": True,
                    "detail": "Service data covers the next 26834 days.",
                }
            ],
        },
    }

    rider = _rider_impact_section(artifact)
    assert "published to an unusually distant date" in rider
    assert "may be intentional or a placeholder" in rider
    assert "26,834" not in rider and "26834" not in rider

    hero = _board_hero("Demo Transit", "demo", artifact, [])
    assert "Review service end date" in hero
    assert "Covers 26834 days" not in hero

    # First deploy renders old artifacts without rewriting them. Every static
    # presentation path must replace embedded and regenerated raw countdowns.
    for html in (_render_agency(artifact), _render_brief(artifact)):
        assert "Review service end date" in html or "unusually distant" in html
        assert "26834" not in html
        assert "26,834" not in html


def test_agency_page_allowlists_hostile_artifact_severity() -> None:
    from scorecard_pipeline.render_site import _render_agency

    path = Path(__file__).resolve().parents[2] / "data" / "artifacts" / "abq-ride" / "latest.json"
    artifact = json.loads(path.read_text())
    hostile = 'ERROR" onmouseover="window.__pwned=1'
    finding = artifact["categories"]["correctness"]["findings"][0]
    finding["severity"] = hostile
    finding["code"] = "hostile-severity-test"

    html = _render_agency(artifact)

    assert '<span class="sev sev-info">Info</span>' in html
    assert hostile not in html
    assert 'onmouseover="window.__pwned=1' not in html


def test_catalog_derives_status_from_legacy_latest_artifact(
    isolated_repo_root: Path,
) -> None:
    from scorecard_pipeline.render_site import render_site

    fixture = Path(__file__).parent / "fixtures" / "golden_site"
    shutil.copytree(fixture, isolated_repo_root)
    latest = isolated_repo_root / "data" / "artifacts" / "unitrans" / "latest.json"
    artifact = json.loads(latest.read_text())
    artifact["snapshot_date"] = "2026-07-13"
    freshness = artifact["categories"]["freshness"]
    freshness["summary"] = "Service data covers the next 26834 days."
    freshness["details"]["days_until_expiry"] = 26_834
    freshness["details"]["last_service_date"] = "2099-12-31"
    freshness["details"].pop("service_horizon_status", None)
    freshness["details"].pop("effective_expiry_date", None)
    latest.write_text(json.dumps(artifact))

    render_site(dt.datetime(2026, 7, 13, 12, tzinfo=dt.UTC))

    catalog = json.loads((isolated_repo_root / "web" / "catalog.json").read_text())
    row = next(row for row in catalog["agencies"] if row["id"] == "unitrans")
    assert row["days_until_expiry"] == 26_834
    assert row["service_horizon_status"] == "unusually_distant"
    agency_html = (isolated_repo_root / "web" / "agency" / "unitrans" / "index.html").read_text()
    assert "Review service end date" in agency_html
    assert "26834" not in agency_html
    assert "26,834" not in agency_html

    global_coverage = json.loads(
        (isolated_repo_root / "web" / "api" / "v1" / "global-coverage.json").read_text()
    )
    assert global_coverage["scope"]["name"] == "Bounded European GTFS Schedule beta"
    assert global_coverage["status"] == "not_ready"


def test_catalog_top_level_rubric_reports_mixed_row_versions() -> None:
    from scorecard_pipeline.render_site import _write_catalog

    written: dict[str, str] = {}

    def write(path: str, text: str, *_args: object) -> None:
        written[path] = text

    _write_catalog(
        write,
        [
            {
                "id": "old",
                "rubric_version": "1.1",
                "reader_archive_profile": "raw-v1",
                "comparison_eligible": False,
            },
            {
                "id": "new",
                "rubric_version": "1.2",
                "reader_archive_profile": "flat-single-root-v1",
                "comparison_eligible": True,
            },
        ],
    )

    catalog = json.loads(written["catalog.json"])
    assert catalog["rubric_version"] == "mixed"
    assert catalog["rubric_versions"] == ["1.1", "1.2"]
    csv_lines = written["catalog.csv"].splitlines()
    assert "comparison_eligible" in csv_lines[0]
    assert "reader_archive_profile" in csv_lines[0]
    assert "raw-v1" in csv_lines[1]
    assert "flat-single-root-v1" in csv_lines[2]


def test_california_checklist_reads_measured_fields() -> None:
    art = {
        "feed": {"reachable": True},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "completeness": {
                "status": "measured",
                "findings": [],
                "details": {
                    "accessibility": {"stops_stated_pct": 95, "trips_stated_pct": 92},
                    "has_fares": True,
                    "fare_free": False,
                },
            },
        },
    }
    items = _california_guideline_checklist(art)
    by_label = {i["label"]: i for i in items}
    assert by_label["Publish GTFS Schedule at a stable, automatically-fetchable URL"]["met"] is True
    assert by_label["Produce no critical errors in the MobilityData GTFS Validator"]["met"] is True
    wheelchair = by_label["wheelchair_boarding stated on stops and trips"]
    assert wheelchair["met"] is True
    assert "95%" in wheelchair["detail"] and "92%" in wheelchair["detail"]
    fares = by_label["Fare data published, or the service marked fare-free"]
    assert fares["met"] is True
    # Items outside this scorecard's measurement stay explicitly unmeasured, not
    # silently omitted or guessed at.
    unmeasured = [i for i in items if i["met"] is None]
    assert any("Urban Transportation Research" in i["label"] for i in unmeasured)
    assert any("20 seconds" in i["label"] for i in unmeasured)


def test_california_checklist_gaps_and_unmeasured_are_distinct() -> None:
    art = {
        "feed": {"reachable": False},
        "categories": {
            "correctness": {
                "status": "measured",
                "findings": [{"severity": "ERROR"}, {"severity": "ERROR"}],
            },
            "completeness": {
                "status": "measured",
                "findings": [{"code": "scorecard_no_feed_contact"}],
                "details": {"has_fares": False, "fare_free": False},
            },
        },
    }
    items = _california_guideline_checklist(art)
    by_label = {i["label"]: i for i in items}
    url_item = by_label["Publish GTFS Schedule at a stable, automatically-fetchable URL"]
    assert url_item["met"] is False
    errors_item = by_label["Produce no critical errors in the MobilityData GTFS Validator"]
    assert errors_item["met"] is False
    assert "2 validator errors" in errors_item["detail"]
    contact_item = by_label["Designate a technical contact in feed_info.txt's feed_contact_email"]
    assert contact_item["met"] is False
    fares_item = by_label["Fare data published, or the service marked fare-free"]
    assert fares_item["met"] is False
    # Not-yet-measured fields (no completeness or correctness category at all)
    # render as None across every item they gate, not as a false gap -- a
    # regression that dropped one of the `is not None`/`if comp_measured`
    # guards would otherwise report a "Gap" for an agency that simply hasn't
    # been scored yet.
    unmeasured_art: dict[str, Any] = {"feed": {}, "categories": {}}
    unmeasured_by_label = {i["label"]: i for i in _california_guideline_checklist(unmeasured_art)}
    assert unmeasured_by_label["wheelchair_boarding stated on stops and trips"]["met"] is None
    assert (
        unmeasured_by_label["Designate a technical contact in feed_info.txt's feed_contact_email"][
            "met"
        ]
        is None
    )
    assert (
        unmeasured_by_label["Fare data published, or the service marked fare-free"]["met"] is None
    )
    assert (
        unmeasured_by_label["Produce no critical errors in the MobilityData GTFS Validator"]["met"]
        is None
    )


def test_california_checklist_html_counts_only_measured_items() -> None:
    art = {
        "feed": {"reachable": True},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "completeness": {"status": "measured", "findings": [], "details": {}},
        },
    }
    items = _california_guideline_checklist(art)
    measured = [i for i in items if i["met"] is not None]
    met = [i for i in items if i["met"]]
    html = _california_guideline_html(art)
    # The summary counts only against items this tool actually measures, never
    # against the checklist's full 13 (most of which stay unmeasured here).
    assert f"({len(met)} of {len(measured)} measured items met)" in html
    assert len(measured) < len(items)
    assert "Meets" in html
    assert "Not measured here" in html


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


def test_ferry_accessibility_substat_and_conformance_use_terminal_language() -> None:
    from scorecard_pipeline.render_site import _conformance_section

    artifact: dict[str, Any] = {
        "mode_profile": {
            "measured": True,
            "ferry_only": True,
            "is_multimodal": False,
            "primary_mode": "ferry",
        },
        "feed": {"reachable": True},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "freshness": {"status": "measured", "details": {"days_until_expiry": 52}},
            "completeness": {
                "status": "measured",
                "details": {
                    "accessibility": {
                        "score": 40.0,
                        "stops_stated_pct": 40.0,
                        "stops_marked_accessible_pct": 35.0,
                        "trips_stated_pct": 50.0,
                    }
                },
            },
        },
    }

    substat = _accessibility_substat(artifact["categories"]["completeness"], artifact)
    conformance = _conformance_section(artifact, "demo-ferry", "Demo Ferry")

    assert "40% of terminals state accessibility" in substat
    assert "40% of terminals and 50% of trips" in conformance
    assert "nearly every terminal and trip" in conformance
    assert "whether a terminal is physically usable" in conformance


def test_accessibility_depth_signals_lists_the_second_lens_checks() -> None:
    """EXP-05: pathway connectivity and field-plausibility findings (from the
    second, BlinkTag-modeled accessibility lens) render as an adoption-framed
    signal list, tagged zero-deduction, distinct from the field-presence
    sub-score above them."""
    art = {
        "recommendations": [
            {
                "code": "scorecard_station_missing_step_free_data",
                "category": "accessibility",
                "what": "This feed models stations or entrances but has no pathways.txt.",
                "fix": "Add pathways.txt connecting entrances, platforms, and elevators.",
            },
            {
                "code": "scorecard_fares_v2_rider_categories",
                "category": "fares",
                "what": "No rider categories.",
                "fix": "Add rider_categories.txt.",
            },
        ]
    }
    html = _accessibility_depth_signals(art)
    assert "1 accessibility depth signal" in html
    assert "pathways.txt" in html and "Consider:" in html
    # A fares recommendation elsewhere in the block is not pulled in here.
    assert "rider_categories" not in html
    assert "not deductions" in html


def test_accessibility_depth_signals_empty_when_no_accessibility_recs() -> None:
    assert _accessibility_depth_signals({"recommendations": []}) == ""
    assert _accessibility_depth_signals({}) == ""
    assert (
        _accessibility_depth_signals(
            {"recommendations": [{"code": "x", "category": "fares", "what": "y", "fix": "z"}]}
        )
        == ""
    )


def test_accessibility_substat_includes_depth_signals_when_artifact_given() -> None:
    cat = {
        "status": "measured",
        "details": {"accessibility": {"score": 80.0}},
    }
    art = {
        "recommendations": [
            {
                "code": "scorecard_route_color_low_contrast",
                "category": "accessibility",
                "what": "1 route badge pairs colors below the WCAG 4.5:1 contrast bar.",
                "fix": "Adjust route_color or route_text_color.",
            }
        ]
    }
    html = _accessibility_substat(cat, art)
    assert "accessibility depth signal" in html
    assert "contrast" in html
    # Without an artifact, the sub-score still renders, just without the
    # second-lens block -- callers that predate EXP-05 keep working.
    assert "a11y-depth" not in _accessibility_substat(cat)


def test_recommendations_section_excludes_accessibility_depth_items() -> None:
    """EXP-05: accessibility-depth recs get their own celebrated presentation in
    the sub-score block, not the generic 'beyond the grade' list."""
    from scorecard_pipeline.render_site import _recommendations_section

    art = {
        "recommendations": [
            {
                "code": "scorecard_stop_name_needs_tts",
                "category": "accessibility",
                "what": "3 stop names use abbreviations a screen reader may mispronounce.",
                "fix": "Add tts_stop_name.",
            },
            {
                "code": "scorecard_fares_v2_rider_categories",
                "category": "fares",
                "what": "No rider categories.",
                "fix": "Add rider_categories.txt so apps can show senior and youth fares.",
            },
        ]
    }
    html = _recommendations_section(art)
    assert "rider_categories" in html
    assert "tts_stop_name" not in html


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


def test_guide_glossary_deep_link_has_a_matching_fragment() -> None:
    from scorecard_pipeline.render_site import _render_guide
    from scorecard_pipeline.site_shell import FOOTER_HTML

    html = _render_guide()
    assert 'href="#glossary"' in html
    assert '<section id="glossary" aria-labelledby="glossary-h">' in html
    assert 'id="glossary-h"' in html
    assert 'href="/how-to-read/#glossary"' in FOOTER_HTML


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


def test_vendor_request_lists_fixes_with_finding_codes() -> None:
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
    assert "Finding code: scorecard_feed_expired" in note
    assert "Validator notice:" not in note
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
    for entry in entries:
        for point in entry.get("history", []):
            point.setdefault("rubric_version", "1.2")
            point.setdefault("scoring_profile_id", "gtfs-scorecard-1.2")
            point.setdefault("scoring_profile_rubric_version", "1.2")
            point.setdefault("validator_version", "8.0.1")
            point.setdefault(
                "categories",
                {"correctness": 80.0, "freshness": 80.0, "completeness": 80.0},
            )
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


def test_states_by_agency_joins_prefixed_v2_id_to_numeric_legacy_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import config, mobilitydb
    from scorecard_pipeline.config import Agency

    monkeypatch.setattr(
        config,
        "AGENCIES",
        {
            "v2-feed": Agency(
                "v2-feed",
                "V2 Feed",
                "https://example.org/feed.zip",
                mdb_id="mdb-00123",
            )
        },
    )
    catalog = mobilitydb.parse_catalog(
        "mdb_source_id,data_type,location.subdivision_name,provider,"
        "urls.direct_download\n"
        "123,gtfs,California,V2 Feed,https://example.org/feed.zip\n"
    )
    monkeypatch.setattr(mobilitydb, "load_catalog", lambda: catalog)

    assert _states_by_agency() == {"v2-feed": "California"}


def test_peer_context_renders_only_catalog_location() -> None:
    html = _peer_context(
        {
            "national_percentile": 53,
            "peer_percentile": 68,
            "size_tier": "large",
            "state": "New Mexico",
        }
    )
    assert "Catalogued in <bdi>New Mexico</bdi>." in html
    assert "53%" not in html and "68%" not in html
    assert "percentile" not in html


def test_peer_context_ignores_retired_percentile_fields() -> None:
    html = _peer_context(
        {"national_percentile": 40, "peer_percentile": None, "size_tier": "unknown", "state": ""}
    )
    assert html == ""


def test_peer_context_empty_without_record_or_location() -> None:
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
        "scoring_profile": {"id": "gtfs-scorecard-1.4", "rubric_version": "1.4"},
        "feed": {"static_url": "https://data.trilliumtransit.com/gtfs/demo.zip"},
        "top_fixes": [
            {
                "code": "scorecard_wheelchair_boarding_unknown",
                "fix": "Set wheelchair_boarding on every stop.",
                "what": "12 stops blank.",
                "why": "Riders using wheelchairs cannot plan trips.",
                "effort": "Usually one export setting.",
            }
        ],
        "categories": {"freshness": {"status": "measured", "score": 84.0, "findings": []}},
    }


def test_board_page_leads_with_progress_and_frames_fixes_as_asks() -> None:
    prev = {
        "rubric_version": "1.4",
        "validator_version": "7.0.0",
        "scoring_profile": {"id": "gtfs-scorecard-1.4", "rubric_version": "1.4"},
        "categories": {
            "freshness": {
                "status": "measured",
                "findings": [{"code": "expired_calendar", "what": "3 calendars expired."}],
            }
        },
    }
    html = _render_board_page(_board_artifact(), history=None, prev_artifact=prev)
    assert "Board packet" in html
    assert "Grade B" in html
    # The later feed state leads, without attributing cause, before the asks.
    assert "was no longer reported" in html and "3 calendars expired." in html
    assert "not who made a change or why" in html
    assert "What needs attention next" in html
    assert "Set wheelchair_boarding on every stop." in html
    # The producing tool is named so the board sees who does the work (R5).
    assert "Trillium" in html
    # It says what the grade does and does not measure.
    assert "not service" in html
    assert '<meta name="robots" content="noindex,follow">' in html


@pytest.mark.parametrize("agency_id", ["unitrans", "yolobus"])
def test_selected_finding_survives_agency_brief_board_and_fix_guide(
    agency_id: str,
) -> None:
    from scorecard_pipeline import render_site
    from scorecard_pipeline.render_site import _render_agency, _render_brief, _render_fix
    from scorecard_pipeline.site_shell import esc

    root = Path(__file__).parent / "fixtures" / "golden_site"
    artifact = json.loads((root / "data" / "artifacts" / agency_id / "latest.json").read_text())
    code = artifact["top_fixes"][0]["code"]
    render_site.FIX_CODES_WITH_PAGES.add(code)
    try:
        agency_html = _render_agency(artifact)
        brief_html = _render_brief(artifact)
        board_html = _render_board_page(artifact)
    finally:
        render_site.FIX_CODES_WITH_PAGES.discard(code)

    expected = f"?finding={code}#finding-handoff"
    for html in (agency_html, brief_html, board_html):
        assert 'id="finding-handoff"' in html
        assert f'data-finding-panel="{code}"' in html
        assert expected in html
        assert esc(artifact["top_fixes"][0]["what"]) in html
        assert esc(artifact["top_fixes"][0]["fix"]) in html
        assert "next complete, comparable scorecard run" in html
        assert "this finding is no longer reported" in html
        assert "Copy handoff text" in html

    assert "Finding code:" in agency_html
    assert "Validator rule:" not in agency_html

    fix_html = _render_fix(
        code,
        _authored_markdown(f"# Fix {code}\n\nFollow the published guide.\n"),
    )
    assert f'data-fix-context="{code}"' in fix_html
    assert "Keep " + code + " attached to the agency record" in fix_html
    assert "[data-context-target]" in fix_html


def test_board_page_never_publishes_individual_percentile_standing() -> None:
    record = {"national_percentile": 76, "peer_percentile": 88, "size_tier": "small"}
    html = _render_board_page(_board_artifact(), dir_record=record)
    assert "Where this agency stands" not in html
    assert "76%" not in html and "88%" not in html


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
    assert "2 verified finding clearances" in html
    # Every receipt is its own anchor with a self-link, newest first.
    assert 'id="r-2026-07-01-expired_calendar"' in html
    assert '"#r-2026-06-11-unused_shape"' in html
    assert html.index("expired_calendar") < html.index("unused_shape")
    assert "Reported through 2026-06-30" in html
    assert "the 2026-07-01 check verified it gone" in html


def test_fixlog_metadata_reuses_planned_feed_disambiguators() -> None:
    from html import unescape

    from scorecard_pipeline.config import Agency
    from scorecard_pipeline.render_site import (
        _plan_agency_seo_metadata,
        _render_fixlog_page,
    )

    agency_name = "North County Transit District (NCTD)"
    records = [
        {
            "id": "north-county-transit-district-nctd",
            "name": agency_name,
            "country": "US",
            "subdivision_name": "California",
        },
        {
            "id": "north-county-transit-district-nctd-3093",
            "name": agency_name,
            "country": "US",
            "subdivision_name": "California",
        },
    ]
    artifacts = {
        record["id"]: {
            "agency": {"id": record["id"], "name": agency_name},
            "categories": {"realtime": {"status": "not_yet_measured"}},
        }
        for record in records
    }
    registry = {
        records[0]["id"]: Agency(
            records[0]["id"],
            agency_name,
            "https://example.test/nctd.zip",
            mdb_id="14",
        ),
        records[1]["id"]: Agency(
            records[1]["id"],
            agency_name,
            "https://example.test/nctd-3093.zip",
            mdb_id="3093",
        ),
    }
    planned = _plan_agency_seo_metadata(records, artifacts, registry)
    receipts = [
        {
            "code": "expired_calendar",
            "what": "The old calendar was replaced.",
            "last_seen": "2026-06-30",
            "cleared": "2026-07-01",
        }
    ]

    pages = [
        _render_fixlog_page(
            artifacts[record["id"]],
            receipts,
            record,
            seo_metadata=planned[record["id"]],
        )
        for record in records
    ]
    titles = [unescape(page.split("<title>", 1)[1].split("</title>", 1)[0]) for page in pages]
    descriptions = [
        unescape(page.split('<meta name="description" content="', 1)[1].split('">', 1)[0])
        for page in pages
    ]

    assert "[MDB 14]" in planned[records[0]["id"]].title
    assert "[MDB 3093]" in planned[records[1]["id"]].title
    assert len(set(titles)) == len(set(descriptions)) == 2
    assert all(len(title) <= 60 for title in titles)
    assert all(len(description) <= 155 for description in descriptions)
    assert "[MDB 14]" in titles[0] and "[MDB 3093]" in titles[1]
    assert all(
        f'<h1 class="page-title">Finding clearance log: {agency_name}</h1>' in page
        for page in pages
    )
    assert (
        f'<link rel="canonical" href="https://gtfsscorecard.org/agency/{records[0]["id"]}/fixes/">'
        in pages[0]
    )
    assert (
        f'<link rel="canonical" href="https://gtfsscorecard.org/agency/{records[1]["id"]}/fixes/">'
        in pages[1]
    )
    assert f'<meta property="og:title" content="{titles[0]}">' in pages[0]
    assert f'<meta property="og:title" content="{titles[1]}">' in pages[1]


def test_fixlog_metadata_preserves_location_identity_and_bounds_long_names() -> None:
    from html import unescape

    from scorecard_pipeline.config import Agency
    from scorecard_pipeline.render_site import (
        _agency_seo_metadata,
        _plan_agency_seo_metadata,
        _render_fixlog_page,
    )

    records = [
        {
            "id": "capital-transit-alaska",
            "name": "Capital Transit",
            "country": "US",
            "subdivision_name": "Alaska",
        },
        {
            "id": "capital-transit-montana",
            "name": "Capital Transit",
            "country": "US",
            "subdivision_name": "Montana",
        },
    ]
    artifacts = {
        record["id"]: {
            "agency": {"id": record["id"], "name": record["name"]},
            "categories": {"realtime": {"status": "not_yet_measured"}},
        }
        for record in records
    }
    registry = {
        record["id"]: Agency(
            record["id"],
            record["name"],
            f"https://example.test/{record['id']}.zip",
        )
        for record in records
    }
    planned = _plan_agency_seo_metadata(records, artifacts, registry)
    receipts = [
        {
            "code": "expired_calendar",
            "what": "The old calendar was replaced.",
            "last_seen": "2026-06-30",
            "cleared": "2026-07-01",
        }
    ]

    pages = [
        _render_fixlog_page(
            artifacts[record["id"]],
            receipts,
            record,
            seo_metadata=planned[record["id"]],
        )
        for record in records
    ]
    titles = [unescape(page.split("<title>", 1)[1].split("</title>", 1)[0]) for page in pages]
    descriptions = [
        unescape(page.split('<meta name="description" content="', 1)[1].split('">', 1)[0])
        for page in pages
    ]

    assert "(Alaska)" in titles[0] and "(Montana)" in titles[1]
    assert len(set(titles)) == len(set(descriptions)) == 2
    assert all(len(title) <= 60 for title in titles)
    assert all(len(description) <= 155 for description in descriptions)

    long_name = (
        "San Francisco Bay Area Water Emergency Transportation Authority "
        "(WETA) Regional Ferry Service"
    )
    long_artifact = {"agency": {"id": "weta", "name": long_name}}
    long_page = _render_fixlog_page(
        long_artifact,
        receipts,
        seo_metadata=_agency_seo_metadata(long_name, location_label="California"),
    )
    long_title = unescape(long_page.split("<title>", 1)[1].split("</title>", 1)[0])
    long_description = unescape(
        long_page.split('<meta name="description" content="', 1)[1].split('">', 1)[0]
    )
    assert len(long_title) <= 60
    assert len(long_description) <= 155
    assert long_title.endswith("GTFS clearance log")


def test_previous_artifact_requires_exact_index_identity_and_summary() -> None:
    from scorecard_pipeline.render_site import _previous_indexed_artifact

    history: list[dict[str, Any]] = [
        {"date": "2026-06-27"},
        {
            "date": "2026-07-23",
            "score": 73,
            "grade": "C",
            "feed_sha256": "expected-feed-hash",
        },
        {"date": "2026-07-25"},
    ]
    stale_checkout: list[dict[str, Any]] = [
        {"agency": {"id": "agency-one"}, "snapshot_date": "2026-06-26"},
        {"agency": {"id": "agency-one"}, "snapshot_date": "2026-06-27"},
        {"agency": {"id": "agency-one"}, "snapshot_date": "2026-07-25"},
    ]

    assert _previous_indexed_artifact("agency-one", history, stale_checkout) is None
    wrong_identity = {
        "agency": {"id": "agency-two"},
        "snapshot_date": "2026-07-23",
        "overall": {"score": 73, "grade": "C"},
        "feed": {"sha256": "expected-feed-hash"},
    }
    malformed_identity = {
        "agency": "not-an-object",
        "snapshot_date": "2026-07-23",
    }
    wrong_summary = {
        "agency": {"id": "agency-one"},
        "snapshot_date": "2026-07-23",
        "overall": {"score": 72, "grade": "C"},
        "feed": {"sha256": "stale-feed-hash"},
    }
    assert (
        _previous_indexed_artifact(
            "agency-one",
            history,
            [*stale_checkout, wrong_identity, malformed_identity, wrong_summary],
        )
        is None
    )
    exact_prior = {
        "agency": {"id": "agency-one"},
        "snapshot_date": "2026-07-23",
        "overall": {"score": 73, "grade": "C"},
        "feed": {"sha256": "expected-feed-hash"},
    }
    assert (
        _previous_indexed_artifact(
            "agency-one",
            history,
            [*stale_checkout, wrong_summary, exact_prior],
        )
        == exact_prior
    )


def test_non_us_fixlog_prefers_current_directory_country_over_a_stale_artifact() -> None:
    from scorecard_pipeline.render_site import _render_fixlog_page

    artifact = {
        "agency": {
            "id": "legacy-ca",
            "name": "Legacy Canadian Transit",
            "country": "US",
        }
    }
    receipts = [
        {
            "code": "expired_calendar",
            "what": "The old calendar was replaced.",
            "last_seen": "2026-06-30",
            "cleared": "2026-07-01",
        }
    ]

    html = _render_fixlog_page(artifact, receipts, dir_record={"country": "CA"})

    assert "United States tools" not in html
    assert 'href="/ntd/"' not in html
    assert 'href="/equity/"' not in html
    assert 'href="/agencies/"' in html and 'href="/check/"' in html


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
    return {
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile": {
            "id": f"gtfs-scorecard-{RUBRIC_VERSION}",
            "rubric_version": RUBRIC_VERSION,
        },
        "validator_version": "8.0.1",
        "categories": {"correctness": {"status": "measured", "findings": list(findings)}},
    }


def _with_contract(points: list[dict]) -> list[dict]:  # type: ignore[type-arg]
    """Give synthetic history points the provenance production now requires."""
    for point in points:
        point.setdefault("rubric_version", RUBRIC_VERSION)
        point.setdefault("scoring_profile_id", f"gtfs-scorecard-{RUBRIC_VERSION}")
        point.setdefault("scoring_profile_rubric_version", RUBRIC_VERSION)
        point.setdefault("validator_version", "8.0.1")
        if not point.get("categories"):
            point["categories"] = {"correctness": point.get("score", 0.0)}
    return points


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


@pytest.mark.parametrize(
    "code",
    ["scorecard_feed_expired", "scorecard_feed_expiring_soon"],
)
def test_fix_rule_reference_describes_effective_expiry_provenance(code: str) -> None:
    from scorecard_pipeline.render_site import _fix_rule_reference

    html = _fix_rule_reference(code)

    assert "combines feed_info and calendar service dates" in html
    assert "no single validator rule uses this exact combined calculation" in html
    assert "the field is valid GTFS when left empty" not in html
    assert "Read the relevant GTFS Best Practice" in html


@pytest.mark.parametrize(
    "code",
    [
        "scorecard_missing_headsigns",
        "scorecard_no_fare_data",
        "scorecard_stop_names_all_caps",
    ],
)
def test_fix_rule_reference_uses_neutral_best_practice_provenance(code: str) -> None:
    from scorecard_pipeline.render_site import _fix_rule_reference

    html = _fix_rule_reference(code)

    assert "The GTFS Validator does not flag this" in html
    assert "the field is valid GTFS when left empty" not in html
    assert "Read the relevant GTFS Best Practice" in html


def test_fix_rule_reference_does_not_overstate_realtime_reference() -> None:
    from scorecard_pipeline.render_site import _fix_rule_reference

    html = _fix_rule_reference("scorecard_rt_trip_coverage")

    assert "reference defines the message this scorecard checks" in html
    assert "expectation comes from" not in html


def test_fix_rule_reference_does_not_overstate_schedule_reference() -> None:
    from scorecard_pipeline.render_site import _fix_rule_reference

    html = _fix_rule_reference("scorecard_wheelchair_boarding_unknown")

    assert "reference defines the field or data this scorecard finding checks" in html
    assert "expectation comes from" not in html


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

    history = _with_contract(
        [
            {
                "date": "2026-06-10",
                "score": 70.0,
                "grade": "C",
                "rubric_version": RUBRIC_VERSION,
                "categories": {"correctness": 80.0},
            },
            {
                "date": "2026-06-11",
                "score": 75.0,
                "grade": "C",
                "rubric_version": RUBRIC_VERSION,
                "categories": {"correctness": 90.0},
            },
        ]
    )
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

    history = _with_contract(
        [
            {"date": "2026-06-10", "score": 70.0, "grade": "C", "rubric_version": RUBRIC_VERSION},
            {"date": "2026-06-11", "score": 75.0, "grade": "C", "rubric_version": RUBRIC_VERSION},
        ]
    )
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
        "a-t": _with_contract(
            [
                {
                    "date": "2026-06-10",
                    "score": 93.0,
                    "grade": "A",
                    "rubric_version": RUBRIC_VERSION,
                },
                {
                    "date": "2026-06-11",
                    "score": 95.0,
                    "grade": "A",
                    "rubric_version": RUBRIC_VERSION,
                },
            ]
        )
    }
    html = _leaderboard_sections(board, histories)
    assert "<th>Trend</th>" in html
    assert 'aria-label="Score trend for Alpha: 2026-06-10 93.0; 2026-06-11 95.0"' in html
    assert "spark-mini" in html
    # Retired top/bottom rows never render, even if present in stale cached input.
    assert "Zulu" not in html
    # Without histories at all, every trend cell degrades to the em dash.
    assert "spark-mini" not in _leaderboard_sections(board)


def test_leaderboard_ignores_ranked_lists_under_policy() -> None:
    from scorecard_pipeline.render_site import _leaderboard_sections

    html = _leaderboard_sections(
        {
            "comparison": {
                "suppressed": True,
                "eligible_count": 7,
                "minimum_cohort": 20,
            },
            "top": [{"id": "should-not-render", "name": "Hidden"}],
        }
    )
    assert "Absolute rankings and individual percentiles are not published" in html
    assert "Hidden" not in html


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
    assert "Lowest scoring" not in html
    assert "A Transit" not in html and "Z Transit" not in html


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
    # Retired bottom rows stay hidden; ridership is contextual only on a mover.
    assert "5,000,000" not in html
    assert "250,000" in html
    # A row without a matched ridership record renders an empty cell, not "None".
    assert ">None<" not in html
    assert html.count("Riders/yr") == 1


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
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile": {
            "id": f"gtfs-scorecard-{RUBRIC_VERSION}",
            "rubric_version": RUBRIC_VERSION,
        },
        "validator_version": "8.0.1",
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
    assert "Finding code: new_one" in html
    assert "Validator rule:" not in html
    assert "No longer reported since 2026-06-11" in html
    assert "an old issue" in html
    assert "does not establish who made a change or why" in html
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

    history = _with_contract(
        [
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
    )
    html = _history_section(history)
    assert "What changed over time" in html
    assert "2026-06-14" in html and "Grade went B to C" in html
    # A flat feed gets nothing.
    steady = _with_contract(
        [
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
    )
    assert _history_section(steady) == ""
    assert _history_section(None) == ""


def test_history_section_leads_with_a_dated_grade_story_paragraph() -> None:
    from scorecard_pipeline.render_site import _history_section

    history = _with_contract(
        [
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
    )
    artifacts = _with_contract(
        [
            {
                "snapshot_date": "2026-06-10",
                "categories": {
                    "correctness": {
                        "status": "measured",
                        "findings": [{"code": "missing_feed_contact", "what": "no contact"}],
                    }
                },
            },
            {
                "snapshot_date": "2026-06-14",
                "categories": {"correctness": {"status": "measured", "findings": []}},
            },
        ]
    )
    html = _history_section(history, artifacts)
    assert 'class="grade-story"' in html
    assert "On 2026-06-10 this feed started at grade B." in html
    assert "the check no longer reported: no contact" in html
    # The story sits above the newest-first timeline lede.
    assert html.index('class="grade-story"') < html.index("newest first")


def test_embed_section_offers_a_live_badge_and_copyable_markdown() -> None:
    from scorecard_pipeline.render_site import _embed_section

    html = _embed_section("demo-transit", "Demo Transit", "B")
    assert "Show your grade" in html
    # A live badge preview and a copyable Markdown snippet pointing at the
    # published badge.svg and the agency page.
    assert "/data/artifacts/demo-transit/badge.svg" in html
    assert "https://gtfsscorecard.org/agency/demo-transit/" in html
    assert 'class="copy-btn"' in html and 'data-copy="embed-md"' in html
    # The shields.io endpoint alternative points at badge.json.
    assert "img.shields.io/endpoint" in html and "badge.json" in html
    assert "Demo Transit" in html  # alt text names the agency


def test_embed_section_markdown_alt_text_names_the_agency_and_grade() -> None:
    from scorecard_pipeline.render_site import _embed_section

    html = _embed_section("demo-transit", "Demo Transit", "B")
    # The copied Markdown's own alt text (inside the textarea, HTML-escaped)
    # names the agency and its grade, not a generic "GTFS data quality" with
    # no link context -- so a screen reader or a stripped-image client still
    # gets the badge's content, and a README gets a real anchor.
    assert "[![Demo Transit GTFS data quality grade: B]" in html
    assert "![GTFS data quality]" not in html
    # The live preview's own alt attribute matches.
    assert 'alt="Demo Transit GTFS data quality grade: B"' in html


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

    def comparable(point: dict[str, object]) -> dict[str, object]:
        point.update(
            {
                "rubric_version": "1.2",
                "scoring_profile_id": "gtfs-scorecard-1.2",
                "scoring_profile_rubric_version": "1.2",
                "validator_version": "8.0.1",
                "categories": {"correctness": 80.0},
            }
        )
        return point

    dip = [
        comparable({"date": "2026-06-16", "score": 80.0, "grade": "B", "days_until_expiry": 83}),
        comparable({"date": "2026-06-19", "score": 44.0, "grade": "F", "days_until_expiry": -138}),
        comparable({"date": "2026-06-20", "score": 83.0, "grade": "B", "days_until_expiry": 79}),
    ]
    html = _anomaly_note(dip)
    assert "Heads-up" in html and "anomaly-note" in html
    steady = [
        comparable({"date": "2026-06-19", "score": 82.0, "grade": "B", "days_until_expiry": 80}),
        comparable({"date": "2026-06-20", "score": 83.0, "grade": "B", "days_until_expiry": 79}),
    ]
    assert _anomaly_note(steady) == ""
    assert _anomaly_note([]) == ""

    profile_change = [dict(point) for point in dip]
    profile_change[-1]["reader_archive_profile"] = "flat-single-root-v1"
    assert _anomaly_note(profile_change) == ""


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
    assert '<meta name="robots" content="noindex,follow">' in html


def test_canadian_brief_omits_us_ntd_language() -> None:
    from scorecard_pipeline.render_site import _render_brief

    artifact = {
        # The directory remains a safe fallback for older artifacts that did
        # not yet carry the additive country field.
        "agency": {"id": "barrie", "name": "Barrie Transit"},
        "overall": {"grade": "B", "score": 84.0},
        "snapshot_date": "2026-07-01",
        "feed": {"static_url": "https://example.ca/gtfs.zip"},
        "categories": {"freshness": {"status": "measured", "details": {}}},
        "top_fixes": [],
    }
    html = _render_brief(
        artifact,
        dir_record={
            "country": "CA",
            "subdivision_code": "CA-ON",
            "subdivision_name": "Ontario",
        },
    )
    assert 'id="brief-ntd-h"' not in html
    assert "NTD details line up" not in html
    assert "rider information is complete" in html
    assert "guidance, and key feed facts" in html
    assert "<dt>Location</dt><dd>Ontario, Canada</dd>" in html
    assert "United States tools" not in html
    assert 'href="/ntd/"' not in html


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
    # "<abbr ...>NTD</abbr> GTFS readiness" without implying certification.
    assert "GTFS readiness" in html
    assert "certification readiness" not in html
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
    # A mismatch shows optional equality neutrally; required agency_id presence
    # is a separate readiness pillar (ADR 0016).
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
    assert "agency_id provided" in html
    assert "agency_id equals your NTD ID (optional)" in html
    assert "Different (allowed)" in html
    assert "Needs attention" not in html
    # The wording is recomputed at render time from the stored inputs, so a
    # stale artifact can never resurface pre-final-rule prescriptive copy: the
    # fixture's baked-in strings are ignored in favour of the current ones.
    assert "Confirm that P-50 crosswalks agency_id UNITRANS to NTD ID 90142" in html
    assert "Your feed uses agency_id UNITRANS." not in html
    # The fineprint states the P-50 crosswalk and rejects an equality mandate.
    assert "P-50 form" in html
    assert "values do not need to be equal" in html

    # Absent block (older artifacts) renders no alignment row.
    old_html = _ntd_section(base)
    assert "agency_id equals your NTD ID (optional)" not in old_html
    assert "agency_id presence has not been checked" in old_html

    # Missing presence is required work, not an optional-equality suggestion.
    missing = {
        **base,
        "ntd_id_alignment": {
            "status": "missing",
            "detail": "stale",
            "ntd_id": "90142",
            "feed_agency_ids": [],
        },
    }
    missing_html = _ntd_section(missing)
    assert "agency.txt has no nonblank agency_id" in missing_html
    assert "Not ready" in missing_html
    assert "agency_id equals your NTD ID (optional)" not in missing_html


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


def test_rollup_common_fixes_section_links_the_fix_guide_when_one_exists() -> None:
    from scorecard_pipeline.render_site import FIX_CODES_WITH_PAGES, _rollup_common_fixes_section

    FIX_CODES_WITH_PAGES.add("scorecard_no_feed_contact")
    try:
        rollup = {
            "rollup": {"id": "test-state", "name": "Test State"},
            "common_fixes": [
                {
                    "code": "scorecard_no_feed_contact",
                    "fix": "Add feed_contact_email to feed_info.txt.",
                    "agencies": 5,
                }
            ],
        }
        html = _rollup_common_fixes_section(rollup)
        assert "Fixes shared across this group" in html
        assert "Add feed_contact_email to feed_info.txt." in html
        assert "Shared by 5 agencies in this group." in html
        assert 'href="/fix/scorecard_no_feed_contact/"' in html
    finally:
        FIX_CODES_WITH_PAGES.discard("scorecard_no_feed_contact")


def test_rollup_common_fixes_section_omits_the_guide_link_without_a_page() -> None:
    from scorecard_pipeline.render_site import FIX_CODES_WITH_PAGES, _rollup_common_fixes_section

    FIX_CODES_WITH_PAGES.discard("some_uncovered_code")
    rollup = {
        "rollup": {"id": "test-state", "name": "Test State"},
        "common_fixes": [{"code": "some_uncovered_code", "fix": "Do the thing.", "agencies": 2}],
    }
    html = _rollup_common_fixes_section(rollup)
    assert "Do the thing." in html
    assert "fix-guide" not in html


def test_rollup_common_fixes_section_empty_when_nothing_shared() -> None:
    from scorecard_pipeline.render_site import _rollup_common_fixes_section

    rollup = {"rollup": {"id": "test-state", "name": "Test State"}, "common_fixes": []}
    assert _rollup_common_fixes_section(rollup) == ""


def test_rollup_common_fixes_section_caps_at_ten_and_links_the_full_list() -> None:
    from scorecard_pipeline.render_site import _rollup_common_fixes_section

    common = [{"code": f"code_{i}", "fix": f"Fix {i}.", "agencies": 20 - i} for i in range(15)]
    rollup = {"rollup": {"id": "big-state", "name": "Big State"}, "common_fixes": common}
    html = _rollup_common_fixes_section(rollup)
    assert "Fix 0." in html
    assert "Fix 9." in html
    assert "Fix 10." not in html
    assert "5 more shared fixes" in html
    assert 'href="/data/artifacts/rollups/big-state.json"' in html


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
    # Links the on-site crosswalk page, not the raw GitHub source file.
    assert 'href="/crosswalk/"' in html
    assert "docs/crosswalk.md" not in html


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
        _map_feature(
            "alpha-transit", _sample_artifact("A", -97.0, 40.0), "Iowa", "US", "US-IA", "Iowa"
        ),
        _map_feature(
            "bravo-transit", _sample_artifact("F", -80.0, 35.0), "Ohio", "US", "US-OH", "Ohio"
        ),
    ]
    return [f for f in feats if f is not None]


def _directory_index(count: int) -> dict[str, Any]:
    return {
        "agencies": {
            f"agency-{number:03d}": {
                "name": f"Agency {number:03d}",
                "history": [
                    {
                        "grade": "B",
                        "score": 82.0,
                        "date": "2026-07-28",
                        "days_until_expiry": 30,
                    }
                ],
            }
            for number in range(count)
        }
    }


def test_agency_directory_pagination_is_complete_canonical_and_crawlable() -> None:
    index = _directory_index(7)
    pages = [_render_agency_index(index, {}, page=page, page_size=3) for page in range(1, 4)]

    assert '<link rel="canonical" href="https://gtfsscorecard.org/agencies/">' in pages[0]
    assert 'rel="prev"' not in pages[0]
    assert '<link rel="next" href="https://gtfsscorecard.org/agencies/page/2/">' in pages[0]
    assert '<link rel="canonical" href="https://gtfsscorecard.org/agencies/page/2/">' in pages[1]
    assert '<link rel="prev" href="https://gtfsscorecard.org/agencies/">' in pages[1]
    assert '<link rel="next" href="https://gtfsscorecard.org/agencies/page/3/">' in pages[1]
    assert '<link rel="canonical" href="https://gtfsscorecard.org/agencies/page/3/">' in pages[2]
    assert 'rel="next"' not in pages[2]
    links = [
        agency_id
        for html in pages
        for agency_id in re.findall(r'href="/agency/(agency-\d{3})/"', html)
    ]
    assert links == [f"agency-{number:03d}" for number in range(7)]
    assert len(links) == len(set(links))
    assert "<title>Agency scorecards — GTFS Scorecard</title>" in pages[0]
    assert "<title>Agency scorecards, page 2 — GTFS Scorecard</title>" in pages[1]
    assert 'aria-current="page">Page 2 of 3' in pages[1]


def test_agency_directory_rejects_a_page_outside_the_chain() -> None:
    with pytest.raises(ValueError, match=r"outside 1\.\.2"):
        _render_agency_index(_directory_index(4), {}, page=3, page_size=3)


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


def test_render_map_page_bounds_initial_dom_and_hydrates_safely() -> None:
    features = []
    for number in range(55):
        artifact = _sample_artifact("B", -120.0 + number / 10, 35.0)
        artifact["agency"]["name"] = f"Agency {number:03d}"
        feature = _map_feature(
            f"agency-{number:03d}", artifact, "California", "US", "US-CA", "California"
        )
        assert feature is not None
        features.append(feature)
    features[-1]["properties"]["name"] = "ZZZ <unsafe> & agency"

    html = _render_map_page(features)

    assert html.count("<tr data-grade=") == 50
    assert "Agency 049" in html
    assert "ZZZ &lt;unsafe&gt;" not in html
    assert html.count('fetch("/map.geojson"') == 1
    assert "document.createDocumentFragment()" in html
    assert "name.textContent =" in html
    assert r"/^[a-z0-9][a-z0-9-]*$/.test(id)" in html
    assert "var dataPromise = null;" in html
    assert "if (!rowsHydrated)" in html
    assert "Loading the complete scorecard list for this filter." in html
    assert '<select id="map-grade"' in html and '<select id="map-grade" disabled' not in html
    assert 'href="/agencies/">complete paginated agency directory</a>' in html


def test_render_map_page_links_points_to_rows_with_keyboard_model() -> None:
    html = _render_map_page(_map_features())
    # The existing agency link is the single ID source for linked brushing;
    # avoid duplicating every slug in the full table's markup.
    assert 'href="/agency/alpha-transit/"' in html
    assert 'href="/agency/bravo-transit/"' in html
    assert "function rowAgencyId(tr)" in html
    assert "data-id=" not in html
    # A highlight layer enlarges one point at a time (the routes-hi pattern).
    assert '"agencies-hi"' in html
    assert '["==", ["get", "id"], NONE]' in html
    # Point -> row: hovering brushes the row and scrolls it into view, except
    # under prefers-reduced-motion.
    assert '"mousemove", "agencies"' in html
    assert "scrollIntoView" in html
    assert "!reduce" in html
    # Row -> point: the row's existing link is the tab stop (no new tabindex);
    # focus reaching it brushes, and Space pins without scrolling the page.
    assert '"focusin"' in html and '"focusout"' in html
    assert 'tabindex="0"' not in html
    assert "e.preventDefault()" in html
    # A changed filter never moves focus (WCAG 3.2.2 On Input): the result
    # count sits in a role="status" live region that a screen reader announces
    # on its own, and a skip link jumps to the list on demand.
    assert "focusResults" not in html
    assert 'role="status"' in html
    assert 'href="#agency-list"' in html
    assert 'id="agency-list" tabindex="-1"' in html


def test_render_map_page_filters_cover_grade_and_state() -> None:
    html = _render_map_page(_map_features())
    assert 'id="map-grade"' in html and 'id="map-state"' in html
    # Portable subdivision options are namespaced and country-qualified.
    assert '<option value="subdivision:US-IA">Iowa, United States</option>' in html
    assert '<option value="subdivision:US-OH">Ohio, United States</option>' in html


def test_render_map_page_generates_configured_non_us_country_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline.location import COUNTRY_NAMES

    monkeypatch.setitem(COUNTRY_NAMES, "GB", "United Kingdom")
    feature = _map_feature(
        "example-gb", _sample_artifact("B", -1.5, 52.3), "", "GB", "GB-ENG", "England"
    )
    assert feature is not None
    html = _render_map_page([feature])
    assert '<option value="country:GB">United Kingdom</option>' in html
    assert '<option value="subdivision:GB-ENG">England, United Kingdom</option>' in html
    assert 'data-country="GB"' in html
    assert "<bdi>England, United Kingdom</bdi>" in html
    assert "country === loc.slice(countryPrefix.length)" in html
    assert 'loc === "Canada"' not in html
    assert "map.fitBounds(bounds" in html
    assert "animate: !reduce" in html
    assert "if (fittedLocation)" in html
    assert "var worldBounds = [[-180, -85], [180, 85]];" in html
    assert "bounds: worldBounds" in html
    assert "map.fitBounds(worldBounds" in html


def test_render_map_page_disambiguates_duplicate_subdivision_names_with_iso_code() -> None:
    first = _sample_artifact("B", -1.5, 52.3)
    first["agency"]["name"] = "First Transit"
    second = _sample_artifact("A", -3.2, 55.9)
    second["agency"]["name"] = "Second Transit"
    features = [
        _map_feature("first", first, "", "GB", "GB-ENG", "Central"),
        _map_feature("second", second, "", "GB", "GB-SCT", "Central"),
    ]

    html = _render_map_page([feature for feature in features if feature is not None])

    assert '<option value="subdivision:GB-ENG">Central (GB-ENG), United Kingdom</option>' in html
    assert '<option value="subdivision:GB-SCT">Central (GB-SCT), United Kingdom</option>' in html


def test_routes_map_initial_bounds_include_high_arctic_agencies() -> None:
    from scorecard_pipeline.render_site import _routes_map_script

    script = _routes_map_script()

    assert "var worldBounds = [[-180, -85], [180, 85]];" in script
    assert "bounds: worldBounds" in script


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
    assert "These scorecards are not like-for-like" in html
    assert "scoring profile" in html and "validator" in html
    assert "reader archive profile" in html
    assert "flat-single-root-v1" in html and "raw-v1" in html
    assert "hasOwnProperty.call(owner" in html
    assert "contractA.readerArchive === contractB.readerArchive" in html
    assert "distinct feed bytes" in html and "measured category set" in html


def test_citation_carries_the_reader_archive_profile() -> None:
    from scorecard_pipeline.render_site import _citation_bibtex, _citation_reference

    artifact = _diff_artifact(date="2026-06-12", grade="B", score=82.0)
    artifact["fetch"] = {"reader_archive_profile": "flat-single-root-v1"}
    url = "https://gtfsscorecard.org/data/artifacts/demo/2026-06-12.json"

    reference = _citation_reference(artifact, "demo", "Demo Transit", url)
    bibtex = _citation_bibtex(artifact, "demo", "Demo Transit", url)

    assert "reader archive profile flat-single-root-v1" in reference
    assert "reader archive profile flat-single-root-v1" in bibtex


def test_render_map_page_marker_shows_grade_not_color_only() -> None:
    html = _render_map_page(_map_features())
    # A symbol layer draws the grade letter on every point (WCAG 1.4.1).
    assert '"text-field": ["get", "grade"]' in html
    # Clustering at low zoom, and reduced-motion is honoured for the cluster zoom.
    assert "cluster: true" in html
    assert "prefers-reduced-motion" in html
    # The canvas is an enhancement: aria-hidden, no on-canvas controls.
    assert 'id="map" class="national-map national-map-pending" aria-hidden="true"' in html
    assert "NavigationControl" not in html
    assert "attributionControl: false" in html
    # The expensive visual enhancement loads only after an explicit request.
    assert 'id="map-load"' in html
    assert '<script src="https://unpkg.com/maplibre-gl' not in html
    assert 'script.src = "https://unpkg.com/maplibre-gl' in html
    # Do not duplicate every agency name in an unused data attribute. On the
    # full directory that dead payload materially delays first paint.
    assert "data-name=" not in html
    assert "data-id=" not in html
    assert "rowAgencyId" in html


# ---- equity choropleth (/equity/) ----


_EQUITY: dict[str, Any] = {
    "comparison_eligible_count": 13,
    "comparison": {"eligible_count": 13},
    "priority": [
        {
            "state": "Louisiana",
            "low_grade_share": 100.0,
            "agency_count": 3,
            "feed_record_count": 3,
            "comparison_eligible_count": 3,
            "median_score": 37.4,
            "need_tier": "high",
        }
    ],
    "states": [
        {
            "state": "Louisiana",
            "low_grade_share": 100.0,
            "agency_count": 3,
            "feed_record_count": 3,
            "comparison_eligible_count": 3,
            "median_score": 37.4,
            "need_tier": "high",
        },
        {
            "state": "Iowa",
            "low_grade_share": 20.0,
            "agency_count": 10,
            "feed_record_count": 10,
            "comparison_eligible_count": 10,
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
    assert (
        "Louisiana: High need, 3 feed records covered, "
        "100.0% on D or F across 3 comparable feed records"
    ) in svg
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
    assert "score-based priority" in html
    assert "unavailable until current-contract checks" in html


def test_render_equity_page_without_geometry_keeps_tables() -> None:
    html = _render_equity_page(_EQUITY, None)
    assert "us-map-svg" not in html
    assert "High-need states" in html and "Every state" in html


def test_equity_choropleth_omits_score_claim_without_state_denominator() -> None:
    by_state = {
        "Iowa": {
            "state": "Iowa",
            "need_tier": "lower",
            "feed_record_count": 10,
            "comparison_eligible_count": 0,
            # A stale artifact may still carry this old value. It must not leak
            # through the SVG title while the comparison denominator is zero.
            "low_grade_share": 20.0,
        }
    }
    svg = _equity_choropleth(_GEO, by_state)
    assert "Iowa: Lower need, 10 feed records covered" in svg
    assert "20.0%" not in svg
    assert "D or F" not in svg


def test_ntd_page_carries_ry2026_and_one_fix_table() -> None:
    from scorecard_pipeline.render_site import _FEDERAL_REGISTER_RY2026, _render_ntd_page

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
        "close-t": _with_contract(
            [
                {
                    "date": "2026-06-10",
                    "score": 71.0,
                    "grade": "C",
                    "rubric_version": RUBRIC_VERSION,
                },
                {
                    "date": "2026-06-11",
                    "score": 72.0,
                    "grade": "C",
                    "rubric_version": RUBRIC_VERSION,
                },
            ]
        )
    }
    html = _render_ntd_page(payload, histories)
    # The RY2026 wave and the waiver path are named, with the rule cited.
    assert "Report year 2026" in html
    assert "waiver" in html
    assert f'<a href="{_FEDERAL_REGISTER_RY2026}">' in html
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
    # The RY2026 section hands off to the shapes.txt explainer.
    assert 'href="/ntd/shapes/"' in html


def test_shapes_page_explains_the_phase_in_and_carries_the_numbers() -> None:
    from scorecard_pipeline.render_site import _FEDERAL_REGISTER_RY2026, _render_shapes_page

    shapes = {
        "total": 4,
        "ready": 1,
        "at_risk": 1,
        "not_ready": 2,
        "pct_ready": 25.0,
        "by_state": {"Iowa": {"ready": 1, "at_risk": 1, "not_ready": 2, "total": 4}},
    }
    html = _render_shapes_page(shapes)
    # The lead answers the title question and names both phase-in years.
    assert "Does your GTFS feed need shapes.txt?" in html
    assert "Report Year 2025" in html
    assert "Report Year 2026" in html
    # The requirement is sourced and the waiver path is named.
    assert f'<a href="{_FEDERAL_REGISTER_RY2026}">' in html
    assert "waiver" in html
    # Live numbers: the headline share, the coverage table, and the state row.
    assert "25.0% carry a shape for every trip" in html
    assert "Every trip has a shape" in html
    assert "<td>Iowa</td>" in html
    # Self-serve checks are linked for tracked and untracked feeds alike.
    assert 'href="/agencies/"' in html
    assert 'href="/try.html"' in html
    assert 'href="/check/"' in html
    # The reporter cut stays population-level and states-not-certifies.
    assert "For reporters" in html
    assert "certifies nothing" in html
    assert "not covered, never failing" in html
    assert 'href="/press/"' in html
    assert 'href="/ntd.json"' in html
    # No per-agency links: population framing only on this surface.
    assert 'href="/agency/' not in html
    articles = _jsonld_documents(html)
    assert len(articles) == 1
    _assert_tech_article_identity(
        articles[0],
        "https://gtfsscorecard.org/ntd/shapes/",
    )
    assert articles[0]["about"] == {
        "@type": "Thing",
        "name": "GTFS shapes.txt NTD requirement",
    }
    assert "datePublished" not in articles[0]
    assert "dateModified" not in articles[0]


def test_shapes_page_without_data_keeps_the_explainer() -> None:
    from scorecard_pipeline.render_site import _render_shapes_page

    html = _render_shapes_page({})
    # The explainer stands on its own before any rollup has run.
    assert "No feeds have been checked for shape coverage yet." in html
    assert "Report Year 2026" in html
    assert "Of 0 tracked" not in html
    # No dangling reference to a state table that is not on the page.
    assert "per-state counts above" not in html


def test_rt_page_most_reliable_rows_carry_mini_sparklines() -> None:
    from scorecard_pipeline.render_site import _render_rt_page

    nat = {
        "feed_record_count": 1,
        "comparison_eligible_count": 1,
        "comparison": {"eligible_count": 1},
        "monitored_feed_record_count": 1,
        "raw_monitored_feed_record_count": 1,
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
        "steady-t": _with_contract(
            [
                {
                    "date": "2026-06-10",
                    "score": 88.0,
                    "grade": "B",
                    "rubric_version": RUBRIC_VERSION,
                },
                {
                    "date": "2026-06-11",
                    "score": 90.0,
                    "grade": "A",
                    "rubric_version": RUBRIC_VERSION,
                },
            ]
        )
    }
    html = _render_rt_page(nat, histories)
    assert "Most reliable" in html
    assert "<th>Score trend</th>" in html
    assert 'aria-label="Score trend for Steady Transit: 2026-06-10 88.0; 2026-06-11 90.0"' in html
    assert "spark-mini" in html
    assert 'class="service-chart reliability-chart"' in html
    assert "1 of 1 feeds" in html
    assert "Show the table" in html
    # Without histories the trend cell degrades to an em dash, never breaks.
    assert '<span class="spark-none">&mdash;</span>' in _render_rt_page(nat)


def test_rt_page_renders_collapsed_worldwide_rollups_and_isolated_sample_labels() -> None:
    from scorecard_pipeline.render_site import _render_rt_page

    nat = {
        "feed_record_count": 2,
        "comparison_eligible_count": 2,
        "comparison": {"eligible_count": 2},
        "monitored_feed_record_count": 2,
        "raw_monitored_feed_record_count": 2,
        "monitored_count": 2,
        "median_uptime_pct": 98.5,
        "median_lag_seconds": 18,
        "bands": {"reliable": 1, "mostly": 1, "spotty": 0},
        "most_reliable": [
            {
                "id": "nasu-bus",
                "name": "那須町町民バス",
                "country": "JP",
                "subdivision_code": "JP-09",
                "subdivision_name": "Tochigi",
                "uptime_pct": 99.8,
                "median_lag_seconds": 8,
            }
        ],
        "countries": [
            {
                "country_code": "JP",
                "country_name": "Japan",
                "agencies": 1,
                "median_uptime_pct": 99.8,
                "reliable": 1,
                "subdivisions": [
                    {
                        "subdivision_code": "JP-09",
                        "subdivision_name": "Tochigi",
                        "agencies": 1,
                        "median_uptime_pct": 99.8,
                        "reliable": 1,
                    }
                ],
            },
            {
                "country_code": "US",
                "country_name": "United States",
                "agencies": 1,
                "median_uptime_pct": 97.2,
                "reliable": 0,
                "subdivisions": [],
            },
        ],
        "states": [{"state": "Iowa", "agencies": 1, "median_uptime_pct": 97.2, "reliable": 0}],
    }

    html = _render_rt_page(nat)

    assert "<bdi>Japan</bdi>" in html
    assert "<bdi>Tochigi</bdi>" in html
    assert "Show 1 covered subdivision in <bdi>Japan</bdi>" in html
    assert '<details class="subdivision-rollup">' in html
    assert '<a href="/agency/nasu-bus/"><bdi>那須町町民バス</bdi></a>' in html
    assert "<td><bdi>Tochigi, Japan</bdi></td>" in html
    assert '<h2 class="section-title">United States by state</h2>' in html


def test_rt_page_zero_comparison_suppresses_stale_metrics_and_names() -> None:
    from scorecard_pipeline.render_site import _render_rt_page

    html = _render_rt_page(
        {
            "feed_record_count": 100,
            "comparison_eligible_count": 0,
            "comparison": {"eligible_count": 0},
            "raw_monitored_feed_record_count": 8,
            "monitored_feed_record_count": 1,
            "monitored_count": 1,
            "median_uptime_pct": 99.9,
            "bands": {"reliable": 1, "mostly": 0, "spotty": 0},
            "most_reliable": [{"id": "stale", "name": "Stale Transit"}],
        }
    )
    assert "unavailable until current-contract checks" in html
    assert "8 observed feed records" in html
    assert "Most reliable" not in html
    assert "Stale Transit" not in html
    assert "99.9%" not in html


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
    assert "Expiry support worklist" in html
    assert "Producer provenance" in html
    assert "reader_archive_profile" in html
    assert "comparison_eligible = true" in html
    assert "not rankings" in html
    assert "Grade distribution" not in html
    assert "Covered-set category averages" not in html
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


def test_page_shell_describes_the_shared_social_image() -> None:
    from scorecard_pipeline.site_shell import _page

    html = _page(
        title="t",
        description="d",
        canonical="https://gtfsscorecard.org/x/",
        body="<p>hi</p>",
    )

    alt = "GTFS Scorecard: transit data quality for small agencies."
    assert html.count(f'<meta property="og:image:alt" content="{alt}">') == 1
    assert html.count(f'<meta name="twitter:image:alt" content="{alt}">') == 1


def test_page_shell_uses_local_system_font_fallbacks() -> None:
    from scorecard_pipeline.site_shell import _page

    html = _page(
        title="t",
        description="d",
        canonical="https://gtfsscorecard.org/x/",
        body="<p>hi</p>",
    )

    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert '<link rel="stylesheet" href="/src/styles.css">' in html


def test_page_shell_can_mark_utility_pages_noindex() -> None:
    from scorecard_pipeline.site_shell import _page

    html = _page(
        title="t",
        description="d",
        canonical="https://gtfsscorecard.org/x/",
        body="<p>hi</p>",
        robots="noindex,follow",
    )

    assert '<meta name="robots" content="noindex,follow">' in html


def test_map_page_names_its_cdn_fallback() -> None:
    html = _render_map_page(_map_features())
    assert "map-fallback" in html
    assert "Use the complete-list control or the paginated agency" in html
    assert 'id="map-load-status"' in html
    assert "The map could not load" in html


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
    # every page. Absorbed pages still light up their hub's stop, and the
    # feature finder has a direct primary-nav destination.
    from scorecard_pipeline.site_shell import _NAV_ITEMS, _nav_active

    hrefs = [href for _, href in _NAV_ITEMS]
    assert len(hrefs) == 6
    assert hrefs == [
        "/agencies/",
        "/pulse/",
        "/app/#/?view=features",
        "/tools/",
        "/how-to-read/",
        "/about/",
    ]
    assert _nav_active("/app/") == "/agencies/"
    assert _nav_active("/map/") == "/agencies/"
    assert _nav_active("/ntd/") == "/pulse/"
    assert _nav_active("/adoption/") == "/app/#/?view=features"
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


def test_page_shell_hides_us_policy_tools_only_for_non_us_agency_context() -> None:
    from scorecard_pipeline.site_shell import _page

    common: dict[str, Any] = {
        "title": "t",
        "description": "d",
        "canonical": "https://gtfsscorecard.org/agency/demo/",
        "body": "<p>x</p>",
    }
    global_html = _page(**common, country_code="JP")
    us_html = _page(**common, country_code="us")

    assert "United States tools" not in global_html
    assert 'href="/ntd/"' not in global_html
    assert 'href="/equity/"' not in global_html
    assert 'href="/agencies/"' in global_html and 'href="/check/"' in global_html
    assert "United States tools" in us_html
    assert 'href="/ntd/"' in us_html and 'href="/equity/"' in us_html


def test_pulse_page_combines_guarded_changes_and_trend_without_rankings() -> None:
    from scorecard_pipeline.render_site import _render_pulse_page

    board = {
        "top": [{"id": "a-t", "name": "Alpha", "grade": "A", "score": 95}],
        "bottom": [{"id": "z-t", "name": "Zulu", "grade": "F", "score": 20}],
        "most_improved": [],
        "most_declined": [],
        "comparison": {"eligible_count": 10},
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
    # One page, two anchored sections, reached by a plain jump nav (no JS).
    for anchor in ('id="changes"', 'id="trend"'):
        assert anchor in html, anchor
    assert 'href="#rankings"' not in html and 'href="#trend"' in html
    # Stale cached absolute ranking rows are ignored.
    assert "Highest scoring" not in html and "Alpha" not in html
    assert "Up Transit" in html and "up 9" in html
    assert '<a class="delta-cat" href="/agency/up1/"><bdi>Up Transit</bdi></a>' in html
    # Common problems stays its own page, linked from here.
    assert 'href="/problems/"' in html
    # The covered-set framing survives the merge, and the page renders wide.
    assert "not covered yet" in html.replace("\n    ", " ")
    assert 'class="wrap wrap-wide"' in html


def test_pulse_distinguishes_one_point_contract_baseline_from_quiet_comparison() -> None:
    from scorecard_pipeline.render_site import _render_pulse_page

    baseline_date = "2030-02-03"
    html = _render_pulse_page(
        {"comparison": {"eligible_count": 10}},
        [],
        [
            {
                "date": baseline_date,
                "average_score": 68.4,
                "agency_count": 10,
                "expired_pct": 5.9,
            }
        ],
        {"points": 1, "score_delta": None, "first": None, "last": None},
        [],
    )

    assert "first comparable snapshot under the current scoring contract" in html
    assert (
        f"Comparable history under the current scoring contract begins on {baseline_date}" in html
    )
    assert "Any scores from earlier contracts are intentionally excluded" in html
    assert "Rechecks on the same day update that day's snapshot" in html
    assert "No material score or grade changes were detected" not in html


def test_pulse_suppresses_change_and_trend_claims_without_a_guarded_cohort() -> None:
    from scorecard_pipeline.render_site import _render_pulse_page

    stale_change = {
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
    html = _render_pulse_page(
        {"comparison": {"eligible_count": 0}},
        [stale_change],
        [
            {"date": "2026-06-01", "average_score": 70.0, "agency_count": 10},
            {"date": "2026-07-01", "average_score": 71.0, "agency_count": 10},
        ],
        {
            "score_delta": 1.0,
            "first": {"date": "2026-06-01"},
            "last": {"date": "2026-07-01", "average_score": 71.0},
        },
        [],
    )

    assert "Named changes are unavailable" in html
    assert "covered-corpus trend is unavailable" in html
    assert "No improvement or regression claim is made" in html
    assert "Up Transit" not in html
    assert "No agencies improved" not in html
    assert "good day" not in html


def test_retired_urls_render_redirects() -> None:
    from scorecard_pipeline.site_shell import _redirect_page

    html = _redirect_page("/pulse/#changes", "What changed")
    assert 'http-equiv="refresh"' in html
    assert "url=/pulse/#changes" in html
    assert '<link rel="canonical" href="https://gtfsscorecard.org/pulse/">' in html
    assert html.count('rel="canonical"') == 1
    assert 'name="robots"' not in html
    # A no-JS, no-meta fallback link is always present.
    assert '<a href="/pulse/#changes">' in html
    # If refreshes are disabled, the fallback is still a complete mobile and
    # keyboard-readable page rather than an unstructured line of text.
    assert '<meta name="viewport"' in html
    assert '<a class="skip-link" href="#main">' in html
    assert '<main id="main"' in html
    assert html.count("<h1") == 1


def test_retired_url_canonical_preserves_query_but_not_literal_fragment() -> None:
    from scorecard_pipeline.site_shell import _redirect_page

    html = _redirect_page(
        "/pulse/?filter=route%23A&sort=score#changes",
        "Route A changes",
    )

    assert (
        '<meta http-equiv="refresh" '
        'content="0; url=/pulse/?filter=route%23A&amp;sort=score#changes">'
    ) in html
    assert (
        '<link rel="canonical" '
        'href="https://gtfsscorecard.org/pulse/?filter=route%23A&amp;sort=score">'
    ) in html
    assert ('<a href="/pulse/?filter=route%23A&amp;sort=score#changes">Route A changes</a>') in html


@pytest.mark.parametrize(
    "target",
    [
        "pulse/#changes",
        "https://example.com/pulse/#changes",
        "//example.com/pulse/#changes",
        r"/\evil.example/pulse/#changes",
        "/pulse/\n#changes",
        "/pulse/\t#changes",
    ],
)
def test_retired_url_redirect_rejects_unsafe_target(target: str) -> None:
    from scorecard_pipeline.site_shell import _redirect_page

    with pytest.raises(ValueError, match="root-relative path"):
        _redirect_page(target, "Unsafe redirect")


def test_adoption_page_absorbs_access_coverage() -> None:
    from scorecard_pipeline.render_site import _render_adoption_page

    adoption = {
        "feed_record_count": 10,
        "comparison_eligible_count": 10,
        "comparison": {"eligible_count": 10},
        "measured_feed_record_count": 10,
        "agency_count": 10,
        "flex": {"count": 4, "pct": 40.0},
        "fares": {"count": 6, "pct": 60.0},
        "fares_v2": {"count": 2, "pct": 20.0},
        "pathways": {"count": 1, "pct": 10.0},
        "step_free": {"count": 1, "pct": 10.0},
        "translations": {"count": 2, "pct": 25.0, "measured_feed_record_count": 8},
        "translations_sample": [],
        "flex_sample": [],
        "states": [],
    }
    coverage = {
        "feed_record_count": 10,
        "comparison_eligible_count": 10,
        "comparison": {"eligible_count": 10},
        "measured_feed_record_count": 10,
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
    # Ranked percentages use the shared semantic route-bar grammar; the exact
    # table remains available as the detail layer.
    assert 'class="service-chart adoption-chart"' in html
    assert 'class="service-bars"' in html
    assert "6 of 10 measured feeds" in html
    assert "2 of 8 measured feeds" in html
    assert "Build a feature shortlist" in html
    assert "Show the table" in html
    assert 'class="service-chart access-coverage-chart"' in html
    assert "5 of 10 feeds" in html
    assert html.index("Fare data (any model)") < html.index("Flexible (demand-responsive) service")


def test_adoption_page_renders_collapsed_worldwide_rollups_and_isolated_samples() -> None:
    from scorecard_pipeline.render_site import _render_adoption_page

    adoption = {
        "feed_record_count": 2,
        "comparison_eligible_count": 2,
        "comparison": {"eligible_count": 2},
        "measured_feed_record_count": 2,
        "agency_count": 2,
        "flex": {"count": 1, "pct": 50.0},
        "fares": {"count": 1, "pct": 50.0},
        "fares_v2": {"count": 0, "pct": 0.0},
        "pathways": {"count": 0, "pct": 0.0},
        "step_free": {"count": 0, "pct": 0.0},
        "cemv": {"count": 0, "pct": 0.0},
        "flex_sample": [
            {
                "id": "example-gb",
                "name": "ناقل لندن",
                "country": "GB",
                "subdivision_code": "GB-ENG",
                "subdivision_name": "England",
            }
        ],
        "countries": [
            {
                "country_code": "GB",
                "country_name": "United Kingdom",
                "agencies": 1,
                "flex": 1,
                "fares": 1,
                "fares_v2": 0,
                "pathways": 0,
                "subdivisions": [
                    {
                        "subdivision_code": "GB-ENG",
                        "subdivision_name": "England",
                        "agencies": 1,
                        "flex": 1,
                        "fares": 1,
                        "fares_v2": 0,
                        "pathways": 0,
                    }
                ],
            },
            {
                "country_code": "US",
                "country_name": "United States",
                "agencies": 1,
                "flex": 0,
                "fares": 0,
                "fares_v2": 0,
                "pathways": 0,
                "subdivisions": [],
            },
        ],
        "states": [
            {
                "state": "Iowa",
                "agencies": 1,
                "flex": 0,
                "fares": 0,
                "fares_v2": 0,
                "pathways": 0,
            }
        ],
    }

    html = _render_adoption_page(adoption, {"agency_count": 0})

    assert "<bdi>United Kingdom</bdi>" in html
    assert "<bdi>England</bdi>" in html
    assert "Show 1 covered subdivision in <bdi>United Kingdom</bdi>" in html
    assert '<details class="subdivision-rollup">' in html
    assert '<a href="/agency/example-gb/"><bdi>ناقل لندن</bdi></a>' in html
    assert "<td><bdi>England, United Kingdom</bdi></td>" in html
    assert '<h2 class="section-title">United States by state</h2>' in html


def test_adoption_page_zero_comparison_suppresses_stale_aggregates_and_names() -> None:
    from scorecard_pipeline.render_site import _render_adoption_page

    stale = {
        "feed_record_count": 100,
        "comparison_eligible_count": 0,
        "comparison": {"eligible_count": 0},
        "measured_feed_record_count": 1,
        "agency_count": 1,
        "flex": {"count": 1, "pct": 100.0},
        "flex_sample": [{"id": "stale", "name": "Stale Transit"}],
    }
    html = _render_adoption_page(stale, {**stale, "average_boarding_pct": 100.0})
    assert html.count("unavailable until current-contract checks") >= 2
    assert "Stale Transit" not in html
    assert "100.0%" not in html
    assert "Most complete" not in html


def test_problem_page_visualizes_prevalence_without_hiding_fix_text() -> None:
    from scorecard_pipeline.render_site import _render_problems_page

    html = _render_problems_page(
        {
            "feed_record_count": 10,
            "comparison_eligible_count": 10,
            "comparison": {"eligible_count": 10},
            "comparison_feed_record_count": 10,
            "total_agencies": 10,
            "problems": [
                {
                    "code": "expired_calendar",
                    "what": "Some service calendars have expired.",
                    "why": "Trips can disappear.",
                    "fix": "Extend the calendar.",
                    "severity": "WARNING",
                    "prevalence_pct": 70.0,
                    "agencies": 7,
                    "instances": 14,
                }
            ],
        }
    )
    assert 'class="service-chart problems-chart"' in html
    assert 'style="--value:70"' in html
    assert "70%" in html and "7 feed records" in html
    assert "Expired service calendars" in html
    assert "Typical finding:" in html
    assert "Some service calendars have expired." in html
    assert "Trips can disappear." in html
    assert "Extend the calendar." in html


def test_problem_page_zero_comparison_is_unavailable_not_clean() -> None:
    from scorecard_pipeline.render_site import _render_problems_page

    html = _render_problems_page(
        {
            "feed_record_count": 100,
            "comparison_eligible_count": 0,
            "comparison": {"eligible_count": 0},
            "comparison_feed_record_count": 1,
            "total_agencies": 1,
            "problems": [
                {
                    "code": "stale_problem",
                    "prevalence_pct": 100.0,
                    "feed_records": 1,
                }
            ],
        }
    )
    assert "unavailable until current-contract checks" in html
    assert "no clean-corpus" in html
    assert "stale_problem" not in html
    assert "No findings have been aggregated" not in html


def test_ridership_impact_line_states_coverage_and_never_ranks() -> None:
    from scorecard_pipeline.render_site import _ridership_impact_line

    impact = {
        "matched_agencies": 120,
        "total_agencies": 1400,
        "matched_ntd_reporters": 120,
        "total_feed_records": 1400,
        "duplicate_feed_records_excluded": 38,
        "total_annual_trips": 250_000_000,
        "expired_trips_pct": 7.5,
    }
    line = _ridership_impact_line(impact)
    assert "250,000,000" in line
    assert "120 matches across 1400" in line  # coverage is always stated
    assert "38 feed records" in line
    assert "double-counted" in line
    assert "7.5%" in line
    # Absent or empty data renders nothing rather than a fabricated number.
    assert _ridership_impact_line(None) == ""
    assert _ridership_impact_line({"matched_agencies": 0}) == ""


def test_change_snapshot_cleanup_keeps_only_auditable_contracts(tmp_path: Path) -> None:
    from scorecard_pipeline.render_site import _prune_unverifiable_change_snapshots

    invalid = tmp_path / "2026-06-20.json"
    invalid.write_text('{"count": 1, "changes": [{"id": "legacy"}]}\n')
    valid = tmp_path / "2026-07-14.json"
    valid.write_text(
        json.dumps(
            {
                "count": 0,
                "changes": [],
                "comparison_eligible_count": 0,
                "comparison": {
                    "eligible_count": 0,
                    "required_rubric_version": "1.2",
                    "required_scoring_profile_id": "gtfs-scorecard-1.2",
                    "required_validator_version": "8.0.1",
                    "required_reader_archive_profile": "raw-v1",
                    "required_measured_categories": [],
                },
            }
        )
    )

    _prune_unverifiable_change_snapshots(tmp_path)

    assert not invalid.exists()
    assert valid.exists()


def test_press_page_guards_the_no_shaming_line() -> None:
    from scorecard_pipeline.render_site import _render_press_page

    html = _render_press_page()
    assert "Claims the data supports" in html
    assert "Claims it does not support" in html
    assert "worst transit agency" in html  # the unfair claim is named and refused
    assert "not covered, never failing" in html.replace("\n      ", " ")
    assert "individual peer percentiles are not" in html.replace("\n      ", " ")
    assert "per-agency pages show peer percentiles" not in html
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
    title = html.split("<title>", 1)[1].split("</title>", 1)[0]
    description = html.split('<meta name="description" content="', 1)[1].split('">', 1)[0]
    assert title == "Demo Transit GTFS quality report"
    assert "grade" not in title.lower()
    assert len(title) <= 60
    assert len(description) <= 155
    assert "realtime quality" not in description
    assert 'itemtype="https://schema.org/BreadcrumbList"' in html
    assert '"license":"https://creativecommons.org/licenses/by/4.0/"' in html
    assert '"isBasedOn":"https://ex.org/g.zip"' in html
    assert html.index('id="fixes-h"') < html.index('id="rider-impact"') < html.index('id="cats-h"')


def test_agency_page_title_truncates_long_names_and_uses_state() -> None:
    import datetime as dt
    from pathlib import Path

    from scorecard_pipeline.config import Agency
    from scorecard_pipeline.fetch import FetchResult
    from scorecard_pipeline.metrics import CategoryResult
    from scorecard_pipeline.publish import build_artifact
    from scorecard_pipeline.render_site import _render_agency
    from scorecard_pipeline.score import build_scorecard

    agency = Agency(
        id="long-name",
        name="A Very Long Regional Transportation Authority and Municipal Transit District",
        static_gtfs_url="https://ex.org/long.zip",
    )
    fetch = FetchResult(
        agency_id=agency.id,
        path=Path("/tmp/long.zip"),
        url=agency.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256="abc",
        size_bytes=1,
        reused=False,
        source="origin",
    )
    card = build_scorecard([CategoryResult(name="correctness", score=90.0, summary="s")])
    artifact = build_artifact(agency, fetch, card, dt.datetime(2026, 6, 11, tzinfo=dt.UTC))
    html = _render_agency(artifact, dir_record={"state": "California"})
    title = html.split("<title>", 1)[1].split("</title>", 1)[0]

    assert len(title) <= 60
    assert "(California) GTFS quality report" in title
    assert "…" in title


def test_agency_metadata_planner_disambiguates_truncated_feed_variants() -> None:
    from scorecard_pipeline.config import Agency
    from scorecard_pipeline.render_site import _plan_agency_seo_metadata

    shared_prefix = "A Very Long Regional Transportation Authority and Municipal Transit "
    records = [
        {
            "id": "demo-bus",
            "name": f"{shared_prefix}Bus Network",
            "country": "US",
            "subdivision_name": "California",
        },
        {
            "id": "demo-rail",
            "name": f"{shared_prefix}Rail Network",
            "country": "US",
            "subdivision_name": "California",
        },
    ]
    artifacts = {
        record["id"]: {"categories": {"realtime": {"status": "not_yet_measured"}}}
        for record in records
    }
    registry = {
        "demo-bus": Agency(
            "demo-bus",
            records[0]["name"],
            "https://example.com/bus.zip",
            feed_variant="Bus",
        ),
        "demo-rail": Agency(
            "demo-rail",
            records[1]["name"],
            "https://example.com/rail.zip",
            feed_variant="Rail",
        ),
    }

    planned = _plan_agency_seo_metadata(records, artifacts, registry)

    assert "[Bus]" in planned["demo-bus"].title
    assert "[Rail]" in planned["demo-rail"].title
    assert len({item.title for item in planned.values()}) == 2
    assert len({item.description for item in planned.values()}) == 2
    assert len({item.dataset_name for item in planned.values()}) == 2
    assert all(len(item.title) <= 60 for item in planned.values())
    assert all(len(item.description) <= 155 for item in planned.values())


def test_agency_metadata_bounds_long_subdivision_labels() -> None:
    from scorecard_pipeline.render_site import _agency_seo_metadata

    metadata = _agency_seo_metadata(
        "Cardiff Bus (Bws Caerdydd)",
        location_label="Cardiff [Caerdydd GB-CRD], United Kingdom",
        rt_measured=True,
    )

    assert len(metadata.title) <= 60
    assert "(United Kingdom) GTFS quality report" in metadata.title
    assert len(metadata.description) <= 155
    assert "United Kingdom" in metadata.description


def test_registry_name_overlay_changes_current_index_only() -> None:
    from scorecard_pipeline.config import Agency
    from scorecard_pipeline.render_site import _apply_registry_agency_names

    index = {
        "agencies": {
            "demo": {
                "name": "Stale Export Name",
                "history": [{"date": "2026-07-28", "score": 80, "grade": "B"}],
            }
        }
    }
    history = index["agencies"]["demo"]["history"]
    registry = {
        "demo": Agency(
            "demo",
            "Curated Demo Transit",
            "https://example.com/demo.zip",
        )
    }

    assert _apply_registry_agency_names(index, registry) is True
    assert index["agencies"]["demo"]["name"] == "Curated Demo Transit"
    assert index["agencies"]["demo"]["history"] is history
    assert _apply_registry_agency_names(index, registry) is False


def test_non_us_agency_title_and_peer_context_include_country() -> None:
    from scorecard_pipeline.render_site import _peer_context, _render_agency

    artifact = _board_artifact()
    record = {
        "country": "GB",
        "subdivision_code": "GB-ENG",
        "subdivision_name": "England",
        "national_percentile": 60,
        "peer_percentile": 55,
        "size_tier": "small",
    }
    html = _render_agency(artifact, dir_record=record)
    title = html.split("<title>", 1)[1].split("</title>", 1)[0]

    assert "(England, United Kingdom) GTFS quality report" in title
    assert "Catalogued in <bdi>England, United Kingdom</bdi>." in _peer_context(record)
    assert "60%" not in _peer_context(record) and "55%" not in _peer_context(record)
    assert "Comparisons use agencies currently tracked worldwide." not in html
    assert "United States tools" not in html
    assert 'href="/ntd/"' not in html
    assert "NTD GTFS readiness" not in html
    assert "FTA National Transit Database GTFS requirement" not in html


def test_old_canadian_artifact_uses_directory_country_for_country_body_sections() -> None:
    from scorecard_pipeline.render_site import _render_agency

    artifact = _board_artifact()
    artifact["canada_equity"] = {"need_tier": "high"}

    html = _render_agency(
        artifact,
        dir_record={
            "country": "CA",
            "subdivision_code": "CA-ON",
            "subdivision_name": "Ontario",
        },
    )

    assert "Who this service reaches" in html
    assert "within-Canada measure" in html
    assert "NTD GTFS readiness" not in html
    assert "FTA National Transit Database GTFS requirement" not in html
    assert "United States tools" not in html


def test_us_agency_keeps_us_policy_tools_in_footer() -> None:
    from scorecard_pipeline.render_site import _render_agency

    artifact = _board_artifact()
    artifact["agency"]["country"] = "US"
    html = _render_agency(artifact, dir_record={"country": "US", "state": "California"})

    assert "United States tools" in html
    assert 'href="/ntd/"' in html and 'href="/equity/"' in html


def test_agency_fix_points_name_the_category_scale() -> None:
    from scorecard_pipeline.render_site import _render_agency

    artifact = _board_artifact()
    artifact["top_fixes"][0]["points"] = 17.4

    html = _render_agency(artifact)

    assert '<span class="aworth">worth about +17 points in its category</span>' in html


def test_sitemap_deduplicates_urls_and_adds_known_lastmod() -> None:
    from scorecard_pipeline.render_site import _sitemap

    xml = _sitemap(
        [
            "https://gtfsscorecard.org/x/",
            "https://gtfsscorecard.org/x/",
            "https://gtfsscorecard.org/y/",
        ],
        {"https://gtfsscorecard.org/x/": "2026-07-09"},
    )

    assert xml.count("https://gtfsscorecard.org/x/") == 1
    assert "<lastmod>2026-07-09</lastmod>" in xml
    assert "<lastmod>" not in xml.split("https://gtfsscorecard.org/y/", 1)[1]


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
    # (2) "Make the change": the tool-specific fix path (Trillium, hosted). A
    # legacy artifact URL is deliberately ignored; the service does not publish
    # modified agency feeds.
    assert "Make the change." in html
    assert "Trillium" in html
    assert "https://cdn.example.com/demo/corrected.zip" not in html
    assert "Download the corrected feed for this fix" not in html
    # (3) Check the result: comparable feed state and the clearance-log link.
    assert "Check the result." in html
    assert "clearance log records that result" in html
    assert 'href="/agency/demo/fixes/"' in html
    # The explicit causal boundary copy.
    assert "Only an action or ticket record can attribute" in html
    assert "not who made the change" in html


def test_autofix_section_ignores_legacy_public_download_url() -> None:
    from scorecard_pipeline.render_site import _autofix_section

    html = _autofix_section(_guided_flow_artifact())

    assert "https://cdn.example.com/demo/corrected.zip" not in html
    assert "Download corrected feed" not in html
    assert "Safe fixes you can run locally" in html
    assert "scorecard autofix &lt;feed.zip&gt; --out corrected.zip" in html
    assert "does not publish a modified feed" in html


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

    html = _render_fix(
        "expired_calendar",
        _authored_markdown("# Fix expired calendars\n\nRe-export the feed.\n"),
    )
    assert "After you republish" in html
    assert "dated finding clearance" in html
    assert "not who changed the feed or why" in html
    assert '<a class="backlink" href="/fix/">' in html
    assert '"author":{"@type":"Organization","name":"GTFS Scorecard"' in html
    articles = _jsonld_documents(html)
    assert len(articles) == 1
    _assert_tech_article_identity(
        articles[0],
        "https://gtfsscorecard.org/fix/expired_calendar/",
    )
    assert articles[0]["about"] == {
        "@type": "Thing",
        "name": "GTFS validator notice expired_calendar",
    }
    assert articles[0]["datePublished"] == "2026-07-03"
    assert articles[0]["dateModified"] == "2026-07-08"
    assert '<time datetime="2026-07-03">3 July 2026</time>' in html
    assert '<time datetime="2026-07-08">8 July 2026</time>' in html


@pytest.mark.parametrize(
    ("code", "expected_name"),
    [
        ("expired_calendar", "GTFS validator notice expired_calendar"),
        (
            "scorecard_missing_feed_info_dates",
            "GTFS validator notice missing_feed_info_date",
        ),
        (
            "scorecard_feed_expired",
            "GTFS data-quality finding scorecard_feed_expired",
        ),
    ],
)
def test_fix_guide_about_matches_finding_provenance(code: str, expected_name: str) -> None:
    from scorecard_pipeline.render_site import _render_fix

    html = _render_fix(code, _authored_markdown(f"# Fix {code}\n\nDo the next step.\n"))
    (article,) = _jsonld_documents(html)

    assert article["about"] == {"@type": "Thing", "name": expected_name}


def test_tech_article_helper_has_stable_identity_without_inventing_dates() -> None:
    from scorecard_pipeline.render_site import _tech_article_jsonld

    about = {"@type": "Thing", "name": "GTFS service calendars"}
    article = _tech_article_jsonld(
        headline="Fix a GTFS service calendar",
        description="How to repair an expired service calendar.",
        canonical="https://gtfsscorecard.org/fix/example/",
        about=about,
    )

    _assert_tech_article_identity(
        article,
        "https://gtfsscorecard.org/fix/example/",
    )
    assert article["about"] == about
    assert "datePublished" not in article
    assert "dateModified" not in article

    without_about = _tech_article_jsonld(
        headline="Article",
        description="Description",
        canonical="https://gtfsscorecard.org/article/",
    )
    assert "about" not in without_about


def test_fix_guide_description_skips_the_validator_code_line() -> None:
    from scorecard_pipeline.render_site import _render_fix

    html = _render_fix(
        "expired_calendar",
        _authored_markdown(
            "# Fix expired calendars\n\n"
            "Code: `expired_calendar` (MobilityData validator)\n\n"
            "## What this means\n\n"
            "The service calendar ended in the past, so the feed may stop showing trips.\n"
        ),
    )

    description = html.split('<meta name="description" content="', 1)[1].split('">', 1)[0]
    assert description.startswith("The service calendar ended")
    assert "Code:" not in description


def test_fix_guide_description_fallback_is_provenance_neutral() -> None:
    from scorecard_pipeline.render_site import _fix_description

    assert _fix_description("<h1>Fix an unnamed issue</h1>", "scorecard_example") == (
        "What the GTFS data-quality finding scorecard_example means and how to fix it."
    )


def test_md_to_html_renders_a_table() -> None:
    from scorecard_pipeline.render_site import _md_to_html

    md = "# Title\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\nAfter.\n"
    html, title = _md_to_html(md)
    compact = re.sub(r"\s+", "", html)
    assert title == "Title"
    assert '<table class="leaderboard">' in html
    assert "<thead><tr><th>A</th><th>B</th></tr></thead>" in compact
    assert "<tr><td>1</td><td>2</td></tr>" in compact
    assert "<tr><td>3</td><td>4</td></tr>" in compact
    assert "</tbody></table>" in compact
    # The paragraph after the table still renders, so the table doesn't eat
    # the rest of the document.
    assert "<p>After.</p>" in html


def test_md_to_html_renders_h3_as_a_section_subtitle() -> None:
    from scorecard_pipeline.render_site import _md_to_html

    html, _ = _md_to_html("## Section\n\n### Subsection\n\nBody.\n")
    assert '<h3 class="section-subtitle">Subsection</h3>' in html


def test_md_to_html_table_at_end_of_document_closes_cleanly() -> None:
    from scorecard_pipeline.render_site import _md_to_html

    html, _ = _md_to_html("# T\n\n| A |\n|---|\n| 1 |\n")
    assert html.endswith("</table>")


def test_md_to_html_preserves_wrapped_paragraphs_and_list_continuations() -> None:
    from scorecard_pipeline.render_site import _md_to_html

    html, _ = _md_to_html(
        "# T\n\nA paragraph that wraps\nonto another source line.\n\n"
        "- A list item that wraps\n  onto its continuation.\n"
    )

    assert "<p>A paragraph that wraps\nonto another source line.</p>" in html
    assert "<li>A list item that wraps\nonto its continuation.</li>" in html


def test_parse_authored_markdown_strips_dates_and_preserves_body_rules() -> None:
    from scorecard_pipeline.render_site import _md_to_html, _parse_authored_markdown

    document = _parse_authored_markdown(
        "---\r\n"
        "date_published: 2026-07-03\r\n"
        'date_modified: "2026-07-14"\r\n'
        "---\r\n"
        "# Authored title\r\n\r\nFirst explanation.\r\n\r\n---\r\n",
        "example.md",
    )

    assert document.date_published == "2026-07-03"
    assert document.date_modified == "2026-07-14"
    assert document.body.startswith("# Authored title")
    html, title = _md_to_html(document.body)
    assert title == "Authored title"
    assert "<hr" in html
    assert "date_published" not in html
    assert "date_modified" not in html


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "# No front matter\n",
            "must start with YAML front matter",
        ),
        (
            "---\ndate_published: 2026-07-03\ndate_modified: 2026-07-14\n",
            "no exact closing delimiter",
        ),
        (
            "---\ndate_published: 2026-07-03\n---\n# Missing modified\n",
            "missing authored front matter keys",
        ),
        (
            "---\n- 2026-07-03\n- 2026-07-14\n---\n# Sequence\n",
            "must be a mapping",
        ),
        (
            "---\n!!bool date_published: 2026-07-03\n"
            "date_modified: 2026-07-14\n---\n# Tagged key\n",
            "front matter keys must be strings",
        ),
        (
            "---\ndate_published: true\ndate_modified: 2026-07-14\n---\n# Boolean\n",
            "date_published must use YYYY-MM-DD",
        ),
        (
            '---\ndate_published: "2026-02-30"\ndate_modified: 2026-07-14\n---\n# Bad date\n',
            "date_published is not a valid calendar date",
        ),
        (
            "---\ndate_published: 2026-07-03T10:30:00Z\ndate_modified: 2026-07-14\n"
            "---\n# Timestamp\n",
            "date_published must be an ISO date, not a timestamp",
        ),
        (
            "---\ndate_published: 2026-07-14\ndate_modified: 2026-07-03\n---\n# Reversed\n",
            "date_modified cannot be before date_published",
        ),
        (
            "---\ndate_published: 2026-07-03\ndate_published: 2026-07-04\n"
            "date_modified: 2026-07-14\n---\n# Duplicate\n",
            "duplicate authored front matter key",
        ),
        (
            "---\ndate_published: 2026-07-03\ndate_modified: 2026-07-14\n"
            "reviewer: Transit team\n---\n# Unknown\n",
            "unknown authored front matter keys",
        ),
    ],
)
def test_parse_authored_markdown_rejects_invalid_metadata(text: str, message: str) -> None:
    from scorecard_pipeline.render_site import _parse_authored_markdown

    with pytest.raises(ValueError, match=message) as exc_info:
        _parse_authored_markdown(text, "example.md")
    assert "example.md" in str(exc_info.value)


def test_fix_index_groups_guides_and_publishes_collection_schema() -> None:
    from scorecard_pipeline.render_site import _render_fix_index

    html = _render_fix_index(
        [
            {
                "code": "expired_calendar",
                "title": "Fix expired calendars",
                "description": "Remove service periods that already ended.",
                "category": "Service dates and freshness",
            }
        ]
    )

    assert "GTFS errors and fixes" in html
    assert 'href="/fix/expired_calendar/"' in html
    assert "Finding code: expired_calendar" in html
    assert "Validator rule:" not in html
    assert (
        '<meta name="description" content="Plain-language guides for common GTFS findings,' in html
    )
    (metadata,) = _jsonld_documents(html)
    assert metadata["description"] == "Plain-language guides for common GTFS findings."
    assert '"@type":"CollectionPage"' in html


def test_render_crosswalk_page_links_the_authoritative_sources() -> None:
    from scorecard_pipeline.render_site import _render_crosswalk_page

    document = _authored_markdown(
        "# How the grade maps to the standards\n\n"
        "This crosswalk explains the mapping.\n\n"
        "## The standards\n\n"
        "- [NTD](https://www.transit.dot.gov/ntd)\n",
        date_modified="2026-07-14",
    )
    html = _render_crosswalk_page(document)
    assert "/crosswalk/" in html
    assert "How the grade maps to the standards" in html
    assert 'href="https://www.transit.dot.gov/ntd"' in html
    articles = _jsonld_documents(html)
    assert len(articles) == 1
    _assert_tech_article_identity(
        articles[0],
        "https://gtfsscorecard.org/crosswalk/",
    )
    assert "about" not in articles[0]
    assert articles[0]["datePublished"] == "2026-07-03"
    assert articles[0]["dateModified"] == "2026-07-14"
    assert '<time datetime="2026-07-03">3 July 2026</time>' in html
    assert '<time datetime="2026-07-14">14 July 2026</time>' in html
    assert "date_published" not in html
    assert "date_modified" not in html


def test_fixlog_page_frames_clearances_as_feed_state_not_causal_proof() -> None:
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
    assert "comparable-feed check in the guided change flow" in html
    assert "who acted, why the feed changed" in html
    assert "Pair a" in html and "owner or vendor's action record" in html
    assert "NTD narrative" not in html
    assert 'href="/agency/demo/"' in html


def test_staleness_distribution_buckets_by_snapshot_age() -> None:
    import datetime as dt

    from scorecard_pipeline.render_site import _staleness_distribution

    now = dt.datetime(2026, 7, 8, 12, 0, tzinfo=dt.UTC)
    catalog: list[dict[str, Any]] = [
        {"id": "a", "retrieved_at": (now - dt.timedelta(hours=2)).isoformat()},
        {"id": "b", "retrieved_at": (now - dt.timedelta(days=1, hours=12)).isoformat()},
        {"id": "c", "retrieved_at": (now - dt.timedelta(days=5)).isoformat()},
        {"id": "d", "retrieved_at": (now - dt.timedelta(days=10)).isoformat()},
        {"id": "e", "retrieved_at": None},
        {"id": "f"},
    ]
    dist = dict(_staleness_distribution(catalog, now))
    assert dist["under 1 day"] == 1
    assert dist["1-2 days"] == 1
    assert dist["3-7 days"] == 1
    assert dist["over 7 days"] == 1
    assert dist["unknown"] == 2


def test_staleness_distribution_empty_catalog() -> None:
    import datetime as dt

    from scorecard_pipeline.render_site import _staleness_distribution

    now = dt.datetime(2026, 7, 8, tzinfo=dt.UTC)
    empty_catalog: list[dict[str, Any]] = []
    dist = _staleness_distribution(empty_catalog, now)
    assert all(count == 0 for _, count in dist)
    assert "unknown" not in dict(dist)


def test_status_page_with_no_run_summary_says_not_published_yet() -> None:
    import datetime as dt

    from scorecard_pipeline.render_site import _status_evidence_section

    html = _status_evidence_section(None, [], dt.datetime(2026, 7, 8, tzinfo=dt.UTC))
    assert "No run-health summary has been published yet" in html
    assert "Latest full scoring run" in html


def test_status_commitment_labels_current_liveness_and_explains_mirror_difference() -> None:
    import datetime as dt

    from scorecard_pipeline.metrics import UNREACHABLE_STREAK_CHECKS
    from scorecard_pipeline.render_site import _status_commitment_section
    from scorecard_pipeline.status_commitment import build_status_commitment

    now = dt.datetime(2026, 7, 8, 14, 0, tzinfo=dt.UTC)
    doc = build_status_commitment(
        {
            "clean": {
                "checked_at": "2026-07-08T13:00:00+00:00",
                "consecutive_failures": 0,
            },
            "recent-failure": {
                "checked_at": "2026-07-08T12:00:00+00:00",
                "consecutive_failures": 2,
            },
            "unreachable": {
                "checked_at": "2026-07-08T11:00:00+00:00",
                "consecutive_failures": UNREACHABLE_STREAK_CHECKS,
            },
        },
        now,
        "https://gtfsscorecard.org",
    )

    html = _status_commitment_section(doc)

    assert "Current feed URL liveness" in html
    assert "Currently checking clean: <strong>33.3%</strong>" in html
    assert "Overall clean-check rate" not in html
    assert "without a mirror" in html
    assert "daily full scoring run can use the Mobility Database mirror" in html
    assert '<time datetime="2026-07-08T14:00:00+00:00">2026-07-08 14:00 UTC</time>' in html


def test_status_page_healthy_run_shows_counts_and_no_degraded_banner() -> None:
    import datetime as dt

    from scorecard_pipeline.render_site import _status_evidence_section

    now = dt.datetime(2026, 7, 8, 14, 0, tzinfo=dt.UTC)
    run_summary = {
        "generated_at": "2026-07-08T13:30:00+00:00",
        "shard_count": 2,
        "agency_count": 100,
        "scored": 95,
        "reused": 5,
        "unreachable": 0,
        "mirrored": 1,
        "cache_hit": 40,
        "unreachable_agencies": [],
        "degraded": False,
        "degraded_threshold": 0.05,
        "shards": [
            {
                "shard": "0",
                "scored": 50,
                "reused": 2,
                "unreachable": 0,
                "mirrored": 1,
                "cache_hit": 20,
                "wall_clock_seconds": 120.0,
            },
        ],
    }
    catalog = [{"id": "unitrans", "name": "Unitrans", "retrieved_at": "2026-07-08T13:00:00+00:00"}]
    html = _status_evidence_section(run_summary, catalog, now)
    assert "Run completed" in html
    assert "Healthy" not in html
    assert "warning threshold" not in html
    assert ">95<" in html  # scored count
    assert "No currently published feed record was unreachable" in html
    assert 'class="bucket-chart staleness-chart"' in html
    assert "Snapshot age distribution" in html
    assert "All 1 tracked feed scorecards" in html
    assert 'aria-label="1 feed scorecard, under 1 day"' in html
    assert "Show per-shard breakdown" in html
    assert "Show snapshot-age table" in html


def test_status_page_degraded_run_names_unreachable_agencies() -> None:
    import datetime as dt

    from scorecard_pipeline.render_site import _status_evidence_section

    now = dt.datetime(2026, 7, 8, 14, 0, tzinfo=dt.UTC)
    run_summary = {
        "generated_at": "2026-07-08T13:30:00+00:00",
        "shard_count": 1,
        "agency_count": 10,
        "scored": 5,
        "reused": 0,
        "unreachable": 5,
        "mirrored": 0,
        "cache_hit": 0,
        "unreachable_agencies": ["unitrans"],
        "degraded": True,
        "degraded_threshold": 0.05,
        "shards": [],
    }
    catalog = [{"id": "unitrans", "name": "Unitrans"}]
    html = _status_evidence_section(run_summary, catalog, now)
    assert "Run completed with warnings" in html
    assert "exceeded the warning threshold" in html
    assert 'href="/agency/unitrans/"' in html
    assert "Unitrans" in html


def test_run_status_scopes_names_to_current_catalog_without_rewriting_history() -> None:
    from scorecard_pipeline.render_site import _scope_run_summary, _status_evidence_section

    run_summary = {
        "generated_at": "2026-07-08T13:30:00+00:00",
        "shard_count": 1,
        "agency_count": 10,
        "scored": 5,
        "reused": 0,
        "unreachable": 2,
        "mirrored": 0,
        "cache_hit": 0,
        "unreachable_agencies": ["unitrans", "removed-feed"],
        "degraded": True,
        "degraded_threshold": 0.05,
        "shards": [
            {
                "shard": "0",
                "unreachable": 2,
                "unreachable_agencies": ["unitrans", "removed-from-shard"],
            }
        ],
    }
    catalog = [{"id": "unitrans", "name": "Unitrans"}]

    scoped = _scope_run_summary(run_summary, catalog)
    assert scoped is not None
    assert scoped["unreachable"] == 2
    assert scoped["unreachable_agencies"] == ["unitrans"]
    assert scoped["unreachable_outside_current_published_set"] == 1
    assert scoped["published_feed_record_count"] == 1
    assert scoped["shards"][0]["unreachable"] == 2
    assert scoped["shards"][0]["unreachable_agencies"] == ["unitrans"]
    assert scoped["shards"][0]["unreachable_outside_current_published_set"] == 1

    def _all_named_unreachable(value: object) -> set[str]:
        if isinstance(value, dict):
            names = set(value.get("unreachable_agencies", []))
            return names.union(*(_all_named_unreachable(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(_all_named_unreachable(item) for item in value))
        return set()

    assert _all_named_unreachable(scoped) <= {"unitrans"}
    html = _status_evidence_section(scoped, catalog, dt.datetime(2026, 7, 8, tzinfo=dt.UTC))
    assert 'href="/agency/unitrans/"' in html
    assert "removed-feed" not in html
    assert "1 additional record was part of this run's attempted set" in html


def test_render_status_combines_commitment_and_evidence_sections() -> None:
    """The one /status/ page composes EXP-10's commitment section ("what we
    commit to") and FIX-11's latest-run-evidence section --
    they used to render to the same URL from two separate functions, each
    silently clobbering the other's file on disk (see _render_status's
    docstring). Both machine-readable twins must stay cross-linked."""
    import datetime as dt

    from scorecard_pipeline.render_site import _render_status
    from scorecard_pipeline.status_commitment import build_status_commitment

    now = dt.datetime(2026, 7, 8, 14, 0, tzinfo=dt.UTC)
    status_doc = build_status_commitment({}, now, "https://gtfsscorecard.org")
    run_summary = {
        "generated_at": "2026-07-08T13:30:00+00:00",
        "shard_count": 1,
        "agency_count": 10,
        "scored": 10,
        "reused": 0,
        "unreachable": 0,
        "mirrored": 0,
        "cache_hit": 0,
        "unreachable_agencies": [],
        "degraded": False,
        "degraded_threshold": 0.05,
        "shards": [],
    }
    catalog = [{"id": "unitrans", "name": "Unitrans", "retrieved_at": "2026-07-08T13:00:00+00:00"}]
    global_coverage = {
        "status": "not_ready",
        "ready": False,
        "cohort": {"feed_record_count": 6, "country_count": 3},
        "criteria": [
            {
                "key": "reviewed_feed_records",
                "label": "Reviewed European GTFS Schedule feed records",
                "actual": 6,
                "threshold": 250,
                "operator": ">=",
                "unit": "feed_records",
                "met": False,
            },
            {
                "key": "translations_measured",
                "label": "Translation publication measured",
                "actual": 100.0,
                "threshold": 100.0,
                "operator": ">=",
                "unit": "percent",
                "met": True,
            },
        ],
        "exceptions": [
            {
                "key": "stale_scorecard",
                "label": "Scorecard is older than the seven-day freshness window",
                "count": 2,
                "feed_record_ids": ["one", "two"],
            }
        ],
    }
    html = _render_status(status_doc, run_summary, catalog, now, global_coverage)
    # The commitment half (EXP-10).
    assert "Service status" in html
    assert "Monitoring status and schedule" in html
    assert "Current feed URL liveness" in html
    assert "Scheduled checks" in html
    assert "When a check fails" in html
    assert 'class="page-lede">"Refreshed daily"' not in html
    assert "Direct liveness checks and the mirror-assisted daily run" in html
    # The run-evidence half (FIX-11).
    assert "Latest full scoring run" in html
    assert "Show per-shard breakdown" in html
    assert "Catalog freshness" in html
    # The bounded Europe gate is the third section, with its status expressed
    # in text, current/threshold comparison, and exception counts.
    assert "European beta readiness" in html
    assert ">Not ready<" in html
    assert "6</strong> GTFS Schedule feed records across <strong>3</strong> countries" in html
    assert "Current European beta measures compared with release thresholds" in html
    assert "at least 250" in html
    assert "at least 100%" in html
    assert "Scorecard is older than the seven-day freshness window" in html
    assert "<td>2</td>" in html
    assert "not a claim\n    of coverage for all European public transport" in html
    assert "does not assess NeTEx coverage" in html
    # All three JSON documents stay cross-linked, and only one page-level title exists.
    assert 'href="/api/v1/status.json"' in html
    assert 'href="/api/v1/run-status.json"' in html
    assert 'href="/api/v1/global-coverage.json"' in html
    assert "docs/global-expansion.md" in html
    assert html.count("<h1") == 1


def test_feeddiff_section_shows_the_export_diff_block_first() -> None:
    from scorecard_pipeline.render_site import _feeddiff_section

    prev = _diff_artifact(date="2026-06-11", grade="B", score=82.0)
    cur = _diff_artifact(date="2026-06-12", grade="B", score=82.0, sha256="bbb")
    cur["export_diff"] = {
        "from_sha256": "aaa",
        "to_sha256": "bbb",
        "changes": ["Route 5 (E Street Express) is no longer in the export."],
    }
    html = _feeddiff_section(prev, cur, "acme")
    assert "What changed inside the export" in html
    assert "Route 5 (E Street Express) is no longer in the export." in html
    assert "this is a heads-up" in html


def test_feeddiff_section_omits_the_export_block_when_absent() -> None:
    from scorecard_pipeline.render_site import _feeddiff_section

    prev = _diff_artifact(date="2026-06-11", grade="B", score=82.0)
    cur = _diff_artifact(date="2026-06-12", grade="C", score=74.0, sha256="bbb")
    assert "What changed inside the export" not in _feeddiff_section(prev, cur, "acme")
