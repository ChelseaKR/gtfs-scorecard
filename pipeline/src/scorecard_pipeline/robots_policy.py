"""Read a host's robots.txt before requesting a feed from it (ADR 0070).

The maintainer's rules, decided 2026-10-13:

- Every request for a feed identifies the project (``USER_AGENT``). Nothing
  presents as a browser.
- An explicit ``Disallow`` that covers the feed path is obeyed. The record is
  "not fetched: robots disallows", which is shown as that and never as a
  score.
- A 404 or 410 at ``/robots.txt`` means the host publishes no rules.
- A 403 at ``/robots.txt`` also means "no file", but only on the hosts in
  ``MISSING_OBJECT_403_HOSTS``: object stores and API gateways where 403 is the
  generic answer for any object that does not exist. Each entry carries the
  reason and the date it was checked.
- Everywhere else, a 401, 403, 429 or 5xx, a redirect that leaves the
  ``robots.txt`` path, an HTML page served in place of a rules file, or a
  failure to read the file at all puts the host off-limits.

One request per origin per process, cached.
"""

from __future__ import annotations

import fnmatch
import importlib.metadata
import urllib.parse
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass

from .instance import BASE_URL


def _package_version() -> str:
    try:
        return importlib.metadata.version("gtfs-scorecard")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - source checkout
        return "unknown"


USER_AGENT = f"gtfs-scorecard/{_package_version()} (+{BASE_URL})"

# Reason codes, written into run summaries and reports.
NO_ROBOTS_FILE = "no_robots_file"
MISSING_OBJECT_403 = "missing_object_403"
ALLOWED_BY_ROBOTS = "allowed_by_robots"
DISALLOWED_BY_ROBOTS = "disallowed_by_robots"
ROBOTS_REDIRECTED_OFF = "robots_redirected_off"
ROBOTS_NOT_A_RULES_FILE = "robots_not_a_rules_file"
ROBOTS_UNREACHABLE = "robots_unreachable"
INVALID_URL = "invalid_url"

# The two public phrases a refused record carries. The first is the
# maintainer's wording for an explicit Disallow.
NOT_FETCHED_DISALLOWED = "not fetched: robots disallows"
NOT_FETCHED_OFF_LIMITS = "not fetched: robots.txt refused or unreadable"
NOT_FETCHED_PREFIX = "not fetched:"


@dataclass(frozen=True)
class AllowlistedHost:
    """A host whose 403 at /robots.txt is the generic missing-object answer."""

    pattern: str  # an fnmatch pattern over the lowercase hostname
    reason: str


