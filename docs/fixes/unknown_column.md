---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: files contain columns that are not part of GTFS

Code: `unknown_column` (MobilityData validator)

## What this means

A file in your feed has a column header that is not a field in the GTFS spec.
Apps ignore columns they do not recognise, so these do no harm on their own. The
validator surfaces them because an unknown column is sometimes a misspelled real
one, and that case does cause harm.

## Why it matters

Two things hide behind an unknown column. The harmless kind is a vendor extra:
an internal field the export carries that no app reads. The harmful kind is a
typo in a standard field name, like `stop_lat` written `stop_latt` or
`wheelchair_boarding` written `wheelchair_boardng`. When a real field is
misspelled, every app treats it as missing, so the data you entered silently
does nothing. The check is worth a look precisely because it catches that.

## How to fix it

Look at each flagged column name:

- **A misspelled GTFS field**: correct the spelling so apps read the data again.
  Compare against the field names in the GTFS reference; the typo is usually one
  or two letters off a real field.
- **A genuine vendor extra**: it is safe to leave, but removing it keeps the feed
  clean and the next reviewer from wondering. Many tools have a setting to export
  only standard fields.

## How long it usually takes

A quick look at the flagged files. Correcting a typo is a one-line change;
deciding a column is a harmless extra takes only a glance.
