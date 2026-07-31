---
date_published: "2026-07-04"
date_modified: "2026-07-04"
---

# Fix: flexible service with no booking rules

Code: `scorecard_flex_no_booking_rules`

## What this means

Your feed describes flexible, demand-responsive service (a service area or
flexible stops, the GTFS-Flex extension to GTFS Schedule), but it has no
`booking_rules.txt`.

## Why it matters

Riders can see that the service exists and where it covers, but not how or
when to actually reserve a trip. A service area with no way to book it is not
usable, no matter how well the rest of the feed is described.

## How to fix it

- **Add `booking_rules.txt`** with how far ahead a rider needs to book and how
  to reach the service: a phone number, a booking link, or a message.
- **One rule can often cover the whole service.** If every flexible route
  books the same way, a single `booking_rules.txt` row applies to all of
  them; you do not need one per route.
- **Link it from `stop_times.txt`.** Reference the rule through
  `pickup_booking_rule_id` and `drop_off_booking_rule_id` so trip planners
  know which booking rule applies to which stop.

## How long it usually takes

A small file; for most small agencies, one booking rule describes the entire
demand-responsive service.
