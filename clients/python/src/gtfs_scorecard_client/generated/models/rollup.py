from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.rollup_common_fixes_item import RollupCommonFixesItem
    from ..models.rollup_comparison import RollupComparison
    from ..models.rollup_expired import RollupExpired
    from ..models.rollup_grade_distribution import RollupGradeDistribution
    from ..models.rollup_members_item import RollupMembersItem
    from ..models.rollup_realtime import RollupRealtime
    from ..models.rollup_reconciliation import RollupReconciliation
    from ..models.rollup_rollup import RollupRollup
    from ..models.rollup_shapes_readiness import RollupShapesReadiness


T = TypeVar("T", bound="Rollup")


@_attrs_define
class Rollup:
    """One program's cohort view: members needing attention first, common fixes counted only across the guarded comparison
    cohort, and expiry / shapes-readiness summaries over all members. Additive within a major schema_version: newer
    fields stay optional so older published documents still conform. Top level is closed (additionalProperties: false)
    so a new block cannot reach production without a schema update, the same enforcement point as artifact.schema.json.

        Attributes:
            schema_version (str):
            rollup (RollupRollup):
            generated_at (str):
            agency_count (int):
            average_score (float | None):
            grade_distribution (RollupGradeDistribution):
            needs_attention (int):
            expired (RollupExpired):
            members (list[RollupMembersItem]):
            common_fixes (list[RollupCommonFixesItem]):
            shapes_readiness (RollupShapesReadiness | Unset):
            comparison (RollupComparison | Unset):
            state_percentile (int | None | Unset): Deprecated compatibility field. Current payloads publish null; historical
                1.x state rollups may contain an integer.
            reconciliation (RollupReconciliation | Unset): How this program's feed records line up with an external agency
                directory published by a transport authority. Present only for programs with a mapped directory. Never a grade
                input.
            realtime (RollupRealtime | Unset): Realtime reliability across this program's members, from the scheduled
                realtime monitor's record. Members the monitor has not observed are counted as unmonitored, never as a zero. Not
                a grade input.
    """

    schema_version: str
    rollup: RollupRollup
    generated_at: str
    agency_count: int
    average_score: float | None
    grade_distribution: RollupGradeDistribution
    needs_attention: int
    expired: RollupExpired
    members: list[RollupMembersItem]
    common_fixes: list[RollupCommonFixesItem]
    shapes_readiness: RollupShapesReadiness | Unset = UNSET
    comparison: RollupComparison | Unset = UNSET
    state_percentile: int | None | Unset = UNSET
    reconciliation: RollupReconciliation | Unset = UNSET
    realtime: RollupRealtime | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        schema_version = self.schema_version

        rollup = self.rollup.to_dict()

        generated_at = self.generated_at

        agency_count = self.agency_count

        average_score: float | None
        average_score = self.average_score

        grade_distribution = self.grade_distribution.to_dict()

        needs_attention = self.needs_attention

        expired = self.expired.to_dict()

        members = []
        for members_item_data in self.members:
            members_item = members_item_data.to_dict()
            members.append(members_item)

        common_fixes = []
        for common_fixes_item_data in self.common_fixes:
            common_fixes_item = common_fixes_item_data.to_dict()
            common_fixes.append(common_fixes_item)

        shapes_readiness: dict[str, Any] | Unset = UNSET
        if not isinstance(self.shapes_readiness, Unset):
            shapes_readiness = self.shapes_readiness.to_dict()

        comparison: dict[str, Any] | Unset = UNSET
        if not isinstance(self.comparison, Unset):
            comparison = self.comparison.to_dict()

        state_percentile: int | None | Unset
        if isinstance(self.state_percentile, Unset):
            state_percentile = UNSET
        else:
            state_percentile = self.state_percentile

        reconciliation: dict[str, Any] | Unset = UNSET
        if not isinstance(self.reconciliation, Unset):
            reconciliation = self.reconciliation.to_dict()

        realtime: dict[str, Any] | Unset = UNSET
        if not isinstance(self.realtime, Unset):
            realtime = self.realtime.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "schema_version": schema_version,
                "rollup": rollup,
                "generated_at": generated_at,
                "agency_count": agency_count,
                "average_score": average_score,
                "grade_distribution": grade_distribution,
                "needs_attention": needs_attention,
                "expired": expired,
                "members": members,
                "common_fixes": common_fixes,
            }
        )
        if shapes_readiness is not UNSET:
            field_dict["shapes_readiness"] = shapes_readiness
        if comparison is not UNSET:
            field_dict["comparison"] = comparison
        if state_percentile is not UNSET:
            field_dict["state_percentile"] = state_percentile
        if reconciliation is not UNSET:
            field_dict["reconciliation"] = reconciliation
        if realtime is not UNSET:
            field_dict["realtime"] = realtime

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.rollup_common_fixes_item import (
            RollupCommonFixesItem,
        )
        from ..models.rollup_comparison import RollupComparison
        from ..models.rollup_expired import RollupExpired
        from ..models.rollup_grade_distribution import (
            RollupGradeDistribution,
        )
        from ..models.rollup_members_item import RollupMembersItem
        from ..models.rollup_realtime import RollupRealtime
        from ..models.rollup_reconciliation import RollupReconciliation
        from ..models.rollup_rollup import RollupRollup
        from ..models.rollup_shapes_readiness import (
            RollupShapesReadiness,
        )

        _d = dict(src_dict)
        schema_version = _d.pop("schema_version")

        rollup = RollupRollup.from_dict(_d.pop("rollup"))

        generated_at = _d.pop("generated_at")

        agency_count = _d.pop("agency_count")

        def _parse_average_score(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        average_score = _parse_average_score(_d.pop("average_score"))

        grade_distribution = RollupGradeDistribution.from_dict(
            _d.pop("grade_distribution")
        )

        needs_attention = _d.pop("needs_attention")

        expired = RollupExpired.from_dict(_d.pop("expired"))

        members = []
        _members = _d.pop("members")
        for members_item_data in _members:
            members_item = RollupMembersItem.from_dict(members_item_data)

            members.append(members_item)

        common_fixes = []
        _common_fixes = _d.pop("common_fixes")
        for common_fixes_item_data in _common_fixes:
            common_fixes_item = RollupCommonFixesItem.from_dict(common_fixes_item_data)

            common_fixes.append(common_fixes_item)

        _shapes_readiness = _d.pop("shapes_readiness", UNSET)
        shapes_readiness: RollupShapesReadiness | Unset
        if isinstance(_shapes_readiness, Unset):
            shapes_readiness = UNSET
        else:
            shapes_readiness = RollupShapesReadiness.from_dict(_shapes_readiness)

        _comparison = _d.pop("comparison", UNSET)
        comparison: RollupComparison | Unset
        if isinstance(_comparison, Unset):
            comparison = UNSET
        else:
            comparison = RollupComparison.from_dict(_comparison)

        def _parse_state_percentile(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        state_percentile = _parse_state_percentile(_d.pop("state_percentile", UNSET))

        _reconciliation = _d.pop("reconciliation", UNSET)
        reconciliation: RollupReconciliation | Unset
        if isinstance(_reconciliation, Unset):
            reconciliation = UNSET
        else:
            reconciliation = RollupReconciliation.from_dict(_reconciliation)

        _realtime = _d.pop("realtime", UNSET)
        realtime: RollupRealtime | Unset
        if isinstance(_realtime, Unset):
            realtime = UNSET
        else:
            realtime = RollupRealtime.from_dict(_realtime)

        rollup = cls(
            schema_version=schema_version,
            rollup=rollup,
            generated_at=generated_at,
            agency_count=agency_count,
            average_score=average_score,
            grade_distribution=grade_distribution,
            needs_attention=needs_attention,
            expired=expired,
            members=members,
            common_fixes=common_fixes,
            shapes_readiness=shapes_readiness,
            comparison=comparison,
            state_percentile=state_percentile,
            reconciliation=reconciliation,
            realtime=realtime,
        )

        return rollup
