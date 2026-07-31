---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: the feed expires within 7 days

Code: `feed_expiration_date7_days` (MobilityData validator)

## What this means

`feed_info.txt` sets `feed_end_date`, the last day this data is meant to be
valid, and it is within the next week. The feed is about to expire.

## Why it matters

This is the classic small-agency failure. When `feed_end_date` passes, trip
planners stop showing the agency's service even though the buses are still
running. Riders are told the agency does not exist, and nobody is warned first.
Seven days is short notice, so this one is worth acting on now.

## How to fix it

- **Re-export the feed** with a validity window that reaches further out. Most
  scheduling tools set `feed_end_date` from the service span or a configured
  number of days; push it out so the feed always has at least a month of runway.
- **Publish on a schedule.** The durable fix is exporting often enough that the
  end date is never close. A feed that is re-exported weekly never gets near
  expiry.
- If your tool (Trillium and several others do this) sets the dates
  automatically, confirm the export is actually running and uploading to the URL
  apps read.

## How long it usually takes

One export, today. The lasting fix is a regular export schedule so this never
gets close again.
