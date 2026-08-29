"""Rider experience completeness: the fields riders feel directly.

Based on portable GTFS fields and Best Practices, with the California Transit
Data Guidelines documented as one source in the published scoring profile (see
docs/rubric.md "Rider experience completeness"). Accessibility fields carry
the most weight on purpose: they are both a values statement and a common gap
in small-agency feeds.
"""

from __future__ import annotations

from collections.abc import Iterable

from .cemv import detect_cemv
from .fares import detect_fares, fares_findings
from .flex import detect_flex, flex_findings
from .gtfs import TableTooLargeError, iter_table_rows, read_tables
from .metrics import CategoryResult, Finding
from .pathways import detect_pathways, pathways_findings
from .translations import detect_translations

# Component weights, summing to 100. Accessibility totals 40.
WEIGHTS = {
    "wheelchair_stops": 25.0,
    "wheelchair_trips": 15.0,
    "fares": 15.0,
    "stop_names": 15.0,
    "headsigns": 15.0,
    "contact": 15.0,
}

# Applicability analysis is optional and must not make a previously scoreable
# feed exhaust runner memory. Parse stop_times.txt as a stream, consider only
# trips that could qualify, and retain the ordinary headsign check above this
# uncompressed size.
HEADSIGN_STOP_TIMES_MAX_BYTES = 64 * 1024 * 1024


def _fraction_with_value(rows: list[dict[str, str]], field: str, allowed: set[str]) -> float | None:
    """Share of rows whose field holds one of the allowed values.

    ``None`` when there is nothing to measure (``rows`` is empty): a feed
    with no stops (a demand-response/Flex-only service, GTFS Best Practices)
    or no trips gave the pipeline nothing to check, which is not the same as
    every one of them failing the check. Returning ``0.0`` here previously
    scored a stopless feed as "0 of 0 stops don't say whether a wheelchair
    user can board there" — a fabricated failure for a measurement that
    could not be made (issue #286).
    """
    if not rows:
        return None
    good = sum(1 for row in rows if row.get(field, "").strip() in allowed)
    return good / len(rows)


def _is_shouty(name: str) -> bool:
    """True for names written LIKE THIS. Short tokens ('4 & B', 'UCD') are
    fine; only a fully-uppercase word of 4+ letters in a cased script reads as
    shouting. Scripts without letter case (for example Japanese or Arabic)
    must never be treated as uppercase."""
    words = ["".join(c for c in token if c.isalpha()) for token in name.split()]
    cased = [c for c in name if c.isalpha() and c.lower() != c.upper()]
    return (
        bool(cased)
        and all(c == c.upper() for c in cased)
        and any(
            len(w) >= 4 and any(c.lower() != c.upper() for c in w) and w == w.upper() for w in words
        )
    )


def _fraction_mixed_case(rows: list[dict[str, str]], field: str) -> float | None:
    """Share of rows whose name reads like a name, not LIKE THIS.

    ``None`` when ``rows`` itself is empty — no stops to check at all
    (issue #286). A stop that exists but has a blank name is a different,
    narrower gap than shouting and keeps scoring 0.0 for this specific
    check, since there was something to measure and it failed.
    """
    if not rows:
        return None
    named = [row[field].strip() for row in rows if row.get(field, "").strip()]
    if not named:
        return 0.0
    return sum(1 for name in named if not _is_shouty(name)) / len(named)


