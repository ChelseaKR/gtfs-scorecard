# Roadmap: scaling the scorecard from two agencies to a national service

> A multiyear plan for growing the GTFS Scorecard from its two pilot feeds to
> as many transit agencies as want it, and the tooling and infrastructure that
> growth requires. This picks up where the build plan in `CLAUDE.md` leaves
> off (Phase 4, "generalize"). It is a planning document, not a commitment;
> revise it as the pilot teaches us what agencies actually need.

## The shape of the opportunity

There are roughly 2,500 GTFS Schedule feeds published in the United States and
catalogued in the Mobility Database, and on the order of 10,000 worldwide. A
large share belong to exactly the agency this tool was built for: a small or
rural operator that exports GTFS from a vendor tool and has no independent way
to know whether the result is any good. California alone has close to 200
agencies that have moved through statewide data support programs.

The scorecard already validates and grades any one of those feeds. What stands
between two agencies and two thousand is not the scoring logic. It is four
things: getting feeds into the system without hand-editing YAML, running the
pipeline at volume without it becoming expensive or slow, storing and serving
a growing history of artifacts, and giving agencies and the people who support
them reasons to come back. The plan below is organized around those four, on a
roughly three-year horizon, with each year defined by the scale it has to
support rather than by a calendar.

## Guardrails that do not change as we grow

These are the commitments that keep the tool the thing it is. Every decision
below is checked against them.

- **Cost stays proportional and small.** The pilot runs at zero. A thousand
  feeds should run in the low tens of dollars a month, not hundreds. If a
  feature needs always-on infrastructure, it has to justify itself against
  that bar.
- **The frontend reads only pre-computed JSON.** No API server in the request
  path of the public site, no database the page depends on to render. History
  is dated artifacts. This is what keeps hosting trivial and the site fast.
- **Findings are framed as fixes, never failures, and absence of realtime is
  never a zero.** Scale does not get to erode the empathy. A statewide table of
  grades is the most tempting place to turn the tool into a leaderboard that
  shames small agencies; we do not.
- **We score on top of the canonical validator; we do not re-validate GTFS.**
  The value we add is the scoring, trending, prioritization, and plain
  language. When MobilityData ships a new validator version or notice, we
  adopt it rather than forking the rules.
- **We respect the feeds.** Polling etiquette holds at any scale: schedule
  feeds daily, realtime no faster than every 30 to 60 seconds, and we prefer
  archived snapshots over hammering an agency's endpoint when an archive
  exists.

## Year 1 — from two feeds to a region (target: 50 to 200 agencies)

> Status (2026-07): the registry passed this target ahead of plan and now
> tracks ~1,490 agencies across the US and Canada (~1,450 scored with published
> pages). The Year 1 work below is done; what remains is the storage/serving
> move (see `docs/follow-ups.md`).

The goal of year one is to prove the tool works unattended across a whole
region's worth of feeds, and to move off the parts of the pilot architecture
that only work at single-digit scale. The natural first cohort is California
small and rural agencies, because the statewide data guidelines the rubric
already cites give those agencies a reason to care about the grade.

### Onboarding without hand-editing YAML

Today an agency is added by editing `agencies.yaml` and opening a pull request.
That is the right primitive and it stays, but two things get added on top:

- **A Mobility Database sync.** A pipeline command that reads the Mobility
  Database API, filters to a region or a list, and proposes `agencies.yaml`
  entries with feed URLs, license notes, and realtime endpoints pre-filled. A
  human still reviews and merges, so the registry stays curated, but the
  typing goes away. This is how a region's worth of feeds gets added in an
  afternoon instead of a week.
- **A self-serve claim path.** A short web form that lets an agency or a
  liaison submit a feed URL. The submission opens a pull request automatically
  (via a small serverless function and the GitHub API). The "add your agency in
  ten minutes" promise in the docs becomes "add your agency in two minutes
  without knowing what YAML is."

### Artifacts move off git and onto object storage

