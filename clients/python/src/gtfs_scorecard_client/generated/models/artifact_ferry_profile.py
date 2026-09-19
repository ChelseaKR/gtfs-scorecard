from __future__ import annotations

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

if TYPE_CHECKING:
    from ..models.artifact_enum_coverage import ArtifactEnumCoverage
    from ..models.artifact_ferry_profile_accessibility import (
        ArtifactFerryProfileAccessibility,
    )
    from ..models.artifact_ferry_profile_fares import ArtifactFerryProfileFares
    from ..models.artifact_ferry_profile_realtime import ArtifactFerryProfileRealtime
    from ..models.artifact_ferry_profile_stop_access import (
        ArtifactFerryProfileStopAccess,
    )
    from ..models.artifact_ferry_profile_terminal_hierarchy import (
        ArtifactFerryProfileTerminalHierarchy,
    )


T = TypeVar("T", bound="ArtifactFerryProfile")


@_attrs_define
class ArtifactFerryProfile:
    """Descriptive, ungraded capability measurements for the ferry routes and trips in a feed. Fare and realtime facts are
    explicitly whole-feed scope.

        Attributes:
            measured (Literal[True]):
            graded (Literal[False]):
            scope (Literal['ferry_routes_and_trips']):
            route_count (int):
            trip_count (int):
            terminal_hierarchy (ArtifactFerryProfileTerminalHierarchy):
            stop_access (ArtifactFerryProfileStopAccess):
            accessibility (ArtifactFerryProfileAccessibility):
            bikes (ArtifactEnumCoverage):
            cars (ArtifactEnumCoverage):
            fares (ArtifactFerryProfileFares):
            realtime (ArtifactFerryProfileRealtime):
    """

    measured: Literal[True]
    graded: Literal[False]
    scope: Literal["ferry_routes_and_trips"]
    route_count: int
    trip_count: int
    terminal_hierarchy: ArtifactFerryProfileTerminalHierarchy
    stop_access: ArtifactFerryProfileStopAccess
    accessibility: ArtifactFerryProfileAccessibility
    bikes: ArtifactEnumCoverage
    cars: ArtifactEnumCoverage
    fares: ArtifactFerryProfileFares
    realtime: ArtifactFerryProfileRealtime

    def to_dict(self) -> dict[str, Any]:
        measured = self.measured

        graded = self.graded

        scope = self.scope

        route_count = self.route_count

        trip_count = self.trip_count

        terminal_hierarchy = self.terminal_hierarchy.to_dict()

        stop_access = self.stop_access.to_dict()

        accessibility = self.accessibility.to_dict()

        bikes = self.bikes.to_dict()

        cars = self.cars.to_dict()

        fares = self.fares.to_dict()

        realtime = self.realtime.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "measured": measured,
                "graded": graded,
                "scope": scope,
                "route_count": route_count,
                "trip_count": trip_count,
                "terminal_hierarchy": terminal_hierarchy,
                "stop_access": stop_access,
                "accessibility": accessibility,
                "bikes": bikes,
                "cars": cars,
                "fares": fares,
                "realtime": realtime,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.artifact_enum_coverage import (
            ArtifactEnumCoverage,
        )
        from ..models.artifact_ferry_profile_accessibility import (
            ArtifactFerryProfileAccessibility,
        )
        from ..models.artifact_ferry_profile_fares import (
            ArtifactFerryProfileFares,
        )
        from ..models.artifact_ferry_profile_realtime import (
            ArtifactFerryProfileRealtime,
        )
        from ..models.artifact_ferry_profile_stop_access import (
            ArtifactFerryProfileStopAccess,
        )
        from ..models.artifact_ferry_profile_terminal_hierarchy import (
            ArtifactFerryProfileTerminalHierarchy,
        )

        _d = dict(src_dict)
        measured = cast(Literal[True], _d.pop("measured"))
        if measured != True:
            raise ValueError(f"measured must match const True, got '{measured}'")

        graded = cast(Literal[False], _d.pop("graded"))
        if graded != False:
            raise ValueError(f"graded must match const False, got '{graded}'")

        scope = cast(Literal["ferry_routes_and_trips"], _d.pop("scope"))
        if scope != "ferry_routes_and_trips":
            raise ValueError(
                f"scope must match const 'ferry_routes_and_trips', got '{scope}'"
            )

        route_count = _d.pop("route_count")

        trip_count = _d.pop("trip_count")

        terminal_hierarchy = ArtifactFerryProfileTerminalHierarchy.from_dict(
            _d.pop("terminal_hierarchy")
        )

        stop_access = ArtifactFerryProfileStopAccess.from_dict(_d.pop("stop_access"))

        accessibility = ArtifactFerryProfileAccessibility.from_dict(
            _d.pop("accessibility")
        )

        bikes = ArtifactEnumCoverage.from_dict(_d.pop("bikes"))

        cars = ArtifactEnumCoverage.from_dict(_d.pop("cars"))

        fares = ArtifactFerryProfileFares.from_dict(_d.pop("fares"))

        realtime = ArtifactFerryProfileRealtime.from_dict(_d.pop("realtime"))

        artifact_ferry_profile = cls(
            measured=measured,
            graded=graded,
            scope=scope,
            route_count=route_count,
            trip_count=trip_count,
            terminal_hierarchy=terminal_hierarchy,
            stop_access=stop_access,
            accessibility=accessibility,
            bikes=bikes,
            cars=cars,
            fares=fares,
            realtime=realtime,
        )

        return artifact_ferry_profile
