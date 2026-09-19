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
    from ..models.artifact_mode_profile_modes_item import ArtifactModeProfileModesItem


T = TypeVar("T", bound="ArtifactModeProfile")


@_attrs_define
class ArtifactModeProfile:
    """Descriptive, ungraded service modes derived from routes.txt and weighted by trips.txt.

    Attributes:
        measured (Literal[True]):
        graded (Literal[False]):
        primary_mode (None | str):
        primary_mode_label (None | str):
        modes (list[ArtifactModeProfileModesItem]):
        route_count (int):
        trip_count (int):
        is_multimodal (bool):
        has_ferry (bool):
        ferry_only (bool):
    """

    measured: Literal[True]
    graded: Literal[False]
    primary_mode: None | str
    primary_mode_label: None | str
    modes: list[ArtifactModeProfileModesItem]
    route_count: int
    trip_count: int
    is_multimodal: bool
    has_ferry: bool
    ferry_only: bool

    def to_dict(self) -> dict[str, Any]:
        measured = self.measured

        graded = self.graded

        primary_mode: None | str
        primary_mode = self.primary_mode

        primary_mode_label: None | str
        primary_mode_label = self.primary_mode_label

        modes = []
        for modes_item_data in self.modes:
            modes_item = modes_item_data.to_dict()
            modes.append(modes_item)

        route_count = self.route_count

        trip_count = self.trip_count

        is_multimodal = self.is_multimodal

        has_ferry = self.has_ferry

        ferry_only = self.ferry_only

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "measured": measured,
                "graded": graded,
                "primary_mode": primary_mode,
                "primary_mode_label": primary_mode_label,
                "modes": modes,
                "route_count": route_count,
                "trip_count": trip_count,
                "is_multimodal": is_multimodal,
                "has_ferry": has_ferry,
                "ferry_only": ferry_only,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.artifact_mode_profile_modes_item import (
            ArtifactModeProfileModesItem,
        )

        _d = dict(src_dict)
        measured = cast(Literal[True], _d.pop("measured"))
        if measured != True:
            raise ValueError(f"measured must match const True, got '{measured}'")

        graded = cast(Literal[False], _d.pop("graded"))
        if graded != False:
            raise ValueError(f"graded must match const False, got '{graded}'")

        def _parse_primary_mode(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        primary_mode = _parse_primary_mode(_d.pop("primary_mode"))

        def _parse_primary_mode_label(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        primary_mode_label = _parse_primary_mode_label(_d.pop("primary_mode_label"))

        modes = []
        _modes = _d.pop("modes")
        for modes_item_data in _modes:
            modes_item = ArtifactModeProfileModesItem.from_dict(modes_item_data)

            modes.append(modes_item)

        route_count = _d.pop("route_count")

        trip_count = _d.pop("trip_count")

        is_multimodal = _d.pop("is_multimodal")

        has_ferry = _d.pop("has_ferry")

        ferry_only = _d.pop("ferry_only")

        artifact_mode_profile = cls(
            measured=measured,
            graded=graded,
            primary_mode=primary_mode,
            primary_mode_label=primary_mode_label,
            modes=modes,
            route_count=route_count,
            trip_count=trip_count,
            is_multimodal=is_multimodal,
            has_ferry=has_ferry,
            ferry_only=ferry_only,
        )

        return artifact_mode_profile
