from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.catalog_agency import CatalogAgency


T = TypeVar("T", bound="Catalog")


@_attrs_define
class Catalog:
    """Flat list of every published feed scorecard. Additive within a major schema_version: tolerate unknown fields.

    Attributes:
        schema_version (str):
        agencies (list[CatalogAgency]):
        source (str | Unset):
        rubric_version (str | Unset): The sole rubric version present in agencies, or mixed when rows span versions;
            unknown when no row records one.
        rubric_versions (list[str] | Unset): Sorted rubric-version values present in row provenance; unknown represents
            a row without a version.
        license_ (str | Unset):
        attribution (str | Unset):
    """

    schema_version: str
    agencies: list[CatalogAgency]
    source: str | Unset = UNSET
    rubric_version: str | Unset = UNSET
    rubric_versions: list[str] | Unset = UNSET
    license_: str | Unset = UNSET
    attribution: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        schema_version = self.schema_version

        agencies = []
        for agencies_item_data in self.agencies:
            agencies_item = agencies_item_data.to_dict()
            agencies.append(agencies_item)

        source = self.source

        rubric_version = self.rubric_version

        rubric_versions: list[str] | Unset = UNSET
        if not isinstance(self.rubric_versions, Unset):
            rubric_versions = self.rubric_versions

        license_ = self.license_

        attribution = self.attribution

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "schema_version": schema_version,
                "agencies": agencies,
            }
        )
        if source is not UNSET:
            field_dict["source"] = source
        if rubric_version is not UNSET:
            field_dict["rubric_version"] = rubric_version
        if rubric_versions is not UNSET:
            field_dict["rubric_versions"] = rubric_versions
        if license_ is not UNSET:
            field_dict["license"] = license_
        if attribution is not UNSET:
            field_dict["attribution"] = attribution

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.catalog_agency import CatalogAgency

        _d = dict(src_dict)
        schema_version = _d.pop("schema_version")

        agencies = []
        _agencies = _d.pop("agencies")
        for agencies_item_data in _agencies:
            agencies_item = CatalogAgency.from_dict(agencies_item_data)

            agencies.append(agencies_item)

        source = _d.pop("source", UNSET)

        rubric_version = _d.pop("rubric_version", UNSET)

        rubric_versions = cast(list[str], _d.pop("rubric_versions", UNSET))

        license_ = _d.pop("license", UNSET)

        attribution = _d.pop("attribution", UNSET)

        catalog = cls(
            schema_version=schema_version,
            agencies=agencies,
            source=source,
            rubric_version=rubric_version,
            rubric_versions=rubric_versions,
            license_=license_,
            attribution=attribution,
        )

        catalog.additional_properties = _d
        return catalog

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
