from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.coverage_definitions import CoverageDefinitions


T = TypeVar("T", bound="Coverage")


@_attrs_define
class Coverage:
    """
    Attributes:
        configured_feed_records (int):
        active_canonical_feed_records (int):
        country_count (int):
        distinct_organization_keys (int):
        provisional_organization_keys (int):
        published_scorecard_pages (int):
        scored_latest_rows (int):
        definitions (CoverageDefinitions):
    """

    configured_feed_records: int
    active_canonical_feed_records: int
    country_count: int
    distinct_organization_keys: int
    provisional_organization_keys: int
    published_scorecard_pages: int
    scored_latest_rows: int
    definitions: CoverageDefinitions

    def to_dict(self) -> dict[str, Any]:
        configured_feed_records = self.configured_feed_records

        active_canonical_feed_records = self.active_canonical_feed_records

        country_count = self.country_count

        distinct_organization_keys = self.distinct_organization_keys

        provisional_organization_keys = self.provisional_organization_keys

        published_scorecard_pages = self.published_scorecard_pages

        scored_latest_rows = self.scored_latest_rows

        definitions = self.definitions.to_dict()

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
                "definitions": definitions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.coverage_definitions import CoverageDefinitions

        _d = dict(src_dict)
        configured_feed_records = _d.pop("configured_feed_records")

        active_canonical_feed_records = _d.pop("active_canonical_feed_records")

        country_count = _d.pop("country_count")

        distinct_organization_keys = _d.pop("distinct_organization_keys")

        provisional_organization_keys = _d.pop("provisional_organization_keys")

        published_scorecard_pages = _d.pop("published_scorecard_pages")

        scored_latest_rows = _d.pop("scored_latest_rows")

        definitions = CoverageDefinitions.from_dict(_d.pop("definitions"))

        coverage = cls(
            configured_feed_records=configured_feed_records,
            active_canonical_feed_records=active_canonical_feed_records,
            country_count=country_count,
            distinct_organization_keys=distinct_organization_keys,
            provisional_organization_keys=provisional_organization_keys,
            published_scorecard_pages=published_scorecard_pages,
            scored_latest_rows=scored_latest_rows,
            definitions=definitions,
        )

        return coverage
