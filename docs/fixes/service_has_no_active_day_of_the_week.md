---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: service calendars with no days switched on

Code: `service_has_no_active_day_of_the_week` (MobilityData validator)

## What this means

A row in `calendar.txt` has `monday` through `sunday` all set to `0`, so the
service runs on no day of the week. Any trip tied to that calendar never runs.
It is usually a calendar that was being edited and left empty, or one whose days
were cleared but the row was never deleted.

## Why it matters

The trips attached to an empty calendar are invisible to riders, because they
never run. That is rarely intended. Either the trips should run on some days and
the calendar was left blank by mistake, or the calendar is retired and should be
gone. Both cases hide the real schedule from your staff and your vendor.

## How to fix it

First decide which case it is:

- **The service should run**: set the correct days on the calendar (switch the
  right `monday`–`sunday` columns to `1`). Check `calendar_dates.txt` too, in
  case the days were meant to come from exception dates.
- **The calendar is retired**: delete the empty calendar row, and remove the
  trips that pointed at it if they are also retired.

In most scheduling tools this is the service or calendar editor, where you
toggle the days a service pattern runs.

## How long it usually takes

A few minutes once you know whether the service is meant to run. The fix itself
is toggling days or deleting a row.