# Each entry was checked on 2026-10-13 by requesting /robots.txt and a random
# path that cannot exist: both answered 403 with the store's own error body
# (S3-compatible ``<Error><Code>AccessDenied</Code>`` XML, or API Gateway's
# ``Missing Authentication Token``), while the feed objects themselves answer
# 200. A host is added only with that evidence; a WAF or CDN that answers 403
# to every unknown client (Cloudflare challenge pages, Akamai, a city's web
# firewall) is not a missing-object answer and stays off-limits.
_S3 = "Amazon S3: a missing object in a non-listable bucket answers 403 AccessDenied"
_S3_DOMAIN = (
    "S3 bucket behind a custom domain (Server: AmazonS3); /robots.txt and a random "
    "path both answer 403 AccessDenied"
)
MISSING_OBJECT_403_HOSTS: tuple[AllowlistedHost, ...] = (
    AllowlistedHost("s3.amazonaws.com", _S3),
    AllowlistedHost("s3.*.amazonaws.com", _S3),
    AllowlistedHost("s3-*.amazonaws.com", _S3),
    AllowlistedHost("*.s3.amazonaws.com", _S3),
    AllowlistedHost("*.s3.*.amazonaws.com", _S3),
    AllowlistedHost("*.s3-*.amazonaws.com", _S3),
    AllowlistedHost(
        "storage.googleapis.com",
        "Google Cloud Storage: a missing object in a private bucket answers 403 AccessDenied",
    ),
    AllowlistedHost(
        "*.digitaloceanspaces.com",
        "DigitalOcean Spaces (S3-compatible): a missing object answers 403 AccessDenied",
    ),
    AllowlistedHost(
        "api.gtfs-data.jp",
        "AWS API Gateway: any undefined route answers 403 Missing Authentication Token",
    ),
    AllowlistedHost("ajt-mobusta-gtfs.mcapps.jp", _S3_DOMAIN),
    AllowlistedHost("gtfs.remix.com", _S3_DOMAIN),
    AllowlistedHost("eu-gtfs.remix.com", _S3_DOMAIN),
    AllowlistedHost("gtfs.sound.obaweb.org", _S3_DOMAIN),
    AllowlistedHost("gtfs.adelaidemetro.com.au", _S3_DOMAIN),
    AllowlistedHost("gtfs.vta.org", _S3_DOMAIN),
    AllowlistedHost("cdn.hibuwebsites.com", _S3_DOMAIN),
    AllowlistedHost("irp.cdn-website.com", _S3_DOMAIN),
    AllowlistedHost(
        "static.data.gov.hk",
        "S3-compatible store behind a custom domain; /robots.txt and a random path both "
        "answer 403 AccessDenied XML",
    ),
    AllowlistedHost(
        "media.ilevia.fr",
        "S3-compatible bucket behind Cloudflare; /robots.txt and a random path both "
        "answer 403 AccessDenied XML naming the bucket",
    ),
    AllowlistedHost(
        "d16k74nzx9emoe.cloudfront.net",
        "CloudFront distribution over an S3 origin (Server: AmazonS3); a random path "
        "answers 403 AccessDenied",
    ),
    AllowlistedHost(
        "d2igk3wxwksqfb.cloudfront.net",
        "CloudFront distribution over an S3 origin (Server: AmazonS3); a random path "
        "answers 403 AccessDenied",
    ),
)


def allowlisted_403(host: str) -> AllowlistedHost | None:
    """The allowlist entry that covers ``host``, if any."""
    name = host.lower().rstrip(".")
    for entry in MISSING_OBJECT_403_HOSTS:
        if fnmatch.fnmatchcase(name, entry.pattern):
            return entry
    return None


@dataclass(frozen=True)
class RobotsVerdict:
    """Whether a URL may be requested, and the evidence for that answer."""

    allowed: bool
    reason: str

    @property
    def not_fetched_reason(self) -> str:
        """The public phrase for a refusal."""
        if self.reason == DISALLOWED_BY_ROBOTS:
            return NOT_FETCHED_DISALLOWED
        return NOT_FETCHED_OFF_LIMITS


class RobotsRefusedError(RuntimeError):
    """A feed request this project will not make, because of robots.txt.

    Raised before any request for the feed itself. ``reason`` is the fixed
    phrase the run summary records; ``detail`` is the verdict's reason code.
    It is not a ``requests`` exception, so realtime sampling treats it as "not
    measured", never as the agency's outage.
    """

    def __init__(self, verdict: RobotsVerdict, url_host: str) -> None:
        self.reason = verdict.not_fetched_reason
        self.detail = verdict.reason
        super().__init__(f"{self.reason} ({verdict.reason} at {url_host})")


