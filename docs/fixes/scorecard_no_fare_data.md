---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: the feed contains no fare information

Code: `scorecard_no_fare_data`

## What this means

The feed has no fare files, so it does not say what a trip costs. GTFS carries
fares either in the classic `fare_attributes.txt` and `fare_rules.txt`, or in
the newer Fares v2 files (`fare_products.txt`, `fare_leg_rules.txt`, and
related). Neither is present.

## Why it matters

Without fare data, trip planners show "fare unknown", and a rider cannot tell
what to bring or budget for the trip before they board. Visitors and occasional
riders feel this most, because regulars already know the fare. For a flat-fare
system, the missing information is small and easy to supply, so the gap is more
about it never being entered than about complexity.

## How to fix it

- **Flat fare (one price to ride):** add a `fare_attributes.txt` with a single
  fare (price, currency, payment method, transfer rules), and a `fare_rules.txt`
  that applies it to your routes. This is a short file for most small systems.
- **Zones or distance-based fares:** model the fare zones on your stops and the
  rules between them, or use Fares v2 if your tool supports it.
- **In your scheduling tool:** look for a fares or pricing section, enter the
  fare once, and enable fare output in the export settings.

Set the currency correctly (for example `USD`) so apps display the price
properly.

## How long it usually takes

A small file for most flat-fare systems, entered once. Zone and distance fares
take longer because the structure itself is larger.
