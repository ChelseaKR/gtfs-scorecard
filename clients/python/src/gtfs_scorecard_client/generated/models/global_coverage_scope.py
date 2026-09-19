from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.global_coverage_europe_country_code import GlobalCoverageEuropeCountryCode

T = TypeVar("T", bound="GlobalCoverageScope")


@_attrs_define
class GlobalCoverageScope:
    """
    Attributes:
        name (str):
        country_codes (list[GlobalCoverageEuropeCountryCode]):
        unit (Literal['feed_records']):
        selection (str):
    """

    name: str
    country_codes: list[GlobalCoverageEuropeCountryCode]
    unit: Literal["feed_records"]
    selection: str

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        country_codes = []
        for country_codes_item_data in self.country_codes:
            country_codes_item = country_codes_item_data.value
            country_codes.append(country_codes_item)

        unit = self.unit

        selection = self.selection

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "country_codes": country_codes,
                "unit": unit,
                "selection": selection,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        name = _d.pop("name")

        country_codes = []
        _country_codes = _d.pop("country_codes")
        for country_codes_item_data in _country_codes:
            country_codes_item = GlobalCoverageEuropeCountryCode(
                country_codes_item_data
            )

            country_codes.append(country_codes_item)

        unit = cast(Literal["feed_records"], _d.pop("unit"))
        if unit != "feed_records":
            raise ValueError(f"unit must match const 'feed_records', got '{unit}'")

        selection = _d.pop("selection")

        global_coverage_scope = cls(
            name=name,
            country_codes=country_codes,
            unit=unit,
            selection=selection,
        )

        return global_coverage_scope