def robots_url(url: str) -> str | None:
    """The ``robots.txt`` URL for ``url``'s origin, or None for a non-HTTP URL."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return f"{parts.scheme}://{parts.netloc}/robots.txt"


def _looks_like_html(content_type: str, body: str) -> bool:
    if "html" in content_type.lower():
        return True
    return body.lstrip()[:64].lower().startswith(("<!doctype", "<html"))


def classify_robots_response(
    *,
    target_url: str,
    status: int,
    final_url: str,
    content_type: str,
    body: str,
    user_agent: str = USER_AGENT,
) -> RobotsVerdict:
    """Decide from one ``/robots.txt`` response whether ``target_url`` may be fetched."""
    if status in (404, 410):
        return RobotsVerdict(True, NO_ROBOTS_FILE)
    if status == 403 and allowlisted_403(urllib.parse.urlsplit(target_url).hostname or ""):
        return RobotsVerdict(True, MISSING_OBJECT_403)
    if status >= 400:
        return RobotsVerdict(False, f"robots_status_{status}")
    if not urllib.parse.urlsplit(final_url).path.endswith("/robots.txt"):
        return RobotsVerdict(False, ROBOTS_REDIRECTED_OFF)
    if _looks_like_html(content_type, body):
        return RobotsVerdict(False, ROBOTS_NOT_A_RULES_FILE)
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(body.splitlines())
    if parser.can_fetch(user_agent, target_url):
        return RobotsVerdict(True, ALLOWED_BY_ROBOTS)
    return RobotsVerdict(False, DISALLOWED_BY_ROBOTS)


@dataclass(frozen=True)
class RobotsResponse:
    status: int
    final_url: str
    content_type: str
    body: str


Getter = Callable[[str], RobotsResponse]

# RFC 9309 lets a crawler stop reading after 500 KiB.
ROBOTS_MAX_BYTES = 512 * 1024


def _default_get(url: str) -> RobotsResponse:
    """Read one robots.txt through the SSRF-guarded client, keeping the status."""
    import requests

    from .net import FetchTrace, safe_get

    trace = FetchTrace()
    try:
        body = safe_get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=(12, 20),
            max_bytes=ROBOTS_MAX_BYTES,
            trace=trace,
        )
    except requests.exceptions.HTTPError as exc:
        response = exc.response
        if response is None:
            raise
        return RobotsResponse(
            status=response.status_code,
            final_url=str(response.url or url),
            content_type=str(response.headers.get("content-type", "")),
            body="",
        )
    return RobotsResponse(
        status=200,
        final_url=trace.final_url or url,
        content_type="",
        body=body.decode("utf-8", "replace"),
    )


class RobotsChecker:
    """Check URLs against their hosts' robots.txt, one request per origin.

    ``get`` is injectable for tests. A failure to read the file is a refusal
    (``robots_unreachable``), never permission.
    """

    def __init__(self, get: Getter | None = None) -> None:
        self._get = get or _default_get
        self._responses: dict[str, RobotsResponse | None] = {}

    def _response(self, rules_url: str) -> RobotsResponse | None:
        if rules_url not in self._responses:
            try:
                self._responses[rules_url] = self._get(rules_url)
            except Exception:  # any failure to read the rules is a refusal
                self._responses[rules_url] = None
        return self._responses[rules_url]

    def check(self, url: str) -> RobotsVerdict:
        rules_url = robots_url(url)
        if rules_url is None:
            return RobotsVerdict(False, INVALID_URL)
        response = self._response(rules_url)
        if response is None:
            return RobotsVerdict(False, ROBOTS_UNREACHABLE)
        return classify_robots_response(
            target_url=url,
            status=response.status,
            final_url=response.final_url,
            content_type=response.content_type,
            body=response.body,
        )

    def require(self, url: str) -> None:
        """Raise ``RobotsRefusedError`` unless ``url`` may be requested."""
        verdict = self.check(url)
        if not verdict.allowed:
            raise RobotsRefusedError(verdict, urllib.parse.urlsplit(url).hostname or "")


_SHARED: RobotsChecker | None = None


def shared_checker() -> RobotsChecker:
    """The process-wide checker, so a shard reads each host's file once."""
    global _SHARED
    if _SHARED is None:
        _SHARED = RobotsChecker()
    return _SHARED


def reset_shared_checker(checker: RobotsChecker | None = None) -> None:
    """Replace (or clear) the process-wide checker; for tests."""
    global _SHARED
    _SHARED = checker
