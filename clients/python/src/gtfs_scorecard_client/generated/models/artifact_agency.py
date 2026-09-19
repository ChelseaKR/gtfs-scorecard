from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="ArtifactAgency")


@_attrs_define
class ArtifactAgency:
    """
    Attributes:
        id (str):
        name (str):
        country (str | Unset): ISO 3166-1 alpha-2 country code; omitted for US agencies so their artifacts stay byte-
            identical. Registry configuration determines which well-formed country codes this deployment activates.
        operating_note (str | Unset): Curator-verified operating status, mainly for long-expired feeds; omitted when
            empty.
        ntd_note (str | Unset): Curator-recorded NTD reporting arrangement (shared feed, waiver); omitted when empty.
        state (str | Unset): Deprecated US-only compatibility name; omitted when unlocated.
        subdivision_code (str | Unset): Primary catalog subdivision as an ISO 3166-2 code; omitted when unknown.
        subdivision_name (str | Unset): Practitioner-facing name of the primary catalog subdivision; omitted when
            unknown.
    """

    id: str
    name: str
    country: str | Unset = UNSET
    operating_note: str | Unset = UNSET
    ntd_note: str | Unset = UNSET
    state: str | Unset = UNSET
    subdivision_code: str | Unset = UNSET
    subdivision_name: str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        country = self.country

        operating_note = self.operating_note

        ntd_note = self.ntd_note

        state = self.state

        subdivision_code = self.subdivision_code

        subdivision_name = self.subdivision_name

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
            }
        )
        if country is not UNSET:
            field_dict["country"] = country
        if operating_note is not UNSET:
            field_dict["operating_note"] = operating_note
        if ntd_note is not UNSET:
            field_dict["ntd_note"] = ntd_note
        if state is not UNSET:
            field_dict["state"] = state
        if subdivision_code is not UNSET:
            field_dict["subdivision_code"] = subdivision_code
        if subdivision_name is not UNSET:
            field_dict["subdivision_name"] = subdivision_name

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        id = _d.pop("id")

        name = _d.pop("name")

        country = _d.pop("country", UNSET)

        operating_note = _d.pop("operating_note", UNSET)

        ntd_note = _d.pop("ntd_note", UNSET)

        state = _d.pop("state", UNSET)

        subdivision_code = _d.pop("subdivision_code", UNSET)

        subdivision_name = _d.pop("subdivision_name", UNSET)

        artifact_agency = cls(
            id=id,
            name=name,
            country=country,
            operating_note=operating_note,
            ntd_note=ntd_note,
            state=state,
            subdivision_code=subdivision_code,
            subdivision_name=subdivision_name,
        )

        return artifact_agency
