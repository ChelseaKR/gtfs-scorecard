"""What a finding costs, not only what is wrong.

A finding today states a defect: "296 of 296 stops don't say whether a wheelchair
user can board there." What it does not state is the consequence: how much of the
network that touches, how many rider-trips ride on the feed carrying it, and how
much the served area needs transit. A rule engine cannot produce any of that,
because every one of those numbers lives outside the file being validated
(`docs/competitive-positioning.md`, "The category: valid but wrong";
`docs/product-roadmap.md`, "How coverage is chosen").

This module is the pure foundation of that layer. It answers three questions
about one finding, and refuses each of them out loud when the data is not there:

1. **Reach.** Which denominator does this finding actually divide by, and what
   share of it does the finding cover? The basis comes from a reviewed table
   (``FINDING_BASIS``), derived by reading each producer rather than by reading
   the code name, because the two disagree: ``scorecard_orphan_stops`` counts
   against boardable stops, not all stops, and ``scorecard_station_missing_step_free_data``
   counts *files*, so it has no network share at all.
2. **Ridership.** Annual rider-trips for the feed's National Transit Database
   reporter. The NTD is a United States federal programme (ADR 0026), and one
   reporter's trips must never be applied to several feed records
   (``ridership.duplicate_ntd_reporter_ids``), so both cases return an explicit
   absence.
3. **Served-area need.** The need tier for the area the feed's stops sit in,
   from the US ACS overlay (ADR 0015) or the Canadian CIMD overlay (ADR 0027).
   The two tiers are not comparable to each other, so the scale that produced a
   tier travels with it and no comparison is made here.

Nothing is estimated. Where a number is unavailable the result carries a reason
and ``None``, never a zero: a feed outside the United States has unknown
ridership, not no riders. Reach is deliberately not multiplied into rider-trips
either, because boardings are not spread evenly across stops, so
"22% of stops" times "annual rider-trips" would be a fabricated number wearing a
measurement's clothes.

Pure by design, like ``anomaly.py`` and ``fixlog.py``: dicts in, dataclasses out,
no fetching and no disk. Wiring the result into artifacts or the agency page is a
separate change.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .equity import EquityIndicators, need_tier
from .ridership import annual_trips_for, normalize_ntd_id

# --- denominator bases -------------------------------------------------------

STOPS = "stops"
BOARDABLE_STOPS = "boardable_stops"
ROUTES = "routes"
TRIPS = "trips"
NO_BASIS = "none"

# Plain-language noun for each basis, used directly in the consequence line.
BASIS_LABEL: dict[str, str] = {
    STOPS: "stops",
    BOARDABLE_STOPS: "boardable stops",
    ROUTES: "routes",
    TRIPS: "trips",
    NO_BASIS: "",
}

# Where each basis's denominator is read from in a published artifact, in
# preference order. These are the only stop/route/trip totals an artifact
# carries, and they are not interchangeable:
#
# - ``geo.stop_count`` counts stops.txt rows that have usable coordinates, which
#   is the closest published stand-in for "every stop in the feed". Across the
#   published corpus it is at least as large as ``routability.boardable_stops``
#   for all but a handful of feeds, and the two agree for most.
# - ``routability.boardable_stops`` counts only rows a rider can board at
#   (location_type blank or 0). It is the denominator ``assess_routability``
#   itself divides orphan stops by, and it is *not* a valid denominator for a
#   finding computed over every stops.txt row: 262 published feeds have more
#   stops missing wheelchair_boarding than they have boardable stops.
# - ``routability.trips_total`` counts trips.txt rows with a trip_id, which is the
#   row set completeness and routability both iterate. ``mode_profile.trip_count``
#   drops trips whose route_id does not resolve, so it is the fallback.
_DENOMINATOR_PATHS: dict[str, tuple[tuple[str, str], ...]] = {
    STOPS: (("geo", "stop_count"), ("routability", "boardable_stops")),
    BOARDABLE_STOPS: (("routability", "boardable_stops"),),
    ROUTES: (("mode_profile", "route_count"),),
    TRIPS: (("routability", "trips_total"), ("mode_profile", "trip_count")),
}

# Why a finding has no share of the network. Every value here is a statement the
# module can defend, not a placeholder for work not done.
FEED_LEVEL = "feed_level"
NOT_NETWORK_COUNTABLE = "not_network_countable"
SAMPLED_WINDOW = "sampled_window"
VALIDATOR_NOTICE = "validator_notice"
UNMAPPED_FINDING = "unmapped_finding"
DENOMINATOR_MISSING = "denominator_missing"
INCONSISTENT_COUNTS = "inconsistent_counts"
COUNT_MISSING = "count_missing"

# Finding code to denominator basis. Each entry was decided by reading the code
# that builds the finding, not by reading its name. The comment on each block
# names the producer so the next person can re-check it the same way.
FINDING_BASIS: dict[str, str] = {
    # completeness.py: computed over every row of the named table.
    "scorecard_wheelchair_boarding_unknown": STOPS,  # (1 - wb) * len(stops)
    "scorecard_stop_names_all_caps": STOPS,  # (1 - mixed) * len(stops)
    "scorecard_wheelchair_accessible_unknown": TRIPS,  # (1 - wa) * len(trips)
    "scorecard_missing_headsigns": TRIPS,  # len(trips) - headsigned - loop-exempt
    # completeness.py: one fact about the feed, count is always 1.
    "scorecard_no_fare_data": NO_BASIS,
    "scorecard_fare_free": NO_BASIS,
    "scorecard_no_feed_contact": NO_BASIS,
    "scorecard_bad_agency_url": NO_BASIS,
    # routability.py: single-stop trips divide by len(trip_ids); orphan stops
    # divide by the boardable subset, which is the whole point of the check.
    "scorecard_single_stop_trips": TRIPS,
    "scorecard_orphan_stops": BOARDABLE_STOPS,
    # accessibility.py: route badges are counted per route, risky stop names per
    # stop. The step-free finding counts missing *files* (1 or 2), so it has no
    # share of the network however large the station is.
    "scorecard_route_color_low_contrast": ROUTES,
    "scorecard_stop_name_needs_tts": STOPS,
    "scorecard_station_missing_step_free_data": NO_BASIS,
    # metrics.py freshness: every one of these is a single fact about the feed's
    # calendar. They reach the whole network, but not as a countable subset.
    "scorecard_no_expiry_date": NO_BASIS,
    "scorecard_feed_expired": NO_BASIS,
    "scorecard_feed_expiring_soon": NO_BASIS,
    "scorecard_intermittent_calendar_ended": NO_BASIS,
    "scorecard_planned_service_boundary": NO_BASIS,
    "scorecard_missing_feed_info_dates": NO_BASIS,
    # rt.py: measured over a sampling window, so the denominators that exist
    # (trips scheduled in the window, vehicles sampled, alerts published) are
    # window-scoped and must not be read against a feed-wide total.
    "scorecard_rt_trip_updates_unreachable": NO_BASIS,
    "scorecard_rt_vehicle_positions_unreachable": NO_BASIS,
    "scorecard_rt_service_alerts_unreachable": NO_BASIS,
    "scorecard_rt_feed_lapsed": NO_BASIS,
    "scorecard_rt_stale": NO_BASIS,
    "scorecard_rt_no_timestamp": NO_BASIS,
    "scorecard_rt_alerts_ended": NO_BASIS,
    "scorecard_rt_alerts_missing_text": NO_BASIS,
    "scorecard_rt_trip_coverage": NO_BASIS,
    "scorecard_rt_vehicles_off_route": NO_BASIS,
    "scorecard_rt_predictions_implausible": NO_BASIS,
    # pathways.py / flex.py / fares.py: counts here are pathways, booking rules,
    # or fare products. None of them is a share of the riding network.
    "scorecard_station_no_pathways": NO_BASIS,
    "scorecard_station_pathways": NO_BASIS,
    "scorecard_flex_no_booking_rules": NO_BASIS,
    "scorecard_flex_booking_unreachable": NO_BASIS,
    "scorecard_flex_completeness_no_booking_rules": NO_BASIS,
    "scorecard_flex_completeness_no_contact": NO_BASIS,
    "scorecard_flex_service": NO_BASIS,
    "scorecard_fares_published_not_applied": NO_BASIS,
    "scorecard_fares_v2_no_rider_categories": NO_BASIS,
    "scorecard_fares_v2_no_fare_media": NO_BASIS,
}

# The reason a mapped NO_BASIS finding has no share, so the absence note can say
# something true rather than "not applicable".
_NO_BASIS_REASON: dict[str, str] = {
    "scorecard_no_fare_data": FEED_LEVEL,
    "scorecard_fare_free": FEED_LEVEL,
    "scorecard_no_feed_contact": FEED_LEVEL,
    "scorecard_bad_agency_url": FEED_LEVEL,
    "scorecard_no_expiry_date": FEED_LEVEL,
    "scorecard_feed_expired": FEED_LEVEL,
    "scorecard_feed_expiring_soon": FEED_LEVEL,
    "scorecard_intermittent_calendar_ended": FEED_LEVEL,
    "scorecard_planned_service_boundary": FEED_LEVEL,
    "scorecard_missing_feed_info_dates": FEED_LEVEL,
    "scorecard_rt_trip_updates_unreachable": SAMPLED_WINDOW,
    "scorecard_rt_vehicle_positions_unreachable": SAMPLED_WINDOW,
    "scorecard_rt_service_alerts_unreachable": SAMPLED_WINDOW,
    "scorecard_rt_feed_lapsed": SAMPLED_WINDOW,
    "scorecard_rt_stale": SAMPLED_WINDOW,
    "scorecard_rt_no_timestamp": SAMPLED_WINDOW,
    "scorecard_rt_alerts_ended": SAMPLED_WINDOW,
    "scorecard_rt_alerts_missing_text": SAMPLED_WINDOW,
    "scorecard_rt_trip_coverage": SAMPLED_WINDOW,
    "scorecard_rt_vehicles_off_route": SAMPLED_WINDOW,
    "scorecard_rt_predictions_implausible": SAMPLED_WINDOW,
    "scorecard_station_missing_step_free_data": NOT_NETWORK_COUNTABLE,
    "scorecard_station_no_pathways": NOT_NETWORK_COUNTABLE,
    "scorecard_station_pathways": NOT_NETWORK_COUNTABLE,
    "scorecard_flex_no_booking_rules": NOT_NETWORK_COUNTABLE,
    "scorecard_flex_booking_unreachable": NOT_NETWORK_COUNTABLE,
    "scorecard_flex_completeness_no_booking_rules": NOT_NETWORK_COUNTABLE,
    "scorecard_flex_completeness_no_contact": NOT_NETWORK_COUNTABLE,
    "scorecard_flex_service": NOT_NETWORK_COUNTABLE,
    "scorecard_fares_published_not_applied": NOT_NETWORK_COUNTABLE,
    "scorecard_fares_v2_no_rider_categories": NOT_NETWORK_COUNTABLE,
    "scorecard_fares_v2_no_fare_media": NOT_NETWORK_COUNTABLE,
}

# --- regional scope ----------------------------------------------------------

# Ridership is an FTA National Transit Database concept and the NTD covers United
# States reporters only (ADR 0026). Everywhere else the honest answer is "not
# known here", never zero.
RIDERSHIP_COUNTRIES = frozenset({"US"})

# Served-area need has an overlay for the United States (ACS, ADR 0015) and for
# Canada (CIMD, ADR 0027). The two tiers are within-country and not comparable to
# each other, which is why ``ServedAreaNeed`` carries the scale that produced it.
NEED_SCALES: dict[str, str] = {"US": "us_acs", "CA": "ca_cimd"}

# Tier vocabulary shared by both overlays (``equity.need_tier``, ``cimd._tier``).
_KNOWN_TIERS = frozenset({"high", "moderate", "lower", "unknown"})

# Why ridership or need is absent.
OUTSIDE_RIDERSHIP_SCOPE = "outside_ridership_scope"
NO_RIDERSHIP_DATA = "no_ridership_data"
NO_NTD_ID = "no_ntd_id"
DUPLICATE_NTD_REPORTER = "duplicate_ntd_reporter"
UNMATCHED_NTD_ID = "unmatched_ntd_id"
OUTSIDE_NEED_SCOPE = "outside_need_scope"
NO_SERVED_AREA_DATA = "no_served_area_data"
UNKNOWN_TIER = "unknown_tier"


# --- results -----------------------------------------------------------------


@dataclass(frozen=True)
class Reach:
    """How much of the network one finding touches.

    ``share`` is ``affected / total`` in 0..1, rounded to four places, and is
    ``None`` whenever the pair cannot be trusted. ``reason`` is empty when the
    reach is known and names the obstacle otherwise.
    """

    basis: str
    basis_label: str
    affected: int | None = None
    total: int | None = None
    share: float | None = None
    total_source: str = ""
    reason: str = ""

    @property
    def known(self) -> bool:
        return self.share is not None

    def to_json(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "basis_label": self.basis_label,
            "affected": self.affected,
            "total": self.total,
            "share": self.share,
            "total_source": self.total_source,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Ridership:
    """Annual rider-trips for the feed's NTD reporter, or why there are none."""

    annual_rider_trips: int | None = None
    ntd_id: str = ""
    reason: str = ""

    @property
    def known(self) -> bool:
        return self.annual_rider_trips is not None

    def to_json(self) -> dict[str, Any]:
        return {
            "annual_rider_trips": self.annual_rider_trips,
            "ntd_id": self.ntd_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ServedAreaNeed:
    """The served-area need tier, with the within-country scale that produced it."""

    tier: str | None = None
    scale: str = ""
    reason: str = ""

    @property
    def known(self) -> bool:
        return self.tier is not None

    def to_json(self) -> dict[str, Any]:
        return {"tier": self.tier, "scale": self.scale, "reason": self.reason}


@dataclass(frozen=True)
class Consequence:
    """One finding's measured cost, with every gap stated rather than filled."""

    code: str
    reach: Reach
    ridership: Ridership
    need: ServedAreaNeed

    @property
    def line(self) -> str:
        """The plain-language line for the agency page."""
        return consequence_line(self)

    @property
    def absences(self) -> list[str]:
        """Plain-language notes for everything this consequence does not know."""
        return absence_notes(self)

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reach": self.reach.to_json(),
            "ridership": self.ridership.to_json(),
            "served_area_need": self.need.to_json(),
            "line": self.line,
            "absences": self.absences,
        }


