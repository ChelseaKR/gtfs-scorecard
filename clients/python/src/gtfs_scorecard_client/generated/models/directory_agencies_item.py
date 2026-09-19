from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.directory_agencies_item_google_gate import DirectoryAgenciesItemGoogleGate
from ..models.directory_agencies_item_grade import DirectoryAgenciesItemGrade
from ..models.directory_agencies_item_ntd_ready_type_1 import (
    DirectoryAgenciesItemNtdReadyType1,
)
from ..models.directory_agencies_item_ntd_ready_type_2_type_1 import (
    DirectoryAgenciesItemNtdReadyType2Type1,
)
from ..models.directory_agencies_item_ntd_ready_type_3_type_1 import (
    DirectoryAgenciesItemNtdReadyType3Type1,
)
from ..models.directory_agencies_item_reader_archive_profile import (
    DirectoryAgenciesItemReaderArchiveProfile,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="DirectoryAgenciesItem")


@_attrs_define
class DirectoryAgenciesItem:
    """
    Attributes:
        id (str):
        name (str):
        grade (DirectoryAgenciesItemGrade):
        score (float):
        state (str | Unset):
        subdivision_code (str | Unset):
        subdivision_name (str | Unset):
        comparison_eligible (bool | Unset): Whether this row belongs to the comparison cohort documented in
            summary.comparison.
        correctness (float | None | Unset):
        freshness (float | None | Unset):
        completeness (float | None | Unset):
        realtime (float | None | Unset):
        size_tier (str | Unset):
        national_percentile (int | None | Unset): Deprecated compatibility field. Current payloads publish null;
            integers remain valid only so historical 1.x documents still conform.
        peer_percentile (int | None | Unset): Deprecated compatibility field. Current payloads publish null; integers
            remain valid only so historical 1.x documents still conform.
        expiry_status (str | Unset):
        days_until_expiry (int | None | Unset):
        mdb_id (str | Unset):
        ntd_ready (DirectoryAgenciesItemNtdReadyType1 | DirectoryAgenciesItemNtdReadyType2Type1 |
            DirectoryAgenciesItemNtdReadyType3Type1 | None | Unset): NTD GTFS certification readiness heads-up; null for
            non-US agencies (see catalog schema).
        google_gate (DirectoryAgenciesItemGoogleGate | Unset): Google/Apple Maps four-week coverage bar (see catalog
            schema).
        stops (int | None | Unset): Boardable stop count from stops.txt.
        feed_url (None | str | Unset): The static GTFS URL that was scored.
        feed_sha256 (None | str | Unset): SHA-256 of the exact feed bytes scored.
        reader_archive_profile (DirectoryAgenciesItemReaderArchiveProfile | Unset):
        retrieved_at (None | str | Unset): When the feed was fetched and scored (ISO 8601).
        snapshot_date (None | str | Unset): The scorecard's snapshot date (YYYY-MM-DD).
        rubric_version (None | str | Unset): Rubric version that produced this grade.
        scoring_profile_id (None | str | Unset): Stable scoring-profile identifier that produced this grade.
        scoring_profile_rubric_version (None | str | Unset): Rubric version declared by the scoring profile.
        validator_version (None | str | Unset): MobilityData gtfs-validator release used.
        scorecard_url (None | str | Unset): Canonical scorecard page for this agency.
        top_fix (None | str | Unset): The highest-leverage plain-language fix, when any.
        country (str | Unset): ISO 3166-1 alpha-2 country code. Registry configuration determines which well-formed
            country codes this deployment activates.
        modes_measured (bool | Unset): Whether the route-mode contract was measured for this feed.
        primary_mode (None | str | Unset):
        modes (list[str] | None | Unset):
        has_ferry (bool | None | Unset):
        ferry_only (bool | None | Unset):
    """

    id: str
    name: str
    grade: DirectoryAgenciesItemGrade
    score: float
    state: str | Unset = UNSET
    subdivision_code: str | Unset = UNSET
    subdivision_name: str | Unset = UNSET
    comparison_eligible: bool | Unset = UNSET
    correctness: float | None | Unset = UNSET
    freshness: float | None | Unset = UNSET
    completeness: float | None | Unset = UNSET
    realtime: float | None | Unset = UNSET
    size_tier: str | Unset = UNSET
    national_percentile: int | None | Unset = UNSET
    peer_percentile: int | None | Unset = UNSET
    expiry_status: str | Unset = UNSET
    days_until_expiry: int | None | Unset = UNSET
    mdb_id: str | Unset = UNSET
    ntd_ready: (
        DirectoryAgenciesItemNtdReadyType1
        | DirectoryAgenciesItemNtdReadyType2Type1
        | DirectoryAgenciesItemNtdReadyType3Type1
        | None
        | Unset
    ) = UNSET
    google_gate: DirectoryAgenciesItemGoogleGate | Unset = UNSET
    stops: int | None | Unset = UNSET
    feed_url: None | str | Unset = UNSET
    feed_sha256: None | str | Unset = UNSET
    reader_archive_profile: DirectoryAgenciesItemReaderArchiveProfile | Unset = UNSET
    retrieved_at: None | str | Unset = UNSET
    snapshot_date: None | str | Unset = UNSET
    rubric_version: None | str | Unset = UNSET
    scoring_profile_id: None | str | Unset = UNSET
    scoring_profile_rubric_version: None | str | Unset = UNSET
    validator_version: None | str | Unset = UNSET
    scorecard_url: None | str | Unset = UNSET
    top_fix: None | str | Unset = UNSET
    country: str | Unset = UNSET
    modes_measured: bool | Unset = UNSET
    primary_mode: None | str | Unset = UNSET
    modes: list[str] | None | Unset = UNSET
    has_ferry: bool | None | Unset = UNSET
    ferry_only: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        grade = self.grade.value

        score = self.score

        state = self.state

        subdivision_code = self.subdivision_code

        subdivision_name = self.subdivision_name

        comparison_eligible = self.comparison_eligible

        correctness: float | None | Unset
        if isinstance(self.correctness, Unset):
            correctness = UNSET
        else:
            correctness = self.correctness

        freshness: float | None | Unset
        if isinstance(self.freshness, Unset):
            freshness = UNSET
        else:
            freshness = self.freshness

        completeness: float | None | Unset
        if isinstance(self.completeness, Unset):
            completeness = UNSET
        else:
            completeness = self.completeness

        realtime: float | None | Unset
        if isinstance(self.realtime, Unset):
            realtime = UNSET
        else:
            realtime = self.realtime

        size_tier = self.size_tier

        national_percentile: int | None | Unset
        if isinstance(self.national_percentile, Unset):
            national_percentile = UNSET
        else:
            national_percentile = self.national_percentile

        peer_percentile: int | None | Unset
        if isinstance(self.peer_percentile, Unset):
            peer_percentile = UNSET
        else:
            peer_percentile = self.peer_percentile

        expiry_status = self.expiry_status

        days_until_expiry: int | None | Unset
        if isinstance(self.days_until_expiry, Unset):
            days_until_expiry = UNSET
        else:
            days_until_expiry = self.days_until_expiry

        mdb_id = self.mdb_id

        ntd_ready: None | str | Unset
        if isinstance(self.ntd_ready, Unset):
            ntd_ready = UNSET
        elif (
            isinstance(self.ntd_ready, DirectoryAgenciesItemNtdReadyType1)
            or isinstance(self.ntd_ready, DirectoryAgenciesItemNtdReadyType2Type1)
            or isinstance(self.ntd_ready, DirectoryAgenciesItemNtdReadyType3Type1)
        ):
            ntd_ready = self.ntd_ready.value
        else:
            ntd_ready = self.ntd_ready

        google_gate: str | Unset = UNSET
        if not isinstance(self.google_gate, Unset):
            google_gate = self.google_gate.value

        stops: int | None | Unset
        if isinstance(self.stops, Unset):
            stops = UNSET
        else:
            stops = self.stops

        feed_url: None | str | Unset
        if isinstance(self.feed_url, Unset):
            feed_url = UNSET
        else:
            feed_url = self.feed_url

        feed_sha256: None | str | Unset
        if isinstance(self.feed_sha256, Unset):
            feed_sha256 = UNSET
        else:
            feed_sha256 = self.feed_sha256

        reader_archive_profile: str | Unset = UNSET
        if not isinstance(self.reader_archive_profile, Unset):
            reader_archive_profile = self.reader_archive_profile.value

        retrieved_at: None | str | Unset
        if isinstance(self.retrieved_at, Unset):
            retrieved_at = UNSET
        else:
            retrieved_at = self.retrieved_at

        snapshot_date: None | str | Unset
        if isinstance(self.snapshot_date, Unset):
            snapshot_date = UNSET
        else:
            snapshot_date = self.snapshot_date

        rubric_version: None | str | Unset
        if isinstance(self.rubric_version, Unset):
            rubric_version = UNSET
        else:
            rubric_version = self.rubric_version

        scoring_profile_id: None | str | Unset
        if isinstance(self.scoring_profile_id, Unset):
            scoring_profile_id = UNSET
        else:
            scoring_profile_id = self.scoring_profile_id

        scoring_profile_rubric_version: None | str | Unset
        if isinstance(self.scoring_profile_rubric_version, Unset):
            scoring_profile_rubric_version = UNSET
        else:
            scoring_profile_rubric_version = self.scoring_profile_rubric_version

        validator_version: None | str | Unset
        if isinstance(self.validator_version, Unset):
            validator_version = UNSET
        else:
            validator_version = self.validator_version

        scorecard_url: None | str | Unset
        if isinstance(self.scorecard_url, Unset):
            scorecard_url = UNSET
        else:
            scorecard_url = self.scorecard_url

        top_fix: None | str | Unset
        if isinstance(self.top_fix, Unset):
            top_fix = UNSET
        else:
            top_fix = self.top_fix

        country = self.country

        modes_measured = self.modes_measured

        primary_mode: None | str | Unset
        if isinstance(self.primary_mode, Unset):
            primary_mode = UNSET
        else:
            primary_mode = self.primary_mode

        modes: list[str] | None | Unset
        if isinstance(self.modes, Unset):
            modes = UNSET
        elif isinstance(self.modes, list):
            modes = self.modes

        else:
            modes = self.modes

        has_ferry: bool | None | Unset
        if isinstance(self.has_ferry, Unset):
            has_ferry = UNSET
        else:
            has_ferry = self.has_ferry

        ferry_only: bool | None | Unset
        if isinstance(self.ferry_only, Unset):
            ferry_only = UNSET
        else:
            ferry_only = self.ferry_only

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "grade": grade,
                "score": score,
            }
        )
        if state is not UNSET:
            field_dict["state"] = state
        if subdivision_code is not UNSET:
            field_dict["subdivision_code"] = subdivision_code
        if subdivision_name is not UNSET:
            field_dict["subdivision_name"] = subdivision_name
        if comparison_eligible is not UNSET:
            field_dict["comparison_eligible"] = comparison_eligible
        if correctness is not UNSET:
            field_dict["correctness"] = correctness
        if freshness is not UNSET:
            field_dict["freshness"] = freshness
        if completeness is not UNSET:
            field_dict["completeness"] = completeness
        if realtime is not UNSET:
            field_dict["realtime"] = realtime
        if size_tier is not UNSET:
            field_dict["size_tier"] = size_tier
        if national_percentile is not UNSET:
            field_dict["national_percentile"] = national_percentile
        if peer_percentile is not UNSET:
            field_dict["peer_percentile"] = peer_percentile
        if expiry_status is not UNSET:
            field_dict["expiry_status"] = expiry_status
        if days_until_expiry is not UNSET:
            field_dict["days_until_expiry"] = days_until_expiry
        if mdb_id is not UNSET:
            field_dict["mdb_id"] = mdb_id
        if ntd_ready is not UNSET:
            field_dict["ntd_ready"] = ntd_ready
        if google_gate is not UNSET:
            field_dict["google_gate"] = google_gate
        if stops is not UNSET:
            field_dict["stops"] = stops
        if feed_url is not UNSET:
            field_dict["feed_url"] = feed_url
        if feed_sha256 is not UNSET:
            field_dict["feed_sha256"] = feed_sha256
        if reader_archive_profile is not UNSET:
            field_dict["reader_archive_profile"] = reader_archive_profile
        if retrieved_at is not UNSET:
            field_dict["retrieved_at"] = retrieved_at
        if snapshot_date is not UNSET:
            field_dict["snapshot_date"] = snapshot_date
        if rubric_version is not UNSET:
            field_dict["rubric_version"] = rubric_version
        if scoring_profile_id is not UNSET:
            field_dict["scoring_profile_id"] = scoring_profile_id
        if scoring_profile_rubric_version is not UNSET:
            field_dict["scoring_profile_rubric_version"] = (
                scoring_profile_rubric_version
            )
        if validator_version is not UNSET:
            field_dict["validator_version"] = validator_version
        if scorecard_url is not UNSET:
            field_dict["scorecard_url"] = scorecard_url
        if top_fix is not UNSET:
            field_dict["top_fix"] = top_fix
        if country is not UNSET:
            field_dict["country"] = country
        if modes_measured is not UNSET:
            field_dict["modes_measured"] = modes_measured
        if primary_mode is not UNSET:
            field_dict["primary_mode"] = primary_mode
        if modes is not UNSET:
            field_dict["modes"] = modes
        if has_ferry is not UNSET:
            field_dict["has_ferry"] = has_ferry
        if ferry_only is not UNSET:
            field_dict["ferry_only"] = ferry_only

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        id = _d.pop("id")

        name = _d.pop("name")

        grade = DirectoryAgenciesItemGrade(_d.pop("grade"))

        score = _d.pop("score")

        state = _d.pop("state", UNSET)

        subdivision_code = _d.pop("subdivision_code", UNSET)

        subdivision_name = _d.pop("subdivision_name", UNSET)

        comparison_eligible = _d.pop("comparison_eligible", UNSET)

        def _parse_correctness(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        correctness = _parse_correctness(_d.pop("correctness", UNSET))

        def _parse_freshness(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        freshness = _parse_freshness(_d.pop("freshness", UNSET))

        def _parse_completeness(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        completeness = _parse_completeness(_d.pop("completeness", UNSET))

        def _parse_realtime(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        realtime = _parse_realtime(_d.pop("realtime", UNSET))

        size_tier = _d.pop("size_tier", UNSET)

        def _parse_national_percentile(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        national_percentile = _parse_national_percentile(
            _d.pop("national_percentile", UNSET)
        )

        def _parse_peer_percentile(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        peer_percentile = _parse_peer_percentile(_d.pop("peer_percentile", UNSET))

        expiry_status = _d.pop("expiry_status", UNSET)

        def _parse_days_until_expiry(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        days_until_expiry = _parse_days_until_expiry(_d.pop("days_until_expiry", UNSET))

        mdb_id = _d.pop("mdb_id", UNSET)

        def _parse_ntd_ready(
            data: object,
        ) -> (
            DirectoryAgenciesItemNtdReadyType1
            | DirectoryAgenciesItemNtdReadyType2Type1
            | DirectoryAgenciesItemNtdReadyType3Type1
            | None
            | Unset
        ):
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ntd_ready_type_1 = DirectoryAgenciesItemNtdReadyType1(data)

                return ntd_ready_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ntd_ready_type_2_type_1 = DirectoryAgenciesItemNtdReadyType2Type1(data)

                return ntd_ready_type_2_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ntd_ready_type_3_type_1 = DirectoryAgenciesItemNtdReadyType3Type1(data)

                return ntd_ready_type_3_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                DirectoryAgenciesItemNtdReadyType1
                | DirectoryAgenciesItemNtdReadyType2Type1
                | DirectoryAgenciesItemNtdReadyType3Type1
                | None
                | Unset,
                data,
            )

        ntd_ready = _parse_ntd_ready(_d.pop("ntd_ready", UNSET))

        _google_gate = _d.pop("google_gate", UNSET)
        google_gate: DirectoryAgenciesItemGoogleGate | Unset
        if isinstance(_google_gate, Unset):
            google_gate = UNSET
        else:
            google_gate = DirectoryAgenciesItemGoogleGate(_google_gate)

        def _parse_stops(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        stops = _parse_stops(_d.pop("stops", UNSET))

        def _parse_feed_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        feed_url = _parse_feed_url(_d.pop("feed_url", UNSET))

        def _parse_feed_sha256(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        feed_sha256 = _parse_feed_sha256(_d.pop("feed_sha256", UNSET))

        _reader_archive_profile = _d.pop("reader_archive_profile", UNSET)
        reader_archive_profile: DirectoryAgenciesItemReaderArchiveProfile | Unset
        if isinstance(_reader_archive_profile, Unset):
            reader_archive_profile = UNSET
        else:
            reader_archive_profile = DirectoryAgenciesItemReaderArchiveProfile(
                _reader_archive_profile
            )

        def _parse_retrieved_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        retrieved_at = _parse_retrieved_at(_d.pop("retrieved_at", UNSET))

        def _parse_snapshot_date(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        snapshot_date = _parse_snapshot_date(_d.pop("snapshot_date", UNSET))

        def _parse_rubric_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rubric_version = _parse_rubric_version(_d.pop("rubric_version", UNSET))

        def _parse_scoring_profile_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        scoring_profile_id = _parse_scoring_profile_id(
            _d.pop("scoring_profile_id", UNSET)
        )

        def _parse_scoring_profile_rubric_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        scoring_profile_rubric_version = _parse_scoring_profile_rubric_version(
            _d.pop("scoring_profile_rubric_version", UNSET)
        )

        def _parse_validator_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        validator_version = _parse_validator_version(_d.pop("validator_version", UNSET))

        def _parse_scorecard_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        scorecard_url = _parse_scorecard_url(_d.pop("scorecard_url", UNSET))

        def _parse_top_fix(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        top_fix = _parse_top_fix(_d.pop("top_fix", UNSET))

        country = _d.pop("country", UNSET)

        modes_measured = _d.pop("modes_measured", UNSET)

        def _parse_primary_mode(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        primary_mode = _parse_primary_mode(_d.pop("primary_mode", UNSET))

        def _parse_modes(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                modes_type_0 = cast(list[str], data)

                return modes_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        modes = _parse_modes(_d.pop("modes", UNSET))

        def _parse_has_ferry(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        has_ferry = _parse_has_ferry(_d.pop("has_ferry", UNSET))

        def _parse_ferry_only(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        ferry_only = _parse_ferry_only(_d.pop("ferry_only", UNSET))

        directory_agencies_item = cls(
            id=id,
            name=name,
            grade=grade,
            score=score,
            state=state,
            subdivision_code=subdivision_code,
            subdivision_name=subdivision_name,
            comparison_eligible=comparison_eligible,
            correctness=correctness,
            freshness=freshness,
            completeness=completeness,
            realtime=realtime,
            size_tier=size_tier,
            national_percentile=national_percentile,
            peer_percentile=peer_percentile,
            expiry_status=expiry_status,
            days_until_expiry=days_until_expiry,
            mdb_id=mdb_id,
            ntd_ready=ntd_ready,
            google_gate=google_gate,
            stops=stops,
            feed_url=feed_url,
            feed_sha256=feed_sha256,
            reader_archive_profile=reader_archive_profile,
            retrieved_at=retrieved_at,
            snapshot_date=snapshot_date,
            rubric_version=rubric_version,
            scoring_profile_id=scoring_profile_id,
            scoring_profile_rubric_version=scoring_profile_rubric_version,
            validator_version=validator_version,
            scorecard_url=scorecard_url,
            top_fix=top_fix,
            country=country,
            modes_measured=modes_measured,
            primary_mode=primary_mode,
            modes=modes,
            has_ferry=has_ferry,
            ferry_only=ferry_only,
        )

        directory_agencies_item.additional_properties = _d
        return directory_agencies_item

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
