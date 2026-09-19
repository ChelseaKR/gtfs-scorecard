from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="GlobalCoverageMethodology")


@_attrs_define
class GlobalCoverageMethodology:
    """
    Attributes:
        freshness_window_days (int):
        freshness_window_inclusive (bool):
        future_timestamps_are_fresh (bool):
        translation_measurement (str):
        empty_percentage (str):
        registry_permission_fields_not_used (list[str]):
    """

    freshness_window_days: int
    freshness_window_inclusive: bool
    future_timestamps_are_fresh: bool
    translation_measurement: str
    empty_percentage: str
    registry_permission_fields_not_used: list[str]

    def to_dict(self) -> dict[str, Any]:
        freshness_window_days = self.freshness_window_days

        freshness_window_inclusive = self.freshness_window_inclusive

        future_timestamps_are_fresh = self.future_timestamps_are_fresh

        translation_measurement = self.translation_measurement

        empty_percentage = self.empty_percentage

        registry_permission_fields_not_used = self.registry_permission_fields_not_used

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "freshness_window_days": freshness_window_days,
                "freshness_window_inclusive": freshness_window_inclusive,
                "future_timestamps_are_fresh": future_timestamps_are_fresh,
                "translation_measurement": translation_measurement,
                "empty_percentage": empty_percentage,
                "registry_permission_fields_not_used": registry_permission_fields_not_used,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        freshness_window_days = _d.pop("freshness_window_days")

        freshness_window_inclusive = _d.pop("freshness_window_inclusive")

        future_timestamps_are_fresh = _d.pop("future_timestamps_are_fresh")

        translation_measurement = _d.pop("translation_measurement")

        empty_percentage = _d.pop("empty_percentage")

        registry_permission_fields_not_used = cast(
            list[str], _d.pop("registry_permission_fields_not_used")
        )

        global_coverage_methodology = cls(
            freshness_window_days=freshness_window_days,
            freshness_window_inclusive=freshness_window_inclusive,
            future_timestamps_are_fresh=future_timestamps_are_fresh,
            translation_measurement=translation_measurement,
            empty_percentage=empty_percentage,
            registry_permission_fields_not_used=registry_permission_fields_not_used,
        )

        return global_coverage_methodology
