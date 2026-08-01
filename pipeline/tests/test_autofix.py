"""Tests for the deterministic auto-fix layer."""

from __future__ import annotations

import inspect
import zipfile
from collections.abc import Callable
from pathlib import Path

from scorecard_pipeline.autofix import apply_fixes, autofix_zip, render_report
from scorecard_pipeline.cli import _dispatch, run_agency
from scorecard_pipeline.gtfs import read_tables


def test_recases_shouty_stop_names_but_leaves_acronyms() -> None:
    tables = {
        "stops.txt": [
            {"stop_id": "1", "stop_name": "MAIN ST & 2ND AVE"},
            {"stop_id": "2", "stop_name": "UCD"},  # short acronym, left alone
            {"stop_id": "3", "stop_name": "Davis Depot"},  # already mixed
            {"stop_id": "4", "stop_name": "那須町役場前"},  # uncased script, left alone
        ]
    }
    results = {r.code: r for r in apply_fixes(tables)}
    assert tables["stops.txt"][0]["stop_name"] == "Main St & 2nd Ave"
    assert tables["stops.txt"][1]["stop_name"] == "UCD"
    assert tables["stops.txt"][2]["stop_name"] == "Davis Depot"
    assert tables["stops.txt"][3]["stop_name"] == "那須町役場前"
    assert results["autofix_stop_name_case"].count == 1


def test_trims_surrounding_whitespace_everywhere() -> None:
    tables = {"stops.txt": [{"stop_id": " 1 ", "stop_name": "Main St "}]}
    results = {r.code: r for r in apply_fixes(tables)}
    assert tables["stops.txt"][0]["stop_id"] == "1"
    assert tables["stops.txt"][0]["stop_name"] == "Main St"
    assert results["autofix_trim_whitespace"].count == 2


def test_recases_route_names_and_descriptions() -> None:
    tables = {
        "routes.txt": [
            {
                "route_id": "A",
                "route_long_name": "DOWNTOWN LOOP",
                "route_desc": "WEST SACRAMENTO SHUTTLE",
            }
        ]
    }
    results = {r.code: r for r in apply_fixes(tables)}
    assert tables["routes.txt"][0]["route_long_name"] == "Downtown Loop"
    assert tables["routes.txt"][0]["route_desc"] == "West Sacramento Shuttle"
    assert results["autofix_route_name_case"].count == 2


def test_clean_feed_yields_no_results() -> None:
    tables = {"stops.txt": [{"stop_id": "1", "stop_name": "Main St"}]}
    assert apply_fixes(tables) == []


def test_autofix_zip_patches_only_changed_files(make_gtfs_zip: Callable[..., Path]) -> None:
    src = make_gtfs_zip(
        {
            "agency.txt": "agency_id,agency_name\nx,X Transit\n",
            "stops.txt": "stop_id,stop_name\n1,MAIN STREET STATION\n2,Elm St\n",
            "calendar.txt": "service_id,monday\ns,1\n",
        }
    )
    out = src.parent / "fixed.zip"
    results = autofix_zip(str(src), str(out))
    assert any(r.code == "autofix_stop_name_case" for r in results)

    fixed = read_tables(str(out), ["stops.txt", "agency.txt"])
    assert fixed["stops.txt"][0]["stop_name"] == "Main Street Station"
    # An untouched file is preserved.
    assert fixed["agency.txt"][0]["agency_name"] == "X Transit"
    # Every original member survives.
    with zipfile.ZipFile(out) as zf:
        assert set(zf.namelist()) == {"agency.txt", "stops.txt", "calendar.txt"}


def test_autofix_zip_on_clean_feed_keeps_all_members(make_gtfs_zip: Callable[..., Path]) -> None:
    src = make_gtfs_zip(
        {
            "agency.txt": "agency_id,agency_name\nx,X Transit\n",
            "stops.txt": "stop_id,stop_name\n1,Main St\n",
        }
    )
    out = src.parent / "fixed.zip"
    results = autofix_zip(str(src), str(out))
    assert results == []
    with zipfile.ZipFile(out) as zf:
        assert set(zf.namelist()) == {"agency.txt", "stops.txt"}


def test_render_report_lists_changes_and_clean_case() -> None:
    tables = {"stops.txt": [{"stop_id": "1", "stop_name": "MAIN STREET"}]}
    report = render_report(apply_fixes(tables), feed_label="demo.zip")
    assert "Auto-fix applied to demo.zip" in report
    assert "Main Street" in report
    assert "nothing to change" in render_report([], feed_label="demo.zip")


def test_daily_scoring_does_not_generate_or_advertise_a_corrected_feed() -> None:
    source = inspect.getsource(run_agency)

    assert "autofix_zip" not in source
    assert "corrected.zip" not in source
    assert 'artifact["autofix"]' not in source


def test_autofix_remains_an_explicit_local_cli_command() -> None:
    """Auto-fix must stay something a person opts into by name, never something the
    daily pipeline reaches on its own. The subcommand table moved from `main` into
    `_dispatch` when `main` grew its contributor-facing error handling (#188); the
    guarantee is about the table, not about which function holds it."""
    assert '"autofix": _cmd_autofix' in inspect.getsource(_dispatch)
