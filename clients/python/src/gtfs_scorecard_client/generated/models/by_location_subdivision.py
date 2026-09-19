from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.by_location_grade_distribution import ByLocationGradeDistribution


T = TypeVar("T", bound="ByLocationSubdivision")


@_attrs_define
class ByLocationSubdivision:
    """
    Attributes:
        count (int):
        median_score (float | None):
        grade_distribution (ByLocationGradeDistribution):
        subdivision_code (None | str):
        subdivision_name (str):
        comparison_eligible_count (int | Unset):
    """

    count: int
    median_score: float | None
    grade_distribution: ByLocationGradeDistribution
    subdivision_code: None | str
    subdivision_name: str
    comparison_eligible_count: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        median_score: float | None
        median_score = self.median_score

        grade_distribution = self.grade_distribution.to_dict()

        subdivision_code: None | str
        subdivision_code = self.subdivision_code

        subdivision_name = self.subdivision_name

        comparison_eligible_count = self.comparison_eligible_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "count": count,
                "median_score": median_score,
                "grade_distribution": grade_distribution,
                "subdivision_code": subdivision_code,
                "subdivision_name": subdivision_name,
            }
        )
        if comparison_eligible_count is not UNSET:
            field_dict["comparison_eligible_count"] = comparison_eligible_count

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.by_location_grade_distribution import (
            ByLocationGradeDistribution,
        )

        _d = dict(src_dict)
        count = _d.pop("count")

        def _parse_median_score(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        median_score = _parse_median_score(_d.pop("median_score"))

        grade_distribution = ByLocationGradeDistribution.from_dict(
            _d.pop("grade_distribution")
        )

        def _parse_subdivision_code(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        subdivision_code = _parse_subdivision_code(_d.pop("subdivision_code"))

        subdivision_name = _d.pop("subdivision_name")

        comparison_eligible_count = _d.pop("comparison_eligible_count", UNSET)

        by_location_subdivision = cls(
            count=count,
            median_score=median_score,
            grade_distribution=grade_distribution,
            subdivision_code=subdivision_code,
            subdivision_name=subdivision_name,
            comparison_eligible_count=comparison_eligible_count,
        )

        by_location_subdivision.additional_properties = _d
        return by_location_subdivision

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
