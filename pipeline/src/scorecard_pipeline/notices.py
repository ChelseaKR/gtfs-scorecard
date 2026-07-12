"""Plain-language translations of gtfs-validator notice codes.

Every translated notice answers three questions for a non-developer transit
manager: what is wrong, why a rider cares, and what to do about it. Codes
without a curated entry fall back to a readable generic line that links to
the validator's rule documentation.

Curated set: the notices small agencies hit most often, drawn from the
validator's RULES.md taxonomy. Grow this table as pilot feeds surface new
codes; never ship a metric without its explanation (CLAUDE.md quality bar).
"""

from __future__ import annotations

from dataclasses import dataclass

RULES_URL = "https://gtfs-validator.mobilitydata.org/rules.html"


@dataclass(frozen=True)
class Translation:
    """Practitioner-facing wording for one notice code."""

    what: str  # what is wrong, plainly
    why: str  # why a rider or the agency should care
    fix: str  # imperative, concrete next step
    effort: str  # rough effort hint shown next to the fix


TRANSLATIONS: dict[str, Translation] = {
    "feed_expiration_date7_days": Translation(
        what="This feed's service calendar runs out within the next 7 days.",
        why="When the calendar ends, Google Maps and other trip planners drop "
        "your agency entirely. Riders see no service at all.",
        fix="Export and publish an updated GTFS feed that covers at least the "
        "next 30 days of service.",
        effort="Usually a re-export from your scheduling software.",
    ),
    "feed_expiration_date30_days": Translation(
        what="This feed's service calendar runs out within the next 30 days.",
        why="If a new feed isn't published before it ends, trip planners will "
        "drop your agency and riders will see no service.",
        fix="Schedule a feed re-export now so the new calendar is live well "
        "before the current one ends.",
        effort="Usually a re-export from your scheduling software.",
    ),
    "expired_calendar": Translation(
        what="Some service calendars in the feed have already ended.",
        why="Expired calendars are dead weight and can hide real schedule "
        "problems from your staff and vendors.",
        fix="Remove past service periods the next time you export the feed.",
        effort="One setting in most export tools.",
    ),
    "missing_feed_info_date": Translation(
        what="feed_info.txt does not state when this feed starts and ends.",
        why="Without stated dates, apps can't warn anyone before your data "
        "goes stale; it just disappears one day.",
        fix="Fill in feed_start_date and feed_end_date in feed_info.txt.",
        effort="Two fields, likely set once in your export settings.",
    ),
    "stop_too_far_from_shape": Translation(
        what="Some stops sit far from the route line they belong to.",
        why="Trip planners may draw the bus route through the wrong streets "
        "or point riders to the wrong corner.",
        fix="Check the flagged stops' coordinates and the route shape in your "
        "scheduling software; re-snap whichever is misplaced.",
        effort="A few minutes per flagged stop.",
    ),
    "stop_without_location": Translation(
        what="Some stops have no latitude/longitude.",
        why="Riders can't find these stops on any map.",
        fix="Add coordinates for the flagged stops.",
        effort="A few minutes per stop with a map open.",
    ),
    "missing_trip_headsign": Translation(
        what="Some trips have no headsign (the destination text on the bus).",
        why="Riders at the stop can't tell which direction a bus is going.",
        fix="Populate trip_headsign for the flagged trips, matching what the "
        "bus actually displays.",
        effort="Usually a bulk edit in your scheduling software.",
    ),
    "missing_route_long_name": Translation(
        what="Some routes are missing a descriptive long name.",
        why="Apps fall back to bare route numbers, which mean little to visitors and new riders.",
        fix="Add a route_long_name (e.g. 'Downtown – Campus Loop') for the flagged routes.",
        effort="One field per route.",
    ),
    "route_color_contrast": Translation(
        what="Some route colors don't contrast with their text color.",
        why="Route badges get hard to read, most of all for riders with low vision.",
        fix="Pick a darker/lighter route_text_color for the flagged routes.",
        effort="One field per route.",
    ),
    "duplicate_route_name": Translation(
        what="Two or more routes share the same name.",
        why="Riders can't tell the routes apart in apps.",
        fix="Give each route a distinct short or long name.",
        effort="One field per route.",
    ),
    "unusable_trip": Translation(
        what="Some trips serve fewer than two stops.",
        why="A trip with one stop can't be ridden; planners ignore it and it "
        "may signal an export problem.",
        fix="Check the flagged trips in your scheduling software; remove them "
        "or restore their missing stops.",
        effort="Worth a vendor question if it appears often.",
    ),
    "unused_shape": Translation(
        what="The feed contains route shapes no trip uses.",
        why="Harmless to riders, but it bloats the feed and suggests stale export data.",
        fix="Turn on 'remove unused shapes' (or the like) in your export tool.",
        effort="One setting.",
    ),
    "unused_stop": Translation(
        what="Some stops in the feed are not served by any trip.",
        why="Riders may walk to a stop where no bus will ever arrive.",
        fix="Remove retired stops from the export, or reconnect them to "
        "trips if they should still be served.",
        effort="A review pass in your scheduling software.",
    ),
    "stop_without_stop_time": Translation(
        what="Some stops exist in the feed but no trip ever stops at them.",
        why="Riders may walk to a stop where no bus is scheduled to arrive.",
        fix="Remove retired stops from the export, or add them back to the "
        "trips that should serve them.",
        effort="A review pass in your scheduling software.",
    ),
    "service_has_no_active_day_of_the_week": Translation(
        what="Some service calendars have no days of the week switched on.",
        why="Trips tied to these calendars never run; they are dead data "
        "that can mask real schedule problems.",
        fix="Delete the empty calendars or set their service days.",
        effort="A few minutes in your scheduling software.",
    ),
    "trip_coverage_not_active_for_next7_days": Translation(
        what="Many of the feed's trips don't run at all in the next 7 days.",
        why="It usually means old service periods are still in the export, "
        "making the feed bigger and harder to check.",
        fix="Trim past service periods the next time you export.",
        effort="One setting in most export tools.",
    ),
    "unknown_column": Translation(
        what="Some files contain columns that are not part of the GTFS spec.",
        why="Harmless to riders, but apps ignore these columns and they can "
        "hide typos in real column names.",
        fix="Check the flagged column names for misspellings of standard "
        "GTFS fields; remove them if they are vendor extras.",
        effort="A quick look at the flagged files.",
    ),
    "mixed_case_recommended_field": Translation(
        what="Some rider-facing names are in ALL CAPS or all lowercase.",
        why="ALL-CAPS stop and headsign names are harder to read in apps "
        "and are read awkwardly by screen readers.",
        fix="Use mixed case for stop names and headsigns (e.g. 'Main St & "
        "2nd Ave', not 'MAIN ST & 2ND AVE').",
        effort="Often a bulk fix in your scheduling software.",
    ),
    "non_ascii_or_non_printable_char": Translation(
        what="Some internal IDs use characters outside the basic text set.",
        why="These IDs are valid UTF-8 data. This warning is only about support in older "
        "apps. It does not mean that names in other languages are wrong.",
        fix="Only change the flagged IDs if an app needs basic ASCII values. Update each place "
        "that uses the ID. Keep all names and headsigns in their original language.",
        effort="A planned ID change, not a quick text cleanup.",
    ),
    "missing_recommended_file": Translation(
        what="A file GTFS asks for (usually feed_info.txt) is missing.",
        why="feed_info.txt tells apps who publishes the feed and when it "
        "expires; without it nobody is warned before data goes stale.",
        fix="Add feed_info.txt with publisher name, URL, language, and "
        "feed_start_date/feed_end_date.",
        effort="One small file, set once in export settings.",
    ),
    "missing_recommended_field": Translation(
        what="Some files leave out fields that GTFS asks for but does not require.",
        why="Recommended fields like agency_phone or stop descriptions make "
        "the feed more useful to riders and trip planners.",
        fix="Review the flagged fields and fill in the ones your riders would use.",
        effort="A field at a time; not urgent.",
    ),
    "decreasing_or_equal_stop_time_distance": Translation(
        what="Some trips have stop times whose distances along the route go backwards.",
        why="Apps can show buses jumping backwards or mis-order stops.",
        fix="Re-generate shape distances in your export; flag to your vendor if it persists.",
        effort="Usually an export-tool fix, not hand editing.",
    ),
    "fast_travel_between_consecutive_stops": Translation(
        what="Some scheduled trips move faster between stops than a bus can.",
        why="Usually a typo'd stop time; riders get arrival times no bus can meet.",
        fix="Check the flagged stop times for transposed minutes.",
        effort="A few minutes per flagged trip.",
    ),
}


def humanize_code(code: str) -> str:
    """Turn a snake_case notice code into a readable phrase."""
    return code.replace("_", " ").strip().capitalize()


def translate(code: str) -> Translation:
    """Curated translation for a code, or a readable generic fallback."""
    if code in TRANSLATIONS:
        return TRANSLATIONS[code]
    return Translation(
        what=f"{humanize_code(code)} (flagged by the MobilityData validator).",
        why="See the linked rule for what this affects.",
        fix=f"Review the rule documentation for '{code}' at {RULES_URL} and "
        "check the flagged rows in your feed.",
        effort="Varies.",
    )
