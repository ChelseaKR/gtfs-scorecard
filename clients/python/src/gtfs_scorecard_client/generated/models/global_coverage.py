from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.global_coverage_status import GlobalCoverageStatus

if TYPE_CHECKING:
    from ..models.global_coverage_cohort import GlobalCoverageCohort
    from ..models.global_coverage_country import GlobalCoverageCountry
    from ..models.global_coverage_criterion import GlobalCoverageCriterion
    from ..models.global_coverage_exception import GlobalCoverageException
    from ..models.global_coverage_feature_finder import GlobalCoverageFeatureFinder
    from ..models.global_coverage_feed_record import GlobalCoverageFeedRecord
    from ..models.global_coverage_methodology import GlobalCoverageMethodology
    from ..models.global_coverage_scope import GlobalCoverageScope


T = TypeVar("T", bound="GlobalCoverage")


@_attrs_define
class GlobalCoverage:
    """Auditable readiness criteria for the bounded European GTFS Schedule beta. Counts are reviewed feed records, not
    agencies, operators, routes, or all European transit.

        Attributes:
            schema_version (Literal['1.0']):
            license_ (Literal['CC-BY-4.0']):
            attribution (str):
            license_scope (str):
            generated_at (datetime.datetime):
            evaluated_at (datetime.datetime):
            status (GlobalCoverageStatus):
            ready (bool):
            scope (GlobalCoverageScope):
            limitations (list[str]):
            methodology (GlobalCoverageMethodology):
            cohort (GlobalCoverageCohort):
            feature_finder (GlobalCoverageFeatureFinder):
            criteria (list[GlobalCoverageCriterion]):
            countries (list[GlobalCoverageCountry]):
            exceptions (list[GlobalCoverageException]):
            records (list[GlobalCoverageFeedRecord]):
    """

    schema_version: Literal["1.0"]
    license_: Literal["CC-BY-4.0"]
    attribution: str
    license_scope: str
    generated_at: datetime.datetime
    evaluated_at: datetime.datetime
    status: GlobalCoverageStatus
    ready: bool
    scope: GlobalCoverageScope
    limitations: list[str]
    methodology: GlobalCoverageMethodology
    cohort: GlobalCoverageCohort
    feature_finder: GlobalCoverageFeatureFinder
    criteria: list[GlobalCoverageCriterion]
    countries: list[GlobalCoverageCountry]
    exceptions: list[GlobalCoverageException]
    records: list[GlobalCoverageFeedRecord]

    def to_dict(self) -> dict[str, Any]:
        schema_version = self.schema_version

        license_ = self.license_

        attribution = self.attribution

        license_scope = self.license_scope

        generated_at = self.generated_at.isoformat()

        evaluated_at = self.evaluated_at.isoformat()

        status = self.status.value

        ready = self.ready

        scope = self.scope.to_dict()

        limitations = self.limitations

        methodology = self.methodology.to_dict()

        cohort = self.cohort.to_dict()

        feature_finder = self.feature_finder.to_dict()

        criteria = []
        for criteria_item_data in self.criteria:
            criteria_item = criteria_item_data.to_dict()
            criteria.append(criteria_item)

        countries = []
        for countries_item_data in self.countries:
            countries_item = countries_item_data.to_dict()
            countries.append(countries_item)

        exceptions = []
        for exceptions_item_data in self.exceptions:
            exceptions_item = exceptions_item_data.to_dict()
            exceptions.append(exceptions_item)

        records = []
        for records_item_data in self.records:
            records_item = records_item_data.to_dict()
            records.append(records_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "schema_version": schema_version,
                "license": license_,
                "attribution": attribution,
                "license_scope": license_scope,
                "generated_at": generated_at,
                "evaluated_at": evaluated_at,
                "status": status,
                "ready": ready,
                "scope": scope,
                "limitations": limitations,
                "methodology": methodology,
                "cohort": cohort,
                "feature_finder": feature_finder,
                "criteria": criteria,
                "countries": countries,
                "exceptions": exceptions,
                "records": records,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.global_coverage_cohort import (
            GlobalCoverageCohort,
        )
        from ..models.global_coverage_country import (
            GlobalCoverageCountry,
        )
        from ..models.global_coverage_criterion import (
            GlobalCoverageCriterion,
        )
        from ..models.global_coverage_exception import (
            GlobalCoverageException,
        )
        from ..models.global_coverage_feature_finder import (
            GlobalCoverageFeatureFinder,
        )
        from ..models.global_coverage_feed_record import (
            GlobalCoverageFeedRecord,
        )
        from ..models.global_coverage_methodology import (
            GlobalCoverageMethodology,
        )
        from ..models.global_coverage_scope import GlobalCoverageScope

        _d = dict(src_dict)
        schema_version = cast(Literal["1.0"], _d.pop("schema_version"))
        if schema_version != "1.0":
            raise ValueError(
                f"schema_version must match const '1.0', got '{schema_version}'"
            )

        license_ = cast(Literal["CC-BY-4.0"], _d.pop("license"))
        if license_ != "CC-BY-4.0":
            raise ValueError(f"license must match const 'CC-BY-4.0', got '{license_}'")

        attribution = _d.pop("attribution")

        license_scope = _d.pop("license_scope")

        generated_at = datetime.datetime.fromisoformat(_d.pop("generated_at"))

        evaluated_at = datetime.datetime.fromisoformat(_d.pop("evaluated_at"))

        status = GlobalCoverageStatus(_d.pop("status"))

        ready = _d.pop("ready")

        scope = GlobalCoverageScope.from_dict(_d.pop("scope"))

        limitations = cast(list[str], _d.pop("limitations"))

        methodology = GlobalCoverageMethodology.from_dict(_d.pop("methodology"))

        cohort = GlobalCoverageCohort.from_dict(_d.pop("cohort"))

        feature_finder = GlobalCoverageFeatureFinder.from_dict(_d.pop("feature_finder"))

        criteria = []
        _criteria = _d.pop("criteria")
        for criteria_item_data in _criteria:
            criteria_item = GlobalCoverageCriterion.from_dict(criteria_item_data)

            criteria.append(criteria_item)

        countries = []
        _countries = _d.pop("countries")
        for countries_item_data in _countries:
            countries_item = GlobalCoverageCountry.from_dict(countries_item_data)

            countries.append(countries_item)

        exceptions = []
        _exceptions = _d.pop("exceptions")
        for exceptions_item_data in _exceptions:
            exceptions_item = GlobalCoverageException.from_dict(exceptions_item_data)

            exceptions.append(exceptions_item)

        records = []
        _records = _d.pop("records")
        for records_item_data in _records:
            records_item = GlobalCoverageFeedRecord.from_dict(records_item_data)

            records.append(records_item)

        global_coverage = cls(
            schema_version=schema_version,
            license_=license_,
            attribution=attribution,
            license_scope=license_scope,
            generated_at=generated_at,
            evaluated_at=evaluated_at,
            status=status,
            ready=ready,
            scope=scope,
            limitations=limitations,
            methodology=methodology,
            cohort=cohort,
            feature_finder=feature_finder,
            criteria=criteria,
            countries=countries,
            exceptions=exceptions,
            records=records,
        )

        return global_coverage
