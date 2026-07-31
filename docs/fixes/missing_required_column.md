---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: a required column is missing from a file

Code: `missing_required_column` (MobilityData validator)

## What this means

A GTFS file is present but is missing a column the spec requires. The notice
names the file and the column, for example `routes.txt` without `route_type`, or
`stop_times.txt` without `departure_time`.

## Why it matters

This is an error, not a warning. A missing required column can make apps reject
the file or drop the affected rows, so trips, routes, or stops can silently
disappear from trip planners. It usually means the export is misconfigured or an
older template is in use.

## How to fix it

- **Add the named column** to the named file with valid values for every row.
  The validator message tells you exactly which file and field.
- **Check your export settings.** A missing required column is almost always the
  export tool not writing a field it should; look for the option that controls
  that file's columns, or update to a current export template.
- Re-run the feed through the validator after the fix to confirm the error is
  gone, since required-column problems often come in groups.

## How long it usually takes

A configuration fix in your export, then a re-export. Short once you know which
field is missing.
