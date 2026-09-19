from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.artifact_feed_source_provenance import ArtifactFeedSourceProvenance
from ..types import UNSET, Unset

T = TypeVar("T", bound="ArtifactFeed")


@_attrs_define
class ArtifactFeed:
    """
    Attributes:
        static_url (str):
        sha256 (str):
        size_bytes (int):
        license_note (str):
        reachable (bool):
        source_provenance (ArtifactFeedSourceProvenance | Unset): Registry-backed relationship of the configured feed
            URL to its publisher. This is independent from fetch.source, which records how this run obtained the bytes. A
            recognized TransitFeeds URL is archive; otherwise is_official true/false maps to official/third_party and
            absence stays unverified.
    """

    static_url: str
    sha256: str
    size_bytes: int
    license_note: str
    reachable: bool
    source_provenance: ArtifactFeedSourceProvenance | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        static_url = self.static_url

        sha256 = self.sha256

        size_bytes = self.size_bytes

        license_note = self.license_note

        reachable = self.reachable

        source_provenance: str | Unset = UNSET
        if not isinstance(self.source_provenance, Unset):
            source_provenance = self.source_provenance.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "static_url": static_url,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "license_note": license_note,
                "reachable": reachable,
            }
        )
        if source_provenance is not UNSET:
            field_dict["source_provenance"] = source_provenance

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        static_url = _d.pop("static_url")

        sha256 = _d.pop("sha256")

        size_bytes = _d.pop("size_bytes")

        license_note = _d.pop("license_note")

        reachable = _d.pop("reachable")

        _source_provenance = _d.pop("source_provenance", UNSET)
        source_provenance: ArtifactFeedSourceProvenance | Unset
        if isinstance(_source_provenance, Unset):
            source_provenance = UNSET
        else:
            source_provenance = ArtifactFeedSourceProvenance(_source_provenance)

        artifact_feed = cls(
            static_url=static_url,
            sha256=sha256,
            size_bytes=size_bytes,
            license_note=license_note,
            reachable=reachable,
            source_provenance=source_provenance,
        )

        return artifact_feed
