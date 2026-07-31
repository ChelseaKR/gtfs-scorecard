---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: service dates fall outside the feed's stated validity window

Code: `service_window_outside_feed_period` (MobilityData validator)

## What this means

Two parts of the feed disagree about the dates it covers. `feed_info.txt` states
a validity window with `feed_start_date` and `feed_end_date`, while the actual
service in `calendar.txt` and `calendar_dates.txt` runs on dates outside that
window. The feed says it is valid for one range but schedules trips in another.

## Why it matters

The validity window is a promise about when the data is good. When service runs
outside it, the promise and the schedule no longer match, and any app or program
that trusts the stated window can draw the wrong conclusion: that current service
is expired, or that the feed covers dates it does not. It usually points to one
of two slips: the `feed_info` dates were not updated when a new schedule was
published, or old service periods are still in the export past the window's end.

## How to fix it

Decide which side is wrong:

- **The stated window is stale**: update `feed_start_date` and `feed_end_date`
  in `feed_info.txt` to match the service you actually publish. Many tools set
  these automatically from the service span if you let them.
- **Old service is lingering**: trim the past or future service periods that
  fall outside the intended window (see
  [`expired_calendar`](expired_calendar.md) and
  [`trip_coverage_not_active_for_next7_days`](trip_coverage_not_active_for_next7_days.md)).

After the fix, the validity window and the service dates should describe the
same range.

## How long it usually takes

A quick reconciliation. Updating the two `feed_info` dates is a one-time edit;
trimming stray service periods is one export setting.
