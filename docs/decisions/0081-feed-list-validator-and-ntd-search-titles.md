# ADR 0081: Search titles for the feed list, the validator guide and NTD state pages

**Status:** Accepted (2026-11-17). Approved by the maintainer.

## Context

A Search Console review on 2026-11-17 (28 days to 2026-11-15) found three
pages whose titles did not name what their searchers type.

- `/program/all/` had about 166 impressions a month at position 8.6 and a CTR
  of 0.65%. Its title, "All tracked agencies: GTFS quality scores", reads as a
  rollup, while the page is the one list of every tracked feed.
- "gtfs validator" and "gtfs feed validator" were split across six URLs at
  positions 19 to 78: `/`, `/about/`, `/focus/`, `/check/`, `/how-to-read/` and
  `/gtfs-validator/`. It is the only tool-intent query the site gets, and the
  page written for it (#550) ranked best, at 19.
- NTD state pages had about 103 impressions a month at a CTR of 1.04%, titled
  "Texas NTD shapes.txt readiness".

The expected gain is small (a few clicks a month in all) and the queries for
the first page are not disclosed, so the wording is a reasoned guess.

## Decision

- `/program/all/` is titled "GTFS feed list: quality grades for N transit
  feeds". Its description is "All N tracked transit GTFS feeds in one list,
  each with its quality grade; M need attention, plus the fixes they share."
  N and M come from the rollup payload the page itself shows, so they change
  with the corpus. State and country rollups keep their titles.
- `/gtfs-validator/` is the one page meant to answer "gtfs validator". Its H1,
  and so its title, is "GTFS validator: check a feed and read the results".
  The site name is dropped from the title when both do not fit in 60
  characters. Its description says how the MobilityData validator checks a
  feed, what its notices mean in plain English, and what the grade adds. The
  document's `date_modified` moves to 2026-11-17, because its heading changed.
- `/about/`, `/how-to-read/`, `/check/` and `/focus/`, the other pages that
  showed for the query, each link the guide once with the words "GTFS
  validator guide". The home page's link to it now reads "the GTFS validator
  guide" instead of "how the scorecard uses it". The home title is unchanged.
- NTD state pages are titled "<state> transit GTFS for NTD: shapes.txt and
  agency_id", or "...: shapes.txt check" when that is over 60 characters
  (North Carolina, District of Columbia). Their description already names
  both checks and is unchanged.

Nothing here adds an offer or a price, and no page claims anything it did not
already explain.

## Consequences

- Read Search Console for these URLs 28 and 56 days after the deploy, against
  the 28 days to 2026-11-15. A drop in impressions for `/program/all/` or the
  NTD pages would mean the old words matched better; restore them.
- The four new links make `/gtfs-validator/` the page with the most internal
  links using the query's words. Whether Google consolidates the query there
  can only be seen in Search Console.
- `pipeline/tests/test_search_titles_program_validator_ntd.py` holds the exact
  wording, the length bounds at 1 and 99,999 feeds, the untouched state
  rollup titles, the five links, and the NTD fallback. Goldens for
  `/program/all/`, `/how-to-read/`, `/check/`, `/focus/` and `/tools/` are
  refreshed.
- These titles are checked by the deploy-only SEO contract
  (`check_site_seo.py`), which was run on a full render of the committed
  corpus before merging.
