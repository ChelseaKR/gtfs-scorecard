from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.rollup_members_item_expiry_status import RollupMembersItemExpiryStatus
from ..models.rollup_members_item_grade import RollupMembersItemGrade
from ..models.rollup_members_item_shapes_status_type_1 import (
    RollupMembersItemShapesStatusType1,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="RollupMembersItem")


@_attrs_define
class RollupMembersItem:
    """
    Attributes:
        id (str):
        name (str):
        score (float):
        grade (RollupMembersItemGrade):
        snapshot_date (str):
        needs_attention (bool):
        attention_reason (None | str):
        days_until_expiry (int | None):
        expiry_status (RollupMembersItemExpiryStatus):
        top_fix (None | str):
        top_fix_code (None | str | Unset): Finding code for the member's highest-priority fix, used to preserve evidence
            context when opening its scorecard.
        shapes_status (None | RollupMembersItemShapesStatusType1 | Unset):
        annual_trips (int | None | Unset):
    """

    id: str
    name: str
    score: float
    grade: RollupMembersItemGrade
    snapshot_date: str
    needs_attention: bool
    attention_reason: None | str
    days_until_expiry: int | None
    expiry_status: RollupMembersItemExpiryStatus
    top_fix: None | str
    top_fix_code: None | str | Unset = UNSET
    shapes_status: None | RollupMembersItemShapesStatusType1 | Unset = UNSET
    annual_trips: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        score = self.score

        grade = self.grade.value

        snapshot_date = self.snapshot_date

        needs_attention = self.needs_attention

        attention_reason: None | str
        attention_reason = self.attention_reason

        days_until_expiry: int | None
        days_until_expiry = self.days_until_expiry

        expiry_status = self.expiry_status.value

        top_fix: None | str
        top_fix = self.top_fix

        top_fix_code: None | str | Unset
        if isinstance(self.top_fix_code, Unset):
            top_fix_code = UNSET
        else:
            top_fix_code = self.top_fix_code

        shapes_status: None | str | Unset
        if isinstance(self.shapes_status, Unset):
            shapes_status = UNSET
        elif isinstance(self.shapes_status, RollupMembersItemShapesStatusType1):
            shapes_status = self.shapes_status.value
        else:
            shapes_status = self.shapes_status

        annual_trips: int | None | Unset
        if isinstance(self.annual_trips, Unset):
            annual_trips = UNSET
        else:
            annual_trips = self.annual_trips

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
                "score": score,
                "grade": grade,
                "snapshot_date": snapshot_date,
                "needs_attention": needs_attention,
                "attention_reason": attention_reason,
                "days_until_expiry": days_until_expiry,
                "expiry_status": expiry_status,
                "top_fix": top_fix,
            }
        )
        if top_fix_code is not UNSET:
            field_dict["top_fix_code"] = top_fix_code
        if shapes_status is not UNSET:
            field_dict["shapes_status"] = shapes_status
        if annual_trips is not UNSET:
            field_dict["annual_trips"] = annual_trips

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        id = _d.pop("id")

        name = _d.pop("name")

        score = _d.pop("score")

        grade = RollupMembersItemGrade(_d.pop("grade"))

        snapshot_date = _d.pop("snapshot_date")

        needs_attention = _d.pop("needs_attention")

        def _parse_attention_reason(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        attention_reason = _parse_attention_reason(_d.pop("attention_reason"))

        def _parse_days_until_expiry(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        days_until_expiry = _parse_days_until_expiry(_d.pop("days_until_expiry"))

        expiry_status = RollupMembersItemExpiryStatus(_d.pop("expiry_status"))

        def _parse_top_fix(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        top_fix = _parse_top_fix(_d.pop("top_fix"))

        def _parse_top_fix_code(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        top_fix_code = _parse_top_fix_code(_d.pop("top_fix_code", UNSET))

        def _parse_shapes_status(
            data: object,
        ) -> None | RollupMembersItemShapesStatusType1 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                shapes_status_type_1 = RollupMembersItemShapesStatusType1(data)

                return shapes_status_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RollupMembersItemShapesStatusType1 | Unset, data)

        shapes_status = _parse_shapes_status(_d.pop("shapes_status", UNSET))

        def _parse_annual_trips(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        annual_trips = _parse_annual_trips(_d.pop("annual_trips", UNSET))

        rollup_members_item = cls(
            id=id,
            name=name,
            score=score,
            grade=grade,
            snapshot_date=snapshot_date,
            needs_attention=needs_attention,
            attention_reason=attention_reason,
            days_until_expiry=days_until_expiry,
            expiry_status=expiry_status,
            top_fix=top_fix,
            top_fix_code=top_fix_code,
            shapes_status=shapes_status,
            annual_trips=annual_trips,
        )

        return rollup_members_item