Committing one JSON file per agency per day works for two agencies. At fifty it
makes the repo history noisy; at two hundred it is untenable. Year one moves
published artifacts to S3, fronted by CloudFront, keeping the exact same
`<agency>/<date>.json`, `latest.json`, and `index.json` contract the frontend
already reads. Because the web app only ever knew about URLs, this is a hosting
change, not a code change, exactly as ADR 0001 anticipated.

GitHub Pages can remain the host of the static site itself, or the site can
move behind the same CloudFront distribution. Either way the artifacts-only
contract means the two halves stay decoupled.

### The pipeline learns to fan out

The validator runs in a few seconds per feed, so two hundred feeds is still
well under any reasonable batch window. Year one keeps the GitHub Actions cron
but restructures the single job into a matrix that processes agencies in
parallel shards, so the wall-clock stays flat as the count grows. Each shard
fetches, validates, scores, and uploads its slice to S3 independently, and a
final small job rebuilds the cross-agency `index.json`. No new infrastructure,
just better use of the runner minutes we already have.

### First retention tool: expiration alerts

The single most valuable thing this tool can tell a small agency is "your feed
expires in N days and trip planners are about to drop you." Year one ships an
opt-in email digest built on this. An agency or liaison subscribes to a feed;
when freshness crosses a threshold (service end date inside the calendar
window, or a grade regression between runs), they get a plain-language note
with the fix. This is a scheduled job reading the artifacts that already exist,
plus a transactional email provider and a tiny subscription store. It is the
first thing that makes someone open the tool a second time.

### Year 1 infrastructure summary

```
Mobility DB sync (CLI)  ->  agencies.yaml (curated, in git)
Self-serve form         ->  serverless fn  ->  GitHub PR
GitHub Actions (cron, sharded matrix)
    fetch -> validate -> score -> publish
                                      |
                                      v
                                 S3 artifacts  ->  CloudFront  ->  static web app
Scheduled alert job  ->  email provider  (reads artifacts + subscription store)
```

Estimated cost at 200 agencies: still single-digit dollars a month. S3 storage
for a year of artifacts is trivial, CloudFront egress for a low-traffic site is
near zero, and the email volume is small.

## Year 2 — from a region to a country (target: 200 to 2,500 agencies)

Year two is where the architecture genuinely changes, because two things stop
being free: compute at thousands of feeds a day, and realtime sampling, which
needs sustained polling that a cron job is poorly suited to. This is the year
the ADR's "Lambda container image stays on the table" option comes off the
table and into production.

### Validation moves to a real fan-out compute layer

A daily run over a couple thousand feeds wants a queue, not a loop. The shape:
an EventBridge schedule drops one message per agency onto a queue (SQS); a pool
of containerized workers (Lambda with a JVM base image, or AWS Batch / Fargate
if any feed needs more memory than Lambda allows) pulls messages, runs the
validator, scores, and writes to S3. The work is embarrassingly parallel and
each unit is small, so this scales by raising concurrency, and it costs only
for the seconds of compute actually used.

The pipeline code does not meaningfully change. It is already a filesystem CLI;
the worker is a thin wrapper that pulls one agency, runs the existing
`scorecard run`, and pushes the result. Keeping the core runtime-agnostic was
the point of ADR 0001 and it pays off here.

### Realtime sampling gets its own service

Realtime quality is the category that does not fit a once-a-day batch. Scoring
trip coverage and vehicle-position plausibility needs samples across a window,
polled every 30 to 60 seconds during representative service hours. Year two
introduces a small, dedicated realtime sampler: a scheduled task that wakes for
defined windows (a morning peak, a midday, an evening peak), polls the realtime
endpoints of agencies that publish them, writes raw protobuf snapshots to S3,
and lets the daily scoring job consume those snapshots. This runs as a Fargate
task on a schedule rather than always-on, so cost tracks the sampling windows,
not the clock.

This is also where agency-specific realtime auth gets handled at scale (the
Unitrans case, where the feed exists but needs a key). A per-agency secret
store lets the sampler authenticate where it has been granted access, while
agencies without realtime keep showing "not yet published" neutrally.

### The artifacts become a dataset

