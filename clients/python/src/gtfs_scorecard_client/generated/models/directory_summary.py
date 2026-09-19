from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.directory_summary_comparison import DirectorySummaryComparison
    from ..models.directory_summary_countries_item import DirectorySummaryCountriesItem
    from ..models.directory_summary_expired import DirectorySummaryExpired
    from ..models.directory_summary_grade_distribution import (
        DirectorySummaryGradeDistribution,
    )
    from ..models.directory_summary_size_tiers_item import DirectorySummarySizeTiersItem
    from ..models.directory_summary_states_item import DirectorySummaryStatesItem


T = TypeVar("T", bound="DirectorySummary")


@_attrs_define
class DirectorySummary:
    """
    Attributes:
        agencies (int):
        grade_distribution (DirectorySummaryGradeDistribution):
        feed_records (int | Unset):
        scored_feed_records (int | Unset):
        comparison_eligible_count (int | Unset):
        average_score (float | None | Unset):
        median_score (float | None | Unset):
        expiring_soon (int | Unset):
        expired (DirectorySummaryExpired | Unset):
        states (list[DirectorySummaryStatesItem] | Unset):
        countries (list[DirectorySummaryCountriesItem] | Unset): Portable country rollups with nested ISO 3166-2
            subdivisions. The legacy states array is unchanged.
        size_tiers (list[DirectorySummarySizeTiersItem] | Unset):
        comparison (DirectorySummaryComparison | Unset):
    """

    agencies: int
    grade_distribution: DirectorySummaryGradeDistribution
    feed_records: int | Unset = UNSET
    scored_feed_records: int | Unset = UNSET
    comparison_eligible_count: int | Unset = UNSET
    average_score: float | None | Unset = UNSET
    median_score: float | None | Unset = UNSET
    expiring_soon: int | Unset = UNSET
    expired: DirectorySummaryExpired | Unset = UNSET
    states: list[DirectorySummaryStatesItem] | Unset = UNSET
    countries: list[DirectorySummaryCountriesItem] | Unset = UNSET
    size_tiers: list[DirectorySummarySizeTiersItem] | Unset = UNSET
    comparison: DirectorySummaryComparison | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agencies = self.agencies

        grade_distribution = self.grade_distribution.to_dict()

        feed_records = self.feed_records

        scored_feed_records = self.scored_feed_records

        comparison_eligible_count = self.comparison_eligible_count

        average_score: float | None | Unset
        if isinstance(self.average_score, Unset):
            average_score = UNSET
        else:
            average_score = self.average_score

        median_score: float | None | Unset
        if isinstance(self.median_score, Unset):
            median_score = UNSET
        else:
            median_score = self.median_score

        expiring_soon = self.expiring_soon

        expired: dict[str, Any] | Unset = UNSET
        if not isinstance(self.expired, Unset):
            expired = self.expired.to_dict()

        states: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.states, Unset):
            states = []
            for states_item_data in self.states:
                states_item = states_item_data.to_dict()
                states.append(states_item)

        countries: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.countries, Unset):
            countries = []
            for countries_item_data in self.countries:
                countries_item = countries_item_data.to_dict()
                countries.append(countries_item)

        size_tiers: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.size_tiers, Unset):
            size_tiers = []
            for size_tiers_item_data in self.size_tiers:
                size_tiers_item = size_tiers_item_data.to_dict()
                size_tiers.append(size_tiers_item)

        comparison: dict[str, Any] | Unset = UNSET
        if not isinstance(self.comparison, Unset):
            comparison = self.comparison.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agencies": agencies,
                "grade_distribution": grade_distribution,
            }
        )
        if feed_records is not UNSET:
            field_dict["feed_records"] = feed_records
        if scored_feed_records is not UNSET:
            field_dict["scored_feed_records"] = scored_feed_records
        if comparison_eligible_count is not UNSET:
            field_dict["comparison_eligible_count"] = comparison_eligible_count
        if average_score is not UNSET:
            field_dict["average_score"] = average_score
        if median_score is not UNSET:
            field_dict["median_score"] = median_score
        if expiring_soon is not UNSET:
            field_dict["expiring_soon"] = expiring_soon
        if expired is not UNSET:
            field_dict["expired"] = expired
        if states is not UNSET:
            field_dict["states"] = states
        if countries is not UNSET:
            field_dict["countries"] = countries
        if size_tiers is not UNSET:
            field_dict["size_tiers"] = size_tiers
        if comparison is not UNSET:
            field_dict["comparison"] = comparison

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.directory_summary_comparison import (
            DirectorySummaryComparison,
        )
        from ..models.directory_summary_countries_item import (
            DirectorySummaryCountriesItem,
        )
        from ..models.directory_summary_expired import (
            DirectorySummaryExpired,
        )
        from ..models.directory_summary_grade_distribution import (
            DirectorySummaryGradeDistribution,
        )
        from ..models.directory_summary_size_tiers_item import (
            DirectorySummarySizeTiersItem,
        )
        from ..models.directory_summary_states_item import (
            DirectorySummaryStatesItem,
        )

        _d = dict(src_dict)
        agencies = _d.pop("agencies")

        grade_distribution = DirectorySummaryGradeDistribution.from_dict(
            _d.pop("grade_distribution")
        )

        feed_records = _d.pop("feed_records", UNSET)

        scored_feed_records = _d.pop("scored_feed_records", UNSET)

        comparison_eligible_count = _d.pop("comparison_eligible_count", UNSET)

        def _parse_average_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        average_score = _parse_average_score(_d.pop("average_score", UNSET))

        def _parse_median_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        median_score = _parse_median_score(_d.pop("median_score", UNSET))

        expiring_soon = _d.pop("expiring_soon", UNSET)

        _expired = _d.pop("expired", UNSET)
        expired: DirectorySummaryExpired | Unset
        if isinstance(_expired, Unset):
            expired = UNSET
        else:
            expired = DirectorySummaryExpired.from_dict(_expired)

        _states = _d.pop("states", UNSET)
        states: list[DirectorySummaryStatesItem] | Unset = UNSET
        if _states is not UNSET:
            states = []
            for states_item_data in _states:
                states_item = DirectorySummaryStatesItem.from_dict(states_item_data)

                states.append(states_item)

        _countries = _d.pop("countries", UNSET)
        countries: list[DirectorySummaryCountriesItem] | Unset = UNSET
        if _countries is not UNSET:
            countries = []
            for countries_item_data in _countries:
                countries_item = DirectorySummaryCountriesItem.from_dict(
                    countries_item_data
                )

                countries.append(countries_item)

        _size_tiers = _d.pop("size_tiers", UNSET)
        size_tiers: list[DirectorySummarySizeTiersItem] | Unset = UNSET
        if _size_tiers is not UNSET:
            size_tiers = []
            for size_tiers_item_data in _size_tiers:
                size_tiers_item = DirectorySummarySizeTiersItem.from_dict(
                    size_tiers_item_data
                )

                size_tiers.append(size_tiers_item)

        _comparison = _d.pop("comparison", UNSET)
        comparison: DirectorySummaryComparison | Unset
        if isinstance(_comparison, Unset):
            comparison = UNSET
        else:
            comparison = DirectorySummaryComparison.from_dict(_comparison)

        directory_summary = cls(
            agencies=agencies,
            grade_distribution=grade_distribution,
            feed_records=feed_records,
            scored_feed_records=scored_feed_records,
            comparison_eligible_count=comparison_eligible_count,
            average_score=average_score,
            median_score=median_score,
            expiring_soon=expiring_soon,
            expired=expired,
            states=states,
            countries=countries,
            size_tiers=size_tiers,
            comparison=comparison,
        )

        directory_summary.additional_properties = _d
        return directory_summary

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
