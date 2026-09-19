from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="CoverageDefinitions")


@_attrs_define
class CoverageDefinitions:
    """
    Attributes:
        configured_feed_records (str):
        active_canonical_feed_records (str):
        country_count (str):
        distinct_organization_keys (str):
        provisional_organization_keys (str):
        published_scorecard_pages (str):
        scored_latest_rows (str):
    """

    configured_feed_records: str
    active_canonical_feed_records: str
    country_count: str
    distinct_organization_keys: str
    provisional_organization_keys: str
    published_scorecard_pages: str
    scored_latest_rows: str

    def to_dict(self) -> dict[str, Any]:
        configured_feed_records = self.configured_feed_records

        active_canonical_feed_records = self.active_canonical_feed_records

        country_count = self.country_count

        distinct_organization_keys = self.distinct_organization_keys

        provisional_organization_keys = self.provisional_organization_keys

        published_scorecard_pages = self.published_scorecard_pages

        scored_latest_rows = self.scored_latest_rows

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "configured_feed_records": configured_feed_records,
                "active_canonical_feed_records": active_canonical_feed_records,
                "country_count": country_count,
                "distinct_organization_keys": distinct_organization_keys,
                "provisional_organization_keys": provisional_organization_keys,
                "published_scorecard_pages": published_scorecard_pages,
                "scored_latest_rows": scored_latest_rows,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        configured_feed_records = _d.pop("configured_feed_records")

        active_canonical_feed_records = _d.pop("active_canonical_feed_records")

        country_count = _d.pop("country_count")

        distinct_organization_keys = _d.pop("distinct_organization_keys")

        provisional_organization_keys = _d.pop("provisional_organization_keys")

        published_scorecard_pages = _d.pop("published_scorecard_pages")

        scored_latest_rows = _d.pop("scored_latest_rows")

        coverage_definitions = cls(
            configured_feed_records=configured_feed_records,
            active_canonical_feed_records=active_canonical_feed_records,
            country_count=country_count,
            distinct_organization_keys=distinct_organization_keys,
            provisional_organization_keys=provisional_organization_keys,
            published_scorecard_pages=published_scorecard_pages,
            scored_latest_rows=scored_latest_rows,
        )

        return coverage_definitions
