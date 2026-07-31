---
date_published: "2026-07-05"
date_modified: "2026-07-05"
---

# Fix: the ServiceAlerts realtime feed failed during sampling

Code: `scorecard_rt_service_alerts_unreachable`

## What this means

The scorecard tried to sample your GTFS-Realtime ServiceAlerts feed and it
failed to return usable data during the sampling window.

## Why it matters

When this feed is down, riders see scheduled times presented as if they were
live, with no way to know about a detour, a stop closure, or a delay that the
agency already knows about and would otherwise be publishing.

## How to fix it

- **Check the ServiceAlerts endpoint with your AVL vendor or CAD/AVL
  provider.** It should return a fresh GTFS-Realtime protobuf on every
  request, not a stale cache, an error page, or an empty response.
- **Confirm the URL itself hasn't changed.** A vendor migration or a renewed
  certificate sometimes moves the endpoint without updating what's on file.
- **Check for a rate limit or an IP block** if the feed works in a browser but
  not from an automated request.

## How long it usually takes

Usually a vendor support ticket. If the fix is just a stale certificate or a
changed URL, it can be same-day.
