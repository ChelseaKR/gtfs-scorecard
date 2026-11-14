"""Every automated request names the scorecard; none presents as a browser
(ADR 0070, ADR 0075).

Three layers, each with a negative control:

- the shared constant and the checks in ``user_agent.py``;
- real requests to a local server from each HTTP client the pipeline uses,
  recording the User-Agent that arrived, plus ``net``'s refusal to send a
  browser-like one at all;
- a scan of every tracked source tree for a User-Agent literal that is not
  the identifying shape, or a browser product token anywhere.

``conftest.no_browser_user_agent_on_the_wire`` also fails any test, anywhere
in the suite, that writes a browser-like User-Agent to a socket.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import subprocess
import threading
import zipfile
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from scorecard_pipeline import net
from scorecard_pipeline import user_agent as ua
from scorecard_pipeline.config import Agency

REPO = Path(__file__).resolve().parents[2]
CHROME = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("agency.txt", "agency_name\nX")
    return buf.getvalue()


# ----------------------------------------------------------- the constant


def test_the_user_agent_names_the_scorecard_and_links_to_the_fetcher_page() -> None:
    assert re.fullmatch(
        r"gtfs-scorecard/\S+ \(\+https://gtfsscorecard\.org/fetcher/\)", ua.USER_AGENT
    )
    assert ua.is_identifying(ua.USER_AGENT)
    assert not ua.is_browser_like(ua.USER_AGENT)


def test_every_module_shares_the_one_user_agent() -> None:
    from scorecard_pipeline import catalog_api, fetch, liveness, robots_policy, rt

    for module in (robots_policy, fetch, liveness, rt, catalog_api):
        assert module.USER_AGENT == ua.USER_AGENT, module.__name__


@pytest.mark.parametrize(
    "value",
    [
        CHROME,
        "Mozilla/5.0 (compatible; gtfs-scorecard)",
        "gtfs-scorecard (+https://x.example) AppleWebKit/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17 Safari/605",
    ],
)
def test_browser_strings_are_recognized(value: str) -> None:
    assert ua.is_browser_like(value)
    with pytest.raises(ua.BrowserUserAgentError):
        ua.require_identifying(value)


@pytest.mark.parametrize(
    "value",
    ["python-requests/2.32", "gtfs-scorecard-mcp", "gtfs-scorecard/1.0 (equity)", ""],
)
def test_an_honest_string_that_does_not_name_us_with_a_link_is_refused(value: str) -> None:
    """Negative control: honest but anonymous is not enough."""
    assert not ua.is_browser_like(value)
    with pytest.raises(ua.BrowserUserAgentError):
        ua.require_identifying(value)


def test_with_identifying_user_agent_fills_in_and_checks() -> None:
    assert ua.with_identifying_user_agent(None) == {"User-Agent": ua.USER_AGENT}
    kept = ua.with_identifying_user_agent({"Accept": "x", "user-agent": ua.USER_AGENT})
    assert kept == {"Accept": "x", "user-agent": ua.USER_AGENT}
    with pytest.raises(ua.BrowserUserAgentError):
        ua.with_identifying_user_agent({"USER-AGENT": CHROME})


# ----------------------------------------------------------- on the wire


class _Server(ThreadingHTTPServer):
    seen: list[tuple[str, str, str]]  # (method, path, user agent)


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _record(self) -> None:
        self.server.seen.append((self.command, self.path, self.headers.get("User-Agent", "")))

    def do_GET(self) -> None:
        self._record()
        path = urlsplit(self.path).path
        if path == "/robots.txt":
            body, ctype = b"User-agent: *\nAllow: /\n", "text/plain"
        elif path.endswith(".zip"):
            body, ctype = _zip_bytes(), "application/zip"
        elif path.endswith(".csv"):
            body, ctype = b"mdb_source_id,data_type,provider\n1,gtfs,X\n", "text/csv"
        elif path.endswith(".json"):
            body, ctype = b"{}", "application/json"
        else:
            body, ctype = b"\x00", "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        self._record()
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.send_response(204)
        self.end_headers()


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Server]:
    """A local origin that every guarded client is allowed to reach."""
    srv = _Server(("127.0.0.1", 0), _Handler)
    srv.seen = []
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    def only_this_server(url: str) -> None:
        parts = urlsplit(url)
        if f"{parts.scheme}://{parts.netloc}" != base:
            raise net.UnsafeURLError(f"not the fixture origin: {url!r}")

    monkeypatch.setattr(net, "validate_public_url", only_this_server)
    srv.base = base  # type: ignore[attr-defined]
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _assert_all_identifying(seen: list[tuple[str, str, str]], *, at_least: int) -> None:
    assert len(seen) >= at_least, seen
    for method, path, agent in seen:
        assert agent == ua.USER_AGENT, (method, path, agent)


def test_each_client_sends_the_identifying_user_agent(
    server: _Server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scorecard_pipeline import fetch as fetchmod
    from scorecard_pipeline import liveness, mobilitydb, notify, rt
    from scorecard_pipeline.mcp_server import _http_fetch
    from scorecard_pipeline.robots_policy import RobotsChecker, _default_get, reset_shared_checker

    base: str = server.base  # type: ignore[attr-defined]
    # The real robots.txt reader, through net, against the local server.
    reset_shared_checker(RobotsChecker(get=_default_get))
    monkeypatch.setattr(fetchmod, "FETCH_RETRIES", 0)

    # The daily schedule fetch (robots.txt read, then the feed).
    agency = Agency(id="x", name="X", static_gtfs_url=f"{base}/feed.zip")
    fetchmod.fetch_static(agency, dt.date(2026, 11, 5))
    # A realtime sample, the liveness check (urllib), a catalog read, net's
    # default, the MCP server's read of our own site, and a webhook POST.
    rt.fetch_sample("trip_updates", f"{base}/tu.pb")
    liveness.check_feed(f"{base}/feed.zip", None)
    mobilitydb.fetch_catalog_bytes(f"{base}/catalog.csv")
    net.safe_get(f"{base}/plain.json", timeout=10)
    _http_fetch(f"{base}/api.json")
    notify.send_webhooks([notify.WebhookNotification(url=f"{base}/hook", payload={})])

    paths = [path for _method, path, _agent in server.seen]
    for expected in ("/robots.txt", "/feed.zip", "/tu.pb", "/catalog.csv", "/plain.json"):
        assert expected in paths, (expected, paths)
    assert ("POST", "/hook") in [(m, p) for m, p, _a in server.seen]
    _assert_all_identifying(server.seen, at_least=8)


def test_net_refuses_a_browser_user_agent_before_any_request(server: _Server) -> None:
    base: str = server.base  # type: ignore[attr-defined]
    with pytest.raises(ua.BrowserUserAgentError):
        net.safe_get(f"{base}/feed.zip", headers={"User-Agent": CHROME}, timeout=10)
    with pytest.raises(ua.BrowserUserAgentError):
        net.safe_download(
            f"{base}/feed.zip", Path("unused.zip"), headers={"user-agent": CHROME}, timeout=10
        )
    assert server.seen == []

    # Negative control: the same request with no User-Agent reaches the server
    # and carries ours.
    net.safe_get(f"{base}/feed.zip", timeout=10)
    _assert_all_identifying(server.seen, at_least=1)


def test_the_wire_guard_catches_a_client_that_bypasses_net(server: _Server) -> None:
    """The conftest guard sits under every client, including a raw one."""
    import urllib.request

    base: str = server.base  # type: ignore[attr-defined]
    raw = urllib.request.Request(f"{base}/x.json", headers={"User-Agent": CHROME})  # noqa: S310
    with pytest.raises(AssertionError, match="browser-like User-Agent"):
        urllib.request.urlopen(raw, timeout=10)  # noqa: S310 - local fixture server
    assert server.seen == []

    # Negative control: the guard lets an identifying request through.
    ok = urllib.request.Request(  # noqa: S310 - local fixture server
        f"{base}/x.json", headers={"User-Agent": ua.USER_AGENT}
    )
    with urllib.request.urlopen(ok, timeout=10) as resp:  # noqa: S310 - local fixture server
        assert resp.status == 200
    _assert_all_identifying(server.seen, at_least=1)


# ----------------------------------------------------------- the source tree

#: Trees that hold code which makes requests. Docs, fixtures, and recorded
#: artifacts quote historical values and are not scanned.
SCANNED = ("pipeline/src", "pipeline/scripts", "infra", "scripts", ".github", "action")
_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".js", ".mjs", ".ts"}
_LITERAL = re.compile(
    r"""(?x)
    (?:(?i:["']user-agent["']\s*:\s*)|            # {"User-Agent": "..."}
       (?i:add_header\(\s*["']user-agent["']\s*,\s*)|
       \b[A-Z_]*USER_AGENT\s*=\s*\(?\s*|         # USER_AGENT = "..."
       \b(?:curl|wget)\b[^\n]*?\s-A\s+|
       (?i:--user-agent[\s=]+))
    (?P<q>["'])(?P<value>[^"']*)(?P=q)
    """
)


def _tracked_sources() -> list[Path]:
    out = subprocess.run(  # noqa: S603 - fixed argv, no user input
        ["git", "ls-files", "--", *SCANNED],  # noqa: S607 - git from PATH, as CI runs it
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return [REPO / p for p in out if Path(p).suffix in _SUFFIXES]


def _violations(text: str) -> list[str]:
    bad = [m.group(0) for m in re.finditer(r"Mozilla/\d|AppleWebKit/|Chrome/\d", text)]
    for match in _LITERAL.finditer(text):
        value = match.group("value")
        if value and not ua.is_identifying(value):
            bad.append(value)
    return bad


def test_no_source_file_sets_a_browser_or_anonymous_user_agent() -> None:
    files = _tracked_sources()
    assert len(files) > 100  # the scan really ran over the tree
    found = {
        str(path.relative_to(REPO)): hits
        for path in files
        if (hits := _violations(path.read_text(errors="replace")))
    }
    assert found == {}


def test_the_scan_catches_what_it_is_for() -> None:
    """Negative control for the scan: each old value is flagged."""
    assert _violations(f'USER_AGENT = (\n    "{CHROME}"\n)')
    assert _violations('headers={"User-Agent": "gtfs-scorecard/1.0 (equity)"}')
    assert _violations('req.add_header("User-Agent", "gtfs-scorecard-submit")')
    assert _violations("curl -A 'Mozilla/5.0' https://x")
    assert not _violations(f'headers={{"User-Agent": "{ua.USER_AGENT}"}}')
    assert not _violations('headers={"User-Agent": USER_AGENT}')
