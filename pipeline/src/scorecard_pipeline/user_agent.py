"""The one User-Agent every automated request sends (ADR 0070, ADR 0075).

The maintainer's rule, restated 2026-11-05: every automated fetch the pipeline
makes -- feed downloads, realtime samples, robots.txt reads, liveness checks,
catalog and overlay downloads, any HTTP client -- names the scorecard and links
to the page that explains the fetcher. Nothing presents as a browser.

``net.safe_get`` and ``net.safe_download`` add this header when a caller sends
none and refuse to send a browser-like one (``BrowserUserAgentError``), so a
regression fails loudly at the request instead of reaching a publisher's logs.
Clients that cannot import the pipeline (the Lambdas under ``infra/``) carry
the same shape as a literal, and ``tests/test_user_agent.py`` scans the tree for
any other value.
"""

from __future__ import annotations

import importlib.metadata
import re

from .instance import BASE_URL


def _package_version() -> str:
    try:
        return importlib.metadata.version("gtfs-scorecard")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - source checkout
        return "unknown"


#: The page a publisher reaches from the header: who is asking, how often,
#: what robots.txt does, and how to tell us to stop.
FETCHER_URL = f"{BASE_URL}/fetcher/"

#: ``gtfs-scorecard/<version> (+https://gtfsscorecard.org/fetcher/)``
USER_AGENT = f"gtfs-scorecard/{_package_version()} (+{FETCHER_URL})"

# Product tokens only browsers (or clients imitating one) send. "Mozilla/" is
# the prefix every mainstream browser string starts with; the rest catch a
# string assembled without it.
_BROWSER_TOKENS = re.compile(
    r"mozilla/|applewebkit|chrome/|chromium/|safari/|firefox/|gecko/|edg/|opr/|"
    r"\bmsie\b|trident/|khtml",
    re.IGNORECASE,
)


class BrowserUserAgentError(ValueError):
    """Raised before a request that would present as a browser."""


def is_browser_like(user_agent: str) -> bool:
    """True when ``user_agent`` carries a browser product token."""
    return bool(_BROWSER_TOKENS.search(user_agent or ""))


def is_identifying(user_agent: str) -> bool:
    """True when ``user_agent`` names the scorecard and links to a page.

    The shape is ``gtfs-scorecard[/<version>][ <purpose>] (+https://...)``.
    """
    return (
        user_agent.startswith("gtfs-scorecard")
        and "(+https://" in user_agent
        and not is_browser_like(user_agent)
    )


def require_identifying(user_agent: str) -> str:
    """Return ``user_agent`` unchanged, or raise if it would not identify us."""
    if is_browser_like(user_agent):
        raise BrowserUserAgentError(
            f"refusing to send a browser-like User-Agent ({user_agent!r}); "
            "automated requests identify the scorecard (ADR 0075)"
        )
    if not is_identifying(user_agent):
        raise BrowserUserAgentError(
            f"refusing to send a User-Agent that does not name the scorecard and link to "
            f"{FETCHER_URL} ({user_agent!r}; ADR 0075)"
        )
    return user_agent


def with_identifying_user_agent(headers: dict[str, str] | None) -> dict[str, str]:
    """``headers`` with the scorecard's User-Agent filled in and checked.

    A caller that names no User-Agent gets :data:`USER_AGENT`. A caller that
    names one must pass :func:`require_identifying`. Header names are matched
    case-insensitively, as HTTP does.
    """
    out = dict(headers or {})
    key = next((k for k in out if k.lower() == "user-agent"), None)
    if key is None:
        out["User-Agent"] = USER_AGENT
    else:
        require_identifying(out[key])
    return out
