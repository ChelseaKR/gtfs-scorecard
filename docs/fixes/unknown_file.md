---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: the feed contains a file that isn't part of GTFS

Code: `unknown_file` (MobilityData validator)

## What this means

The zip contains a file whose name is not part of the GTFS spec. Apps ignore
files they do not recognise, so an unknown file does no harm on its own. The
validator surfaces it because an unknown file is sometimes a misspelled required
one, and that case does cause harm.

## Why it matters

Two things hide behind an unknown file. The harmless kind is an extra the export
includes (a readme, a vendor file) that no app reads. The harmful kind is a typo
in a standard file name, like `stop_time.txt` instead of `stop_times.txt`: the
real file is then missing and every app treats those trips as having no
schedule, while your data sits in the zip unread.

## How to fix it

Look at the flagged file name:

- **A misspelled GTFS file**: rename it to the correct spelling so apps read it
  again. Compare against the standard file list; the typo is usually one or two
  characters off.
- **A genuine extra**: it is safe to leave, but removing it keeps the feed clean.
  Many export tools have a setting to include only standard GTFS files.

## How long it usually takes

A quick look at the file name. Renaming is instant; deciding a file is a harmless
extra takes only a glance.
