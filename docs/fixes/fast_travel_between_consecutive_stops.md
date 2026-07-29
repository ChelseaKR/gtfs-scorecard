---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: a bus appears to travel impossibly fast between two stops

Code: `fast_travel_between_consecutive_stops` (MobilityData validator)

## What this means

For some trips, the time between two consecutive stops in `stop_times.txt` is too
short for the distance between them: the implied speed is faster than a bus could
go. Either a stop time is wrong or a stop is in the wrong place.

## Why it matters

Wrong times or locations make trip planners give riders bad arrival predictions
and draw routes that jump around the map. A single fat-fingered time can make a
whole trip look unreliable. The usual causes are a typo in a stop time, a stop
placed at the wrong coordinates, or two stops that are actually the same place.

## How to fix it

Check the trips the validator flags:

- **A wrong stop time**: correct the `arrival_time` / `departure_time` so the
  segment takes a realistic amount of time.
- **A misplaced stop**: fix the `stop_lat` / `stop_lon` in `stops.txt` so the
  distance is right. A stop dropped at 0,0 or at the wrong corner is a common
  cause.
- **Duplicate stops**: if two consecutive stops are the same physical location,
  merge them or remove the duplicate.

## How long it usually takes

A targeted fix on the flagged trips. The count tells you how widespread it is; a
single bad stop can explain many flagged segments at once.
