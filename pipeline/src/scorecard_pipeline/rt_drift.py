"""Schedule-vs-realtime drift and vehicle position plausibility.

Both work on whatever the sampling window captured (docs/rubric.md
"Realtime quality"):

- Drift: how far TripUpdates predictions sit from the published schedule.
  Reported as a distribution (median, p90, share within the standard
  on-time band of 1 minute early to 5 minutes late). Drift describes
  operations as much as data, so it informs the scorecard but only turns
  into a finding when predictions disagree with the schedule so wildly
  that the predictions themselves look wrong.

- Plausibility: the share of reported vehicle positions within
  PLAUSIBLE_METERS of their assigned trip's published route shape. Folded
  into the realtime score; a bus reported far off its route usually means
  a wrong trip assignment or stale AVL mapping.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
import zoneinfo
from dataclasses import dataclass

from .gtfs import read_tables
from .rt import RtSample, _gtfs_time_to_seconds

ON_TIME_EARLY_SECONDS = -60
ON_TIME_LATE_SECONDS = 300
SANITY_BOUND_SECONDS = 6 * 3600  # discard matches further out than this
PLAUSIBLE_METERS = 250.0


@dataclass(frozen=True)
class DriftStats:
    """Distribution of prediction-vs-schedule deltas, seconds (+ = late)."""

    observations: int
    median_seconds: int
    p90_abs_seconds: int
    on_time_share: float  # within [-60s, +300s]


@dataclass(frozen=True)
class PlausibilityStats:
    """Share of vehicle positions on or near their trip's route shape."""

    vehicles_checked: int
    plausible_share: float
    worst_meters: int


# ---------------------------------------------------------------- drift


def _schedule_lookup(
    gtfs_zip_path: str,
) -> tuple[dict[tuple[str, int], int], dict[tuple[str, str], int], str]:
    """Scheduled seconds-past-midnight keyed by (trip, stop_sequence) and
    (trip, stop_id), plus the agency timezone."""
    tables = read_tables(gtfs_zip_path, ["stop_times.txt", "agency.txt"])
    by_seq: dict[tuple[str, int], int] = {}
    by_stop: dict[tuple[str, str], int] = {}
    for row in tables["stop_times.txt"]:
        trip = row.get("trip_id", "")
        seconds = _gtfs_time_to_seconds(
            row.get("arrival_time", "") or row.get("departure_time", "")
        )
        if not trip or seconds is None:
            continue
        seq = row.get("stop_sequence", "").strip()
        if seq.isdigit():
            by_seq[(trip, int(seq))] = seconds
        stop = row.get("stop_id", "").strip()
        if stop:
            by_stop.setdefault((trip, stop), seconds)
    tz = tables["agency.txt"][0].get("agency_timezone", "UTC") if tables["agency.txt"] else "UTC"
    return by_seq, by_stop, tz


