---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: a recommended GTFS file is missing

Code: `missing_recommended_file` (MobilityData validator)

## What this means

GTFS has required files and recommended ones. This finding means a recommended
file is absent from the feed. In practice it is almost always `feed_info.txt`,
the file that names the publisher and states the feed's validity dates.

## Why it matters

`feed_info.txt` tells apps who publishes the feed, in what language, and when it
expires. Without it, no app can warn a rider that your data is going stale, and
a developer who finds a problem has no stated owner to contact. It is a small
file that does a lot of quiet work, which is why the spec recommends it even
though it is not strictly required.

## How to fix it

Add the missing file. For `feed_info.txt`, include:

- `feed_publisher_name` and `feed_publisher_url`,
- `feed_lang`,
- `feed_start_date` and `feed_end_date` (the validity window).

Most scheduling tools can write `feed_info.txt` from an export setting once you
enter the publisher details. If the finding names a different recommended file,
the same idea applies: look for the matching export option, or add the file to
the export.

## How long it usually takes

A one-time setup in export settings. After the publisher details are entered the
file ships on every run.
