# Fix: trips don't say where they're headed

Code: `scorecard_missing_headsigns`

## What this means

A trip can use `trip_headsign` in `trips.txt` for its destination, direction,
or "via" label. `stop_headsign` in `stop_times.txt` can change that label during
the trip. Some trips leave both blank even though the route has more than one
direction or pattern.

`trip_headsign` is optional. The scorecard does not ask a single-pattern,
single-direction loop to invent one, and GTFS Best Practices says not to copy
`route_short_name` or `route_long_name` into it.

## Why it matters

The headsign is the "to Downtown" or "to Transit Center" label a rider reads on
the front of the bus and in an app. When a route has multiple directions,
branches, or short turns, that text helps a rider tell which service is coming.
For a one-way loop with one pattern, the route identity may already be the only
useful label.

## How to fix it

- **Use the public destination, direction, or "via" text** riders actually see
  (for example "Downtown via Main St"). Do not duplicate the route name.
- **In most scheduling tools** this is a field on the trip or the route pattern;
  set it once per pattern and every trip on that pattern inherits it.
- **Use `stop_headsign`** where that rider-facing text changes partway through a
  trip.
- **For a single-pattern, single-direction loop**, leave `trip_headsign` blank
  when the vehicle displays only the route identity. Do not invent "clockwise"
  or "counterclockwise" unless riders actually see or use that label.

## How long it usually takes

Usually one value per route pattern. A loop that has no distinct rider-facing
destination needs no change.
