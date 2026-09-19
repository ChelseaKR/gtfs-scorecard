from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ArtifactFerryProfileStopAccess")


@_attrs_define
class ArtifactFerryProfileStopAccess:
    """
    Attributes:
        eligible_terminal_count (int):
        stated_count (int):
        stated_pct (float | None):
        direct_count (int):
        through_station_count (int):
    """

    eligible_terminal_count: int
    stated_count: int
    stated_pct: float | None
    direct_count: int
    through_station_count: int

    def to_dict(self) -> dict[str, Any]:
        eligible_terminal_count = self.eligible_terminal_count

        stated_count = self.stated_count

        stated_pct: float | None
        stated_pct = self.stated_pct

        direct_count = self.direct_count

        through_station_count = self.through_station_count

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "eligible_terminal_count": eligible_terminal_count,
                "stated_count": stated_count,
                "stated_pct": stated_pct,
                "direct_count": direct_count,
                "through_station_count": through_station_count,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        eligible_terminal_count = _d.pop("eligible_terminal_count")

        stated_count = _d.pop("stated_count")

        def _parse_stated_pct(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        stated_pct = _parse_stated_pct(_d.pop("stated_pct"))

        direct_count = _d.pop("direct_count")

        through_station_count = _d.pop("through_station_count")

        artifact_ferry_profile_stop_access = cls(
            eligible_terminal_count=eligible_terminal_count,
            stated_count=stated_count,
            stated_pct=stated_pct,
            direct_count=direct_count,
            through_station_count=through_station_count,
        )

        return artifact_ferry_profile_stop_access
