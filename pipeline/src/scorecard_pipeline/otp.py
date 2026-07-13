"""Routing QA against OpenTripPlanner: do sample trips actually plan?

The router-free checks (routability.py) catch trips with no leg and stops with no
service. The full check the expansion plan describes loads the feed into
OpenTripPlanner and asserts that real origin-to-destination trips return
itineraries (ADR 0014). OTP is a heavy Java service, so it runs as an optional,
gated step, not on every feed; this module is the pure glue around it.

It picks origin/destination stop pairs that span the service area, builds OTP plan
requests, parses the responses, and decides pass or fail: did the sampled trips
route. The selection, request building, parsing, and the verdict are pure and
unit-tested; talking to a live OTP instance is a thin call.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any

Point = tuple[float, float]  # (lon, lat)
Place = Point | str


def sample_od_pairs(points: list[Point], count: int = 3) -> list[tuple[Point, Point]]:
    """Pick origin/destination pairs that span the service area.

    Sorting by longitude then latitude gives a stable order; pairing the i-th
    point with its mirror from the end yields pairs that cross the area (so a
    router has a real trip to find), deterministically. Fewer than two distinct
    points yields no pairs.
    """
    unique = sorted(set(points))
    if len(unique) < 2:
        return []
    pairs: list[tuple[Point, Point]] = []
    for i in range(min(count, len(unique) // 2)):
        origin = unique[i]
        destination = unique[-(i + 1)]
        if origin != destination:
            pairs.append((origin, destination))
    return pairs


def _place_value(place: Place) -> str:
    if isinstance(place, str):
        return place
    lon, lat = place
    return f"{lat},{lon}"


def plan_url(base: str, origin: Place, destination: Place, *, date: str, time: str) -> str:
    """Build an OTP REST plan URL for one origin/destination pair.

    Uses the OTP ``/otp/routers/default/plan`` endpoint with ``fromPlace`` and
    ``toPlace`` as ``lat,lon`` (OTP's order, the reverse of GeoJSON). Date and
    time anchor the query inside the feed's service window.
    """
    params = {
        "fromPlace": _place_value(origin),
        "toPlace": _place_value(destination),
        "date": date,
        "time": time,
        "mode": "TRANSIT,WALK",
    }
    return f"{base.rstrip('/')}/otp/routers/default/plan?" + urllib.parse.urlencode(params)


def sample_scheduled_stop_pairs(
    trips: list[dict[str, str]],
    stop_times: list[dict[str, str]],
    active_service_ids: set[str],
    *,
    count: int = 3,
    feed_id: str = "qa",
) -> list[tuple[str, str, str]]:
    """Pick stop-ID pairs and departure times from trips active on the QA date."""
    active_trips = {
        row.get("trip_id", "")
        for row in trips
        if row.get("service_id", "") in active_service_ids and row.get("trip_id", "")
    }
    by_trip: dict[str, list[dict[str, str]]] = {}
    for row in stop_times:
        trip_id = row.get("trip_id", "")
        if trip_id in active_trips:
            by_trip.setdefault(trip_id, []).append(row)

    pairs: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for trip_id in sorted(by_trip):
        rows = sorted(by_trip[trip_id], key=lambda row: int(row.get("stop_sequence", "0") or 0))
        if len(rows) < 2:
            continue
        origin = rows[0].get("stop_id", "")
        destination = rows[-1].get("stop_id", "")
        departure = rows[0].get("departure_time") or rows[0].get("arrival_time", "")
        try:
            hour, minute, _second = (int(part) for part in departure.split(":"))
        except (TypeError, ValueError):
            continue
        key = (origin, destination)
        if not origin or not destination or origin == destination or hour >= 24 or key in seen:
            continue
        seen.add(key)
        pairs.append(
            (f"{feed_id}:{origin}", f"{feed_id}:{destination}", f"{hour:02d}:{minute:02d}")
        )
        if len(pairs) >= count:
            break
    return pairs


@dataclass(frozen=True)
class PlanResult:
    """The outcome of one OTP plan request."""

    routable: bool
    itinerary_count: int
    error: str | None = None


def parse_plan(response: dict[str, Any]) -> PlanResult:
    """Parse an OTP plan response into a routable / not-routable result.

    OTP returns ``plan.itineraries`` on success and an ``error`` object when it
    can't route (no path, snapping failure). Both shapes are handled, so a feed
    that OTP loads but can't route reads as not-routable, not as a crash.
    """
    error = response.get("error")
    if error:
        msg = error.get("msg") if isinstance(error, dict) else str(error)
        return PlanResult(routable=False, itinerary_count=0, error=str(msg) if msg else "error")
    itineraries = (response.get("plan") or {}).get("itineraries") or []
    return PlanResult(routable=bool(itineraries), itinerary_count=len(itineraries))


@dataclass(frozen=True)
class RoutingQA:
    """The verdict over a feed's sampled trips."""

    pairs_tested: int
    pairs_routable: int
    failures: list[str]

    @property
    def all_routable(self) -> bool:
        return self.pairs_tested > 0 and self.pairs_routable == self.pairs_tested

    @property
    def routable_share(self) -> float:
        return self.pairs_routable / self.pairs_tested if self.pairs_tested else 0.0


def assess_routing(results: list[PlanResult]) -> RoutingQA:
    """Aggregate per-pair plan results into a feed-level verdict.

    A pair that returned no itinerary is a failure, with OTP's message when it
    gave one. The share routable is the headline; all-routable is the gate a CI
    job would assert.
    """
    routable = sum(1 for r in results if r.routable)
    failures = [r.error or "no itinerary returned" for r in results if not r.routable]
    return RoutingQA(pairs_tested=len(results), pairs_routable=routable, failures=failures)


def fetch_plan(
    base: str,
    origin: Place,
    destination: Place,
    *,
    date: str,
    time: str,
    timeout: int = 30,
    allow_loopback: bool = False,
) -> PlanResult:
    """Query a live OTP instance for one pair. Thin; the parsing is tested.

    Public OTP endpoints use the shared SSRF-guarded fetcher. The containerized
    CI harness may explicitly allow a literal loopback endpoint; redirects stay
    disabled and no hostname other than ``localhost`` is accepted on that path.
    """
    import json

    url = plan_url(base, origin, destination, date=date, time=time)
    if allow_loopback:
        body = _loopback_get(url, timeout=timeout)
    else:
        from .net import safe_get

        body = safe_get(url, timeout=timeout)
    return parse_plan(json.loads(body.decode("utf-8")))


def _loopback_get(url: str, *, timeout: int) -> bytes:
    """Fetch one explicitly trusted local OTP response without redirects."""
    import ipaddress

    import requests

    parts = urllib.parse.urlsplit(url)
    host = parts.hostname
    try:
        is_literal_loopback = bool(host and ipaddress.ip_address(host).is_loopback)
    except ValueError:
        is_literal_loopback = False
    if parts.scheme not in {"http", "https"} or not (host == "localhost" or is_literal_loopback):
        raise ValueError("allow_loopback requires a localhost or loopback-IP OTP base URL")
    response = requests.get(url, timeout=timeout, allow_redirects=False)
    try:
        response.raise_for_status()
        if response.is_redirect or response.is_permanent_redirect:
            raise ValueError("local OTP endpoint must not redirect")
        if len(response.content) > 1024 * 1024:
            raise ValueError("local OTP response exceeded 1 MiB")
        return response.content
    finally:
        response.close()
