# ADR 0069: Grow coverage by repairing retired feeds first, then by small verified cohorts

**Status:** Accepted (2026-10-13)

## Context

A coverage measurement on 2026-10-12 and 2026-10-13 compared the registry with
the open catalogs it draws from and with FTA's reporter roster.

- **The registry already holds most of what the compliant Mobility Database
  export offers in the US.** Against the `storage.googleapis.com` export that
  `scorecard discover` reads, 795 US Schedule records are already tracked, 365
  are excluded by the catalog itself (355 inactive or deprecated, 9 behind a
  key, 5 marked unofficial), and 28 are open, active and untracked. Of those
  28, about half are not new agencies at all: they are the catalog's current
  record for an agency we track on a retired URL.
- **The larger gap is stale URLs on tracked agencies.** The daily run of
  2026-10-12 could not reach 90 feed records. The catalog had already retired
  many of them and named a successor, but `scorecard supersessions` only acts
  when the successor is a record we publish. When it is not, the record is
  listed as "retired, with no successor we publish" and keeps requesting a
  dead URL. Kansas City, Chattanooga and Richmond were on that list.
- **NTD gives a reporter-unit denominator.** Re-running
  `scripts/ntd_reporter_coverage.py` against the current registry: of 1,253
  NTD reporters with fixed-route service in report year 2024, 601 match a
  registry record on identifier, exact name, domain or close name, 41 match
  only a record in the Transitland Atlas or the Mobility Database, and 447 to
  611 match nothing (lenient to strict). For full reporters it is 313 of 474.
  Several of the 41 are agencies we track under a name the join cannot match
  (MTA New York City Transit, MTA Maryland, Houston METRO, Culver City), so the
  real gap there is an `ntd_id`, not a feed. The rest, mostly small
  Pennsylvania authorities on Avail InfoPoint hosting, are real gaps.
- **robots.txt is not read by the daily fetcher**, and the fetcher presents a
  browser User-Agent (`fetch.py`, discussed in
  `docs/mobility-database-access-review.md`). A sweep of the 530 hosts the
  registry requests found 666 current records on hosts whose `/robots.txt`
  answers 403 (505 of them `api.gtfs-data.jp`, and S3 buckets, which answer 403
  for any missing object) and 307 on hosts whose rules disallow the feed path
  (246 on `www.data.gouv.fr`). Applying the strictest reading to the existing
  registry would remove about 39 percent of it. That is a maintainer decision
  and is not taken here.
- **Search.** ADR 0067 found that US agency pages first published together on
  2026-07-03 are 18 percent indexed, while every agency page published later is
  93 to 100 percent indexed. Nothing on the page separated kept from dropped.
  A burst of hundreds of similar pages at once is the one difference on record.

## Decision

1. **Repair before adding.** `scorecard supersessions` now also proposes a
   *repoint* (`catalog_repoint.py`): when a tracked record's catalog record is
   deprecated and its redirects reach exactly one current Schedule record that
   no registry record tracks, the tracked record keeps its id, page and history,
   and its `static_gtfs_url` and `mdb_id` move to the successor. A catalog-written
   `license_note` follows to the successor's terms; a curator-written note
   stays. A comment above the record names the two catalog ids. The weekly
   `discover` workflow already runs `supersessions --apply` into a review pull
   request, so these arrive the same way.
2. **A repoint is held, with its reason, when** the redirects reach more than
   one current record; the successor needs a key, is marked unofficial or has
   no usable URL; the review flags from `supersession_review` say it is not the
   same agency (different state or country, a name that is not a rename); a
   note on the record names the host it is tracked on; or the successor host's
   robots.txt refuses us.
3. **New URLs pass a robots check first** (`robots_policy.py`). One request per
   origin, with an identifying User-Agent and never a browser one. A 404 or 410
   is no rules. Any other error status, a redirect off the `robots.txt` path,
   or an HTML page served there is a refusal. Otherwise the rules are parsed
   for our User-Agent. A network failure is a refusal. This applies to URLs the
   project starts requesting through this path. It does not change the daily
   fetcher.
4. **New agencies arrive in small, verified cohorts.** A record is added only
   when it is a public operator (an NTD reporter, or an official catalog
   record), no registry record tracks it under another name or URL, its host's
   robots.txt permits the request under the rules in item 3, and a fetch with
   an honest User-Agent returns a valid GTFS archive whose service runs past the
   day of review. A record that never scores never gets a page, so a dead or
   blocked feed adds nothing to the site. A cohort stays under about 50 records
   a week while the July cohort's indexing is being re-measured.
5. **A retired alias of the record being repaired does not block the repair.**
   The 2026-07-11 dedupe sometimes kept the twin on the dead URL canonical and
   aliased the twin on the live one (Stanislaus Regional Transit was graded on
   a Trillium feed that expired in 2020 while its alias held the operator's
   current feed). The alias is the evidence the repair follows. A successor
   tracked by any other live record is still a duplicate for a curator, not a
   repair.
6. **This change applies the rule once by hand.** Eight repoints (Kansas City,
   Chattanooga, Richmond, Virginia Breeze, Monroe County, Birmingham,
   Stanislaus, and Thousand Oaks, whose URL was already right and whose catalog
   id moves) and 23
   new records (16 Pennsylvania NTD reporters from the Transitland Atlas,
   Manchester, Charlottesville, Danville's fixed-route feed, two Golden Crescent
   feeds, Jefferson County NY, and Jackson County IL). The tool proposed two
   more repoints that are not applied: El Paso, whose old feed is still current
   and whose successor may be a different operator, and Xpress, whose successor
   URL answers 404.

## Not decided here

- The daily fetcher's User-Agent and robots handling, and the weekly
  `supersessions` step's catalog source. The maintainer decided both on
  2026-10-13 (an identifying User-Agent, obey robots.txt with a short tested
  allowlist for object stores and API hosts, and the Mobility Database API in
  place of `files.mobilitydatabase.org`). They land in a separate change.
- How many more NTD-reporter cohorts to add, and in what order. The measurement
  that sizes them is in the pull request for this change.
- Twelve agencies carry two live records where the catalog's redirect joins
  them, the dead one with the catalog id and the live one without (Bellflower,
  Beach Cities, Palo Verde, Glendora, Huntington Park and others). Giving the
  live twin its catalog id would let the weekly supersession step retire the
  dead one. Each pair needs a look first, so none is changed here.

## Consequences

- Seven indexed scorecards that were showing a stale or unreachable feed should
  carry a current grade after the next daily run. No page is added or removed
  for them.
- The registry grows from 2,672 to 2,695 feed records, 2,495 to 2,518 active.
  The daily run's shards grow by about one feed each; at the measured median of
  roughly 18 seconds per feed that is well inside the 55-minute shard budget.
- The weekly supersession report gains a section listing repoints, ready and
  held, so a stale URL with a catalog successor is no longer silent.
- A host that refuses non-browser clients at `/robots.txt` (several municipal
  CivicPlus sites, `gtfs.calitp.org` redirecting to its landing page) cannot be
  reached through this path. Those repoints wait for a person.
