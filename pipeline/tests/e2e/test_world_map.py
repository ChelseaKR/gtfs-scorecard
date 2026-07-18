"""Browser contract for the world coverage choropleth on the app overview."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, Route

pytestmark = pytest.mark.e2e


def test_world_map_mounts_shades_and_filters(page: Page, app_url: str) -> None:
    # Progressive enhancement over the country chips: the map mounts from the
    # committed geometry, shades only countries with feed records, and a
    # country path behaves exactly like its chip.
    page.goto(app_url)
    page.wait_for_selector("#world-map svg")
    shaded = page.locator("#world-map path[data-map-country]")
    assert shaded.count() > 0
    # Every shaded country announces its data in text, never color alone.
    first = shaded.first
    label = first.get_attribute("aria-label") or ""
    assert "feed" in label
    assert "expired" in label
    code = first.get_attribute("data-map-country") or ""
    first.click()
    assert first.get_attribute("aria-pressed") == "true"
    chip = page.locator(f'.location-country[data-country="{code}"]')
    assert chip.get_attribute("aria-pressed") == "true"
    # Clicking again clears the filter, mirroring chip behavior.
    first.click()
    assert first.get_attribute("aria-pressed") == "false"
    # The legend restates the shading in text.
    assert "Share of feeds expired" in (page.locator("#world-map .map-legend").inner_text())


def test_world_map_absence_degrades_silently(page: Page, base_url: str) -> None:
    # If the geometry asset cannot load, the chips remain the primary control
    # and no map error surfaces.
    page.route("**/world-countries.json", lambda route: route.abort())
    page.goto(f"{base_url}/app/")
    page.wait_for_selector(".country-grid")
    assert page.locator("#world-map svg").count() == 0
    assert page.locator(".location-country").count() > 0


def test_region_coverage_discloses_the_selected_cohort_denominator(
    page: Page, app_url: str
) -> None:
    # Filtering to a country states that country's own reviewed-cohort size, so
    # a non-US region is never read against only the US-heavy global denominator.
    # Canada stands in for any non-US country (three feed records in the fixture,
    # Ontario carrying two); the counts are read from the chips, not hardcoded,
    # so the test survives data refreshes.
    page.goto(app_url)
    page.wait_for_selector(".location-country")
    disclosure = page.locator("#region-coverage")
    assert disclosure.is_hidden()  # nothing claimed until a region is chosen

    canada = page.locator('.location-country[data-country="CA"]')
    assert canada.count() == 1
    country_count = canada.locator(".state-n").inner_text().strip()
    canada.click()

    page.wait_for_selector("#region-coverage:not([hidden])")
    text = disclosure.inner_text()
    assert "Canada" in text
    assert "reviewed feed record" in text  # cohort size, in text not color
    assert country_count in text
    assert "not a census" in text  # never overstated as coverage

    # Drilling into a subdivision restates the denominator for that area.
    ontario = page.locator('.location-subdivision[data-subdivision="CA-ON"]')
    assert ontario.count() == 1
    sub_count = ontario.locator(".state-n").inner_text().strip()
    ontario.click()
    page.wait_for_function(
        "() => document.querySelector('#region-coverage')?.textContent?.includes('Ontario')"
    )
    sub_text = disclosure.inner_text()
    assert "Ontario, Canada" in sub_text
    assert sub_count in sub_text
    assert "not a census" in sub_text


def test_country_drills_into_its_subdivisions(page: Page, base_url: str) -> None:
    # A country with committed subdivision geometry drills down: selecting it on
    # the world map swaps to its subdivision choropleth, each area filters the
    # list, and a Back control returns to the world. Canada (present in the
    # fixture with one Ontario feed) stands in for any country; the geometry is
    # routed synthetically so the test exercises the interaction, not one
    # country's real shape.
    geometry = {
        "viewBox": "0 0 100 100",
        "country": "CA",
        "subdivisions": {"CA-ON": "M10 10 L90 10 L90 90 L10 90 Z"},
    }

    def serve_geometry(route: Route) -> None:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(geometry))

    page.route("**/subdivisions/ca.json", serve_geometry)
    page.goto(f"{base_url}/app/")
    page.wait_for_selector("#world-map svg")

    canada = page.locator('#world-map path[data-map-country="CA"]')
    assert canada.count() == 1
    canada.click()

    # The map has drilled in: a Back control and the subdivision area appear.
    page.wait_for_selector("#world-map [data-map-back]")
    ontario = page.locator('#world-map path[data-map-subdivision="CA-ON"]')
    assert ontario.count() == 1
    label = ontario.get_attribute("aria-label") or ""
    assert "Ontario" in label
    assert "feed" in label  # counts are announced in text, never color alone

    # Selecting the area filters to it and marks it pressed.
    ontario.click()
    assert ontario.get_attribute("aria-pressed") == "true"

    # Back returns to the world view.
    page.locator("#world-map [data-map-back]").click()
    page.wait_for_selector('#world-map path[data-map-country="CA"]')
    assert page.locator("#world-map [data-map-back]").count() == 0
