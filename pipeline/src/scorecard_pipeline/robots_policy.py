"""Read a host's robots.txt before this project starts requesting a new URL.

The daily fetcher does not consult robots.txt (see
docs/mobility-database-access-review.md, which leaves that decision with the
maintainer). This module is narrower: it is the check a catalog-driven registry
edit runs before it points a tracked record at a URL the project has never
requested. A URL that fails the check is held for a person instead of being
written into the registry.

The rules are deliberately strict, and every refusal names its reason:

- a 404 or 410 at ``/robots.txt`` means the host publishes no rules, so the
  URL is allowed;
- any other error status (401, 403, 429, 5xx) is a host refusing us, so the
  URL is held;
- a redirect that does not end on a ``robots.txt`` path, or an HTML page
  served in place of one, is not a rules file, so the URL is held rather than
  read as permission;
- otherwise the file is parsed and asked whether this project's honest
  User-Agent may fetch the URL.

The request identifies the project. It never presents as a browser.
"""

from __future__ import annotations

import urllib.parse
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .instance import BASE_URL

USER_AGENT = f"gtfs-scorecard catalog check (+{BASE_URL})"

# Reason codes. Stable strings: they are written into the weekly report.
NO_ROBOTS_FILE = "no_robots_file"
ALLOWED_BY_ROBOTS = "allowed_by_robots"
DISALLOWED_BY_ROBOTS = "disallowed_by_robots"
ROBOTS_REDIRECTED_OFF = "robots_redirected_off"
ROBOTS_NOT_A_RULES_FILE = "robots_not_a_rules_file"
ROBOTS_UNREACHABLE = "robots_unreachable"
INVALID_URL = "invalid_url"


@dataclass(frozen=True)
class RobotsVerdict:
    """Whether a URL may be requested, and the evidence for that answer."""

    allowed: bool
    reason: str


def robots_url(url: str) -> str | None:
    """The ``robots.txt`` URL for ``url``'s origin, or None for a non-HTTP URL."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}/robots.txt"


def _looks_like_html(content_type: str, body: str) -> bool:
    if "html" in content_type.lower():
        return True
    head = body.lstrip()[:64].lower()
    return head.startswith(("<!doctype", "<html"))


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


class RobotsChecker:
    """Check URLs against their hosts' robots.txt, one request per origin.

    ``get`` is a ``requests.get``-shaped callable, injectable for tests. A
    network failure is a refusal (``robots_unreachable``), never permission.
    """

    def __init__(self, get: Callable[..., Any] | None = None, timeout: float = 20.0) -> None:
        if get is None:
            import requests

            get = requests.get
        self._get = get
        self._timeout = timeout
        self._responses: dict[str, tuple[int, str, str, str] | None] = {}

    def _response(self, rules_url: str) -> tuple[int, str, str, str] | None:
        if rules_url not in self._responses:
            try:
                response = self._get(
                    rules_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=self._timeout,
                    allow_redirects=True,
                )
                self._responses[rules_url] = (
                    int(response.status_code),
                    str(response.url or rules_url),
                    str(response.headers.get("content-type", "")),
                    str(response.text or ""),
                )
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
        status, final_url, content_type, body = response
        return classify_robots_response(
            target_url=url,
            status=status,
            final_url=final_url,
            content_type=content_type,
            body=body,
        )
