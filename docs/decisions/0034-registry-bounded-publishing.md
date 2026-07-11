# 34. The registry bounds what is published

Date: 2026-07-11. Status: accepted.

## Context

On 2026-07-10 the public directory count jumped from ~1,450 to 2,012 without a
registry change. The extra 563 listings were artifact directories in the S3
store left behind by a pre-release bulk import (scored 2026-06-27/30, never
committed to `agencies.yaml`). The store is deliberately additive — the daily
sync never deletes, so history survives registry churn — but the S3
source-of-truth cutover (PRs #58–#60) made the collect and refresh jobs rebuild
`index.json` from whatever directories the sync brought down. Every leftover
directory came back as a live listing, and the hourly freshness sweep kept
re-stamping them so they read as actively scored. Checking the 563 against the
registry showed all of them duplicated an already-listed feed URL; none were
new agencies.

A related audit of the registry itself found ~320 committed entries whose feed
URL duplicated another entry's modulo the URL scheme (an http/https double from
the same catalog import), 23 entries whose URL was a test file or a broken
duplicate of a tracked feed, and 74 entries displaying a Mobility Database
dataset label ("Flex", "Bus", "fixed route") instead of the agency's name.

## Decision

`agencies.yaml` is the sole source of what the scorecard lists
(docs/listing-policy.md already says so for people; this makes the pipeline
obey it). Everything that walks the artifact tree as a set of listings —
reindex, the freshness sweep, rollups, the vendor report, the regression
radar, the national map — filters to registered ids via
`publish.registered_agency_dirs()`, and reindex warns when it skips
directories so drift stays visible. With no registry loaded (library callers,
unit tests) the walkers behave as before.

Unregistered directories in S3 are quarantined under `quarantine/<date>-.../`
rather than deleted, keeping the durable-history promise while removing them
from the sync the jobs hydrate from. Deletion remains a curator decision
(`scorecard prune`).

The duplicate registry entries were removed in the same change, keeping the
established id in each pair and merging its twin's `mdb_id` pin, so feed
discovery still follows the catalog by id.

## Consequences

- The public count reflects curated listings again (~1,140), and a stray S3
  directory can never re-enter the index, the map, or a rollup.
- Removing an agency from the registry now delists it on the next rebuild,
  which is what the listing policy promises removal requesters.
- Dated history for quarantined ids stays in S3 but has no public page; if one
  of those agencies is ever re-added under the same id, its old history
  resurfaces from the store on the next hydrate.
