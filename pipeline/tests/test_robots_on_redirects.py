"""robots.txt is read before every redirect hop of a feed request (ADR 0077).

These run against real local HTTP servers, so "stops before the second request"
is what the server saw, not what a mock was told. Each server is one host as far
as robots.txt goes, because robots.txt is scoped to host and port.
"""

from __future__ import annotations

import datetime as dt
import io
import threading
import zipfile
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import net
from scorecard_pipeline.cli import _unreachable_reason
from scorecard_pipeline.config import Agency
from scorecard_pipeline.fetch import fetch_static
from scorecard_pipeline.liveness import (
    CHANGED,
    NOT_FETCHED,
    LivenessRecord,
    check_feed,
    recovered,
)
from scorecard_pipeline.mobilitydb import fetch_catalog_bytes
from scorecard_pipeline.net import safe_download, safe_get
from scorecard_pipeline.robots_policy import (
    NOT_FETCHED_DISALLOWED,
    NOT_FETCHED_OFF_LIMITS,
    RobotsChecker,
    RobotsRefusedError,
    require_robots,
    reset_shared_checker,
)
from scorecard_pipeline.rt import fetch_sample

REPO_ROOT = Path(__file__).resolve().parents[2]
DISALLOW_PRIVATE = "User-agent: *\nDisallow: /private\n"


