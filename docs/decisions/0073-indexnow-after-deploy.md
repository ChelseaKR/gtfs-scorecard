# ADR 0073: Announce new and changed pages to IndexNow after each deploy

**Status:** Accepted (2026-11-05). Decided by the maintainer.

## Context

IndexNow is how a site tells Bing (which ChatGPT search leans on) and the
other participating engines that a page is new or changed, instead of
waiting for the next crawl. The maintainer's other sites (Trout Truck, Next
Home Game, Lake Notice, Tide Hours) run the same stdlib-only `indexnow.py`;
their deploys on 2026-11-04 and 2026-11-05 got HTTP 200 or 202.

Sending every URL on every deploy is the pattern IndexNow throttles. This
site does not need a separate change record: a sitemap `<lastmod>` here is a
date the page's own content changed, never the build clock (ADR 0067,
`test_sitemap_lastmod_derived.py`). On 2026-11-05 the live sitemap had 3,867
URLs: 509 dated that day, 303 the day before, 77 the day before that, and 17
to 44 on each earlier day. 33 carry no `<lastmod>`.

## Decision

1. In the Deploy site workflow (`pages.yml`), after every gate in the
   `lighthouse` job and before the Pages upload, `indexnow.py select`
   compares the assembled `_site/sitemap.xml` with the live one, which is
   still the previous deploy at that point. A URL is selected when it is new
   or its `<lastmod>` differs. A URL with no `<lastmod>` on either side is
   unchanged. A build with no content change selects nothing and sends no
   request. A daily deploy is expected to send a few hundred URLs; a move of
   `AGENCY_TEMPLATE_REVISED` sends every agency page once, which is correct.
2. Only https URLs on gtfsscorecard.org, only pages that exist in the build
   without a robots noindex, no duplicates, at most 10,000 a request. If the
   live sitemap cannot be read, nothing is sent: unknown is not "everything
   changed". A 404 (a first deploy) means every page is new.
3. A separate `indexnow` job submits the list. It needs `production-smoke`,
   so it runs only once the live crawl surface is verified. It has
   `contents: read`, no AWS role and no secret, and checks out only
   `indexnow.py`.
4. The key file `web/2bae891ac84ac855329ac50501bdc0aa.txt` reaches the site
   root through the existing `cp -r web/. _site/`. It is public by design:
   IndexNow fetches it to check that this site owns the host.
5. The script exits 0 on any problem and prints a `::notice::` line, so it
   never fails the deploy and needs no `continue-on-error`.

## Consequences

- No page, sitemap or robots change, and no new third-party request from any
  page. The SEO contract and page-size budgets run before selection, as
  before.
- `pipeline/tests/test_indexnow.py` checks the golden site assembled the way
  `pages.yml` assembles `_site`: against an identical live sitemap it sends
  nothing (the negative control), and one moved agency `<lastmod>` selects
  exactly that page. A workflow test pins the step order and the job's
  dependency on `production-smoke`.
- Reversible: delete the two steps, the `indexnow` job and the key file.
