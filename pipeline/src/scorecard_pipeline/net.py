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

import binascii
import hashlib
import hmac
import ipaddress
import socket
import ssl
import time
from importlib.resources import files
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
import truststore
from requests.adapters import HTTPAdapter

# Ceiling for any single feed or jar download. Real GTFS feeds are well under
# this; the cap exists to stop a hostile or misconfigured endpoint.
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024

# Statuses worth a retry: a momentary 429/5xx, or a WAF 403 that often lets a
# second request through. SSRF and oversize rejections are never retried.
RETRIABLE_STATUS = frozenset({403, 408, 425, 429, 500, 502, 503, 504})

# Some early-generation Let's Encrypt Root YR deployments omit the official
# cross-certificate needed to reach the already-trusted ISRG Root X1. Keep the
# bridge's provenance independent of any feed server and fail closed if the
# packaged certificate changes. Source:
# https://letsencrypt.org/certs/gen-y/root-yr-by-x1.pem
_ROOT_YR_BY_X1_RESOURCE = "certs/root-yr-by-x1.pem"
_ROOT_YR_BY_X1_SHA256 = "072639d0b140d5bffae16ad9c3f6cc6086040621f51ee61a6d46a8915c07cf76"


class UnsafeURLError(ValueError):
    """A URL was rejected before or during fetching (bad scheme, private host,
    oversized response, or too many redirects)."""


def _validated_root_yr_bridge(pem: str) -> str:
    """Return the official Root YR cross-certificate after checking its DER hash."""
    try:
        der = ssl.PEM_cert_to_DER_cert(pem)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("bundled Root YR bridge is not valid PEM") from exc
    actual = hashlib.sha256(der).hexdigest()
    if not hmac.compare_digest(actual, _ROOT_YR_BY_X1_SHA256):
        raise RuntimeError("bundled Root YR bridge fingerprint does not match Let's Encrypt")
    return pem


def _system_tls_context() -> ssl.SSLContext:
    """Build a scoped client context from OS trust plus one verified CA bridge.

    ``VERIFY_X509_PARTIAL_CHAIN`` stays disabled so the cross-certificate is an
    intermediate, not a trust anchor: a chain must still reach a root trusted by
    the operating system (ISRG Root X1 for the bundled bridge).
    """
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.verify_flags = ssl.VerifyFlags(context.verify_flags & ~ssl.VERIFY_X509_PARTIAL_CHAIN)
    bridge = (
        files("scorecard_pipeline").joinpath(_ROOT_YR_BY_X1_RESOURCE).read_text(encoding="ascii")
    )
    context.load_verify_locations(cadata=_validated_root_yr_bridge(bridge))
    return context


class _SystemTrustHTTPSAdapter(HTTPAdapter):
    """Requests adapter that applies the scoped system-trust context to HTTPS."""

    def __init__(self, context: ssl.SSLContext) -> None:
        self.ssl_context = context
        super().__init__()

    def init_poolmanager(
        self,
        connections: int,
        maxsize: int,
        block: bool = False,
        **pool_kwargs: Any,
    ) -> None:
        pool_kwargs["ssl_context"] = self.ssl_context
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any) -> Any:
        # HTTPS destinations must use the same trust policy through a proxy.
        proxy_kwargs["ssl_context"] = self.ssl_context
        if urlsplit(proxy).scheme.lower() == "https":
            proxy_kwargs["proxy_ssl_context"] = self.ssl_context
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def _new_http_session() -> requests.Session:
    """Create an isolated session whose HTTPS requests use system trust."""
    session = requests.Session()
    session.mount("https://", _SystemTrustHTTPSAdapter(_system_tls_context()))
    session.verify = True
    return session


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
    session = _new_http_session()
    try:
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
    finally:
        session.close()
