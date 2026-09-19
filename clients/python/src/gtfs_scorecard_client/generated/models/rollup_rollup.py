from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="RollupRollup")


@_attrs_define
class RollupRollup:
    """
    Attributes:
        id (str):
        name (str):
        country_code (str | Unset): ISO 3166-1 alpha-2 identity carried by country rollups (rollups.py _rollup_identity,
            shipped with the country program pages) so renderers can state the cohort's scope without keying off id naming
            conventions. Absent on state and named-cohort rollups.
        country_name (str | Unset): Display name for country_code, resolved by the pipeline's location tables.
    """

    id: str
    name: str
    country_code: str | Unset = UNSET
    country_name: str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        country_code = self.country_code

        country_name = self.country_name

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
            }
        )
        if country_code is not UNSET:
            field_dict["country_code"] = country_code
        if country_name is not UNSET:
            field_dict["country_name"] = country_name

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        id = _d.pop("id")

        name = _d.pop("name")

        country_code = _d.pop("country_code", UNSET)

        country_name = _d.pop("country_name", UNSET)

        rollup_rollup = cls(
            id=id,
            name=name,
            country_code=country_code,
            country_name=country_name,
        )

        return rollup_rollup
