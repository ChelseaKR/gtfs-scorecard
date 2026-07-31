---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: service calendars that have already expired

Code: `expired_calendar` (MobilityData validator)

## What this means

`calendar.txt` (and `calendar_dates.txt`) define the date ranges your service
runs. Some of those ranges have an end date in the past, so they describe
service that has already stopped. They are leftovers the export carried forward.

## Why it matters

Expired calendars are dead weight. On their own they do not break a trip
planner, but they are the early warning sign of the failure that does: a feed
whose service quietly runs out. If the only calendars left are expiring, trip
planners drop the agency on the day they lapse, and nobody is told first. Old
calendars also make the feed harder for you and your vendor to read, because
they hide which service is actually current.

## How to fix it

- **In your export settings**, look for an option like "only export active
  service", "trim past service periods", or a service-window date range. Setting
  it drops expired calendars on the next export.
- **At the source**, retire the old service periods (last season's schedule, a
  past pick) so they stop being exported.
- **Check what remains is current.** After trimming, confirm the feed still
  covers the next several weeks. Expired calendars often sit next to a calendar
  that is about to expire, which is the more urgent fix.

## How long it usually takes

One setting in most export tools, applied on the next run. Confirming the
remaining service window is current is a quick look.
