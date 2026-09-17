"""The Program Report Bundle's on-site sample (bundle_sample.py).

Before this existed, a buyer had to take /bundle/'s description of a branded
board report on faith; nothing on the site showed the actual format. These
tests hold four things: the sample renders correctly through the real
report-generation path; the score it shows is read from a real published
artifact, never fabricated; it is marked SAMPLE everywhere a reader could
land, so it can never be mistaken for a delivered order; and the generation
step is actually wired into the deploy pipeline (pages.yml), so it cannot go
stale the way a hand-run, hand-committed sample would.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from scorecard_pipeline.bundle_sample import (
    SAMPLE_AGENCY_ID,
    SAMPLE_CANONICAL_URL,
    SAMPLE_DESCRIPTION,
    SAMPLE_PROGRAM_NAME,
    build_bundle_sample,
)
from scorecard_pipeline.config import AGENCIES, Agency
from scorecard_pipeline.report import ReportError, generate_report

FROZEN = dt.datetime(2026, 7, 10, 12, 0, tzinfo=dt.UTC)
_REPO = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden_site"


def _generate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """Render the sample against the committed golden_site fixture, the same
    read-only fixture test_report_golden.py points at -- a real artifact tree,
    not hand-typed numbers."""
    if not FIXTURE_ROOT.exists():
        pytest.skip("golden fixture not available")
    monkeypatch.setenv("SCORECARD_ROOT", str(FIXTURE_ROOT))
    out = tmp_path / "sample.html"
    path = build_bundle_sample(out, now=FROZEN)
    return path, path.read_text()


# ---------------------------------------------------------------------------
# Renders correctly
# ---------------------------------------------------------------------------


def test_build_bundle_sample_writes_a_complete_html_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, html = _generate(tmp_path, monkeypatch)
    assert path == tmp_path / "sample.html"
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    # Exactly one h1, the same structural expectation report.py's own goldens
    # hold for a real report.
    assert html.count("<h1>") == 1


def test_default_out_path_is_under_web_bundle_sample() -> None:
    from scorecard_pipeline.bundle_sample import DEFAULT_SAMPLE_OUT

    assert Path("web") / "bundle" / "sample" / "index.html" == DEFAULT_SAMPLE_OUT


# ---------------------------------------------------------------------------
# Real score data, never fabricated
# ---------------------------------------------------------------------------


def test_sample_reads_the_real_published_artifact_for_its_agency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, html = _generate(tmp_path, monkeypatch)
    artifact = json.loads(
        (FIXTURE_ROOT / "data" / "artifacts" / SAMPLE_AGENCY_ID / "latest.json").read_text()
    )
    overall = artifact["overall"]
    agency_name = artifact["agency"]["name"]
    assert agency_name in html
    assert f"Grade {overall['grade']} &middot; {overall['score']} out of 100" in html
    # A finding pulled straight from the fixture's top_fixes, not paraphrased
    # or invented for the sample.
    first_fix = artifact["top_fixes"][0]["fix"]
    assert first_fix in html


def test_sample_agency_id_is_a_real_current_pilot_agency() -> None:
    # CLAUDE.md: Unitrans and Yolobus are this project's two pilot agencies,
    # both real and both scored since the pipeline's first phase. Picking one
    # by name keeps the choice reviewable instead of "whichever sorts first".
    assert SAMPLE_AGENCY_ID == "unitrans"


def test_build_bundle_sample_fails_loudly_if_the_agency_has_no_published_scorecard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No fixture, no fallback score: the same failure generate_report raises
    for any other agency with nothing published."""
    monkeypatch.setenv("SCORECARD_ROOT", str(tmp_path / "empty-repo"))
    with pytest.raises(ReportError, match="no published scorecard"):
        build_bundle_sample(tmp_path / "sample.html")


def test_build_bundle_sample_refuses_to_render_a_retired_sample_agency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never silently substitute a different agency or invent a score: if the
    chosen sample agency stops being a current, canonical registry entry,
    building the sample must raise, not quietly render something else."""
    if not FIXTURE_ROOT.exists():
        pytest.skip("golden fixture not available")
    monkeypatch.setenv("SCORECARD_ROOT", str(FIXTURE_ROOT))
    AGENCIES[SAMPLE_AGENCY_ID] = Agency(
        id=SAMPLE_AGENCY_ID,
        name="retired fixture",
        static_gtfs_url="https://example.org/g.zip",
        feed_status="inactive",
    )
    with pytest.raises(ReportError, match="no longer a current"):
        build_bundle_sample(tmp_path / "sample.html")


def test_build_bundle_sample_is_unblocked_when_the_registry_is_not_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Library/test compatibility mode, matching bundle.classify: an empty
    process-global registry has nothing to check the id against, so the
    artifact tree alone decides (and did, in every test above)."""
    assert AGENCIES == {}
    _, html = _generate(tmp_path, monkeypatch)
    assert html


