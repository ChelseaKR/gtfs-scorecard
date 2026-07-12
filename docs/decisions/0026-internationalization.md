# 0026: Internationalize by layer, GTFS-first, starting with Canada

Status: accepted (2026-07)

## Context

The scorecard is US-only today: ~2,000 agencies discovered via the Mobility
Database and Transitland, scored on the MobilityData canonical GTFS validator
against a rubric aligned to the Caltrans / California Transit Data Guidelines,
with a US Census ACS equity overlay and an FTA National Transit Database (NTD)
certification-readiness view. A research pass looked at going global. Its
findings, in short:

- **Discovery is already global.** The Mobility Database (6,000+ feeds across
  99+ countries, distributed as auth-free CSV/JSON) and Transitland are the two
  catalogs the scorecard already uses. Extending discovery internationally is a
  country-code filter, and `scorecard sync --country <cc>` already accepts one.
- **The validator is already the international standard.** The MobilityData
  canonical validator the scorecard scores on is used inside EU National Access
  Points and by national governments, so the scoring core is credible worldwide.
- **Canada is turnkey and proven.** Statistics Canada built a 139-feed national
  transit database using the same two catalogs plus the same validator.
- **Europe is the hard layer.** Binding EU law (MMTIS Delegated Regulation
  2017/1926, amended 2024/490) mandates NeTEx/Transmodel to National Access
  Points, so GTFS is often not the authoritative EU artifact; NeTEx-to-GTFS
  conversion exists (Entur, Chouette) but is Java-heavy and fragmented by
  per-country national profiles, a poor fit for the serverless model.
- **The rubric has clean EU analogues.** NAPCORE's MMTIS Quality Framework
  (v1.0, April 2025) uses four dimensions (correctness, completeness, timeliness,
  reliability and usability) that mirror the rubric, and NAP obligations replace
  NTD-readiness. As of that framework, no adopted, graded, plain-language,
  small-agency-facing quality scorecard exists in Europe: the clearest gap.

Two gaps stayed under-researched and are being investigated separately: non-US
equity/demographic context data (no confirmed ACS equivalent), and the Global
South GTFS landscape (where GTFS is most the lingua franca).

## Decision

Internationalize by layer, cheapest first, not all at once.

1. **Tier 1, GTFS-first countries (near-turnkey).** Canada first (Statistics
   Canada proves the exact stack), then the other GTFS-publishing anglophone
   countries (UK, Australia, New Zealand, Ireland). Discovery is a country filter
   on catalogs already in use; scoring is unchanged.
2. **Tier 2, rubric localization.** Make the US-only surfaces conditional so they
   do not misfire abroad: NTD-readiness and NTD-id alignment gate on the US, and
   the ACS equity overlay stays US-scoped until a cross-country equity source is
   chosen (see the separate context-data research and ADR 0015).
3. **Tier 3, the forks (heavy, later).** Either Europe via NeTEx (strategically
   the open market gap, operationally the heaviest: per-profile NeTEx-to-GTFS
   normalization likely needs a gated non-serverless step), or the Global South,
   where GTFS is most native and a small-agency scorecard may have the highest
   marginal impact. Decide with the follow-up research.

The differentiation is the same abroad as at home: open, graded, plain-language,
small-agency-facing, and it is unfilled in Europe. MobilityData, whose catalog
and validator are the global backbone, is the natural partner.

## The Canada pilot (Tier 1, first concrete PR)

Smallest viable pilot, buildable as one PR:

- **Discover:** `scorecard sync --country CA` already filters the Mobility
  Database by `location.country_code`; add a handful of Canadian feeds to
  `agencies.yaml`. The catalog `mdb_id` follows moved URLs.
- **Make the model country-aware:** add a `country` field to the agency registry
  and the `Agency` model, defaulting to `US` so every current entry is unchanged,
  and carry it into the published artifact's `agency` block.