# --- reach -------------------------------------------------------------------


def basis_for(code: str) -> str:
    """The denominator basis for a finding code, or ``NO_BASIS`` when it has none."""
    return FINDING_BASIS.get(code, NO_BASIS)


def _no_basis_reason(code: str) -> str:
    """Why a code has no share: a reviewed reason, or an honest "we don't know"."""
    if code in _NO_BASIS_REASON:
        return _NO_BASIS_REASON[code]
    if code.startswith("scorecard_"):
        # A scorecard finding this module has not classified yet. Saying so is the
        # point: a new finding must get a reviewed basis, never a guessed one.
        return UNMAPPED_FINDING
    # Everything else is a canonical gtfs-validator notice code. Its count is
    # notice instances, and the validator decides what an instance covers, so no
    # denominator in the artifact is known to match it.
    return VALIDATOR_NOTICE


def _affected_count(finding: dict[str, Any]) -> int | None:
    raw = finding.get("count")
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    if raw < 0:
        return None
    return raw


def _denominator(artifact: dict[str, Any], basis: str) -> tuple[int | None, str]:
    """The published total for a basis and the artifact path it came from."""
    for section, key in _DENOMINATOR_PATHS.get(basis, ()):
        block = artifact.get(section)
        if not isinstance(block, dict):
            continue
        value = block.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            continue
        return value, f"{section}.{key}"
    return None, ""


