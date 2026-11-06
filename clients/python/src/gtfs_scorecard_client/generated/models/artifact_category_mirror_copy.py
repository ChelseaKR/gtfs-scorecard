from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ArtifactCategoryMirrorCopy")


@_attrs_define
class ArtifactCategoryMirrorCopy:
    """The held mirror copy's own service dates, never an expiry countdown. Either side is null when unknown.

    Attributes:
        service_start (None | str):
        service_end (None | str):
    """

    service_start: None | str
    service_end: None | str

    def to_dict(self) -> dict[str, Any]:
        service_start: None | str
        service_start = self.service_start

        service_end: None | str
        service_end = self.service_end

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "service_start": service_start,
                "service_end": service_end,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)

        def _parse_service_start(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        service_start = _parse_service_start(_d.pop("service_start"))

        def _parse_service_end(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        service_end = _parse_service_end(_d.pop("service_end"))

        artifact_category_mirror_copy = cls(
            service_start=service_start,
            service_end=service_end,
        )

        return artifact_category_mirror_copy
