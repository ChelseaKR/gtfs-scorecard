# ADR 0080: Clearance logs in the sitemap, the two WMATA feeds, and /app/'s canonical

**Status:** Accepted (2026-11-17). Approved by the maintainer.

## Context

A Search Console review on 2026-11-17 found three small indexing problems.

- **Clearance logs.** 812 of the 1,171 clearance logs in the sitemap had no
  search impression in the 90 days to 2026-11-15. The ones that did had about
  384 impressions a month at a CTR of 0.84%, and some compete with their own
  agency page ("go transit gtfs" reached the clearance log at 9.3 and the
  agency page at 6). The October indexing report advised against any noindex,
  and recommended a sitemap closer to the pages that earn traffic.
- **WMATA.** Two agency pages, `…-wmata/` and `…-wmata-1847/`, were both
  "Crawled - currently not indexed", and the review read them as one agency
  twice. Reading the registry shows two feeds: WMATA's bus feed
  (`bus-gtfs-static.zip`, Mobility Database 1846) and its rail feed
  (`rail-gtfs-static.zip`, 1847). Their names end in "Bus" and "Rail", but a
  58-character name is cut in the title, so both titles read "Washington
  Metropolitan Area… [MDB 184x] GTFS feed quality". Nothing told them apart
  except a database number.
- **/app/.** The interactive directory declared `/agencies/` as its
  canonical. Google ignored that, indexed `/app/` as its own canonical, and
  showed it 52 times in 90 days.

## Decision

- The sitemap lists a clearance log only when it is indexable (three or more
  clearances, `FIXLOG_INDEX_MIN_RECEIPTS`) and its URL earned at least one
  impression. The list is `data/clearance-logs-in-sitemap.json`, written by
  `pipeline/scripts/clearance_log_sitemap_list.py` from a Search Console page
  export, never by hand. The first one holds the 384 logs with an impression
  from 2026-08-18 to 2026-11-15; about 359 of them are indexable today. A log
  that is left out stays indexable and linked from its scorecard and the
  directory. If the file is missing or unreadable, every indexable log is
  listed, as before.
- The structural SEO contract gains `sitemap_optional_path_patterns`, set to
  `/agency/*/fixes/`. A page under it may be in the sitemap or not; every other
  indexable page must still be listed, and a noindex page still may not. The
  rule is a path pattern, so the deploy check does not depend on the list and
  cannot freeze the site when the list changes (the 2026-10-06 freeze was a
  missing sitemap URL on an indexable clearance log).
- Neither WMATA record is retired: retiring one with a redirect would drop a
  real feed's scorecard. The maintainer approved labeling them instead on
  2026-11-17. Each gets a `feed_variant` ("Bus", "Rail"), which the
  title planner already uses to tell apart records whose titles collide, so
  the titles read "Washington Metropolitan Area… [Bus] GTFS feed quality" and
  "…[Rail]…". No name, URL or score changes.
- `/app/` names itself as canonical, and its `og:url` matches. It joins the
  sitemap, leaves `canonical_aliases`, and carries one static `<h1>` in its
  `<noscript>` block, beside the note for readers without JavaScript. With
  JavaScript the app renders its own heading, as before, so the page never
  shows two and the browser tests that wait for the app's heading still wait
  for the app. Its
  title and description are unchanged. It was the site's only canonical
  alias, so the contract now accepts an empty `canonical_aliases` map; the
  key itself stays required.

## Consequences

- Refresh the list after a later Search Console pull with the script. A log
  that starts earning impressions is listed only from then on, which is the
  point; it is crawlable through links in the meantime.
- Expected in Search Console: fewer sitemap URLs (about 812 fewer), and over
  the following weeks fewer clearance logs shown for agency-name queries. The
  WMATA pages may or may not be indexed once their titles differ; that is a
  judgment Google makes. For `/app/`, the declared canonical and the one Google
  chose should now agree in URL Inspection.
- `pipeline/tests/test_sitemap_clearance_wmata_app.py` holds the listing rule,
  its fallback, the committed list, the script, the two WMATA feeds and their
  titles, and `/app/`'s head. `pipeline/tests/test_site_seo.py` holds the new
  contract rule, with a negative control that fails without it.
- The committed corpus has no clearance logs (their receipts live only in
  production). The full-corpus render that checked this branch replaced the
  receipt loader with synthetic receipts: 236 log pages, of which the sitemap
  listed the 65 that were indexable and on the list, and left out the rest
  (indexable but not on the list, or thin and noindex). `check_site_seo.py`
  passed on that render with no findings.
- That render first failed with "'canonical_aliases' must be a non-empty
  object", a configuration error no PR check runs into. A test now loads the
  committed `site-seo.json` through the checker, so a config the deploy would
  reject fails in CI.
