from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.global_coverage_country import GlobalCoverageCountry


T = TypeVar("T", bound="GlobalCoverageCohort")


@_attrs_define
class GlobalCoverageCohort:
    """
    Attributes:
        feed_record_count (int):
        country_count (int):
        feature_record_count (int):
        largest_country (GlobalCoverageCountry | None):
    """

    feed_record_count: int
    country_count: int
    feature_record_count: int
    largest_country: GlobalCoverageCountry | None

    def to_dict(self) -> dict[str, Any]:
        from ..models.global_coverage_country import (
            GlobalCoverageCountry,
        )

        feed_record_count = self.feed_record_count

        country_count = self.country_count

        feature_record_count = self.feature_record_count

        largest_country: dict[str, Any] | None
        if isinstance(self.largest_country, GlobalCoverageCountry):
            largest_country = self.largest_country.to_dict()
        else:
            largest_country = self.largest_country

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "feed_record_count": feed_record_count,
                "country_count": country_count,
                "feature_record_count": feature_record_count,
                "largest_country": largest_country,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.global_coverage_country import (
            GlobalCoverageCountry,
        )

        _d = dict(src_dict)
        feed_record_count = _d.pop("feed_record_count")

        country_count = _d.pop("country_count")

        feature_record_count = _d.pop("feature_record_count")

        def _parse_largest_country(data: object) -> GlobalCoverageCountry | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                largest_country_type_0 = GlobalCoverageCountry.from_dict(data)

                return largest_country_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GlobalCoverageCountry | None, data)

        largest_country = _parse_largest_country(_d.pop("largest_country"))

        global_coverage_cohort = cls(
            feed_record_count=feed_record_count,
            country_count=country_count,
            feature_record_count=feature_record_count,
            largest_country=largest_country,
        )

        return global_coverage_cohort
