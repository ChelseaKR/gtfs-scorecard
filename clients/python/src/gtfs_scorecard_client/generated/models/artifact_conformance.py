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

T = TypeVar("T", bound="ArtifactConformance")


@_attrs_define
class ArtifactConformance:
    """Conformance-mark credential over the scores (conformance.assess). The independent version changes when derived
    machine-readable guidance must be refreshed.

        Attributes:
            version (Literal[2] | Unset):
    """

    version: Literal[2] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        version = self.version

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if version is not UNSET:
            field_dict["version"] = version

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        version = cast(Literal[2] | Unset, _d.pop("version", UNSET))
        if version != 2 and not isinstance(version, Unset):
            raise ValueError(f"version must match const 2, got '{version}'")

        artifact_conformance = cls(
            version=version,
        )

        artifact_conformance.additional_properties = _d
        return artifact_conformance

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
