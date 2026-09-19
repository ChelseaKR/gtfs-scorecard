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

from ..models.artifact_ferry_profile_fares_model import ArtifactFerryProfileFaresModel

T = TypeVar("T", bound="ArtifactFerryProfileFares")


@_attrs_define
class ArtifactFerryProfileFares:
    """
    Attributes:
        scope (Literal['whole_feed']):
        fare_free (bool):
        model (ArtifactFerryProfileFaresModel):
        applied (bool):
    """

    scope: Literal["whole_feed"]
    fare_free: bool
    model: ArtifactFerryProfileFaresModel
    applied: bool

    def to_dict(self) -> dict[str, Any]:
        scope = self.scope

        fare_free = self.fare_free

        model = self.model.value

        applied = self.applied

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "scope": scope,
                "fare_free": fare_free,
                "model": model,
                "applied": applied,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        scope = cast(Literal["whole_feed"], _d.pop("scope"))
        if scope != "whole_feed":
            raise ValueError(f"scope must match const 'whole_feed', got '{scope}'")

        fare_free = _d.pop("fare_free")

        model = ArtifactFerryProfileFaresModel(_d.pop("model"))

        applied = _d.pop("applied")

        artifact_ferry_profile_fares = cls(
            scope=scope,
            fare_free=fare_free,
            model=model,
            applied=applied,
        )

        return artifact_ferry_profile_fares
