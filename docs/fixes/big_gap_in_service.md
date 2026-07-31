---
date_published: "2026-07-09"
date_modified: "2026-07-09"
---

# Fix: a service calendar has a gap longer than 13 days

Code: `big_gap_in_service` (MobilityData validator)

## What this means

One `service_id` has more than 13 days between dates when it runs. The gap can
be intentional, such as a seasonal route, but it can also mean a new service
period or a set of exception dates did not make it into the export.

## Why it matters

If the gap is accidental, trip planners show no trips for that service during
the missing dates. Riders may read that as the route not operating, even when
the published timetable says otherwise. An intentional seasonal gap is safe to
leave in place after you confirm it matches operations.

## How to fix it

- Check the `service_id`, gap start, and gap end named by the validator.
- Compare those dates with the service calendar in your scheduling system.
- If service should run, extend the matching row in `calendar.txt` or add the
  missing dates to `calendar_dates.txt` with `exception_type=1`.
- If the gap is intentional, document the seasonal pattern for the person who
  maintains the next export and leave the data unchanged.

## How long it usually takes

Checking the dates takes a few minutes. Correcting an export rule or adding a
block of exception dates usually fits into the next scheduled feed export.
