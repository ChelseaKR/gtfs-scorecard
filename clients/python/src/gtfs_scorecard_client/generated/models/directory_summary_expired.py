from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="DirectorySummaryExpired")


@_attrs_define
class DirectorySummaryExpired:
    """
    Attributes:
        lapsed (int | Unset):
        stale (int | Unset):
        total (int | Unset):
    """

    lapsed: int | Unset = UNSET
    stale: int | Unset = UNSET
    total: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        lapsed = self.lapsed

        stale = self.stale

        total = self.total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if lapsed is not UNSET:
            field_dict["lapsed"] = lapsed
        if stale is not UNSET:
            field_dict["stale"] = stale
        if total is not UNSET:
            field_dict["total"] = total

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        lapsed = _d.pop("lapsed", UNSET)

        stale = _d.pop("stale", UNSET)

        total = _d.pop("total", UNSET)

        directory_summary_expired = cls(
            lapsed=lapsed,
            stale=stale,
            total=total,
        )

        directory_summary_expired.additional_properties = _d
        return directory_summary_expired

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
