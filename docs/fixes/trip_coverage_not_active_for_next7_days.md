---
date_published: "2026-07-03"
date_modified: "2026-07-14"
---

# Fix: many trips do not run in the next 7 days

Code: `trip_coverage_not_active_for_next7_days` (MobilityData validator)

## What this means

A large share of the trips in your feed are not scheduled to run on any of the
next seven days. The trips exist in `trips.txt`, but their calendars place them
in the past or in a future window, so a rider looking at this week sees little
of the service the feed describes.

## Why it matters

Most often this means old service periods are still in the export: last
season's trips are riding along beside the current ones, inflating the feed and
making it harder to check. In the worst case it is the early sign of a feed
about to expire, where almost nothing runs next week because the current
calendar is lapsing and a new one has not been published. Either way, the trips
a rider can actually take should dominate the feed, not the trips they cannot.

## How to fix it

- **Trim past service periods** in your export settings ("only export active
  service" or a service-window date range). Re-run validation to check whether
  inactive trips still dominate the result.
- **Confirm current service is published.** If little runs next week because the
  next pick or season has not been exported yet, publish the current schedule so
  the feed covers the coming weeks.
- This finding often travels with
  [`expired_calendar`](expired_calendar.md); fixing the expired calendars
  usually moves this one too.

## How long it usually takes

One export setting in most tools. If the cause is that current service has not
been published yet, the work is running the export for the current schedule.
