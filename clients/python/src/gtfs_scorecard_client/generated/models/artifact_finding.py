from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.artifact_finding_severity import ArtifactFindingSeverity
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.artifact_consequence import ArtifactConsequence


T = TypeVar("T", bound="ArtifactFinding")


@_attrs_define
class ArtifactFinding:
    """
    Attributes:
        code (str):
        severity (ArtifactFindingSeverity):
        count (int):
        what (str):
        why (str):
        fix (str):
        effort (str):
        points (float):
        owner (str):
        rank (int | Unset): 1-based position in top_fixes; present only there.
        consequence (ArtifactConsequence | Unset): Per-finding consequence block (consequence.py). Reach is computed
            from this artifact. Ridership and served-area need are properties of the feed and are null with a reason
            wherever the writer did not join them; not_joined_here means the step that wrote this record does not read that
            input, not that the data does not exist.
    """

    code: str
    severity: ArtifactFindingSeverity
    count: int
    what: str
    why: str
    fix: str
    effort: str
    points: float
    owner: str
    rank: int | Unset = UNSET
    consequence: ArtifactConsequence | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        severity = self.severity.value

        count = self.count

        what = self.what

        why = self.why

        fix = self.fix

        effort = self.effort

        points = self.points

        owner = self.owner

        rank = self.rank

        consequence: dict[str, Any] | Unset = UNSET
        if not isinstance(self.consequence, Unset):
            consequence = self.consequence.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "code": code,
                "severity": severity,
                "count": count,
                "what": what,
                "why": why,
                "fix": fix,
                "effort": effort,
                "points": points,
                "owner": owner,
            }
        )
        if rank is not UNSET:
            field_dict["rank"] = rank
        if consequence is not UNSET:
            field_dict["consequence"] = consequence

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.artifact_consequence import ArtifactConsequence

        _d = dict(src_dict)
        code = _d.pop("code")

        severity = ArtifactFindingSeverity(_d.pop("severity"))

        count = _d.pop("count")

        what = _d.pop("what")

        why = _d.pop("why")

        fix = _d.pop("fix")

        effort = _d.pop("effort")

        points = _d.pop("points")

        owner = _d.pop("owner")

        rank = _d.pop("rank", UNSET)

        _consequence = _d.pop("consequence", UNSET)
        consequence: ArtifactConsequence | Unset
        if isinstance(_consequence, Unset):
            consequence = UNSET
        else:
            consequence = ArtifactConsequence.from_dict(_consequence)

        artifact_finding = cls(
            code=code,
            severity=severity,
            count=count,
            what=what,
            why=why,
            fix=fix,
            effort=effort,
            points=points,
            owner=owner,
            rank=rank,
            consequence=consequence,
        )

        return artifact_finding
