# 0021: Ridership-weighted impact, built and gated on data

Status: accepted (2026-06)

## Context

Agency counts understate impact: "63 feeds are expired" reads the same whether a
feed carries a thousand annual trips or a million. The strongest policy and press
number is rider-trips, and the NTD publishes annual unlinked passenger trips
(UPT) per reporter, keyed by the five-digit NTD ID that ADR 0016's crosswalk now
puts on matched feeds. The join is available in principle.

## Decision

Build the join and the weighting as a pure, tested module (`ridership.py`) plus a
`scorecard ntd-ridership` command, and gate it on data the repository does not yet
hold rather than ship a misleading page.

- `parse_ridership_csv` reads an NTD ridership file by header (not column
  position), summing UPT per NTD ID and normalizing zero-padded ids.
- `weighted_impact` weights the matched feeds' grades, scores, and expiry by
  ridership, and reports its own coverage (matched vs total agencies) so it never
  pretends to be more national than it is.
- The command reads `data/ntd-ridership.csv` when present and prints the weighted
  impact; when absent it logs how to activate the feature and exits cleanly.

## Why gated, not shipped as a page

Two facts make a "national" ridership-weighted page dishonest today, and a page is
the wrong thing to ship on dishonest data:

- The NTD ridership endpoints (`transit.dot.gov`, `data.transportation.gov`) are
  unreachable from the build environment, so no ridership snapshot is committed
  yet. Nothing in this module fabricates ridership; absent data yields an empty,
  labeled result.
- Only a minority of feeds carry an NTD ID so far (the crosswalk matches by exact
  feed URL and is deliberately conservative), so even with ridership in hand the
  weighting would cover a fraction of the corpus.

This mirrors the repository's existing pattern of building a capability and gating
it on data (the OpenTripPlanner checks in `otp.py`, the tract-level equity
refinement in `tract_equity.py`).

## How to activate it

1. Commit a public NTD annual ridership snapshot to `data/ntd-ridership.csv` (any
   layout with an NTD-ID column and a UPT or ridership column).
2. Broaden NTD-ID coverage so the weighting is national: extend
   `ntd_crosswalk` with a precise name-plus-state fallback for feeds whose URL did
   not match the Atlas exactly, keeping the conservative "drop on ambiguity" rule.
3. Run `scorecard ntd-ridership`; once coverage is meaningful, surface the result
   as an `/impact/` page and an `api/v1/impact.json`, the same way the other
   national rollups publish (ADRs 0017–0020).

## Consequences

- The math is correct and unit tested now, so activation is a data step, not a
  code step.
- No grade impact, and no page that could mislead until the data supports one.
