from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="RollupShapesReadiness")


@_attrs_define
class RollupShapesReadiness:
    """
    Attributes:
        ready (int):
        at_risk (int):
        not_ready (int):
        not_measured (int):
        total (int):
    """

    ready: int
    at_risk: int
    not_ready: int
    not_measured: int
    total: int

    def to_dict(self) -> dict[str, Any]:
        ready = self.ready

        at_risk = self.at_risk

        not_ready = self.not_ready

        not_measured = self.not_measured

        total = self.total

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "ready": ready,
                "at_risk": at_risk,
                "not_ready": not_ready,
                "not_measured": not_measured,
                "total": total,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        ready = _d.pop("ready")

        at_risk = _d.pop("at_risk")

        not_ready = _d.pop("not_ready")

        not_measured = _d.pop("not_measured")

        total = _d.pop("total")

        rollup_shapes_readiness = cls(
            ready=ready,
            at_risk=at_risk,
            not_ready=not_ready,
            not_measured=not_measured,
            total=total,
        )

        return rollup_shapes_readiness
