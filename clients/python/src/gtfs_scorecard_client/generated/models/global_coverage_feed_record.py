from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.global_coverage_europe_country_code import GlobalCoverageEuropeCountryCode
from ..models.global_coverage_feed_record_freshness_status import (
    GlobalCoverageFeedRecordFreshnessStatus,
)

if TYPE_CHECKING:
    from ..models.global_coverage_reuse_evidence import GlobalCoverageReuseEvidence


T = TypeVar("T", bound="GlobalCoverageFeedRecord")


@_attrs_define
class GlobalCoverageFeedRecord:
    """
    Attributes:
        id (str):
        name (str):
        organization_id (None | str):
        country (GlobalCoverageEuropeCountryCode):
        subdivision_code (str):
        subdivision_name (str):
        feed_url (str):
        scorecard_url (None | str):
        retrieved_at (None | str): Raw published timestamp. Malformed values remain visible and are identified by
            freshness_status.
        fresh (bool):
        freshness_status (GlobalCoverageFeedRecordFreshnessStatus):
        feature_record_present (bool):
        translations_measured (bool):
        portable_location_valid (bool):
        identity_reviewed (bool):
        reuse_evidence (GlobalCoverageReuseEvidence):
    """

    id: str
    name: str
    organization_id: None | str
    country: GlobalCoverageEuropeCountryCode
    subdivision_code: str
    subdivision_name: str
    feed_url: str
    scorecard_url: None | str
    retrieved_at: None | str
    fresh: bool
    freshness_status: GlobalCoverageFeedRecordFreshnessStatus
    feature_record_present: bool
    translations_measured: bool
    portable_location_valid: bool
    identity_reviewed: bool
    reuse_evidence: GlobalCoverageReuseEvidence

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        organization_id: None | str
        organization_id = self.organization_id

        country = self.country.value

        subdivision_code = self.subdivision_code

        subdivision_name = self.subdivision_name

        feed_url = self.feed_url

        scorecard_url: None | str
        scorecard_url = self.scorecard_url

        retrieved_at: None | str
        retrieved_at = self.retrieved_at

        fresh = self.fresh

        freshness_status = self.freshness_status.value

        feature_record_present = self.feature_record_present

        translations_measured = self.translations_measured

        portable_location_valid = self.portable_location_valid

        identity_reviewed = self.identity_reviewed

        reuse_evidence = self.reuse_evidence.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
                "organization_id": organization_id,
                "country": country,
                "subdivision_code": subdivision_code,
                "subdivision_name": subdivision_name,
                "feed_url": feed_url,
                "scorecard_url": scorecard_url,
                "retrieved_at": retrieved_at,
                "fresh": fresh,
                "freshness_status": freshness_status,
                "feature_record_present": feature_record_present,
                "translations_measured": translations_measured,
                "portable_location_valid": portable_location_valid,
                "identity_reviewed": identity_reviewed,
                "reuse_evidence": reuse_evidence,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.global_coverage_reuse_evidence import (
            GlobalCoverageReuseEvidence,
        )

        _d = dict(src_dict)
        id = _d.pop("id")

        name = _d.pop("name")

        def _parse_organization_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        organization_id = _parse_organization_id(_d.pop("organization_id"))

        country = GlobalCoverageEuropeCountryCode(_d.pop("country"))

        subdivision_code = _d.pop("subdivision_code")

        subdivision_name = _d.pop("subdivision_name")

        feed_url = _d.pop("feed_url")

        def _parse_scorecard_url(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        scorecard_url = _parse_scorecard_url(_d.pop("scorecard_url"))

        def _parse_retrieved_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        retrieved_at = _parse_retrieved_at(_d.pop("retrieved_at"))

        fresh = _d.pop("fresh")

        freshness_status = GlobalCoverageFeedRecordFreshnessStatus(
            _d.pop("freshness_status")
        )

        feature_record_present = _d.pop("feature_record_present")

        translations_measured = _d.pop("translations_measured")

        portable_location_valid = _d.pop("portable_location_valid")

        identity_reviewed = _d.pop("identity_reviewed")

        reuse_evidence = GlobalCoverageReuseEvidence.from_dict(_d.pop("reuse_evidence"))

        global_coverage_feed_record = cls(
            id=id,
            name=name,
            organization_id=organization_id,
            country=country,
            subdivision_code=subdivision_code,
            subdivision_name=subdivision_name,
            feed_url=feed_url,
            scorecard_url=scorecard_url,
            retrieved_at=retrieved_at,
            fresh=fresh,
            freshness_status=freshness_status,
            feature_record_present=feature_record_present,
            translations_measured=translations_measured,
            portable_location_valid=portable_location_valid,
            identity_reviewed=identity_reviewed,
            reuse_evidence=reuse_evidence,
        )

        return global_coverage_feed_record
