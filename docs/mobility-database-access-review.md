# Mobility Database access review

**Status:** open question for the maintainer. Nothing in this document changes
fetching behaviour; it exists so the decision can be made on facts.

**Reviewed:** 2026-08-15. All URLs and robots.txt bodies below were fetched on
that date and are quoted verbatim.

**The question.** `files.mobilitydatabase.org/robots.txt` disallows every agent
on every path. This pipeline requests that host. Does it, and should it?

---

## 1. What the pipeline does today

Traced in code, not inferred from constants. There are three separate Mobility
Database touchpoints, and only one of them is both automated and pointed at the
disallowing host.

| # | Path | Host requested | Runs when | Disallowed host? |
|---|---|---|---|---|
| A | `scorecard discover` | `storage.googleapis.com` | weekly, `discover.yml` | no |
| B | `scorecard sync` | `files.mobilitydatabase.org/feeds_v2.csv` | manual only | yes |
| C | feed-fetch mirror fallback | `files.mobilitydatabase.org/<mdb-N>/latest.zip` | **daily, automatically** | **yes** |

### A. `scorecard discover`: weekly, and not on the disallowing host

`_cmd_discover` (`pipeline/src/scorecard_pipeline/cli.py:1301`) defaults to
`DEFAULT_CATALOG_URL`, which is the legacy export:

```python
LEGACY_MOBILITY_DATABASE_CATALOG_URL = (
    "https://storage.googleapis.com/storage/v1/b/mdb-csv/o/sources.csv?alt=media"
)
```

That is Google Cloud Storage, not `files.mobilitydatabase.org`. This is the one
Mobility Database call `discover.yml` makes on a schedule, and it does not touch
the disallowing host.

### B. `scorecard sync` points at the disallowing host, but nothing schedules it

`_cmd_sync` (`cli.py:1131`) defaults to `DEFAULT_PROPOSAL_CATALOG_URL`, which is
`MOBILITY_DATABASE_FEEDS_V2_URL = "https://files.mobilitydatabase.org/feeds_v2.csv"`
(`mobilitydb.py:40`). No workflow in `.github/workflows/` invokes `scorecard
sync`; it appears only in docs as a manual registry-intake step. So this is a
configured URL that is requested only when a human runs the command.

### C. The mirror fallback, the one that runs daily

This is the finding that matters. `fetch.py:410-433`: when an agency's own feed
URL fails, the fetcher falls back to MobilityData's hosted mirror.

```python
except (requests.exceptions.RequestException, UnsafeURLError) as origin_exc:
    from .mobilitydb import hosted_mirror_url
    ...
    mirror = hosted_mirror_url(agency.id, agency.name, agency.static_gtfs_url, agency.mdb_id)
    ...
    final_url = _fetch_to(mirror, dest, max_bytes=max_bytes, retries=0, large=large)
```

and `hosted_mirror_url` hand-builds the URL (`mobilitydb.py:1049`):

```python
return f"https://files.mobilitydatabase.org/{normalized}/latest.zip"
```

**This is not hypothetical.** The pipeline counts it. `RunOutcome.mirrored` is
set from `fetched.source == "mirror"` (`cli.py:374`), aggregated in
`run_summary.py:115`, and published. Today's `api/v1/run-status.json` reports:

```
"mirrored": 125
```

So the most recent run made on the order of 125 requests to a host whose
robots.txt disallows all agents. This is a real, recurring, automated request
path, not a dormant constant.

---

## 2. What robots.txt actually says, and whether we consult it

`https://files.mobilitydatabase.org/robots.txt` HTTP 200, fetched 2026-08-15:

```
User-agent: *
Disallow: /
```

For contrast, `https://mobilitydatabase.org/robots.txt` HTTP 200:

```
User-Agent: *
Allow: /

Sitemap: https://mobilitydatabase.org/sitemap.xml
```

And `https://api.mobilitydatabase.org/` returns HTTP 302 with
`Invalid GCIP ID token: empty token`. The API is authenticated, not open.

**Does the fetcher consult robots.txt? No.** There is no robots handling
anywhere in the pipeline's fetching code. Every `robots` match in
`pipeline/src/` is about *generating* the scorecard's own `robots.txt`
(`render_site.py:11074`) or its meta tags. `net.py`, the single choke point all
feed downloads pass through, never retrieves or parses a robots.txt. So the
pipeline is not deliberately overriding a disallow. It has never looked.

### Two further facts that bear on the values question

These are independent of the robots question and, in my read, matter more.

**The feed fetcher presents as a browser.** `fetch.py:30`:

```python
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
```

The comment above it gives the reasoning honestly: many agencies serve GTFS from
behind a WAF that 403s non-browser agents, which blocked legitimate public-feed
fetches. But the effect is that the operator of any host we fetch, including
`files.mobilitydatabase.org`, cannot identify this client, cannot rate-limit it
specifically, and cannot block it without blocking Chrome.