def reach_for(finding: dict[str, Any], artifact: dict[str, Any]) -> Reach:
    """How much of the network one finding touches, or why that is not known.

    ``finding`` is a finding dict as published (``code``, ``count``, and the rest
    of ``Finding.to_json``); ``artifact`` is the agency artifact that carries the
    denominators. A count larger than the published total is reported as unknown
    rather than as a share above 100%, because the two numbers then describe
    different row sets and neither the numerator nor the denominator can be
    trusted on its own.
    """
    code = str(finding.get("code") or "")
    basis = basis_for(code)
    label = BASIS_LABEL.get(basis, "")
    if basis == NO_BASIS:
        return Reach(basis=NO_BASIS, basis_label="", reason=_no_basis_reason(code))

    affected = _affected_count(finding)
    if affected is None:
        return Reach(basis=basis, basis_label=label, reason=COUNT_MISSING)

    total, source = _denominator(artifact, basis)
    if total is None:
        return Reach(basis=basis, basis_label=label, affected=affected, reason=DENOMINATOR_MISSING)
    if affected > total:
        return Reach(
            basis=basis,
            basis_label=label,
            affected=affected,
            total=total,
            total_source=source,
            reason=INCONSISTENT_COUNTS,
        )
    return Reach(
        basis=basis,
        basis_label=label,
        affected=affected,
        total=total,
        share=round(affected / total, 4),
        total_source=source,
    )


