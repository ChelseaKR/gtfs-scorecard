# Fix: remove a duplicated point from a route shape

Code: `equal_shape_distance_same_coordinates` (MobilityData validator)

## What this means

Two consecutive rows in `shapes.txt` have the same latitude, longitude, and
`shape_dist_traveled`. They describe the same point twice instead of moving
forward along the route shape.

## Why it matters

A single duplicate point rarely changes what a rider sees, but repeated points
make the shape harder for trip planners and mapping tools to process. They also
often reveal a geometry export or simplification setting that can create more
serious distance-order problems elsewhere in the feed.

## How to fix it

- Open the two row numbers and `shape_id` named by the validator.
- Remove one row if the latitude, longitude, and distance are identical.
- Renumber `shape_pt_sequence` so it still increases along the shape.
- Regenerate `shape_dist_traveled` if your export tool calculates it; do not
  hand-edit one distance without checking the rest of that shape.
- Run the validator again and confirm the route still follows the intended
  street or track alignment.

## How long it usually takes

One isolated duplicate is a short data edit. Many duplicates usually call for
changing the shape export or simplification setting and publishing a fresh feed.
