"""The selected finding rides in the URL fragment, never the query string (ADR 0074).

Google picked agency pages' ``?finding=`` URLs as canonical over the clean
pages, because every agency page, brief, board and state or country rollup
linked to them. A fragment is not a separate URL to a crawler. These tests
hold the generated links to the fragment form, keep the canonical clean, and
keep old ``?finding=`` links readable by the page script.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import render_site
from scorecard_pipeline.render_site import (
    _FINDING_CONTEXT_SCRIPT,
    _finding_url,
    _parse_authored_markdown,
    _render_agency,
    _render_board_page,
    _render_brief,
    _render_fix,
    _render_rollup,
)

_TESTS = Path(__file__).parent
_REPO = _TESTS.parents[1]
_FIXTURE = _TESTS / "fixtures" / "golden_site"
_GOLDENS = _TESTS / "goldens"

# A crawlable link (href) or a printed URL that carries the finding in a query.
_QUERY_FINDING = re.compile(r"\?(?:[^\"'<>\s#]*&)?(?:amp;)?finding=")
_HREF = re.compile(r'href="([^"]*)"')


def _query_finding_hrefs(html: str) -> list[str]:
    return [href for href in _HREF.findall(html) if _QUERY_FINDING.search(href)]


def _artifact(agency_id: str) -> dict[str, Any]:
    path = _FIXTURE / "data" / "artifacts" / agency_id / "latest.json"
    artifact: dict[str, Any] = json.loads(path.read_text())
    return artifact


def _member(agency_id: str, grade: str = "B") -> dict[str, Any]:
    return {
        "id": agency_id,
        "name": agency_id.title(),
        "grade": grade,
        "score": 81.5,
        "snapshot_date": "2026-11-01",
        "status": "ready",
        "top_fix_code": "stop_times_future_date",
        "needs_attention": False,
        "attention_reason": None,
    }


def _rollup(count: int) -> dict[str, Any]:
    members = [_member(f"agency{i}") for i in range(count)]
    return {
        "rollup": {"id": "us-ca", "name": "California"},
        "agency_count": count,
        "average_score": 81.5,
        "grade_distribution": {"B": count},
        "comparison": {"eligible_count": 0},
        "needs_attention": 0,
        "expired": {"lapsed": 0, "stale": 0, "total": 0},
        "members": members,
    }


def _rendered_surfaces(agency_id: str) -> dict[str, str]:
    artifact = _artifact(agency_id)
    code = artifact["top_fixes"][0]["code"]
    render_site.FIX_CODES_WITH_PAGES.add(code)
    try:
        return {
            "agency": _render_agency(artifact),
            "brief": _render_brief(artifact),
            "board": _render_board_page(artifact),
            "rollup": _render_rollup(_rollup(12)),
        }
    finally:
        render_site.FIX_CODES_WITH_PAGES.discard(code)


def test_finding_url_puts_the_code_in_the_fragment() -> None:
    assert _finding_url("/agency/unitrans/", "unused_shape") == (
        "/agency/unitrans/#finding=unused_shape"
    )
    assert _finding_url("/fix/unused_shape/", "unused_shape", agency_id="unitrans") == (
        "/fix/unused_shape/#finding=unused_shape&agency=unitrans"
    )
    assert _finding_url("/agency/unitrans/", "unused_shape", anchor="trend-h") == (
        "/agency/unitrans/#finding=unused_shape&at=trend-h"
    )


def test_finding_url_rejects_unsafe_values() -> None:
    # An unsafe code leaves the clean path; an unsafe agency or anchor is dropped.
    assert _finding_url("/agency/unitrans/", "bad code") == "/agency/unitrans/"
    assert _finding_url("/agency/unitrans/", "") == "/agency/unitrans/"
    assert _finding_url("/fix/x/", "x", agency_id="../evil") == "/fix/x/#finding=x"
    assert _finding_url("/agency/a/", "x", anchor="a b") == "/agency/a/#finding=x"


@pytest.mark.parametrize("agency_id", ["unitrans", "yolobus"])
def test_no_rendered_surface_links_a_query_finding(agency_id: str) -> None:
    surfaces = _rendered_surfaces(agency_id)
    code = _artifact(agency_id)["top_fixes"][0]["code"]
    for name, html in surfaces.items():
        assert _query_finding_hrefs(html) == [], name
        assert "?finding=" not in html, f"{name} still prints a query-form finding URL"
    for name in ("agency", "brief", "board"):
        html = surfaces[name]
        assert f'href="/agency/{agency_id}/brief/#finding={code}"' in html, name
        assert f'href="/agency/{agency_id}/board/#finding={code}"' in html, name
        assert f'href="/agency/{agency_id}/#finding={code}&amp;at=trend-h"' in html, name
        assert f'href="/fix/{code}/#finding={code}&amp;agency={agency_id}"' in html, name
        # The copied handoff text names the same fragment URL.
        assert f"Evidence: https://gtfsscorecard.org/agency/{agency_id}/#finding={code}" in html
    assert 'href="/agency/agency0/#finding=stop_times_future_date"' in surfaces["rollup"]


@pytest.mark.parametrize("agency_id", ["unitrans", "yolobus"])
def test_canonical_stays_the_clean_agency_url(agency_id: str) -> None:
    html = _rendered_surfaces(agency_id)["agency"]
    canonicals = re.findall(r'<link rel="canonical" href="([^"]*)">', html)
    assert canonicals == [f"https://gtfsscorecard.org/agency/{agency_id}/"]


def test_query_detector_negative_control(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restoring the old query form must trip the detector, so the checks above
    can fail. The sabotage is asserted to have taken effect first."""

    def old_query_form(
        path: str,
        code: str,
        *,
        agency_id: str | None = None,
        anchor: str = "finding-handoff",
    ) -> str:
        return f"{path}?finding={code}#{anchor}"

    monkeypatch.setattr(render_site, "_finding_url", old_query_form)
    assert render_site._finding_url("/a/", "x") == "/a/?finding=x#finding-handoff"
    for name, html in _rendered_surfaces("unitrans").items():
        assert _query_finding_hrefs(html), f"{name}: detector missed the query form"


