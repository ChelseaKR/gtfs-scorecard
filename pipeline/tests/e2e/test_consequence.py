"""The consequence layer on the scorecard page (issue #367).

Each finding on the SPA scorecard says how much of the network it covers, and
the fixes carry a "Riders and need" block underneath. This file drives the real
app over the immutable golden site and checks three things: the SPA words a
consequence the way the prerendered page does, an absence is never drawn as a
value, and the block is usable by keyboard and at phone width.

The golden artifacts predate schema 1.19 and carry no consequence block, so each
test serves the same artifact with the block the publisher would have written
(``with_consequences``), by answering the artifact request itself. Where a
sabotage is the point, the test first shows the intact block does what the
sabotage is meant to break.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, Route, expect

from scorecard_pipeline.consequence import with_consequences

pytestmark = pytest.mark.e2e

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "golden_site"
AGENCIES = ["unitrans", "yolobus", "barrie-transit"]

Transform = Callable[[dict[str, Any]], dict[str, Any]]


def _golden(agency_id: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (GOLDEN / "data" / "artifacts" / agency_id / "latest.json").read_text()
    )
    return loaded


@pytest.fixture
def serve(page: Page) -> Callable[[str, Transform | None], None]:
    """Answer one agency's artifact request with the golden artifact, changed by
    ``transform``. The default adds the consequence blocks."""

    def register(agency_id: str, transform: Transform | None = None) -> None:
        artifact = (transform or with_consequences)(_golden(agency_id))
        body = json.dumps(artifact)

        def fulfill(route: Route) -> None:
            route.fulfill(status=200, content_type="application/json", body=body)

        page.route(re.compile(rf"/data/artifacts/{re.escape(agency_id)}/latest\.json"), fulfill)

    return register


def _open_spa(page: Page, base: str, agency_id: str) -> None:
    page.goto(f"{base}/app/#/agency/{agency_id}")
    expect(page.locator("h1.board-title")).to_be_visible()
    expect(page.locator(".platforms .platform")).to_have_count(4)


_STATIC_VIEW = """
() => ({
  heading: document.querySelector('.consequence h3')?.textContent.trim() ?? null,
  fineprint: document.querySelector('.consequence .fineprint')?.textContent.trim() ?? null,
  ridership: document.querySelectorAll('.consequence li')[0]?.textContent.trim() ?? null,
  reach: [...document.querySelectorAll('.alerts .alert')].map(
    (alert) => alert.querySelectorAll('.awhy')[1]?.textContent.trim() ?? null),
})
"""

_SPA_VIEW = """
() => ({
  heading: document.querySelector('.consequence h3')?.textContent.trim() ?? null,
  fineprint: document.querySelector('.consequence .fineprint')?.textContent.trim() ?? null,
  ridership: document.querySelector('[data-consequence="ridership"]')?.textContent.trim() ?? null,
  need: document.querySelector('[data-consequence="need"]')?.textContent.trim() ?? null,
  reach: [...document.querySelectorAll('.alerts [data-consequence="reach"]')].map(
    (line) => line.textContent.trim()),
  states: [...document.querySelectorAll('.alerts [data-consequence="reach"]')].map(
    (line) => line.getAttribute('data-state')),
})
"""


@pytest.mark.parametrize("agency_id", AGENCIES)
def test_the_spa_words_reach_the_way_the_prerendered_page_does(
    page: Page,
    parity_base_url: str,
    serve: Callable[[str, Transform | None], None],
    agency_id: str,
) -> None:
    page.goto(f"{parity_base_url}/agency/{agency_id}/")
    expect(page.locator(".consequence")).to_be_visible()
    static_view = page.evaluate(_STATIC_VIEW)
    assert all(static_view["reach"]), "the prerendered page should state reach on every fix"

    serve(agency_id, None)
    _open_spa(page, parity_base_url, agency_id)
    expect(page.locator(".consequence")).to_be_visible()
    spa_view = page.evaluate(_SPA_VIEW)

    assert spa_view["reach"] == static_view["reach"]
    assert spa_view["heading"] == static_view["heading"] == "Riders and need behind these fixes"
    assert spa_view["fineprint"] == static_view["fineprint"]
    if agency_id == "barrie-transit":
        # Outside the United States both pages give the same reason, in the same words.
        assert spa_view["ridership"] == static_view["ridership"]
        assert "does not cover this feed's country" in spa_view["ridership"]


def test_a_measured_share_and_an_absence_are_told_apart(
    page: Page, parity_base_url: str, serve: Callable[[str, Transform | None], None]
) -> None:
    serve("unitrans", None)
    _open_spa(page, parity_base_url, "unitrans")
    view = page.evaluate(_SPA_VIEW)
    # Unitrans: two shares, then a validator notice that has none.
    assert view["states"] == ["measured", "measured", "absent"]
    assert view["reach"][0] == "Fixing this covers all 296 stops in the feed."
    assert view["reach"][2].startswith("This is a validator notice")
    assert not re.search(r"\d|%", view["reach"][2])


def test_a_partial_share_is_worded_with_its_counts(
    page: Page, parity_base_url: str, serve: Callable[[str, Transform | None], None]
) -> None:
    def thirty_stops(artifact: dict[str, Any]) -> dict[str, Any]:
        artifact = json.loads(json.dumps(artifact))
        artifact["top_fixes"][0]["count"] = 30
        return with_consequences(artifact)

    serve("unitrans", thirty_stops)
    _open_spa(page, parity_base_url, "unitrans")
    view = page.evaluate(_SPA_VIEW)
    assert view["reach"][0] == "Fixing this covers 30 of 296 stops, about 10% of them."
    assert view["states"][0] == "measured"


def test_every_finding_in_the_list_states_its_reach(
    page: Page, parity_base_url: str, serve: Callable[[str, Transform | None], None]
) -> None:
    serve("yolobus", None)
    _open_spa(page, parity_base_url, "yolobus")
    findings = page.locator(".findings .finding")
    total = findings.count()
    assert total > 0
    expect(page.locator(".findings .finding [data-consequence='reach']")).to_have_count(total)
    # A filter re-renders the list, and the reach lines come with it.
    page.get_by_role("button", name=re.compile(r"^Warnings")).click()
    shown = page.locator(".findings .finding").count()
    expect(page.locator(".findings .finding [data-consequence='reach']")).to_have_count(shown)


# --- what this view holds back ------------------------------------------------------


def test_rider_trips_and_need_are_reasons_never_numbers(
    page: Page, parity_base_url: str, serve: Callable[[str, Transform | None], None]
) -> None:
    serve("unitrans", None)
    _open_spa(page, parity_base_url, "unitrans")
    block = page.locator(".consequence")
    rider = block.locator("[data-consequence='ridership']")
    need = block.locator("[data-consequence='need']")
    expect(rider).to_contain_text("This view does not show annual rider-trips")
    expect(need).to_contain_text("This view does not show transit need")
    text = block.inner_text()
    assert not re.search(r"\d", text.replace("Riders and need behind these fixes", "")), text
    expect(block.get_by_role("link", name="Open the agency page for Unitrans")).to_have_attribute(
        "href", "/agency/unitrans/"
    )


def test_negative_control_a_stray_number_is_not_shown(
    page: Page, parity_base_url: str, serve: Callable[[str, Transform | None], None]
) -> None:
    def with_stray_values(artifact: dict[str, Any]) -> dict[str, Any]:
        out = with_consequences(artifact)
        for fix in out["top_fixes"]:
            fix["consequence"]["ridership"] = {
                "annual_rider_trips": 3_456_789,
                "ntd_id": "90142",
                "reason": "",
            }
            fix["consequence"]["served_area_need"] = {
                "tier": "high",
                "scale": "us_acs",
                "reason": "",
            }
        return out

    # The sabotage has to land: this record, joined the way the pages join it
    # with a source and a date, would state the figure. Without them it must not.
    stray = with_stray_values(_golden("unitrans"))
    assert stray["top_fixes"][0]["consequence"]["ridership"]["annual_rider_trips"] == 3_456_789

    serve("unitrans", with_stray_values)
    _open_spa(page, parity_base_url, "unitrans")
    text = page.locator(".consequence").inner_text()
    assert "3,456,789" not in text and "3456789" not in text
    assert "high" not in text
    assert "does not record its report year or fetch date, so its figures are not shown" in text


def test_negative_control_a_share_that_cannot_be_counted_is_not_a_number(
    page: Page, parity_base_url: str, serve: Callable[[str, Transform | None], None]
) -> None:
    # Control: with its denominators, the first fix on this record is a measured share.
    serve("unitrans", None)
    _open_spa(page, parity_base_url, "unitrans")
    assert page.evaluate(_SPA_VIEW)["states"][0] == "measured"

    def without_denominators(artifact: dict[str, Any]) -> dict[str, Any]:
        artifact = json.loads(json.dumps(artifact))
        artifact["geo"].pop("stop_count", None)
        artifact["routability"].pop("boardable_stops", None)
        return with_consequences(artifact)

    sabotaged = without_denominators(_golden("unitrans"))
    assert sabotaged["top_fixes"][0]["consequence"]["reach"]["share"] is None

    # The later registration takes precedence over the earlier one. The address is
    # unchanged, so a reload is what makes the app fetch the record again.
    serve("unitrans", without_denominators)
    page.reload()
    expect(page.locator("h1.board-title")).to_be_visible()
    expect(page.locator(".consequence")).to_be_visible()
    view = page.evaluate(_SPA_VIEW)
    assert view["states"][0] == "absent"
    assert (
        view["reach"][0] == "The feed's stops count is not published here, so no share is reported."
    )
    assert not re.search(r"\d|%", view["reach"][0])


def test_a_scorecard_published_before_the_block_says_so_once(
    page: Page, parity_base_url: str
) -> None:
    # No stub: the golden artifact is schema 1.4 and has no consequence blocks.
    _open_spa(page, parity_base_url, "unitrans")
    expect(page.locator("[data-consequence='record']")).to_have_count(1)
    expect(page.locator("[data-consequence='record']")).to_contain_text(
        "published before reach, rider-trips, and transit need were recorded"
    )
    expect(page.locator("[data-consequence='reach']")).to_have_count(0)
    expect(page.locator("[data-consequence='ridership']")).to_have_count(0)
    expect(page.get_by_role("link", name="Open the agency page for Unitrans")).to_be_visible()


# --- accessibility and layout -------------------------------------------------------


def test_the_block_is_structured_and_reachable_by_keyboard(
    page: Page, parity_base_url: str, serve: Callable[[str, Transform | None], None]
) -> None:
    serve("unitrans", None)
    _open_spa(page, parity_base_url, "unitrans")
    heading = page.locator("#consequence-h")
    assert heading.evaluate("el => el.tagName") == "H3"
    # The block sits under the section's own h2, so the outline has no gap.
    assert page.locator("#fixes-h").evaluate("el => el.tagName") == "H2"
    assert page.locator(".consequence ul li").count() == 2
    # Meaning is carried by words. The state markers are attributes for tests, not styling
    # or announcements, so nothing depends on color or on an unread attribute.
    assert page.locator(".consequence [aria-label], .consequence [role]").count() == 0

    link = page.get_by_role("link", name="Open the agency page for Unitrans")
    link.focus()
    expect(link).to_be_focused()
    box = link.bounding_box()
    assert box is not None and box["height"] >= 44, "target size, WCAG 2.5.5"
    page.keyboard.press("Enter")
    expect(page).to_have_url(re.compile(r"/agency/unitrans/$"))


@pytest.mark.parametrize("agency_id", ["unitrans", "barrie-transit"])
def test_the_block_fits_a_phone_without_sideways_scrolling(
    page: Page,
    parity_base_url: str,
    serve: Callable[[str, Transform | None], None],
    agency_id: str,
) -> None:
    page.set_viewport_size({"width": 320, "height": 640})
    serve(agency_id, None)
    _open_spa(page, parity_base_url, agency_id)
    expect(page.locator(".consequence")).to_be_visible()
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, f"page scrolls sideways by {overflow}px"
    for line in page.locator(".consequence li, [data-consequence='reach']").all():
        box = line.bounding_box()
        assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= 320
