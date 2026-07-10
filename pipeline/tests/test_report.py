"""Unit tests for the board-ready report module: brand loading, the pure
data-assembly step, the standalone renderer, and the CLI entry point."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.report import (
    DEFAULT_ACCENT,
    Brand,
    ReportError,
    _logo_data_uri,
    _validate_accent,
    build_report_data,
    generate_report,
    load_brand,
    main,
    render_report,
)

FROZEN = dt.datetime(2026, 7, 10, 12, 0, tzinfo=dt.UTC)


def _artifact(**overrides: Any) -> dict[str, Any]:
    """A minimal published artifact with the fields the report reads."""
    base: dict[str, Any] = {
        "schema_version": "1.5",
        "rubric_version": "1.2",
        "validator_version": "7.0.0",
        "snapshot_date": "2026-07-10",
        "agency": {"id": "sampletown", "name": "Sampletown Transit"},
        "overall": {"grade": "B", "score": 81.5},
        "categories": {
            "correctness": {
                "name": "correctness",
                "status": "measured",
                "score": 90.0,
                "weight": 0.35,
                "summary": "The validator flagged 2 kinds of issue.",
            },
            "freshness": {
                "name": "freshness",
                "status": "measured",
                "score": 100.0,
                "weight": 0.2,
                "summary": "Service data covers the next 60 days.",
            },
            "completeness": {
                "name": "completeness",
                "status": "measured",
                "score": 55.0,
                "weight": 0.25,
                "summary": "Wheelchair accessibility is unstated on most stops.",
            },
            "realtime": {
                "name": "realtime",
                "status": "not_yet_measured",
                "weight": 0.2,
                "summary": ("No realtime feed is published yet. Nothing counts against the grade."),
            },
        },
        "top_fixes": [
            {
                "rank": 1,
                "code": "scorecard_wheelchair_boarding_unknown",
                "what": "12 of 12 stops don't say whether a wheelchair user can board there.",
                "why": "Riders who use wheelchairs can't plan a trip.",
                "fix": "Set wheelchair_boarding for every stop.",
                "effort": "A column in stops.txt.",
            }
        ],
        "ntd_readiness": {
            "status": "ready",
            "summary": "This feed looks ready for your NTD certification.",
            "pillars": [
                {"key": "published", "status": "ready", "detail": "Published at a public URL."},
                {"key": "valid", "status": "ready", "detail": "Passes validation with no errors."},
                {
                    "key": "current",
                    "status": "ready",
                    "detail": "Service data covers the next 60 days.",
                },
            ],
        },
    }
    base.update(overrides)
    return base


def _history(*points: tuple[str, float, str]) -> list[dict[str, Any]]:
    return [{"date": d, "score": s, "grade": g, "categories": {}} for d, s, g in points]


# ---------------------------------------------------------------------------
# Brand loading
# ---------------------------------------------------------------------------


def test_validate_accent_accepts_hex_and_normalizes_case() -> None:
    assert _validate_accent("#2C5F70") == "#2c5f70"


@pytest.mark.parametrize("bad", ["2c5f70", "#2c5f7", "#2c5f7g", "teal", "#2c5f7000"])
def test_validate_accent_rejects_non_hex(bad: str) -> None:
    with pytest.raises(ReportError, match="rrggbb"):
        _validate_accent(bad)


def test_load_brand_full(tmp_path: Path) -> None:
    (tmp_path / "logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    brand_file = tmp_path / "brand.yaml"
    brand_file.write_text("name: Example Program\nlogo: logo.svg\naccent: '#2c5f70'\n")
    brand = load_brand(brand_file)
    assert brand.name == "Example Program"
    assert brand.accent == "#2c5f70"
    assert brand.logo_data_uri is not None
    assert brand.logo_data_uri.startswith("data:image/svg+xml;base64,")


def test_load_brand_defaults_accent_and_logo(tmp_path: Path) -> None:
    brand_file = tmp_path / "brand.yaml"
    brand_file.write_text("name: Example Program\n")
    brand = load_brand(brand_file)
    assert brand.accent == DEFAULT_ACCENT
    assert brand.logo_data_uri is None


def test_load_brand_requires_name(tmp_path: Path) -> None:
    brand_file = tmp_path / "brand.yaml"
    brand_file.write_text("accent: '#2c5f70'\n")
    with pytest.raises(ReportError, match="name"):
        load_brand(brand_file)


def test_load_brand_rejects_non_mapping(tmp_path: Path) -> None:
    brand_file = tmp_path / "brand.yaml"
    brand_file.write_text("- just\n- a list\n")
    with pytest.raises(ReportError, match="mapping"):
        load_brand(brand_file)


def test_load_brand_rejects_invalid_yaml(tmp_path: Path) -> None:
    brand_file = tmp_path / "brand.yaml"
    brand_file.write_text("name: [unclosed\n")
    with pytest.raises(ReportError, match="YAML"):
        load_brand(brand_file)


def test_load_brand_missing_file() -> None:
    with pytest.raises(ReportError, match="not readable"):
        load_brand(Path("/nonexistent/brand.yaml"))


def test_logo_data_uri_rejects_unknown_type(tmp_path: Path) -> None:
    logo = tmp_path / "logo.bmp"
    logo.write_bytes(b"BM")
    with pytest.raises(ReportError, match=r"logo\.bmp"):
        _logo_data_uri(logo)


def test_logo_data_uri_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ReportError, match="not readable"):
        _logo_data_uri(tmp_path / "gone.png")


def test_logo_data_uri_encodes_png(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n")
    assert _logo_data_uri(logo).startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------


def test_build_report_data_categories_in_rubric_order() -> None:
    data = build_report_data(_artifact(), [], generated_at=FROZEN)
    assert [c["key"] for c in data["categories"]] == [
        "correctness",
        "freshness",
        "completeness",
        "realtime",
    ]
    assert data["categories"][0]["label"] == "Correctness"


def test_build_report_data_unmeasured_category_stays_neutral() -> None:
    data = build_report_data(_artifact(), [], generated_at=FROZEN)
    realtime = data["categories"][3]
    assert realtime["measured"] is False
    assert realtime["score"] is None
    assert "counts against the grade" in realtime["summary"]


def test_build_report_data_caps_fixes_at_three() -> None:
    fixes = [{"rank": i, "fix": f"Fix {i}.", "what": "", "why": "", "effort": ""} for i in range(5)]
    data = build_report_data(_artifact(top_fixes=fixes), [], generated_at=FROZEN)
    assert len(data["fixes"]) == 3


def test_build_report_data_first_check_has_no_trend() -> None:
    data = build_report_data(_artifact(), _history(("2026-07-10", 81.5, "B")), generated_at=FROZEN)
    assert data["trend_line"] == "First check for this agency, so there is no trend yet."
    assert data["history"][0]["change"] == "first check"


def test_build_report_data_history_change_words() -> None:
    hist = _history(("2026-07-08", 78.0, "C"), ("2026-07-09", 81.5, "B"), ("2026-07-10", 81.5, "B"))
    data = build_report_data(_artifact(), hist, generated_at=FROZEN)
    changes = [row["change"] for row in data["history"]]
    assert changes == ["first check", "up 3.5", "no change"]
    assert data["trend_line"] == "Unchanged since 2026-07-09."


def test_build_report_data_ntd_for_us_agency() -> None:
    data = build_report_data(_artifact(), [], generated_at=FROZEN)
    assert data["ntd"] is not None
    assert data["ntd"]["status_label"] == "Ready"
    assert [p["name"] for p in data["ntd"]["pillars"]] == ["Published", "Valid", "Current"]


def test_build_report_data_no_ntd_for_non_us_agency() -> None:
    artifact = _artifact(agency={"id": "barrie", "name": "Barrie Transit", "country": "CA"})
    data = build_report_data(artifact, [], generated_at=FROZEN)
    assert data["ntd"] is None


def test_build_report_data_shapes_row_recomputed_from_counts() -> None:
    artifact = _artifact(shapes_readiness={"total_trips": 10, "trips_with_shape": 4})
    data = build_report_data(artifact, [], generated_at=FROZEN)
    shapes = data["ntd"]["shapes"]
    assert shapes["label"] == "Needs attention"
    assert "4 of 10 trips" in shapes["detail"]
    assert "shapes.txt" in shapes["detail"]  # the fix sentence rides along


def test_build_report_data_carries_ntd_note() -> None:
    artifact = _artifact(
        agency={"id": "a", "name": "A", "ntd_note": "Reports under a shared regional feed."}
    )
    data = build_report_data(artifact, [], generated_at=FROZEN)
    assert data["ntd"]["note"] == "Reports under a shared regional feed."


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render(
    artifact: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    brand: Brand | None = None,
) -> str:
    data = build_report_data(artifact or _artifact(), history or [], generated_at=FROZEN)
    return render_report(data, brand)


def test_render_report_is_self_contained() -> None:
    html_text = _render()
    assert 'lang="en"' in html_text
    assert "<style>" in html_text
    for marker in ("http://", "https://"):
        # The only network references are citation links, never loaded assets.
        for line in html_text.splitlines():
            if marker in line:
                assert "<a href=" in line or "xmlns" in line, line
    assert "<script" not in html_text
    assert '<link rel="stylesheet"' not in html_text


def test_render_report_escapes_agency_name() -> None:
    artifact = _artifact(agency={"id": "x", "name": "Ride<script>alert(1)</script>"})
    html_text = _render(artifact)
    assert "<script>" not in html_text
    assert "Ride&lt;script&gt;" in html_text


def test_render_report_tables_carry_scope() -> None:
    hist = _history(("2026-07-09", 80.0, "B"), ("2026-07-10", 81.5, "B"))
    html_text = _render(history=hist)
    assert '<th scope="col">Category</th>' in html_text
    assert '<th scope="row">Correctness</th>' in html_text
    assert '<th scope="col">Check</th>' in html_text
    assert '<th scope="row">2026-07-10</th>' in html_text


def test_render_report_unmeasured_realtime_shows_no_number() -> None:
    html_text = _render()
    assert "Not yet published" in html_text


def test_render_report_omits_trend_on_first_check() -> None:
    html_text = _render(history=_history(("2026-07-10", 81.5, "B")))
    assert "Over time" not in html_text


def test_render_report_trend_change_in_words_not_color() -> None:
    hist = _history(("2026-07-09", 80.0, "B"), ("2026-07-10", 81.5, "B"))
    html_text = _render(history=hist)
    assert "up 1.5" in html_text
    assert "Up 1.5 points since 2026-07-09" in html_text


def test_render_report_long_history_capped_with_note() -> None:
    hist = _history(*[(f"2026-06-{d:02d}", 70.0 + d, "C") for d in range(1, 21)])
    html_text = _render(history=hist)
    assert "Showing the 12 most recent of 20 checks." in html_text


def test_render_report_branding_appears_and_default_stays_neutral() -> None:
    brand = Brand(
        name="Example Program", logo_data_uri="data:image/png;base64,AAAA", accent="#2c5f70"
    )
    branded = _render(brand=brand)
    assert "Prepared by Example Program" in branded
    assert 'alt="Example Program logo"' in branded
    assert "#2c5f70" in branded
    plain = _render()
    assert "Prepared by" not in plain
    assert DEFAULT_ACCENT in plain
    assert "Produced by the GTFS Scorecard" in plain


def test_render_report_accent_never_colors_text() -> None:
    brand = Brand(name="Example Program", accent="#ffff00")
    html_text = _render(brand=brand)
    for line in html_text.splitlines():
        if "#ffff00" in line:
            assert "background:" in line or "border" in line, line


def test_render_report_footer_cites_rubric_and_timestamp() -> None:
    html_text = _render()
    assert "docs/rubric.md" in html_text
    assert "rubric v1.2" in html_text
    assert "validator 7.0.0" in html_text
    assert "2026-07-10 12:00 UTC" in html_text
    assert "not an official compliance determination" in html_text


def test_render_report_no_fixes_reads_as_upkeep() -> None:
    html_text = _render(_artifact(top_fixes=[]))
    assert "continued upkeep" in html_text


def test_render_report_print_rules_present() -> None:
    html_text = _render()
    assert "@media print" in html_text
    assert "break-inside: avoid" in html_text
    assert "break-before: page" in html_text


# ---------------------------------------------------------------------------
# Loading + CLI
# ---------------------------------------------------------------------------


def _publish_fixture(root: Path, agency_id: str = "sampletown") -> None:
    art = root / "data" / "artifacts"
    (art / agency_id).mkdir(parents=True)
    (art / agency_id / "latest.json").write_text(json.dumps(_artifact()))
    index = {
        "schema_version": "1",
        "agencies": {
            agency_id: {
                "name": "Sampletown Transit",
                "history": _history(("2026-07-09", 80.0, "B"), ("2026-07-10", 81.5, "B")),
            }
        },
    }
    (art / "index.json").write_text(json.dumps(index))


def test_generate_report_writes_file(isolated_repo_root: Path, tmp_path: Path) -> None:
    _publish_fixture(isolated_repo_root)
    out = tmp_path / "out" / "sampletown.html"
    path = generate_report("sampletown", out=out, now=FROZEN)
    assert path == out
    text = out.read_text()
    assert "Sampletown Transit" in text
    assert "Up 1.5 points since 2026-07-09" in text


def test_generate_report_unknown_agency_names_the_path(isolated_repo_root: Path) -> None:
    _publish_fixture(isolated_repo_root)
    with pytest.raises(ReportError, match="no published scorecard for 'nowhere'"):
        generate_report("nowhere", now=FROZEN)


def test_generate_report_tolerates_missing_index(isolated_repo_root: Path, tmp_path: Path) -> None:
    _publish_fixture(isolated_repo_root)
    (isolated_repo_root / "data" / "artifacts" / "index.json").unlink()
    out = tmp_path / "sampletown.html"
    generate_report("sampletown", out=out, now=FROZEN)
    assert "no trend yet" in out.read_text()


def test_main_renders_report(
    isolated_repo_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_fixture(isolated_repo_root)
    out = tmp_path / "report.html"
    assert main(["--agency", "sampletown", "--out", str(out)]) == 0
    assert str(out) in capsys.readouterr().out
    assert out.exists()


def test_main_with_brand_file(isolated_repo_root: Path, tmp_path: Path) -> None:
    _publish_fixture(isolated_repo_root)
    brand_file = tmp_path / "brand.yaml"
    brand_file.write_text("name: Example Program\naccent: '#2c5f70'\n")
    out = tmp_path / "report.html"
    assert main(["--agency", "sampletown", "--brand", str(brand_file), "--out", str(out)]) == 0
    assert "Prepared by Example Program" in out.read_text()


def test_main_reports_errors_plainly(
    isolated_repo_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_fixture(isolated_repo_root)
    assert main(["--agency", "nowhere", "--out", str(tmp_path / "x.html")]) == 2
    assert "no published scorecard" in capsys.readouterr().err


def test_cli_subcommand_dispatches(isolated_repo_root: Path, tmp_path: Path) -> None:
    from scorecard_pipeline.cli import main as cli_main

    _publish_fixture(isolated_repo_root)
    # cli.main() loads the agency registry up front, so give the isolated
    # repo root a minimal valid one.
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: sampletown\n"
        "    name: Sampletown Transit\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )
    out = tmp_path / "report.html"
    assert cli_main(["report", "--agency", "sampletown", "--out", str(out)]) == 0
    assert out.exists()
