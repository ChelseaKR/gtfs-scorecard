"""Tests for the SSRF/size guards in net.safe_get."""

from __future__ import annotations

import pytest

from scorecard_pipeline.net import UnsafeURLError, validate_public_url

# IP-literal URLs so the checks run without any DNS lookup.
BLOCKED = [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "http://127.0.0.1/",
    "http://10.0.0.5/feed.zip",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://[::1]/",
    "http://0.0.0.0/",
]


@pytest.mark.parametrize("url", BLOCKED)
def test_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_public_url(url)


def test_allows_public_ip_literal() -> None:
    # 93.184.216.34 (example.com) is publicly routable; no DNS needed.
    validate_public_url("https://93.184.216.34/feed.zip")


def test_rejects_missing_host() -> None:
    with pytest.raises(UnsafeURLError):
        validate_public_url("http:///nohost")


@pytest.mark.parametrize("url", ["https://example.org:abc/feed.zip", "https://example.org:99999/"])
def test_rejects_invalid_ports_as_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeURLError, match="invalid port"):
        validate_public_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://[::1/feed.zip",
        "https://example.org\uff0f@evil.example/feed.zip",
    ],
)
def test_rejects_malformed_netlocs_as_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeURLError, match="malformed"):
        validate_public_url(url)


import socket  # noqa: E402
import time  # noqa: E402

import requests  # noqa: E402

from scorecard_pipeline import net  # noqa: E402
from scorecard_pipeline.fetch import FEED_HEADERS  # noqa: E402


def _http_error(status: int) -> requests.exceptions.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    return requests.exceptions.HTTPError(response=resp)


def test_is_retriable_only_for_http_statuses_not_timeouts() -> None:
    assert net._is_retriable(_http_error(403))
    assert net._is_retriable(_http_error(503))
    assert not net._is_retriable(_http_error(404))
    # Connection timeouts are persistent and slow; retrying them wastes minutes.
    assert not net._is_retriable(requests.exceptions.ConnectTimeout())
    assert not net._is_retriable(requests.exceptions.ReadTimeout())
    assert not net._is_retriable(requests.exceptions.ConnectionError())
    assert not net._is_retriable(net.UnsafeURLError("private host"))


def test_safe_get_does_not_retry_a_connect_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_once(url: str, **_: object) -> bytes:
        calls["n"] += 1
        raise requests.exceptions.ConnectTimeout("connect timed out")

    monkeypatch.setattr(net, "_fetch_once", fake_once)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    with pytest.raises(requests.exceptions.ConnectTimeout):
        net.safe_get("https://blocked.example.org/g.zip", timeout=(12, 120), retries=3)
    assert calls["n"] == 1  # failed fast, no expensive retries


def test_safe_get_retries_a_403_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_once(url: str, **_: object) -> bytes:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(403)  # WAF block that clears on retry
        return b"ZIPDATA"

    monkeypatch.setattr(net, "_fetch_once", fake_once)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    assert net.safe_get("https://feeds.example.org/g.zip", timeout=1, retries=3) == b"ZIPDATA"
    assert calls["n"] == 3


