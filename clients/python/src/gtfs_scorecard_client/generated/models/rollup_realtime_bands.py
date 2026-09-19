from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="RollupRealtimeBands")


@_attrs_define
class RollupRealtimeBands:
    """
    Attributes:
        reliable (int):
        mostly (int):
        spotty (int):
    """

    reliable: int
    mostly: int
    spotty: int

    def to_dict(self) -> dict[str, Any]:
        reliable = self.reliable

        mostly = self.mostly

        spotty = self.spotty

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "reliable": reliable,
                "mostly": mostly,
                "spotty": spotty,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        reliable = _d.pop("reliable")

        mostly = _d.pop("mostly")

        spotty = _d.pop("spotty")

        rollup_realtime_bands = cls(
            reliable=reliable,
            mostly=mostly,
            spotty=spotty,
        )

        return rollup_realtime_bands
