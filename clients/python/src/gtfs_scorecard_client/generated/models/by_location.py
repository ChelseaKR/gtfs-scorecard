from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.by_location_comparison import ByLocationComparison
    from ..models.by_location_country import ByLocationCountry


T = TypeVar("T", bound="ByLocation")


@_attrs_define
class ByLocation:
    """Additive API v1 location rollups. Count fields cover all published feed records in a location; score aggregates use
    the guarded comparison cohort and expose its denominator. Null codes collect rows whose curated location is unknown.

        Attributes:
            countries (list[ByLocationCountry]):
            comparison (ByLocationComparison | Unset):
    """

    countries: list[ByLocationCountry]
    comparison: ByLocationComparison | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        countries = []
        for countries_item_data in self.countries:
            countries_item = countries_item_data.to_dict()
            countries.append(countries_item)

        comparison: dict[str, Any] | Unset = UNSET
        if not isinstance(self.comparison, Unset):
            comparison = self.comparison.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "countries": countries,
            }
        )
        if comparison is not UNSET:
            field_dict["comparison"] = comparison

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.by_location_comparison import (
            ByLocationComparison,
        )
        from ..models.by_location_country import ByLocationCountry

        _d = dict(src_dict)
        countries = []
        _countries = _d.pop("countries")
        for countries_item_data in _countries:
            countries_item = ByLocationCountry.from_dict(countries_item_data)

            countries.append(countries_item)

        _comparison = _d.pop("comparison", UNSET)
        comparison: ByLocationComparison | Unset
        if isinstance(_comparison, Unset):
            comparison = UNSET
        else:
            comparison = ByLocationComparison.from_dict(_comparison)

        by_location = cls(
            countries=countries,
            comparison=comparison,
        )

        by_location.additional_properties = _d
        return by_location

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
