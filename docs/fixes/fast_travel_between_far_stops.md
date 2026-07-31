---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: impossibly fast travel between distant stops

Code: `fast_travel_between_far_stops` (MobilityData validator)

## What this means

Between two stops that are far apart, the scheduled times imply a speed no bus
reaches. The usual causes: an arrival or departure time typed a minute or an
hour off, a stop placed at the wrong coordinates so the distance is inflated,
or a missing stop between the two that would have broken the leg up.

## Why it matters

A rider planning around these times gets an itinerary that cannot happen; a
realtime system comparing predictions to this schedule reports phantom delays.
Either way, the feed promises something the street cannot deliver, and the
rider pays for the gap.

## How to fix it

- **Check the times first.** Open the flagged trip and look at the two stop
  times; a transposed digit or wrong hour is the most common cause.
- **Then check the stop locations.** If a stop sits miles from where the bus
  actually stops, correcting its coordinates fixes the implied speed and
  every other check that uses that stop.
- **Then check for a missing stop.** If the vehicle really serves a stop
  between the two, adding it back splits the leg into plausible pieces.

## How long it usually takes

Minutes per flagged trip once you open it: these are almost always a typo, a
misplaced pin, or a dropped stop, each visible at a glance.
