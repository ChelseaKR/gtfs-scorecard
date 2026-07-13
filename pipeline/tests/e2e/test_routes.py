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
    """Current directory enriched with the additive portable location fields.

    The committed production snapshot predates the generated contract. Keeping
    this browser fixture local lets the SPA behavior be exercised without
    changing the pipeline or checked-in operational data.
    """
    directory = json.loads((ARTIFACTS / "directory.json").read_text())
    canadian = {
        "barrie-transit": ("CA-ON", "Ontario"),
        "london-transit-commission": ("CA-ON", "Ontario"),
    }
    california_count = 0
    for agency in directory["agencies"]:
        if agency["id"] in canadian:
            agency["subdivision_code"], agency["subdivision_name"] = canadian[agency["id"]]
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
    expect(page.locator("#main h1.page-title")).to_have_text("How is transit data doing?")
    expect(page.locator("#agency-search")).to_be_visible()
    _assert_not_stuck_loading(page)


def test_agency_route_renders_scorecard(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/agency/{AGENCY_ID}")
    expect(page.locator("h1.board-title")).to_have_text(_agency_name(AGENCY_ID))
    expect(page.locator("#fixes-h")).to_have_text("Top things to fix")
    expect(page.locator("#cats-h")).to_have_text("Score by category")
    expect(page.locator(".platforms .platform")).to_have_count(4)
    _assert_not_stuck_loading(page)


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
    expect(page.locator("#members-h")).to_have_text("Agencies, worst first")
    expect(page.locator(".program-list .program-row").first).to_be_visible()
    _assert_not_stuck_loading(page)


def test_hash_navigation_reroutes_without_reload(page: Page, app_url: str) -> None:
    """The hashchange listener re-renders in place, both forward and back."""
    page.goto(f"{app_url}#/")
    expect(page.locator("#main h1.page-title")).to_have_text("How is transit data doing?")
    page.locator('#main a[href="#/programs"]').click()
    expect(page.locator("#main h1.page-title")).to_have_text("Program rollups.")
    page.go_back()
    expect(page.locator("#main h1.page-title")).to_have_text("How is transit data doing?")
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
    expect(page.locator(".agency-count")).to_contain_text("agencies")
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
    page.locator("#agency-sort").select_option("best")
    params = _hash_params(page)
    assert params == {"country": "CA", "subdivision": "CA-ON", "sort": "best"}

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
    page.locator("#agency-sort").select_option("best")
    assert _hash_params(page) == {
        "country": "GB",
        "subdivision": "GB-ENG",
        "sort": "best",
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

    page.locator("#agency-sort").select_option("worst")
    params = _hash_params(page)
    assert params == {"country": "US", "subdivision": "US-CA", "sort": "worst"}


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
