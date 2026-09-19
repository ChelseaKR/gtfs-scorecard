from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...types import Response


def _get_kwargs(
    rollup_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/data/artifacts/rollups/{rollup_id}.csv".format(
            rollup_id=quote(str(rollup_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> str | None:
    if response.status_code == 200:
        response_200 = response.text
        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[str]:
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
) -> Response[str]:
    """The same rollup's members as a spreadsheet.

    Args:
        rollup_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[str]
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
) -> str | None:
    """The same rollup's members as a spreadsheet.

    Args:
        rollup_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        str
    """

    return sync_detailed(
        rollup_id=rollup_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    rollup_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[str]:
    """The same rollup's members as a spreadsheet.

    Args:
        rollup_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[str]
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
) -> str | None:
    """The same rollup's members as a spreadsheet.

    Args:
        rollup_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        str
    """

    return (
        await asyncio_detailed(
            rollup_id=rollup_id,
            client=client,
        )
    ).parsed