By year two there is a longitudinal record: every feed, scored every day, for a
year or more. That is a genuinely useful research and policy dataset, and it
unlocks features the single-artifact view cannot. The move is to also write
each run as a row to columnar storage (Parquet in S3, queried with Athena, or a
small managed warehouse). Nothing in the public render path depends on it; it
sits beside the JSON artifacts and powers the analytical tools below.

What the dataset enables:

- **Benchmarking and percentiles.** "Your correctness score is in the top
  quartile for agencies your size." Framed as encouragement and context, never
  as a ranked leaderboard.
- **Vendor-level signal.** Aggregate scores by the scheduling tool that
  produced the feed (inferred from `feed_info` and export fingerprints). Which
  vendor exports tend to miss wheelchair fields, which produce stale calendars.
  This is the kind of finding a statewide support program would act on, and it
  is only visible at scale.
- **Regression detection across the whole corpus.** Catch the day a vendor
  software update quietly breaks fare data for forty of its customers at once.

### State and program rollup views

At a couple thousand agencies, the per-agency page is necessary but not
sufficient. The other core user, the district liaison or statewide program
staffer, wants a view across their portfolio: every agency they support, sorted
by what needs attention, with the same top-three-fixes framing rolled up. Year
two ships configurable rollup pages (a California view, a single district's
view, a custom list) generated as static artifacts like everything else.

### Year 2 infrastructure summary

```
EventBridge schedule
   |
   v
SQS (one message per agency)  ->  worker pool (Lambda JVM / Fargate Batch)
                                      fetch -> validate -> score
                                      |                       |
                                      v                       v
                              S3 raw snapshots          S3 JSON artifacts
                                      ^                       |
Realtime sampler (Fargate,           |                       +--> Parquet / Athena
 scheduled windows) ----------------+                       |       (benchmarking,
   polls RT, writes protobuf                                |        vendor signal)
                                                            v
                                              CloudFront -> static web app
                                              (per-agency + rollup pages)
```

Estimated cost at 2,500 agencies: low tens of dollars a month. Validation
compute is seconds times feeds and bills per millisecond. The realtime sampler
is the largest line item because it runs sustained polling windows, which is
why it is scoped to windows rather than continuous, and only for feeds that
publish realtime.

## Year 3 — from a country to a platform (target: 2,500+, including global)

Year three is about durability and reach rather than raw scale: making the tool
something agencies and programs can build on and trust over the long term, and
opening it beyond a single curator.

### A public read API and embeddable badges

The artifacts are already public JSON, which is a de facto API. Year three
makes it intentional: a documented, versioned read API (API Gateway in front of
the same S3 data, or signed CloudFront URLs) so that other tools, dashboards,
and agency websites can pull a grade programmatically. The companion is an
embeddable grade badge, the way open-source projects embed a build-status
badge, so an agency can put "GTFS quality: B+, updated today" on its own
developer page. Every badge is a link back, which is how the tool spreads
without a marketing budget.

### Self-serve becomes self-governing

By year three the registry is too large for one curator to vouch for every
entry. The model shifts toward verified self-service: an agency proves control
of its feed domain (a token at a well-known URL, or DNS, the standard patterns)
and from then on manages its own entry, including supplying realtime auth keys
through a secure path rather than a pull request. Authentication for this lives
in a managed identity service (Cognito or equivalent) and touches only the
write path; the public read path stays static and anonymous.

### White-label for statewide programs

The most committed users are statewide and regional programs that want this
view for their own agencies under their own banner. Year three supports
white-label deployments: the same pipeline and rubric, a program's branding and
agency list, optionally their own object storage and domain. Because the whole
system is static artifacts plus a stateless pipeline, a white-label instance is
a configuration and a deploy, not a fork.

### Internationalization and the global catalogue

GTFS is a global standard and the Mobility Database is a global catalogue. The
scoring logic is already feed-agnostic. Year three handles the rest: rubric
elements that are region-specific (the California guidelines citations) become
pluggable so other jurisdictions can map the rubric to their own guidance, and
the UI copy is structured for translation. This is gated on demand, not built
speculatively.

### Year 3 additions summary