def test_safe_get_does_not_retry_a_404(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_once(url: str, **_: object) -> bytes:
        calls["n"] += 1
        raise _http_error(404)

    monkeypatch.setattr(net, "_fetch_once", fake_once)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    with pytest.raises(requests.exceptions.HTTPError):
        net.safe_get("https://feeds.example.org/g.zip", timeout=1, retries=3)
    assert calls["n"] == 1


def test_safe_get_never_retries_ssrf_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_once(url: str, **_: object) -> bytes:
        calls["n"] += 1
        raise net.UnsafeURLError("resolves to private address")

    monkeypatch.setattr(net, "_fetch_once", fake_once)
    with pytest.raises(net.UnsafeURLError):
        net.safe_get("https://feeds.example.org/g.zip", timeout=1, retries=3)
    assert calls["n"] == 1


def test_safe_get_exhausts_retries_and_raises_last(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_once(url: str, **_: object) -> bytes:
        calls["n"] += 1
        raise _http_error(429)

    monkeypatch.setattr(net, "_fetch_once", fake_once)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    with pytest.raises(requests.exceptions.HTTPError):
        net.safe_get("https://feeds.example.org/g.zip", timeout=1, retries=2)
    assert calls["n"] == 3  # initial try + 2 retries


def test_feed_headers_present_as_a_browser() -> None:
    assert FEED_HEADERS["User-Agent"].startswith("Mozilla/5.0")
    assert "gtfs-scorecard" not in FEED_HEADERS["User-Agent"]  # WAFs block our old token
    assert "Accept" in FEED_HEADERS


def test_validate_public_url_rejects_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> object:
        raise socket.gaierror("name does not resolve")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(net.UnsafeURLError):
        net.validate_public_url("https://does-not-resolve.invalid/feed.zip")


# --- _fetch_once: the redirect-revalidation and size-cap core (SSRF guard) ---
#
# Public IP literals so validate_public_url runs without real DNS, and a fake
# requests.Session so no network is touched.

# example.com, publicly routable; no DNS lookup needed.
PUBLIC = "https://93.184.216.34/feed.zip"


class _FakeResp:
    def __init__(
        self,
        *,
        redirect: bool = False,
        location: str | None = None,
        status: int = 200,
        headers: dict[str, str] | None = None,
        chunks: tuple[bytes, ...] = (),
    ) -> None:
        self.is_redirect = redirect
        self.is_permanent_redirect = False
        self.status_code = status
        self.headers = dict(headers or {})
        if location is not None:
            self.headers["location"] = location
        self._chunks = chunks

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return list(self._chunks)

    def close(self) -> None:
        pass


class _FakeSession:
    def __init__(self, responses: list[_FakeResp]) -> None:
        self._responses = responses
        self.urls: list[str] = []

    def get(self, url: str, **_kw: object) -> _FakeResp:
        self.urls.append(url)
        return self._responses.pop(0)


def _use_session(monkeypatch: pytest.MonkeyPatch, responses: list[_FakeResp]) -> _FakeSession:
    session = _FakeSession(responses)
    monkeypatch.setattr(requests, "Session", lambda: session)
    return session


def test_fetch_once_returns_body_under_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_session(monkeypatch, [_FakeResp(headers={"content-length": "6"}, chunks=(b"ZIPDAT",))])
    body = net._fetch_once(PUBLIC, headers=None, timeout=1, max_bytes=1000, max_redirects=5)
    assert body == b"ZIPDAT"


def test_fetch_once_records_the_actual_final_url(monkeypatch: pytest.MonkeyPatch) -> None:
    final = "https://93.184.216.34/releases/current.zip"
    _use_session(
        monkeypatch,
        [
            _FakeResp(redirect=True, location="/releases/current.zip"),
            _FakeResp(chunks=(b"ZIPDATA",)),
        ],
    )
    trace = net.FetchTrace()

    body = net._fetch_once(
        PUBLIC,
        headers=None,
        timeout=1,
        max_bytes=1000,
        max_redirects=5,
        trace=trace,
    )

    assert body == b"ZIPDATA"
    assert trace.final_url == final
    assert trace.redirect_chain == (PUBLIC, final)


def test_fetch_once_revalidates_a_redirect_to_an_internal_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A public URL that 302s to cloud metadata must be rejected on the next hop,
    # not blindly followed. This is the redirect-SSRF guard.
    session = _use_session(
        monkeypatch, [_FakeResp(redirect=True, location="http://169.254.169.254/latest/")]
    )
    with pytest.raises(net.UnsafeURLError):
        net._fetch_once(PUBLIC, headers=None, timeout=1, max_bytes=1000, max_redirects=5)
    assert session.urls == [PUBLIC]  # stopped before fetching the internal target


def test_fetch_once_redirect_without_location_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_session(monkeypatch, [_FakeResp(redirect=True, location=None)])
    with pytest.raises(net.UnsafeURLError):
        net._fetch_once(PUBLIC, headers=None, timeout=1, max_bytes=1000, max_redirects=5)


def test_fetch_once_rejects_oversized_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_session(monkeypatch, [_FakeResp(headers={"content-length": "2000"})])
    with pytest.raises(net.UnsafeURLError):
        net._fetch_once(PUBLIC, headers=None, timeout=1, max_bytes=1000, max_redirects=5)


def test_fetch_once_rejects_a_stream_that_exceeds_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No content-length header, so the cap is enforced while streaming chunks.
    _use_session(monkeypatch, [_FakeResp(chunks=(b"x" * 600, b"y" * 600))])
    with pytest.raises(net.UnsafeURLError):
        net._fetch_once(PUBLIC, headers=None, timeout=1, max_bytes=1000, max_redirects=5)


def test_fetch_once_caps_redirect_chain_length(monkeypatch: pytest.MonkeyPatch) -> None:
    forever = [_FakeResp(redirect=True, location=PUBLIC) for _ in range(8)]
    _use_session(monkeypatch, forever)
    with pytest.raises(net.UnsafeURLError):
        net._fetch_once(PUBLIC, headers=None, timeout=1, max_bytes=1000, max_redirects=3)
