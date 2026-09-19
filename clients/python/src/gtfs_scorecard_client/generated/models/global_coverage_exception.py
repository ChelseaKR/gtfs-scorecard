from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.global_coverage_exception_key import GlobalCoverageExceptionKey

T = TypeVar("T", bound="GlobalCoverageException")


@_attrs_define
class GlobalCoverageException:
    """
    Attributes:
        key (GlobalCoverageExceptionKey):
        label (str):
        count (int):
        feed_record_ids (list[str]):
    """

    key: GlobalCoverageExceptionKey
    label: str
    count: int
    feed_record_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        key = self.key.value

        label = self.label

        count = self.count

        feed_record_ids = self.feed_record_ids

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "key": key,
                "label": label,
                "count": count,
                "feed_record_ids": feed_record_ids,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        key = GlobalCoverageExceptionKey(_d.pop("key"))

        label = _d.pop("label")

        count = _d.pop("count")

        feed_record_ids = cast(list[str], _d.pop("feed_record_ids"))

        global_coverage_exception = cls(
            key=key,
            label=label,
            count=count,
            feed_record_ids=feed_record_ids,
        )

        return global_coverage_exception
