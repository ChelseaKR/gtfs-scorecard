"""Routing-flavored QA: can a rider actually use this feed?

Structural validation can pass on a feed a rider still can't travel on. The
expansion plan's routing check (docs/expansion.md, Phase C) loads a feed into
OpenTripPlanner and asserts sample trips return itineraries. OTP is a heavy Java
service to stand up per feed, so this is the serverless tier: two router-free
checks that catch the most common "validates but unusable" breakage, with OTP as
the documented escalation (ADR 0014).

- Single-stop trips: a trip with fewer than two stop_times has no leg a rider
  can board and alight, so it carries no actual service.
- Orphan stops: a boardable stop that no trip ever serves shows up in trip
  planners and on the map, but a rider can never catch anything there.

Both are zero-deduction (ADR pattern shared with flex and pathways): they name a
concrete usability gap without moving the grade, since the rubric weights are a
separate decision. The checks are pure over the feed's tables and unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gtfs import iter_table_rows, read_tables
from .metrics import Finding

# GTFS location_type values that a rider boards at. 1 (station), 2 (entrance),
# 3 (generic node), 4 (boarding area) are structural and legitimately absent from
# stop_times, so they are never counted as orphans.
_BOARDABLE_LOCATION_TYPES = {"", "0"}


def _location_id_key(row: dict[str, str]) -> str | None:
    """The header this row spells ``location_id`` with, tolerating one known
    producer header typo, or None when the row carries no such column.

    This normalization stays inside the ungraded routability check. Graded
    freshness/completeness readers continue to see producer headers exactly as
    published, while the canonical validator reports the malformed header.

    Resolved from one row and reused for the rest of the table: a CSV reader
    gives every row the same header, and re-deriving it per row costs a scan of
    every column of every row -- 188 million of them on the Dutch national
    aggregate, for an answer that cannot change.
    """
    if "location_id" in row:
        return "location_id"
    return next(
        (key for key in row if isinstance(key, str) and key.strip() == "location_id"),
        None,
    )


def _stop_time_facts(gtfs_zip_path: str) -> tuple[set[str], set[str], set[str]]:
    """Fold stop_times.txt into the three bounded facts this check needs.

    Streamed, never materialized. The whole table as ``list[dict[str, str]]``
    costs about 750 bytes a row, so the Dutch national aggregate's 17 million
    rows come to roughly 13 GB -- more than the runner has, from a file that
    sits under the whole-table byte cap. What the check actually reads out of
    those rows is three sets keyed by trip and by stop, so the cost that matters
    is the number of distinct trips and stops (855 thousand and 57 thousand
    there), and it does not grow with the row count at all.

    Returns the trips with at least two serviced locations, the stop ids some
    trip calls at, and the location group ids some trip calls at.
    """
    # A trip is only interesting until it has a second location, so the two sets
    # partition trips by "seen once" and "seen twice or more" rather than
    # counting rows per trip.
    seen_once: set[str] = set()
    trips_with_a_leg: set[str] = set()
    served_stop_ids: set[str] = set()
    served_location_group_ids: set[str] = set()
    location_key: str | None = None
    header_read = False
    # max_member_bytes=None: the byte cap exists to bound a whole-table read,
    # and there is no whole table here to bound.
    for row in iter_table_rows(gtfs_zip_path, "stop_times.txt", max_member_bytes=None):
        if not header_read:
            location_key = _location_id_key(row)
            header_read = True
        trip_id = row.get("trip_id", "").strip()
        stop_id = row.get("stop_id", "").strip()
        location_group_id = row.get("location_group_id", "").strip()
        location_id = (row.get(location_key) or "").strip() if location_key else ""
        # GTFS Schedule uses exactly one of these three fields to identify a
        # serviced location. A GeoJSON location is a rideable trip location but
        # has no implied relationship to an ordinary stop_id.
        if trip_id and (stop_id or location_group_id or location_id):
            if trip_id in seen_once:
                seen_once.discard(trip_id)
                trips_with_a_leg.add(trip_id)
            elif trip_id not in trips_with_a_leg:
                seen_once.add(trip_id)
        if stop_id:
            served_stop_ids.add(stop_id)
        if location_group_id:
            served_location_group_ids.add(location_group_id)
    return trips_with_a_leg, served_stop_ids, served_location_group_ids


@dataclass(frozen=True)
class RoutabilityProfile:
    trips_total: int
    single_stop_trips: int
    boardable_stops: int
    orphan_stops: int
    findings: list[Finding]

    def to_details(self) -> dict[str, Any]:
        return {
            "trips_total": self.trips_total,
            "single_stop_trips": self.single_stop_trips,
            "boardable_stops": self.boardable_stops,
            "orphan_stops": self.orphan_stops,
        }


def assess_routability(gtfs_zip_path: str) -> RoutabilityProfile:
    """Check whether a rider could actually travel on this feed.

    Counts trips that have no rideable leg (fewer than two stop_times) and
    boardable stops that no trip ever serves. Returns the counts and a
    zero-deduction finding for each gap that is present.
    """
    tables = read_tables(
        gtfs_zip_path,
        ["trips.txt", "stops.txt", "location_group_stops.txt"],
    )
    trips, stops = tables["trips.txt"], tables["stops.txt"]

    trips_with_a_leg, served_stop_ids, served_location_group_ids = _stop_time_facts(gtfs_zip_path)

    # A referenced location group serves each stop explicitly assigned to it.
    # Expand only that declared relationship; GeoJSON location_id values have
    # no equivalent stop mapping in the official schema.
    for row in tables["location_group_stops.txt"]:
        location_group_id = row.get("location_group_id", "").strip()
        stop_id = row.get("stop_id", "").strip()
        if location_group_id in served_location_group_ids and stop_id:
            served_stop_ids.add(stop_id)

    trip_ids = [row.get("trip_id", "").strip() for row in trips if row.get("trip_id", "").strip()]
    # A trip with no stop_times at all, or only one, has no rideable leg.
    single_stop_trips = sum(1 for tid in trip_ids if tid not in trips_with_a_leg)

    boardable = [
        row
        for row in stops
        if row.get("location_type", "").strip() in _BOARDABLE_LOCATION_TYPES
        and row.get("stop_id", "").strip()
    ]
    orphan_stops = sum(1 for row in boardable if row["stop_id"].strip() not in served_stop_ids)

    findings: list[Finding] = []
    if single_stop_trips:
        findings.append(
            Finding(
                code="scorecard_single_stop_trips",
                severity="WARNING",
                count=single_stop_trips,
                what=f"{single_stop_trips} of {len(trip_ids)} trips list fewer than two stops.",
                why="A trip with one stop has no ride in it. Trip planners can't put "
                "a rider on that trip at all.",
                fix="Check your scheduling export: every trip should list each stop it "
                "calls at, in order, with times.",
                effort="Usually an export setting or a stop_times mapping in your software.",
                deduction=0.0,
            )
        )
    if orphan_stops:
        findings.append(
            Finding(
                code="scorecard_orphan_stops",
                severity="INFO",
                count=orphan_stops,
                what=f"{orphan_stops} of {len(boardable)} boardable stops are never served "
                "by any trip.",
                why="Riders see these stops in apps and on the map but can never catch "
                "anything there, which erodes trust in the data.",
                fix="Remove stops no route serves, or add the trips that should call at them.",
                effort="A cleanup pass in your scheduling software.",
                deduction=0.0,
            )
        )

    return RoutabilityProfile(
        trips_total=len(trip_ids),
        single_stop_trips=single_stop_trips,
        boardable_stops=len(boardable),
        orphan_stops=orphan_stops,
        findings=findings,
    )
