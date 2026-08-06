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
    # These three had published fix guides in docs/fixes/ and no entry here, so every scorecard
    # showed the generic validator fallback for them while the plain language sat written and
    # shipped a directory away. missing_timepoint_value alone is 58.4% of all finding instances in
    # the national corpus, so the single most common thing an agency saw was the one line this
    # table exists to replace. A test now asserts that a fix page implies a curated entry.
    "missing_timepoint_value": Translation(
        what="Some rows in stop_times.txt leave the timepoint column blank.",
        why="That column says whether a time is a real checkpoint or an estimate. "
        "Blank leaves apps guessing, and they may show your estimates as promises.",
        fix="Set timepoint=1 on stops that are real time checks and 0 on the rest. "
        "If every published time is a scheduled one, mark them all 1.",
        effort="Usually one export setting.",
    ),
    "fast_travel_between_far_stops": Translation(
        what="Between two distant stops, the times imply a speed no bus reaches.",
        why="A rider gets a trip plan that cannot happen. Live systems then "
        "report delays that are not real.",
        fix="Check the two stop times for a wrong digit first. Then check whether a "
        "stop sits at the wrong coordinates, or a stop between them is missing.",
        effort="Minutes per flagged trip once you open it.",
    ),
    "invalid_currency_amount": Translation(
        what="A fare amount has the wrong number of decimals for its currency.",
        why="Apps may reject the amount or show a price off by a factor of ten. "
        "US dollars take two decimals, so 2.5 is wrong where 2.50 is meant.",
        fix="Write every amount with the decimals its currency takes, and check "
        "that currency_type is the right ISO code.",
        effort="A quick edit of the fare file.",
    ),
    # Added from a corpus-frequency scan of scored feeds: the untranslated
    # validator notices that showed up across the most distinct agencies, so the
    # generic fallback stopped covering the codes agencies actually hit.
    "unknown_file": Translation(
        what="The feed includes a file that is not part of the GTFS spec.",
        why="Apps ignore files they don't know, and a stray file can hide a "
        "misspelled standard file name.",
        fix="Check the flagged file name for a typo of a standard GTFS file. "
        "Remove it if it is a vendor extra.",
        effort="A quick look at the flagged file.",
    ),
    "service_window_outside_feed_period": Translation(
        what="Some service dates fall outside the date window set in feed_info.txt.",
        why="feed_info.txt should span every day your service runs, so apps know "
        "when the data applies.",
        fix="Widen feed_start_date and feed_end_date to cover all service dates, "
        "or fix the dates that fall outside.",
        effort="Two fields in feed_info.txt, or one export setting.",
    ),
    "missing_feed_contact_email_and_url": Translation(
        what="feed_info.txt lists no contact email and no contact URL.",
        why="Without a contact, apps like Google Maps can't reach you when they "
        "find a problem in the feed.",
        fix="Add feed_contact_email or feed_contact_url to feed_info.txt.",
        effort="One field, set once in export settings.",
    ),
    "stop_too_far_from_shape_using_user_distance": Translation(
        what="Some stops sit far from the route line, going by the feed's own distance values.",
        why="Trip planners may draw the route down the wrong streets or point "
        "riders to the wrong corner.",
        fix="Check the flagged stops' shape_dist_traveled against the route "
        "shape, and re-generate it on export if they disagree.",
        effort="Usually an export-tool fix, not hand editing.",
    ),
    "big_gap_in_service": Translation(
        what="The feed has a stretch of two weeks or more with no service running.",
        why="A long gap can mean dates were left out of the calendar. Apps then "
        "show no trips on those days.",
        fix="Check whether the gap is real, like a seasonal break; if not, add "
        "the missing dates to the calendar.",
        effort="A review of your calendar dates.",
    ),
    "missing_required_column": Translation(
        what="A file is missing a column that GTFS requires.",
        why="Apps may reject the whole file, so riders could lose the affected routes or stops.",
        fix="Add the required column named in the finding to the flagged file.",
        effort="Often an export setting; ask your vendor if it recurs.",
    ),
    "equal_shape_distance_same_coordinates": Translation(
        what="Some route lines list the same point twice in a row.",
        why="Repeated points don't hurt riders, but they can skew distance math "
        "and hint at a shaky export.",
        fix="Turn on shape cleanup in your export tool, or drop the repeated "
        "points from shapes.txt.",
        effort="Usually one export setting.",
    ),
    "trip_distance_exceeds_shape_distance_below_threshold": Translation(
        what="On some trips the stop distances run a little past the end of the route line.",
        why="The stop and shape distance values don't quite line up, so any math "
        "that uses them can drift.",
        fix="Re-generate shape_dist_traveled on export so stop and shape "
        "distances use the same units.",
        effort="Usually an export-tool fix, not hand editing.",
    ),
    "route_long_name_contains_short_name": Translation(
        what="Some route long names repeat the route's short name inside them.",
        why="Apps show both names together, so riders see the number twice, like '5 5 Downtown'.",
        fix="Drop the short name from route_long_name and keep the long name "
        "descriptive, like 'Downtown via 5th Ave'.",
        effort="One field per flagged route.",
    ),
    "stops_match_shape_out_of_order": Translation(
        what="On some trips the stops fall along the route line in a different "
        "order than the schedule lists.",
        why="Trip planners can draw the bus doubling back or skipping ahead, "
        "which confuses riders reading the map.",
        fix="Check the stop order and the shape direction in your scheduling "
        "software; the shape is often drawn backwards.",
        effort="A few minutes per flagged trip.",
    ),
    "leading_or_trailing_whitespaces": Translation(
        what="Some values have extra spaces at the start or end.",
        why="A stray space can break a match, so a stop or route may fail to link across files.",
        fix="Trim leading and trailing spaces on export. The scorecard's "
        "auto-fixed copy already does this.",
        effort="Usually one export setting.",
    ),
    "trip_headsign_matches_intermediate_stop": Translation(
        what="Some trip headsigns name a stop along the way, not the final destination.",
        why="The sign should tell riders where the bus ends up, so a midpoint "
        "name can send them the wrong way.",
        fix="Set trip_headsign to the trip's last stop or its overall destination.",
        effort="Usually a bulk edit in your scheduling software.",
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
