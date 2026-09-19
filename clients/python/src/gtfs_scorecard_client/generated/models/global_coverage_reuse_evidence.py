from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.global_coverage_reuse_evidence_source_kind import (
    GlobalCoverageReuseEvidenceSourceKind,
)

T = TypeVar("T", bound="GlobalCoverageReuseEvidence")


@_attrs_define
class GlobalCoverageReuseEvidence:
    """
    Attributes:
        decision (Literal['approved']):
        source_kind (GlobalCoverageReuseEvidenceSourceKind):
        provider_source_url (str):
        terms_url (str):
        scope (list[Literal['gtfs_schedule']]):
        attribution (str):
        reviewed_by (str):
        reviewed_on (datetime.date):
        identity_reviewed (bool):
    """

    decision: Literal["approved"]
    source_kind: GlobalCoverageReuseEvidenceSourceKind
    provider_source_url: str
    terms_url: str
    scope: list[Literal["gtfs_schedule"]]
    attribution: str
    reviewed_by: str
    reviewed_on: datetime.date
    identity_reviewed: bool

    def to_dict(self) -> dict[str, Any]:
        decision = self.decision

        source_kind = self.source_kind.value

        provider_source_url = self.provider_source_url

        terms_url = self.terms_url

        scope = self.scope

        attribution = self.attribution

        reviewed_by = self.reviewed_by

        reviewed_on = self.reviewed_on.isoformat()

        identity_reviewed = self.identity_reviewed

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "decision": decision,
                "source_kind": source_kind,
                "provider_source_url": provider_source_url,
                "terms_url": terms_url,
                "scope": scope,
                "attribution": attribution,
                "reviewed_by": reviewed_by,
                "reviewed_on": reviewed_on,
                "identity_reviewed": identity_reviewed,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        decision = cast(Literal["approved"], _d.pop("decision"))
        if decision != "approved":
            raise ValueError(f"decision must match const 'approved', got '{decision}'")

        source_kind = GlobalCoverageReuseEvidenceSourceKind(_d.pop("source_kind"))

        provider_source_url = _d.pop("provider_source_url")

        terms_url = _d.pop("terms_url")

        scope = []
        _scope = _d.pop("scope")
        for scope_item_data in _scope:
            scope_item = cast(Literal["gtfs_schedule"], scope_item_data)
            if scope_item != "gtfs_schedule":
                raise ValueError(
                    f"scope_item must match const 'gtfs_schedule', got '{scope_item}'"
                )
            scope.append(scope_item)

        attribution = _d.pop("attribution")

        reviewed_by = _d.pop("reviewed_by")

        reviewed_on = datetime.date.fromisoformat(_d.pop("reviewed_on"))

        identity_reviewed = _d.pop("identity_reviewed")

        global_coverage_reuse_evidence = cls(
            decision=decision,
            source_kind=source_kind,
            provider_source_url=provider_source_url,
            terms_url=terms_url,
            scope=scope,
            attribution=attribution,
            reviewed_by=reviewed_by,
            reviewed_on=reviewed_on,
            identity_reviewed=identity_reviewed,
        )

        return global_coverage_reuse_evidence
