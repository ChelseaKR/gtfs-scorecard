from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.artifact_held_mirror_freshness_mirror_copy import (
        ArtifactHeldMirrorFreshnessMirrorCopy,
    )


T = TypeVar("T", bound="ArtifactHeldMirrorFreshness")


@_attrs_define
class ArtifactHeldMirrorFreshness:
    """Freshness held out of the grade because the feed URL failed and the Mobility Database mirror copy scored instead has
    already ended its service. It has no score, findings, or details: the copy's dates sit under mirror_copy, never as
    an expiry countdown, so they cannot read as the agency's own lapse. Comes with overall.grade_qualifier.

        Attributes:
            name (Literal['freshness']):
            status (Literal['not_yet_measured']):
            weight (float):
            reason (Literal['mirror_copy_expired']):
            summary (str):
            mirror_copy (ArtifactHeldMirrorFreshnessMirrorCopy):
    """

    name: Literal["freshness"]
    status: Literal["not_yet_measured"]
    weight: float
    reason: Literal["mirror_copy_expired"]
    summary: str
    mirror_copy: ArtifactHeldMirrorFreshnessMirrorCopy

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        status = self.status

        weight = self.weight

        reason = self.reason

        summary = self.summary

        mirror_copy = self.mirror_copy.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "status": status,
                "weight": weight,
                "reason": reason,
                "summary": summary,
                "mirror_copy": mirror_copy,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.artifact_held_mirror_freshness_mirror_copy import (
            ArtifactHeldMirrorFreshnessMirrorCopy,
        )

        _d = dict(src_dict)
        name = cast(Literal["freshness"], _d.pop("name"))
        if name != "freshness":
            raise ValueError(f"name must match const 'freshness', got '{name}'")

        status = cast(Literal["not_yet_measured"], _d.pop("status"))
        if status != "not_yet_measured":
            raise ValueError(
                f"status must match const 'not_yet_measured', got '{status}'"
            )

        weight = _d.pop("weight")

        reason = cast(Literal["mirror_copy_expired"], _d.pop("reason"))
        if reason != "mirror_copy_expired":
            raise ValueError(
                f"reason must match const 'mirror_copy_expired', got '{reason}'"
            )

        summary = _d.pop("summary")

        mirror_copy = ArtifactHeldMirrorFreshnessMirrorCopy.from_dict(
            _d.pop("mirror_copy")
        )

        artifact_held_mirror_freshness = cls(
            name=name,
            status=status,
            weight=weight,
            reason=reason,
            summary=summary,
            mirror_copy=mirror_copy,
        )

        return artifact_held_mirror_freshness