Note that `liveness.py:36` already does this the honest way:

```python
USER_AGENT = f"gtfs-scorecard liveness (+{BASE_URL})"
```

So the project has both patterns in it today.

**403 is treated as retriable.** `net.py:40`:

```python
RETRIABLE_STATUS = frozenset({403, 408, 425, 429, 500, 502, 503, 504})
```

with `FETCH_RETRIES = 3` and exponential backoff, and the inline comment "a WAF
403 that often lets a second request through." A 403 is the server saying no.
Retrying it three times is, on the project's own stated rail, closer to
circumventing a block than to honouring one. (The mirror fetch itself passes
`retries=0`, so this applies to origin fetches, not to the Mobility Database
path.)

---

## 3. Is retrieving a documented file at a known URL "crawling"?

Genuinely arguable. Both readings, as fairly as I can put them.

### The case that RFC 9309 does not reach this

- **RFC 9309 is addressed to crawlers.** It defines its subject as "automatic
  clients known as crawlers," services that *discover and traverse* URIs. This
  pipeline discovers nothing on that host. It requests one CSV at a documented
  address, and per-agency zips at addresses derived from an identifier already
  pinned in our registry. No link is followed, no path enumerated, no index
  read.
- **The operator publishes the very URL in its own FAQ.** MobilityData's FAQ
  tells users they can "download GTFS and GTFS Realtime feeds via the
  spreadsheet" and links `files.mobilitydatabase.org/feeds_v2.csv`. An operator
  that documents a download URL on its public help page intends that URL to be
  downloaded, including by software.
- **A blanket disallow on a file bucket usually means "don't index me."** The
  human-facing site is `Allow: /` with a sitemap; the asset host is
  `Disallow: /`. That is the textbook configuration for "keep the bucket out of
  search results," not "no automated client may ever retrieve these bytes."
- **The mirror exists to be fetched.** MobilityData hosts copies of feeds
  precisely so consumers can still get a feed when the agency's own server is
  down. Fetching the mirror when the origin is unreachable is the mirror's
  stated purpose, and it takes load *off* the agency.
- **The operator's actual legal instrument is silent on this.** The Terms and
  Conditions (see §4) contain no anti-automation, anti-scraping, or rate-limit
  clause.

### The case that it does reach this, or that it does not matter whether it does

- **"Automatic client" is a plain-language fit.** An unattended daily job
  issuing ~125 requests to a host is an automatic client on any ordinary
  reading. Narrowing "crawler" to "thing that follows links" is a convenient
  definition, and it is being chosen by the party it benefits.
- **`Disallow: /` is unambiguous and blanket.** It is the machine-readable form
  of the operator's wishes at that host. It does not carve out "except
  documented files." Deciding that a friendlier sentence on a different
  hostname's FAQ page overrides the explicit directive at *this* hostname is
  exactly the sort of reasoning-toward-the-desired-answer this project refuses
  elsewhere.
- **The FAQ documents one file, not the pattern we actually use.** It points at
  `feeds_v2.csv`, path B, the manual one. It does not document per-agency
  `<mdb-N>/latest.zip` retrieval, which is what path C does automatically. The
  strongest "they told us to" argument covers the path we use least.
- **This project's own rail is stricter than RFC 9309.** The standing rule is
  "robots respected, never circumvent a block." That rule does not turn on
  whether an RFC formally binds; it turns on whether a host said no. This one
  did, in the only machine-readable place it had to say it.
- **The browser User-Agent poisons the well.** Whatever the right answer on
  robots, fetching a `Disallow: /` host while presenting as Chrome means the
  operator has no way to notice, throttle, or refuse us. That is the part I do
  not think survives scrutiny under this project's rails, and it does not depend
  on resolving the crawler question at all.

---

## 4. Terms of service

There is a terms document separate from robots.txt:
**https://mobilitydatabase.org/terms-and-conditions** ("Mobility Database API
Terms and Conditions").

What it says:

- The API codebase is Apache-2.0; **the catalog metadata is CC0 1.0** (public
  domain dedication). Individual feed contents remain under their own
  publishers' licences, and the consumer is responsible for complying with each.
- MobilityData may modify, suspend, or discontinue the API without notice, and
  disclaims liability for availability.
- Terms may be amended at any time without notice.
- Governed by the laws of Quebec and Canada.

What it does **not** say: there is no clause prohibiting automated downloading,
no scraping prohibition, no rate limit, and no attribution requirement.

So the operator's written terms do not forbid this use. The only artefact that
arguably forbids it is the robots.txt.

---

## 5. What the operator sanctions

MobilityData's sanctioned programmatic route is **the Mobility Feed API**, and
it requires registration:

- Access needs an account created at `mobilitydatabase.org` and a **bearer
  access token**, minted from a refresh token and periodically renewed. This is
  confirmed by the live 302 from `api.mobilitydatabase.org` (`Invalid GCIP ID
  token: empty token`).
