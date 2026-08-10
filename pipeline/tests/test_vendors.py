"""Tests for the operator vendor view: freshness aggregated by feed host."""

from __future__ import annotations

import json

from scorecard_pipeline.cli import main
from scorecard_pipeline.config import Agency, artifacts_dir, register
from scorecard_pipeline.vendors import (
    MIN_AGENCIES_FOR_BENCHMARK,
    _feed_host,
    render_vendor_report,
    render_vendor_report_csv,
    render_vendor_report_markdown,
    vendor_breakdown,
)


def write_latest(agency_id: str, name: str, url: str, days: int | None) -> None:
    path = artifacts_dir() / agency_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "latest.json").write_text(
        json.dumps(
            {
                "agency": {"id": agency_id, "name": name},
                "overall": {"score": 50.0, "grade": "F"},
                "snapshot_date": "2026-06-16",
                "feed": {"static_url": url},
                "categories": {"freshness": {"details": {"days_until_expiry": days}}},
            }
        )
    )


def test_feed_host_normalizes() -> None:
    assert _feed_host("http://data.trilliumtransit.com/gtfs/x/x.zip") == "data.trilliumtransit.com"
    assert _feed_host("https://www.example.org:8080/a.zip") == "example.org"
    assert _feed_host("") == "unknown"


def test_breakdown_groups_and_counts_by_host() -> None:
    write_latest("a", "A", "http://data.trilliumtransit.com/gtfs/a/a.zip", -1000)  # stale
    write_latest("b", "B", "http://data.trilliumtransit.com/gtfs/b/b.zip", -1200)  # stale
    write_latest("c", "C", "http://data.trilliumtransit.com/gtfs/c/c.zip", 120)  # current
    write_latest("d", "D", "https://avl.example.org/g.zip", -10)  # lapsed, other host

    stats = vendor_breakdown()
    # Trillium sorts first: it carries the most long-stale feeds.
    assert stats[0].host == "data.trilliumtransit.com"
    assert stats[0].counts["stale"] == 2
    assert stats[0].counts["current"] == 1
    assert stats[0].total == 3
    assert sorted(stats[0].stale_agencies) == ["A", "B"]

    other = next(s for s in stats if s.host == "avl.example.org")
    assert other.counts["lapsed"] == 1
    assert other.expired == 1


def test_report_headlines_the_dominant_host() -> None:
    write_latest("a", "A", "http://data.trilliumtransit.com/gtfs/a/a.zip", -1000)
    write_latest("b", "B", "http://data.trilliumtransit.com/gtfs/b/b.zip", -1200)
    write_latest("d", "D", "https://avl.example.org/g.zip", -10)
    report = render_vendor_report(vendor_breakdown())
    assert "data.trilliumtransit.com accounts for 2 of 2" in report
    assert "data.trilliumtransit.com" in report
    # No ranking or scoring language in the operator report.
    assert "rank" not in report.lower()


def test_scoped_breakdown_respects_agency_ids() -> None:
    write_latest("a", "A", "http://data.trilliumtransit.com/gtfs/a/a.zip", -1000)
    write_latest("b", "B", "https://avl.example.org/g.zip", -10)
    stats = vendor_breakdown(["b"])
    assert [s.host for s in stats] == ["avl.example.org"]


def test_vendor_breakdown_excludes_retired_alias_by_default_and_scope() -> None:
    live = Agency("live", "Live Transit", "https://live.example.org/feed.zip")
    retired = Agency(
        "retired",
        "Retired Transit export",
        "https://retired.example.org/feed.zip",
        alias_of=live.id,
        feed_status="deprecated",
    )
    register(live)
    register(retired)
    write_latest(live.id, live.name, live.static_gtfs_url, 120)
    write_latest(retired.id, retired.name, retired.static_gtfs_url, -1_000)

    assert [stat.host for stat in vendor_breakdown()] == ["live.example.org"]
    assert [stat.host for stat in vendor_breakdown([retired.id, live.id])] == ["live.example.org"]
    assert (artifacts_dir() / retired.id / "latest.json").exists()


# --- vendor-report command and markdown/CSV render tests ---


def test_vendor_report_command_empty_artifacts_exits_zero(isolated_repo_root) -> None:  # type: ignore[no-untyped-def]
    """The vendor-report command returns 0 even when there are no artifacts."""
    from pathlib import Path

    root = Path(isolated_repo_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: test-agency\n"
        "    name: Test Agency\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )
    assert main(["vendor-report"]) == 0


def test_vendor_report_markdown_empty_has_footer() -> None:
    """An empty artifact dir produces no table rows but still shows the footer."""
    out = render_vendor_report_markdown([])
    assert "Internal support tool" in out
    assert "enough agencies" in out
    assert "|" not in out  # no table rows


def test_vendor_report_markdown_qualified_host_appears() -> None:
    """A host with >= MIN_AGENCIES_FOR_BENCHMARK agencies appears in the table."""
    write_latest("a", "Agency A", "http://data.trilliumtransit.com/gtfs/a/a.zip", -1000)
    write_latest("b", "Agency B", "http://data.trilliumtransit.com/gtfs/b/b.zip", -1200)
    stats = vendor_breakdown()
    out = render_vendor_report_markdown(stats)
    assert "data.trilliumtransit.com" in out
    assert "| Host |" in out
    assert "Internal support tool" in out


def test_vendor_report_markdown_single_agency_host_excluded() -> None:
    """A host with fewer than MIN_AGENCIES_FOR_BENCHMARK agencies is not shown."""
    assert MIN_AGENCIES_FOR_BENCHMARK == 2
    write_latest("a", "Agency A", "http://data.trilliumtransit.com/gtfs/a/a.zip", -1000)
    write_latest("b", "Agency B", "http://data.trilliumtransit.com/gtfs/b/b.zip", -1200)
    write_latest("solo", "Solo Agency", "https://solo.example.net/g.zip", -500)
    stats = vendor_breakdown()
    out = render_vendor_report_markdown(stats)
    assert "solo.example.net" not in out
    assert "data.trilliumtransit.com" in out


def test_vendor_report_csv_qualified_host_appears() -> None:
    """The CSV render includes a qualified host and a header row."""
    write_latest("a", "Agency A", "http://data.trilliumtransit.com/gtfs/a/a.zip", -1000)
    write_latest("b", "Agency B", "http://data.trilliumtransit.com/gtfs/b/b.zip", -1200)
    stats = vendor_breakdown()
    out = render_vendor_report_csv(stats)
    assert "host,agencies,expired,stale,example_agencies" in out
    assert "data.trilliumtransit.com" in out


def test_vendor_report_csv_single_agency_host_excluded() -> None:
    """A host below the threshold is absent from the CSV output."""
    write_latest("a", "Agency A", "http://data.trilliumtransit.com/gtfs/a/a.zip", -1000)
    write_latest("b", "Agency B", "http://data.trilliumtransit.com/gtfs/b/b.zip", -1200)
    write_latest("solo", "Solo Agency", "https://solo.example.net/g.zip", -500)
    stats = vendor_breakdown()
    out = render_vendor_report_csv(stats)
    assert "solo.example.net" not in out