```
Read API (API Gateway / signed URLs)  ->  third-party tools, agency sites
Embeddable badge  ->  agency dev pages  ->  inbound links
Verified claim (domain/DNS proof + Cognito)  ->  agency self-manages entry
White-label config  ->  per-program branded static deploys
Pluggable region rubric + i18n copy  ->  beyond California / US
```

## The tools, gathered in one place

Pulling the user-facing pieces out of the timeline, this is the full tool
surface the plan builds toward, roughly in priority order:

1. **The scorecard page** (exists): grade, four categories, top three fixes,
   trend, findings table.
2. **Self-serve onboarding**: web form to claim or submit a feed (Year 1),
   verified self-management (Year 3).
3. **Expiration and regression alerts**: opt-in email digest, the core
   retention loop (Year 1).
4. **Program rollup dashboards**: portfolio views for liaisons and statewide
   staff (Year 2).
5. **Benchmarking and vendor signal**: percentile context and
   export-tool-level findings from the corpus (Year 2).
6. **Public read API and embeddable badge**: programmatic access and organic
   distribution (Year 3).
7. **White-label deployments**: branded instances for statewide programs
   (Year 3).
8. **A notice-to-fix knowledge base** (cross-cutting): every validator notice
   the rubric surfaces links to a short, plain-language how-to for fixing it in
   common vendor tools. This is the most durable value-add and it grows with
   every agency conversation. Worth starting in Year 1 and never finishing.

## Governance, sustainability, and the things that can go wrong

Scale introduces problems that two pilot feeds never had. Naming them is part
of the plan.

- **Rubric fairness and gaming.** A published grade creates an incentive to
  optimize the grade rather than the rider experience. The defenses are an open,
  versioned rubric (the `docs/rubric.md` plus ADRs already in place), a public
  changelog when weights change, and resisting any metric that is easy to game
  and weakly tied to actual rider outcomes. Grade methodology changes are
  announced before they take effect so no agency is surprised by a drop it did
  not cause.
- **License and consent.** Feeds carry varying license terms, some unstated.
  Cataloguing a public feed's quality is low-risk, but at scale the registry
  should record each feed's license explicitly (the `license_note` field
  already does this), honor takedown requests, and give agencies a clear way to
  ask not to be listed.
- **Feed churn.** URLs move, agencies switch vendors, feeds break. The pipeline
  needs to degrade gracefully: a feed that fails to fetch shows "could not
  reach this feed" with its last-known grade and date, not a crash and not a
  zero. Mobility Database sync helps catch URL moves automatically.
- **Polling at scale.** Two thousand daily fetches and realtime sampling across
  hundreds of endpoints must not read as abuse. We stagger fetches, honor cache
  headers, prefer archived snapshots where they exist, and stay within the
  etiquette the guardrails set. Coordinating with MobilityData on archive
  access is preferable to independently polling everything.
- **Sustainability.** The cost guardrail keeps the infrastructure affordable,
  but someone still maintains it. The plausible paths are grant or program
  funding tied to statewide data quality goals, sponsorship by the programs that
  get the most value from the rollup views, or hosting under an existing transit
  data nonprofit. The architecture deliberately stays cheap and boring so that
  none of these require a large budget to keep the lights on.
- **Scope discipline.** The temptation at every stage is to start
  re-validating GTFS, or to build a general transit data platform. The tool
  stays a scoring, trending, and plain-language layer on top of the canonical
  validator. Every proposed feature is checked against whether it serves the
  transit manager who inherited a feed and the staffer helping them.

## What to do first

The first concrete steps, in order, that move toward Year 1 without waiting on
any of the larger architecture:

1. Write the Mobility Database sync command and use it to draft a California
   small-and-rural cohort into `agencies.yaml` for review.
2. Move published artifacts from git to S3 behind CloudFront, keeping the JSON
   contract identical, and point the existing site at the new URLs.
3. Shard the GitHub Actions run into a parallel matrix so the cohort scores
   within the existing cron window.
4. Ship the opt-in expiration alert digest against the artifacts that already
   exist.
5. Stand up the self-serve submission form that opens a pull request.

Each of these is independently shippable, none of them breaks the demo, and
together they take the tool from two feeds to a region without changing what
makes it worth using.
