---
date_published: "2026-07-05"
date_modified: "2026-07-05"
---

# Fix: some scheduled trips have no live predictions

Code: `scorecard_rt_trip_coverage`

## What this means

During the sampling window, some trips that were scheduled to be running had
no matching prediction in the TripUpdates feed. The feed itself is reachable;
it just doesn't cover every trip that should be in it.

## Why it matters

Riders on those trips get schedule data dressed up as realtime: the app shows
a time, but nobody actually confirmed the vehicle is where the schedule says
it should be. Caltrans' realtime guidance expects every operating trip to show
up in TripUpdates, not just the ones an AVL happened to report on.

## How to fix it

- **Check with your AVL vendor that every vehicle assignment flows into
  TripUpdates**, including school-day-only trips, tripper runs, and any
  service added outside the normal daily pattern.
- **Confirm vehicles are actually logged in** for every scheduled run, not
  just the ones on a fixed route pattern. A common gap is trips run by a
  spare vehicle or a contracted operator that never gets assigned in the
  AVL system.
- **Compare a sample day's TripUpdates against that day's scheduled trips**
  to see which specific trips or blocks are consistently missing.

## How long it usually takes

A vendor data-mapping question, usually resolved within a data-mapping
support ticket rather than a code change on your end.
