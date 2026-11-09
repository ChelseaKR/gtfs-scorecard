from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ArtifactHeldMirrorFreshnessMirrorCopy")


@_attrs_define
class ArtifactHeldMirrorFreshnessMirrorCopy:
    """
    Attributes:
        service_start (datetime.date | None):
        service_end (datetime.date | None):
    """

    service_start: datetime.date | None
    service_end: datetime.date | None

    def to_dict(self) -> dict[str, Any]:
        service_start: None | str
        if isinstance(self.service_start, datetime.date):
            service_start = self.service_start.isoformat()
        else:
            service_start = self.service_start

        service_end: None | str
        if isinstance(self.service_end, datetime.date):
            service_end = self.service_end.isoformat()
        else:
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

        def _parse_service_start(data: object) -> datetime.date | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                service_start_type_0 = datetime.date.fromisoformat(data)

                return service_start_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None, data)

        service_start = _parse_service_start(_d.pop("service_start"))

        def _parse_service_end(data: object) -> datetime.date | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                service_end_type_0 = datetime.date.fromisoformat(data)

                return service_end_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None, data)

        service_end = _parse_service_end(_d.pop("service_end"))

        artifact_held_mirror_freshness_mirror_copy = cls(
            service_start=service_start,
            service_end=service_end,
        )

        return artifact_held_mirror_freshness_mirror_copy
