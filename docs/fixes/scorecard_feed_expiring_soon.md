---
date_published: "2026-07-04"
date_modified: "2026-07-29"
---

# Fix: service coverage expires soon

Code: `scorecard_feed_expiring_soon`

## What this means

This scorecard finding compares `feed_info.txt`'s `feed_end_date` with the last
day any `calendar.txt` or `calendar_dates.txt` entry runs service, then uses
whichever date comes first. That earlier date is still in the future, but it is
less than 30 days away.

## Why it matters

This is the early warning before [the feed has already
expired](scorecard_feed_expired.md). Once the calendar runs out, trip planners
stop showing your service to riders, with no notice to them first. Acting now,
while it is a heads-up rather than an outage, means a calm export instead of a
scramble after riders start reporting the agency missing from their app.

## How to fix it

- **Re-export the feed** with a validity window reaching further out. Most
  scheduling tools set the calendar span, or `feed_info.txt`'s
  `feed_end_date`, from a configured number of days; push it out to at least
  60 days so this stops firing.
- **Make exporting routine.** If exports happen weekly or on every schedule
  change, the end date stays comfortably ahead and this finding stops
  appearing on its own.

## How long it usually takes

One export, today. Worth doing now while it is a heads-up rather than an
outage.
