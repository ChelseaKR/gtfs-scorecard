---
date_published: "2026-07-04"
date_modified: "2026-07-04"
---

# Fix: a station with no pathways.txt

Code: `scorecard_station_no_pathways`

## What this means

Your `stops.txt` has at least one stop marked as a station (`location_type`
1) or an entrance (`location_type` 2), but the feed has no `pathways.txt`
describing how a rider moves between them.

This only applies to feeds that model stations at all. A flat, stop-only feed,
which is most small and rural agencies, is complete as is and never sees this
finding.

## Why it matters

Once a feed models a station with multiple entrances, platforms, or levels, a
trip planner cannot route a rider through it without `pathways.txt`, and there
is no way to tell a wheelchair user whether a step-free route exists. Without
it, the station shows up as a single point with no instructions for getting
from the entrance to the platform.

## How to fix it

- **Add `pathways.txt`** connecting each entrance to the platforms it leads
  to, and each level to the ones it connects, including any elevators.
- **Add `levels.txt`** alongside it if the station spans more than one floor,
  so each pathway can reference the level it is on.
- **Mark elevator pathways explicitly** (`pathway_mode` 5) so a step-free
  route is identifiable, not just implied.

This is worth doing for a multi-level or large station where riders genuinely
need directions inside it. A flat stop, or a simple single-entrance station,
does not need it.

## How long it usually takes

Depends on the station's complexity: mapping a single-entrance station is
quick, while a large multi-level hub takes more care to get every connection
right.
