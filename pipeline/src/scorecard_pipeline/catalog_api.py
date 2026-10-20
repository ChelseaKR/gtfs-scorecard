"""Read the Mobility Database catalog through its API (ADR 0070).

`files.mobilitydatabase.org` serves `User-agent: * / Disallow: /`, so this
project no longer reads it, for the catalog or for anything else. The weekly
catalog update reads the official Mobility Database API instead, authenticated
with the maintainer's refresh token in ``MOBILITY_FEED_API_TOKEN``. Without the
token the update pauses with a message that says so. It never falls back to
the disallowed host or to any other source.

The API answers `/v1/gtfs_feeds` in pages. Each feed record is mapped onto the
same ``CatalogFeed`` shape the CSV parser produces, so `discover` and
`supersessions` consume it unchanged: status, the official flag, the
producer URL and its authentication type, the license link, the first
location, and the redirect targets that record a retirement.

Parsing is pure and tested against fixture JSON. The two network calls take
injectable callables.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from .mobilitydb import CatalogFeed
from .robots_policy import USER_AGENT

API_BASE = "https://api.mobilitydatabase.org/v1"
TOKEN_ENV = "MOBILITY_FEED_API_TOKEN"  # noqa: S105 - the variable name, not a secret
PAGE_SIZE = 500
# A hard stop on pagination, far above the catalog's size, so a server that
# ignores offset cannot loop the weekly job forever.
MAX_PAGES = 200

PAUSED_MESSAGE = (
    "Catalog update paused: MOBILITY_FEED_API_TOKEN is not set. This project reads the "
    "Mobility Database only through its API (files.mobilitydatabase.org disallows "
    "automated access), so nothing was read and nothing changed. Set the repository "
    "secret to resume."
)

Post = Callable[[str, Mapping[str, Any], Mapping[str, str]], Mapping[str, Any]]
Get = Callable[[str, Mapping[str, str]], Any]


class CatalogPausedError(RuntimeError):
    """The API token is not configured, so the catalog was not read at all."""

    def __init__(self) -> None:
        super().__init__(PAUSED_MESSAGE)


def configured_token(environ: Mapping[str, str] | None = None) -> str:
    """The refresh token from the environment, or raise ``CatalogPausedError``."""
    token = (environ if environ is not None else os.environ).get(TOKEN_ENV, "").strip()
    if not token:
        raise CatalogPausedError
    return token


def _default_post(url: str, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Any:
    import requests

    from .net import validate_public_url

    validate_public_url(url)
    response = requests.post(url, json=dict(payload), headers=dict(headers), timeout=60)
    response.raise_for_status()
    return response.json()


def _default_get(url: str, headers: Mapping[str, str]) -> Any:
    from .net import safe_get

    return json.loads(safe_get(url, headers=dict(headers), timeout=120).decode("utf-8"))


def access_token(refresh_token: str, *, post: Post | None = None) -> str:
    """Exchange the long-lived refresh token for a short-lived access token."""
    send = post or _default_post
    body = send(
        f"{API_BASE}/tokens",
        {"refresh_token": refresh_token},
        {"User-Agent": USER_AGENT, "Content-Type": "application/json"},
    )
    token = str(body.get("access_token") or "")
    if not token:
        raise RuntimeError("the Mobility Database API returned no access token")
    return token


def fetch_gtfs_feeds(token: str, *, get: Get | None = None) -> list[dict[str, Any]]:
    """Every GTFS Schedule feed record, page by page."""
    read = get or _default_get
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    rows: list[dict[str, Any]] = []
    for page in range(MAX_PAGES):
        url = f"{API_BASE}/gtfs_feeds?limit={PAGE_SIZE}&offset={page * PAGE_SIZE}"
        batch = read(url, headers)
        if not isinstance(batch, list):
            raise RuntimeError("the Mobility Database API returned a non-list feed page")
        rows.extend(row for row in batch if isinstance(row, dict))
        if len(batch) < PAGE_SIZE:
            return rows
    raise RuntimeError(f"the Mobility Database API returned more than {MAX_PAGES} pages")


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _official(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in ("true", "1"):
        return True
    if text in ("false", "0"):
        return False
    return None


def catalog_feed_from_api(row: Mapping[str, Any]) -> CatalogFeed | None:
    """One API feed record as a ``CatalogFeed``, or None when it is not Schedule."""
    data_type = _text(row.get("data_type")).lower() or "gtfs"
    if data_type != "gtfs":
        return None
    source = row.get("source_info") or {}
    locations = row.get("locations") or [{}]
    location = locations[0] if isinstance(locations, list) and locations else {}
    latest = row.get("latest_dataset") or {}
    redirects = row.get("redirects") or []
    redirect_ids = tuple(
        dict.fromkeys(
            _text(item.get("target_id"))
            for item in redirects
            if isinstance(item, Mapping) and _text(item.get("target_id"))
        )
    )
    return CatalogFeed(
        mdb_id=_text(row.get("id")),
        data_type="gtfs",
        entity_type="",
        country=_text(location.get("country_code")).upper(),
        subdivision_code="",
        subdivision=_text(location.get("subdivision_name")),
        municipality=_text(location.get("municipality")),
        provider=_text(row.get("provider")),
        name=_text(row.get("feed_name")),
        direct_download=_text(source.get("producer_url")),
        license_url=_text(source.get("license_url")),
        authentication_type=_text(source.get("authentication_type")),
        static_reference="",
        hosted_url=_text(latest.get("hosted_url")) if isinstance(latest, Mapping) else "",
        status=_text(row.get("status")).lower(),
        is_official=_official(row.get("official")),
        redirect_ids=redirect_ids,
    )


def catalog_feeds_from_api(rows: list[dict[str, Any]]) -> list[CatalogFeed]:
    """Map an API feed list, keeping only Schedule records, in source order."""
    feeds: list[CatalogFeed] = []
    for position, row in enumerate(rows, start=1):
        feed = catalog_feed_from_api(row)
        if feed is not None and feed.mdb_id:
            feeds.append(replace(feed, source_record_number=position))
    return feeds


def load_api_catalog(
    *,
    environ: Mapping[str, str] | None = None,
    post: Post | None = None,
    get: Get | None = None,
) -> list[CatalogFeed]:
    """The whole Schedule catalog from the API; raises ``CatalogPausedError``
    before any request when the token is not configured."""
    refresh = configured_token(environ)
    token = access_token(refresh, post=post)
    return catalog_feeds_from_api(fetch_gtfs_feeds(token, get=get))