# --- ridership ---------------------------------------------------------------


def _country(artifact: dict[str, Any]) -> str:
    """The artifact's ISO country, defaulting to US for records that predate the field.

    ``agency.country`` is additive: United States artifacts published before it
    existed omit it, and the site resolves those the same way (``render_site``
    reads ``agency.country`` with a "US" default).
    """
    agency = artifact.get("agency")
    if not isinstance(agency, dict):
        return "US"
    return str(agency.get("country") or "US").strip().upper()


def _artifact_ntd_id(artifact: dict[str, Any]) -> str:
    alignment = artifact.get("ntd_id_alignment")
    if not isinstance(alignment, dict):
        return ""
    return normalize_ntd_id(alignment.get("ntd_id"))


def ridership_for(
    artifact: dict[str, Any],
    ridership: dict[str, int] | None = None,
    *,
    quarantined_ntd_ids: Iterable[str] = (),
) -> Ridership:
    """Annual rider-trips for this feed's NTD reporter, or an explicit absence.

    ``ridership`` is the map ``ridership.load_ridership`` returns.
    ``quarantined_ntd_ids`` must be computed over the unfiltered registry with
    ``ridership.duplicate_ntd_reporter_ids``: when several feed records claim one
    reporter, that reporter's annual trips belong to none of them individually,
    so applying them here would multiply a national total by feed count.

    Every absence returns ``None`` with a reason. A feed outside the United
    States has unknown rider-trips, not zero rider-trips.
    """
    if _country(artifact) not in RIDERSHIP_COUNTRIES:
        return Ridership(reason=OUTSIDE_RIDERSHIP_SCOPE)
    ntd_id = _artifact_ntd_id(artifact)
    if not ntd_id:
        return Ridership(reason=NO_NTD_ID)
    quarantined = {normalize_ntd_id(value) for value in quarantined_ntd_ids}
    quarantined.discard("")
    if ntd_id in quarantined:
        return Ridership(ntd_id=ntd_id, reason=DUPLICATE_NTD_REPORTER)
    if not ridership:
        return Ridership(ntd_id=ntd_id, reason=NO_RIDERSHIP_DATA)
    trips = annual_trips_for({"ntd_id": ntd_id}, ridership)
    if trips is None:
        return Ridership(ntd_id=ntd_id, reason=UNMATCHED_NTD_ID)
    return Ridership(annual_rider_trips=trips, ntd_id=ntd_id)


