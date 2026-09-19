from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ArtifactScoringProfile")


@_attrs_define
class ArtifactScoringProfile:
    """Identity and provenance of the scoring contract that produced the unchanged score fields. This is not a jurisdiction
    overlay or compliance determination.

        Attributes:
            id (str):
            rubric_version (str):
            provenance (str):
    """

    id: str
    rubric_version: str
    provenance: str

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        rubric_version = self.rubric_version

        provenance = self.provenance

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "rubric_version": rubric_version,
                "provenance": provenance,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        id = _d.pop("id")

        rubric_version = _d.pop("rubric_version")

        provenance = _d.pop("provenance")

        artifact_scoring_profile = cls(
            id=id,
            rubric_version=rubric_version,
            provenance=provenance,
        )

        return artifact_scoring_profile
