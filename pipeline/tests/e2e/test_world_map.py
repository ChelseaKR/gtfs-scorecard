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
    # Selecting a country path filters the directory, marking its chip pressed —
    # whether or not the country also drills into its subdivisions. The chip is
    # outside #world-map, so a drill-down re-render never detaches it.
    chip = page.locator(f'.location-country[data-country="{code}"]')
    assert chip.get_attribute("aria-pressed") == "true"
    # Clearing via the chip returns the filter to all.
    chip.click()
    assert chip.get_attribute("aria-pressed") == "false"
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

    # Back returns to the world view and restores keyboard focus to the country
    # the user drilled from (WCAG 2.4.3 focus order), not to <body>.
    page.locator("#world-map [data-map-back]").click()
    page.wait_for_selector('#world-map path[data-map-country="CA"]')
    assert page.locator("#world-map [data-map-back]").count() == 0
    assert page.evaluate("() => document.activeElement?.getAttribute('data-map-country')") == "CA"
