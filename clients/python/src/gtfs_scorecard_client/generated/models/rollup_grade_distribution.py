from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="RollupGradeDistribution")


@_attrs_define
class RollupGradeDistribution:
    """
    Attributes:
        a (int | Unset):
        b (int | Unset):
        c (int | Unset):
        d (int | Unset):
        f (int | Unset):
    """

    a: int | Unset = UNSET
    b: int | Unset = UNSET
    c: int | Unset = UNSET
    d: int | Unset = UNSET
    f: int | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        a = self.a

        b = self.b

        c = self.c

        d = self.d

        f = self.f

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if a is not UNSET:
            field_dict["A"] = a
        if b is not UNSET:
            field_dict["B"] = b
        if c is not UNSET:
            field_dict["C"] = c
        if d is not UNSET:
            field_dict["D"] = d
        if f is not UNSET:
            field_dict["F"] = f

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        a = _d.pop("A", UNSET)

        b = _d.pop("B", UNSET)

        c = _d.pop("C", UNSET)

        d = _d.pop("D", UNSET)

        f = _d.pop("F", UNSET)

        rollup_grade_distribution = cls(
            a=a,
            b=b,
            c=c,
            d=d,
            f=f,
        )

        return rollup_grade_distribution
