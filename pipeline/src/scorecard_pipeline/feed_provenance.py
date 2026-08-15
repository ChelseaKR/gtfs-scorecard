"""Conservative provenance labels for a configured GTFS Schedule source.

``fetch.source`` answers how this run obtained the bytes (configured URL,
Mobility Database mirror, local copy, or legacy unknown). It does not answer
who publishes the configured URL. That second question comes from the
registry's tri-state ``is_official`` evidence, with one narrower URL fact: a
recognized TransitFeeds URL is an archive even when the registry has not yet
recorded an ownership decision.

Unknown stays unknown. In particular, a successful request and a repository
host are not evidence that an agency owns or publishes a URL.
"""

from __future__ import annotations

from typing import Literal

from .config import Agency
from .tool_profiles import detect_tool

FeedSourceProvenance = Literal["official", "archive", "third_party", "unverified"]


def classify_feed_source(agency: Agency) -> FeedSourceProvenance:
    """Classify the configured URL without inferring ownership from reachability."""

    profile = detect_tool(agency.static_gtfs_url)
    if profile is not None and profile.kind == "archive":
        return "archive"
    if agency.is_official is True:
        return "official"
    if agency.is_official is False:
        return "third_party"
    return "unverified"


def confidence_source_note(provenance: FeedSourceProvenance, fetch_source: str) -> str:
    """Plain-language fetch note that keeps retrieval and ownership distinct."""

    if fetch_source == "mirror":
        configured = {
            "official": "The official feed URL on file",
            "archive": "The archived feed URL on file",
            "third_party": "The third-party feed URL on file",
            "unverified": "The configured feed URL",
        }[provenance]
        note = (
            f"{configured} was unreachable, so the Mobility Database's hosted mirror copy "
            "was scored instead."
        )
        if provenance == "unverified":
            note += " Publisher ownership of the configured URL is not verified."
        return note
    if fetch_source == "unknown":
        return (
            "This snapshot predates fetch-source recording, so where it was originally "
            "downloaded from is not known."
        )
    if fetch_source == "local":
        return (
            "A local feed copy was scored. Its recorded SHA-256 can be compared with the "
            "source or corrected copy used for this run."
        )
    if provenance == "official":
        return "The feed was downloaded from the official feed URL on file."
    if provenance == "archive":
        return "The feed was downloaded from an archived feed URL on file."
    if provenance == "third_party":
        return "The feed was downloaded from a third-party feed URL on file."
    return (
        "The feed was downloaded from the configured feed URL. Publisher ownership of that "
        "URL is not verified."
    )


def feed_source_lede(provenance: object, fetch_source: object) -> str:
    """Short page lede; malformed or legacy provenance fails closed to unverified."""

    kind = provenance if provenance in {"official", "archive", "third_party"} else "unverified"
    if fetch_source == "unknown":
        return "Based on a snapshot whose download source was not recorded"
    if fetch_source == "local":
        return "Based on a local feed copy"
    if fetch_source == "mirror":
        return {
            "official": "Based on a Mobility Database mirror copy of an official feed source",
            "archive": "Based on a Mobility Database mirror copy of an archived feed listing",
            "third_party": (
                "Based on a Mobility Database mirror copy of a third-party feed source"
            ),
            "unverified": (
                "Based on a Mobility Database mirror copy of the feed source on file; "
                "publisher ownership is not verified"
            ),
        }[kind]
    return {
        "official": "Based on the official feed source on file",
        "archive": "Based on an archived feed source on file",
        "third_party": "Based on a third-party feed source on file",
        "unverified": ("Based on the feed source on file; publisher ownership is not verified"),
    }[kind]
