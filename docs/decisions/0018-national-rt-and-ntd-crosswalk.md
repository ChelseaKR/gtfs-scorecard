# 0018: National realtime rollup, and NTD-ID population from the Atlas

Status: accepted (2026-06)

## Context

Two items were deferred from the expansion research
([docs/expansion-research.md](../expansion-research.md)) as the bigger bets:
a national realtime-quality view, and turning the NTD-ID alignment check
(ADR 0016) on past the two pilot agencies. This records how both were done while
staying inside the serverless, single-digit-dollars model.

## Decision 1: national realtime reliability as a rollup, not a fleet

The realtime monitor already records per-agency uptime and header-lag samples in
`data/rt-health` (ADR 0012), and each agency page shows that agency's reliability.
The research noted that *continuous, high-cadence* national realtime monitoring is
the one feature that forces a worker fleet. We did not build that. Instead we roll
the samples the cron already records up into a national view:

- `rt_national.national_rt` (pure) summarizes the per-agency `RtHealth` records
  into a reliability-band distribution, national median uptime and lag, a
  per-state breakdown, and the most reliable feeds.
- `render_site` writes `api/v1/realtime.json` and a `/realtime/` page from it.

This adds no polling and no backend: it reads the existing `data/rt-health`
artifacts at render time. Agencies that publish no realtime feed are not counted,
never shown as a zero, consistent with the principle that a missing realtime feed
is neutral.

## Decision 2: populate NTD IDs from the Transitland Atlas, by feed URL

ADR 0016 could only compare optional equality where we knew the agency's NTD ID,
and we curated that for two pilots. Required agency_id presence can be checked
without this registry value. The Transitland Atlas (CC-BY) records `us_ntd_id` on
its US operators and links each operator to its feeds, giving an open join from a
feed to its five-digit NTD ID.

- `ntd_crosswalk` (pure matching + an Atlas fetcher) maps each Atlas feed's
  `static_current` URL to its operator's NTD ID, then matches our registry's
  `static_gtfs_url`. The join key is the normalized feed URL.
- A URL the Atlas links to more than one NTD ID (a shared regional feed) is
  **dropped, not guessed**, so we never stamp one agency with the NTD ID of a feed
  it shares. We populate an `ntd_id` only on an unambiguous, exact URL match.
- `scorecard ntd-crosswalk [--apply]` runs it. `--apply` inserts one `ntd_id` line
  per matched agency into its registry shard as a text edit (not a YAML round-trip),
  so the 345 KB hand-maintained file keeps its formatting and the diff is one
  added line per agency. Curated values are never overwritten.

## Why URL matching, and why conservative

The registry stores each agency's feed URL but not a Transitland Onestop ID, so
the feed URL is the join we have. Matching exactly (after normalizing scheme,
host case, and trailing slash) is precise; a fuzzy name match would risk assigning
a wrong NTD ID, which is worse than none, because the alignment check would then
report a confident but false mismatch. Dropping ambiguous regional feeds and
exact-matching only keeps the populated IDs trustworthy. Agencies we cannot match
stay `unknown` on the optional equality comparison; their presence check still
runs.

## Consequences

- Both `rt_national` and `ntd_crosswalk`'s matching logic are pure and unit
  tested without the network; only `fetch_atlas` reaches out, and it is injectable
  for tests.
- Turning more NTD IDs on lights up the optional equality flag (ADR 0016) for
  every matched agency, with zero grade impact. Presence remains part of the
  separate NTD-readiness status.
- Re-running `ntd-crosswalk` is safe and idempotent: agencies that already have an
  `ntd_id` are skipped, so it only ever adds.
- The `/realtime/` page and `/ntd/` page now give a program the two national views
  the research asked for, both off data already on disk.
