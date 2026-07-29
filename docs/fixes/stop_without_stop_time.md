---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: stops that no trip ever serves

Code: `stop_without_stop_time` (MobilityData validator)

## What this means

Some stops in `stops.txt` are never referenced in `stop_times.txt`, so no
scheduled trip stops there. The stop exists in the feed but nothing arrives.

## Why it matters

A rider can find one of these stops in a trip planner or on a map and walk to a
corner where no bus is scheduled to come. It also tends to mean the feed is
carrying retired stops the export never cleaned up.

## How to fix it

First decide which case each stop is:

- **A retired stop** that should no longer be published: remove it from the
  export. Many tools have a "do not export unused stops" option, or you remove
  the stop record at the source.
- **A stop that should be served** but was dropped from its trips by mistake:
  add it back to the trips that should serve it, so it gets `stop_times`
  entries again.

A stop that is a parent station or a boarding area referenced by other stops is
a different case and is not flagged by this notice.

## How long it usually takes

A review pass in your scheduling software. The count tells you how big the pass
is; a handful is minutes, dozens is an afternoon of cleanup.
