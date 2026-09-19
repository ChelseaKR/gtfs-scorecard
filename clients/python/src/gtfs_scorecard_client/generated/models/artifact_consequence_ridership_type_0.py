from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="ArtifactConsequenceRidershipType0")


@_attrs_define
class ArtifactConsequenceRidershipType0:
    """
    Attributes:
        annual_rider_trips (int | Unset):
        reason (Literal[''] | Unset):
    """

    annual_rider_trips: int | Unset = UNSET
    reason: Literal[""] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        annual_rider_trips = self.annual_rider_trips

        reason = self.reason

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if annual_rider_trips is not UNSET:
            field_dict["annual_rider_trips"] = annual_rider_trips
        if reason is not UNSET:
            field_dict["reason"] = reason

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        annual_rider_trips = _d.pop("annual_rider_trips", UNSET)

        reason = cast(Literal[""] | Unset, _d.pop("reason", UNSET))
        if reason != "" and not isinstance(reason, Unset):
            raise ValueError(f"reason must match const '', got '{reason}'")

        artifact_consequence_ridership_type_0 = cls(
            annual_rider_trips=annual_rider_trips,
            reason=reason,
        )

        artifact_consequence_ridership_type_0.additional_properties = _d
        return artifact_consequence_ridership_type_0

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
