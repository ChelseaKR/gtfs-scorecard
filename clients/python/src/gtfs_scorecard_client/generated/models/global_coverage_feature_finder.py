from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="GlobalCoverageFeatureFinder")


@_attrs_define
class GlobalCoverageFeatureFinder:
    """
    Attributes:
        source_feed_record_count (int | None):
        source_row_count (int):
        reviewed_europe_feed_record_count (int):
        reviewed_europe_feature_record_count (int):
        denominator_disclosed (bool):
    """

    source_feed_record_count: int | None
    source_row_count: int
    reviewed_europe_feed_record_count: int
    reviewed_europe_feature_record_count: int
    denominator_disclosed: bool

    def to_dict(self) -> dict[str, Any]:
        source_feed_record_count: int | None
        source_feed_record_count = self.source_feed_record_count

        source_row_count = self.source_row_count

        reviewed_europe_feed_record_count = self.reviewed_europe_feed_record_count

        reviewed_europe_feature_record_count = self.reviewed_europe_feature_record_count

        denominator_disclosed = self.denominator_disclosed

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "source_feed_record_count": source_feed_record_count,
                "source_row_count": source_row_count,
                "reviewed_europe_feed_record_count": reviewed_europe_feed_record_count,
                "reviewed_europe_feature_record_count": reviewed_europe_feature_record_count,
                "denominator_disclosed": denominator_disclosed,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)

        def _parse_source_feed_record_count(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        source_feed_record_count = _parse_source_feed_record_count(
            _d.pop("source_feed_record_count")
        )

        source_row_count = _d.pop("source_row_count")

        reviewed_europe_feed_record_count = _d.pop("reviewed_europe_feed_record_count")

        reviewed_europe_feature_record_count = _d.pop(
            "reviewed_europe_feature_record_count"
        )

        denominator_disclosed = _d.pop("denominator_disclosed")

        global_coverage_feature_finder = cls(
            source_feed_record_count=source_feed_record_count,
            source_row_count=source_row_count,
            reviewed_europe_feed_record_count=reviewed_europe_feed_record_count,
            reviewed_europe_feature_record_count=reviewed_europe_feature_record_count,
            denominator_disclosed=denominator_disclosed,
        )

        return global_coverage_feature_finder