# --- served-area need --------------------------------------------------------


def _tier_from(served_area: str | EquityIndicators | None) -> str | None:
    """Normalize the accepted served-area inputs to a tier string."""
    if served_area is None:
        return None
    if isinstance(served_area, EquityIndicators):
        return need_tier(served_area)
    tier = str(served_area).strip().lower()
    return tier if tier in _KNOWN_TIERS else None


def served_area_need_for(
    artifact: dict[str, Any],
    served_area: str | EquityIndicators | None = None,
) -> ServedAreaNeed:
    """The served-area need tier for this feed, or an explicit absence.

    ``served_area`` accepts either an already-computed tier string (the first
    element of ``tract_equity.served_area_need`` or of ``cimd.served_area_cimd``)
    or the ``EquityIndicators`` that ``tract_equity.served_area_indicators``
    returns, which are classified here with the same ``equity.need_tier``.

    The overlays cover the United States and Canada. Elsewhere this returns an
    absence, not a "lower need" default, and the returned ``scale`` records which
    country's overlay produced the tier so a caller never ranks one against the
    other (ADR 0026).
    """
    scale = NEED_SCALES.get(_country(artifact), "")
    if not scale:
        return ServedAreaNeed(reason=OUTSIDE_NEED_SCOPE)
    tier = _tier_from(served_area)
    if tier is None:
        return ServedAreaNeed(scale=scale, reason=NO_SERVED_AREA_DATA)
    if tier == "unknown":
        return ServedAreaNeed(scale=scale, reason=UNKNOWN_TIER)
    return ServedAreaNeed(tier=tier, scale=scale)


