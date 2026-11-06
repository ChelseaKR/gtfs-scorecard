from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.artifact_overall_grade import ArtifactOverallGrade
from ..models.artifact_overall_grade_qualifier import ArtifactOverallGradeQualifier
from ..types import UNSET, Unset

T = TypeVar("T", bound="ArtifactOverall")


@_attrs_define
class ArtifactOverall:
    """
    Attributes:
        score (float):
        grade (ArtifactOverallGrade):
        grade_qualifier (ArtifactOverallGradeQualifier | Unset): Present only when the grade is partial: freshness was
            not measured because an expired Mobility Database mirror copy was held out of the grade (rubric 1.5). The letter
            is still published and must be shown with this qualifier.
        margin_to_next_band (float | None | Unset):
        margin_to_lower_band (float | None | Unset):
    """

    score: float
    grade: ArtifactOverallGrade
    grade_qualifier: ArtifactOverallGradeQualifier | Unset = UNSET
    margin_to_next_band: float | None | Unset = UNSET
    margin_to_lower_band: float | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        score = self.score

        grade = self.grade.value

        grade_qualifier: str | Unset = UNSET
        if not isinstance(self.grade_qualifier, Unset):
            grade_qualifier = self.grade_qualifier.value

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
        if grade_qualifier is not UNSET:
            field_dict["grade_qualifier"] = grade_qualifier
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

        _grade_qualifier = _d.pop("grade_qualifier", UNSET)
        grade_qualifier: ArtifactOverallGradeQualifier | Unset
        if isinstance(_grade_qualifier, Unset):
            grade_qualifier = UNSET
        else:
            grade_qualifier = ArtifactOverallGradeQualifier(_grade_qualifier)

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
            grade_qualifier=grade_qualifier,
            margin_to_next_band=margin_to_next_band,
            margin_to_lower_band=margin_to_lower_band,
        )

        return artifact_overall
