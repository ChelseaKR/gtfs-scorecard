---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: the feed expires within 30 days

Code: `feed_expiration_date30_days` (MobilityData validator)

## What this means

`feed_info.txt` sets `feed_end_date`, and it falls within the next month. The
data is not expired, but the window is closing.

## Why it matters

This is the early warning before
[`feed_expiration_date7_days`](feed_expiration_date7_days.md). When the end date
passes, trip planners drop the agency. Acting at the 30-day mark means you fix it
calmly instead of scrambling after riders report the agency missing from their
app.

## How to fix it

- **Re-export with a later validity window.** Set `feed_end_date` (or the
  service span your tool exports from) to cover at least the next 60 to 90 days.
- **Make it routine.** If exports happen weekly or whenever the schedule
  changes, the end date stays comfortably ahead and this notice never fires.

## How long it usually takes

One export. Worth doing now while it is a heads-up rather than an outage.
