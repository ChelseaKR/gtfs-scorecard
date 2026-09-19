from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.rollup import Rollup
from ...types import Response


def _get_kwargs(
    rollup_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/data/artifacts/rollups/{rollup_id}.json".format(
            rollup_id=quote(str(rollup_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Rollup | None:
    if response.status_code == 200:
        response_200 = Rollup.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Rollup]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    rollup_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Rollup]:
    """One rollup across many agencies.

    Args:
        rollup_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Rollup]
    """

    kwargs = _get_kwargs(
        rollup_id=rollup_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rollup_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Rollup | None:
    """One rollup across many agencies.

    Args:
        rollup_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Rollup
    """

    return sync_detailed(
        rollup_id=rollup_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    rollup_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Rollup]:
    """One rollup across many agencies.

    Args:
        rollup_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Rollup]
    """

    kwargs = _get_kwargs(
        rollup_id=rollup_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rollup_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Rollup | None:
    """One rollup across many agencies.

    Args:
        rollup_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Rollup
    """

    return (
        await asyncio_detailed(
            rollup_id=rollup_id,
            client=client,
        )
    ).parsed
