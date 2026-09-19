from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.rollup_index_rollups_item import RollupIndexRollupsItem


T = TypeVar("T", bound="RollupIndex")


@_attrs_define
class RollupIndex:
    """The list of published program rollups with one summary row each, written beside the per-rollup documents as
    rollups/index.json.

        Attributes:
            schema_version (str):
            rollups (list[RollupIndexRollupsItem]):
    """

    schema_version: str
    rollups: list[RollupIndexRollupsItem]

    def to_dict(self) -> dict[str, Any]:
        schema_version = self.schema_version

        rollups = []
        for rollups_item_data in self.rollups:
            rollups_item = rollups_item_data.to_dict()
            rollups.append(rollups_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "schema_version": schema_version,
                "rollups": rollups,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.rollup_index_rollups_item import (
            RollupIndexRollupsItem,
        )

        _d = dict(src_dict)
        schema_version = _d.pop("schema_version")

        rollups = []
        _rollups = _d.pop("rollups")
        for rollups_item_data in _rollups:
            rollups_item = RollupIndexRollupsItem.from_dict(rollups_item_data)

            rollups.append(rollups_item)

        rollup_index = cls(
            schema_version=schema_version,
            rollups=rollups,
        )

        return rollup_index
