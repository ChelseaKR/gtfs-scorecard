"""Honest User-Agent, robots.txt on every feed request, and no reads of the
disallowed Mobility Database file host (ADR 0070)."""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
import requests

from scorecard_pipeline import fetch as fetchmod
from scorecard_pipeline import robots_policy as rp
from scorecard_pipeline.config import Agency
from scorecard_pipeline.robots_policy import RobotsChecker, RobotsRefusedError, RobotsResponse
from scorecard_pipeline.run_summary import (
    AgencyOutcome,
    build_shard_summary,
    merge_run_summaries,
)

ORIGIN = "https://origin.example.org/g.zip"
AGENCY = Agency(id="x", name="X Transit", static_gtfs_url=ORIGIN)
DISALLOW_ALL = RobotsResponse(
    200, "https://origin.example.org/robots.txt", "", "User-agent: *\nDisallow: /\n"
)


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("agency.txt", "agency_name\nX")
    return buf.getvalue()


def _robots(response_by_host: dict[str, RobotsResponse]) -> None:
    def get(url: str) -> RobotsResponse:
        for host, response in response_by_host.items():
            if host in url:
                return response
        return RobotsResponse(404, url, "", "")

    rp.reset_shared_checker(RobotsChecker(get=get))


def test_feed_requests_send_the_identifying_user_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sent: list[dict[str, str]] = []

    def fake_safe_get(url: str, **kwargs: Any) -> bytes:
        sent.append(kwargs["headers"])
        return _zip_bytes()

    monkeypatch.setattr(fetchmod, "safe_get", fake_safe_get)
    fetchmod._download_with_mirror_fallback(AGENCY, tmp_path / "g.zip", None)
    assert sent[0]["User-Agent"] == rp.USER_AGENT
    assert "Mozilla" not in sent[0]["User-Agent"]
    assert fetchmod.USER_AGENT == rp.USER_AGENT


def test_a_disallowed_feed_is_not_requested_at_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requested: list[str] = []
    monkeypatch.setattr(
        fetchmod, "safe_get", lambda url, **_: requested.append(url) or _zip_bytes()
    )
    monkeypatch.setattr(
        "scorecard_pipeline.mobilitydb.hosted_mirror_url", lambda *a, **k: "https://m.example/x.zip"
    )
    _robots({"origin.example.org": DISALLOW_ALL})

    with pytest.raises(RobotsRefusedError) as raised:
        fetchmod._download_with_mirror_fallback(AGENCY, tmp_path / "g.zip", None)

    assert raised.value.reason == "not fetched: robots disallows"
    assert requested == []  # neither the feed nor a mirror

    # Negative control: the same fetch with no rules on the host downloads.
    _robots({})
    fetchmod._download_with_mirror_fallback(AGENCY, tmp_path / "g.zip", None)
    assert requested == [ORIGIN]


def test_the_mobility_database_file_host_is_never_used_as_a_mirror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requested: list[str] = []

    def fake_safe_get(url: str, **_: Any) -> bytes:
        requested.append(url)
        raise requests.exceptions.ConnectTimeout("origin firewalls our IP")

    robots_reads: list[str] = []

    def get(url: str) -> RobotsResponse:
        robots_reads.append(url)
        return RobotsResponse(404, url, "", "")

    rp.reset_shared_checker(RobotsChecker(get=get))
    monkeypatch.setattr(fetchmod, "safe_get", fake_safe_get)
    mirror = "https://files.mobilitydatabase.org/mdb-1/latest.zip"
    monkeypatch.setattr("scorecard_pipeline.mobilitydb.hosted_mirror_url", lambda *a, **k: mirror)

    with pytest.raises(requests.exceptions.ConnectTimeout):
        fetchmod._download_with_mirror_fallback(AGENCY, tmp_path / "g.zip", None)

    assert mirror not in requested
    assert not any("mobilitydatabase" in url for url in requested + robots_reads)


