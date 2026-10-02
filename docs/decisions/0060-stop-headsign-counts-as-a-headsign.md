# ADR 0060: A stop_headsign at every stop counts as a headsign

**Status:** Accepted (2026-10-01)

## Context

The headsign component of rider-experience completeness (15 points) counted a
trip as headed only when `trips.trip_headsign` was non-empty.
`stop_times.stop_headsign` appeared only in the fix text.

TriMet publishes its destinations the other way. Its feed of 2026-09-24
(`feed_version` 20260913-20260924-0900, downloaded from
developer.trimet.org/schedule/gtfs.zip on 2026-10-01) leaves `trip_headsign`
blank on all 67,510 trips and fills `stop_headsign` on all 3,402,538 stop
times. The scorecard reported 0% headsigns, deducted the full 15 points, and
made "missing headsigns on every trip" TriMet's top fix. Riders using that feed
see a destination at every stop, so the finding was a false negative of the
same kind ADR 0041 corrected for loops.

What the sources say:

- The GTFS Schedule
  [reference](https://gtfs.org/documentation/schedule/reference/#stop_timestxt)
  defines `stop_headsign` as "Text that appears on signage identifying the
  trip's destination to riders", the same definition as `trip_headsign`, and
  says it "overrides the default `trips.trip_headsign` when the headsign
  changes between stops." It also says "A `stop_headsign` value specified for
  one `stop_time` does not apply to subsequent `stop_time`s in the same trip."
- The same reference says "If the headsign is displayed for an entire trip,
  `trips.trip_headsign` should be used instead." That is a recommendation about
  where the text lives, not a statement that a trip without it lacks a
  headsign.
- The California Transit Data Guidelines v4.0 (Service Accuracy, a Caltrans
  Check item) ask that "trip headsigns" match what riders see on vehicles and
  infrastructure. They name the concept, not a field.

## Decision

A trip counts toward the headsign component when either:

- `trip_headsign` is non-empty; or
- every one of the trip's rows in `stop_times.txt` has a non-empty
  `stop_headsign`.

"Every row" follows from the reference: a `stop_headsign` covers only its own
stop, so one blank row is a stop where the rider sees no destination. A trip
with no stop times at all earns nothing through this path. The ADR 0041 loop
exemption still applies to the trips left over, and a trip is counted once
whichever path credits it.

The pass streams `stop_times.txt` and keeps only the IDs of trips that lack
`trip_headsign`, so its memory is bounded by the trip count. It therefore runs
without the 64 MiB cap the loop analysis uses; TriMet's table is 227 MB
uncompressed and would otherwise fall back to the old check. A table with no
`stop_headsign` column stops reading after its first row.

Artifacts keep `headsign_pct` as the literal `trip_headsign` share, as ADR 0041
established, and add `headsign_stop_headsign_trips`, the count of trips credited
through `stop_headsign`. `headsign_scored_pct` is the share the score uses. The
remaining finding now says what counts: `trip_headsign`, or a `stop_headsign`
at every stop.

This is a change to what is measured, so the rubric moves to 1.4
(`gtfs-scorecard-1.4`).

## Consequences

- TriMet, scored on the 2026-10-01 download with validator 8.0.1: headsigns
  move from 0% to 100% scored (0% literal), rider experience from 85.0 to
  100.0, and the overall score from B 85.1 to B 89.8, 0.2 below an A. The headsign fix leaves
  its top three.
- Feeds that fill `stop_headsign` on only some stops of a trip are unchanged.
  Partial per-stop text still leaves stops with no destination.
- The scorecard does not ask a producer that uses `stop_headsign` everywhere to
  move constant text into `trip_headsign`. The reference's "should" is a
  modelling preference; riders see the same text either way, and a scoring
  penalty for it would be about authoring style rather than rider information.
- The stop-time pass reads one more large table per feed that lacks
  `trip_headsign` and has a `stop_headsign` column. It is a single streamed
  read; the validator already reads the same table.

## Alternatives rejected

- **Credit a trip when any stop time has `stop_headsign`.** A single row
  covers a single stop, so this would credit trips where most stops show no
  destination.
- **Keep the 64 MiB cap for this pass too.** The cap exists because the loop
  analysis retains stop patterns. This pass retains trip IDs only, and the cap
  would leave exactly the large feeds that use `stop_headsign` with the false
  negative.
- **Require `trip_headsign` and add a zero-point note for per-stop text.** The
  reference allows per-stop text, Caltrans does not name a field, and riders
  are served. Scoring the field location would repeat the error ADR 0041 fixed.
