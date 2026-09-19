from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="DirectorySummarySizeTiersItem")


@_attrs_define
class DirectorySummarySizeTiersItem:
    """
    Attributes:
        key (str | Unset):
        label (str | Unset):
        agencies (int | Unset):
        feed_records (int | Unset):
    """

    key: str | Unset = UNSET
    label: str | Unset = UNSET
    agencies: int | Unset = UNSET
    feed_records: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        key = self.key

        label = self.label

        agencies = self.agencies

        feed_records = self.feed_records

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if key is not UNSET:
            field_dict["key"] = key
        if label is not UNSET:
            field_dict["label"] = label
        if agencies is not UNSET:
            field_dict["agencies"] = agencies
        if feed_records is not UNSET:
            field_dict["feed_records"] = feed_records

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        key = _d.pop("key", UNSET)

        label = _d.pop("label", UNSET)

        agencies = _d.pop("agencies", UNSET)

        feed_records = _d.pop("feed_records", UNSET)

        directory_summary_size_tiers_item = cls(
            key=key,
            label=label,
            agencies=agencies,
            feed_records=feed_records,
        )

        directory_summary_size_tiers_item.additional_properties = _d
        return directory_summary_size_tiers_item

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
