# ADR 0067: Agency lastmod follows template revisions, and a moved scorecard's companion pages redirect

**Status:** Accepted (2026-10-11).

## Context

Search Console's Pages report on 2026-10-11: 3K indexed, 5.68K not indexed.
The reasons were "Excluded by noindex" 2,400, "Crawled - currently not
indexed" 1,225, "Alternate page with proper canonical" 715, "Not found (404)"
645, "Discovered - currently not indexed" 519, "Page with redirect" 167,
and 8 more split between the two duplicate reasons.

Measured the same day:

- **The sitemap is clean.** All 3,680 URLs answer 200 with no robots meta,
  no redirect, and a self-referencing canonical. `check_site_seo.py` already
  requires the sitemap to equal the set of indexable, non-redirect pages, at
  deploy.
- **The 404s come from moved scorecards.** 495 retired or removed ids
  (aliases plus the 2026-07-11 dedupe's twins) redirect at `/agency/<id>/`,
  but their `brief/`, `board/` and `fixes/` URLs answered 404: 1,482 of
  1,482 probed. Search Console had shown impressions for 200 of them. A
  crawl of 3,979 live pages found no internal link to a 404.
- **Noindex is the brief and board pages.** Every scorecard links its
  call-prep brief and board one-pager. Both are `noindex,follow` by design
  (`site-seo.json`, since #223): they restate the scorecard for
  one reader and would compete with it. That stays.
- **"Crawled - currently not indexed" is a cohort, not a template.** Of
  1,800 agency pages inspected, US pages first published on 2026-07-03 are
  18% indexed (166 of 922); every agency page published later is 93-100%
  indexed, US or not (US: 46 of 47). Within the 2026-07-03 US cohort,
  indexed and dropped pages do not differ in word count, unique text,
  boilerplate share, internal links in, grade, or freshness. 651 of the 743
  dropped pages had search impressions this summer: Google indexed them,
  then dropped them. 85% of them were last crawled before 2026-10-06, the
  day "About this feed", the feed history table and the de-duplicated
  handoff reached every scorecard (#501, #502). Google has not seen the
  current pages.

The sitemap's agency `<lastmod>` is the day the feed file last changed
(#500), omitted when no change was observed. That is true, but it leaves
1,529 of 1,999 locally rendered agency entries with no date at all, and it
tells a crawler nothing when the page itself changed without the feed.

## Decision

1. An agency page's `<lastmod>` is the latest of: the day its feed file last
   changed, the day the scorecard template last changed every agency page
   (`AGENCY_TEMPLATE_REVISED`, now 2026-10-06), and the page's first check.
   All three are days the page's content changed. The daily check date is
   still never used.
2. `AGENCY_TEMPLATE_REVISED` moves only in a change that alters what every
   agency page says, set to that change's deploy date. Styling, wording
   fixes and per-feed data do not move it. A lastmod Google cannot verify
   against the page teaches it to ignore every lastmod.
3. Each redirected scorecard's `brief/`, `board/` and `fixes/` URLs redirect
   to the successor's scorecard, not to its brief or board: those are
   noindex, and the SEO contract requires a redirect to land on an
   indexable page. They are listed in `_meta/retained-agency-redirects.json`,
   and the checker accepts those three companion paths in the manifest.
   A redirect stub under a noindex path is validated as a redirect (no
   robots meta), not as a noindex page.

## Not decided here

- No agency page is noindexed, merged or rewritten for the cohort. The data
  gives no on-page feature to act on, and the pages Google keeps are built
  from the same template.
- The `?finding=` deep links, `/compare/?a=` and `/claim/?agency=` produce
  the "Alternate page with proper canonical" entries. Each canonicalizes
  correctly; they stay.

## Consequences

- About 1,500 URLs Google reports as 404 become redirects, and move to
  "Page with redirect" over the following weeks.
- Every agency sitemap entry carries a date no earlier than 2026-10-06, so a
  page last crawled in September is a candidate for recrawl. Whether Google
  recrawls, and whether the cohort returns, is measured by re-inspecting the
  2026-10-11 sample 4 to 8 weeks after deploy.
- A future template change that forgets to move the constant leaves lastmod
  where it was, which is the behavior before this ADR.
