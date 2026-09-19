from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_changes_on_date_response_200 import GetChangesOnDateResponse200
from ...types import Response


def _get_kwargs(
    date: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/data/artifacts/changes/{date}.json".format(
            date=quote(str(date), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GetChangesOnDateResponse200 | None:
    if response.status_code == 200:
        response_200 = GetChangesOnDateResponse200.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[GetChangesOnDateResponse200]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    date: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[GetChangesOnDateResponse200]:
    """An immutable dated copy of the change list.

     Kept only when it carries the full comparison contract; pre-contract snapshots were withdrawn.

    Args:
        date (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetChangesOnDateResponse200]
    """

    kwargs = _get_kwargs(
        date=date,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    date: str,
    *,
    client: AuthenticatedClient | Client,
) -> GetChangesOnDateResponse200 | None:
    """An immutable dated copy of the change list.

     Kept only when it carries the full comparison contract; pre-contract snapshots were withdrawn.

    Args:
        date (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetChangesOnDateResponse200
    """

    return sync_detailed(
        date=date,
        client=client,
    ).parsed


async def asyncio_detailed(
    date: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[GetChangesOnDateResponse200]:
    """An immutable dated copy of the change list.

     Kept only when it carries the full comparison contract; pre-contract snapshots were withdrawn.

    Args:
        date (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetChangesOnDateResponse200]
    """

    kwargs = _get_kwargs(
        date=date,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    date: str,
    *,
    client: AuthenticatedClient | Client,
) -> GetChangesOnDateResponse200 | None:
    """An immutable dated copy of the change list.

     Kept only when it carries the full comparison contract; pre-contract snapshots were withdrawn.

    Args:
        date (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetChangesOnDateResponse200
    """

    return (
        await asyncio_detailed(
            date=date,
            client=client,
        )
    ).parsed
