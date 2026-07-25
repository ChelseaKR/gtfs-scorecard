# ADR 0041: Headsign scoring excludes provably unambiguous loops

**Status:** Accepted (2026-07-24)

## Context

Issue [#180](https://github.com/ChelseaKR/gtfs-scorecard/issues/180)
returned a generic instruction to populate `trip_headsign` for MRC de
Joliette. The feed producer explained that routes A, B, C, D, E, and X are
one-way loops and that copying their route names into `trip_headsign` would be
wrong.

The published feed supported that explanation. Its 164 trips included 152
linear trips with headsigns and 12 blank loop templates. Each affected route
had one closed stop pattern, one shape, and one `direction_id`. The scorecard
nevertheless treated every blank as incomplete, deducted 1.1 points from the
rider-experience category, and presented the generated instruction as a fix.

That instruction exceeded the evidence. The GTFS Schedule
[reference](https://gtfs.org/documentation/schedule/reference/#tripstxt) makes
`trip_headsign` optional and recommends it when vehicle-displayed text
distinguishes trips on a route. GTFS Schedule
[Best Practices](https://gtfs.org/documentation/schedule/schedule-best-practices/#tripstxt)
says not to copy `route_short_name` or `route_long_name` into a headsign and
makes consistency with rider-facing vehicle signage the overriding goal. The
[loop-route guidance](https://gtfs.org/documentation/schedule/schedule-best-practices/#loop-routes)
uses `stop_headsign` when useful destination text changes around a loop.

## Decision

Keep headsigns as a 15-point rider-experience component, but credit a blank
`trip_headsign` when the feed itself proves that the route is an unambiguous
loop. Every trip on that route must:

- omit `trip_headsign`;
- start and end at the same stop;
- use the same complete stop sequence without revisiting an internal stop;
- use one shape; and
- use one `direction_id`.

Any mixed headsign population, missing stop-time evidence, second shape,
second direction, distinct stop pattern, or out-and-back sequence keeps the
ordinary check. This is a narrow evidence rule, not a general loop exemption.
The stop-time evidence is streamed and limited to 64 MiB uncompressed. A
larger table keeps the ordinary check rather than risking an out-of-memory
failure or granting an exemption from partial evidence.

Artifacts retain `headsign_pct` as the literal published share. Schema 1.17
adds `headsign_scored_pct`, `headsign_applicable_trips`, and
`headsign_loop_exempt_trips` so consumers can see exactly how the score differs
from raw field presence. Rubric 1.3 records the scoring change.

The remaining finding also changes from a blanket instruction to conditional,
standards-aligned guidance: use the destination, direction, or "via" label
riders actually see; do not copy the route name; use `stop_headsign` when the
label changes during the trip.

## Consequences

- The MRC de Joliette reproduction credits all 12 loop templates. Its literal
  headsign presence remains 92.7%, its scored headsign value becomes 100%, its
  rider-experience score moves from 83.9 to 85.0, and its overall score moves
  from 95.0 to 95.3. The incorrect headsign fix disappears.
- Linear routes and loops with multiple patterns or directions remain
  actionable.
- A methodology re-score can raise other feeds with the same provable pattern.
  That shift is attributed to rubric 1.3, not presented as an agency feed
  improvement.
- The scorecard still cannot observe the text on a physical vehicle. A producer
  can supply better evidence when the feed topology alone is insufficient.

## Alternatives rejected

- **Make headsigns ungraded.** This would discard useful rider-facing evidence
  for ordinary routes because one conditional case was wrong.
- **Exempt every loop.** Loops can run in both directions or use meaningful
  destination and "via" labels. Geometry alone is not enough.
- **Require a per-agency override.** An override would fix known feeds but leave
  the same false positive for the next producer. Use observable feed evidence
  first; add an assertion mechanism only if real cases remain ambiguous.