# --- the whole picture -------------------------------------------------------


def consequence_for(
    finding: dict[str, Any],
    artifact: dict[str, Any],
    *,
    ridership: dict[str, int] | None = None,
    quarantined_ntd_ids: Iterable[str] = (),
    served_area: str | EquityIndicators | None = None,
) -> Consequence:
    """What one finding costs: network reach, rider-trips, and served-area need.

    Only ``finding`` and ``artifact`` are required, and with those alone the
    result carries reach plus two honest absences. Supplying the ridership
    snapshot and the served-area tier fills the other two in where the data
    covers the feed's country.
    """
    return Consequence(
        code=str(finding.get("code") or ""),
        reach=reach_for(finding, artifact),
        ridership=ridership_for(artifact, ridership, quarantined_ntd_ids=quarantined_ntd_ids),
        need=served_area_need_for(artifact, served_area),
    )


# --- plain language ----------------------------------------------------------

_REACH_ABSENCE: dict[str, str] = {
    FEED_LEVEL: "This one is about the feed as a whole, so there is no share of it to count.",
    SAMPLED_WINDOW: (
        "This was measured over a realtime sampling window, so it has no feed-wide share."
    ),
    NOT_NETWORK_COUNTABLE: (
        "What this one counts is not stops, routes, or trips, so there is no network share."
    ),
    VALIDATOR_NOTICE: (
        "This is a validator notice. The validator decides what each instance covers, "
        "so no share of the network can be read from it."
    ),
    UNMAPPED_FINDING: (
        "This finding has no reviewed denominator yet, so no share is reported for it."
    ),
    COUNT_MISSING: "This finding carries no usable count, so no share is reported.",
}

