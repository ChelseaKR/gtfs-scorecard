"""Realtime quality: sample GTFS-Realtime feeds and score them.

Measures what a sampling window can honestly support: every configured feed
kind reachable and parseable, header freshness, TripUpdates coverage when that
feed kind is published, and VehiclePositions plausibility when that feed kind
is published. Schedule-vs-RT drift is computed in rt_drift.py from the same
window and reported alongside; the category summary says exactly what was
sampled.

Polling etiquette (docs/feeds.md): one request per endpoint per sample,
samples at least 30 seconds apart, bounded windows only.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import time
import zoneinfo
from collections.abc import Collection
from dataclasses import dataclass, field, replace
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

# An alert whose every active period ended this long ago and that is still
# being served has been forgotten, not scheduled: riders reading "detour ends
# May 3" in July learn to ignore every future alert (EXP-19). Thirty days
# gives planned multi-phase work generous room before the flag fires.
ALERT_STALE_SECONDS = 30 * 86400


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
class AlertObs:
    """Content observations for one service alert entity (EXP-19).

    Alerts are the one realtime payload a rider reads verbatim, so what is
    observed is mechanical readability: is there plain header text, a longer
    description, a stated cause and effect, an informed entity scoping it to
    routes or stops, and has its active period already ended. Judgments stay
    mechanical (presence and dates), never stylistic.
    """

    has_header_text: bool
    has_description: bool
    has_cause: bool
    has_effect: bool
    has_informed_entity: bool
    # Latest end across active periods, unix seconds; None means open-ended
    # (an alert with no stated end can't be called stale by date).
    period_end: int | None


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
    alerts: tuple[AlertObs, ...] = ()
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


def alerts_content(window: RtWindow) -> dict[str, int] | None:
    """Summarize alert content over a window's newest good alerts snapshot.

    An alerts feed is a full snapshot, so the newest successful sample speaks
    for the whole window; staleness is judged against that sample's own fetch
    time, which keeps the read reproducible. None when the window holds no
    successful alerts sample (nothing measured is reported as nothing, never
    as a zero). An empty feed is a normal, healthy state: no disruptions.
    """
    samples = [s for s in window.for_kind("service_alerts") if s.ok]
    if not samples:
        return None
    newest = max(samples, key=lambda s: s.fetched_at)
    alerts = newest.alerts
    return {
        "alerts": len(alerts),
        "with_header_text": sum(1 for a in alerts if a.has_header_text),
        "with_description": sum(1 for a in alerts if a.has_description),
        "with_cause_and_effect": sum(1 for a in alerts if a.has_cause and a.has_effect),
        "with_informed_entity": sum(1 for a in alerts if a.has_informed_entity),
        "ended_over_30_days_ago": sum(
            1
            for a in alerts
            if a.period_end is not None and newest.fetched_at - a.period_end > ALERT_STALE_SECONDS
        ),
    }


def _has_text(translated: object) -> bool:
    """Whether a TranslatedString carries any non-blank text."""
    return any(t.text.strip() for t in getattr(translated, "translation", ()))


def parse_alerts(msg: gtfs_realtime_pb2.FeedMessage) -> tuple[AlertObs, ...]:
    """Content observations for every alert entity in one snapshot (EXP-19)."""
    observations: list[AlertObs] = []
    for entity in msg.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert
        # The latest stated end across periods; any open-ended period means
        # the alert as a whole has no end date.
        period_end: int | None = None
        if alert.active_period and all(p.HasField("end") for p in alert.active_period):
            period_end = max(int(p.end) for p in alert.active_period)
        observations.append(
            AlertObs(
                has_header_text=_has_text(alert.header_text),
                has_description=_has_text(alert.description_text),
                has_cause=alert.HasField("cause"),
                has_effect=alert.HasField("effect"),
                has_informed_entity=len(alert.informed_entity) > 0,
                period_end=period_end,
            )
        )
    return tuple(observations)


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

    alerts = parse_alerts(msg) if kind == "service_alerts" else ()

    return RtSample(
        kind=kind,
        fetched_at=fetched_at,
        ok=True,
        header_timestamp=int(msg.header.timestamp) if msg.header.timestamp else None,
        entity_count=len(msg.entity),
        trip_ids=frozenset(trip_ids),
        stop_time_events=tuple(events),
        vehicles=tuple(vehicles),
        alerts=alerts,
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


def _assessed_kinds(window: RtWindow, configured_kinds: Collection[str] | None) -> tuple[str, ...]:
    """The feed kinds this window is scored against, in ``RT_KINDS`` order.

    ``configured_kinds`` is the authoritative agency configuration. Callers
    predating that argument fall back to the known feed kinds present in the
    window, and an entirely empty legacy window retains the former fail-closed
    three-feed interpretation.
    """
    if configured_kinds is None:
        observed = {sample.kind for sample in window.samples if sample.kind in RT_KINDS}
        return tuple(kind for kind in RT_KINDS if kind in observed) or RT_KINDS
    assessed = tuple(kind for kind in RT_KINDS if kind in configured_kinds)
    if not assessed:
        raise ValueError("realtime requires at least one configured GTFS-Realtime feed kind")
    return assessed


def _reachability(
    window: RtWindow, assessed_kinds: tuple[str, ...]
) -> tuple[list[str], float, list[Finding]]:
    """Reachability of the configured feed kinds (``WEIGHT_REACHABLE``)."""
    reachable_kinds = [kind for kind in assessed_kinds if window.kind_ok(kind)]
    findings = [
        Finding(
            code=f"scorecard_rt_{kind}_unreachable",
            severity="ERROR",
            count=1,
            what=f"The {kind.replace('_', ' ')} realtime feed failed during sampling.",
            why="When this feed is down, riders see scheduled times "
            "presented as if they were live.",
            fix=f"Check the {kind.replace('_', ' ')} endpoint with your AVL vendor; it "
            "should return a fresh GTFS-Realtime protobuf on every request.",
            effort="Usually a vendor support ticket.",
            deduction=WEIGHT_REACHABLE / len(assessed_kinds),
        )
        for kind in assessed_kinds
        if not window.kind_ok(kind)
    ]
    return reachable_kinds, len(reachable_kinds) / len(assessed_kinds), findings


def _freshness(
    window: RtWindow, assessed_kinds: tuple[str, ...]
) -> tuple[int | None, float | None, str | None, list[Finding]]:
    """Header freshness (``WEIGHT_FRESH``): worst lag, fraction, band, findings.

    Mirrors the schedule's freshness framing so a stale realtime feed reads the
    same way: fresh, stale (transient lag), or lapsed (effectively stopped).
    """
    freshness_kinds = tuple(
        kind for kind in ("trip_updates", "vehicle_positions") if kind in assessed_kinds
    )
    known_lags = [
        lag for lag in (window.worst_lag(kind) for kind in freshness_kinds) if lag is not None
    ]
    if not known_lags:
        # No header timestamp on any reachable feed: freshness isn't measurable,
        # so it drops out of the score (renormalized) rather than scoring zero.
        # A reachable feed that simply omits the optional timestamp shouldn't be
        # marked stale. Note it as a fix instead.
        findings = []
        if any(window.kind_ok(kind) for kind in freshness_kinds):
            findings.append(
                Finding(
                    code="scorecard_rt_no_timestamp",
                    severity="INFO",
                    count=1,
                    what="Realtime feeds didn't include a header timestamp, so "
                    "freshness couldn't be checked.",
                    why="Without a header timestamp, apps and this scorecard can't "
                    "tell how old the data is.",
                    fix="Stamp every realtime response with the time it was made. "
                    "The field is FeedHeader.timestamp.",
                    effort="A vendor configuration question.",
                    deduction=0.0,
                )
            )
        return None, None, None, findings

    worst = max(known_lags)
    if worst <= FRESH_FULL_SECONDS:
        fresh_fraction = 1.0
    elif worst >= FRESH_ZERO_SECONDS:
        fresh_fraction = 0.0
    else:
        fresh_fraction = 1 - (worst - FRESH_FULL_SECONDS) / (
            FRESH_ZERO_SECONDS - FRESH_FULL_SECONDS
        )

    findings = []
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
                deduction=(1 - fresh_fraction) * WEIGHT_FRESH,
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
                fix="Ask your AVL vendor to send updates at least every 20 seconds. "
                "That is the Caltrans guideline.",
                effort="A vendor configuration question.",
                deduction=(1 - fresh_fraction) * WEIGHT_FRESH,
            )
        )

    if worst >= RT_LAPSED_SECONDS:
        band = "lapsed"
    elif worst > FRESH_FULL_SECONDS:
        band = "stale"
    else:
        band = "fresh"
    return worst, fresh_fraction, band, findings


def _alerts(
    window: RtWindow, assessed_kinds: tuple[str, ...]
) -> tuple[dict[str, int] | None, list[Finding]]:
    """Service-alert content (EXP-19): observed and reported, never scored.

    Any weight for this enters through the governed shadow-scoring path
    (FIX-06), never a quiet commit, so every finding here carries
    ``deduction=0.0``.
    """
    if "service_alerts" not in assessed_kinds:
        return None, []
    summary = alerts_content(window)
    if summary is None:
        return None, []
    findings = []
    stale_count = summary["ended_over_30_days_ago"]
    if stale_count:
        findings.append(
            Finding(
                code="scorecard_rt_alerts_ended",
                severity="WARNING",
                count=stale_count,
                what=f"{stale_count} of {summary['alerts']} published service "
                "alerts ended more than 30 days ago.",
                why="A rider who reads about a detour that ended weeks ago learns "
                "to ignore the next alert too.",
                fix="Remove or close out ended alerts in your alerts tool; most "
                "publish an end date and clear them automatically.",
                effort="A few minutes in your alerts tool.",
                deduction=0.0,
            )
        )
    missing_text = summary["alerts"] - summary["with_header_text"]
    if missing_text:
        findings.append(
            Finding(
                code="scorecard_rt_alerts_missing_text",
                severity="INFO",
                count=missing_text,
                what=f"{missing_text} of {summary['alerts']} published service "
                "alerts have no header text.",
                why="An alert with no text shows up blank in the app. Riders never "
                "learn what changed.",
                fix="Give every alert a one-line plain-language header in your "
                "alerts tool; the description field can carry the detail.",
                effort="A habit in your alerts tool, not a code change.",
                deduction=0.0,
            )
        )
    return summary, findings


def _trip_coverage(
    window: RtWindow, assessed_kinds: tuple[str, ...], scheduled: set[str] | None
) -> tuple[float | None, dict[str, object], list[Finding]]:
    """Sampled trip coverage (``WEIGHT_COVERAGE``).

    Returns its detail keys in the order the artifact publishes them.
    """
    if "trip_updates" not in assessed_kinds:
        return None, {"coverage_pct": None}, []
    if not (scheduled and any(sample.ok for sample in window.for_kind("trip_updates"))):
        return None, {"scheduled_trips_in_window": len(scheduled or ()), "coverage_pct": None}, []

    seen = window.seen_trip_ids()
    covered = len(scheduled & seen)
    coverage_fraction = covered / len(scheduled)
    details: dict[str, object] = {
        "scheduled_trips_in_window": len(scheduled),
        "covered_trips": covered,
        "coverage_pct": round(coverage_fraction * 100, 1),
    }
    findings = []
    if coverage_fraction < 1.0:
        missing = len(scheduled) - covered
        findings.append(
            Finding(
                code="scorecard_rt_trip_coverage",
                severity="WARNING",
                count=missing,
                what=f"{missing} of {len(scheduled)} trips scheduled during the "
                "sampling window had no live predictions.",
                why="Riders on those trips get schedule times labeled as live. "
                "Caltrans asks that every trip you run shows up in TripUpdates.",
                fix="Ask your AVL vendor to check that every vehicle assignment "
                "reaches TripUpdates. School-day and tripper runs are the ones most "
                "often left out.",
                effort="A vendor data-mapping question.",
                deduction=(1 - coverage_fraction) * WEIGHT_COVERAGE,
            )
        )
    return coverage_fraction, details, findings


def _plausibility_component(
    assessed_kinds: tuple[str, ...], plausibility: PlausibilityStats | None
) -> tuple[float | None, dict[str, object], list[Finding]]:
    """Vehicle position plausibility (``WEIGHT_PLAUSIBLE``)."""
    if "vehicle_positions" not in assessed_kinds or plausibility is None:
        return None, {}, []
    details: dict[str, object] = {
        "vehicles_checked": plausibility.vehicles_checked,
        "vehicles_on_route_pct": round(plausibility.plausible_share * 100, 1),
    }
    findings = []
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
                deduction=(1 - plausibility.plausible_share) * WEIGHT_PLAUSIBLE,
            )
        )
    return plausibility.plausible_share, details, findings


def _drift_component(
    assessed_kinds: tuple[str, ...], drift: DriftStats | None
) -> tuple[dict[str, object], list[Finding]]:
    """Schedule-vs-realtime drift: reported in the details, not scored.

    It only becomes a finding when predictions disagree with the schedule
    beyond plausibility, and even then it deducts nothing.
    """
    if "trip_updates" not in assessed_kinds or drift is None:
        return {}, []
    details: dict[str, object] = {
        "drift": {
            "observations": drift.observations,
            "median_seconds": drift.median_seconds,
            "p90_abs_seconds": drift.p90_abs_seconds,
            "on_time_share_pct": round(drift.on_time_share * 100, 1),
        }
    }
    findings = []
    if drift.p90_abs_seconds > 1800:
        findings.append(
            Finding(
                code="scorecard_rt_predictions_implausible",
                severity="WARNING",
                count=drift.observations,
                what="Some live predictions are more than 30 minutes away from the schedule.",
                why="Differences that large usually mean predictions are keyed "
                "to the wrong trips, not that buses are that late.",
                fix="Spot-check the flagged predictions against what buses "
                "actually did; raise trip-matching with your AVL vendor.",
                effort="A vendor data-mapping question.",
                deduction=0.0,
            )
        )
    return details, findings


def _realtime_summary(
    window: RtWindow,
    assessed_kinds: tuple[str, ...],
    kinds_ok: int,
    details: dict[str, object],
    scheduled: set[str] | None,
    coverage_fraction: float | None,
    plausible_fraction: float | None,
    drift: DriftStats | None,
) -> str:
    """The plain-language one-liner shown above the realtime findings."""
    feed_word = "feed" if len(assessed_kinds) == 1 else "feeds"
    bits = [
        f"Sampled {len(window.samples)} times: {kinds_ok} of "
        f"{len(assessed_kinds)} configured {feed_word} healthy"
    ]
    if coverage_fraction is not None:
        bits.append(f"{details['coverage_pct']}% of scheduled trips had live predictions")
    elif "trip_updates" in assessed_kinds and not scheduled:
        bits[0] = (
            f"Sampled {len(window.samples)} times outside service hours: "
            f"{kinds_ok} of {len(assessed_kinds)} configured {feed_word} healthy"
        )
    if plausible_fraction is not None:
        bits.append(f"{details['vehicles_on_route_pct']}% of vehicles on their route")
    elif "vehicle_positions" in assessed_kinds:
        bits.append("vehicle position plausibility was not measurable")
    if "trip_updates" in assessed_kinds and drift is not None:
        bits.append(
            f"predictions ran a median of {abs(drift.median_seconds)}s "
            f"{'behind' if drift.median_seconds >= 0 else 'ahead of'} schedule"
        )
    return "; ".join(bits) + "."


def realtime(
    window: RtWindow,
    scheduled: set[str] | None,
    drift: DriftStats | None = None,
    plausibility: PlausibilityStats | None = None,
    configured_kinds: Collection[str] | None = None,
) -> CategoryResult:
    """Score a sampled realtime window.

    Rationale (rubric.md "Realtime quality"): four weighted components —
    reachability of the feed kinds the agency configured (25), header freshness
    (25, full credit at <=60s lag, zero at 10 minutes), sampled trip coverage
    when TripUpdates is configured (35, Caltrans v4.0 expects 100% of operating
    trips in TripUpdates), and vehicle position plausibility when
    VehiclePositions is configured (15, on/near the published route shape).
    Unconfigured feed kinds and components the window can't measure drop out;
    the rest renormalize to 100. Drift vs schedule is reported in the details
    and summary; it only becomes a finding when predictions disagree with the
    schedule beyond plausibility.

    ``configured_kinds`` is the authoritative agency configuration. Callers
    predating this argument fall back to the known feed kinds present in the
    window. An entirely empty legacy window retains the former fail-closed
    three-feed interpretation; the collect path never calls this function for
    an agency with no realtime configuration.
    """
    assessed_kinds = _assessed_kinds(window, configured_kinds)

    reachable_kinds, reachable_fraction, reach_findings = _reachability(window, assessed_kinds)
    kinds_ok = len(reachable_kinds)
    worst, fresh_fraction, rt_freshness, fresh_findings = _freshness(window, assessed_kinds)
    alert_summary, alert_findings = _alerts(window, assessed_kinds)
    coverage_fraction, coverage_details, coverage_findings = _trip_coverage(
        window, assessed_kinds, scheduled
    )
    plausible_fraction, plausible_details, plausible_findings = _plausibility_component(
        assessed_kinds, plausibility
    )
    drift_details, drift_findings = _drift_component(assessed_kinds, drift)

    details: dict[str, object] = {
        "samples": len(window.samples),
        "configured_kinds": list(assessed_kinds),
        "reachable_kinds": reachable_kinds,
        "kinds_configured": len(assessed_kinds),
        "kinds_reachable": kinds_ok,
        "worst_lag_seconds": worst,
        "rt_freshness": rt_freshness,
    }
    if alert_summary is not None:
        details["alerts_content"] = alert_summary
    details.update(coverage_details)
    details.update(plausible_details)
    details.update(drift_details)

    # Findings are concatenated in the order the components are scored, which
    # is the order the agency page reads them in.
    findings: list[Finding] = [
        *reach_findings,
        *fresh_findings,
        *alert_findings,
        *coverage_findings,
        *plausible_findings,
        *drift_findings,
    ]

    components: list[tuple[float, float | None]] = [
        (WEIGHT_REACHABLE, reachable_fraction),
        (WEIGHT_FRESH, fresh_fraction),
        (WEIGHT_COVERAGE, coverage_fraction),
        (WEIGHT_PLAUSIBLE, plausible_fraction),
    ]
    measurable = [(w, f) for w, f in components if f is not None]
    measurable_weight = sum(w for w, _ in measurable)
    score = sum(w * f for w, f in measurable) / measurable_weight * 100.0

    # Finding points drive both the public "+N points" copy and top-fix
    # priority, so they must use the same denominator as the category score.
    # Keep informational findings at exactly zero; only scored shortfalls are
    # expanded when unmeasurable components drop out.
    deduction_scale = 100.0 / measurable_weight
    findings = [
        replace(finding, deduction=finding.deduction * deduction_scale)
        if finding.deduction > 0
        else finding
        for finding in findings
    ]

    return CategoryResult(
        name="realtime",
        score=max(0.0, min(100.0, score)),
        summary=_realtime_summary(
            window,
            assessed_kinds,
            kinds_ok,
            details,
            scheduled,
            coverage_fraction,
            plausible_fraction,
            drift,
        ),
        findings=findings,
        details=details,
    )
