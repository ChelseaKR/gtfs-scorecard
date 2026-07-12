# 0035: Worldwide defaults, regional modules

Date: 2026-07-12. Status: accepted.

## Context

The first international pass added portable country and subdivision fields but
left the product framed as a U.S. service with exceptions. The primary
navigation said “National,” maps opened over the United States, worldwide
locations were described as “not on this U.S. map,” submission and MCP inputs
were state-first, and U.S. NTD ridership influenced corpus ranking order. That
was technically extensible, but it was not a genuinely global product.

The scorecard must also avoid the opposite error: a global-shaped interface is
not proof of global coverage. The registry is curated and currently remains
geographically uneven. Missing places are not poor performers.

## Decision

The default product is worldwide and coverage-bounded.

1. The runtime ships the full assigned ISO 3166-1 and ISO 3166-2 vocabulary.
   This vocabulary validates location; it does not activate or imply coverage.
   `agencies.yaml` remains the sole source of published coverage.
2. Country is the primary discovery scope. Subdivision is optional and nested
   below its country. Maps begin with responsive world bounds; a U.S. state
   choropleth appears only after the United States is selected.
3. Correctness, freshness, rider-experience completeness, and optional realtime
   quality form one disclosed GTFS scoring profile. The canonical validator runs
   with the feed's country code. A regional guideline may explain the result but
   does not silently change the worldwide core.
4. U.S. NTD readiness, U.S. ridership, by-state compatibility endpoints, and
   domestic equity data remain supported regional modules. They are labelled
   “United States” and never order or define worldwide corpus views.
5. API, MCP, submission, aggregate, map, and directory contracts use additive
   `country`, `subdivision_code`, and `subdivision_name` fields. Existing
   `state`, `by-state.json`, `national_stats`, and percentile fields remain as
   compatibility interfaces; new consumers use the portable fields.
6. The agency/practitioner experience remains the full operational surface.
   Rider access is an additional plain-language lens over the same evidence,
   especially service freshness, accessibility fields, fares, realtime, and
   disruptions. It does not remove findings, remediation detail, or program
   workflows.
7. The first production canaries are official open feeds in Japan, Australia,
   and Ireland. A new country requires verified endpoint, reuse terms, cadence,
   location behavior, non-U.S. policy gating, accessible rendering, and several
   successful scoring runs. Community or informal feeds covered by ADR 0028
   additionally require a local steward and consent.

## Compatibility and migration

- Historical registry entries without `country` continue to resolve to `US`.
- Historical `?state=` directory links continue to resolve to U.S.
  subdivisions and are rewritten only after user interaction.
- `/pulse/`, `/map/`, and `/routes/` keep their URLs while their labels and
  default framing become coverage-oriented.
- Regional modules keep stable URLs so existing U.S. users lose no capability.
- Country-only feeds are valid. Subdivision code and name are optional, but if
  either is supplied the pair must be valid and belong to the country.

## Consequences

Adding a country no longer requires an allowlist or frontend branch. Global
coverage claims must still name the actual denominator. A single universal
equity score is explicitly out of scope because local deprivation sources are
not comparable; country-specific overlays can be added as regional modules.
Localization remains a reviewed content task rather than an automatic claim
derived from Unicode support.

Related: ADR 0026 (internationalization), ADR 0028 (Global South pilot), ADR
0034 (registry-bounded publishing).