- **Gate the US-only per-agency surfaces on `country == "US"`:** NTD-readiness
  and NTD-id alignment (both keyed to the FTA five-digit NTD ID) render only for
  US agencies; a Canadian feed shows the GTFS-quality core (correctness,
  freshness, completeness, realtime) without a hollow NTD box.
- **Subdivision:** the US-state subdivision mapping returns empty for a Canadian
  province, so a pilot agency lands in the existing "Unlocated" bucket. Extending
  province handling is a later refinement, not a blocker.
- **National rollups:** the ACS-equity, adoption, and accessibility national
  rollups stay US-framed for now; non-US agencies are simply outside them until
  Tier 2 localizes the context data.
- **Verify:** the rubric core is GTFS-generic and needs no change; only the
  US-institutional surfaces are hidden. The country field and the gating are
  unit-testable; a live Canadian feed is scored in CI, like any feed.

Files this touches: the config/registry loader and `Agency` model (add
`country`), `publish.py` (artifact `agency` block), `cli.py` `run_agency` (gate
the NTD calls), `render_site.py` (hide the US-only sections for non-US agencies),
and tests.

## Consequences

- Tier 1 is a small, mostly additive change on infrastructure already in place;
  the serverless model holds and current US behavior is unchanged (country
  defaults to US).
- The scorecard can credibly claim international coverage on the two layers that
  matter most (discovery, validation) long before it solves Europe.
- Europe (NeTEx) and a true cross-country equity overlay remain open, and each is
  its own decision; this ADR does not commit to either.

## Implementation update (2026-07-12)

The no-build frontend now routes dates, counts, and agency-name collation through
`web/src/locale.js`, using the page's BCP 47 `lang` value and the browser's
`Intl` implementation. The same module sets the root writing direction, with a
browser contract covering a right-to-left locale. English remains the declared
default; this removes the earlier `en-US` formatting assumption without claiming
that the full practitioner interface has been translated.

## Open questions

- What cross-country demographic/equity dataset (Eurostat grids, the EU GHSL,
  WorldPop, OSM-derived access) could power a non-US equity overlay, and is it
  harmonized enough to be comparable across borders? (Answered; see the update
  below.)
- Can per-profile NeTEx-to-GTFS normalization run inside the GitHub Actions cron,
  or does it force a heavier step and break the cost model?
- How should the plain-language framing, effort hints, and letter-grade tone be
  localized across languages without losing the respectful, fix-oriented voice?

## Update (2026-07): international equity-context data

A follow-up research pass answered the equity open question. No single dataset
matches the US Census ACS mix of within-country consistency and
poverty/vehicle/disability detail across borders. The usable options fall in
three groups:

- Harmonized geometry, demographics only: the EU 2021 Census 1 km grid
  (comparable across 30 countries) and global gridded population (the EU GHS-POP
  and WorldPop surfaces) carry population, not deprivation.
- Deprivation, but country by country: Canada's Index of Multiple Deprivation
  (CIMD) is an open, pre-computed small-area index and the closest turnkey ACS
  analogue; the European Deprivation Index and national deprivation indices exist
  per country and are not mutually harmonized.
- Global lower/middle-income wealth proxy: Meta's Relative Wealth Index covers
  90-plus countries but is within-country only and licensed CC BY-NC, a
  NonCommercial constraint to settle before any client-facing or commercial use.

So an international equity overlay should present need relative to each country's
own distribution (within-country quintiles), not one global scale, and attach
richer deprivation only where a national index exists. Practical consequence for
this plan: the Canada pilot can ship a real equity overlay cheaply, because CIMD
is open and small-area; most other countries would start from population-only
geometry. The Global South GTFS landscape stayed unanswered in that pass and is
being researched separately.

## Related

ADR 0015 (equity, state-level first), 0016 (NTD id alignment), 0025
(access-to-opportunity scope). All three are US-anchored surfaces this decision
makes conditional abroad.
