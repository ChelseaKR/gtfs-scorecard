"""The `schema_version` guard.

`docs/api.md` asks consumers to tolerate added fields and to treat a change in
the major version as a breaking change. This module is that rule, so a caller
does not have to remember it: a document whose major version is not the one
this client was generated against raises `UnsupportedSchemaVersion` instead of
being parsed into models that may no longer describe it.

Written by hand. Nothing under `generated/` is, and `make clients` never
touches this file. A test in the repository binds `SUPPORTED_SCHEMA_MAJOR` to
`x-artifact-schema-version-major` in the OpenAPI description, so the two cannot
drift apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

#: The `schema_version` major this client's models were generated against.
SUPPORTED_SCHEMA_MAJOR = "1"

_MISSING: Any = object()


class UnsupportedSchemaVersion(Exception):
    """A document carries a `schema_version` major this client was not generated for.

    Upgrade the client. Parsing the document into the old models would silently
    drop or misread whatever the new major changed.
    """

    def __init__(self, message: str, *, found: object = None) -> None:
        super().__init__(message)
        self.found = found


def _read_version(document: object) -> object:
    """The `schema_version` of a raw mapping, a generated model, or a bare version."""
    if isinstance(document, Mapping):
        return document.get("schema_version", _MISSING)
    to_dict = getattr(document, "to_dict", None)
    if callable(to_dict):
        as_mapping = to_dict()
        if isinstance(as_mapping, Mapping):
            return as_mapping.get("schema_version", _MISSING)
    return document


def schema_major(version: object) -> str:
    """`'1.19'` -> `'1'`. A version that is not a string or an integer is refused."""
    if isinstance(version, bool) or not isinstance(version, str | int):
        raise UnsupportedSchemaVersion(
            f"schema_version {version!r} is not a version string", found=version
        )
    return str(version).split(".", 1)[0]


def check_schema_version(
    document: object,
    *,
    supported_major: str = SUPPORTED_SCHEMA_MAJOR,
    require: bool = True,
) -> None:
    """Raise `UnsupportedSchemaVersion` unless the document's major matches.

    `document` is a raw JSON mapping, a generated model, or a bare version. A
    document with no `schema_version` raises unless `require` is false, because
    a client that cannot tell which contract it was given should say so.
    """
    version = _read_version(document)
    if version is _MISSING:
        if require:
            raise UnsupportedSchemaVersion("the document carries no schema_version")
        return
    found = schema_major(version)
    if found != supported_major:
        raise UnsupportedSchemaVersion(
            f"schema_version {version!r} has major version {found}; this client was "
            f"generated against major version {supported_major}. Upgrade the client.",
            found=version,
        )


def _guard_body(response: httpx.Response) -> None:
    """Check a JSON object body. Anything else has no `schema_version` to read."""
    if "json" not in response.headers.get("content-type", "").lower():
        return
    try:
        body = response.json()
    except ValueError:
        # Not this guard's job. The generated parser reports a malformed body.
        return
    # `run-status.json` is JSON `null` until a run publishes; that is not a
    # document that lost its version, so it is not checked.
    if isinstance(body, Mapping):
        check_schema_version(body, require=False)


def check_response(response: httpx.Response) -> None:
    """An httpx response hook for the synchronous client."""
    if response.is_error:
        return
    response.read()
    _guard_body(response)


async def acheck_response(response: httpx.Response) -> None:
    """An httpx response hook for the asynchronous client."""
    if response.is_error:
        return
    await response.aread()
    _guard_body(response)
