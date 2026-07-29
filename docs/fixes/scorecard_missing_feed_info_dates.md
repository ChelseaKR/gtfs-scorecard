---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: the feed does not state its validity dates

Code: `scorecard_missing_feed_info_dates`

## What this means

`feed_info.txt` is where a feed states the window it is valid for, using
`feed_start_date` and `feed_end_date`. This finding fires when those dates are
absent, usually because `feed_info.txt` itself is not in the export. Without
them, nothing in the feed says when the data is meant to expire.

## Why it matters

Stated validity dates are how apps, and this scorecard, warn someone before a
feed goes stale. With them, a trip planner can flag that your data ends soon and
your staff can act. Without them, the first sign of trouble is riders being told
your agency does not exist, after the calendars have already lapsed. The dates
are also the input the freshness score reads, so a feed with none cannot earn
full marks for freshness even when its service is current.

## How to fix it

Add `feed_info.txt` with at least:

- `feed_publisher_name` and `feed_publisher_url` (who publishes the feed),
- `feed_lang` (the language of the rider-facing text),
- `feed_start_date` and `feed_end_date` (the validity window, `YYYYMMDD`).

Most scheduling tools have an export option that writes `feed_info.txt` for you;
set the publisher fields once and let the tool fill the dates from the service
window. If yours does not, `feed_info.txt` is a single short file you can add to
the export.

## How long it usually takes

A one-time setup in export settings. Once the publisher details are entered, the
file is written on every run.
