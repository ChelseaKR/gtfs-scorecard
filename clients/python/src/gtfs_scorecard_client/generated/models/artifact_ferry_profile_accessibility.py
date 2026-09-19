from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.artifact_enum_coverage import ArtifactEnumCoverage


T = TypeVar("T", bound="ArtifactFerryProfileAccessibility")


@_attrs_define
class ArtifactFerryProfileAccessibility:
    """
    Attributes:
        terminals (ArtifactEnumCoverage):
        trips (ArtifactEnumCoverage):
        measures (Literal['published_values_not_physical_usability']):
    """

    terminals: ArtifactEnumCoverage
    trips: ArtifactEnumCoverage
    measures: Literal["published_values_not_physical_usability"]

    def to_dict(self) -> dict[str, Any]:
        terminals = self.terminals.to_dict()

        trips = self.trips.to_dict()

        measures = self.measures

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "terminals": terminals,
                "trips": trips,
                "measures": measures,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.artifact_enum_coverage import (
            ArtifactEnumCoverage,
        )

        _d = dict(src_dict)
        terminals = ArtifactEnumCoverage.from_dict(_d.pop("terminals"))

        trips = ArtifactEnumCoverage.from_dict(_d.pop("trips"))

        measures = cast(
            Literal["published_values_not_physical_usability"], _d.pop("measures")
        )
        if measures != "published_values_not_physical_usability":
            raise ValueError(
                f"measures must match const 'published_values_not_physical_usability', got '{measures}'"
            )

        artifact_ferry_profile_accessibility = cls(
            terminals=terminals,
            trips=trips,
            measures=measures,
        )

        return artifact_ferry_profile_accessibility
