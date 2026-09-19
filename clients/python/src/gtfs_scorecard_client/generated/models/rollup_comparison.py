from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.rollup_comparison_required_measured_categories_item import (
    RollupComparisonRequiredMeasuredCategoriesItem,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.rollup_comparison_exclusion_counts import (
        RollupComparisonExclusionCounts,
    )
    from ..models.rollup_comparison_measured_category_cohorts import (
        RollupComparisonMeasuredCategoryCohorts,
    )


T = TypeVar("T", bound="RollupComparison")


@_attrs_define
class RollupComparison:
    """
    Attributes:
        eligible_count (int):
        excluded_count (int):
        required_rubric_version (str):
        required_scoring_profile_id (str):
        required_validator_version (str):
        required_measured_categories (list[RollupComparisonRequiredMeasuredCategoriesItem]):
        measured_category_cohorts (RollupComparisonMeasuredCategoryCohorts):
        exclusion_counts (RollupComparisonExclusionCounts):
        absolute_rankings_published (Literal[False]):
        individual_percentiles_published (Literal[False]):
        note (str):
        required_reader_archive_profile (str | Unset):
    """

    eligible_count: int
    excluded_count: int
    required_rubric_version: str
    required_scoring_profile_id: str
    required_validator_version: str
    required_measured_categories: list[RollupComparisonRequiredMeasuredCategoriesItem]
    measured_category_cohorts: RollupComparisonMeasuredCategoryCohorts
    exclusion_counts: RollupComparisonExclusionCounts
    absolute_rankings_published: Literal[False]
    individual_percentiles_published: Literal[False]
    note: str
    required_reader_archive_profile: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eligible_count = self.eligible_count

        excluded_count = self.excluded_count

        required_rubric_version = self.required_rubric_version

        required_scoring_profile_id = self.required_scoring_profile_id

        required_validator_version = self.required_validator_version

        required_measured_categories = []
        for required_measured_categories_item_data in self.required_measured_categories:
            required_measured_categories_item = (
                required_measured_categories_item_data.value
            )
            required_measured_categories.append(required_measured_categories_item)

        measured_category_cohorts = self.measured_category_cohorts.to_dict()

        exclusion_counts = self.exclusion_counts.to_dict()

        absolute_rankings_published = self.absolute_rankings_published

        individual_percentiles_published = self.individual_percentiles_published

        note = self.note

        required_reader_archive_profile = self.required_reader_archive_profile

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "eligible_count": eligible_count,
                "excluded_count": excluded_count,
                "required_rubric_version": required_rubric_version,
                "required_scoring_profile_id": required_scoring_profile_id,
                "required_validator_version": required_validator_version,
                "required_measured_categories": required_measured_categories,
                "measured_category_cohorts": measured_category_cohorts,
                "exclusion_counts": exclusion_counts,
                "absolute_rankings_published": absolute_rankings_published,
                "individual_percentiles_published": individual_percentiles_published,
                "note": note,
            }
        )
        if required_reader_archive_profile is not UNSET:
            field_dict["required_reader_archive_profile"] = (
                required_reader_archive_profile
            )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.rollup_comparison_exclusion_counts import (
            RollupComparisonExclusionCounts,
        )
        from ..models.rollup_comparison_measured_category_cohorts import (
            RollupComparisonMeasuredCategoryCohorts,
        )

        _d = dict(src_dict)
        eligible_count = _d.pop("eligible_count")

        excluded_count = _d.pop("excluded_count")

        required_rubric_version = _d.pop("required_rubric_version")

        required_scoring_profile_id = _d.pop("required_scoring_profile_id")

        required_validator_version = _d.pop("required_validator_version")

        required_measured_categories = []
        _required_measured_categories = _d.pop("required_measured_categories")
        for required_measured_categories_item_data in _required_measured_categories:
            required_measured_categories_item = (
                RollupComparisonRequiredMeasuredCategoriesItem(
                    required_measured_categories_item_data
                )
            )

            required_measured_categories.append(required_measured_categories_item)

        measured_category_cohorts = RollupComparisonMeasuredCategoryCohorts.from_dict(
            _d.pop("measured_category_cohorts")
        )

        exclusion_counts = RollupComparisonExclusionCounts.from_dict(
            _d.pop("exclusion_counts")
        )

        absolute_rankings_published = cast(
            Literal[False], _d.pop("absolute_rankings_published")
        )
        if absolute_rankings_published != False:
            raise ValueError(
                f"absolute_rankings_published must match const False, got '{absolute_rankings_published}'"
            )

        individual_percentiles_published = cast(
            Literal[False], _d.pop("individual_percentiles_published")
        )
        if individual_percentiles_published != False:
            raise ValueError(
                f"individual_percentiles_published must match const False, got '{individual_percentiles_published}'"
            )

        note = _d.pop("note")

        required_reader_archive_profile = _d.pop(
            "required_reader_archive_profile", UNSET
        )

        rollup_comparison = cls(
            eligible_count=eligible_count,
            excluded_count=excluded_count,
            required_rubric_version=required_rubric_version,
            required_scoring_profile_id=required_scoring_profile_id,
            required_validator_version=required_validator_version,
            required_measured_categories=required_measured_categories,
            measured_category_cohorts=measured_category_cohorts,
            exclusion_counts=exclusion_counts,
            absolute_rankings_published=absolute_rankings_published,
            individual_percentiles_published=individual_percentiles_published,
            note=note,
            required_reader_archive_profile=required_reader_archive_profile,
        )

        rollup_comparison.additional_properties = _d
        return rollup_comparison

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
