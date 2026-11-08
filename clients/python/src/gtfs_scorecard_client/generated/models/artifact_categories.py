from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.artifact_category import ArtifactCategory
    from ..models.artifact_held_mirror_freshness import ArtifactHeldMirrorFreshness


T = TypeVar("T", bound="ArtifactCategories")


@_attrs_define
class ArtifactCategories:
    """
    Attributes:
        correctness (ArtifactCategory):
        freshness (ArtifactCategory | ArtifactHeldMirrorFreshness):
        completeness (ArtifactCategory):
        realtime (ArtifactCategory):
    """

    correctness: ArtifactCategory
    freshness: ArtifactCategory | ArtifactHeldMirrorFreshness
    completeness: ArtifactCategory
    realtime: ArtifactCategory

    def to_dict(self) -> dict[str, Any]:
        from ..models.artifact_held_mirror_freshness import ArtifactHeldMirrorFreshness

        correctness = self.correctness.to_dict()

        freshness: dict[str, Any]
        if isinstance(self.freshness, ArtifactHeldMirrorFreshness):
            freshness = self.freshness.to_dict()
        else:
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
        from ..models.artifact_held_mirror_freshness import (
            ArtifactHeldMirrorFreshness,
        )

        _d = dict(src_dict)
        correctness = ArtifactCategory.from_dict(_d.pop("correctness"))

        def _parse_freshness(
            data: object,
        ) -> ArtifactCategory | ArtifactHeldMirrorFreshness:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                freshness_type_0 = ArtifactHeldMirrorFreshness.from_dict(data)

                return freshness_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            freshness_type_1 = ArtifactCategory.from_dict(data)

            return freshness_type_1

        freshness = _parse_freshness(_d.pop("freshness"))

        completeness = ArtifactCategory.from_dict(_d.pop("completeness"))

        realtime = ArtifactCategory.from_dict(_d.pop("realtime"))

        artifact_categories = cls(
            correctness=correctness,
            freshness=freshness,
            completeness=completeness,
            realtime=realtime,
        )

        return artifact_categories
