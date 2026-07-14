# 0010 — Two-tier update cadence

Status: accepted
Date: 2026-06-20

## Context

A feed's quality is only as current as the last time it was scored. The full
score downloads each feed and runs the MobilityData Java validator, which is the
expensive step and the reason scoring runs once a day (ADR 0001, ADR 0003).

That daily cadence has two weaknesses. First, a feed can change or break right
after a run and the scorecard will not reflect it for almost a day. Second, when
the heavy run is delayed or skipped, the published data goes stale with it. Both
showed up in practice: Yolobus published a stale export that expired its calendar
to February, sat undetected through a two-day gap in the daily run, then
corrected itself before anyone could act. The classic small-agency failure the
project exists to catch is exactly this kind of silent expiry or breakage.

Running the full validator more often does not fit. It would breach the polling
etiquette in `docs/feeds.md` (download static GTFS at most once a day per feed)
and the single-digit-dollar monthly budget, and it scales with the registry,
which keeps growing.

## Decision

Split the work into a cheap tier and an expensive tier, and run the cheap tier
more often.

1. **Daily full score (unchanged).** The `Daily scorecard` workflow keeps
   re-validating every feed once a day. It remains the source of truth and the
   correctness floor.

2. **Intraday refresh (new, every 6 hours).** The `Intraday refresh` workflow
   does only cheap work and never runs the validator across the whole registry:
   - **`scorecard liveness`** issues a conditional GET per feed. A 304 means
     unchanged with no body transferred; a 200 is hashed against the last seen
     body to confirm a real change; a 403/404/timeout is an availability problem.
     State persists in `data/liveness.json`.
   - **`scorecard freshness-sweep`** recomputes every feed's expiry and grade
     from the calendar dates already stored in its last artifact. No fetch, no
     validator. It skips any feed already scored that day, so it never restamps a
     full score, and it only acts when a feed's published data has gone stale.
   - The validator runs only on the handful of feeds `liveness` reports as
     changed or recovered, fed in by id. Cost stays flat as the registry grows
     because the expensive step is gated on actual change.

3. **Honest partial artifacts.** A freshness sweep writes a dated artifact marked
   `recompute: freshness` that carries the last fetch's correctness, completeness,
   and realtime forward and refreshes only freshness, recording the date the feed
   was actually fetched. A past snapshot's freshness is never rewritten, so trend
   history stays accurate.

## Consequences

- Detection latency for an expiry or outage drops from up to a day to a few
  hours, without re-validating feeds that did not change.
- The sweep is a resilience layer: if a daily run is delayed, the expiry clock
  still advances on its own.
- The two workflows both commit generated artifacts to `main`; each rebases onto
  the latest `main` and retries, so a race between them resolves without losing a
  cycle.
- `liveness` and `freshness-sweep` are report-only by default; the workflow opts
  into `--apply`. The live conditional GET runs only where outbound access is
  allowed, so the change classification is unit-tested with an injected opener.

## Cadence tiers (follow-up)

The intraday refresh now runs hourly, and `scorecard cadence` decides which feeds
are checked each hour so the tightest cadence goes to the feeds that need it:

- **Priority (every cycle):** realtime publishers, and feeds in the expiry danger
  or recovery window (expiring soon, or recently lapsed).
- **Standard (once per six-hour period):** everything else, with each feed
  assigned a stable bucket from its id so the long tail spreads evenly across
  cycles instead of every host being hit at once.

This keeps detection latency tight for at-risk feeds without checking all ~1,100
hosts every hour. `liveness --only` consumes the due list; the full validator
still runs only on the feeds that actually changed.

## Validator-result cache (follow-up)

The daily run still re-validates every feed, but most feeds are byte-identical to
the day before, so most of those Java runs are redundant. Each score now caches
its normalized validator report locally at `data/cache/validator/<id>.json`,
keyed by the feed's sha256, validator version, and assigned country. This path
is ignored by git and sits outside the public `data/artifacts` tree. Production
runs also use the private S3 prefix `cache/validator/<id>.json` as the durable
tier. A re-score whose bytes, validator version, and country all match reuses
the cached report and skips the validator; changed bytes, an upgraded validator,
or a country correction re-runs and refreshes the cache. Historical cache
records without a country are treated as U.S. records only. Reusable raw reports
use the same country boundary: the legacy `validator/` path remains U.S.-only,
while a non-U.S. run writes to a suffixed path such as `validator-ca/`.

Earlier releases wrote `validator-cache.json` inside each agency's public
artifact directory. Those files are removed from the repository, excluded from
all S3 and Pages publication paths, and deleted from the artifact bucket during
publication. The CloudFront viewer function and origin bucket policy also deny
the legacy key shape while deployed copies are retired.

The agency page also shows a monitoring line ("checked for changes N hours ago;
last changed ...") from the liveness state, so a reader can see how current the
change detection is.

## Not yet

Active service-window realtime sampling (timing a capture to when buses are
running) is deferred. The realtime scorer already renormalizes away components it
cannot measure when no service is scheduled, so an off-hours sample is not scored
as a failure; the remaining gain is timing captures to maximize a real coverage
read, which is a scheduling refinement rather than a scoring change.
