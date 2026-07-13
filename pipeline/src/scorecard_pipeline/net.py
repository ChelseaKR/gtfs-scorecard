"""Guarded HTTP fetching for untrusted feed URLs.

Feed and realtime URLs come from agencies.yaml, which Phase 4 lets outside
parties propose through the self-serve form. Fetching them with a bare
``requests.get`` is an SSRF and resource-exhaustion sink: a URL can point at
cloud metadata (169.254.169.254), an internal host, or an endpoint that streams
gigabytes. ``safe_get`` is the single choke point that every feed download goes
through. It:

- allows only http/https,
- resolves each host and rejects private, loopback, link-local, reserved,
  multicast, and unspecified addresses,
- validates every redirect hop (so a public URL can't bounce to an internal
  one), and
- caps the downloaded size.

Residual risk: a DNS-rebinding race between the resolve check and the socket
connect. The registry is curated and submissions are human-reviewed, so this is
an accepted limitation rather than a reason to pin sockets to resolved IPs.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit

import requests

# Ceiling for any single feed or jar download. Real GTFS feeds are well under
# this; the cap exists to stop a hostile or misconfigured endpoint.
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024

# Statuses worth a retry: a momentary 429/5xx, or a WAF 403 that often lets a
# second request through. SSRF and oversize rejections are never retried.
RETRIABLE_STATUS = frozenset({403, 408, 425, 429, 500, 502, 503, 504})


class UnsafeURLError(ValueError):
    """A URL was rejected before or during fetching (bad scheme, private host,
    oversized response, or too many redirects)."""


def validate_public_url(url: str) -> None:
    """Raise UnsafeURLError unless the URL is http(s) and every resolved
    address for its host is publicly routable."""
    try:
        # Invalid IPv6 brackets and NFKC-sensitive netloc delimiters raise
        # during parsing, before ``hostname`` or ``port`` can be inspected.
        parts = urlsplit(url)
    except ValueError as exc:
        raise UnsafeURLError(f"URL is malformed: {url!r}") from exc
    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError(f"only http(s) URLs are allowed, got {parts.scheme or 'no'} scheme")
    host = parts.hostname
    if not host:
        raise UnsafeURLError(f"URL has no host: {url!r}")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeURLError(f"URL has an invalid port: {url!r}") from exc
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"cannot resolve host {host!r}: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURLError(f"host {host!r} resolves to non-public address {ip}")


def _is_retriable(exc: Exception) -> bool:
    """Whether a failed attempt is worth retrying.

    Only a retriable HTTP status (a transient 5xx/429 or a flaky WAF 403). A
    connection timeout is deliberately NOT retried: a host that drops our packets
    (usually an IP-range firewall on a datacenter address) just times out again,
    and each attempt is slow, so retrying turns one dead feed into minutes of
    wasted wall-clock. UnsafeURLError (SSRF/oversize) is never retried.
    """
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code in RETRIABLE_STATUS
    return False


def safe_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float | tuple[float, float],
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    max_redirects: int = 5,
    retries: int = 0,
    backoff: float = 2.0,
) -> bytes:
    """Fetch a URL's body with SSRF and size guards, validating each redirect hop.

    Retries up to `retries` times on a transient or WAF-style failure (see
    RETRIABLE_STATUS), with exponential backoff, since a GTFS host behind a bot
    filter often serves the second request. Returns the bytes; raises
    UnsafeURLError or the last requests exception.
    """
    for attempt in range(retries + 1):
        try:
            return _fetch_once(
                url,
                headers=headers,
                timeout=timeout,
                max_bytes=max_bytes,
                max_redirects=max_redirects,
            )
        except (requests.exceptions.RequestException, UnsafeURLError) as exc:
            if attempt >= retries or not _is_retriable(exc):
                raise
            time.sleep(backoff**attempt)
    raise UnsafeURLError(f"exhausted retries fetching {url!r}")  # unreachable; for type-checkers


def _fetch_once(
    url: str,
    *,
    headers: dict[str, str] | None,
    timeout: float | tuple[float, float],
    max_bytes: int,
    max_redirects: int,
) -> bytes:
    """A single fetch attempt with SSRF, redirect, and size guards."""
    session = requests.Session()
    current = url
    for _ in range(max_redirects + 1):
        validate_public_url(current)
        resp = session.get(
            current, headers=headers, timeout=timeout, stream=True, allow_redirects=False
        )
        try:
            if resp.is_redirect or resp.is_permanent_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise UnsafeURLError("redirect response had no Location header")
                current = urljoin(current, location)
                continue
            resp.raise_for_status()
            declared = resp.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise UnsafeURLError(f"response is {declared} bytes, over the {max_bytes} cap")
            body = bytearray()
            for chunk in resp.iter_content(chunk_size=1 << 20):
                body += chunk
                if len(body) > max_bytes:
                    raise UnsafeURLError(f"response exceeded the {max_bytes}-byte cap")
            return bytes(body)
        finally:
            resp.close()
    raise UnsafeURLError(f"too many redirects (>{max_redirects}) starting at {url!r}")
