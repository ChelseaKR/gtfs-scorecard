# Expansion plan: large features, integrations, data

A research-grounded plan for taking the scorecard from one agency-facing screen to
the national transit-data-quality platform. It is organized as the team can build
it: a near-term phase that stays serverless and single-digit dollars a month, a
big bet that justifies a backend, and a depth phase after that.

Sources are cited inline. A few claims (funding figures, market counts) came from
a research pass with a degraded web backend and are marked to re-verify.

## What the research said

- The canonical MobilityData `gtfs-validator` (v8.0.1, May 2026) only identifies
  issues; it does not apply fixes, and the realtime validator is point-in-time,
  not a longitudinal monitor.
  [validator](https://github.com/MobilityData/gtfs-validator),
  [rt-validator](https://github.com/MobilityData/gtfs-realtime-validator)
- The Mobility Database is a registry updated 1-3 times a month, not a daily
  archive, and it now exposes a feed API that already returns validation counts
  per dataset (`total_error/warning/info`, `validator_version`, report links).
  [catalog](https://github.com/MobilityData/mobility-database-catalogs),
  [feed API](https://raw.githubusercontent.com/MobilityData/mobility-feed-api/main/docs/DatabaseCatalogAPI.yaml)
- Cal-ITP publishes per-agency California GTFS quality reports monthly, with the
  data in `gs://calitp-reports-data/`. It is the closest precedent and a possible
  partner. [cal-itp/reports](https://github.com/cal-itp/reports)
- Open national data sources are ready to ingest: Mobility Database (CC0) and
  Transitland Atlas (CC-BY) feed lists; GBFS (~1,500 systems); NTD ridership and
  agency profiles; Census LODES and ACS for equity overlays; OSM and Wikidata for
  geometry ground-truth.
  [Atlas](https://raw.githubusercontent.com/transitland/transitland-atlas/main/README.md),
  [GBFS](https://raw.githubusercontent.com/MobilityData/gbfs/master/systems.csv),
  [NTD](https://www.transit.dot.gov/ntd/ntd-data)
- A national interactive map needs no backend (PMTiles on object storage +
  MapLibre), and cross-agency queries can run on DuckDB/Athena over partitioned
  object storage rather than an always-on database. Continuous national realtime
  is the one feature that forces a worker fleet (the Cal-ITP archiver polls every
  feed every 20 seconds).
  [PMTiles](https://github.com/protomaps/PMTiles),
  [cal-itp/data-infra](https://github.com/cal-itp/data-infra/tree/main/services/gtfs-rt-archiver-v3)

## Phase A: near-term, serverless, builds on what exists

| # | Unit | What | Effort | Depends on |
|---|---|---|---|---|
| A1 | **Embeddable live-grade badge** | A copy-paste Markdown/HTML badge on each agency page, served from the `badge.svg`/`badge.json` already published. Distribution with no new backend. | done | the published badge artifacts |
| A2 | **Feed time-machine** | A per-agency, plain-language timeline of what changed at each snapshot (grade moves, expiry-window crossings, category-driven score swings), the text companion to the trend chart. Done from the dated artifacts; true GTFS-file diffing still needs the raw feed archived. Now also composes finding-level diff events (codes cleared/introduced across the dated artifacts) and a short deterministic "grade story" paragraph — a few dated, traceable, correlational sentences narrating how the current grade came to be — rendered above the timeline on the agency page. No LLM. | done | dated artifacts |
| A3 | **Self-serve instant onboarding** | Productize `submit.html` + `scorecard try` into a hosted "paste a feed URL, get a grade in a minute" flow, against the Mobility Database's week-long PR onboarding. Built as an issue-form to Actions to comment flow, so it stays serverless. [page](https://gtfsscorecard.org/try.html) | done | the ad-hoc scorer |
| A4 | **Conformance trust mark** | Formalize a pass threshold (zero validator errors, a valid freshness window, an accessibility floor) and issue it as a credential. Extends NTD readiness and the badge. [doc](conformance.md) | done | NTD readiness, badge |
| A5 | **CI Action** | Package `scorecard try --min-grade` as a reusable GitHub Action so a vendor or agency build fails on a bad feed before publishing. A community validator action already exists to model. [precedent](https://github.com/npaun/md-gtfs-validator-action) [usage](ci-action.md) | done | the CI gate |
| A6 | **Ingest from the Mobility Feed API** | Reuse `api.mobilitydatabase.org` per-dataset validation to skip re-running the Java validator where MobilityData already validated the identical bytes. A cost lever on top of the sha-keyed validator cache; full feed-list auto-discovery is a follow-on. [ADR](decisions/0011-mobility-feed-api-reuse.md) | done | the validator cache |

Effort: S = days, M = a week or two. All of Phase A holds the single-digit-dollar
budget.

## Phase B: the big bet, justifies a backend

- **National GTFS-Realtime monitoring.** Serverless tier shipped (ADR 0012): an
  Actions cron samples each agency's realtime feeds on a schedule and records an
  uptime and header-lag time series in `data/rt-health`, surfaced as "realtime
  reliability" on each page. A high-cadence archiving session bridges to the fleet
  (`rt_archiver.py` plus `rt-archive.yml`): `scorecard rt-archive` polls one
  agency on the spec's 20s cadence for a bounded window in a single job, recording
  a high-resolution observation per round. The always-on worker-fleet tier
  (continuous polling into object storage, the Cal-ITP pattern) is the final
  escalation, triggered when the cohort or a sub-minute-outage need outgrows it.
  Ingest realtime
  through transit.land and regional aggregators (one `api.511.org` key yields 30+
  Bay Area operators) rather than per-agency plumbing.
  [511](https://511.org/open-data/transit)
- **Cross-agency trends and a public API.** Serverless tier shipped (ADR 0013): a
  versioned static API at `/api/v1/` (agencies list, leaderboard, per-state
  aggregates, national stats) plus a human [/leaderboard/](https://gtfsscorecard.org/leaderboard/),
  precomputed from the index and served as flat JSON, no query server. The
  warehouse (DuckDB or Athena over partitioned object storage, a keyed read API,
  or transit.land's Go + Postgres + GraphQL model) is the escalation once
  interactive multi-tenant queries appear.
  [transitland-lib](https://github.com/interline-io/transitland-lib)
- **National map.** Shipped (serverless tier): every located agency as a point in
  one small `map.geojson`, rendered client-side by MapLibre over the keyless
  demotiles basemap, at [/map/](https://gtfsscorecard.org/map/). Geometry is the
  feed's median stop, computed at score time. PMTiles is the optimization once the
  point count makes a flat GeoJSON heavy; the no-tile-server property already holds.

## Phase C: depth

- **Equity overlays** from Census ACS: shipped at state level and wired live
  (ADR 0015). A weekly `equity.yml` workflow fetches per-state ACS poverty,
  zero-vehicle (B08201), and disability shares from the Census API, joins them to
  agency grades, and publishes `/api/v1/equity.json` and the
  [/equity/](https://gtfsscorecard.org/equity/) page that flags high-need states
  carrying many low-grade feeds, so a program triages data-quality help by need.
  Zero grade impact. The tract-level refinement's
  geospatial core is built (`tract_equity.py`: point-in-polygon, bbox-prefiltered
  locate, stop-weighted served-area aggregation); wiring Census TIGER tract
  polygons and tract ACS values is the remaining data step (ADR 0015).
- **Routing-based QA**: shipped (router-free tier, ADR 0014). `routability.py`
  runs two pure "can a rider use it" checks on every feed: trips with no rideable
  leg (fewer than two stops) and boardable stops no trip serves. Zero-deduction,
  surfaced as "can riders use it?" on each page. The full OpenTripPlanner check is
  built as the gated escalation (`otp.py` plus a manual `otp-qa.yml`): it samples
  origin/destination pairs, plans them through an OTP instance, and asserts they
  return itineraries. The OTP graph build per feed is the heavy step the user
  runs; the daily run stays on the router-free checks.
- **Auto-fix layer**: shipped (first recipes). `autofix.py` plus `scorecard
  autofix <zip> --out fixed.zip` applies the safe, deterministic edits (trim
  surrounding whitespace, recase shouting stop and route names), preserving every
  other byte and reporting the diff. The conservative recipe set grows as more
  findings gain one unambiguous fix; opening a PR against the agency's feed repo
  is the downstream step on top of the patch this produces.
- **GBFS expansion**: shipped (currency check). `gbfs.py` plus `scorecard gbfs
  [--country US]` reads the open MobilityData GBFS catalog and reports how many
  shared-mobility systems are on the current 3.x line versus stuck on an outdated
  version, listing the laggards. Reading currency from the catalog's stated
  versions needs no per-system fetch; richer per-feed GBFS checks build on this.

## Architecture decision tree

- **Stays serverless** for the registry (flat JSON), per-agency scorecards (dated
  JSON), the national map (PMTiles), and search (a client-side index up to low
  thousands of agencies).
- **Forces a backend** only for continuous national realtime (workers + object
  store), cross-agency interactive queries (a warehouse over object storage), and
  a keyed public API. Cheapest order: client search, then a queryable SQLite or
  DuckDB/Athena artifact over object storage, then a managed database only if
  interactive multi-tenant queries appear.

## Funding (re-verify)

The funding research pass was throttled, so treat this as leads. The closest
models are MobilityData (nonprofit, membership and grants) and transit.land /
Interline (an open commons with paid commercial services), which together suggest
an open-core pattern: the dashboard and dataset stay free, while alerts, an API,
and SLAs are where a sustaining revenue or grant line could sit. The most direct
buyer or partner is Cal-ITP / Caltrans. Federal vehicles worth investigating, with
figures to confirm: FTA SMART grants, ITS4US, and Mobility for All. The US market
is roughly 3,000 NTD reporters, heavily weighted to small and rural agencies;
confirm the exact urban-versus-rural split before using it.
