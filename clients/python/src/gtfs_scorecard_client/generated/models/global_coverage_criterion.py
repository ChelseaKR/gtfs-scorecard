from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.global_coverage_criterion_key import GlobalCoverageCriterionKey
from ..models.global_coverage_criterion_operator import GlobalCoverageCriterionOperator
from ..models.global_coverage_criterion_unit import GlobalCoverageCriterionUnit
from ..types import UNSET, Unset

T = TypeVar("T", bound="GlobalCoverageCriterion")


@_attrs_define
class GlobalCoverageCriterion:
    """
    Attributes:
        key (GlobalCoverageCriterionKey):
        label (str):
        actual (bool | float | None):
        threshold (bool | float):
        operator (GlobalCoverageCriterionOperator):
        unit (GlobalCoverageCriterionUnit):
        met (bool):
        numerator (int | Unset):
        denominator (int | Unset):
    """

    key: GlobalCoverageCriterionKey
    label: str
    actual: bool | float | None
    threshold: bool | float
    operator: GlobalCoverageCriterionOperator
    unit: GlobalCoverageCriterionUnit
    met: bool
    numerator: int | Unset = UNSET
    denominator: int | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        key = self.key.value

        label = self.label

        actual: bool | float | None
        actual = self.actual

        threshold: bool | float
        threshold = self.threshold

        operator = self.operator.value

        unit = self.unit.value

        met = self.met

        numerator = self.numerator

        denominator = self.denominator

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "key": key,
                "label": label,
                "actual": actual,
                "threshold": threshold,
                "operator": operator,
                "unit": unit,
                "met": met,
            }
        )
        if numerator is not UNSET:
            field_dict["numerator"] = numerator
        if denominator is not UNSET:
            field_dict["denominator"] = denominator

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        key = GlobalCoverageCriterionKey(_d.pop("key"))

        label = _d.pop("label")

        def _parse_actual(data: object) -> bool | float | None:
            if data is None:
                return data
            return cast(bool | float | None, data)

        actual = _parse_actual(_d.pop("actual"))

        def _parse_threshold(data: object) -> bool | float:
            return cast(bool | float, data)

        threshold = _parse_threshold(_d.pop("threshold"))

        operator = GlobalCoverageCriterionOperator(_d.pop("operator"))

        unit = GlobalCoverageCriterionUnit(_d.pop("unit"))

        met = _d.pop("met")

        numerator = _d.pop("numerator", UNSET)

        denominator = _d.pop("denominator", UNSET)

        global_coverage_criterion = cls(
            key=key,
            label=label,
            actual=actual,
            threshold=threshold,
            operator=operator,
            unit=unit,
            met=met,
            numerator=numerator,
            denominator=denominator,
        )

        return global_coverage_criterion