_RIDERSHIP_ABSENCE: dict[str, str] = {
    OUTSIDE_RIDERSHIP_SCOPE: (
        "Rider-trip counts come from the United States National Transit Database. "
        "It does not cover this feed's country."
    ),
    NO_RIDERSHIP_DATA: "No ridership snapshot was supplied, so annual rider-trips are not known.",
    NO_NTD_ID: (
        "This feed carries no National Transit Database ID, so annual rider-trips "
        "are not known for it."
    ),
    DUPLICATE_NTD_REPORTER: (
        "More than one feed record claims this National Transit Database reporter. "
        "Its rider-trips are held back rather than counted against any one feed."
    ),
    UNMATCHED_NTD_ID: (
        "The ridership snapshot has no row for this feed's National Transit Database ID."
    ),
}

_NEED_ABSENCE: dict[str, str] = {
    OUTSIDE_NEED_SCOPE: (
        "The served-area need overlays cover the United States and Canada, "
        "so none of them applies to this feed."
    ),
    NO_SERVED_AREA_DATA: "No served-area indicators were supplied, so transit need is not known.",
    UNKNOWN_TIER: (
        "No served-area indicator covered this feed's stops, so transit need is not known."
    ),
}


def _percent_phrase(share: float) -> str:
    """A percentage a reader can say out loud, without pretending to precision.

    Only reached for a partial share, so the two ends round away from the
    absolutes: 3 of 9,850 stops is "under 1%", not "0%", and 9,847 of 9,850 is
    "nearly all", not the "100%" that would contradict the counts beside it.
    """
    pct = share * 100
    if pct < 1:
        return "under 1%"
    if pct >= 99.5:
        return "nearly all"
    return f"about {round(pct)}%"


def reach_sentence(reach: Reach) -> str:
    """One sentence for a finding's network reach, framed as what a fix covers."""
    if not reach.known or reach.affected is None or reach.total is None:
        return _REACH_ABSENCE.get(
            reach.reason,
            f"The feed's {reach.basis_label or 'network'} count is not published here, "
            "so no share is reported.",
        )
    if reach.affected == 0:
        return f"None of the feed's {reach.total:,} {reach.basis_label} are affected."
    if reach.affected == reach.total:
        return f"Fixing this covers all {reach.total:,} {reach.basis_label} in the feed."
    share = reach.share if reach.share is not None else 0.0
    return (
        f"Fixing this covers {reach.affected:,} of {reach.total:,} "
        f"{reach.basis_label}, {_percent_phrase(share)} of them."
    )


def consequence_line(consequence: Consequence) -> str:
    """The one-line consequence for the agency page.

    Leads with reach, because that number holds everywhere. Rider-trips and
    served-area need are appended only where the data actually covers the feed;
    what is missing is reported by ``absence_notes`` instead of being implied to
    be zero here.
    """
    parts = [reach_sentence(consequence.reach)]
    trips = consequence.ridership.annual_rider_trips
    if trips is not None:
        parts.append(
            f"This feed's National Transit Database reporter recorded {trips:,} annual rider-trips."
        )
    if consequence.need.tier is not None:
        parts.append(f"The area this feed serves measures {consequence.need.tier} on transit need.")
    return " ".join(parts)


def absence_notes(consequence: Consequence) -> list[str]:
    """Plain-language notes for the numbers this consequence does not have.

    A caller that shows the line should show these too. An unmeasured number is
    not a zero, and a silent omission invites a reader to fill it in with one.
    Reach is not repeated here: when it is unknown the line already says so.
    """
    notes: list[str] = []
    if not consequence.ridership.known:
        note = _RIDERSHIP_ABSENCE.get(consequence.ridership.reason)
        if note:
            notes.append(note)
    if not consequence.need.known:
        note = _NEED_ABSENCE.get(consequence.need.reason)
        if note:
            notes.append(note)
    return notes
