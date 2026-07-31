# 0015: Equity overlay at state level before tract-level joins

Status: accepted (2026-06)

## Context

A data gap matters most where riders have the fewest alternatives: low-income
areas, car-free households, and people with disabilities. The expansion plan
(docs/expansion.md, Phase C) proposes overlaying Census LODES and ACS data so the
program can prioritize data-quality help by need, not only by grade.

The precise version is a tract-level join: take each feed's stops, locate each in
a Census tract (point-in-polygon against tract shapes), and aggregate ACS
indicators over the served tracts. That is the right resolution, and it is also a
real geospatial pipeline: tract shapefiles, a spatial index, a point-in-polygon
pass over hundreds of thousands of stops, and a per-stop ACS join. It needs data
and compute the serverless pilot does not have.

## Decision

Ship the state-level overlay first. `equity.py` classifies each state's transit
need from three ACS indicators (poverty, zero-vehicle households, disability
share), joins that need tier to each agency by its state, and reports where
high-need states carry a high share of low-grade feeds. The classifier and the
join are pure and unit-tested; fetching ACS is a handful of public state-level
queries with no API key.

The need tiers prioritize outreach. They never change a grade.

## Why state level is a useful first cut

The overlay's job is triage: which states should a program look at first because
weak data there lands on riders with the fewest options. State-level ACS answers
that at the granularity a state DOT or Cal-ITP-style program already works in, and
it is wireable today from a few queries. It is coarse: a low-need state can
contain a high-need city, which state averages hide.

## Escalation trigger

Move to the tract-level join when the program needs within-state targeting (which
*communities*, not which states) or stop-level prioritization (which specific
data gaps fall on high-need tracts). That step adds the tract shapefiles, the
spatial join over stops (the geometry the national map already computes per feed
is the starting point), and a LODES journey-to-work overlay. The classifier in
this module is the same shape a tract-level producer feeds, so the consumer side
does not change.

## Update (tract geospatial core built)

The served-area refinement's geometry is built (`tract_equity.py`): a correct
point-in-polygon test (ray casting, holes handled), a bbox-prefiltered locate,
and a stop-weighted aggregation of tract ACS indicators into one served-area need
profile, reusing the same `EquityIndicators` and `need_tier`. The core is pure
and unit-tested. What remains for the live tract overlay is the data wiring:
loading Census TIGER tract polygons and tract ACS values, and running the join
over each feed's stops (a national spatial index is the scale optimization). The
state-level overlay stays the default cut until that data step runs.

## Consequences

- An equity lens ships now, serverless, from public ACS.
- It is state-granular and so misses within-state variation; the report says so.
- Zero grade impact: the overlay reprioritizes help, it does not re-score feeds.
- ACS is fetched at run time; a fetch failure degrades to need tiers of "unknown"
  rather than failing the run, and the overlay still publishes the per-state
  agency counts and low-grade shares.

## Census API key (operational note)

The keyless Census API is rate-limited per IP and, from CI's shared runners,
frequently answers 200 with an empty body, leaving every state's tier "unknown".
The `equity.yml` workflow reads an optional `CENSUS_API_KEY` repo secret (a free
key from api.census.gov) and appends it to the queries; with it set, the overlay
populates real need tiers on every run. Without it, the counts-only overlay still
publishes, so the page and endpoint always work.

Last verified: 2026-07-17. `equity.py`, the `equity.yml` workflow, and its
optional `CENSUS_API_KEY` path are present and match this record. Since this
decision, `tract_equity.py` has landed the pure point-in-polygon and
aggregation core; the published overlay is still state-level, so the decision
stands. Recheck cadence: on each ACS release the overlay ingests, or when
tract-level data loading lands.