def compute_drift(samples: list[RtSample], gtfs_zip_path: str) -> DriftStats | None:  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    """Compare sampled TripUpdates predictions against the static schedule.

    Per (trip, stop) the latest sample wins. Predictions given as absolute
    times are matched against the schedule on both the sample's service
    date and the previous one (after-midnight service), keeping whichever
    interpretation is nearer; matches beyond a 6 hour sanity bound are
    discarded as mis-keyed rather than treated as record-setting lateness.
    """
    by_seq, by_stop, tz_name = _schedule_lookup(gtfs_zip_path)
    tz = zoneinfo.ZoneInfo(tz_name)

    deltas: dict[tuple[str, str, int | None], int] = {}
    for sample in samples:
        if sample.kind != "trip_updates" or not sample.ok:
            continue
        local_date = dt.datetime.fromtimestamp(sample.fetched_at, tz).date()
        for ev in sample.stop_time_events:
            key = (ev.trip_id, ev.stop_id, ev.stop_sequence)
            if ev.delay_seconds is not None:
                # Same sanity bound as the predicted-time branch, so a feed
                # reporting an absurd delay can't skew the median/p90.
                if abs(ev.delay_seconds) <= SANITY_BOUND_SECONDS:
                    deltas[key] = ev.delay_seconds
                continue
            if ev.predicted_time is None:
                continue
            sched = None
            if ev.stop_sequence is not None:
                sched = by_seq.get((ev.trip_id, ev.stop_sequence))
            if sched is None:
                sched = by_stop.get((ev.trip_id, ev.stop_id))
            if sched is None:
                continue
            candidates = []
            for offset in (0, -1):
                midnight = dt.datetime.combine(
                    local_date + dt.timedelta(days=offset), dt.time(), tz
                )
                candidates.append(ev.predicted_time - (int(midnight.timestamp()) + sched))
            best = min(candidates, key=abs)
            if abs(best) <= SANITY_BOUND_SECONDS:
                deltas[key] = best

    if not deltas:
        return None
    values = sorted(deltas.values())
    p90_abs = sorted(abs(v) for v in values)[max(0, math.ceil(0.9 * len(values)) - 1)]
    on_time = sum(1 for v in values if ON_TIME_EARLY_SECONDS <= v <= ON_TIME_LATE_SECONDS)
    return DriftStats(
        observations=len(values),
        median_seconds=round(statistics.median(values)),
        p90_abs_seconds=p90_abs,
        on_time_share=on_time / len(values),
    )


# ---------------------------------------------------------------- plausibility


def _meters_xy(lat_ref: float, lat: float, lon: float) -> tuple[float, float]:
    """Equirectangular projection to meters around a reference latitude;
    plenty accurate at route scale."""
    x = lon * 111_320.0 * math.cos(math.radians(lat_ref))
    y = lat * 110_540.0
    return x, y


