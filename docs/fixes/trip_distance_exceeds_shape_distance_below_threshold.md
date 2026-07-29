---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: trips slightly longer than their drawn route shape

Code: `trip_distance_exceeds_shape_distance_below_threshold` (MobilityData validator)

## What this means

A trip's stops, laid end to end, travel slightly farther than the route line
(`shapes.txt`) drawn for that trip. The gap is small, under the validator's
error threshold, which is why this is informational: the shape is a little
short, or a stop sits a little past where the drawn line ends.

## Why it matters

Apps draw the route line from the shape and place the bus along it. When the
line ends short of the last stop, the bus icon stops moving before the bus
does, and the drawn route visibly misses a stop the rider is standing at. A
small gap reads as a small glitch; several of them erode trust in the map.

## How to fix it

- **Extend the shape to the ends of the trip.** In your scheduling tool,
  re-snap or redraw the route so the line reaches the first and last stops,
  including any loop or turnaround the vehicle actually drives.
- **Or check the outlying stop.** If the last stop's pin sits past the real
  end of the route, correcting the pin closes the gap from the other side.
- Re-export and the notice clears when the trip and shape lengths agree.

## How long it usually takes

A few minutes per route in the map editor of your scheduling tool; it is
usually one endpoint that needs dragging.
