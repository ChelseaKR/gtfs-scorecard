"""SPA/prerendered parity: for the same agency, the prerendered
web/agency/<id>/ page and the SPA's #/agency/<id> route must present the same
grade letter, the same four category scores, and the same top-3 fix titles.
Both are generated from the same artifact (render_site.py mirrors app.js), so
any disagreement means one renderer drifted."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]

# Shared extraction over the DOM both renderers emit: the grade reel's
# aria-label, each platform row's name and score, and the top-3 alert titles
# (with the owner chip stripped; scores compared as numbers because the SPA
# prints 39 where the prerendered page prints 39.0).
_EXTRACT = """
() => {
  const reel = document.querySelector('.reel');
  const grade = (reel?.getAttribute('aria-label') || '').replace('Overall grade', '').trim();
  const categories = {};
  for (const p of document.querySelectorAll('.platforms .platform')) {
    const name = p.querySelector('.pname')?.textContent.trim() || '';
    const scoreEl = p.querySelector('.pscore')?.cloneNode(true);
    scoreEl?.querySelectorAll('.outof').forEach((s) => s.remove());
    const raw = (scoreEl?.textContent || '').trim();
    const num = Number.parseFloat(raw);
    categories[name] = Number.isNaN(num) ? raw : num;
  }
  const fixes = [...document.querySelectorAll('.alerts .alert .afix')].slice(0, 3).map((p) => {
    const clone = p.cloneNode(true);
    clone.querySelectorAll('.aowner').forEach((s) => s.remove());
    return clone.textContent.replace(/\\s+/g, ' ').trim();
  });
  return { grade, categories, fixes };
}
"""


def _snapshot_date_matches(agency_id: str) -> bool:
    """True when the committed prerendered page and latest.json come from the
    same snapshot, so parity is meaningful even if a deploy half-landed."""
    html_path = REPO_ROOT / "web" / "agency" / agency_id / "index.html"
    artifact_path = REPO_ROOT / "data" / "artifacts" / agency_id / "latest.json"
    if not html_path.is_file() or not artifact_path.is_file():
        return False
    checked = re.search(r"checked (\d{4}-\d{2}-\d{2})", html_path.read_text())
    if checked is None:
        return False
    snapshot: object = json.loads(artifact_path.read_text()).get("snapshot_date")
    return checked.group(1) == snapshot


@pytest.fixture(scope="module")
def parity_ids() -> list[str]:
    """Three agency ids rendered in both forms from the same snapshot: the
    first, middle, and last of the shared set, so the picks are deterministic
    and spread across the directory."""
    prerendered = {p.name for p in (REPO_ROOT / "web" / "agency").iterdir() if p.is_dir()}
    scored = {p.name for p in (REPO_ROOT / "data" / "artifacts").iterdir() if p.is_dir()}
    shared = sorted(aid for aid in prerendered & scored if _snapshot_date_matches(aid))
    assert len(shared) >= 3, "expected at least three agencies rendered in both forms"
    return [shared[0], shared[len(shared) // 2], shared[-1]]


def test_prerendered_page_matches_spa(
    page: Page, base_url: str, app_url: str, parity_ids: list[str]
) -> None:
    for agency_id in parity_ids:
        page.goto(f"{base_url}/agency/{agency_id}/")
        expect(page.locator("h1.board-title")).to_be_visible()
        expect(page.locator(".platforms .platform")).to_have_count(4)
        static_view = page.evaluate(_EXTRACT)

        page.goto(f"{app_url}#/agency/{agency_id}")
        expect(page.locator("h1.board-title")).to_be_visible()
        expect(page.locator(".platforms .platform")).to_have_count(4)
        spa_view = page.evaluate(_EXTRACT)

        assert spa_view["grade"] in "ABCDF" and len(spa_view["grade"]) == 1, agency_id
        assert spa_view == static_view, f"SPA and prerendered page disagree for {agency_id}"
