"""Browser contracts for the progressively hydrated national map directory."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, expect

from scorecard_pipeline.render_site import _render_map_page

pytestmark = pytest.mark.e2e


def _features(count: int = 55) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [-120.0 + number / 100, 38.0],
                },
                "properties": {
                    "id": f"agency-{number:03d}",
                    "name": f"Agency {number:03d}",
                    "grade": "A" if number % 2 == 0 else "B",
                    "score": 90 - number / 10,
                    "state": "California",
                    "country": "US",
                    "subdivision_code": "US-CA",
                    "subdivision_name": "California",
                    "has_flex": number % 3 == 0,
                    "color": "#1f7a4d",
                    "url": f"/agency/agency-{number:03d}/",
                },
            }
            for number in range(count)
        ],
    }


def test_first_map_filter_hydrates_complete_list_once(page: Page, base_url: str) -> None:
    payload = _features()
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if request.url.endswith("/map.geojson") else None
        ),
    )
    page.route(
        "**/map/",
        lambda route: route.fulfill(
            content_type="text/html",
            body=_render_map_page(payload["features"]),
        ),
    )
    page.route("**/map.geojson", lambda route: route.fulfill(json=payload))

    page.goto(f"{base_url}/map/")

    rows = page.locator("#map-tbody tr")
    expect(rows).to_have_count(50)
    assert requests == []

    page.locator("#map-grade").select_option("A")

    expect(rows).to_have_count(55)
    expect(page.locator("#map-list-status")).to_contain_text("Complete list loaded")
    expect(page.locator("#map-tbody tr:visible")).to_have_count(28)
    assert page.locator("#map-tbody tr:visible").evaluate_all(
        "(rows) => rows.every((row) => row.dataset.grade === 'A')"
    )
    page.locator("#map-flex").check()
    assert len(requests) == 1


def test_map_filter_failure_keeps_bounded_fallback_consistent(page: Page, base_url: str) -> None:
    payload = _features()
    page.route(
        "**/map/",
        lambda route: route.fulfill(
            content_type="text/html",
            body=_render_map_page(payload["features"]),
        ),
    )
    page.route(
        "**/map.geojson",
        lambda route: route.fulfill(status=500, content_type="application/json", body="{}"),
    )
    page.goto(f"{base_url}/map/")

    rows = page.locator("#map-tbody tr")
    expect(rows).to_have_count(50)
    page.locator("#map-grade").select_option("A")

    expect(page.locator("#map-list-status")).to_contain_text(
        "This filter applies to the first 50 rows only"
    )
    expect(page.locator("#map-grade")).to_be_enabled()
    expect(page.locator("#map-grade")).to_have_value("A")
    assert page.locator("#map-tbody tr:visible").evaluate_all(
        "(visibleRows) => visibleRows.every((row) => row.dataset.grade === 'A')"
    )
