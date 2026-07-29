---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: rider-facing names are in ALL CAPS or all lowercase

Code: `mixed_case_recommended_field` (MobilityData validator)

## What this means

Some rider-facing text, usually stop names or trip headsigns, is written in a
single case: `MAIN ST & 2ND AVE` or `main st & 2nd ave` instead of
`Main St & 2nd Ave`. The spec recommends mixed (title) case for these fields,
and the validator flags the ones that are not.

## Why it matters

ALL-CAPS text is measurably slower to read, and it loses the cues that case
gives: a screen reader may spell out an all-caps word letter by letter or read
it with odd emphasis, so a blind rider hears "M-A-I-N" instead of "Main". The
data is not wrong, but it reads worse in every app that shows it, which is all
of them. Fixing the case is a direct readability and accessibility improvement.

## How to fix it

Rewrite the flagged names in mixed case: capitalise the first letter of each
word, keep ordinals and directionals natural (`2nd`, `NW`), and leave genuine
acronyms as they are (`UC Davis`, `VA Hospital`).

- **In your scheduling tool**, this is usually a bulk edit on stop names and
  headsigns. Some tools have a "title case" or "normalise case" helper.
- **If the source data is all-caps**, fixing it at the source means it stays
  fixed on every future export, rather than re-capitalising after each run.

Watch for names that should not be fully title-cased, like `Davis Amtrak` or a
street named after initials; review rather than blindly applying a script.

## How long it usually takes

Often a single bulk fix in your scheduling software, plus a quick review of the
acronyms and proper nouns the bulk change would get wrong.
