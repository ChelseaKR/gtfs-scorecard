from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.global_coverage_europe_country_code import GlobalCoverageEuropeCountryCode

T = TypeVar("T", bound="GlobalCoverageCountry")


@_attrs_define
class GlobalCoverageCountry:
    """
    Attributes:
        country_code (GlobalCoverageEuropeCountryCode):
        country_name (str):
        feed_record_count (int):
        share_pct (float):
    """

    country_code: GlobalCoverageEuropeCountryCode
    country_name: str
    feed_record_count: int
    share_pct: float

    def to_dict(self) -> dict[str, Any]:
        country_code = self.country_code.value

        country_name = self.country_name

        feed_record_count = self.feed_record_count

        share_pct = self.share_pct

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "country_code": country_code,
                "country_name": country_name,
                "feed_record_count": feed_record_count,
                "share_pct": share_pct,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        country_code = GlobalCoverageEuropeCountryCode(_d.pop("country_code"))

        country_name = _d.pop("country_name")

        feed_record_count = _d.pop("feed_record_count")

        share_pct = _d.pop("share_pct")

        global_coverage_country = cls(
            country_code=country_code,
            country_name=country_name,
            feed_record_count=feed_record_count,
            share_pct=share_pct,
        )

        return global_coverage_country
