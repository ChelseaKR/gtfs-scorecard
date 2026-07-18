"""Browser contract for the world coverage choropleth on the app overview."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page

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
