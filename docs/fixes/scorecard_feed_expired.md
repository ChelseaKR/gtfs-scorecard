---
date_published: "2026-07-04"
date_modified: "2026-07-29"
---

# Fix: the feed has already expired

Code: `scorecard_feed_expired`

## What this means

The scorecard compares `feed_info.txt`'s `feed_end_date` with the last day any
`calendar.txt` or `calendar_dates.txt` entry runs service, then uses whichever
date comes first. That earlier date has already passed.

## Why it matters

This is the most urgent thing a small agency's feed can get wrong. Trip
planners stop showing your service the day the calendar runs out, even though
the buses are still running. Riders are not warned first; they just stop
seeing the agency as an option. An expired feed is worse for riders than a
feed with data-quality problems, because it looks like the service does not
exist at all.

## How to fix it

- **Re-export the feed** with a calendar that reaches further out, and set
  `feed_info.txt`'s `feed_end_date` past your next planned service change.
- **Publish on a schedule.** A feed that is re-exported weekly, or whenever
  the schedule changes, never gets close to expiry again. This is the durable
  fix, not a one-time patch.
- If your export tool sets these dates automatically, confirm the export
  itself is actually running on schedule and reaching the URL riders' apps
  read.

See [the feed expires within 7 days](feed_expiration_date7_days.md) and
[within 30 days](feed_expiration_date30_days.md) for the validator's own
date-based warnings on `feed_info.txt`'s `feed_end_date` (computed differently
from this finding, so the two do not always fire in the same order), and
[expired service calendars](expired_calendar.md) for leftover calendars an
export should stop carrying forward.

## How long it usually takes

Often a same-day fix: one export with the calendar reaching further out. The
lasting fix is the export schedule so this never recurs.
