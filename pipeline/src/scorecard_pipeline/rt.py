"""Realtime quality: sample GTFS-Realtime feeds and score them.

Measures what a sampling window can honestly support: all three feeds
reachable and parseable, header freshness, the share of currently-scheduled
trips present in TripUpdates (a Caltrans v4.0 "100% of trips represented"
check, sampled), and vehicle position plausibility against route shapes.
Schedule-vs-RT drift is computed in rt_drift.py from the same window and
reported alongside; the category summary says exactly what was sampled.

Polling etiquette (docs/feeds.md): one request per endpoint per sample,
samples at least 30 seconds apart, bounded windows only.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import time
import zoneinfo
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .rt_drift import DriftStats, PlausibilityStats
from google.transit import gtfs_realtime_pb2

from .config import Agency, raw_dir
from .fetch import USER_AGENT
from .gtfs import _parse_gtfs_date, read_tables
from .metrics import CategoryResult, Finding
from .net import safe_get

log = logging.getLogger(__name__)

RT_KINDS = ("trip_updates", "vehicle_positions", "service_alerts")

# Scoring weights (rubric.md "Realtime quality"). Components a window can't
# measure (no scheduled trips, no vehicles seen) drop out and the rest
# renormalize.
WEIGHT_REACHABLE = 25.0
WEIGHT_FRESH = 25.0
WEIGHT_COVERAGE = 35.0
WEIGHT_PLAUSIBLE = 15.0

# Full freshness credit at or under 60s of header lag (Caltrans v4.0 asks for
# 20s publish frequency; 60s allows for fetch latency), zero credit at 10min.
FRESH_FULL_SECONDS = 60
FRESH_ZERO_SECONDS = 600
# Past this, the feed isn't merely stale, it has stopped: a header an hour or
# more old means the realtime feed has lapsed, the realtime analogue of an
# expired schedule. It reads as a freshness failure, not a missing-feed zero.
RT_LAPSED_SECONDS = 3600


def _human_duration(seconds: int) -> str:
    """A coarse, readable age for a stale realtime header (e.g. '2 hours')."""
    if seconds < 90:
        return f"{seconds} seconds"
    if seconds < 5400:
        return f"{seconds // 60} minutes"
    if seconds < 129600:
        return f"{seconds // 3600} hours"
    return f"{seconds // 86400} days"


@dataclass(frozen=True)
class StopTimeEvent:
    """One stop_time_update observation from a TripUpdates sample."""

    trip_id: str
    stop_id: str
    stop_sequence: int | None
    delay_seconds: int | None  # taken directly from the feed when present
    predicted_time: int | None  # unix epoch, when the feed gives times instead


@dataclass(frozen=True)
class VehicleObs:
    """One vehicle position observation."""

    trip_id: str
    lat: float
    lon: float


@dataclass(frozen=True)
class RtSample:
    """One fetch of one realtime endpoint."""

    kind: str
    fetched_at: int  # unix seconds
    ok: bool
    header_timestamp: int | None = None
    entity_count: int = 0
    trip_ids: frozenset[str] = frozenset()
    stop_time_events: tuple[StopTimeEvent, ...] = ()
    vehicles: tuple[VehicleObs, ...] = ()
    error: str | None = None

    @property
    def lag_seconds(self) -> int | None:
        if self.header_timestamp is None:
            return None
        return max(0, self.fetched_at - self.header_timestamp)


@dataclass(frozen=True)
class RtWindow:
    """All samples captured for one agency in one run."""

    samples: list[RtSample] = field(default_factory=list)

    def for_kind(self, kind: str) -> list[RtSample]:
        return [s for s in self.samples if s.kind == kind]

    def kind_ok(self, kind: str) -> bool:
        ok = [s.ok for s in self.for_kind(kind)]
        return bool(ok) and all(ok)

    def worst_lag(self, kind: str) -> int | None:
        lags = [s.lag_seconds for s in self.for_kind(kind) if s.lag_seconds is not None]
        return max(lags) if lags else None

    def seen_trip_ids(self) -> frozenset[str]:
        seen: set[str] = set()
        for s in self.for_kind("trip_updates"):
            seen |= s.trip_ids
        return frozenset(seen)


def fetch_sample(kind: str, url: str, archive_to: str | None = None) -> RtSample:
    """Fetch and parse one protobuf snapshot of one realtime endpoint."""
    fetched_at = int(time.time())
    try:
        body = safe_get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        msg = gtfs_realtime_pb2.FeedMessage()
        msg.ParseFromString(body)
    except Exception as exc:
        return RtSample(kind=kind, fetched_at=fetched_at, ok=False, error=str(exc)[:200])

    if archive_to:
        path = Path(archive_to)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    trip_ids: set[str] = set()
    events: list[StopTimeEvent] = []
    vehicles: list[VehicleObs] = []
    if kind == "trip_updates":
        for entity in msg.entity:
            if not (entity.HasField("trip_update") and entity.trip_update.trip.trip_id):
                continue
            tu = entity.trip_update
            trip_ids.add(tu.trip.trip_id)
            for stu in tu.stop_time_update:
                event = stu.arrival if stu.HasField("arrival") else stu.departure
                events.append(
                    StopTimeEvent(
                        trip_id=tu.trip.trip_id,
                        stop_id=stu.stop_id,
                        stop_sequence=stu.stop_sequence if stu.HasField("stop_sequence") else None,
                        delay_seconds=event.delay if event.HasField("delay") else None,
                        predicted_time=event.time if event.HasField("time") else None,
                    )
                )
    elif kind == "vehicle_positions":
        for entity in msg.entity:
            if entity.HasField("vehicle") and entity.vehicle.HasField("position"):
                v = entity.vehicle
                vehicles.append(
                    VehicleObs(
                        trip_id=v.trip.trip_id,
                        lat=v.position.latitude,
                        lon=v.position.longitude,
                    )
                )

    return RtSample(
        kind=kind,
        fetched_at=fetched_at,
        ok=True,
        header_timestamp=int(msg.header.timestamp) if msg.header.timestamp else None,
        entity_count=len(msg.entity),
        trip_ids=frozenset(trip_ids),
        stop_time_events=tuple(events),
        vehicles=tuple(vehicles),
    )


def capture_window(
    agency: Agency, date: dt.date, samples: int = 3, interval_seconds: int = 30
) -> RtWindow:
    """Sample every realtime endpoint `samples` times, `interval` apart."""
    window = RtWindow()
    for i in range(samples):
        if i > 0:
            time.sleep(interval_seconds)
        for kind, url in agency.rt_urls.items():
            stamp = int(time.time())
            archive = raw_dir() / agency.id / date.isoformat() / "rt" / f"{kind}-{stamp}.pb"
            sample = fetch_sample(kind, url, archive_to=str(archive))
            window.samples.append(sample)
            log.info(
                "%s rt %s sample %d/%d: %s",
                agency.id,
                kind,
                i + 1,
                samples,
                "ok" if sample.ok else f"FAILED ({sample.error})",
            )
    return window


# ---------------------------------------------------------------- schedule


def _gtfs_time_to_seconds(value: str) -> int | None:
    parts = value.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, s = (int(p) for p in parts)
    except ValueError:
        return None
    return h * 3600 + m * 60 + s


def _active_service_ids(tables: dict[str, list[dict[str, str]]], date: dt.date) -> set[str]:
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[
        date.weekday()
    ]
    active: set[str] = set()
    for row in tables["calendar.txt"]:
        start = _parse_gtfs_date(row.get("start_date", ""))
        end = _parse_gtfs_date(row.get("end_date", ""))
        if (
            row.get(weekday, "").strip() == "1"
            and start is not None
            and end is not None
            and start <= date <= end
        ):
            active.add(row.get("service_id", ""))
    for row in tables["calendar_dates.txt"]:
        if _parse_gtfs_date(row.get("date", "")) == date:
            if row.get("exception_type", "").strip() == "1":
                active.add(row.get("service_id", ""))
            elif row.get("exception_type", "").strip() == "2":
                active.discard(row.get("service_id", ""))
    return active - {""}


def scheduled_trip_ids_at(gtfs_zip_path: str, moment: dt.datetime) -> set[str]:
    """Trip ids scheduled to be in service at `moment` (agency-local).

    Checks both the calendar day of `moment` and the previous day, because
    GTFS times run past 24:00:00 for service that continues after midnight.

    `moment` must be timezone-aware: a naive datetime would be silently assumed
    to be in system-local time by astimezone, skewing the service window.
    """
    if moment.tzinfo is None:
        raise ValueError("scheduled_trip_ids_at requires a timezone-aware datetime")
    tables = read_tables(
        gtfs_zip_path, ["agency.txt", "calendar.txt", "calendar_dates.txt", "trips.txt"]
    )
    tz_name = (
        tables["agency.txt"][0].get("agency_timezone", "UTC") if tables["agency.txt"] else "UTC"
    )
    local = moment.astimezone(zoneinfo.ZoneInfo(tz_name))

    spans = _trip_time_spans(gtfs_zip_path)
    active: set[str] = set()
    for day_offset in (0, -1):
        service_date = (local + dt.timedelta(days=day_offset)).date()
        seconds = local.hour * 3600 + local.minute * 60 + local.second - day_offset * 86400
        service_ids = _active_service_ids(tables, service_date)
        for row in tables["trips.txt"]:
            if row.get("service_id") in service_ids:
                trip_id = row.get("trip_id", "")
                span = spans.get(trip_id)
                if span and span[0] <= seconds <= span[1]:
                    active.add(trip_id)
    return active


def _trip_time_spans(gtfs_zip_path: str) -> dict[str, tuple[int, int]]:
    """First departure and last arrival (seconds past local midnight) per trip."""
    rows = read_tables(gtfs_zip_path, ["stop_times.txt"])["stop_times.txt"]
    spans: dict[str, tuple[int, int]] = {}
    for row in rows:
        trip_id = row.get("trip_id", "")
        # Prefer departure, fall back to arrival, but distinguish a real 00:00:00
        # (0 seconds) from a missing value: `or` would treat midnight as absent.
        dep = _gtfs_time_to_seconds(row.get("departure_time", ""))
        arr = _gtfs_time_to_seconds(row.get("arrival_time", ""))
        t = dep if dep is not None else arr
        if not trip_id or t is None:
            continue
        lo, hi = spans.get(trip_id, (t, t))
        spans[trip_id] = (min(lo, t), max(hi, t))
    return spans


# ---------------------------------------------------------------- scoring


def realtime(  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    window: RtWindow,
    scheduled: set[str] | None,
    drift: DriftStats | None = None,
    plausibility: PlausibilityStats | None = None,
) -> CategoryResult:
    """Score a sampled realtime window.

    Rationale (rubric.md "Realtime quality"): four weighted components —
    reachability of all three feeds (25), header freshness (25, full credit
    at <=60s lag, zero at 10 minutes), sampled trip coverage (35, Caltrans
    v4.0 expects 100% of operating trips in TripUpdates), and vehicle
    position plausibility (15, on/near the published route shape).
    Components the window can't measure (no trips scheduled, no vehicles
    seen) drop out and the rest renormalize to 100. Drift vs schedule is
    reported in the details and summary; it only becomes a finding when
    predictions disagree with the schedule beyond plausibility.
    """
    findings: list[Finding] = []

    kinds_ok = sum(1 for kind in RT_KINDS if window.kind_ok(kind))
    reachable_fraction = kinds_ok / len(RT_KINDS)
    for kind in RT_KINDS:
        if not window.kind_ok(kind):
            label = kind.replace("_", " ")
            findings.append(
                Finding(
                    code=f"scorecard_rt_{kind}_unreachable",
                    severity="ERROR",
                    count=1,
                    what=f"The {label} realtime feed failed during sampling.",
                    why="When this feed is down, riders see scheduled times "
                    "presented as if they were live.",
                    fix=f"Check the {label} endpoint with your AVL vendor; it "
                    "should return a fresh GTFS-Realtime protobuf on every request.",
                    effort="Usually a vendor support ticket.",
                    deduction=round(WEIGHT_REACHABLE / len(RT_KINDS), 1),
                )
            )

    lags = [window.worst_lag(k) for k in ("trip_updates", "vehicle_positions")]
    known_lags = [lag for lag in lags if lag is not None]
    worst: int | None
    fresh_fraction: float | None
    if known_lags:
        worst = max(known_lags)
        if worst <= FRESH_FULL_SECONDS:
            fresh_fraction = 1.0
        elif worst >= FRESH_ZERO_SECONDS:
            fresh_fraction = 0.0
        else:
            fresh_fraction = 1 - (worst - FRESH_FULL_SECONDS) / (
                FRESH_ZERO_SECONDS - FRESH_FULL_SECONDS
            )
        if worst >= RT_LAPSED_SECONDS:
            # The feed has effectively stopped. Frame it like an expired schedule:
            # a freshness failure, not a transient lag.
            findings.append(
                Finding(
                    code="scorecard_rt_feed_lapsed",
                    severity="ERROR",
                    count=1,
                    what=f"The realtime feed's last update was about {_human_duration(worst)} "
                    "old when sampled.",
                    why="A realtime feed this far behind has effectively stopped. Riders see "
                    "buses that already left, or apps quietly fall back to the schedule while "
                    "still showing a live label.",
                    fix="Ask your AVL vendor why the feed stopped advancing; the "
                    "GTFS-Realtime header timestamp should move forward on every publish.",
                    effort="A vendor support ticket; treat it as a feed outage.",
                    deduction=round((1 - fresh_fraction) * WEIGHT_FRESH, 1),
                )
            )
        elif fresh_fraction < 1.0:
            findings.append(
                Finding(
                    code="scorecard_rt_stale",
                    severity="WARNING",
                    count=1,
                    what=f"Realtime data was up to {worst} seconds old when sampled.",
                    why="Stale positions and predictions are worse than none: riders "
                    "watch a bus that already left.",
                    fix="Ask your AVL vendor to publish updates at least every 20 "
                    "seconds (the Caltrans guideline).",
                    effort="A vendor configuration question.",
                    deduction=round((1 - fresh_fraction) * WEIGHT_FRESH, 1),
                )
            )
    else:
        # No header timestamp on any reachable feed: freshness isn't measurable,
        # so it drops out of the score (renormalized) rather than scoring zero.
        # A reachable feed that simply omits the optional timestamp shouldn't be
        # marked stale. Note it as a fix instead.
        worst = None
        fresh_fraction = None
        if reachable_fraction > 0:
            findings.append(
                Finding(
                    code="scorecard_rt_no_timestamp",
                    severity="INFO",
                    count=1,
                    what="Realtime feeds didn't include a header timestamp, so "
                    "freshness couldn't be checked.",
                    why="Without a header timestamp, apps and this scorecard can't "
                    "tell how old the data is.",
                    fix="Set the GTFS-Realtime FeedHeader.timestamp on every response.",
                    effort="A vendor configuration question.",
                    deduction=0.0,
                )
            )

    # Mirror the schedule's freshness framing so a stale realtime feed reads the
    # same way: fresh, stale (transient lag), or lapsed (effectively stopped).
    if worst is None:
        rt_freshness = None
    elif worst >= RT_LAPSED_SECONDS:
        rt_freshness = "lapsed"
    elif worst > FRESH_FULL_SECONDS:
        rt_freshness = "stale"
    else:
        rt_freshness = "fresh"

    details: dict[str, object] = {
        "samples": len(window.samples),
        "kinds_reachable": kinds_ok,
        "worst_lag_seconds": worst,
        "rt_freshness": rt_freshness,
    }

    # Weighted components; None fraction means "not measurable this window".
    coverage_fraction: float | None = None
    if scheduled:
        seen = window.seen_trip_ids()
        coverage_fraction = len(scheduled & seen) / len(scheduled)
        details["scheduled_trips_in_window"] = len(scheduled)
        details["covered_trips"] = len(scheduled & seen)
        details["coverage_pct"] = round(coverage_fraction * 100, 1)
        if coverage_fraction < 1.0:
            missing = len(scheduled) - len(scheduled & seen)
            findings.append(
                Finding(
                    code="scorecard_rt_trip_coverage",
                    severity="WARNING",
                    count=missing,
                    what=f"{missing} of {len(scheduled)} trips scheduled during the "
                    "sampling window had no live predictions.",
                    why="Riders on those trips get schedule data dressed up as "
                    "realtime. Caltrans expects every operating trip in TripUpdates.",
                    fix="Check with your AVL vendor that every vehicle assignment "
                    "flows into TripUpdates, including school-day and tripper runs.",
                    effort="A vendor data-mapping question.",
                    deduction=round((1 - coverage_fraction) * WEIGHT_COVERAGE, 1),
                )
            )
    else:
        details["scheduled_trips_in_window"] = 0
        details["coverage_pct"] = None

    plausible_fraction: float | None = None
    if plausibility is not None:
        plausible_fraction = plausibility.plausible_share
        details["vehicles_checked"] = plausibility.vehicles_checked
        details["vehicles_on_route_pct"] = round(plausibility.plausible_share * 100, 1)
        if plausibility.plausible_share < 0.9:
            # ceil, not round: when this finding fires (share < 0.9) at least one
            # vehicle is off-route, so "0 of N" must never be shown.
            off = math.ceil((1 - plausibility.plausible_share) * plausibility.vehicles_checked)
            findings.append(
                Finding(
                    code="scorecard_rt_vehicles_off_route",
                    severity="WARNING",
                    count=off,
                    what=f"{off} of {plausibility.vehicles_checked} sampled vehicle "
                    f"positions were far from their assigned route (worst: "
                    f"{plausibility.worst_meters} m).",
                    why="A bus shown off its route usually means a wrong trip "
                    "assignment; riders watch their bus drive the wrong streets.",
                    fix="Ask your AVL vendor to check vehicle-to-trip assignments "
                    "for the flagged trips.",
                    effort="A vendor support ticket with the trip ids attached.",
                    deduction=round((1 - plausibility.plausible_share) * WEIGHT_PLAUSIBLE, 1),
                )
            )

    if drift is not None:
        details["drift"] = {
            "observations": drift.observations,
            "median_seconds": drift.median_seconds,
            "p90_abs_seconds": drift.p90_abs_seconds,
            "on_time_share_pct": round(drift.on_time_share * 100, 1),
        }
        if drift.p90_abs_seconds > 1800:
            findings.append(
                Finding(
                    code="scorecard_rt_predictions_implausible",
                    severity="WARNING",
                    count=drift.observations,
                    what="Some live predictions disagree with the schedule by more "
                    "than 30 minutes.",
                    why="Differences that large usually mean predictions are keyed "
                    "to the wrong trips, not that buses are that late.",
                    fix="Spot-check the flagged predictions against what buses "
                    "actually did; raise trip-matching with your AVL vendor.",
                    effort="A vendor data-mapping question.",
                    deduction=0.0,
                )
            )

    components: list[tuple[float, float | None]] = [
        (WEIGHT_REACHABLE, reachable_fraction),
        (WEIGHT_FRESH, fresh_fraction),
        (WEIGHT_COVERAGE, coverage_fraction),
        (WEIGHT_PLAUSIBLE, plausible_fraction),
    ]
    measurable = [(w, f) for w, f in components if f is not None]
    score = sum(w * f for w, f in measurable) / sum(w for w, _ in measurable) * 100.0

    bits = [f"Sampled {len(window.samples)} times: {kinds_ok} of 3 feeds healthy"]
    if coverage_fraction is not None:
        bits.append(f"{details['coverage_pct']}% of scheduled trips had live predictions")
    else:
        bits[0] = (
            f"Sampled {len(window.samples)} times outside service hours: "
            f"{kinds_ok} of 3 feeds healthy"
        )
    if plausible_fraction is not None:
        bits.append(f"{details['vehicles_on_route_pct']}% of vehicles on their route")
    if drift is not None:
        bits.append(
            f"predictions ran a median of {abs(drift.median_seconds)}s "
            f"{'behind' if drift.median_seconds >= 0 else 'ahead of'} schedule"
        )
    summary = "; ".join(bits) + "."

    return CategoryResult(
        name="realtime",
        score=max(0.0, min(100.0, score)),
        summary=summary,
        findings=findings,
        details=details,
    )
