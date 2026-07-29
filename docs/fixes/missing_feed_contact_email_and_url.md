---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: the feed lists no contact

Code: `missing_feed_contact_email_and_url` (MobilityData validator)

## What this means

`feed_info.txt` has neither `feed_contact_email` nor `feed_contact_url`, so there
is no way to reach whoever maintains the feed. Both are optional in the spec, but
the validator recommends having at least one.

## Why it matters

App makers, trip planners, and state data programs sometimes spot a problem in a
feed before the agency does. With no contact, they have nobody to tell, so the
problem sits unreported and the feed stays broken longer than it needed to. One
field turns a silent failure into a quick heads-up.

## How to fix it

Add a contact to `feed_info.txt`:

- `feed_contact_email`: a monitored address, ideally a role inbox such as
  `gtfs@youragency.org` rather than one person's address, so it survives staff
  changes.
- or `feed_contact_url`: a page or form where issues can be reported.

Either one satisfies the check. Most scheduling tools expose this in the same
export settings that write the rest of `feed_info.txt`.

## How long it usually takes

One field, set once.
