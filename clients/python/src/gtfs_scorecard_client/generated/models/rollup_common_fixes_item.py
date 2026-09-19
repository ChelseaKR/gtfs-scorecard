from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="RollupCommonFixesItem")


@_attrs_define
class RollupCommonFixesItem:
    """
    Attributes:
        code (str):
        fix (str):
        agencies (int):
    """

    code: str
    fix: str
    agencies: int

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        fix = self.fix

        agencies = self.agencies

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "code": code,
                "fix": fix,
                "agencies": agencies,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        code = _d.pop("code")

        fix = _d.pop("fix")

        agencies = _d.pop("agencies")

        rollup_common_fixes_item = cls(
            code=code,
            fix=fix,
            agencies=agencies,
        )

        return rollup_common_fixes_item
