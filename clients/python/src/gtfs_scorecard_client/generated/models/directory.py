from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.directory_agencies_item import DirectoryAgenciesItem
    from ..models.directory_summary import DirectorySummary


T = TypeVar("T", bound="Directory")


@_attrs_define
class Directory:
    """Slim per-scorecard directory plus guarded covered-corpus and location summaries. Additive within a major
    schema_version: tolerate unknown fields.

        Attributes:
            schema_version (str):
            summary (DirectorySummary):
            agencies (list[DirectoryAgenciesItem]):
            license_ (str | Unset):
            attribution (str | Unset):
            generated_at (str | Unset):
    """

    schema_version: str
    summary: DirectorySummary
    agencies: list[DirectoryAgenciesItem]
    license_: str | Unset = UNSET
    attribution: str | Unset = UNSET
    generated_at: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        schema_version = self.schema_version

        summary = self.summary.to_dict()

        agencies = []
        for agencies_item_data in self.agencies:
            agencies_item = agencies_item_data.to_dict()
            agencies.append(agencies_item)

        license_ = self.license_

        attribution = self.attribution

        generated_at = self.generated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "schema_version": schema_version,
                "summary": summary,
                "agencies": agencies,
            }
        )
        if license_ is not UNSET:
            field_dict["license"] = license_
        if attribution is not UNSET:
            field_dict["attribution"] = attribution
        if generated_at is not UNSET:
            field_dict["generated_at"] = generated_at

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.directory_agencies_item import (
            DirectoryAgenciesItem,
        )
        from ..models.directory_summary import DirectorySummary

        _d = dict(src_dict)
        schema_version = _d.pop("schema_version")

        summary = DirectorySummary.from_dict(_d.pop("summary"))

        agencies = []
        _agencies = _d.pop("agencies")
        for agencies_item_data in _agencies:
            agencies_item = DirectoryAgenciesItem.from_dict(agencies_item_data)

            agencies.append(agencies_item)

        license_ = _d.pop("license", UNSET)

        attribution = _d.pop("attribution", UNSET)

        generated_at = _d.pop("generated_at", UNSET)

        directory = cls(
            schema_version=schema_version,
            summary=summary,
            agencies=agencies,
            license_=license_,
            attribution=attribution,
            generated_at=generated_at,
        )

        directory.additional_properties = _d
        return directory

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
