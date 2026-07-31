---
date_published: "2026-07-03"
date_modified: "2026-07-14"
---

# Fix: a stop sits far from the route's drawn path

Code: `stop_too_far_from_shape_using_user_distance` (MobilityData validator)

## What this means

Your feed provides `shape_dist_traveled` values that tie stops to points along a
route's shape in `shapes.txt`. For some trips a stop ends up far from the shape
at the distance given, so the stop and the drawn route disagree about where the
stop is.

## Why it matters

Apps use the shape to draw the route line and to place stops along it. When a
stop is far from the shape, the map shows the route detouring to a stop that
isn't really there, or a stop floating off the line. Riders see a confusing map
and worse walking directions to the stop.

## How to fix it

The mismatch is between three things; check which is off for the flagged trips:

- **The shape**: if the route line does not actually pass the stop, fix or
  re-generate `shapes.txt` so it follows the real path.
- **The stop location**: if `stop_lat` / `stop_lon` is wrong, correct it.
- **The `shape_dist_traveled` values**: if the geometry is right but the distance
  measurements are off, regenerate them. Many tools compute `shape_dist_traveled`
  automatically; re-run validation afterward to check whether this finding remains.

See [a stop far from the shape by raw geometric distance](stop_too_far_from_shape.md)
for the related case where the shape and the stop simply disagree in space,
with no `shape_dist_traveled` measurement involved.

## How long it usually takes

Often a regeneration step in your scheduling tool rather than hand-editing. If a
specific stop or shape is wrong, it is a targeted fix on the flagged trips.
