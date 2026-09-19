from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ArtifactFerryProfileRealtime")


@_attrs_define
class ArtifactFerryProfileRealtime:
    """
    Attributes:
        scope (Literal['whole_feed']):
        configured_kinds (list[str]):
        kinds_configured (int):
    """

    scope: Literal["whole_feed"]
    configured_kinds: list[str]
    kinds_configured: int

    def to_dict(self) -> dict[str, Any]:
        scope = self.scope

        configured_kinds = self.configured_kinds

        kinds_configured = self.kinds_configured

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "scope": scope,
                "configured_kinds": configured_kinds,
                "kinds_configured": kinds_configured,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        scope = cast(Literal["whole_feed"], _d.pop("scope"))
        if scope != "whole_feed":
            raise ValueError(f"scope must match const 'whole_feed', got '{scope}'")

        configured_kinds = cast(list[str], _d.pop("configured_kinds"))

        kinds_configured = _d.pop("kinds_configured")

        artifact_ferry_profile_realtime = cls(
            scope=scope,
            configured_kinds=configured_kinds,
            kinds_configured=kinds_configured,
        )

        return artifact_ferry_profile_realtime
