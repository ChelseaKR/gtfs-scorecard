"""Detect station pathways and levels, and the step-free routes inside a station.

GTFS pathways and levels describe how a rider moves through a station: the
walkways, stairs, escalators, elevators, and fare gates connecting entrances,
platforms, and levels. For a multi-level station or a shared hub this is how a
trip planner routes someone inside, and how a wheelchair user learns whether a
step-free (elevator) route exists.

This is relevant only to feeds that model stations. A flat stop-only feed, which
is most small and rural agencies, is complete as is and is never flagged. In this
first slice the findings do not change the grade (ADR 0009); the gtfs-validator
covers the structural validity of the pathways graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gtfs import read_tables
from .metrics import Finding

# pathway_mode 5 is an elevator: the standard signal for a step-free route.
_ELEVATOR_MODE = "5"


@dataclass(frozen=True)
class PathwaysProfile:
    """What the scorecard knows about a feed's station navigation data."""

    has_stations: bool  # any stop with location_type 1
    has_entrances: bool  # any stop with location_type 2
    has_pathways: bool
    has_levels: bool
    has_step_free: bool  # at least one elevator pathway
    pathway_count: int

    @property
    def models_stations(self) -> bool:
        return self.has_stations or self.has_entrances

    def to_details(self) -> dict[str, Any]:
        return {
            "has_stations": self.has_stations,
            "has_entrances": self.has_entrances,
            "has_pathways": self.has_pathways,
            "has_levels": self.has_levels,
            "has_step_free": self.has_step_free,
            "pathway_count": self.pathway_count,
        }


def detect_pathways(gtfs_zip_path: str, stops: list[dict[str, str]]) -> PathwaysProfile:
    """Detect station modeling and pathways. ``stops`` is passed in (already read
    by the completeness category) so the stops table is not read twice."""
    tables = read_tables(gtfs_zip_path, ["pathways.txt", "levels.txt"])
    pathways = tables["pathways.txt"]
    location_types = {row.get("location_type", "").strip() for row in stops}
    step_free = any(row.get("pathway_mode", "").strip() == _ELEVATOR_MODE for row in pathways)
    return PathwaysProfile(
        has_stations="1" in location_types,
        has_entrances="2" in location_types,
        has_pathways=bool(pathways),
        has_levels=bool(tables["levels.txt"]),
        has_step_free=step_free,
        pathway_count=len(pathways),
    )


def pathways_findings(profile: PathwaysProfile) -> list[Finding]:
    """Findings for station navigation, framed as fixes. Zero-deduction in this
    first slice (ADR 0009). Relevant only when the feed models stations; a flat
    stop-only feed gets nothing."""
    if not profile.models_stations:
        return []
    if not profile.has_pathways:
        return [
            Finding(
                code="scorecard_station_no_pathways",
                severity="WARNING",
                count=1,
                what="This feed models stations or entrances but has no pathways.txt.",
                why="Trip planners can't guide riders through the station, and there "
                "is no step-free route information for wheelchair users.",
                fix="Add pathways.txt to link entrances, platforms, and elevators. "
                "Give each one a level.",
                effort="Worth it for multi-level or large stations; flat stops don't need it.",
                deduction=0.0,
            )
        ]
    detail = (
        "It includes step-free routes with an elevator."
        if profile.has_step_free
        else "No elevator route is described."
    )
    return [
        Finding(
            code="scorecard_station_pathways",
            severity="INFO",
            count=profile.pathway_count,
            what=f"This feed maps paths inside its stations. {detail}",
            why="Riders can be routed through the station, and wheelchair users can "
            "see whether a step-free route exists.",
            fix="No action needed."
            if profile.has_step_free
            else "If the station has an elevator, add it as a pathway so wheelchair "
            "users can find the step-free route.",
            effort="None." if profile.has_step_free else "One pathway per elevator.",
            deduction=0.0,
        )
    ]
