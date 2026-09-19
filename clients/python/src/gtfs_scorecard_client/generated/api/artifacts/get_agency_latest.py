from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.artifact import Artifact
from ...types import Response


def _get_kwargs(
    agency_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/data/artifacts/{agency_id}/latest.json".format(
            agency_id=quote(str(agency_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | Artifact | None:
    if response.status_code == 200:
        response_200 = Artifact.from_dict(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | Artifact]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    agency_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | Artifact]:
    """The most recent full scorecard for one feed record.

    Args:
        agency_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Artifact]
    """

    kwargs = _get_kwargs(
        agency_id=agency_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    agency_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | Artifact | None:
    """The most recent full scorecard for one feed record.

    Args:
        agency_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Artifact
    """

    return sync_detailed(
        agency_id=agency_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    agency_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | Artifact]:
    """The most recent full scorecard for one feed record.

    Args:
        agency_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Artifact]
    """

    kwargs = _get_kwargs(
        agency_id=agency_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    agency_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | Artifact | None:
    """The most recent full scorecard for one feed record.

    Args:
        agency_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Artifact
    """

    return (
        await asyncio_detailed(
            agency_id=agency_id,
            client=client,
        )
    ).parsed