def test_published_goldens_carry_no_query_finding_links() -> None:
    pages = sorted(_GOLDENS.rglob("*.html"))
    assert pages, "no golden pages to scan"
    offenders = {
        str(page.relative_to(_GOLDENS)): hrefs
        for page in pages
        if (hrefs := _query_finding_hrefs(page.read_text()))
    }
    assert offenders == {}
    # Not vacuous: the goldens do carry finding links, in the fragment form.
    assert any("#finding=" in page.read_text() for page in pages)


def test_page_script_reads_the_fragment_and_still_accepts_old_query_links() -> None:
    script = _FINDING_CONTEXT_SCRIPT
    assert "window.location.hash" in script
    assert 'query.get("finding")' in script
    assert 'query.get("agency")' in script
    assert "hashchange" in script
    # The script builds fix-guide context links in the fragment form only.
    assert '"?finding="' not in script
    assert '"#finding="' in script


def test_fix_guide_keeps_the_context_script() -> None:
    html = _render_fix(
        "unused_shape",
        _parse_authored_markdown(
            '---\ndate_published: "2026-07-03"\ndate_modified: "2026-07-08"\n---\n'
            "# Fix unused_shape\n\nFollow the published guide.\n",
            "test.md",
        ),
    )
    assert 'data-fix-context="unused_shape"' in html
    assert _query_finding_hrefs(html) == []
    assert '"#finding="' in html


def test_landing_script_links_findings_in_the_fragment() -> None:
    script = (_REPO / "web" / "src" / "landing-scorecard.js").read_text()
    assert '"?finding="' not in script
    assert 'path + "#finding=" + encodeURIComponent(code)' in script
