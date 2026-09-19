from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ArtifactModeProfileModesItem")


@_attrs_define
class ArtifactModeProfileModesItem:
    """
    Attributes:
        key (str):
        label (str):
        route_count (int):
        trip_count (int):
        trip_share_pct (float | None):
    """

    key: str
    label: str
    route_count: int
    trip_count: int
    trip_share_pct: float | None

    def to_dict(self) -> dict[str, Any]:
        key = self.key

        label = self.label

        route_count = self.route_count

        trip_count = self.trip_count

        trip_share_pct: float | None
        trip_share_pct = self.trip_share_pct

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "key": key,
                "label": label,
                "route_count": route_count,
                "trip_count": trip_count,
                "trip_share_pct": trip_share_pct,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        key = _d.pop("key")

        label = _d.pop("label")

        route_count = _d.pop("route_count")

        trip_count = _d.pop("trip_count")

        def _parse_trip_share_pct(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        trip_share_pct = _parse_trip_share_pct(_d.pop("trip_share_pct"))

        artifact_mode_profile_modes_item = cls(
            key=key,
            label=label,
            route_count=route_count,
            trip_count=trip_count,
            trip_share_pct=trip_share_pct,
        )

        return artifact_mode_profile_modes_item
