from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.artifact_confidence_level import ArtifactConfidenceLevel

T = TypeVar("T", bound="ArtifactConfidence")


@_attrs_define
class ArtifactConfidence:
    """Measurement-confidence read (EXP-01): how much of this grade the pipeline could measure this run and from what
    source. A legibility layer on the one grade, never a second grade; absent on artifacts published before schema 1.5.

        Attributes:
            level (ArtifactConfidenceLevel):
            measured_categories (int):
            total_categories (int):
            fetch_source (str):
            rt_windows (int):
            feed_age_days (int):
            notes (list[str]):
    """

    level: ArtifactConfidenceLevel
    measured_categories: int
    total_categories: int
    fetch_source: str
    rt_windows: int
    feed_age_days: int
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        level = self.level.value

        measured_categories = self.measured_categories

        total_categories = self.total_categories

        fetch_source = self.fetch_source

        rt_windows = self.rt_windows

        feed_age_days = self.feed_age_days

        notes = self.notes

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "level": level,
                "measured_categories": measured_categories,
                "total_categories": total_categories,
                "fetch_source": fetch_source,
                "rt_windows": rt_windows,
                "feed_age_days": feed_age_days,
                "notes": notes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        level = ArtifactConfidenceLevel(_d.pop("level"))

        measured_categories = _d.pop("measured_categories")

        total_categories = _d.pop("total_categories")

        fetch_source = _d.pop("fetch_source")

        rt_windows = _d.pop("rt_windows")

        feed_age_days = _d.pop("feed_age_days")

        notes = cast(list[str], _d.pop("notes"))

        artifact_confidence = cls(
            level=level,
            measured_categories=measured_categories,
            total_categories=total_categories,
            fetch_source=fetch_source,
            rt_windows=rt_windows,
            feed_age_days=feed_age_days,
            notes=notes,
        )

        return artifact_confidence
