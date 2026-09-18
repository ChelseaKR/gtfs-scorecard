# 0025: Access-to-opportunity is a scoped pilot, not a national build

Status: accepted (2026-07)

## Context

A feature-expansion research pass proposed adding "access to opportunity" to the
scorecard: how many jobs, clinics, or other destinations a rider can reach within
a time budget (say 45 minutes), the field-standard way to turn a feed into a
rider outcome. The usual engines are Conveyal's R5 (via r5r) and OpenTripPlanner.

Investigation found the label covers two different things that are in very
different states here:

1. **Trip-plannability QA**: "do sampled origin-to-destination trips actually
   return an itinerary?" This is already built and wired: `otp.py`, the
   `scorecard otp` command, and the manual `otp-qa.yml` workflow sample stop
   pairs, query an OpenTripPlanner instance, and fail when a sampled trip returns
   no itinerary. Per ADR 0014 it is deliberately gated: OTP is a heavy Java
   service, so the graph build is the operator's to provide, and the always-on
   default is `routability.py`'s serverless structural checks. Nothing new is
   needed here.

2. **Access-to-opportunity**: the cumulative-opportunities metric (jobs reached
   in N minutes). This is not built, and it is the expensive one. It needs a
   routable network per area (GTFS plus OpenStreetMap), a destination layer
   (Census LODES jobs), and travel-time-matrix / isochrone compute.

The project runs serverless on precomputed artifacts at single-digit dollars a
month. That constraint is what shapes this decision.

## Decision

Do not build a national, per-feed access-to-opportunity metric. Building a
routable network is minutes of compute and gigabytes of memory per feed; across
roughly two thousand feeds that is hours of compute and a memory footprint far
outside the serverless model, and R5 has no stable API and no support for
third-party deployment.

If access-to-opportunity is pursued, ship it as a bounded, offline **pilot
demonstrator**, not a national feature:

- Pick a few agencies (the two home systems plus one metro).
- Offline, build the network from an OpenStreetMap extract plus the feed, join
  Census LODES jobs, and compute access-to-jobs at one time budget with r5r/R5.
- Publish a small static artifact and a demo panel, clearly labeled a
  demonstrator over a handful of agencies, not a scored metric.

Otherwise defer it until the project takes on a backend (a warehouse or a routing
service), where per-area compute has somewhere to live. Trip-plannability QA
stays exactly as ADR 0014 left it: gated OTP on demand, serverless structural
checks always on.

## Consequences

- No new heavy infrastructure is added to the daily run; the serverless model
  holds.
- The scorecard keeps the cheaper "can a rider use this" signal (routability, and
  optional gated OTP QA) without the cost of full accessibility analysis.
- Access-to-opportunity, if built as the pilot, pairs with the tract-level equity
  work: an area can show both weak data and low reachable opportunity, which is
  the stronger equity story. It also carries a new toolchain (R via r5r) and the
  R5 caveats above, so it stays a demonstrator until the value is proven.

## Alternatives considered

- **National per-feed R5/OTP in CI.** Rejected: minutes plus gigabytes per feed
  across the whole corpus is hours of compute and a memory budget the CI-cron,
  single-digit-dollar model cannot absorb.
- **A persistent routing service.** Rejected for now: real, always-on cost and
  operational surface, the opposite of the current constraint. Revisit only with
  a deliberate move to a backend.

## Pilot scope, if built

Smallest viable version, as its own PR: an offline `access-pilot` script for
about three agencies that fetches an OpenStreetMap extract and Census LODES jobs,
runs an R5 travel-time matrix to compute access-to-jobs within one time budget,
and writes a static artifact plus a small panel. It is a demonstrator over named
agencies, not a national metric, and it does not run in the daily pass.
