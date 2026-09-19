"""A client that enforces the `schema_version` guard on every response."""

from __future__ import annotations

import httpx

from .generated import Client
from .guard import acheck_response, check_response

#: The public instance. A fork's own host works anywhere a base URL is taken.
DEFAULT_BASE_URL = "https://gtfsscorecard.org"


def make_client(
    base_url: str = DEFAULT_BASE_URL,
    *,
    guard: bool = True,
    timeout: float = 30.0,
    follow_redirects: bool = False,
    raise_on_unexpected_status: bool = False,
    transport: httpx.BaseTransport | None = None,
    async_transport: httpx.AsyncBaseTransport | None = None,
) -> Client:
    """Build the generated `Client`, with the guard on both its sync and async paths.

    The read API is static files: no key, no session, no write path. With
    `guard=True` (the default) every JSON response that carries a
    `schema_version` is checked, and a major version this client was not
    generated for raises `UnsupportedSchemaVersion` before any model is built.
    Pass `guard=False` to parse whatever the host serves.

    `transport` and `async_transport` exist so tests can serve recorded
    responses without a network.
    """
    limit = httpx.Timeout(timeout)
    client = Client(
        base_url=base_url,
        timeout=limit,
        follow_redirects=follow_redirects,
        raise_on_unexpected_status=raise_on_unexpected_status,
    )
    client.set_httpx_client(
        httpx.Client(
            base_url=base_url,
            timeout=limit,
            follow_redirects=follow_redirects,
            event_hooks={"response": [check_response]} if guard else {},
            transport=transport,
        )
    )
    client.set_async_httpx_client(
        httpx.AsyncClient(
            base_url=base_url,
            timeout=limit,
            follow_redirects=follow_redirects,
            event_hooks={"response": [acheck_response]} if guard else {},
            transport=async_transport,
        )
    )
    return client