def test_a_mirror_whose_robots_refuses_us_is_not_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requested: list[str] = []

    def fake_safe_get(url: str, **_: Any) -> bytes:
        requested.append(url)
        if url == ORIGIN:
            raise requests.exceptions.ConnectTimeout("down")
        return _zip_bytes()

    monkeypatch.setattr(fetchmod, "safe_get", fake_safe_get)
    mirror = "https://mirror.example.net/x.zip"
    monkeypatch.setattr("scorecard_pipeline.mobilitydb.hosted_mirror_url", lambda *a, **k: mirror)
    _robots(
        {"mirror.example.net": RobotsResponse(503, "https://mirror.example.net/robots.txt", "", "")}
    )

    with pytest.raises(requests.exceptions.ConnectTimeout):
        fetchmod._download_with_mirror_fallback(AGENCY, tmp_path / "g.zip", None)
    assert requested == [ORIGIN]

    # Negative control: the same mirror with no rules file serves the bytes.
    _robots({})
    prov = fetchmod._download_with_mirror_fallback(AGENCY, tmp_path / "g.zip", None)
    assert prov.source == "mirror"


def test_a_refused_realtime_feed_is_not_measured_not_an_outage() -> None:
    from scorecard_pipeline.rt import fetch_sample, measures_the_endpoint

    _robots(
        {
            "rt.example.org": RobotsResponse(
                200, "https://rt.example.org/robots.txt", "", "User-agent: *\nDisallow: /\n"
            )
        }
    )
    sample = fetch_sample("trip_updates", "https://rt.example.org/tu.pb")
    assert sample.ok is False
    assert sample.measured is False
    assert measures_the_endpoint(RobotsRefusedError(rp.RobotsVerdict(False, "x"), "h")) is False


def test_run_outcome_names_the_robots_reason() -> None:
    from scorecard_pipeline.cli import _unreachable_reason

    refused = RobotsRefusedError(rp.RobotsVerdict(False, rp.DISALLOWED_BY_ROBOTS), "h")
    assert _unreachable_reason(refused) == "not fetched: robots disallows"
    assert _unreachable_reason(RuntimeError("publisher down")) is None


def _shard(outcomes: list[AgencyOutcome]) -> dict[str, Any]:
    now = dt.datetime(2026, 10, 13, tzinfo=dt.UTC)
    return build_shard_summary("0", outcomes, now, now)


def test_not_fetched_records_are_counted_apart_from_outages() -> None:
    outcomes = [AgencyOutcome(f"s{i}", "scored") for i in range(80)] + [
        AgencyOutcome(f"r{i}", "unreachable", reason="not fetched: robots disallows")
        for i in range(20)
    ]
    merged = merge_run_summaries([_shard(outcomes)], dt.datetime(2026, 10, 13, tzinfo=dt.UTC))
    assert merged["unreachable"] == 20
    assert merged["not_fetched"] == 20
    # 20 percent of the run was our choice, not an outage: no warning.
    assert merged["degraded"] is False

    # Negative control: the same 20 as plain outages trip the warning.
    outages = outcomes[:80] + [AgencyOutcome(f"r{i}", "unreachable") for i in range(20)]
    merged = merge_run_summaries([_shard(outages)], dt.datetime(2026, 10, 13, tzinfo=dt.UTC))
    assert merged["not_fetched"] == 0
    assert merged["degraded"] is True


def test_status_and_agency_pages_say_why_a_feed_was_not_fetched() -> None:
    from scorecard_pipeline.render_site import _not_fetched_note, _status_evidence_section

    note = _not_fetched_note("not fetched: robots disallows", {"snapshot_date": "2026-10-01"})
    assert "robots.txt asks automated tools not to request it" in note
    assert "2026-10-01" in note
    assert _not_fetched_note(None, {}) == ""
    assert _not_fetched_note("publisher down", {}) == ""

    outcomes = [
        AgencyOutcome("kept", "scored"),
        AgencyOutcome("blocked", "unreachable", reason="not fetched: robots disallows"),
    ]
    summary = merge_run_summaries([_shard(outcomes)], dt.datetime(2026, 10, 13, tzinfo=dt.UTC))
    catalog = [{"id": "kept", "name": "Kept"}, {"id": "blocked", "name": "Blocked Transit"}]
    html = _status_evidence_section(summary, catalog, dt.datetime(2026, 10, 13, 12, tzinfo=dt.UTC))
    assert "Blocked Transit</a> (not fetched: robots disallows)" in html
    assert "not fetched because of robots.txt</dt><dd>1</dd>" in html
