from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ArtifactFerryProfileTerminalHierarchy")


@_attrs_define
class ArtifactFerryProfileTerminalHierarchy:
    """
    Attributes:
        boarding_location_count (int):
        parented_boarding_location_count (int):
        parented_boarding_location_pct (float | None):
        referenced_station_count (int):
    """

    boarding_location_count: int
    parented_boarding_location_count: int
    parented_boarding_location_pct: float | None
    referenced_station_count: int

    def to_dict(self) -> dict[str, Any]:
        boarding_location_count = self.boarding_location_count

        parented_boarding_location_count = self.parented_boarding_location_count

        parented_boarding_location_pct: float | None
        parented_boarding_location_pct = self.parented_boarding_location_pct

        referenced_station_count = self.referenced_station_count

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "boarding_location_count": boarding_location_count,
                "parented_boarding_location_count": parented_boarding_location_count,
                "parented_boarding_location_pct": parented_boarding_location_pct,
                "referenced_station_count": referenced_station_count,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        boarding_location_count = _d.pop("boarding_location_count")

        parented_boarding_location_count = _d.pop("parented_boarding_location_count")

        def _parse_parented_boarding_location_pct(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        parented_boarding_location_pct = _parse_parented_boarding_location_pct(
            _d.pop("parented_boarding_location_pct")
        )

        referenced_station_count = _d.pop("referenced_station_count")

        artifact_ferry_profile_terminal_hierarchy = cls(
            boarding_location_count=boarding_location_count,
            parented_boarding_location_count=parented_boarding_location_count,
            parented_boarding_location_pct=parented_boarding_location_pct,
            referenced_station_count=referenced_station_count,
        )

        return artifact_ferry_profile_terminal_hierarchy
