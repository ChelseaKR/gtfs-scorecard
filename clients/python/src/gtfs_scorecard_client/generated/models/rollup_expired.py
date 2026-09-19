from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="RollupExpired")


@_attrs_define
class RollupExpired:
    """
    Attributes:
        lapsed (int):
        stale (int):
        total (int):
    """

    lapsed: int
    stale: int
    total: int

    def to_dict(self) -> dict[str, Any]:
        lapsed = self.lapsed

        stale = self.stale

        total = self.total

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "lapsed": lapsed,
                "stale": stale,
                "total": total,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        lapsed = _d.pop("lapsed")

        stale = _d.pop("stale")

        total = _d.pop("total")

        rollup_expired = cls(
            lapsed=lapsed,
            stale=stale,
            total=total,
        )

        return rollup_expired
