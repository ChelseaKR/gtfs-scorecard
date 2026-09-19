from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.directory_summary_countries_item_subdivisions_item_grade_distribution import (
        DirectorySummaryCountriesItemSubdivisionsItemGradeDistribution,
    )


T = TypeVar("T", bound="DirectorySummaryCountriesItemSubdivisionsItem")


@_attrs_define
class DirectorySummaryCountriesItemSubdivisionsItem:
    """
    Attributes:
        subdivision_code (None | str):
        subdivision_name (str):
        agencies (int):
        feed_records (int | Unset):
        comparison_eligible_count (int | Unset):
        average_score (float | None | Unset):
        grade_distribution (DirectorySummaryCountriesItemSubdivisionsItemGradeDistribution | Unset):
        expired (int | Unset):
    """

    subdivision_code: None | str
    subdivision_name: str
    agencies: int
    feed_records: int | Unset = UNSET
    comparison_eligible_count: int | Unset = UNSET
    average_score: float | None | Unset = UNSET
    grade_distribution: (
        DirectorySummaryCountriesItemSubdivisionsItemGradeDistribution | Unset
    ) = UNSET
    expired: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subdivision_code: None | str
        subdivision_code = self.subdivision_code

        subdivision_name = self.subdivision_name

        agencies = self.agencies

        feed_records = self.feed_records

        comparison_eligible_count = self.comparison_eligible_count

        average_score: float | None | Unset
        if isinstance(self.average_score, Unset):
            average_score = UNSET
        else:
            average_score = self.average_score

        grade_distribution: dict[str, Any] | Unset = UNSET
        if not isinstance(self.grade_distribution, Unset):
            grade_distribution = self.grade_distribution.to_dict()

        expired = self.expired

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "subdivision_code": subdivision_code,
                "subdivision_name": subdivision_name,
                "agencies": agencies,
            }
        )
        if feed_records is not UNSET:
            field_dict["feed_records"] = feed_records
        if comparison_eligible_count is not UNSET:
            field_dict["comparison_eligible_count"] = comparison_eligible_count
        if average_score is not UNSET:
            field_dict["average_score"] = average_score
        if grade_distribution is not UNSET:
            field_dict["grade_distribution"] = grade_distribution
        if expired is not UNSET:
            field_dict["expired"] = expired

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.directory_summary_countries_item_subdivisions_item_grade_distribution import (
            DirectorySummaryCountriesItemSubdivisionsItemGradeDistribution,
        )

        _d = dict(src_dict)

        def _parse_subdivision_code(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        subdivision_code = _parse_subdivision_code(_d.pop("subdivision_code"))

        subdivision_name = _d.pop("subdivision_name")

        agencies = _d.pop("agencies")

        feed_records = _d.pop("feed_records", UNSET)

        comparison_eligible_count = _d.pop("comparison_eligible_count", UNSET)

        def _parse_average_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        average_score = _parse_average_score(_d.pop("average_score", UNSET))

        _grade_distribution = _d.pop("grade_distribution", UNSET)
        grade_distribution: (
            DirectorySummaryCountriesItemSubdivisionsItemGradeDistribution | Unset
        )
        if isinstance(_grade_distribution, Unset):
            grade_distribution = UNSET
        else:
            grade_distribution = DirectorySummaryCountriesItemSubdivisionsItemGradeDistribution.from_dict(
                _grade_distribution
            )

        expired = _d.pop("expired", UNSET)

        directory_summary_countries_item_subdivisions_item = cls(
            subdivision_code=subdivision_code,
            subdivision_name=subdivision_name,
            agencies=agencies,
            feed_records=feed_records,
            comparison_eligible_count=comparison_eligible_count,
            average_score=average_score,
            grade_distribution=grade_distribution,
            expired=expired,
        )

        directory_summary_countries_item_subdivisions_item.additional_properties = _d
        return directory_summary_countries_item_subdivisions_item

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
