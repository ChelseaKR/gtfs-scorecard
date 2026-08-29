"""Golden-file tests: report output must be byte-identical to committed goldens.

Same harness idea as test_render_golden.py, pointed at the board-ready report
generator instead of render_site. The goldens live under tests/goldens/report/
(test_render_golden.py knows to leave that subtree to this file, since these
documents are generated on demand rather than by render_site). The generation
timestamp is frozen so the comparison is deterministic.

After an intentional rendering change, regenerate and review the diff:

    cd pipeline && REPORT_GOLDEN_REGEN=1 uv run pytest tests/test_report_golden.py
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

FROZEN = dt.datetime(2026, 7, 10, 12, 0, tzinfo=dt.UTC)

GOLDEN_ROOT = Path(__file__).parent / "goldens" / "report"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden_site"
BRAND_FILE = Path(__file__).parent / "fixtures" / "brand" / "brand.yaml"


def _generate(
    agency_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    brand_file: Path | None = None,
) -> str:
    """Render one report from the committed golden_site fixture (read-only)."""
    if not FIXTURE_ROOT.exists():
        pytest.skip("golden fixture not available")
    monkeypatch.setenv("SCORECARD_ROOT", str(FIXTURE_ROOT))
    from scorecard_pipeline.report import generate_report, load_brand

    brand = load_brand(brand_file) if brand_file else None
    out = tmp_path / f"{agency_id}.html"
    generate_report(agency_id, brand=brand, out=out, now=FROZEN)
    return out.read_text()


def _compare(actual: str, golden_name: str) -> None:
    golden = GOLDEN_ROOT / golden_name
    if os.environ.get("REPORT_GOLDEN_REGEN"):
        # This flag turns the assertion below into a write. That is what
        # `make golden-refresh` wants and is the last thing an automated run
        # wants: set in the environment of a CI job, every report golden test
        # would pass by rewriting its own baseline, and the suite would report
        # green having compared nothing. It is a local tool, so refuse it
        # anywhere that looks like CI rather than trusting that nobody exports
        # it. tests/test_report_golden.py::test_the_regeneration_hatch_is_
        # refused_in_ci holds this.
        if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
            pytest.fail(
                "REPORT_GOLDEN_REGEN rewrites the golden instead of comparing to "
                "it. Refusing to do that in CI: the run would be green having "
                "checked nothing. Regenerate locally with `make golden-refresh` "
                "and commit the result for review."
            )
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(actual)
        return
    if not golden.exists():
        pytest.fail(f"missing golden {golden_name}; regenerate with REPORT_GOLDEN_REGEN=1")
    if actual != golden.read_text():
        pytest.fail(f"report golden mismatch: {golden_name}")


def test_unbranded_report_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unitrans: legacy US artifact, NTD shapes check absent, 20 checks."""
    _compare(_generate("unitrans", tmp_path, monkeypatch), "unitrans.html")


def test_branded_report_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy Yolobus artifact: branded cover plus conservative NTD status."""
    actual = _generate("yolobus", tmp_path, monkeypatch, brand_file=BRAND_FILE)
    _compare(actual, "yolobus-branded.html")


def test_non_us_report_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Barrie Transit: a Canadian agency's report carries no NTD section."""
    actual = _generate("barrie-transit", tmp_path, monkeypatch)
    assert "NTD" not in actual
    _compare(actual, "barrie-transit.html")


def test_the_regeneration_hatch_is_refused_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    """REPORT_GOLDEN_REGEN is the one environment variable in this suite that
    converts an assertion into a write. Nothing stopped it being exported in a
    CI environment, where it would have made every report golden test pass by
    rewriting the file it was supposed to be checking."""
    monkeypatch.setenv("REPORT_GOLDEN_REGEN", "1")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    with pytest.raises(pytest.fail.Exception, match="Refusing to do that in CI"):
        _compare("whatever", "this-golden-must-not-be-written.html")

    assert not (GOLDEN_ROOT / "this-golden-must-not-be-written.html").exists()


def test_the_regeneration_hatch_still_works_outside_ci(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The refusal is scoped to CI. `make golden-refresh` still regenerates."""
    monkeypatch.setenv("REPORT_GOLDEN_REGEN", "1")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr("tests.test_report_golden.GOLDEN_ROOT", tmp_path)

    _compare("rendered bytes", "scratch.html")

    assert (tmp_path / "scratch.html").read_text() == "rendered bytes"
