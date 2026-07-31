---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: recommended fields left empty

Code: `missing_recommended_field` (MobilityData validator)

## What this means

A file in the feed is missing a field the spec recommends, one apps rely on
even though the feed still loads without it. Common examples: `agency_lang`,
`stop_desc` alternatives, or `feed_info` contact fields. The validator's
notice names the exact file and field for your feed.

## Why it matters

Recommended fields are where rider experience lives. The feed works without
them, but apps show less: no contact link when a rider needs help, wrong
language assumptions, poorer stop descriptions. Filling them costs little and
each one shows up directly in what riders see.

## How to fix it

- **Read the notice for the exact field.** The validator names the file and
  column; the fix is filling that column.
- **Most scheduling tools have a home for these values** (agency profile,
  feed settings, stop attributes); fill it there so every future export
  carries it.
- **If the tool has no home for it**, a one-time edit of the exported file
  works, but push your vendor to carry the value so it survives the next
  export.

## How long it usually takes

Minutes per field once you find where your tool stores it. The value usually
already exists somewhere in your agency; this is copying it into the export.
