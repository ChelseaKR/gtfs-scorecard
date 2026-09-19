from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="RollupIndexRollupsItem")


@_attrs_define
class RollupIndexRollupsItem:
    """
    Attributes:
        id (str):
        name (str):
        agency_count (int):
        average_score (float | None):
        needs_attention (int):
        expired (int):
        comparison_eligible (int | Unset):
    """

    id: str
    name: str
    agency_count: int
    average_score: float | None
    needs_attention: int
    expired: int
    comparison_eligible: int | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        agency_count = self.agency_count

        average_score: float | None
        average_score = self.average_score

        needs_attention = self.needs_attention

        expired = self.expired

        comparison_eligible = self.comparison_eligible

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
                "agency_count": agency_count,
                "average_score": average_score,
                "needs_attention": needs_attention,
                "expired": expired,
            }
        )
        if comparison_eligible is not UNSET:
            field_dict["comparison_eligible"] = comparison_eligible

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        id = _d.pop("id")

        name = _d.pop("name")

        agency_count = _d.pop("agency_count")

        def _parse_average_score(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        average_score = _parse_average_score(_d.pop("average_score"))

        needs_attention = _d.pop("needs_attention")

        expired = _d.pop("expired")

        comparison_eligible = _d.pop("comparison_eligible", UNSET)

        rollup_index_rollups_item = cls(
            id=id,
            name=name,
            agency_count=agency_count,
            average_score=average_score,
            needs_attention=needs_attention,
            expired=expired,
            comparison_eligible=comparison_eligible,
        )

        return rollup_index_rollups_item
