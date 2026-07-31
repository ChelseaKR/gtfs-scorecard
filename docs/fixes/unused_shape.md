---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: the feed contains route shapes no trip uses

Code: `unused_shape` (MobilityData validator)

## What this means

`shapes.txt` defines geographic paths for routes, and your feed includes shapes
that no trip in `trips.txt` references. They are dead weight left behind by the
export.

## Why it matters

Unused shapes do not hurt riders directly. They make the feed larger than it
needs to be and usually signal that the export is carrying stale data, which is
worth knowing because the same staleness can affect things that do matter.

## How to fix it

- **In your export settings**, look for an option like "remove unused shapes",
  "clean up shapes", or "only export referenced data". Turning it on drops the
  orphans automatically on the next export.
- **If there is no such setting**, the shapes are usually leftovers from
  retired trips or patterns. Removing those retired patterns at the source
  clears the shapes too.

## How long it usually takes

One setting, applied on the next export. If you have to track down retired
patterns by hand it is a short review pass, not a project.
