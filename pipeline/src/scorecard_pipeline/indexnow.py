"""IndexNow: tell search engines which pages are new or changed after a deploy.

Protocol: https://www.indexnow.org/documentation (read 2026-10-22). A site
proves it owns its host by serving ``https://<host>/<key>.txt`` whose body is
the key (8-128 hex characters; the key is public by design, so there is no
secret anywhere in this flow). A POST of ``{"host", "key", "keyLocation",
"urlList"}`` to ``/indexnow`` submits up to 10,000 URLs per request; every URL
must be on ``host``. One submission to a participating endpoint is shared with
the others.

gtfsscorecard.org (ADR 0073) uses ``--kind sitemap``: a sitemap ``lastmod``
here is a date the page's own content changed, never the build clock (ADR
0067), so a URL is announced when it is new or its ``lastmod`` moved. The
same module runs on Trout Truck, Next Home Game, Lake Notice and Tide Hours.

Two steps, so the selection can be checked before anything is sent:

``select``  compares this build with what is live now (the previous deploy)
            and writes the URLs that are new or changed. Runs after the build
            and before the deploy replaces the live site.
``submit``  POSTs that list. Runs only after the production deploy. It never
            fails the job: any problem becomes a ``::notice::`` line.

Rules enforced here, and again by ``validate_submission`` on the final list:
only https URLs on the site's own host, only pages that exist in the build and
carry no robots noindex, no duplicates, at most 10,000 per request. Stdlib
only; the HTTP client is injectable so tests never touch the network.
"""

from __future__ import annotations

import argparse
import html
import http.client
import json
import re
import socket
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS = 10_000
KEY_FILE_RE = re.compile(r"^([0-9a-f]{32})\.txt$")
BOT = "bingbot"
USER_AGENT = "indexnow-submit (+https://github.com/ChelseaKR)"
_NOINDEX_RE = re.compile(
    r"<meta\b[^>]*\bname\s*=\s*[\"']robots[\"'][^>]*\bcontent\s*=\s*[\"'][^\"']*noindex",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"<url>(.*?)</url>", re.DOTALL)
_LOC_RE = re.compile(r"<loc>\s*([^<]*?)\s*</loc>")
_LASTMOD_RE = re.compile(r"<lastmod>\s*([^<]*?)\s*</lastmod>")


class IndexNowError(ValueError):
    """The submission list or key setup breaks a rule; nothing is sent."""


class HttpClient(Protocol):
    def post_json(self, url: str, body: bytes, headers: Mapping[str, str]) -> int: ...


class HttpsClient:
    """http.client over TLS to a fixed https endpoint; no scheme can be swapped."""

    def post_json(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        status, _ = _request("POST", url, body, headers)
        return status


def _request(
    method: str, url: str, body: bytes | None, headers: Mapping[str, str]
) -> tuple[int, bytes]:
    """One https request, following at most 3 redirects to https URLs."""
    for _ in range(4):
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise IndexNowError(f"only https URLs are requested: {url!r}")
        # The scheme was checked as https just above; Python 3.12 verifies certificates by default.
        # nosemgrep: python.lang.security.audit.httpsconnection-detected.httpsconnection-detected
        conn = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=20)
        try:
            target = parts.path or "/"
            if parts.query:
                target += "?" + parts.query
            conn.request(method, target, body=body, headers=dict(headers))
            resp = conn.getresponse()
            data = resp.read()
            location = resp.getheader("Location")
            if resp.status in (301, 302, 303, 307, 308) and location:
                url = urljoin(url, location)
                continue
            return resp.status, data
        finally:
            conn.close()
    raise IndexNowError("too many redirects")


def host_of(base_url: str) -> str:
    parts = urlsplit(base_url)
    if parts.scheme != "https" or not parts.hostname:
        raise IndexNowError(f"base URL must be https with a host: {base_url!r}")
    return parts.hostname


def parse_sitemap(xml_text: str) -> dict[str, str]:
    """url -> lastmod ('' when the entry has none). Read with patterns, not an
    XML parser: the file is our own build output, and a pattern cannot be made
    to expand entities."""
    out: dict[str, str] = {}
    for block in _URL_RE.findall(xml_text):
        loc = _LOC_RE.search(block)
        if loc is None or not loc.group(1):
            continue
        mod = _LASTMOD_RE.search(block)
        out[html.unescape(loc.group(1))] = html.unescape(mod.group(1)) if mod else ""
    return out


