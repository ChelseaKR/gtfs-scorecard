---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: the feed lists no technical contact

Code: `scorecard_no_feed_contact`

## What this means

`feed_info.txt` is present but has neither `feed_contact_email` nor
`feed_contact_url`, so there is no address to reach the people who maintain the
feed. These fields are optional in the spec, but they are the standard way to
say "if something looks wrong with this data, here is who to tell."

## Why it matters

App makers, state data programs, and trip planners do sometimes spot problems in
a feed before the agency does. With no contact, they have nobody to email, so
the problem sits unreported and the feed stays broken longer than it needed to.
A contact turns a silent failure into a quick heads-up. It costs one field and
saves the round of detective work someone would otherwise do to find you.

## How to fix it

Add a contact to `feed_info.txt`:

- `feed_contact_email`: a monitored address, ideally a role inbox like
  `gtfs@youragency.org` rather than one person, so it survives staff changes.
- or `feed_contact_url`: a page or form where issues can be reported.

Either one satisfies the check; an email is usually simplest. Most scheduling
tools expose this in the same export settings that write the rest of
`feed_info.txt`.

## How long it usually takes

One field, set once. Using a role inbox instead of a personal address is the
only judgement call.
