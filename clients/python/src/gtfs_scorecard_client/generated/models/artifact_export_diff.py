from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ArtifactExportDiff")


@_attrs_define
class ArtifactExportDiff:
    """What changed in the feed content since the previous export (EXP-18); present only on the run that first scored a
    changed export with structural differences.

        Attributes:
            from_sha256 (None | str):
            to_sha256 (str):
            changes (list[str]):
    """

    from_sha256: None | str
    to_sha256: str
    changes: list[str]

    def to_dict(self) -> dict[str, Any]:
        from_sha256: None | str
        from_sha256 = self.from_sha256

        to_sha256 = self.to_sha256

        changes = self.changes

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "from_sha256": from_sha256,
                "to_sha256": to_sha256,
                "changes": changes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)

        def _parse_from_sha256(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        from_sha256 = _parse_from_sha256(_d.pop("from_sha256"))

        to_sha256 = _d.pop("to_sha256")

        changes = cast(list[str], _d.pop("changes"))

        artifact_export_diff = cls(
            from_sha256=from_sha256,
            to_sha256=to_sha256,
            changes=changes,
        )

        return artifact_export_diff