def is_noindex(html: str) -> bool:
    return _NOINDEX_RE.search(html) is not None


def page_file(site_dir: Path, base_url: str, url: str) -> Path | None:
    """The built file that serves ``url``, or None when it is not under the base."""
    base = base_url.rstrip("/")
    if not url.startswith(base + "/"):
        return None
    rel = url[len(base) + 1 :].split("#")[0].split("?")[0]
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    return site_dir / rel


def find_key(site_dir: Path) -> str:
    """The one key file at the build root: ``<32 hex>.txt`` whose body is the key."""
    keys = []
    for p in site_dir.iterdir():
        m = KEY_FILE_RE.match(p.name)
        if m and p.is_file():
            if p.read_text(encoding="utf-8").strip() != m.group(1):
                raise IndexNowError(f"{p.name}: body must equal the key in its name")
            keys.append(m.group(1))
    if len(keys) != 1:
        raise IndexNowError(
            f"expected exactly one IndexNow key file in {site_dir}, found {len(keys)}"
        )
    return keys[0]


def copy_key_file(src_dir: Path, out_dir: Path) -> Path:
    """Copy the committed key file from ``src_dir`` to the root of a build."""
    key = find_key(src_dir)
    dest = out_dir / f"{key}.txt"
    dest.write_text(f"{key}\n", encoding="utf-8")
    return dest


def check_robots(robots_text: str, base_url: str) -> list[str]:
    """Problems with robots.txt for this purpose: Bingbot blocked, or no sitemap."""
    rp = RobotFileParser()
    rp.parse(robots_text.splitlines())
    problems = []
    if not rp.can_fetch(BOT, base_url.rstrip("/") + "/"):
        problems.append("robots.txt does not allow Bingbot at the site root")
    sitemap = base_url.rstrip("/") + "/sitemap.xml"
    if sitemap not in (rp.site_maps() or []):
        problems.append(f"robots.txt does not list {sitemap}")
    return problems


def select_changed(previous: Mapping[str, str] | None, current: Mapping[str, str]) -> list[str]:
    """URLs new in ``current`` or whose token (lastmod or fingerprint) differs.

    ``previous`` None means the live site could not be read: whether anything
    changed is unknown, so nothing is selected (absence is not "all changed").
    ``{}`` is a site with no earlier pages: everything is new."""
    if previous is None:
        return []
    return sorted(u for u, t in current.items() if u not in previous or previous[u] != t)


def filter_submittable(
    urls: list[str], *, base_url: str, site_dir: Path
) -> tuple[list[str], list[str]]:
    """Keep own-host https pages that exist in the build and are not noindex.
    Returns (kept, notes about what was dropped and why)."""
    host = host_of(base_url)
    kept: list[str] = []
    notes: list[str] = []
    for url in urls:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != host or parts.port or parts.username:
            notes.append(f"dropped (not on {host}): {url}")
            continue
        f = page_file(site_dir, base_url, url)
        if f is None or not f.is_file():
            notes.append(f"dropped (no built page): {url}")
            continue
        if is_noindex(f.read_text(encoding="utf-8", errors="replace")):
            notes.append(f"dropped (noindex): {url}")
            continue
        kept.append(url)
    return kept, notes


def validate_submission(urls: list[str], *, base_url: str, site_dir: Path) -> None:
    """The final gate: raises IndexNowError when the list breaks any rule."""
    if len(urls) > MAX_URLS:
        raise IndexNowError(f"{len(urls)} URLs exceeds the {MAX_URLS} per-request limit")
    if len(set(urls)) != len(urls):
        raise IndexNowError("duplicate URLs in the submission")
    kept, notes = filter_submittable(urls, base_url=base_url, site_dir=site_dir)
    if len(kept) != len(urls):
        raise IndexNowError("; ".join(notes))


def build_payload(base_url: str, key: str, urls: list[str]) -> dict[str, object]:
    host = host_of(base_url)
    return {
        "host": host,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
        "urlList": urls,
    }


