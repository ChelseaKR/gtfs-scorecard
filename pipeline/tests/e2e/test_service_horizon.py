"""Legacy horizon fallback in the live JavaScript renderer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENCY_ID = "abq-ride"


def test_legacy_distant_horizon_never_renders_raw_countdown(page: Page, app_url: str) -> None:
    artifact = json.loads(
        (REPO_ROOT / "data" / "artifacts" / AGENCY_ID / "latest.json").read_text()
    )
    artifact["snapshot_date"] = "2026-07-13"
    freshness = artifact["categories"]["freshness"]
    freshness["summary"] = "Service data covers the next 26834 days."
    details = freshness["details"]
    details["days_until_expiry"] = 26_834
    details.pop("service_horizon_status", None)
    details.pop("effective_expiry_date", None)

    for pillar in (artifact.get("ntd_readiness") or {}).get("pillars", []):
        if pillar.get("key") == "current":
            pillar["detail"] = "Service data covers the next 26834 days."
    for criterion in (artifact.get("conformance") or {}).get("criteria", []):
        if criterion.get("key") == "current":
            criterion["detail"] = "Service data covers the next 26834 days."

    page.route(
        f"**/data/artifacts/{AGENCY_ID}/latest.json",
        lambda route: route.fulfill(json=artifact),
    )
    page.goto(f"{app_url}#/agency/{AGENCY_ID}")

    expect(page.locator("h1.board-title")).to_be_visible()
    expect(page.get_by_text("Review service end date", exact=True)).to_be_visible()
    expect(page.locator("#main")).to_contain_text("unusually distant")
    rendered = page.locator("#main").inner_text()
    assert "26834" not in rendered
    assert "26,834" not in rendered
