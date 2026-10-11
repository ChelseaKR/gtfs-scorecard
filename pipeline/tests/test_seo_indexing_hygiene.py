"""Search indexing hygiene (ADR 0067): agency lastmod that follows template
revisions, redirects for a moved scorecard's companion pages, and a sitemap
that lists only pages a crawler can index under their own URL."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.config import Agency
from scorecard_pipeline.removed_twins import REMOVED_TWINS_FILENAME
from scorecard_pipeline.render_site import (
    AGENCY_TEMPLATE_REVISED,
    _write_agency_subpage_redirects,
    agency_page_lastmod,
    feed_change_date,
)

A = "a" * 64
B = "b" * 64


def _row(date: str, sha: str | None = A) -> dict[str, Any]:
    row: dict[str, Any] = {"date": date, "grade": "C", "score": 70.0}
    if sha is not None:
        row["feed_sha256"] = sha
    return row


# --- agency_page_lastmod ----------------------------------------------------


def test_unchanged_feed_on_the_old_template_reports_the_template_revision() -> None:
    # The page's content changed on the revision day even though the feed did
    # not; before this, the sitemap carried no lastmod at all for such a page.
    history = [_row("2026-07-03"), _row("2026-09-20"), _row("2026-10-11")]
    assert feed_change_date(history) is None
    assert agency_page_lastmod(history) == AGENCY_TEMPLATE_REVISED


def test_a_feed_change_after_the_revision_wins() -> None:
    history = [_row("2026-07-03", A), _row("2026-10-08", B), _row("2026-10-11", B)]
    assert agency_page_lastmod(history) == "2026-10-08"


def test_a_feed_change_before_the_revision_gives_way_to_it() -> None:
    history = [_row("2026-07-03", A), _row("2026-08-06", B), _row("2026-10-11", B)]
    assert agency_page_lastmod(history) == AGENCY_TEMPLATE_REVISED


def test_a_scorecard_first_published_after_the_revision_starts_at_its_first_check() -> None:
    history = [_row("2026-10-09"), _row("2026-10-10"), _row("2026-10-11")]
    assert agency_page_lastmod(history) == "2026-10-09"


def test_lastmod_is_never_the_latest_check_date() -> None:
    # Negative control for the bug ADR 0067 must not reintroduce: a daily
    # check that changed nothing does not move lastmod.
    history = [_row("2026-07-03"), _row("2026-10-07"), _row("2026-10-11")]
    assert agency_page_lastmod(history) != "2026-10-11"
    assert agency_page_lastmod(None) == AGENCY_TEMPLATE_REVISED
    assert agency_page_lastmod([{"date": "yesterday"}]) == AGENCY_TEMPLATE_REVISED


def test_the_revision_constant_is_an_iso_date() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", AGENCY_TEMPLATE_REVISED)
    dt.date.fromisoformat(AGENCY_TEMPLATE_REVISED)


# --- companion-page redirects -----------------------------------------------


def test_each_moved_scorecard_gets_brief_board_and_fixes_redirects() -> None:
    written: dict[str, str] = {}
    registry = {"metro-ride": Agency("metro-ride", "Metro Ride", "https://example.test/m.zip")}
    redirects = {"/agency/metro-ride-830/": "/agency/metro-ride/"}

    _write_agency_subpage_redirects(
        lambda path, html: written.update({path: html}), registry, redirects
    )

    assert redirects == {
        "/agency/metro-ride-830/": "/agency/metro-ride/",
        "/agency/metro-ride-830/brief/": "/agency/metro-ride/",
        "/agency/metro-ride-830/board/": "/agency/metro-ride/",
        "/agency/metro-ride-830/fixes/": "/agency/metro-ride/",
    }
    assert sorted(written) == [
        "agency/metro-ride-830/board/index.html",
        "agency/metro-ride-830/brief/index.html",
        "agency/metro-ride-830/fixes/index.html",
    ]
    brief = written["agency/metro-ride-830/brief/index.html"]
    assert 'http-equiv="refresh" content="0; url=/agency/metro-ride/"' in brief
    assert '<link rel="canonical" href="https://gtfsscorecard.org/agency/metro-ride/">' in brief
    assert "Metro Ride call-prep brief" in brief
    assert 'name="robots"' not in brief


def test_no_companion_redirects_without_a_moved_scorecard() -> None:
    # Negative control: nothing redirects, nothing is written.
    written: dict[str, str] = {}
    redirects: dict[str, str] = {}
    _write_agency_subpage_redirects(lambda path, html: written.update({path: html}), {}, redirects)
    assert written == {}
    assert redirects == {}


# --- end to end on the golden fixture ---------------------------------------


_REPO_WEB = Path(__file__).resolve().parents[2] / "web"


def _rendered_page(web: Path, url: str) -> Path:
    """The file a URL serves once deployed. The deploy copies the repository's
    committed web/ (the hand-authored pages) and the render together, so a
    page the fixture render does not write is looked up there."""
    path = url.removeprefix("https://gtfsscorecard.org/")
    if path == "" or path.endswith("/"):
        path += "index.html"
    rendered = web / path
    return rendered if rendered.is_file() else _REPO_WEB / path


@pytest.fixture
def rendered_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fixture = Path(__file__).parent / "fixtures" / "golden_site"
    root = tmp_path / "golden_site"
    shutil.copytree(fixture, root)
    (root / REMOVED_TWINS_FILENAME).write_text(
        "schema_version: 1\ntwins:\n  - {id: unitrans-351, kept: unitrans}\n"
    )
    monkeypatch.setenv("SCORECARD_ROOT", str(root))
    from scorecard_pipeline.render_site import render_site

    render_site(now=dt.datetime(2026, 7, 3, tzinfo=dt.UTC))
    return root / "web"


def test_render_redirects_a_moved_scorecards_companion_pages(rendered_golden: Path) -> None:
    web = rendered_golden
    manifest = json.loads((web / "_meta" / "retained-agency-redirects.json").read_text())
    for suffix in ("", "brief/", "board/", "fixes/"):
        source = f"/agency/unitrans-351/{suffix}"
        assert manifest["redirects"][source] == "/agency/unitrans/"
        stub = (web / source.lstrip("/") / "index.html").read_text()
        assert 'http-equiv="refresh" content="0; url=/agency/unitrans/"' in stub
    sitemap = (web / "sitemap.xml").read_text()
    assert "unitrans-351" not in sitemap


def _sitemap_problems(web: Path, sitemap: str) -> list[str]:
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    problems = [f"duplicate: {url}" for url in sorted(set(urls)) if urls.count(url) > 1]
    for url in urls:
        page = _rendered_page(web, url)
        if not page.is_file():
            problems.append(f"missing: {url}")
            continue
        html = page.read_text()
        if re.search(r'<meta name="robots"', html):
            problems.append(f"noindex: {url}")
        if 'http-equiv="refresh"' in html:
            problems.append(f"redirect: {url}")
        canonical = re.findall(r'<link rel="canonical" href="([^"]+)"', html)
        if canonical != [url]:
            problems.append(f"canonical {canonical}: {url}")
    return problems


def test_every_sitemap_url_is_an_indexable_self_canonical_page(rendered_golden: Path) -> None:
    """The sitemap lists only pages that answer, are indexable, do not redirect,
    and name themselves as canonical. Each failure is a Search Console
    'Not found', 'Excluded by noindex', 'Page with redirect' or 'Alternate page'
    entry the site would be asking Google to crawl."""
    sitemap = (rendered_golden / "sitemap.xml").read_text()
    assert "<loc>https://gtfsscorecard.org/agency/unitrans/</loc>" in sitemap
    problems = _sitemap_problems(rendered_golden, sitemap)
    assert problems == [], "\n".join(problems)


def test_sitemap_check_catches_each_defect_class(rendered_golden: Path) -> None:
    # Negative control: the same check over a sitemap that lists a noindex
    # brief, a redirect stub and a URL with no page reports all three.
    sitemap = (rendered_golden / "sitemap.xml").read_text()
    bad = "".join(
        f"<url><loc>https://gtfsscorecard.org/{path}</loc></url>"
        for path in ("agency/unitrans/brief/", "agency/unitrans-351/", "agency/no-such-page/")
    )
    problems = _sitemap_problems(rendered_golden, sitemap.replace("</urlset>", bad + "</urlset>"))
    assert any(p.startswith("noindex: ") and "unitrans/brief/" in p for p in problems)
    assert any(p.startswith("redirect: ") and "unitrans-351/" in p for p in problems)
    assert any(p.startswith("missing: ") and "no-such-page/" in p for p in problems)


def test_agency_sitemap_entries_carry_a_lastmod(rendered_golden: Path) -> None:
    sitemap = (rendered_golden / "sitemap.xml").read_text()
    entry = re.search(
        r"<url><loc>https://gtfsscorecard.org/agency/unitrans/</loc>(.*?)</url>", sitemap
    )
    assert entry is not None
    assert f"<lastmod>{AGENCY_TEMPLATE_REVISED}</lastmod>" in entry.group(1)