def submit(
    payload: Mapping[str, object],
    client: HttpClient | None = None,
    endpoint: str = ENDPOINT,
) -> str:
    """POST the payload. Never raises; returns a one-line outcome."""
    urls = payload["urlList"]
    if not isinstance(urls, list):
        return "IndexNow payload has no urlList"
    if not urls:
        return "nothing to submit: no new or changed pages"
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": USER_AGENT,
    }
    try:
        status = (client or HttpsClient()).post_json(endpoint, body, headers)
    except Exception as exc:
        name = type(exc).__name__
        return f"IndexNow request failed ({name}); pages will be found by the normal crawl"
    if status in (200, 202):
        return f"IndexNow accepted {len(urls)} URLs (HTTP {status})"
    return (
        f"IndexNow answered HTTP {status} for {len(urls)} URLs;"
        " pages will be found by the normal crawl"
    )


def fetch_text(url: str, *, missing_is_empty: bool) -> str | None:
    """Body of a live file. None = unreadable (unknown). '' only for a 404 when
    ``missing_is_empty`` (a site that genuinely has no such file yet), or when the
    host name does not resolve at all (a site that is not live yet)."""
    try:
        status, data = _request("GET", url, None, {"User-Agent": USER_AGENT})
    except socket.gaierror:
        # The host name does not resolve: the site does not exist yet, so
        # every page is new (only when the caller says an absent site is empty).
        return "" if missing_is_empty else None
    except Exception:
        return None
    if status == 200:
        return data.decode("utf-8")
    return "" if (status == 404 and missing_is_empty) else None


def _manifest_tokens(text: str, base_url: str) -> dict[str, str]:
    """url -> fingerprint from a lastmod.json-style manifest (schema 1)."""
    data = json.loads(text)
    pages = data["pages"]
    return {base_url.rstrip("/") + p: str(e["fingerprint"]) for p, e in pages.items()}


def tokens(kind: str, text: str, base_url: str) -> dict[str, str]:
    if kind == "sitemap":
        return parse_sitemap(text)
    if kind == "manifest":
        return _manifest_tokens(text, base_url)
    raise IndexNowError(f"unknown kind {kind!r}")


def cmd_select(args: argparse.Namespace) -> int:
    site_dir, base_url = Path(args.site_dir), args.base_url.rstrip("/")
    out = Path(args.out)
    notes: list[str] = []
    urls: list[str] = []
    try:
        key = find_key(site_dir)
        problems = check_robots((site_dir / "robots.txt").read_text(encoding="utf-8"), base_url)
        if problems:
            raise IndexNowError("; ".join(problems))
        sitemap_urls = set(parse_sitemap((site_dir / "sitemap.xml").read_text(encoding="utf-8")))
        current_text = (site_dir / args.file).read_text(encoding="utf-8")
        current = tokens(args.kind, current_text, base_url)
        current = {u: t for u, t in current.items() if u in sitemap_urls}
        live = fetch_text(f"{base_url}/{args.file}", missing_is_empty=args.missing_is_empty)
        previous = None if live is None else (tokens(args.kind, live, base_url) if live else {})
        if previous is None:
            notes.append(f"could not read the live {args.file}; submitting nothing this deploy")
        urls, drop = filter_submittable(
            select_changed(previous, current), base_url=base_url, site_dir=site_dir
        )
        notes += drop
        if len(urls) > MAX_URLS:
            notes.append(f"{len(urls)} changed; submitting the first {MAX_URLS}")
            urls = urls[:MAX_URLS]
        validate_submission(urls, base_url=base_url, site_dir=site_dir)
        payload = build_payload(base_url, key, urls)
    except Exception as exc:
        notes.append(f"IndexNow selection skipped: {exc}")
        payload = {"host": "", "key": "", "keyLocation": "", "urlList": []}
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    for n in notes:
        print(f"::notice title=IndexNow::{n}")
    print(f"IndexNow: {len(urls)} URLs selected")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(Path(args.list).read_text(encoding="utf-8"))
        outcome = submit(payload)
    except Exception as exc:
        outcome = f"IndexNow submit skipped: {exc}"
    print(f"::notice title=IndexNow::{outcome}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--site-dir", required=True)
    s.add_argument("--base-url", required=True)
    s.add_argument("--kind", choices=("sitemap", "manifest"), required=True)
    s.add_argument(
        "--file",
        required=True,
        help="site-root file to diff: sitemap.xml or lastmod.json",
    )
    s.add_argument("--missing-is-empty", action="store_true")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_select)
    p = sub.add_parser("submit")
    p.add_argument("--list", required=True)
    p.set_defaults(fn=cmd_submit)
    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
