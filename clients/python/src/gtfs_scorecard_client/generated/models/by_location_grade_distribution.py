from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ByLocationGradeDistribution")


@_attrs_define
class ByLocationGradeDistribution:
    """
    Attributes:
        a (int):
        b (int):
        c (int):
        d (int):
        f (int):
    """

    a: int
    b: int
    c: int
    d: int
    f: int

    def to_dict(self) -> dict[str, Any]:
        a = self.a

        b = self.b

        c = self.c

        d = self.d

        f = self.f

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "A": a,
                "B": b,
                "C": c,
                "D": d,
                "F": f,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        a = _d.pop("A")

        b = _d.pop("B")

        c = _d.pop("C")

        d = _d.pop("D")

        f = _d.pop("F")

        by_location_grade_distribution = cls(
            a=a,
            b=b,
            c=c,
            d=d,
            f=f,
        )

        return by_location_grade_distribution
