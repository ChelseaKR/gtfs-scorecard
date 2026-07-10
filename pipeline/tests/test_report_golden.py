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
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(actual)
        return
    if not golden.exists():
        pytest.fail(f"missing golden {golden_name}; regenerate with REPORT_GOLDEN_REGEN=1")
    if actual != golden.read_text():
        pytest.fail(f"report golden mismatch: {golden_name}")


def test_unbranded_report_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unitrans: US agency, NTD ready, realtime not yet measured, 20 checks."""
    _compare(_generate("unitrans", tmp_path, monkeypatch), "unitrans.html")


def test_branded_report_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Yolobus with the fixture brand: cover line, embedded SVG logo, accent."""
    actual = _generate("yolobus", tmp_path, monkeypatch, brand_file=BRAND_FILE)
    _compare(actual, "yolobus-branded.html")


def test_non_us_report_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Barrie Transit: a Canadian agency's report carries no NTD section."""
    actual = _generate("barrie-transit", tmp_path, monkeypatch)
    assert "NTD" not in actual
    _compare(actual, "barrie-transit.html")
