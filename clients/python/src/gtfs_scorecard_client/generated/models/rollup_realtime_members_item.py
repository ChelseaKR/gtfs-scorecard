from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.rollup_realtime_members_item_band import RollupRealtimeMembersItemBand
from ..types import UNSET, Unset

T = TypeVar("T", bound="RollupRealtimeMembersItem")


@_attrs_define
class RollupRealtimeMembersItem:
    """
    Attributes:
        id (str):
        name (str):
        observations (int):
        uptime_pct (float):
        band (RollupRealtimeMembersItemBand):
        configured_kinds (list[str] | Unset):
        median_lag_seconds (int | None | Unset):
        median_coverage_pct (float | None | Unset):
        first_ts (int | None | Unset):
        last_ts (int | None | Unset):
    """

    id: str
    name: str
    observations: int
    uptime_pct: float
    band: RollupRealtimeMembersItemBand
    configured_kinds: list[str] | Unset = UNSET
    median_lag_seconds: int | None | Unset = UNSET
    median_coverage_pct: float | None | Unset = UNSET
    first_ts: int | None | Unset = UNSET
    last_ts: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        observations = self.observations

        uptime_pct = self.uptime_pct

        band = self.band.value

        configured_kinds: list[str] | Unset = UNSET
        if not isinstance(self.configured_kinds, Unset):
            configured_kinds = self.configured_kinds

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

        first_ts: int | None | Unset
        if isinstance(self.first_ts, Unset):
            first_ts = UNSET
        else:
            first_ts = self.first_ts

        last_ts: int | None | Unset
        if isinstance(self.last_ts, Unset):
            last_ts = UNSET
        else:
            last_ts = self.last_ts

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
                "observations": observations,
                "uptime_pct": uptime_pct,
                "band": band,
            }
        )
        if configured_kinds is not UNSET:
            field_dict["configured_kinds"] = configured_kinds
        if median_lag_seconds is not UNSET:
            field_dict["median_lag_seconds"] = median_lag_seconds
        if median_coverage_pct is not UNSET:
            field_dict["median_coverage_pct"] = median_coverage_pct
        if first_ts is not UNSET:
            field_dict["first_ts"] = first_ts
        if last_ts is not UNSET:
            field_dict["last_ts"] = last_ts

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        id = _d.pop("id")

        name = _d.pop("name")

        observations = _d.pop("observations")

        uptime_pct = _d.pop("uptime_pct")

        band = RollupRealtimeMembersItemBand(_d.pop("band"))

        configured_kinds = cast(list[str], _d.pop("configured_kinds", UNSET))

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

        def _parse_first_ts(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        first_ts = _parse_first_ts(_d.pop("first_ts", UNSET))

        def _parse_last_ts(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        last_ts = _parse_last_ts(_d.pop("last_ts", UNSET))

        rollup_realtime_members_item = cls(
            id=id,
            name=name,
            observations=observations,
            uptime_pct=uptime_pct,
            band=band,
            configured_kinds=configured_kinds,
            median_lag_seconds=median_lag_seconds,
            median_coverage_pct=median_coverage_pct,
            first_ts=first_ts,
            last_ts=last_ts,
        )

        return rollup_realtime_members_item
