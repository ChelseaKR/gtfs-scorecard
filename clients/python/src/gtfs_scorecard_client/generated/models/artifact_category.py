from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.artifact_category_reason import ArtifactCategoryReason
from ..models.artifact_category_status import ArtifactCategoryStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.artifact_category_details import ArtifactCategoryDetails
    from ..models.artifact_category_mirror_copy import ArtifactCategoryMirrorCopy
    from ..models.artifact_finding import ArtifactFinding


T = TypeVar("T", bound="ArtifactCategory")


@_attrs_define
class ArtifactCategory:
    """
    Attributes:
        name (str):
        status (ArtifactCategoryStatus):
        weight (float):
        summary (str):
        reason (ArtifactCategoryReason | Unset): Why a not-measured category is held out of the grade. Set only on a
            held Mobility Database mirror copy's freshness (score.hold_mirror_freshness).
        mirror_copy (ArtifactCategoryMirrorCopy | Unset): The held mirror copy's own service dates, never an expiry
            countdown. Either side is null when unknown.
        score (float | Unset):
        findings (list[ArtifactFinding] | Unset):
        details (ArtifactCategoryDetails | Unset):
    """

    name: str
    status: ArtifactCategoryStatus
    weight: float
    summary: str
    reason: ArtifactCategoryReason | Unset = UNSET
    mirror_copy: ArtifactCategoryMirrorCopy | Unset = UNSET
    score: float | Unset = UNSET
    findings: list[ArtifactFinding] | Unset = UNSET
    details: ArtifactCategoryDetails | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        status = self.status.value

        weight = self.weight

        summary = self.summary

        reason: str | Unset = UNSET
        if not isinstance(self.reason, Unset):
            reason = self.reason.value

        mirror_copy: dict[str, Any] | Unset = UNSET
        if not isinstance(self.mirror_copy, Unset):
            mirror_copy = self.mirror_copy.to_dict()

        score = self.score

        findings: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.findings, Unset):
            findings = []
            for findings_item_data in self.findings:
                findings_item = findings_item_data.to_dict()
                findings.append(findings_item)

        details: dict[str, Any] | Unset = UNSET
        if not isinstance(self.details, Unset):
            details = self.details.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "status": status,
                "weight": weight,
                "summary": summary,
            }
        )
        if reason is not UNSET:
            field_dict["reason"] = reason
        if mirror_copy is not UNSET:
            field_dict["mirror_copy"] = mirror_copy
        if score is not UNSET:
            field_dict["score"] = score
        if findings is not UNSET:
            field_dict["findings"] = findings
        if details is not UNSET:
            field_dict["details"] = details

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.artifact_category_details import (
            ArtifactCategoryDetails,
        )
        from ..models.artifact_category_mirror_copy import (
            ArtifactCategoryMirrorCopy,
        )
        from ..models.artifact_finding import ArtifactFinding

        _d = dict(src_dict)
        name = _d.pop("name")

        status = ArtifactCategoryStatus(_d.pop("status"))

        weight = _d.pop("weight")

        summary = _d.pop("summary")

        _reason = _d.pop("reason", UNSET)
        reason: ArtifactCategoryReason | Unset
        if isinstance(_reason, Unset):
            reason = UNSET
        else:
            reason = ArtifactCategoryReason(_reason)

        _mirror_copy = _d.pop("mirror_copy", UNSET)
        mirror_copy: ArtifactCategoryMirrorCopy | Unset
        if isinstance(_mirror_copy, Unset):
            mirror_copy = UNSET
        else:
            mirror_copy = ArtifactCategoryMirrorCopy.from_dict(_mirror_copy)

        score = _d.pop("score", UNSET)

        _findings = _d.pop("findings", UNSET)
        findings: list[ArtifactFinding] | Unset = UNSET
        if _findings is not UNSET:
            findings = []
            for findings_item_data in _findings:
                findings_item = ArtifactFinding.from_dict(findings_item_data)

                findings.append(findings_item)

        _details = _d.pop("details", UNSET)
        details: ArtifactCategoryDetails | Unset
        if isinstance(_details, Unset):
            details = UNSET
        else:
            details = ArtifactCategoryDetails.from_dict(_details)

        artifact_category = cls(
            name=name,
            status=status,
            weight=weight,
            summary=summary,
            reason=reason,
            mirror_copy=mirror_copy,
            score=score,
            findings=findings,
            details=details,
        )

        return artifact_category
