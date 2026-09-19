from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.artifact_category import ArtifactCategory


T = TypeVar("T", bound="ArtifactCategories")


@_attrs_define
class ArtifactCategories:
    """
    Attributes:
        correctness (ArtifactCategory):
        freshness (ArtifactCategory):
        completeness (ArtifactCategory):
        realtime (ArtifactCategory):
    """

    correctness: ArtifactCategory
    freshness: ArtifactCategory
    completeness: ArtifactCategory
    realtime: ArtifactCategory

    def to_dict(self) -> dict[str, Any]:
        correctness = self.correctness.to_dict()

        freshness = self.freshness.to_dict()

        completeness = self.completeness.to_dict()

        realtime = self.realtime.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "correctness": correctness,
                "freshness": freshness,
                "completeness": completeness,
                "realtime": realtime,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.artifact_category import ArtifactCategory

        _d = dict(src_dict)
        correctness = ArtifactCategory.from_dict(_d.pop("correctness"))

        freshness = ArtifactCategory.from_dict(_d.pop("freshness"))

        completeness = ArtifactCategory.from_dict(_d.pop("completeness"))

        realtime = ArtifactCategory.from_dict(_d.pop("realtime"))

        artifact_categories = cls(
            correctness=correctness,
            freshness=freshness,
            completeness=completeness,
            realtime=realtime,
        )

        return artifact_categories
