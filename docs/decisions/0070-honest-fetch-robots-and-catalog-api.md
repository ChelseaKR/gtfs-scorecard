# ADR 0070: An identifying User-Agent, robots.txt on every feed request, and the catalog read only through its API

**Status:** Accepted (2026-10-13). Decided by the maintainer. The number 0070
leaves 0069 to the agency-coverage change on `feat/expand-agency-coverage`.

## Context

`docs/mobility-database-access-review.md` (2026-08-15) left three questions
open. On 2026-10-13 the maintainer answered them.

- The fetcher sent a desktop Chrome User-Agent (`fetch.py`) so that bot
  filters would not refuse it, and never read robots.txt.
- The daily fetch fell back to MobilityData's hosted copies on
  `files.mobilitydatabase.org`, and the weekly `supersessions` step read
  `files.mobilitydatabase.org/feeds_v2.csv`. That host's robots.txt is
  `User-agent: * / Disallow: /`.

## Decision

1. **Every feed request identifies the project.** The User-Agent is
   `gtfs-scorecard/<version> (+https://gtfsscorecard.org)` for the schedule
   fetch, realtime sampling, the liveness check and the publisher sweep. Nothing
   presents as a browser.
2. **robots.txt is read before any feed request** (`robots_policy.py`, one
   request per host per process).
   - An explicit `Disallow` covering the feed path is obeyed. The record is
     "not fetched: robots disallows". Its page says so beside the last grade
     measured, with that grade's date. It is never shown as a zero.
   - A 404 or 410 at `/robots.txt` means no rules.
   - A 403 at `/robots.txt` means no file only on hosts in
     `MISSING_OBJECT_403_HOSTS`: object stores and API gateways where 403 is
     the generic answer for any object that does not exist. Each entry names
     its reason. Each was checked on 2026-10-13 by requesting `/robots.txt`
     and a random path, and both answered with the store's own AccessDenied
     XML or API Gateway's "Missing Authentication Token". A WAF or CDN
     refusal (Cloudflare challenge pages, Akamai, a city firewall) is not
     on the list.
   - Anywhere else, a 401, 403, 429 or 5xx, a redirect that leaves the
     `robots.txt` path, an HTML page served in its place, or a failure to read
     it puts the host off-limits. The record is "not fetched: robots.txt
     refused or unreadable".
   - A realtime feed refused this way is "not measured", never the agency's
     outage.
3. **Not-fetched records are counted apart.** The run summary records the
   reason, `/status/` names it beside each record and counts them, and they
   are left out of the "run completed with warnings" fraction, which is about
   publisher outages.
4. **`files.mobilitydatabase.org` is not read.** There is no mirror fallback
   to it, and `fetch_catalog` refuses a URL on it before any request. Manual
   `sync` and `supersessions` default to the `storage.googleapis.com` export.
5. **The weekly catalog update reads the Mobility Database API**
   (`catalog_api.py`, `--catalog api`), exchanging `MOBILITY_FEED_API_TOKEN`
   for an access token and paging `/v1/gtfs_feeds`. Without the token the
   workflow pauses with a warning and a step-summary line, and the commands
   exit 3 before any request. There is no fallback source. The API host is an
   authenticated service the maintainer chose to use under its terms. Its
   `/robots.txt` redirects to a sign-in page, and robots rules are not applied
   to it.

## Measured on 2026-10-13

Each of the 2,495 active records was checked with the new rules and the new
User-Agent (one robots.txt read per host, and one request for each feed the
rules allow). It was compared with the 2026-10-12 daily run.

| State under the new rules | Records | Of those, reachable on 2026-10-12 |
| --- | --- | --- |
| Fetched as before | 1,983 | 1,977 |
| Not fetched: robots disallows | 307 | 302 |
| Not fetched: robots.txt refused or unreadable | 98 | 78 |
| Feed request fails (404, 403, 401) | 107 | 69 |

- **Disallowed:** 242 of the 302 are on `www.data.gouv.fr`, whose robots.txt
  disallows `/api/1/datasets/r/` and `/datasets/r/`, the resource-redirect
  paths the French records use. Most of the rest are BC Transit's
  `bct.tmix.se` (34) and MTA New York's `web.mta.info` (10), both
  `Disallow: /`.
- **Off-limits (all 98):** 36 non-allowlisted 403s (Cloudflare challenges,
  Akamai, city WAFs, `transitfeeds.com`), 27 unreadable, 25 HTML pages served
  at `/robots.txt`, 5 redirects off it, and 5 other errors (401, 429, 500, 503,
  520).
- **Feed fails:** 61 of the 69 newly failing answer 404 at the origin and were
  being scored from the MobilityData mirror, which is now gone. 6 answer 403
  to the identifying User-Agent and are the only measured cost of dropping the
  browser string.
- The allowlist admits 628 records whose host answers 403 at `/robots.txt`
  (505 on `api.gtfs-data.jp`, the rest on S3 and S3-compatible stores). Without
  it they would all be off-limits.

## Consequences

- About 450 records stop refreshing. They keep their last measured grade and
  page, now with the reason, and age out through the existing freshness
  rules. France loses most of its daily coverage until those records move to
  URLs that robots.txt allows (for example a direct resource URL from the
  data.gouv.fr API).
- The weekly discover job does nothing until `MOBILITY_FEED_API_TOKEN` is set.
- The `/fetcher/` page now describes the User-Agent and robots behavior.
