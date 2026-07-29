"""Golden-file tests: render_site output must be byte-identical to committed golden files.

This harness guards against unintended changes to every published page. The golden
files are committed, so a rendering change fails CI with a readable diff, and the
intentional change is reviewed before goldens are regenerated with `make
golden-refresh`.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def golden_root() -> Path:
    """Path to the committed golden HTML files."""
    return Path(__file__).parent / "goldens"


@pytest.fixture
def golden_fixture_root() -> Path:
    """Path to the minimal fixture data (three agencies, sample rollups, etc.)."""
    return Path(__file__).parent / "fixtures" / "golden_site"


def test_committed_fixture_web_matches_rendered_goldens(
    golden_fixture_root: Path, golden_root: Path
) -> None:
    """The committed fixture's generated web seed must not lag its goldens.

    Rendering into a scratch copy overwrites these files and can otherwise mask
    stale public JSON or HTML in the fixture itself. Report goldens belong to a
    separate on-demand generator and are not part of the static-site seed.
    """
    fixture_web = golden_fixture_root / "web"
    mismatches: list[str] = []
    for golden in sorted(golden_root.rglob("*")):
        if not golden.is_file():
            continue
        rel = golden.relative_to(golden_root)
        if rel.parts[0] == "report":
            continue
        fixture = fixture_web / rel
        if not fixture.exists() or fixture.read_bytes() != golden.read_bytes():
            mismatches.append(str(rel))
    assert not mismatches, "Fixture web seed differs from goldens:\n" + "\n".join(mismatches)


def test_render_site_golden_output(golden_fixture_root: Path, golden_root: Path) -> None:
    """render_site output on a scratch copy of the fixture is byte-identical to goldens.

    The fixture captures real agency artifacts (unitrans, yolobus, barrie-transit),
    so this exercises the full pipeline without external dependencies. The fixture
    tree is copied into a scratch temp directory before rendering, and
    SCORECARD_ROOT is pointed at that copy, so a run of this test never writes
    into (or dirties git status for) the committed fixture tree. Any diff to the
    HTML output fails the test and names the changed file.
    """
    if not golden_fixture_root.exists():
        pytest.skip("golden fixture not available (run `make golden-capture`)")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Render into a scratch copy of the fixture tree, never the committed
        # fixture itself.
        scratch_root = Path(tmpdir) / "golden_site"
        shutil.copytree(golden_fixture_root, scratch_root)
        os.environ["SCORECARD_ROOT"] = str(scratch_root)

        # Seed unsupported output from an earlier render. The current render
        # must remove it even when no replacement is available.
        stale_fixlog = scratch_root / "web" / "agency" / "unitrans" / "fixes"
        stale_fixlog.mkdir(parents=True, exist_ok=True)
        (stale_fixlog / "index.html").write_text("unsupported legacy fix claim")
        stale_ridership = scratch_root / "web" / "api" / "v1" / "ridership-impact.json"
        stale_ridership.parent.mkdir(parents=True, exist_ok=True)
        stale_ridership.write_text('{"weighted_average_score": 53.3}\n')
        legacy_changes = scratch_root / "data" / "artifacts" / "changes"
        legacy_changes.mkdir(parents=True, exist_ok=True)
        legacy_change = legacy_changes / "2026-06-20.json"
        legacy_change.write_text('{"count": 1, "changes": [{"id": "legacy"}]}\n')

        # Import after env is set so the config picks up the fixture root.
        from scorecard_pipeline.render_site import render_site

        # Freeze "now" for the liveness "checked N hours/days ago" prose (see
        # _liveness_note/_ago in render_site.py) so the golden comparison is
        # deterministic no matter when the suite runs. Derived from the
        # fixture's own committed, unchanging liveness timestamps rather than
        # the real wall clock.
        liveness = json.loads((scratch_root / "data" / "liveness.json").read_text())
        checked_ats = [
            dt.datetime.fromisoformat(str(feed["checked_at"]))
            for feed in liveness.get("feeds", {}).values()
            if feed.get("checked_at")
        ]
        now = (max(checked_ats) if checked_ats else dt.datetime.now(dt.UTC)) + dt.timedelta(hours=2)

        written = render_site(now=now)
        web = scratch_root / "web"
        # A standalone render fails closed instead of preserving stale output.
        assert not (web / "agency" / "unitrans" / "fixes").exists()
        assert not stale_ridership.exists()
        assert not legacy_change.exists()
        sitemap = (web / "sitemap.xml").read_text()
        assert (
            "<loc>https://gtfsscorecard.org/fix/expired_calendar/</loc>"
            "<lastmod>2026-07-03</lastmod>"
        ) in sitemap
        assert (
            "<loc>https://gtfsscorecard.org/crosswalk/</loc><lastmod>2026-07-14</lastmod>"
        ) in sitemap
        assert "<loc>https://gtfsscorecard.org/concept/</loc>" not in sitemap
        assert "<loc>https://gtfsscorecard.org/changes/</loc>" not in sitemap
        assert "<loc>https://gtfsscorecard.org/access/</loc>" not in sitemap
        assert "<loc>https://gtfsscorecard.org/trends/</loc>" not in sitemap
        assert "<loc>https://gtfsscorecard.org/leaderboard/</loc>" not in sitemap
        assert "<loc>https://gtfsscorecard.org/how-to-read/</loc>" in sitemap
        assert "<loc>https://gtfsscorecard.org/pulse/</loc>" in sitemap
        assert "<loc>https://gtfsscorecard.org/adoption/</loc>" in sitemap

        # Check that every rendered file matches its golden.
        mismatches = []
        for src in sorted(written):
            rel = src.relative_to(web)
            golden = golden_root / rel
            if not golden.exists():
                mismatches.append(f"New file (not in goldens): {rel}")
                continue
            actual = src.read_text(errors="replace")
            expected = golden.read_text(errors="replace")
            # Some JSON files have generated_at timestamps (wall-clock dependent).
            # Mask them out for deterministic comparison.
            is_json = str(rel).endswith(".json") or str(rel).endswith(".geojson")
            if is_json and "generated_at" in actual:
                try:
                    actual_obj = json.loads(actual)
                    expected_obj = json.loads(expected)
                    actual_obj.pop("generated_at", None)
                    expected_obj.pop("generated_at", None)
                    actual = json.dumps(actual_obj, indent=2, sort_keys=True)
                    expected = json.dumps(expected_obj, indent=2, sort_keys=True)
                except (json.JSONDecodeError, ValueError):
                    pass  # Not JSON, compare as text
            if actual != expected:
                mismatches.append(str(rel))

        if mismatches:
            msg = "Golden file mismatch:\n" + "\n".join(f"  {m}" for m in mismatches)
            pytest.fail(msg)

        # Check that no goldens were left behind (render removed a page).
        # goldens/report/ belongs to the board-ready report generator, which
        # runs on demand rather than in render_site; test_report_golden.py
        # owns that subtree.
        rendered_rels = {f.relative_to(web) for f in written}
        golden_rels = {
            f.relative_to(golden_root)
            for f in golden_root.rglob("*")
            if f.is_file() and f.relative_to(golden_root).parts[0] != "report"
        }
        missing = golden_rels - rendered_rels
        if missing:
            lines = "\n".join(f"  {m}" for m in sorted(missing))
            msg = "Files in goldens but not rendered:\n" + lines
            pytest.fail(msg)


def test_render_site_emits_paginated_directory_chain_and_cleans_stale_pages(
    golden_fixture_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scratch_root = tmp_path / "paginated_site"
    shutil.copytree(golden_fixture_root, scratch_root)
    monkeypatch.setenv("SCORECARD_ROOT", str(scratch_root))

    import scorecard_pipeline.render_site as renderer

    monkeypatch.setattr(renderer, "_AGENCY_INDEX_PAGE_SIZE", 2)
    stale = scratch_root / "web" / "agencies" / "page" / "99" / "index.html"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale generated page")

    renderer.render_site(now=dt.datetime(2026, 7, 2, 12, tzinfo=dt.UTC))

    web = scratch_root / "web"
    first = (web / "agencies" / "index.html").read_text()
    second = (web / "agencies" / "page" / "2" / "index.html").read_text()
    sitemap = (web / "sitemap.xml").read_text()

    assert not stale.exists()
    assert not (web / "agencies" / "page" / "3").exists()
    assert 'rel="next" href="https://gtfsscorecard.org/agencies/page/2/"' in first
    assert 'rel="prev" href="https://gtfsscorecard.org/agencies/"' in second
    assert '<link rel="canonical" href="https://gtfsscorecard.org/agencies/page/2/">' in second
    assert "https://gtfsscorecard.org/agencies/page/2/" in sitemap
    agency_links = [
        link for html in (first, second) for link in re.findall(r'href="/agency/([^/]+)/"', html)
    ]
    assert sorted(agency_links) == ["barrie-transit", "unitrans", "yolobus"]
