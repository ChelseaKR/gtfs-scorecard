from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ArtifactEnumCoverage")


@_attrs_define
class ArtifactEnumCoverage:
    """
    Attributes:
        total_count (int):
        stated_count (int):
        stated_pct (float | None):
        allowed_count (int):
        allowed_pct (float | None):
        not_allowed_count (int):
        not_allowed_pct (float | None):
    """

    total_count: int
    stated_count: int
    stated_pct: float | None
    allowed_count: int
    allowed_pct: float | None
    not_allowed_count: int
    not_allowed_pct: float | None

    def to_dict(self) -> dict[str, Any]:
        total_count = self.total_count

        stated_count = self.stated_count

        stated_pct: float | None
        stated_pct = self.stated_pct

        allowed_count = self.allowed_count

        allowed_pct: float | None
        allowed_pct = self.allowed_pct

        not_allowed_count = self.not_allowed_count

        not_allowed_pct: float | None
        not_allowed_pct = self.not_allowed_pct

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "total_count": total_count,
                "stated_count": stated_count,
                "stated_pct": stated_pct,
                "allowed_count": allowed_count,
                "allowed_pct": allowed_pct,
                "not_allowed_count": not_allowed_count,
                "not_allowed_pct": not_allowed_pct,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        total_count = _d.pop("total_count")

        stated_count = _d.pop("stated_count")

        def _parse_stated_pct(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        stated_pct = _parse_stated_pct(_d.pop("stated_pct"))

        allowed_count = _d.pop("allowed_count")

        def _parse_allowed_pct(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        allowed_pct = _parse_allowed_pct(_d.pop("allowed_pct"))

        not_allowed_count = _d.pop("not_allowed_count")

        def _parse_not_allowed_pct(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        not_allowed_pct = _parse_not_allowed_pct(_d.pop("not_allowed_pct"))

        artifact_enum_coverage = cls(
            total_count=total_count,
            stated_count=stated_count,
            stated_pct=stated_pct,
            allowed_count=allowed_count,
            allowed_pct=allowed_pct,
            not_allowed_count=not_allowed_count,
            not_allowed_pct=not_allowed_pct,
        )

        return artifact_enum_coverage
