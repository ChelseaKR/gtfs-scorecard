---
date_published: "2026-10-01"
date_modified: "2026-10-01"
---

# Fix: your feed_info end date is earlier than your service calendar

Code: `scorecard_feed_end_date_before_calendar`

## What this means

`feed_info.txt` has a `feed_end_date`, the last day the feed says its schedule
is reliable. Your `calendar.txt` or `calendar_dates.txt` has service after that
day. The scorecard uses the earlier of the two dates, so the feed is scored as
ending on `feed_end_date`, and that date has passed or is less than 30 days
away.

This finding takes the place of "the feed has expired" or "the feed expires
soon" when the calendar itself reaches further. The service data is there. One
date is out of step with it.

## Why it matters

The GTFS reference says that for dates past `feed_end_date`, apps should treat
the schedule as not authoritative. An app that follows that rule can stop
showing your service on the earlier date, even though your calendar goes on.
The MobilityData validator's 7-day and 30-day expiry warnings read
`feed_end_date` too, so they will keep firing until it is corrected.

## How to fix it

- **Correct `feed_end_date`** in `feed_info.txt`. Set it to the last day in
  your calendar, or to the last day you are confident the schedule will run.
- **If service really does stop on the earlier date**, end the calendar there
  instead, so the two agree.
- **In most export tools** `feed_end_date` is an export setting or is taken
  from a "valid until" field on the schedule. If it is typed by hand, check it
  each time you export, or let the tool fill it from the calendar.

Publishing service past `feed_end_date` is allowed and even recommended as a
preview of future service. The scorecard only raises this when the earlier
date is close enough to cost freshness points.

## How long it usually takes

One field. The lasting fix is an export setting that fills `feed_end_date`
from the calendar, so the two cannot drift apart.