- The FAQ frames the API as the intended integration path: "Our API allows you
  to pull data from our database seamlessly. Since our URLs are stable and
  checked for updates on a daily basis, data doesn't get dropped if an agency's
  website is down, or if the link expires."
- Everyone gets free access to the database; **an account is required to use the
  API** or to add a feed.

**This repo has already built that client and it is switched off.**
`pipeline/src/scorecard_pipeline/feedapi.py` is a complete Mobility Feed API
client against `https://api.mobilitydatabase.org/v1`. It reads
`MOBILITY_FEED_API_TOKEN` from the environment (`cli.py:84`, `cli.py:2057`),
and **no workflow in `.github/workflows/` sets that variable**, so in CI the
module does nothing by design:

> "The API needs a bearer token (an access token minted from a refresh token);
> without one, this module does nothing and the pipeline runs the validator as
> before."

Relevantly, the API returns a `hosted_url` per dataset, MobilityData's own
pointer to the hosted copy, rather than requiring a consumer to hand-build
`files.mobilitydatabase.org/<mdb-N>/latest.zip` as `hosted_mirror_url` does now.

**So the sanctioned route is: register an account, mint a refresh token, set
`MOBILITY_FEED_API_TOKEN` as a repository secret.** That is a decision only the
maintainer can make. It needs an account in her name, and acceptance of the API
terms.

---

## 6. Recommendation

I would separate two things that are getting conflated.

**On the robots question, I lean toward "this is not crawling" but I would not
rest on it.** The operator documents the file host as a download location and
its written terms permit programmatic use; a blanket disallow on an asset bucket
is far more consistent with "keep this out of search indexes" than with "never
retrieve these bytes." But the argument is close enough that I would not want it
to be the only thing standing between this project and its own stated rail.

**On the User-Agent, there is no real argument.** Fetching any host, least of
all one whose robots.txt says `Disallow: /`, while presenting as
`Chrome/125.0.0.0` fails "honest identifying User-Agent" plainly, and it removes
the operator's ability to enforce whatever preference it holds. Retrying 403s
three times sits badly next to "never circumvent a block" for the same reason.
This is the part I would fix regardless of how the robots question is decided.

**The clean resolution is to stop needing the argument.** The sanctioned,
authenticated route already exists in this codebase and is one secret away from
working. Taking it makes the robots question moot for path C: an authenticated
API client using a documented endpoint under accepted terms is unambiguously
sanctioned, and MobilityData gets exactly what an operator wants: a named,
attributable, throttleable client.

### Smallest changes, in increasing order

1. **Honest User-Agent (smallest, and I would do this first).** Send an
   identifying UA with a contact URL to `files.mobilitydatabase.org` at minimum,
   following the pattern `liveness.py:36` already uses. One constant and one
   header map. It does not risk the agency-WAF problem the browser UA was
   introduced to solve, because it can be scoped to this host.
2. **Take the sanctioned route for path C.** Register, set
   `MOBILITY_FEED_API_TOKEN`, and have `hosted_mirror_url` return the API's
   `hosted_url` instead of hand-building a `files.` URL. Removes the
   unauthenticated file-host fetch from the daily path entirely. Requires the
   maintainer's account and acceptance of the API terms.
3. **Teach the fetcher robots.txt.** A general robots check in `net.py` with a
   cache would make the rail enforced in code rather than in review. Larger, and
   it needs a policy decision about what to do when an *agency's* own host
   disallows a feed the agency publishes for exactly this purpose, so it should
   not be bundled with the above.
4. **Record whatever is decided.** An ADR under `docs/decisions/`, in the style
   of ADR 0042, so the reasoning survives and nobody has to re-derive it.

### What needs the maintainer

- Whether to register a Mobility Database account and add
  `MOBILITY_FEED_API_TOKEN` (item 2). Only she can accept the API terms.
- Whether the robots reading in §3 is one she is willing to stand behind, or
  whether she would rather stop requesting the host until item 2 lands.
- Whether the browser User-Agent stays for agency origins. The WAF problem it
  solves is real, and narrowing it to "honest UA for cooperating hosts, browser
  UA for hosts that 403 non-browsers" is itself a values call, not a technical
  one.

---

## Sources

- `https://files.mobilitydatabase.org/robots.txt` (fetched 2026-08-15)
- `https://mobilitydatabase.org/robots.txt` (fetched 2026-08-15)
- [Mobility Database API Terms and Conditions](https://mobilitydatabase.org/terms-and-conditions)
- [Mobility Database FAQ](https://mobilitydatabase.org/faq)
- [MobilityData/mobility-feed-api](https://github.com/MobilityData/mobility-feed-api)
- [MobilityData/mobility-database-catalogs](https://github.com/MobilityData/mobility-database-catalogs)
- RFC 9309, Robots Exclusion Protocol