def _trip_stop_patterns(
    stop_times: Iterable[dict[str, str]], candidate_trip_ids: set[str]
) -> dict[str, tuple[str, ...]]:
    """Ordered stop IDs for trips whose stop-time evidence is complete.

    The canonical validator owns malformed-field reporting. This narrower
    reader only decides whether there is enough evidence to waive a scorecard
    recommendation, so any blank stop, invalid sequence, or duplicate sequence
    makes the affected trip ineligible for that waiver.
    """
    stop_rows_by_trip: dict[str, list[tuple[int, int, str]]] = {}
    sequences_by_trip: dict[str, set[int]] = {}
    invalid_trip_ids: set[str] = set()
    for position, row in enumerate(stop_times):
        trip_id = (row.get("trip_id") or "").strip()
        if trip_id not in candidate_trip_ids:
            continue
        stop_id = (row.get("stop_id") or "").strip()
        sequence_text = (row.get("stop_sequence") or "").strip()
        try:
            sequence = int(sequence_text)
        except ValueError:
            invalid_trip_ids.add(trip_id)
            continue
        if not stop_id or sequence < 0:
            invalid_trip_ids.add(trip_id)
            continue

        sequences = sequences_by_trip.setdefault(trip_id, set())
        if sequence in sequences:
            invalid_trip_ids.add(trip_id)
            continue
        sequences.add(sequence)
        stop_rows_by_trip.setdefault(trip_id, []).append((sequence, position, stop_id))

    patterns_by_trip: dict[str, tuple[str, ...]] = {}
    for trip_id, indexed_rows in stop_rows_by_trip.items():
        if trip_id in invalid_trip_ids:
            continue
        ordered = sorted(indexed_rows)
        patterns_by_trip[trip_id] = tuple(stop_id for _, _, stop_id in ordered)
    return patterns_by_trip


def _has_loop_candidate_metadata(route_trips: list[dict[str, str]]) -> bool:
    """Whether cheap trip metadata supports reading stop-pattern evidence."""
    if any(trip.get("trip_headsign", "").strip() for trip in route_trips):
        return False
    direction_ids = {trip.get("direction_id", "").strip() for trip in route_trips}
    if len(direction_ids) != 1 or "" in direction_ids:
        return False
    shape_ids = {trip.get("shape_id", "").strip() for trip in route_trips}
    if len(shape_ids) != 1 or "" in shape_ids:
        return False

    trip_ids = [trip.get("trip_id", "").strip() for trip in route_trips]
    return bool(all(trip_ids) and len(set(trip_ids)) == len(trip_ids))


def _is_single_pattern_loop(
    route_trips: list[dict[str, str]], patterns_by_trip: dict[str, tuple[str, ...]]
) -> bool:
    """Whether one route has enough evidence to make a headsign non-actionable."""
    if not _has_loop_candidate_metadata(route_trips):
        return False

    trip_ids = [trip.get("trip_id", "").strip() for trip in route_trips]
    patterns = [patterns_by_trip.get(trip_id) for trip_id in trip_ids]
    if any(pattern is None for pattern in patterns) or len(set(patterns)) != 1:
        return False
    pattern = patterns[0]
    return bool(
        pattern is not None
        and len(pattern) >= 3
        and pattern[0] == pattern[-1]
        # Returning to the origin is not enough: an out-and-back or lollipop
        # pattern can revisit an interior stop and still need changing rider
        # guidance. A simple loop visits each stop once before closing.
        and len(pattern[:-1]) == len(set(pattern[:-1]))
    )


def _single_pattern_loop_headsign_exemptions(
    trips: list[dict[str, str]], stop_times: Iterable[dict[str, str]]
) -> set[str]:
    """Return trips where a blank ``trip_headsign`` is not an actionable gap.

    GTFS makes ``trip_headsign`` optional and says it should distinguish service
    patterns using rider-facing destination, direction, or "via" text. Copying a
    route name into the field is explicitly discouraged. A route whose trips all
    follow one closed stop pattern, one shape, and one direction has nothing for a
    blanket headsign recommendation to distinguish.

    The exemption is deliberately conservative: every trip on the route must
    omit the field and have the same complete loop evidence. Mixed headsigns,
    shapes, directions, stop patterns, or missing stop-time evidence retain the
    ordinary check.
    """
    trips_by_route: dict[str, list[dict[str, str]]] = {}
    for trip in trips:
        route_id = trip.get("route_id", "").strip()
        if route_id:
            trips_by_route.setdefault(route_id, []).append(trip)

    candidate_trip_ids = {
        trip.get("trip_id", "").strip()
        for route_trips in trips_by_route.values()
        if _has_loop_candidate_metadata(route_trips)
        for trip in route_trips
    }
    if not candidate_trip_ids:
        return set()
    patterns_by_trip = _trip_stop_patterns(stop_times, candidate_trip_ids)

    exempt: set[str] = set()
    for route_trips in trips_by_route.values():
        if _is_single_pattern_loop(route_trips, patterns_by_trip):
            exempt.update(trip.get("trip_id", "").strip() for trip in route_trips)
    return exempt


