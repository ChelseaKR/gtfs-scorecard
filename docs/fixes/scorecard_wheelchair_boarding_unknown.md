---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: stops do not state wheelchair accessibility

Code: `scorecard_wheelchair_boarding_unknown`

## What this means

Your `stops.txt` does not set `wheelchair_boarding` for some or all stops, so
the feed says "unknown" for whether a wheelchair user can board there. Unknown
is the default when the field is left blank.

## Why it matters

A rider who uses a wheelchair cannot plan a trip when accessibility is unknown.
Trip planners do not guess; they show no information, which reads as "do not
rely on this stop." Populating the field is a direct accessibility improvement,
and it is often the single biggest gap in an otherwise good small-agency feed.

## How to fix it

Set `wheelchair_boarding` on every stop to `1` (accessible) or `2` (not
accessible). `0` or blank means unknown, which is what you are trying to move
away from.

- **In most scheduling tools** this is a per-stop attribute in the stop editor,
  sometimes labeled "ADA accessible" or "wheelchair boarding". Look for a stop
  attributes or amenities panel.
- **If your tool exports GTFS but has no field for it**, you can set it in the
  source data the export reads from, or as a post-export step on `stops.txt`.
- **You do not need a perfect survey to start.** Set the stops you know, begin
  with the busiest ones, and fill the rest over time. Partial real data beats
  blanket "unknown".

## How long it usually takes

Minutes to flip the field once you know the values. The real work is the field
knowledge, which a small agency usually already has for its top stops.
