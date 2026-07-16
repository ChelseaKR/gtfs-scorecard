"""Route smoke tests: each hash route renders its real content into #main and
the boot spinner ("Loading scorecards…" in web/app/index.html, "Loading…" from
app.js's route()) never persists once a route has rendered."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

ARTIFACTS = Path(__file__).resolve().parents[3] / "data" / "artifacts"
AGENCY_ID = "abq-ride"  # a real committed agency: in index.json and data/artifacts/


def _agency_name(agency_id: str) -> str:
    artifact = json.loads((ARTIFACTS / agency_id / "latest.json").read_text())
    return str(artifact["agency"]["name"])


def _first_rollup() -> tuple[str, str]:
    index = json.loads((ARTIFACTS / "rollups" / "index.json").read_text())
    rollup = index["rollups"][0]
    return str(rollup["id"]), str(rollup["name"])


def _portable_directory() -> dict[str, Any]:
    """Current directory normalized into stable portable-location test cases."""
    directory = json.loads((ARTIFACTS / "directory.json").read_text())
    canadian = {
        "barrie-transit": ("CA-ON", "Ontario"),
        "london-transit-commission": ("CA-ON", "Ontario"),
    }
    california_count = 0
    for agency in directory["agencies"]:
        if agency["id"] in canadian:
            agency["subdivision_code"], agency["subdivision_name"] = canadian[agency["id"]]
        elif agency["id"] == "whitehorse-transit":
            # Keep one Canadian agency deliberately unlocated so the duplicate
            # UNLOCATED sentinel can be tested independently in two countries.
            agency["subdivision_code"] = None
            agency["subdivision_name"] = ""
        elif agency.get("country") == "US" and agency.get("state") == "California":
            agency["subdivision_code"] = "US-CA"
            agency["subdivision_name"] = "California"
            california_count += 1
    british = {
        **directory["agencies"][0],
        "id": "example-gb-transit",
        "name": "Example GB Transit",
        "country": "GB",
        "state": "",
        "subdivision_code": "GB-ENG",
        "subdivision_name": "England",
    }
    directory["agencies"].append(british)
    directory["summary"]["countries"] = [
        {
            "country_code": "US",
            "country_name": "United States",
            "agencies": sum(a.get("country") == "US" for a in directory["agencies"]),
            "subdivisions": [
                {
                    "subdivision_code": "US-CA",
                    "subdivision_name": "California",
                    "agencies": california_count,
                },
                {
                    "subdivision_code": None,
                    "subdivision_name": "Unlocated",
                    "agencies": sum(
                        a.get("country") == "US" and not a.get("subdivision_code")
                        for a in directory["agencies"]
                    ),
                },
            ],
        },
        {
            "country_code": "CA",
            "country_name": "Canada",
            "agencies": 3,
            "subdivisions": [
                {"subdivision_code": "CA-ON", "subdivision_name": "Ontario", "agencies": 2},
                {"subdivision_code": None, "subdivision_name": "Unlocated", "agencies": 1},
            ],
        },
        {
            "country_code": "GB",
            "country_name": "United Kingdom",
            "agencies": 1,
            "subdivisions": [
                {"subdivision_code": "GB-ENG", "subdivision_name": "England", "agencies": 1}
            ],
        },
        {
            "country_code": "XK",
            "country_name": 'Quoted "country" onmouseover="window.__pwned=1" <test>',
            "agencies": 0,
            "subdivisions": [],
        },
    ]
    return cast(dict[str, Any], directory)


def _feature_directory() -> dict[str, Any]:
    """Portable directory with a small, deterministic feature cohort."""
    directory = _portable_directory()
    feature_defaults = {
        "comparison_eligible": False,
        "capabilities_measured": False,
        "accessibility_measured": False,
        "has_accessibility": None,
        "wheelchair_boarding_pct": None,
        "wheelchair_accessible_pct": None,
        "accessibility_band": None,
        "has_flex": None,
        "has_fares": None,
        "has_fares_v2": None,
        "fare_model": None,
        "has_pathways": None,
        "has_step_free": None,
        "has_cemv": None,
        "translations_measured": False,
        "has_translations": None,
        "translation_count": None,
        "translation_languages": None,
        "translated_tables": None,
        "feed_lang": None,
        "modes_measured": False,
        "primary_mode": None,
        "modes": None,
        "has_ferry": None,
        "ferry_only": None,
    }
    for agency in directory["agencies"]:
        agency.update(feature_defaults)
        if agency["id"] == "barrie-transit":
            agency.update(
                {
                    "capabilities_measured": True,
                    "accessibility_measured": True,
                    "has_accessibility": True,
                    "wheelchair_boarding_pct": 100.0,
                    "wheelchair_accessible_pct": 96.0,
                    "accessibility_band": "most",
                    "has_flex": False,
                    "has_fares": True,
                    "has_fares_v2": True,
                    "fare_model": "v2",
                    "has_pathways": True,
                    "has_step_free": True,
                    "has_cemv": False,
                    "translations_measured": True,
                    "has_translations": True,
                    "translation_count": 12,
                    "translation_languages": ["fr", "nl"],
                    "translated_tables": ["routes", "stops"],
                    "feed_lang": "mul",
                    "modes_measured": True,
                    "primary_mode": "ferry",
                    "modes": ["bus", "ferry"],
                    "has_ferry": True,
                    "ferry_only": False,
                }
            )
        elif agency["id"] == "london-transit-commission":
            agency.update(
                {
                    "capabilities_measured": True,
                    "accessibility_measured": True,
                    "has_accessibility": True,
                    "wheelchair_boarding_pct": 80.0,
                    "wheelchair_accessible_pct": 40.0,
                    "accessibility_band": "some",
                    "has_flex": True,
                    "has_fares": True,
                    "has_fares_v2": False,
                    "fare_model": "legacy",
                    "has_pathways": False,
                    "has_step_free": False,
                    "has_cemv": False,
                    "translations_measured": True,
                    "has_translations": False,
                    "translation_count": 0,
                    "translation_languages": [],
                    "translated_tables": [],
                    "feed_lang": "en",
                    "modes_measured": True,
                    "primary_mode": "bus",
                    "modes": ["bus"],
                    "has_ferry": False,
                    "ferry_only": False,
                }
            )
    return directory


def _serve_directory(page: Page, directory: dict[str, Any]) -> None:
    page.route(
        "**/data/artifacts/directory.json",
        lambda route: route.fulfill(json=directory),
    )


def _hash_params(page: Page) -> dict[str, str]:
    return cast(
        dict[str, str],
        page.evaluate("() => Object.fromEntries(new URLSearchParams(location.hash.split('?')[1]))"),
    )


def _assert_not_stuck_loading(page: Page) -> None:
    """Both spinners render as role=status .loading inside #main; a finished
    route replaces main's innerHTML, so none may remain."""
    expect(page.locator("#main .loading")).to_have_count(0)
    expect(page.get_by_text("Loading scorecards…")).to_have_count(0)