def completeness(gtfs_zip_path: str, fare_free: bool = False) -> CategoryResult:  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    """Score rider-facing completeness of a static GTFS feed.

    ``fare_free`` is set for agencies that run fare-free by policy: their feed
    carries no fare files by design, so the fares component is credited and the
    "no fare data" finding is replaced by a neutral note rather than docking the
    score. A deliberate policy is not a gap, the same way a missing realtime feed
    is shown neutrally.
    """
    tables = read_tables(
        gtfs_zip_path,
        [
            "stops.txt",
            "trips.txt",
            "agency.txt",
            "feed_info.txt",
            "fare_attributes.txt",
            "fare_products.txt",
        ],
    )
    stops, trips, agency = tables["stops.txt"], tables["trips.txt"], tables["agency.txt"]

    findings: list[Finding] = []
    # A component holds points (fraction * its weight) when measurable, or
    # None when the feed gave the pipeline nothing to check (issue #286).
    # None components drop out of both the score and the deduction math
    # below rather than scoring as a failure — the same not-measurable
    # pattern rt.py already uses for realtime components.
    parts: dict[str, float | None] = {}

    # Accessibility: wheelchair_boarding on stops (1 = accessible, 2 = not).
    # Blank or 0 means "unknown", which helps no rider plan a trip.
    wb = _fraction_with_value(stops, "wheelchair_boarding", {"1", "2"})
    # Track the share actually marked accessible (value 1), separate from the
    # share merely populated, so "100% populated" can't be read as "100%
    # accessible" and a blanket value-1 fill is visible for what it is.
    wb_accessible = _fraction_with_value(stops, "wheelchair_boarding", {"1"})
    # The share the agency itself marks NOT accessible (value 2). Reported as a
    # neutral equity signal, never collapsed into the populated share, so an
    # honest "this stop is not accessible" is visible rather than hidden inside
    # "populated". This is the agency's own data, so surfacing it is not shaming.
    wb_not_accessible = _fraction_with_value(stops, "wheelchair_boarding", {"2"})
    parts["wheelchair_stops"] = wb * WEIGHTS["wheelchair_stops"] if wb is not None else None
    if wb is not None and wb < 1.0:
        missing = round((1 - wb) * len(stops))
        findings.append(
            Finding(
                code="scorecard_wheelchair_boarding_unknown",
                severity="WARNING",
                count=missing,
                what=f"{missing} of {len(stops)} stops don't say whether a wheelchair "
                "user can board there.",
                why="Riders who use wheelchairs can't plan a trip when accessibility "
                "is marked 'unknown'; apps show no information at all.",
                fix="Set wheelchair_boarding to 1 (accessible) or 2 (not accessible) "
                "for every stop. A field survey can start with the busiest stops.",
                effort="A column in stops.txt; your scheduling software likely has it.",
                deduction=round((1 - wb) * WEIGHTS["wheelchair_stops"], 1),
            )
        )

    wa = _fraction_with_value(trips, "wheelchair_accessible", {"1", "2"})
    parts["wheelchair_trips"] = wa * WEIGHTS["wheelchair_trips"] if wa is not None else None
    if wa is not None and wa < 1.0:
        missing = round((1 - wa) * len(trips))
        findings.append(
            Finding(
                code="scorecard_wheelchair_accessible_unknown",
                severity="WARNING",
                count=missing,
                what=f"{missing} of {len(trips)} trips don't say whether the vehicle "
                "is wheelchair accessible.",
                why="Even with accessible stops, riders need to know the bus itself can take them.",
                fix="Set wheelchair_accessible on every trip. If every vehicle is "
                "accessible, this may be one default; otherwise use the value for each trip.",
                effort="A default or per-trip field in your export.",
                deduction=round((1 - wa) * WEIGHTS["wheelchair_trips"], 1),
            )
        )

    # Fares: either legacy fare_attributes or Fares v2 fare_products counts.
    has_fares = bool(tables["fare_attributes.txt"] or tables["fare_products.txt"])
    # A fare-free agency carries no fare files by design, so credit the component
    # and surface the policy as a zero-deduction note instead of docking it.
    fares_credited = has_fares or fare_free
    parts["fares"] = WEIGHTS["fares"] if fares_credited else 0.0
    if not has_fares and fare_free:
        findings.append(
            Finding(
                code="scorecard_fare_free",
                severity="INFO",
                count=1,
                what="This agency runs fare-free, so no fare data is expected.",
                why="Riders pay nothing to ride, so there is nothing to publish; "
                "the feed is complete as is.",
                fix="No action needed. If you later start charging a fare, add "
                "fare_attributes.txt or Fares v2 files.",
                effort="None.",
                deduction=0.0,
            )
        )
    elif not has_fares:
        findings.append(
            Finding(
                code="scorecard_no_fare_data",
                severity="WARNING",
                count=1,
                what="The feed contains no fare information.",
                why="Riders see 'fare unknown' in trip planners and can't budget "
                "their trip; visitors are most affected.",
                fix="Add fare_attributes.txt (or Fares v2 files) with your fare structure. "
                "If your service is fare-free, ask to have it marked fare-free instead.",
                effort="A small file for most flat-fare systems.",
                deduction=WEIGHTS["fares"],
            )
        )

    # Stop names readable (mixed case, per GTFS best practices).
    mixed = _fraction_mixed_case(stops, "stop_name")
    parts["stop_names"] = mixed * WEIGHTS["stop_names"] if mixed is not None else None
    if mixed is not None and mixed < 0.95:
        shouty = round((1 - mixed) * len(stops))
        findings.append(
            Finding(
                code="scorecard_stop_names_all_caps",
                severity="INFO",
                count=shouty,
                what=f"About {shouty} stop names are written in ALL CAPS.",
                why="Mixed-case names are easier to read in apps and are read "
                "more naturally by screen readers.",
                fix="Rename stops to mixed case where the language has letter case "
                "(for example, 'Central Station').",
                effort="Often a bulk fix in your scheduling software.",
                deduction=round((1 - mixed) * WEIGHTS["stop_names"], 1),
            )
        )

    # Headsigns on trips. Single-pattern, single-direction loops are credited
    # without inventing a direction label or copying the route name into a field
    # where GTFS Best Practices says it does not belong.
    headsign_trip_ids = {
        row.get("trip_id", "").strip() for row in trips if row.get("trip_headsign", "").strip()
    }
    loop_exempt_trip_ids: set[str] = set()
    if len(headsign_trip_ids) < len(trips):
        try:
            stop_times = iter_table_rows(
                gtfs_zip_path,
                "stop_times.txt",
                max_member_bytes=HEADSIGN_STOP_TIMES_MAX_BYTES,
            )
            loop_exempt_trip_ids = _single_pattern_loop_headsign_exemptions(trips, stop_times)
        except TableTooLargeError:
            # Preserve the ordinary check rather than failing scoring or
            # granting an exemption without inspecting complete evidence.
            loop_exempt_trip_ids = set()
    # None when there are no trips at all: nothing to check (issue #286),
    # not a feed that failed to publish any headsign.
    hs_published = len(headsign_trip_ids) / len(trips) if trips else None
    hs_scored = (len(headsign_trip_ids) + len(loop_exempt_trip_ids)) / len(trips) if trips else None
    parts["headsigns"] = hs_scored * WEIGHTS["headsigns"] if hs_scored is not None else None
    missing = len(trips) - len(headsign_trip_ids) - len(loop_exempt_trip_ids)
    # trips is non-empty whenever missing > 0, so hs_scored was computed above;
    # the None check narrows the type without a bare assert (S101).
    if missing and hs_scored is not None:
        findings.append(
            Finding(
                code="scorecard_missing_headsigns",
                severity="WARNING",
                count=missing,
                what=f"{missing} of {len(trips)} trips have no headsign, the text "
                "that tells riders where the bus is going.",
                why="When a route has multiple directions or patterns, the route "
                "name alone may not tell riders which service is coming.",
                fix="Add the destination, direction, or 'via' label riders actually "
                "see to trip_headsign. Do not copy the route name. If the label "
                "changes during the trip, use stop_headsign.",
                effort="Usually one value per route pattern in your scheduling source.",
                deduction=round((1 - hs_scored) * WEIGHTS["headsigns"], 1),
            )
        )

    # Contact: a working agency_url plus a feed contact (v4.0 Recommended).
    agency_url_ok = any(
        (row.get("agency_url") or "").strip().startswith(("http://", "https://")) for row in agency
    )
    feed_info = tables["feed_info.txt"][0] if tables["feed_info.txt"] else {}
    feed_contact_ok = bool(
        (feed_info.get("feed_contact_email") or "").strip()
        or (feed_info.get("feed_contact_url") or "").strip()
    )
    contact_fraction = (0.5 if agency_url_ok else 0.0) + (0.5 if feed_contact_ok else 0.0)
    parts["contact"] = contact_fraction * WEIGHTS["contact"]
    if not feed_contact_ok:
        findings.append(
            Finding(
                code="scorecard_no_feed_contact",
                severity="INFO",
                count=1,
                what="feed_info.txt has no technical contact (feed_contact_email or "
                "feed_contact_url).",
                why="App makers and state data programs have nobody to email when they "
                "spot a problem. Small errors then sit in the feed for months.",
                fix="Add feed_contact_email to feed_info.txt.",
                effort="One field.",
                deduction=round(0.5 * WEIGHTS["contact"], 1),
            )
        )
    if not agency_url_ok:
        findings.append(
            Finding(
                code="scorecard_bad_agency_url",
                severity="WARNING",
                count=1,
                what="agency.txt has no working website URL.",
                why="Trip planners link riders to this URL for schedules and fares.",
                fix="Set agency_url to your agency's website, starting with https://.",
                effort="One field.",
                deduction=round(0.5 * WEIGHTS["contact"], 1),
            )
        )

    # Flexible (demand-responsive) service: represent it and check that riders
    # can book it (ADR 0007). Zero-deduction in this slice, so the score and the
    # overall grade are unchanged; this is representation and guidance, not a
    # penalty. The validator already covers the flex files' structure.
    flex = detect_flex(gtfs_zip_path)
    findings.extend(flex_findings(flex))

    # Fare model: name what the feed publishes and catch fares that are published
    # but never applied to a trip (ADR 0008). Zero-deduction, so the grade is
    # unchanged; the fare-free opt-out suppresses fare findings entirely.
    fares = detect_fares(gtfs_zip_path)
    fares_detail = fares.to_details()
    if not fare_free:
        findings.extend(fares_findings(fares))
    else:
        fares_detail["fare_free"] = True

    # Station pathways and levels: relevant only to feeds that model stations, and
    # never a penalty for a flat stop-only feed (ADR 0009). Zero-deduction, so the
    # grade is unchanged; the validator covers the pathways graph structure.
    pathways = detect_pathways(gtfs_zip_path, stops)
    findings.extend(pathways_findings(pathways))

    # issue #286: reweight over only the components this feed gave the
    # pipeline something to measure, the same not-measurable pattern rt.py
    # uses. `fares` and `contact` are always measurable (presence-based, no
    # denominator), so this can only drop wheelchair_stops, wheelchair_trips,
    # stop_names, and headsigns — and only when their whole denominator (no
    # stops, or no trips) was empty.
    measured = {k: v for k, v in parts.items() if v is not None}
    unmeasured_components = sorted(k for k, v in parts.items() if v is None)
    measured_weight = sum(WEIGHTS[k] for k in measured)
    score = (
        max(0.0, min(100.0, sum(measured.values()) / measured_weight * 100.0))
        if measured_weight > 0
        else 0.0
    )

    def pct(fraction: float | None) -> float | None:
        return round(fraction * 100, 1) if fraction is not None else None

    if not has_fares and fare_free:
        fares_sentence = "This agency runs fare-free, so no fare data is expected."
    else:
        fares_sentence = f"Fare data {'is' if has_fares else 'is not'} published."
    if wb is None or wb_accessible is None or wb_not_accessible is None:
        # No stops at all (a demand-response/Flex-only feed, GTFS Best
        # Practices) — there is nothing to state accessibility about, so say
        # that rather than a fabricated "0% of stops". The three fractions
        # share the same `stops` input, so they are None together.
        summary = f"This feed has no stops to state wheelchair accessibility for. {fares_sentence}"
    else:
        summary = (
            f"{round(wb * 100)}% of stops state wheelchair accessibility "
            f"({round(wb_accessible * 100)}% marked accessible, "
            f"{round(wb_not_accessible * 100)}% marked not accessible). This measures what "
            f"the feed publishes, not whether a stop is physically usable. {fares_sentence}"
        )

    # Accessibility as its own 0-100 sub-score (ADR 0006): the accessibility
    # points earned over the weight actually measurable. None (not 0) when
    # neither wheelchair_stops nor wheelchair_trips could be measured at all.
    access_terms = [
        (WEIGHTS[k], measured_value)
        for k in ("wheelchair_stops", "wheelchair_trips")
        if (measured_value := parts.get(k)) is not None
    ]
    access_weight = sum(w for w, _ in access_terms)
    access_points = sum(v for _, v in access_terms)
    accessibility_score = (
        round(access_points / access_weight * 100, 1) if access_weight > 0 else None
    )

    return CategoryResult(
        name="completeness",
        score=score,
        summary=summary,
        findings=findings,
        details={
            "components": {k: (round(v, 1) if v is not None else None) for k, v in parts.items()},
            # issue #286's confidence signal: which components this feed gave
            # the pipeline nothing to measure, so a reader (or another tool)
            # can tell "not measured" apart from "measured and scored low"
            # without inferring it from an absent finding.
            "unmeasured_components": unmeasured_components,
            "stops": len(stops),
            "trips": len(trips),
            "wheelchair_boarding_pct": pct(wb),
            "wheelchair_marked_accessible_pct": pct(wb_accessible),
            "wheelchair_marked_not_accessible_pct": pct(wb_not_accessible),
            "wheelchair_accessible_pct": pct(wa),
            # Accessibility fields record published values, not a check that a
            # stop is physically usable; consumers should not read a high score
            # as verified accessibility.
            "accessibility_measures": "presence_not_usability",
            "accessibility": {
                "score": accessibility_score,
                "stops_stated_pct": pct(wb),
                "stops_marked_accessible_pct": pct(wb_accessible),
                "stops_marked_not_accessible_pct": pct(wb_not_accessible),
                "trips_stated_pct": pct(wa),
                "measures": "presence_not_usability",
            },
            "has_fares": has_fares,
            "fare_free": fare_free,
            "fares": fares_detail,
            "flex": flex.to_details(),
            "pathways": pathways.to_details(),
            "cemv": detect_cemv(gtfs_zip_path).to_details(),
            # Optional rider-facing translations are an adoption signal, not a
            # score component. Their absence never lowers this category.
            "translations": detect_translations(gtfs_zip_path).to_details(),
            "headsign_pct": pct(hs_published),
            "headsign_scored_pct": pct(hs_scored),
            "headsign_applicable_trips": len(trips) - len(loop_exempt_trip_ids),
            "headsign_loop_exempt_trips": len(loop_exempt_trip_ids),
            "mixed_case_stop_name_pct": pct(mixed),
        },
    )
