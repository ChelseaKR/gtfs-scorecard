# How the grade maps to the standards

The scorecard's four categories are its own. The grade and thresholds do not
change by country. This page separates the universal GTFS references behind the
quality lens from jurisdiction guidance that applies only in a particular place.

This is a crosswalk, not a compliance determination. A category being strong here
does not certify a feed against any guideline, and a weak one does not fail it.
For the official assessment, use the sources linked below.

## The standards

The agency page builds its guidance in layers. Every agency receives the
universal GTFS layer. A US agency also receives the FTA National Transit Database
layer. California receives its published state guideline, while selected state
programs are labelled as support resources rather than scoring authorities.

### Universal GTFS layer

- **[GTFS Schedule Best Practices](https://gtfs.org/schedule/best-practices/)**
  and **[GTFS-Realtime Best Practices](https://gtfs.org/realtime/best-practices/)**
  describe useful, interoperable rider information. They apply regardless of
  country.
- The [MobilityData GTFS Grading Scheme](https://github.com/MobilityData/gtfs-grading-scheme)
  is a qualitative check of rider-facing values against the real world. The
  scorecard automates narrower presence and plausibility proxies; it does not
  replace that human review.
- Trip-planner publication expectations explain why validation and current
  calendars matter to riders. They are operational context, not a legal standard.

### United States overlay

- **The [FTA National Transit Database](https://www.transit.dot.gov/ntd) GTFS
  requirement.** Since Report Year 2023, every NTD reporter with fixed-route
  service must publish and maintain a valid, public GTFS feed and certify it
  annually. For RY2026, every submission must also provide a stable `agency_id`
  value for each represented reporter, unique among those reporters, and
  crosswalk it to the reporter's NTD ID on P-50. The value does not have to equal
  the five-digit NTD ID. The scorecard treats presence as a readiness check and
  shows equality only as a neutral, zero-deduction comparison. This nationwide
  layer tracks the scorecard's Correctness and Freshness categories but does not
  change their grades.
### State and provincial overlays

- **A jurisdiction's own guideline, where one has been mapped.** California is
  currently the only US state with a formal published GTFS quality *guideline*:
  the [California Transit Data Guidelines](https://dot.ca.gov/cal-itp/california-transit-data-guidelines)
  and [Minimum GTFS Guidelines](https://dot.ca.gov/cal-itp/california-minimum-general-transit-feed-specification-gtfs-guidelines-v2_0),
  which define "Features" under GTFS Schedule, Realtime, and Data Availability and
  a ten-point checklist. This scorecard's rubric is anchored to them, so for
  California agencies it is shown as the guideline the score maps to.
  Other states (Colorado, Michigan, Minnesota, Oregon, Washington) run GTFS
  *programs* rather than a quality rubric. Their links are shown as support
  resources, explicitly not as authorities that set or certify the score.
- No Canadian federal or provincial compliance overlay is claimed yet. Canadian
  agencies receive the universal GTFS layer, and never the US NTD layer. A future
  Canadian overlay must cite the responsible authority before it is added.

The source-of-truth records live in
`pipeline/src/scorecard_pipeline/jurisdiction_guidance.py`. The browser constants
are generated from that Python module, so static and interactive pages use the
same applicability rules.

## The Grading Scheme's seven fields, mapped

The [MobilityData GTFS Grading Scheme](https://github.com/MobilityData/gtfs-grading-scheme)
(v1.0.0) grades seven rider-facing fields by hand, comparing each against a source
of truth (the agency website, street imagery). The scorecard automates a proxy
for every one of them. The methods differ on purpose: the scheme verifies that a
value is *accurate against the real world*, which needs a human; the scorecard
checks that a value is *present, legible, and internally plausible*, which a
machine can do daily. The scorecard is the automated complement to the scheme,
not a replacement for its accuracy checks.

| Grading Scheme field | The scheme checks (by hand) | The scorecard's automated proxy |
|---|---|---|
| `route_short_name` | matches on-street signage | Correctness: validator route-name notices |
| `route_long_name` | matches official route documentation | Correctness: `missing_route_long_name` and related notices |
| `route_color` | matches on-the-ground signage | Correctness: `route_color_contrast` (the published color is legible) |
| `route_text_color` | legible against the route color | Correctness: `route_color_contrast` |
| `stop_name` | matches the real stop (`location_type=0`) | Rider experience: readable (mixed-case) stop names; Correctness: name notices |
| `stop_lat` / `stop_lon` | the coordinate is the real location | Correctness: stop-too-far-from-shape; Realtime: position plausibility |
| `trip_headsign` | matches the destination the bus displays | Rider experience: headsign presence |

Beyond these seven, the scorecard also grades accessibility, fares, feed
freshness, and realtime, which the scheme does not address. So it covers every
field the scheme does (automatically, as a proxy) and four dimensions it does not.

## Category by category

### Correctness (35%)

What it measures: structural and semantic problems from the
[MobilityData GTFS validator](https://gtfs-validator.mobilitydata.org/rules.html),
weighted by severity.

- **California Guidelines:** the GTFS Schedule expectation that the feed
  implements the specification per industry best practices. Validator-clean is
  the floor for most Schedule Features.
- **Grading Scheme:** carries the automated proxy for most of the scheme's
  fields (see the seven-field table above): `stop_lat`/`stop_lon` via
  stop-far-from-street-location notices, and `route_color`/`route_text_color`
  and the route names via the validator's color-contrast and route-name notices.
- **Google Transit:** a feed has to pass validation to be accepted and kept in
  Maps, so validator errors here are the same ones that risk the listing.

### Freshness (20%)

What it measures: a present and current `feed_info` validity window, calendar
coverage for the weeks ahead, and days until the service data expires.

- **California Guidelines:** "keep GTFS Schedule up to date and consistent," and
  the Data Availability expectation of a stable, current feed at a fixed URL. This
  is the category closest to the compliance threshold: an expired feed drops the
  agency off the map, which is the failure the Guidelines exist to prevent.
- **Grading Scheme:** not covered (the scheme assesses accuracy, not currency),
  so this category is additive to it.
- **Google Transit:** an expired calendar is one of the clearest ways to fall
  out of Maps, so this is the category that most directly protects the listing.

### Rider experience (25%)

What it measures: accessibility fields populated (`wheelchair_boarding`), fares
present, human-readable stop names, headsigns, and valid agency contact details.

- **California Guidelines:** the expectation that riders get complete and accurate
  information including fare, pathway, accessibility, and geographic data, so
  anyone can plan a trip regardless of familiarity or access needs.
- **Grading Scheme:** directly overlaps the rider-facing-accuracy dimensions —
  `stop_name`, `route_short_name`/`route_long_name`, and `trip_headsign`. Note the
  difference in method: the scheme compares values against real-world signage by
  hand; the scorecard checks presence and plausibility automatically. The
  accessibility and fare parts of this category go beyond the grading scheme,
  which does not assess them.

### Realtime quality (20%)

What it measures: each configured GTFS-Realtime feed reachable, header freshness
for configured TripUpdates and VehiclePositions feeds, the share of scheduled
trips represented when TripUpdates is configured, and plausible vehicle
positions when VehiclePositions is configured. Unpublished feed kinds are
neutral. Shown neutrally as "Not yet published" when an agency has no realtime
feed.

- **California Guidelines:** the GTFS Realtime Features — standard formats at a
  stable URL, with high uptime and update frequency.
- **Grading Scheme:** not covered (Schedule only).

## Where the scorecard and the standards differ

- The scorecard's automated run is scheduled daily, and its public status page
  records when each run actually completes. The Grading Scheme's accuracy checks
  are manual by design. The scorecard approximates them, it does not replace them.
- The scorecard weights and grades; the California Guidelines are pass/fail per
  Feature. A good grade is encouragement toward the Features, not a substitute for
  the official checklist.
- Accessibility and fares are first-class in the scorecard's Rider-experience
  category and absent from the Grading Scheme, which is a deliberate emphasis.