def test_overview_route_renders_directory(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/")
    expect(page.locator("#main h1.page-title")).to_have_text("Find an agency scorecard.")
    expect(page.locator("#agency-search")).to_be_visible()
    _assert_not_stuck_loading(page)


def test_agency_route_renders_scorecard(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/agency/{AGENCY_ID}")
    expect(page.locator("h1.board-title")).to_have_text(_agency_name(AGENCY_ID))
    expect(page.locator("#fixes-h")).to_have_text("Top things to fix")
    expect(page.locator("#cats-h")).to_have_text("Score by category")
    expect(page.locator(".platforms .platform")).to_have_count(4)
    _assert_not_stuck_loading(page)


def test_ferry_scorecard_uses_mode_aware_language(page: Page, app_url: str) -> None:
    artifact = json.loads((ARTIFACTS / AGENCY_ID / "latest.json").read_text())
    artifact["mode_profile"] = {
        "measured": True,
        "graded": False,
        "primary_mode": "ferry",
        "is_multimodal": False,
        "has_ferry": True,
        "ferry_only": True,
        "modes": [{"key": "ferry", "label": "Ferry"}],
    }
    artifact["top_fixes"][0]["why"] = (
        "Even with accessible stops, riders need to know the bus itself can take them."
    )
    artifact["ferry_profile"] = {
        "measured": True,
        "graded": False,
        "route_count": 2,
        "trip_count": 80,
        "terminal_hierarchy": {
            "boarding_location_count": 4,
            "parented_boarding_location_count": 2,
            "referenced_station_count": 1,
        },
        "stop_access": {
            "eligible_terminal_count": 2,
            "stated_count": 1,
            "stated_pct": 50.0,
            "direct_count": 1,
            "through_station_count": 0,
        },
        "accessibility": {
            "terminals": {
                "total_count": 4,
                "stated_count": 2,
                "stated_pct": 50.0,
                "allowed_count": 2,
                "allowed_pct": 50.0,
            },
            "trips": {
                "total_count": 80,
                "stated_count": 40,
                "stated_pct": 50.0,
                "allowed_count": 40,
                "allowed_pct": 50.0,
            },
        },
        "bikes": {
            "total_count": 80,
            "stated_count": 60,
            "stated_pct": 75.0,
            "allowed_count": 50,
            "allowed_pct": 62.5,
        },
        "cars": {
            "total_count": 80,
            "stated_count": 0,
            "stated_pct": 0.0,
            "allowed_count": 0,
            "allowed_pct": 0.0,
        },
        "fares": {"fare_free": False, "model": "legacy", "applied": True},
        "realtime": {"configured_kinds": ["trip_updates", "service_alerts"]},
    }
    page.route(
        f"**/data/artifacts/{AGENCY_ID}/latest.json",
        lambda route: route.fulfill(json=artifact),
    )

    page.goto(f"{app_url}#/agency/{AGENCY_ID}")

    expect(page.locator(".board-mode")).to_have_text("Service mode Ferry")
    fixes = page.locator("section[aria-labelledby='fixes-h']")
    expect(fixes).to_contain_text("accessible terminals")
    expect(fixes).to_contain_text("vessel")
    expect(fixes).not_to_contain_text("bus itself")
    rider = page.locator("#rider-impact")
    expect(rider).to_contain_text("terminals")
    expect(rider).to_contain_text("vessels")
    mark = page.locator("section[aria-labelledby='mark-h']")
    expect(mark).to_contain_text("terminal")
    expect(mark).not_to_contain_text("nearly every stop")
    profile = page.locator("section[aria-labelledby='ferry-profile-h']")
    expect(profile).to_contain_text("Ungraded capability read")
    expect(profile).to_contain_text("2 routes · 80 trips")
    expect(profile).to_contain_text("50% of eligible child terminal locations")
    expect(profile).to_contain_text("Unknown: none of the 80 ferry trips publish cars_allowed")
    expect(profile).to_contain_text("Trip Updates, Service Alerts")


def test_agency_route_allowlists_hostile_artifact_severity(page: Page, app_url: str) -> None:
    artifact = json.loads((ARTIFACTS / AGENCY_ID / "latest.json").read_text())
    hostile = 'ERROR" onmouseover="window.__pwned=1'
    finding = artifact["categories"]["correctness"]["findings"][0]
    finding["severity"] = hostile
    finding["code"] = "hostile-severity-test"
    page.route(
        f"**/data/artifacts/{AGENCY_ID}/latest.json",
        lambda route: route.fulfill(json=artifact),
    )

    page.goto(f"{app_url}#/agency/{AGENCY_ID}")

    row = page.locator(".findings .finding").filter(has_text="hostile-severity-test")
    badge = row.locator(".sev")
    expect(badge).to_have_class("sev sev-info")
    expect(badge).to_have_text("Info")
    expect(page.locator("[onmouseover]")).to_have_count(0)
    assert hostile not in row.inner_html()
    assert page.evaluate("() => window.__pwned") is None


def test_agency_route_scopes_us_policy_footer_to_us_agencies(page: Page, app_url: str) -> None:
    ntd_link = page.locator('.site-footer a[href="/ntd/"]')
    legacy_ca = json.loads((ARTIFACTS / "barrie-transit" / "latest.json").read_text())
    legacy_ca["agency"].pop("country", None)
    page.route(
        "**/data/artifacts/barrie-transit/latest.json",
        lambda route: route.fulfill(json=legacy_ca),
    )

    page.goto(f"{app_url}#/agency/barrie-transit")
    expect(page.locator("h1.board-title")).to_have_text("Barrie Transit (Ontario)")
    expect(ntd_link).to_be_hidden()
    expect(page.locator("#ntd-h")).to_have_count(0)
    expect(page.get_by_text("FTA National Transit Database GTFS requirement")).to_have_count(0)

    page.goto(f"{app_url}#/agency/{AGENCY_ID}")
    expect(page.locator("h1.board-title")).to_have_text(_agency_name(AGENCY_ID))
    expect(ntd_link).to_be_visible()


def test_programs_route_lists_rollups(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/programs")
    expect(page.locator("#main h1.page-title")).to_have_text("Program rollups.")
    expect(page.locator(".agency-list .agency-card").first).to_be_visible()
    _assert_not_stuck_loading(page)


def test_program_route_renders_members(page: Page, app_url: str) -> None:
    rollup_id, rollup_name = _first_rollup()
    page.goto(f"{app_url}#/program/{rollup_id}")
    expect(page.locator("#main h1.page-title")).to_have_text(rollup_name)
    expect(page.locator("#members-h")).to_have_text(
        "Feed scorecards: attention first, then alphabetical"
    )
    expect(page.locator(".program-list .program-row").first).to_be_visible()
    _assert_not_stuck_loading(page)


def test_hash_navigation_reroutes_without_reload(page: Page, app_url: str) -> None:
    """The hashchange listener re-renders in place, both forward and back."""
    page.goto(f"{app_url}#/")
    expect(page.locator("#main h1.page-title")).to_have_text("Find an agency scorecard.")
    page.locator('#main a[href="#/programs"]').click()
    expect(page.locator("#main h1.page-title")).to_have_text("Program rollups.")
    page.go_back()
    expect(page.locator("#main h1.page-title")).to_have_text("Find an agency scorecard.")
    _assert_not_stuck_loading(page)


def test_not_found_route_has_a_page_heading(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/agency/not-a-real-agency")
    expect(page.locator("#main .error-box")).to_have_attribute("role", "alert")
    expect(page.locator("#main h1.page-title")).to_have_text(
        "No scorecard for “not-a-real-agency”."
    )
    _assert_not_stuck_loading(page)


def test_compare_defaults_to_distinct_agencies_and_rejects_duplicates(
    page: Page, app_url: str
) -> None:
    page.goto(f"{app_url}#/compare")
    first = page.locator("#cmp-a")
    second = page.locator("#cmp-b")
    expect(first).to_be_visible()
    a_id = first.input_value()
    b_id = second.input_value()
    assert a_id and b_id and a_id != b_id

    second.select_option(a_id)
    page.locator("#compare-pick button.compare-go").click()
    status = page.locator("#compare-pick-status")
    expect(status).to_be_visible()
    expect(status).to_have_text("Pick two different agencies to compare.")
    assert page.evaluate("() => document.activeElement.id") == "cmp-b"
    assert page.evaluate("() => location.hash") == "#/compare"


def test_empty_directory_state_recovers_to_search(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/")
    search = page.locator("#agency-search")
    search.fill("zzzz no matching agency")
    expect(page.locator(".agency-count")).to_contain_text("0 of")
    expect(page.locator(".agency-count")).to_contain_text("scorecards")
    expect(page.locator(".no-match")).to_be_visible()
    expect(page.locator("#agency-list .agency-card")).to_have_count(0)

    page.get_by_role("button", name="Clear filters").click()
    expect(search).to_have_value("")
    expect(page.locator(".results-hint")).to_be_visible()
    assert page.evaluate("() => document.activeElement.id") == "agency-search"


def test_portable_location_filters_urls_and_search(page: Page, app_url: str) -> None:
    _serve_directory(page, _portable_directory())
    page.goto(f"{app_url}#/?country=us&subdivision=ca-on")

    # The valid subdivision is authoritative even when the supplied country is
    # inconsistent, and the original bookmark is not rewritten on page load.
    expect(page.locator('.location-country[data-country="CA"]').first).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(page.locator('.location-subdivision[data-subdivision="CA-ON"]').first).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(page.locator(".agency-count")).to_contain_text("2 of")
    assert page.evaluate("() => location.hash") == "#/?country=us&subdivision=ca-on"

    # Any user change writes the canonical, upper-case portable keys while
    # preserving the other active controls.
    page.locator("#agency-sort").select_option("za")
    params = _hash_params(page)
    assert params == {"country": "CA", "subdivision": "CA-ON", "sort": "za"}

    page.locator('.location-subdivision[data-subdivision="CA-ON"]').first.click()
    page.locator('.location-country[data-country="CA"]').first.click()
    page.locator("#agency-search").fill("CA-ON")
    expect(page.locator(".agency-count")).to_contain_text("2 of")
    page.locator("#agency-search").fill("Ontario")
    expect(page.locator(".agency-count")).to_contain_text("2 of")

    # Quotes and angle brackets from the directory stay text; they cannot add
    # event-handler attributes to location controls.
    expect(
        page.get_by_role(
            "button", name='Quoted "country" onmouseover="window.__pwned=1" <test> 0'
        ).first
    ).to_be_visible()
    expect(page.locator("[onmouseover]")).to_have_count(0)
    assert page.evaluate("() => window.__pwned") is None


def test_feature_filters_thresholds_geography_and_csv_export(page: Page, app_url: str) -> None:
    directory = _feature_directory()
    _serve_directory(page, directory)
    page.goto(
        f"{app_url}#/?country=ca&subdivision=ca-on"
        "&features=accessibility,fares_v2&stops=95&trips=95"
    )

    expect(page.locator('input[value="accessibility"]')).to_be_checked()
    expect(page.locator('input[value="fares_v2"]')).to_be_checked()
    expect(page.locator("#wheelchair-stops-min")).to_have_value("95")
    expect(page.locator("#wheelchair-trips-min")).to_have_value("95")
    # Feature evidence remains filterable during a score-rubric rollout; every
    # synthetic row is deliberately ineligible for score comparison.
    expect(page.locator(".agency-count")).to_have_text(
        f"1 of {len(directory['agencies']):,} scorecard"
    )
    expect(page.get_by_role("link", name="Barrie Transit (Ontario)")).to_be_visible()
    expect(page.get_by_role("link", name="London Transit Commission")).to_have_count(0)
    expect(page.locator(".feature-evidence")).to_contain_text(
        "Accessibility: 100% stops, 96% trips · Fares v2"
    )
    expect(page.locator(".feature-match-board")).to_have_attribute("data-active", "true")
    expect(page.get_by_role("link", name="Open the feature API")).to_have_attribute(
        "href", "/api/v1/features.json"
    )

    # A user interaction canonicalizes the portable location keys while
    # retaining every feature condition in the shareable URL.
    page.locator("#agency-sort").select_option("za")
    assert _hash_params(page) == {
        "country": "CA",
        "subdivision": "CA-ON",
        "sort": "za",
        "features": "accessibility,fares_v2",
        "view": "features",
        "stops": "95",
        "trips": "95",
    }

    with page.expect_download() as download_info:
        page.get_by_role("button", name="Download 1 matching feed (CSV)").click()
    download = download_info.value
    assert download.suggested_filename.startswith("gtfs-scorecard-feature-matches-")
    csv = Path(download.path()).read_text()
    assert len(csv.splitlines()) == 2
    assert '"capabilities_measured"' in csv.splitlines()[0]
    assert '"accessibility_fields"' in csv.splitlines()[0]
    assert '"translation_languages"' in csv.splitlines()[0]
    assert '"barrie-transit"' in csv
    assert '"london-transit-commission"' not in csv
    assert '"100"' in csv and '"96"' in csv

    page.get_by_role("button", name="Clear shortlist").click()
    expect(page.locator(".results-hint")).to_be_visible()
    expect(page.locator(".agency-count")).to_have_text("Choose a filter to build a shortlist.")
    expect(page.locator(".feature-match-board")).to_have_attribute("data-active", "false")
    expect(page.locator('input[value="accessibility"]')).not_to_be_checked()
    expect(page.locator("#wheelchair-stops-min")).to_have_value("")
    expect(page.locator("#download-feature-results")).to_be_disabled()
    expect(page.locator("#download-feature-results")).to_be_hidden()
    assert _hash_params(page) == {"sort": "za"}


def test_feature_nav_and_translation_language_deep_link(page: Page, app_url: str) -> None:
    directory = _feature_directory()
    _serve_directory(page, directory)
    page.goto(f"{app_url}#/")

    page.get_by_role("link", name="Feed features").click()
    page.wait_for_url(f"{app_url}#/?view=features")
    expect(page.locator("#feature-finder")).to_be_focused()
    expect(page.get_by_role("link", name="Feed features")).to_have_attribute("aria-current", "page")

    page.locator('input[value="translations"]').check()
    page.locator("#translation-language").select_option("fr")

    expect(page.locator(".agency-count")).to_have_text(
        f"1 of {len(directory['agencies']):,} scorecard"
    )
    expect(page.get_by_role("link", name="Barrie Transit (Ontario)")).to_be_visible()
    expect(page.get_by_role("link", name="London Transit Commission")).to_have_count(0)
    expect(page.locator(".feature-evidence")).to_contain_text("Translations: French (fr)")
    assert _hash_params(page) == {
        "features": "translations",
        "view": "features",
        "lang": "fr",
    }


def test_service_mode_filter_is_deep_linkable_and_exports_evidence(
    page: Page, app_url: str
) -> None:
    directory = _feature_directory()
    _serve_directory(page, directory)
    page.goto(f"{app_url}#/?view=features&mode=ferry")

    expect(page.locator("#service-mode")).to_have_value("ferry")
    expect(page.locator(".agency-count")).to_have_text(
        f"1 of {len(directory['agencies']):,} scorecard"
    )
    expect(page.get_by_role("link", name="Barrie Transit (Ontario)")).to_be_visible()
    expect(page.get_by_role("link", name="London Transit Commission")).to_have_count(0)
    expect(page.locator(".feature-evidence")).to_contain_text("Mode: Ferry")

    page.locator("#agency-sort").select_option("za")
    assert _hash_params(page) == {"sort": "za", "view": "features", "mode": "ferry"}

    with page.expect_download() as download_info:
        page.get_by_role("button", name="Download 1 matching feed (CSV)").click()
    csv = Path(download_info.value.path()).read_text()
    assert '"modes_measured"' in csv.splitlines()[0]
    assert '"primary_mode"' in csv.splitlines()[0]
    assert '"bus|ferry"' in csv


def test_feature_nav_is_available_from_mobile_menu(page: Page, app_url: str) -> None:
    _serve_directory(page, _feature_directory())
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{app_url}#/")

    page.get_by_role("button", name="Menu").click()
    page.get_by_role("link", name="Feed features").click()

    page.wait_for_url(f"{app_url}#/?view=features")
    expect(page.locator("#feature-finder")).to_be_focused()
    expect(page.get_by_role("button", name="Menu")).to_have_attribute("aria-expanded", "false")
    expect(page.locator('.nav-stops a[href="/app/#/?view=features"]')).to_have_attribute(
        "aria-current", "page"
    )


def test_cohort_agency_name_cannot_inject_attributes(page: Page, app_url: str) -> None:
    index = json.loads((ARTIFACTS / "index.json").read_text())
    agency_id = next(iter(index["agencies"]))
    hostile_name = 'Quoted " onmouseover="window.__pwned=1" <agency>'
    index["agencies"][agency_id]["name"] = hostile_name
    page.route(
        "**/data/artifacts/index.json",
        lambda route: route.fulfill(json=index),
    )

    page.goto(f"{app_url}#/cohort?ids={agency_id}")

    expect(page.locator(".program-row h3 a")).to_have_text(hostile_name)
    expect(page.locator(".cohort-remove")).to_have_attribute(
        "aria-label", f"Remove {hostile_name} from my agencies"
    )
    expect(page.locator("[onmouseover]")).to_have_count(0)
    assert page.evaluate("() => window.__pwned") is None


def test_arbitrary_country_deep_link_filters_searches_and_canonicalizes(
    page: Page, app_url: str
) -> None:
    _serve_directory(page, _portable_directory())
    page.goto(f"{app_url}#/?country=gb&subdivision=gb-eng")

    expect(page.locator('.location-country[data-country="GB"]').first).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(
        page.locator('.location-subdivision[data-subdivision="GB-ENG"]').first
    ).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".agency-count")).to_contain_text("1 of")
    expect(page.get_by_role("link", name="Example GB Transit")).to_be_visible()
    expect(page.locator(".agency-card .meta")).to_contain_text("England, United Kingdom")
    assert page.evaluate("() => location.hash") == "#/?country=gb&subdivision=gb-eng"

    # The first user interaction rewrites portable location keys to their
    # canonical upper-case form while retaining the active sort.
    page.locator("#agency-sort").select_option("za")
    assert _hash_params(page) == {
        "country": "GB",
        "subdivision": "GB-ENG",
        "sort": "za",
    }

    page.locator("#agency-search").fill("GB-ENG")
    expect(page.locator(".agency-count")).to_contain_text("1 of")
    page.locator("#agency-search").fill("United Kingdom")
    expect(page.locator(".agency-count")).to_contain_text("1 of")


def test_us_detail_map_is_regional_and_only_appears_for_us_selection(
    page: Page, app_url: str
) -> None:
    _serve_directory(page, _portable_directory())
    page.goto(f"{app_url}#/")

    # Country controls are the primary worldwide browser. The optional U.S.
    # state choropleth must not frame every other country as an exception.
    expect(page.locator(".country-grid .location-country")).to_have_count(4)
    expect(page.locator(".location-group:visible")).to_have_count(0)
    expect(page.locator(".location-subdivision")).to_have_count(0)
    expect(page.locator("#us-map")).to_be_hidden()
    expect(page.get_by_text("Not on this US map", exact=False)).to_have_count(0)
    assert page.evaluate(
        """() => {
          const countries = document.querySelector('.country-grid');
          const map = document.querySelector('#us-map');
          const subdivisions = document.querySelector('.location-groups');
          return Boolean(
            countries && map && subdivisions &&
            (countries.compareDocumentPosition(map) & Node.DOCUMENT_POSITION_FOLLOWING) &&
            (map.compareDocumentPosition(subdivisions) & Node.DOCUMENT_POSITION_FOLLOWING)
          );
        }"""
    )

    page.locator('.location-country[data-country="US"]').first.click()
    expect(page.locator('.location-group[data-location-group="US"]')).to_be_visible()
    expect(page.locator(".location-group:visible")).to_have_count(1)
    expect(page.locator('.location-subdivision[data-country="US"]')).to_have_count(2)
    expect(page.locator('.location-subdivision:not([data-country="US"])')).to_have_count(0)
    expect(page.locator("#us-map")).to_be_visible()
    expect(page.locator("#us-map .us-map-svg")).to_be_visible()

    page.locator('.location-country[data-country="CA"]').first.click()
    expect(page.locator("#us-map")).to_be_hidden()
    expect(page.locator('.location-subdivision[data-country="CA"]')).to_have_count(2)
    expect(page.locator('.location-subdivision:not([data-country="CA"])')).to_have_count(0)


def test_legacy_state_bookmark_maps_without_eager_rewrite(page: Page, app_url: str) -> None:
    _serve_directory(page, _portable_directory())
    page.goto(f"{app_url}#/?state=California")
    expect(page.locator('.location-country[data-country="US"]').first).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(page.locator('.location-subdivision[data-subdivision="US-CA"]').first).to_have_attribute(
        "aria-pressed", "true"
    )
    assert page.evaluate("() => location.hash") == "#/?state=California"

    page.locator("#agency-sort").select_option("za")
    params = _hash_params(page)
    assert params == {"country": "US", "subdivision": "US-CA", "sort": "za"}


def test_unlocated_subdivision_is_scoped_by_country_and_preserves_legacy_url(
    page: Page, app_url: str
) -> None:
    _serve_directory(page, _portable_directory())
    page.goto(f"{app_url}#/?state=Unlocated")

    us = page.locator(
        '.location-subdivision[data-country="US"][data-subdivision="UNLOCATED"]'
    ).first
    ca = page.locator(
        '.location-subdivision[data-country="CA"][data-subdivision="UNLOCATED"]'
    ).first
    expect(us).to_have_attribute("aria-pressed", "true")
    expect(ca).to_have_count(0)
    assert page.evaluate("() => location.hash") == "#/?state=Unlocated"

    page.locator('.location-country[data-country="CA"]').first.click()
    ca = page.locator(
        '.location-subdivision[data-country="CA"][data-subdivision="UNLOCATED"]'
    ).first
    expect(ca).to_have_attribute("aria-pressed", "false")
    ca.click()
    expect(us).to_have_count(0)
    expect(ca).to_have_attribute("aria-pressed", "true")
    assert _hash_params(page) == {"country": "CA", "subdivision": "UNLOCATED"}
    expect(page.locator(".agency-count")).to_contain_text("1 of")


def test_old_directory_keeps_state_and_canada_behavior(page: Page, app_url: str) -> None:
    directory = _portable_directory()
    directory["summary"].pop("countries")
    for agency in directory["agencies"]:
        agency.pop("subdivision_code", None)
        agency.pop("subdivision_name", None)
    _serve_directory(page, directory)
    page.goto(f"{app_url}#/?state=Canada")

    expect(page.locator('.legacy-location[data-state="Canada"]')).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(page.locator(".agency-count")).to_contain_text("3 of")
    expect(page.locator("#us-map")).to_be_visible()
    assert page.evaluate("() => location.hash") == "#/?state=Canada"
    page.locator("#agency-search").fill("Barrie")
    params = _hash_params(page)
    assert params == {"state": "Canada", "q": "Barrie"}