def _gtfs_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("agency.txt", "agency_name,agency_url,agency_timezone\nA,http://a,UTC\n")
        archive.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\n1,S,1.0,1.0\n")
        archive.writestr("routes.txt", "route_id,route_type\n1,3\n")
        archive.writestr("trips.txt", "route_id,service_id,trip_id\n1,1,1\n")
        archive.writestr(
            "stop_times.txt", "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        )
    return buffer.getvalue()


class Host:
    """One local server: a log of every path asked for, and what to answer."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.robots: tuple[int, str] | None = None
        self.redirects: dict[str, str] = {}
        self.body = _gtfs_zip()
        host = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                host.requests.append(self.path)
                if self.path == "/robots.txt":
                    status, text = host.robots or (404, "")
                    self._answer(status, text.encode(), "text/plain")
                elif self.path in host.redirects:
                    self.send_response(302)
                    self.send_header("Location", host.redirects[self.path])
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    self._answer(200, host.body, "application/zip")

            def _answer(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def feed_requests(self) -> list[str]:
        return [path for path in self.requests if path != "/robots.txt"]


@pytest.fixture()
def hosts(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Host, Host]]:
    """Two hosts, the real robots client, and the loopback guard lifted for them."""
    monkeypatch.setattr(net, "validate_public_url", lambda _url: None)
    reset_shared_checker(RobotsChecker())
    first, second = Host(), Host()
    first.redirects["/feed.zip"] = f"{second.url}/private/feed.zip"
    yield first, second
    first.server.shutdown()
    second.server.shutdown()


def test_an_allowed_host_redirecting_to_a_disallowed_path_stops_before_that_request(
    hosts: tuple[Host, Host],
) -> None:
    first, second = hosts
    second.robots = (200, DISALLOW_PRIVATE)
    with pytest.raises(RobotsRefusedError) as refused:
        safe_get(f"{first.url}/feed.zip", timeout=5, hop_guard=require_robots)
    assert refused.value.reason == NOT_FETCHED_DISALLOWED
    assert first.feed_requests() == ["/feed.zip"]
    assert second.requests == ["/robots.txt"]


def test_an_all_allowed_redirect_still_downloads(hosts: tuple[Host, Host], tmp_path: Path) -> None:
    first, second = hosts
    second.robots = (200, "User-agent: *\nDisallow: /elsewhere\n")
    dest = tmp_path / "feed.zip"
    size = safe_download(f"{first.url}/feed.zip", dest, timeout=5, hop_guard=require_robots)
    assert size == len(second.body)
    assert dest.read_bytes() == second.body
    assert second.feed_requests() == ["/private/feed.zip"]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_an_unreadable_robots_on_a_redirect_target_is_a_refusal(
    hosts: tuple[Host, Host], status: int
) -> None:
    first, second = hosts
    second.robots = (status, "")
    with pytest.raises(RobotsRefusedError) as refused:
        safe_get(f"{first.url}/feed.zip", timeout=5, hop_guard=require_robots)
    assert refused.value.reason == NOT_FETCHED_OFF_LIMITS
    assert second.feed_requests() == []


def test_a_refusal_is_not_retried_and_leaves_no_partial_file(
    hosts: tuple[Host, Host], tmp_path: Path
) -> None:
    first, second = hosts
    second.robots = (200, DISALLOW_PRIVATE)
    dest = tmp_path / "feed.zip"
    with pytest.raises(RobotsRefusedError):
        safe_download(
            f"{first.url}/feed.zip", dest, timeout=5, retries=3, backoff=0, hop_guard=require_robots
        )
    assert first.feed_requests() == ["/feed.zip"]
    assert list(tmp_path.iterdir()) == []


def test_each_host_robots_is_read_once_across_feeds(hosts: tuple[Host, Host]) -> None:
    first, second = hosts
    second.robots = (200, "User-agent: *\nDisallow: /elsewhere\n")
    first.redirects["/other.zip"] = f"{second.url}/private/other.zip"
    safe_get(f"{first.url}/feed.zip", timeout=5, hop_guard=require_robots)
    safe_get(f"{first.url}/other.zip", timeout=5, hop_guard=require_robots)
    assert first.requests.count("/robots.txt") == 1
    assert second.requests.count("/robots.txt") == 1


def test_the_schedule_fetch_records_a_redirect_refusal_as_not_fetched(
    hosts: tuple[Host, Host], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = hosts
    second.robots = (200, DISALLOW_PRIVATE)
    monkeypatch.setenv("SCORECARD_ROOT", str(tmp_path))
    agency = Agency(id="a", name="A", static_gtfs_url=f"{first.url}/feed.zip")
    with pytest.raises(RobotsRefusedError) as refused:
        fetch_static(agency, dt.date(2026, 11, 8))

    # The run's reason is the existing not-fetched phrase, which the page prints
    # beside the last measured grade; nothing was written over that grade.
    assert _unreachable_reason(refused.value) == NOT_FETCHED_DISALLOWED
    assert second.feed_requests() == []
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []


def test_the_schedule_fetch_follows_an_allowed_redirect(
    hosts: tuple[Host, Host], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = hosts
    monkeypatch.setenv("SCORECARD_ROOT", str(tmp_path))
    agency = Agency(id="a", name="A", static_gtfs_url=f"{first.url}/feed.zip")
    result = fetch_static(agency, dt.date(2026, 11, 8))
    assert result.source == "origin"
    assert result.final_url == f"{second.url}/private/feed.zip"


def test_the_liveness_check_stops_at_a_disallowed_redirect_and_keeps_the_record(
    hosts: tuple[Host, Host],
) -> None:
    first, second = hosts
    second.robots = (200, DISALLOW_PRIVATE)
    prev = LivenessRecord(url="x", etag="e", consecutive_failures=2, checked_at="2026-11-01")
    record, classification = check_feed(f"{first.url}/feed.zip", prev)
    assert classification == NOT_FETCHED
    assert record == prev
    assert second.feed_requests() == []
    assert not recovered(prev, classification)


def test_the_liveness_check_does_not_request_a_disallowed_first_url(
    hosts: tuple[Host, Host],
) -> None:
    first, _second = hosts
    first.robots = (200, DISALLOW_PRIVATE)
    record, classification = check_feed(f"{first.url}/private/feed.zip", None)
    assert classification == NOT_FETCHED
    assert record.checked_at is None
    assert first.feed_requests() == []


def test_the_liveness_check_follows_an_allowed_redirect(hosts: tuple[Host, Host]) -> None:
    first, second = hosts
    _record, classification = check_feed(f"{first.url}/feed.zip", None)
    assert classification == CHANGED
    assert second.feed_requests() == ["/private/feed.zip"]


def test_a_realtime_sample_stops_at_a_disallowed_redirect_as_not_measured(
    hosts: tuple[Host, Host],
) -> None:
    first, second = hosts
    second.robots = (200, DISALLOW_PRIVATE)
    sample = fetch_sample("trip_updates", f"{first.url}/feed.zip")
    assert second.feed_requests() == []
    assert sample.ok is False
    assert sample.measured is False


def test_the_catalog_read_stops_at_a_disallowed_redirect(hosts: tuple[Host, Host]) -> None:
    first, second = hosts
    second.robots = (200, DISALLOW_PRIVATE)
    with pytest.raises(RobotsRefusedError):
        fetch_catalog_bytes(f"{first.url}/feed.zip")
    assert second.feed_requests() == []


def test_no_feed_download_path_keeps_a_redirect_following_client() -> None:
    publishers = (REPO_ROOT / "pipeline/scripts/fetch_feed_publishers.py").read_text()
    assert "urllib.request.urlopen" not in publishers
    assert publishers.count("guarded_urlopen(req") == 3
    liveness = (REPO_ROOT / "pipeline/src/scorecard_pipeline/liveness.py").read_text()
    assert "urlopen(req, timeout=timeout)" not in liveness
    workflow = (REPO_ROOT / ".github/workflows/otp-qa.yml").read_text()
    assert 'curl -fsSL --retry 3 --retry-all-errors "$FEED_URL"' not in workflow
    assert "hop_guard=require_robots" in workflow


def test_the_fetcher_page_states_the_redirect_rule() -> None:
    page = " ".join((REPO_ROOT / "web/fetcher/index.html").read_text().split())
    assert "every host a redirect leads to, before requesting anything from it" in page
