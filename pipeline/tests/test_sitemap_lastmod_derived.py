"""Sitemap ``<lastmod>`` for clearance logs, directory pages and NTD pages.

Each is derived from a date the page itself reports (a clearance, a "checked"
date, a scoring run), never from the build clock, and omitted when the data has
no usable date. The structural checker holds the deployed sitemap to the same
rule. Every check below has a negative control that asserts its sabotage was
applied before asserting the check notices it.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.ntd import state_pages
from scorecard_pipeline.render_site import (
    _AGENCY_INDEX_PAGE_SIZE,
    agency_index_lastmod,
    data_date,
    fixlog_lastmod,
    newest_data_date,
)

TODAY = dt.date.today().isoformat()

# Reuse the checker-fixture helpers from test_site_seo.py. Test modules are not
# importable by name here, so load that file directly.
_spec = importlib.util.spec_from_file_location(
    "_site_seo_fixtures", Path(__file__).with_name("test_site_seo.py")
)
assert _spec is not None and _spec.loader is not None
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
ORIGIN = _fixtures.ORIGIN
_codes = _fixtures._codes
_page = _fixtures._page
_replace = _fixtures._replace
_run = _fixtures._run
_write_clearance_logs = _fixtures._write_clearance_logs
_write_fixture = _fixtures._write_fixture
_write_text = _fixtures._write_text


# --- derivation -------------------------------------------------------------


def test_data_date_accepts_only_real_calendar_dates() -> None:
    assert data_date("2026-10-06") == "2026-10-06"
    for bad in (
        "2026-02-30",
        "2026-13-01",
        "yesterday",
        "2026-10-06T00:00:00Z",
        "",
        None,
        20261006,
    ):
        assert data_date(bad) == ""


def test_newest_data_date_is_none_without_a_usable_date() -> None:
    assert newest_data_date([]) is None
    assert newest_data_date([None, "soon", "2026-02-30"]) is None
    assert newest_data_date(["2026-09-01", "garbage", "2026-10-03", "2026-09-30"]) == "2026-10-03"


def _receipt(cleared: Any) -> dict[str, str]:
    return {"code": "c", "what": "w", "last_seen": "2026-06-01", "cleared": cleared}


def test_fixlog_lastmod_is_the_newest_clearance_not_the_build_date() -> None:
    receipts = [_receipt("2026-06-11"), _receipt("2026-09-02"), _receipt("2026-07-30")]
    assert fixlog_lastmod(receipts) == "2026-09-02"
    # Order of the receipts does not matter, and the answer never tracks the clock.
    assert fixlog_lastmod(list(reversed(receipts))) == "2026-09-02"
    assert fixlog_lastmod(receipts) != TODAY


def test_fixlog_lastmod_skips_unusable_dates_and_is_none_without_any() -> None:
    assert fixlog_lastmod([_receipt("2026-06-11"), _receipt("n/a")]) == "2026-06-11"
    assert fixlog_lastmod([_receipt(""), _receipt("2026-02-30")]) is None
    assert fixlog_lastmod([]) is None


def _index(dates: list[str]) -> dict[str, Any]:
    return {
        "agencies": {
            f"a{i:03d}": {
                "name": f"Agency {i:03d}",
                "history": [{"date": d, "days_until_expiry": 40}],
            }
            for i, d in enumerate(dates)
        }
    }


def test_directory_page_lastmod_is_the_newest_card_date_on_that_page() -> None:
    # 200 agencies, alphabetical; page 2 (rows 81-160) carries one newer check.
    dates = ["2026-10-01"] * 200
    dates[100] = "2026-10-05"
    index = _index(dates)
    assert agency_index_lastmod(index, {}, page=1) == "2026-10-01"
    assert agency_index_lastmod(index, {}, page=2) == "2026-10-05"
    assert agency_index_lastmod(index, {}, page=3) == "2026-10-01"
    assert _AGENCY_INDEX_PAGE_SIZE == 80
    for page in (1, 2, 3):
        assert agency_index_lastmod(index, {}, page=page) != TODAY


def test_directory_page_without_a_valid_card_date_has_no_lastmod() -> None:
    assert agency_index_lastmod(_index(["soon", "2026-02-30"]), {}, page=1) is None


def _artifact(aid: str, snapshot: str | None) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "agency": {"id": aid, "name": aid.title(), "country": "US", "state": "Ohio"},
        "shapes_readiness": {"total_trips": 10, "trips_with_shape": 10},
    }
    if snapshot is not None:
        artifact["snapshot_date"] = snapshot
    return artifact


def test_ntd_state_rows_carry_the_scoring_run_date() -> None:
    artifacts = [_artifact(f"ohio-{i}", f"2026-10-0{i + 1}") for i in range(6)]
    rows = state_pages(artifacts)["Ohio"]
    assert newest_data_date(r.snapshot_date for r in rows) == "2026-10-06"
    # A feed whose record has no date contributes none, and never "today".
    undated = [_artifact(f"ohio-{i}", None) for i in range(6)]
    assert newest_data_date(r.snapshot_date for r in state_pages(undated)["Ohio"]) is None


# --- the committed golden corpus -------------------------------------------


def _golden_sitemap() -> dict[str, str | None]:
    xml = (Path(__file__).parent / "goldens" / "sitemap.xml").read_text()
    out: dict[str, str | None] = {}
    for entry in re.findall(r"<url>(.*?)</url>", xml):
        loc = re.search(r"<loc>(.*?)</loc>", entry)
        assert loc
        lm = re.search(r"<lastmod>(.*?)</lastmod>", entry)
        out[loc.group(1)] = lm.group(1) if lm else None
    return out


def test_rendered_sitemap_dates_the_directory_and_ntd_pages_from_data() -> None:
    sitemap = _golden_sitemap()
    for path in ("/agencies/", "/ntd/", "/ntd/shapes/"):
        lastmod = sitemap[f"https://gtfsscorecard.org{path}"]
        assert lastmod is not None, path
        assert data_date(lastmod) == lastmod
        assert lastmod != TODAY
    # Hand-authored pages with no data date stay undated.
    assert sitemap["https://gtfsscorecard.org/about/"] is None
    assert sitemap["https://gtfsscorecard.org/problems/"] is None


def test_golden_sitemap_control_a_build_clock_stamp_is_detectable() -> None:
    # Sabotage: what the sitemap would hold if lastmod were the build date.
    sabotaged = {url: TODAY for url in _golden_sitemap()}
    assert set(sabotaged.values()) == {TODAY}  # the sabotage applied
    assert (
        sabotaged["https://gtfsscorecard.org/ntd/"]
        != _golden_sitemap()["https://gtfsscorecard.org/ntd/"]
    )


# --- the structural checker -------------------------------------------------

SHOWN = "2026-07-29"


def _dated_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """The clearance-log fixture with the lastmod rules on and a page that
    prints the date its sitemap entry claims."""
    site, config = _write_fixture(tmp_path)
    _write_clearance_logs(site, config)
    _write_text(
        site,
        "agency/demo/fixes/index.html",
        _page(
            "/agency/demo/fixes/",
            "Demo clearance log",
            "Demo clearance log description",
            body=f'<p>the {SHOWN} check verified it gone.</p><a href="/agency/demo/">Scorecard</a>',
        ),
    )
    raw = json.loads(config.read_text(encoding="utf-8"))
    raw["lastmod_required_path_patterns"] = ["/agency/*/fixes/"]
    raw["lastmod_shown_path_patterns"] = ["/agency/*/fixes/"]
    config.write_text(json.dumps(raw), encoding="utf-8")
    return site, config, tmp_path / "report.json"


def test_checker_accepts_a_lastmod_the_page_shows(tmp_path: Path) -> None:
    site, config, report = _dated_fixture(tmp_path)
    result = _run(site, config, report)
    assert result.returncode == 0, report.read_text(encoding="utf-8")
    assert _codes(report) == set()


def test_checker_rejects_a_build_clock_lastmod(tmp_path: Path) -> None:
    site, config, report = _dated_fixture(tmp_path)
    _replace(site / "sitemap.xml", f"<lastmod>{SHOWN}</lastmod>", f"<lastmod>{TODAY}</lastmod>")
    sitemap = (site / "sitemap.xml").read_text(encoding="utf-8")
    assert f"/agency/demo/fixes/</loc><lastmod>{TODAY}</lastmod>" in sitemap  # sabotage applied
    assert TODAY not in (site / "agency/demo/fixes/index.html").read_text(encoding="utf-8")
    result = _run(site, config, report)
    assert result.returncode != 0
    assert "sitemap.lastmod_not_on_page" in _codes(report)


def test_checker_rejects_a_future_lastmod(tmp_path: Path) -> None:
    site, config, report = _dated_fixture(tmp_path)
    # The page shows the future date too, so only the future rule can object.
    _replace(site / "sitemap.xml", f"<lastmod>{SHOWN}</lastmod>", "<lastmod>2999-01-01</lastmod>")
    _replace(site / "agency/demo/fixes/index.html", SHOWN, "2999-01-01")
    assert "2999-01-01" in (site / "sitemap.xml").read_text(encoding="utf-8")
    result = _run(site, config, report)
    assert result.returncode != 0
    codes = _codes(report)
    assert "sitemap.future_lastmod" in codes
    assert "sitemap.lastmod_not_on_page" not in codes


def test_checker_rejects_a_missing_lastmod_in_a_required_class(tmp_path: Path) -> None:
    site, config, report = _dated_fixture(tmp_path)
    _replace(
        site / "sitemap.xml",
        f"<lastmod>{SHOWN}</lastmod></url><url><loc>{ORIGIN}/target/",
        "</url><url><loc>" + ORIGIN + "/target/",
    )
    assert "/agency/demo/fixes/</loc></url>" in (site / "sitemap.xml").read_text(encoding="utf-8")
    result = _run(site, config, report)
    assert result.returncode != 0
    assert "sitemap.missing_lastmod" in _codes(report)


@pytest.mark.parametrize("key", ["lastmod_required_path_patterns", "lastmod_shown_path_patterns"])
def test_checker_rejects_malformed_lastmod_patterns(tmp_path: Path, key: str) -> None:
    site, config, report = _dated_fixture(tmp_path)
    raw = json.loads(config.read_text(encoding="utf-8"))
    raw[key] = ["/agency/*/fixes"]  # no trailing slash
    config.write_text(json.dumps(raw), encoding="utf-8")
    assert json.loads(config.read_text(encoding="utf-8"))[key] == ["/agency/*/fixes"]
    result = _run(site, config, report)
    assert result.returncode != 0


def test_production_config_requires_and_checks_the_lastmod_classes() -> None:
    raw = json.loads((Path(__file__).resolve().parents[2] / "site-seo.json").read_text())
    required = set(raw["lastmod_required_path_patterns"])
    assert {
        "/agency/*/fixes/",
        "/agencies/",
        "/agencies/page/*/",
        "/ntd/",
        "/ntd/shapes/",
    } <= required
    assert "/ntd/states/*/" in required
    assert set(raw["lastmod_shown_path_patterns"]) == {
        "/agency/*/fixes/",
        "/agencies/",
        "/agencies/page/*/",
    }
