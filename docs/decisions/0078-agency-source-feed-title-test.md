# ADR 0078: Half the agency pages name the source feed URL in search results

**Status:** Accepted (2026-11-17). Approved by the maintainer as a test on half
the agency pages. It reverses, for that half only, the 2026-09-13 decision not
to make agency titles clickier.

## Context

Agency pages get about 3,132 Google impressions and 67 clicks a month (28 days
to 2026-11-15, the JGP Niš page left out). The queries Google discloses for
them are "<agency> gtfs", the feed's own URL, and "official". Each page shows
the source feed URL under its heading ("Source feed: https://…"), and since
#555 nine hand-picked pages say so in their titles, but the generated title and
description never mention it.

On 2026-09-13 the maintainer decided not to make agency titles clickier: a low
CTR was read as the title correctly turning away people who want the raw feed
file. The new wording does not chase that intent. It names something every
qualifying page already shows. It is still a change to that decision, so it
runs as a test on half the pages, where a loss is limited and can be measured.

At this volume (about 30 clicks a month per half) a test cannot prove a 20%
lift inside 28 days. It protects against a sitewide loss; it does not measure
the gain precisely.

## Decision

- **Who gets it.** An agency page is in the test half when the first byte of
  `sha256("agency-source-title-test-2026-11:" + agency_id)` is even
  (`source_title_test_arm` in `render_site.py`). The split needs no list, is
  the same on every render, and places a new agency without moving any other.
  Changing the salt reshuffles the halves and ends the test.
- **When it applies.** A page in the test half gets the new copy only when it
  renders a "Source feed" link and shows a grade. A redacted, authenticated or
  withheld feed URL renders no link (ADR 0066, #371, the opt-out ledger), and
  the title says "grade", so those pages keep the control copy. The nine
  hand-written `_SEARCH_INTENT_COPY` pages are in neither half.
- **The copy.** The title suffix is the first that fits of
  " GTFS feed: source URL, grade and fixes", " GTFS feed: URL, grade, fixes",
  " GTFS feed URL and grade", and the control's own " GTFS feed quality". The
  description keeps the dated grade clause and ends "Source feed URL, validator
  findings, service dates and fixes." (with "realtime" when it was measured).
  A name too long for that tail keeps the control's short tail, so the test
  never cuts a name the control shows whole. A title still never carries the
  grade itself.
- **What stays the same.** The control half is exactly what it would be
  without the test: the copy is applied after the corpus-wide uniqueness plan,
  and a test page whose new copy would collide with another page keeps its
  planned copy. Clearance-log titles and Dataset names do not change.

## Reading the result

The test starts on the day this change first deploys, which is the date it
merges to `main`; nothing in the code holds that date. Read Search Console 28
and 56 days after it, and take each half's baseline as the 28 days before it.
Split agency page URLs by `source_title_test_arm(agency_id)` (intent to treat:
a test-half page that kept the control copy still counts in the test half),
and leave out `/agency/jgp-nis/` and the nine search-intent pages. Compare each
half's clicks, impressions and CTR with its own previous 28 days, then the two
halves with each other.

- Roll out to every page if the test half's clicks hold or rise and its
  impressions do not fall more than the control's.
- Roll back (delete the test copy) if the test half loses impressions or
  clicks the control does not, as Caltrain and LPP did after #555.

To list the half for any id:
`uv run python -c "from scorecard_pipeline.render_site import source_title_test_arm as a; print(a('king-county-metro'))"`.

## Consequences

- On the committed corpus (2,491 agency pages, 2026-11-17), the full render
  put 1,268 pages in the test half and 1,216 in the control half, with 7
  search-intent pages in neither. In the test half, 694 pages carry the new
  title and 469 the new description; 782 carry at least one. The other 486
  have no public source link, no grade, or a name too long for the new
  wording, and keep the control copy. No control page changed.
- `pipeline/tests/test_agency_source_title_test.py` pins the split for named
  ids, the approved wording, the fallbacks, the qualifying rule, a byte-for-byte
  unchanged control half, and the length and uniqueness bounds over every
  published record.
- Titles are checked by the deploy-only SEO contract (`check_site_seo.py`),
  which was run on a full render of the committed corpus before merging.
