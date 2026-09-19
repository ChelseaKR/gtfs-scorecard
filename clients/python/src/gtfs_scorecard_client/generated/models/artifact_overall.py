from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.artifact_overall_grade import ArtifactOverallGrade
from ..types import UNSET, Unset

T = TypeVar("T", bound="ArtifactOverall")


@_attrs_define
class ArtifactOverall:
    """
    Attributes:
        score (float):
        grade (ArtifactOverallGrade):
        margin_to_next_band (float | None | Unset):
        margin_to_lower_band (float | None | Unset):
    """

    score: float
    grade: ArtifactOverallGrade
    margin_to_next_band: float | None | Unset = UNSET
    margin_to_lower_band: float | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        score = self.score

        grade = self.grade.value

        margin_to_next_band: float | None | Unset
        if isinstance(self.margin_to_next_band, Unset):
            margin_to_next_band = UNSET
        else:
            margin_to_next_band = self.margin_to_next_band

        margin_to_lower_band: float | None | Unset
        if isinstance(self.margin_to_lower_band, Unset):
            margin_to_lower_band = UNSET
        else:
            margin_to_lower_band = self.margin_to_lower_band

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "score": score,
                "grade": grade,
            }
        )
        if margin_to_next_band is not UNSET:
            field_dict["margin_to_next_band"] = margin_to_next_band
        if margin_to_lower_band is not UNSET:
            field_dict["margin_to_lower_band"] = margin_to_lower_band

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        score = _d.pop("score")

        grade = ArtifactOverallGrade(_d.pop("grade"))

        def _parse_margin_to_next_band(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        margin_to_next_band = _parse_margin_to_next_band(
            _d.pop("margin_to_next_band", UNSET)
        )

        def _parse_margin_to_lower_band(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        margin_to_lower_band = _parse_margin_to_lower_band(
            _d.pop("margin_to_lower_band", UNSET)
        )

        artifact_overall = cls(
            score=score,
            grade=grade,
            margin_to_next_band=margin_to_next_band,
            margin_to_lower_band=margin_to_lower_band,
        )

        return artifact_overall