def _point_segment_meters(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _min_distance_to_shape(lat: float, lon: float, shape: list[tuple[float, float]]) -> float:
    p = _meters_xy(lat, lat, lon)
    pts = [_meters_xy(lat, s_lat, s_lon) for s_lat, s_lon in shape]
    if len(pts) == 1:
        return math.hypot(p[0] - pts[0][0], p[1] - pts[0][1])
    return min(_point_segment_meters(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def vehicle_plausibility(samples: list[RtSample], gtfs_zip_path: str) -> PlausibilityStats | None:
    """Check sampled vehicle positions against their trips' route shapes.

    Returns None (not applicable) when the feed has no shapes or the window
    saw no vehicles assigned to known trips.
    """
    tables = read_tables(gtfs_zip_path, ["trips.txt", "shapes.txt"])
    trip_to_shape = {
        row["trip_id"]: row["shape_id"]
        for row in tables["trips.txt"]
        if row.get("trip_id") and row.get("shape_id")
    }
    shapes: dict[str, list[tuple[int, float, float]]] = {}
    for row in tables["shapes.txt"]:
        try:
            shapes.setdefault(row["shape_id"], []).append(
                (
                    int(row["shape_pt_sequence"]),
                    float(row["shape_pt_lat"]),
                    float(row["shape_pt_lon"]),
                )
            )
        except (KeyError, ValueError):
            continue
    ordered = {
        shape_id: [(lat, lon) for _, lat, lon in sorted(points)]
        for shape_id, points in shapes.items()
    }
    if not ordered:
        return None

    # Latest observation per (trip, rounded position) to avoid double counting.
    seen: dict[tuple[str, float, float], float] = {}
    for sample in samples:
        if sample.kind != "vehicle_positions" or not sample.ok:
            continue
        for v in sample.vehicles:
            shape_id = trip_to_shape.get(v.trip_id)
            if not shape_id or shape_id not in ordered:
                continue
            key = (v.trip_id, round(v.lat, 5), round(v.lon, 5))
            seen[key] = _min_distance_to_shape(v.lat, v.lon, ordered[shape_id])

    if not seen:
        return None
    distances = list(seen.values())
    plausible = sum(1 for d in distances if d <= PLAUSIBLE_METERS)
    return PlausibilityStats(
        vehicles_checked=len(distances),
        plausible_share=plausible / len(distances),
        worst_meters=round(max(distances)),
    )


# ---------------------------------------------------------------- ping-stop deviation

# Mineta Transportation Institute / Newmark, "Assessing the Accuracy of
# GTFS Real-Time Data" (project 2031, 2021): a vehicle position reported
# more than 30 m from the stop the schedule places it at is treated as a
# ping that does not line up with the stop. 30 m is roughly a bus length
# plus normal GPS scatter, so a larger gap points to a stale or mis-mapped
# position rather than ordinary noise.
PING_STOP_DEVIATION_METERS = 30.0


def ping_stop_deviation_meters(
    vehicle_lat: float,
    vehicle_lon: float,
    stop_lat: float,
    stop_lon: float,
) -> float:
    """Straight-line meters between a reported vehicle position and the
    scheduled stop coordinate it should be near."""
    ref = vehicle_lat
    vx, vy = _meters_xy(ref, vehicle_lat, vehicle_lon)
    sx, sy = _meters_xy(ref, stop_lat, stop_lon)
    return math.hypot(vx - sx, vy - sy)


def ping_stop_deviation_exceeded(
    vehicle_lat: float,
    vehicle_lon: float,
    stop_lat: float,
    stop_lon: float,
) -> bool:
    """True when the vehicle is more than PING_STOP_DEVIATION_METERS from the
    scheduled stop coordinate, so the reported position does not match the
    schedule."""
    return (
        ping_stop_deviation_meters(vehicle_lat, vehicle_lon, stop_lat, stop_lon)
        > PING_STOP_DEVIATION_METERS
    )


# ---------------------------------------------------------------- timestamp anomalies


@dataclass(frozen=True)
class StopPrediction:
    """One stop_time_update prediction: a stop and its predicted epoch time."""

    stop_id: str
    predicted_epoch: int


@dataclass(frozen=True)
class TimestampAnomalies:
    """Counts of timestamp problems found in a TripUpdate's predictions."""

    duplicate_timestamp_stops: int  # stops given two predictions with the same time
    past_dated_predictions: int  # predictions timed before the message timestamp

    @property
    def total(self) -> int:
        return self.duplicate_timestamp_stops + self.past_dated_predictions


def find_timestamp_anomalies(
    predictions: list[StopPrediction] | list[tuple[str, int]],
    message_epoch: int,
) -> TimestampAnomalies:
    """Scan a TripUpdate's stop predictions for two timestamp problems.

    Accepts either StopPrediction records or plain (stop_id, predicted_epoch)
    tuples, so callers can pass parsed protobuf or test data without a
    dependency on live feeds.

    Duplicate-timestamp stops: a stop that gets more than one prediction
    carrying the same predicted time. Real predictions for one stop should not
    repeat the same instant, so this points to a feed stamping a default value
    rather than a real estimate.

    Past-dated predictions: a predicted time earlier than the message
    timestamp. A prediction for an upcoming stop should not be dated before
    "now"; when it is, the feed's clock or its prediction is off.
    """
    normalized = [
        p if isinstance(p, StopPrediction) else StopPrediction(p[0], p[1]) for p in predictions
    ]

    by_stop: dict[str, list[int]] = {}
    for p in normalized:
        by_stop.setdefault(p.stop_id, []).append(p.predicted_epoch)
    duplicate_stops = sum(1 for times in by_stop.values() if len(times) != len(set(times)))

    past_dated = sum(1 for p in normalized if p.predicted_epoch < message_epoch)

    return TimestampAnomalies(
        duplicate_timestamp_stops=duplicate_stops,
        past_dated_predictions=past_dated,
    )