# ---------------------------------------------------------------------------
# Marked SAMPLE throughout
# ---------------------------------------------------------------------------


def test_sample_carries_a_banner_a_chip_and_a_footer_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, html = _generate(tmp_path, monkeypatch)
    assert 'class="sample-banner" role="note"' in html
    assert "<strong>Sample report.</strong>" in html
    assert '<span class="sample-tag">Sample</span>' in html
    assert "your program&rsquo;s real branding" in html
    assert "A purchased bundle carries your program's own name" in html


def test_sample_title_and_metadata_say_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, html = _generate(tmp_path, monkeypatch)
    assert "transit data quality report — sample</title>" in html
    assert SAMPLE_DESCRIPTION.replace("'", "&#x27;") in html
    assert f'<link rel="canonical" href="{SAMPLE_CANONICAL_URL}">' in html
    assert '<meta name="robots" content="noindex,follow">' in html


def test_sample_uses_placeholder_branding_not_a_real_organization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, html = _generate(tmp_path, monkeypatch)
    assert f"Prepared by {SAMPLE_PROGRAM_NAME}" in html
    assert SAMPLE_PROGRAM_NAME == "Your Program Name Here"
    # The placeholder logo is embedded inline (never fetched from a URL) and
    # says exactly what it is.
    assert "data:image/svg+xml;base64," in html
    from scorecard_pipeline.bundle_sample import _SAMPLE_LOGO_SVG

    assert b"YOUR LOGO" in _SAMPLE_LOGO_SVG


def test_a_real_paid_reports_output_is_unaffected_by_sample_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate_report and render_report default to sample=False, the same
    call every real bundle.build_bundle report makes. Nothing SAMPLE-shaped
    should ever reach a buyer's actual archive."""
    if not FIXTURE_ROOT.exists():
        pytest.skip("golden fixture not available")
    monkeypatch.setenv("SCORECARD_ROOT", str(FIXTURE_ROOT))
    out = tmp_path / "real-report.html"
    generate_report(SAMPLE_AGENCY_ID, out=out, now=FROZEN)
    html = out.read_text()
    assert "sample" not in html.lower()
    assert "noindex" not in html
    assert "/src/measure.js" not in html
    assert "sample-banner" not in html


# ---------------------------------------------------------------------------
# Wired into the pipeline, so it cannot go stale
# ---------------------------------------------------------------------------


def test_cli_bundle_sample_subcommand_renders_the_real_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the same entry point pages.yml calls
    (`scorecard bundle-sample`), not just the library function underneath."""
    if not FIXTURE_ROOT.exists():
        pytest.skip("golden fixture not available")
    monkeypatch.setenv("SCORECARD_ROOT", str(FIXTURE_ROOT))
    from scorecard_pipeline.cli import main

    out = tmp_path / "cli-sample.html"
    assert main(["bundle-sample", "--out", str(out)]) == 0
    html = out.read_text()
    assert "<strong>Sample report.</strong>" in html


def test_pages_workflow_regenerates_the_sample_before_assembling_the_site() -> None:
    """A sample generated once by hand and committed would drift from the
    real scoring the moment an agency's grade changes. It has to be part of
    the same deploy that renders everything else, and it has to run before
    web/ is copied into _site/ or the fresh file never reaches production."""
    workflow = (_REPO / ".github" / "workflows" / "pages.yml").read_text()
    assert "scorecard bundle-sample" in workflow
    render_at = workflow.index("scorecard render-site")
    sample_at = workflow.index("scorecard bundle-sample")
    assemble_at = workflow.index("cp -r web/. _site/")
    assert render_at < sample_at < assemble_at


def test_bundle_page_links_to_the_sample_with_a_distinct_summary() -> None:
    """/bundle/'s own existing "see a live board report" link (the free,
    unbranded document) must stay exactly as it was; this only checks that a
    second, additive link to the branded sample was added beside it."""
    page = (_REPO / "web" / "bundle" / "index.html").read_text()
    assert 'href="/agency/unitrans/board/">See a live board report for one' in page
    assert 'href="/bundle/sample/"' in page
    assert "placeholder program name, logo, and accent color" in page


def test_noindex_pattern_covers_the_sample_route() -> None:
    """check_site_seo.py requires every configured noindex page to carry
    exactly `noindex,follow`; site-seo.json has to list the route or that
    check treats /bundle/sample/ as a page meant to rank."""
    config = json.loads((_REPO / "site-seo.json").read_text())
    assert "/bundle/sample/" in config["noindex_path_patterns"]
