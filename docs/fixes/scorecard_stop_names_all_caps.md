---
date_published: "2026-07-04"
date_modified: "2026-07-04"
---

# Fix: stop names are written in ALL CAPS

Code: `scorecard_stop_names_all_caps`

## What this means

`stops.txt` writes some or all of your `stop_name` values in ALL CAPS, for
example "MAIN ST & 2ND AVE" instead of "Main St & 2nd Ave".

## Why it matters

Mixed-case names are easier to read in trip-planning apps, and screen readers
say them more naturally: an all-caps name is sometimes read letter by letter
instead of as a word. This does not affect scheduling or routing; it is a
plain readability fix for every rider who reads a stop name.

## How to fix it

- **Rename stops to mixed case**, following normal capitalization for local
  place names: "Main St & 2nd Ave," not "MAIN ST & 2ND AVE."
- **Check your source data first.** All-caps names often come from an older
  system or a vendor default rather than how the agency actually refers to
  the stop, so the readable version may already exist somewhere upstream of
  the export.
- Most scheduling tools support a bulk find-and-replace or a case-conversion
  step across all stop names at once, rather than editing each stop by hand.

## How long it usually takes

Often a bulk fix in your scheduling software, applied to every stop at once
rather than one at a time.
