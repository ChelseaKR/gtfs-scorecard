"""Rider experience completeness: the fields riders feel directly.

Based on portable GTFS fields and Best Practices, with the California Transit
Data Guidelines documented as one source in the published scoring profile (see
docs/rubric.md "Rider experience completeness"). Accessibility fields carry
the most weight on purpose: they are both a values statement and a common gap
in small-agency feeds.
"""

from __future__ import annotations

from .cemv import detect_cemv
from .fares import detect_fares, fares_findings
from .flex import detect_flex, flex_findings
from .gtfs import read_tables
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


def _fraction_with_value(rows: list[dict[str, str]], field: str, allowed: set[str]) -> float:
    if not rows:
        return 0.0
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


def _fraction_mixed_case(rows: list[dict[str, str]], field: str) -> float:
    """Share of rows whose name reads like a name, not LIKE THIS."""
    named = [row[field].strip() for row in rows if row.get(field, "").strip()]
    if not named:
        return 0.0
    return sum(1 for name in named if not _is_shouty(name)) / len(named)


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
    parts: dict[str, float] = {}

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
    parts["wheelchair_stops"] = wb * WEIGHTS["wheelchair_stops"]
    if wb < 1.0:
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
    parts["wheelchair_trips"] = wa * WEIGHTS["wheelchair_trips"]
    if wa < 1.0:
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
    parts["stop_names"] = mixed * WEIGHTS["stop_names"]
    if mixed < 0.95:
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

    # Headsigns on trips.
    hs = (
        sum(1 for row in trips if row.get("trip_headsign", "").strip()) / len(trips)
        if trips
        else 0.0
    )
    parts["headsigns"] = hs * WEIGHTS["headsigns"]
    if hs < 1.0:
        missing = round((1 - hs) * len(trips))
        findings.append(
            Finding(
                code="scorecard_missing_headsigns",
                severity="WARNING",
                count=missing,
                what=f"{missing} of {len(trips)} trips have no headsign.",
                why="Riders at the stop can't tell which direction a bus is going.",
                fix="Populate trip_headsign to match what the bus displays.",
                effort="Usually a bulk edit in your scheduling software.",
                deduction=round((1 - hs) * WEIGHTS["headsigns"], 1),
            )
        )

    # Contact: a working agency_url plus a feed contact (v4.0 Recommended).
    agency_url_ok = any(
        row.get("agency_url", "").strip().startswith(("http://", "https://")) for row in agency
    )
    feed_info = tables["feed_info.txt"][0] if tables["feed_info.txt"] else {}
    feed_contact_ok = bool(
        feed_info.get("feed_contact_email", "").strip()
        or feed_info.get("feed_contact_url", "").strip()
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
                why="Trip-planning apps and regional data coordinators have nobody to email when "
                "they spot a problem with your feed, so problems linger.",
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

    score = max(0.0, min(100.0, sum(parts.values())))
    accessibility_pct = round(wb * 100)
    marked_accessible_pct = round(wb_accessible * 100)
    not_accessible_pct = round(wb_not_accessible * 100)
    if not has_fares and fare_free:
        fares_sentence = "This agency runs fare-free, so no fare data is expected."
    else:
        fares_sentence = f"Fare data {'is' if has_fares else 'is not'} published."
    summary = (
        f"{accessibility_pct}% of stops state wheelchair accessibility "
        f"({marked_accessible_pct}% marked accessible, {not_accessible_pct}% marked not "
        "accessible). This measures what the feed publishes, not whether a stop is "
        f"physically usable. {fares_sentence}"
    )
    return CategoryResult(
        name="completeness",
        score=score,
        summary=summary,
        findings=findings,
        details={
            "components": {k: round(v, 1) for k, v in parts.items()},
            "stops": len(stops),
            "trips": len(trips),
            "wheelchair_boarding_pct": round(wb * 100, 1),
            "wheelchair_marked_accessible_pct": round(wb_accessible * 100, 1),
            "wheelchair_marked_not_accessible_pct": round(wb_not_accessible * 100, 1),
            "wheelchair_accessible_pct": round(wa * 100, 1),
            # Accessibility fields record published values, not a check that a
            # stop is physically usable; consumers should not read a high score
            # as verified accessibility.
            "accessibility_measures": "presence_not_usability",
            # Accessibility as its own 0-100 sub-score (ADR 0006): the
            # accessibility points earned over the 40 available. A lens on the
            # math above, not a new category; the overall grade is unchanged.
            "accessibility": {
                "score": round(
                    (parts["wheelchair_stops"] + parts["wheelchair_trips"])
                    / (WEIGHTS["wheelchair_stops"] + WEIGHTS["wheelchair_trips"])
                    * 100,
                    1,
                ),
                "stops_stated_pct": round(wb * 100, 1),
                "stops_marked_accessible_pct": round(wb_accessible * 100, 1),
                "stops_marked_not_accessible_pct": round(wb_not_accessible * 100, 1),
                "trips_stated_pct": round(wa * 100, 1),
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
            "headsign_pct": round(hs * 100, 1),
            "mixed_case_stop_name_pct": round(mixed * 100, 1),
        },
    )
