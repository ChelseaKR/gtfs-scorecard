---
date_published: "2026-07-05"
date_modified: "2026-07-05"
---

# Fix: the VehiclePositions realtime feed failed during sampling

Code: `scorecard_rt_vehicle_positions_unreachable`

## What this means

The scorecard tried to sample your GTFS-Realtime VehiclePositions feed and it
failed to return usable data during the sampling window.

## Why it matters

When this feed is down, riders see scheduled times presented as if they were
live. A trip planner has no way to tell the difference between "on time" and
"we haven't heard from this feed in a while."

## How to fix it

- **Check the VehiclePositions endpoint with your AVL vendor.** It should
  return a fresh GTFS-Realtime protobuf on every request, not a stale cache,
  an error page, or an empty response.
- **Confirm the URL itself hasn't changed.** A vendor migration or a renewed
  certificate sometimes moves the endpoint without updating what's on file.
- **Check for a rate limit or an IP block** if the feed works in a browser but
  not from an automated request.

## How long it usually takes

Usually a vendor support ticket. If the fix is just a stale certificate or a
changed URL, it can be same-day.
