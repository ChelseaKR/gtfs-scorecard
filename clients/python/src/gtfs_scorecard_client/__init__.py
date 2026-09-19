"""Typed client for the GTFS Scorecard static read API.

`make_client()` is the entry point. The endpoint functions and the models they
return are generated from the API's OpenAPI description and live under
`gtfs_scorecard_client.generated`:

    from gtfs_scorecard_client import make_client
    from gtfs_scorecard_client.generated.api.artifacts import get_agency_latest

    artifact = get_agency_latest.sync(agency_id="unitrans", client=make_client())

A value the scorecard did not measure is never a number here. An absent field
is `UNSET` and an explicit JSON null is `None`; see the README.
"""

from .generated import Client
from .generated.types import UNSET, Unset
from .guard import (
    SUPPORTED_SCHEMA_MAJOR,
    UnsupportedSchemaVersion,
    check_schema_version,
)
from .session import DEFAULT_BASE_URL, make_client

__all__ = (
    "DEFAULT_BASE_URL",
    "SUPPORTED_SCHEMA_MAJOR",
    "UNSET",
    "Client",
    "Unset",
    "UnsupportedSchemaVersion",
    "check_schema_version",
    "make_client",
)
