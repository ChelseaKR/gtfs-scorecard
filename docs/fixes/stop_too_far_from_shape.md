---
date_published: "2026-07-04"
date_modified: "2026-07-04"
---

# Fix: a stop sits far from the route line

Code: `stop_too_far_from_shape` (MobilityData validator)

## What this means

Some stops sit far from the route line (the `shapes.txt` path) they belong
to, based on the geometric distance between the stop and the shape.

## Why it matters

Trip planners use the shape to draw the route on the map. When a stop sits
far from it, the map can draw the bus detouring to reach the stop, or point
riders to the wrong corner to wait.

## How to fix it

Check the flagged stops' coordinates and the route shape in your scheduling
software, then re-snap whichever one is misplaced:

- **If the stop's location is wrong**, correct `stop_lat` / `stop_lon` to
  where the stop actually is.
- **If the shape doesn't actually pass the stop**, fix or re-generate
  `shapes.txt` so it follows the real path the bus drives.

See [a stop far from the shape by its distance measurement](stop_too_far_from_shape_using_user_distance.md)
for the related case where `shape_dist_traveled` values, not the raw
geometry, are what disagree with the stop's location.

## How long it usually takes

A few minutes per flagged stop, checking the coordinates against the map.
