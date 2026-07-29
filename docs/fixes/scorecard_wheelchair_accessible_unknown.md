---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: trips do not state wheelchair accessibility

Code: `scorecard_wheelchair_accessible_unknown`

## What this means

Your `trips.txt` does not set `wheelchair_accessible` for some or all trips, so
the feed says "unknown" for whether the vehicle on that trip can carry a
wheelchair user. Unknown is the default when the field is left blank.

This is the vehicle-side companion to the stop-side check
([`scorecard_wheelchair_boarding_unknown`](scorecard_wheelchair_boarding_unknown.md)).
An accessible stop does not help if the rider cannot tell whether the bus that
serves it is accessible too.

## Why it matters

A rider who uses a wheelchair needs to know both ends are covered: a stop they
can board at and a vehicle that can take them. Trip planners do not guess. With
the field blank they show no information, which a rider reads as "do not rely on
this trip." Most small-agency fleets are fully accessible, so leaving the field
blank understates a service the agency already provides.

## How to fix it

Set `wheelchair_accessible` on every trip to `1` (accessible) or `2` (not
accessible). `0` or blank means unknown.

- **If your whole fleet is accessible**, which is common for small agencies,
  this is usually a single default in your export settings rather than a
  per-trip edit. Look for a fleet-level or agency-level accessibility default.
- **If accessibility varies by vehicle or route**, set the field on the trips
  that differ. Tools that model vehicles or blocks can often derive the trip
  value from the assigned vehicle.
- **In a post-export step** you can fill `wheelchair_accessible` on `trips.txt`
  directly if your tool has no field for it.

## How long it usually takes

Often one default setting in your export, applied on the next run. If
accessibility varies across the fleet it is a short pass to mark the exceptions.
