# ADR 0040: The beta gate stays Europe-scoped until a consumer needs a region

**Status:** Accepted (2026-07-18)

## Context

The European GTFS beta gate in `global-expansion.md` is executable, not prose.
`build_global_coverage` in `pipeline/src/scorecard_pipeline/global_coverage.py`
evaluates it against the published directory and feature documents and writes
`/api/v1/global-coverage.json`. Its thresholds are module-level constants:
`MIN_REVIEWED_FEED_RECORDS = 250`, `MIN_COUNTRIES = 12`,
`MAX_LARGEST_COUNTRY_SHARE_PCT = 40.0`, `MIN_FRESH_SCORECARD_PCT = 95.0`, and a
closed `EUROPE_BETA_COUNTRY_CODES` set of the EU27 plus five named neighbouring
markets. Each of those numbers was chosen for the European market. The 250-record
floor sits below the roughly 406 license-linked discovery rows so review can
still reject candidates, and above a canary cohort so a consumer can make a
bounded decision. The 12-country breadth and the 40% single-country ceiling
describe a continent with dozens of addressable national programs.

The gate exists because a named consumer asked for it. A consumer-side
participant in MobilityData Slack tried the feature finder and named European
coverage as a use blocker. The gate is the auditable answer to that request.

Other regions now have reviewed coverage but no beta label. Oceania official
feeds (Phase 1), Latin America first-party feeds (Phase 2), and Asia-Pacific and
Middle East official feeds (Phase 3) are curated as ordinary reviewed records
under the same scoring core, the same license review, and the same identity
review. They are not gated, and no consumer has yet asked for a beta in any of
them.

The coverage roadmap flags the open question. Should the Europe gate generalize
into a parameterized regional contract (region, country set, thresholds,
denominators) evaluated by the same executable evidence, or should other regions
stay ordinary reviewed coverage with no beta label until a consumer asks? The
roadmap already leans toward the latter.

## Decision

Keep the gate Europe-scoped. Do not parameterize it now.

- `global_coverage.py` stays Europe-coded. The country set and the thresholds
  are the European product's, not a template.
- Oceania, Latin America, Asia, the Middle East, and Africa remain ordinary
  reviewed coverage. They are curated, excluded, or partnership-gated by the
  phase rules in the coverage roadmap, and each activated region discloses its
  own coverage denominator beside the finder and exports.
- No region gets a beta label until both of these hold: a named consumer asks
  for that specific region's beta, and that region's cohort meets a stated,
  executable, region-appropriate gate written for it.

The reason to refuse premature generalization is that the current thresholds are
not neutral defaults. "250 records" and "40% single-country share" encode
assumptions about how many defensible feeds a market publishes and how those
feeds spread across countries. Oceania's whole addressable open official set is
roughly 38 feeds, almost all in Australia and New Zealand. A 250-record floor is
unreachable there, and a 40% two-country ceiling is meaningless. Reusing Europe's
numbers for Oceania would not measure Oceania readiness. It would produce an
arbitrary result dressed as a gate.

A gate with no consumer is worse than no gate. The roadmap's fixed principles say
coverage is not a success measure, and its closing list says the project will not
add a regional beta label before a named consumer needs it. A parameterized gate
built ahead of demand is coverage-as-vanity: machinery that computes readiness
for a beta nobody requested. The Europe gate earns its complexity because a
consumer named Europe. A second region earns its own gate the same way, or it
does not get one.

## The seam for a future regional gate

This decision is a deferral, not a rejection of the shape. When a second region
does need a beta, the parameterization should be a region config, not a fork of
the module.

A future `RegionGate` value would carry the parts that are region-specific today
as module-level constants:

- `region`: the label and identifier for the beta, for example "Bounded Oceania
  GTFS Schedule beta".
- `country_codes`: the closed, visible country set, the role
  `EUROPE_BETA_COUNTRY_CODES` plays now.
- `min_reviewed_feed_records`: the record floor, chosen against that region's
  addressable discovery count, never copied from Europe's 250.
- `min_countries` and `max_largest_country_share_pct`: breadth and balance, sized
  to the region's actual number of national programs. A two-country region needs
  different breadth arithmetic, or none.
- `min_fresh_scorecard_pct`: the freshness floor. This one may be genuinely
  shared, since freshness is a data-quality property rather than a market
  property.
- `denominator_source`: the region's disclosed coverage denominator, so the gate
  and the finder cite the same number.

`build_global_coverage` would take a `RegionGate` parameter instead of reading
the module-level European constants, and the current European values would become
the first `RegionGate` instance rather than being deleted. The per-record checks
(freshness, translation measurement, portable location, identity review) are
already region-neutral and carry over unchanged; only the cohort selector and the
threshold constants become parameters. This ADR does not implement that. It
records the seam so the change is a deliberate follow-up with its own ADR when a
consumer needs it, not a refactor invented under deadline.

## Consequences

- `global_coverage.py` stays Europe-scoped, with its constants and closed country
  set intact. Adding a reviewed feed in Oceania or Latin America does not touch
  the gate.
- The "never a census" principle is upheld by per-region coverage denominators,
  not by per-region gates. A region does not need a beta gate to be disclosed
  honestly. It needs its denominator stated beside every filter and export.
- Claiming a region's beta becomes a deliberate, consumer-driven decision with
  its own ADR: a named consumer, a region-appropriate executable gate, and the
  `RegionGate` seam above. It is not a side effect of registry growth.
- If no second consumer ever asks, the gate stays Europe-only, and that is the
  correct outcome rather than a gap to close.

## Related

ADR 0026 (internationalization; the European GTFS boundary), ADR 0028 (Global
South pilot; the partnership gate for uncurated regions), ADR 0034
(registry-bounded publishing), and ADR 0035 (worldwide defaults, regional
modules; coverage claims must name their denominator). The Europe gate itself is
specified in [`../global-expansion.md`](../global-expansion.md) and sequenced
among regions in [`../global-coverage-roadmap.md`](../global-coverage-roadmap.md).
