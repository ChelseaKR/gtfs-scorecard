"""Route smoke tests: each hash route renders its real content into #main and
the boot spinner ("Loading scorecards…" in web/app/index.html, "Loading…" from
app.js's route()) never persists once a route has rendered."""

from __future__ import annotations

import json
from pathlib import Path

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


def _assert_not_stuck_loading(page: Page) -> None:
    """Both spinners render as role=status .loading inside #main; a finished
    route replaces main's innerHTML, so none may remain."""
    expect(page.locator("#main .loading")).to_have_count(0)
    expect(page.get_by_text("Loading scorecards…")).to_have_count(0)


def test_overview_route_renders_directory(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/")
    expect(page.locator("#main h1.page-title")).to_have_text(
        "How is the country's transit data doing?"
    )
    expect(page.locator("#agency-search")).to_be_visible()
    _assert_not_stuck_loading(page)


def test_agency_route_renders_scorecard(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}#/agency/{AGENCY_ID}")
    expect(page.locator("h1.board-title")).to_have_text(_agency_name(AGENCY_ID))
    expect(page.locator("#fixes-h")).to_have_text("Top things to fix")
    expect(page.locator("#cats-h")).to_have_text("Score by category")
    expect(page.locator(".platforms .platform")).to_have_count(4)
    _assert_not_stuck_loading(page)


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
    expect(page.locator("#main h1.page-title")).to_have_text(
        "How is the country's transit data doing?"
    )
    page.locator('#main a[href="#/programs"]').click()
    expect(page.locator("#main h1.page-title")).to_have_text("Program rollups.")
    page.go_back()
    expect(page.locator("#main h1.page-title")).to_have_text(
        "How is the country's transit data doing?"
    )
    _assert_not_stuck_loading(page)
