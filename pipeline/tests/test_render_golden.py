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
