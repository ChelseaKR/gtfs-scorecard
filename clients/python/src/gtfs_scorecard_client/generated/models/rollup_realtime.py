from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.rollup_realtime_bands import RollupRealtimeBands
    from ..models.rollup_realtime_members_item import RollupRealtimeMembersItem


T = TypeVar("T", bound="RollupRealtime")


@_attrs_define
class RollupRealtime:
    """Realtime reliability across this program's members, from the scheduled realtime monitor's record. Members the
    monitor has not observed are counted as unmonitored, never as a zero. Not a grade input.

        Attributes:
            configured_feed_records (int):
            monitored_feed_records (int):
            bands (RollupRealtimeBands):
            members (list[RollupRealtimeMembersItem]):
            median_uptime_pct (float | None | Unset):
            median_lag_seconds (int | None | Unset):
            median_coverage_pct (float | None | Unset):
    """

    configured_feed_records: int
    monitored_feed_records: int
    bands: RollupRealtimeBands
    members: list[RollupRealtimeMembersItem]
    median_uptime_pct: float | None | Unset = UNSET
    median_lag_seconds: int | None | Unset = UNSET
    median_coverage_pct: float | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        configured_feed_records = self.configured_feed_records

        monitored_feed_records = self.monitored_feed_records

        bands = self.bands.to_dict()

        members = []
        for members_item_data in self.members:
            members_item = members_item_data.to_dict()
            members.append(members_item)

        median_uptime_pct: float | None | Unset
        if isinstance(self.median_uptime_pct, Unset):
            median_uptime_pct = UNSET
        else:
            median_uptime_pct = self.median_uptime_pct

        median_lag_seconds: int | None | Unset
        if isinstance(self.median_lag_seconds, Unset):
            median_lag_seconds = UNSET
        else:
            median_lag_seconds = self.median_lag_seconds

        median_coverage_pct: float | None | Unset
        if isinstance(self.median_coverage_pct, Unset):
            median_coverage_pct = UNSET
        else:
            median_coverage_pct = self.median_coverage_pct

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "configured_feed_records": configured_feed_records,
                "monitored_feed_records": monitored_feed_records,
                "bands": bands,
                "members": members,
            }
        )
        if median_uptime_pct is not UNSET:
            field_dict["median_uptime_pct"] = median_uptime_pct
        if median_lag_seconds is not UNSET:
            field_dict["median_lag_seconds"] = median_lag_seconds
        if median_coverage_pct is not UNSET:
            field_dict["median_coverage_pct"] = median_coverage_pct

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.rollup_realtime_bands import RollupRealtimeBands
        from ..models.rollup_realtime_members_item import (
            RollupRealtimeMembersItem,
        )

        _d = dict(src_dict)
        configured_feed_records = _d.pop("configured_feed_records")

        monitored_feed_records = _d.pop("monitored_feed_records")

        bands = RollupRealtimeBands.from_dict(_d.pop("bands"))

        members = []
        _members = _d.pop("members")
        for members_item_data in _members:
            members_item = RollupRealtimeMembersItem.from_dict(members_item_data)

            members.append(members_item)

        def _parse_median_uptime_pct(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        median_uptime_pct = _parse_median_uptime_pct(_d.pop("median_uptime_pct", UNSET))

        def _parse_median_lag_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        median_lag_seconds = _parse_median_lag_seconds(
            _d.pop("median_lag_seconds", UNSET)
        )

        def _parse_median_coverage_pct(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        median_coverage_pct = _parse_median_coverage_pct(
            _d.pop("median_coverage_pct", UNSET)
        )

        rollup_realtime = cls(
            configured_feed_records=configured_feed_records,
            monitored_feed_records=monitored_feed_records,
            bands=bands,
            members=members,
            median_uptime_pct=median_uptime_pct,
            median_lag_seconds=median_lag_seconds,
            median_coverage_pct=median_coverage_pct,
        )

        return rollup_realtime
