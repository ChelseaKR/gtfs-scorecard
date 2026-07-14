# Expansion research: new use cases, personas, and the public/policy surface

A research pass into how the scorecard can widen its service: more for the three
personas it already serves, new personas it could serve, features for the general
public, and the research-and-policy uses of a national feed-quality dataset. It is
the companion to [`expansion.md`](expansion.md), which is the build-sequenced
feature plan; this document is the evidence and the persona reasoning behind the
next set of features.

Method: a fan-out web search across five angles (competitive landscape,
existing-persona use cases, new personas, research and policy, buildable
features), source extraction, and adversarial verification of each claim (a claim
needed to survive a three-vote refute pass to stay in). Twenty-four of twenty-five
verified claims were confirmed; one was killed and is recorded under "What did not
survive" so it is not repeated.

## The strategic finding

The ingestion layer the scorecard would otherwise have to build already exists at
national scale, and the unfilled gap is the interpretation layer the scorecard is
built to be.

- The Mobility Database catalogs over 6,000 GTFS, GTFS-RT, and GBFS feeds across
  99+ countries, fetches new datasets daily at midnight UTC, and integrates the
  Canonical GTFS Schedule and GBFS validators to publish a per-feed quality report.
  It is free and run by MobilityData (a nonprofit).
  [Mobility Database](https://mobilitydatabase.org/)
- Transitland aggregates thousands of GTFS and GTFS-RT feeds, validates and
  imports daily, and keeps an archive of tens of thousands of feed versions plus
  terabytes of realtime data. Its Atlas registry carries US NTD IDs and is openly
  hosted on GitHub under CC-BY 4.0.
  [Transitland APIs](https://www.interline.io/transitland/apis-for-developers/)
- The canonical validators emit technical INFO/WARNING/ERROR notices.
  MobilityData's own grading scheme notes that "a dataset flagged as valid by an
  automated validator may contain undetected qualitative errors that are
  unsuitable for rider-facing purposes," and fills that gap with manual,
  non-automated checks.
  [gtfs-grading-scheme](https://github.com/MobilityData/gtfs-grading-scheme)

So the daily, national, automated, plain-language grade is the differentiated
layer. Discovery, archival, and validation are upstream commodities the scorecard
reads rather than rebuilds, which is already the posture in
[`expansion.md`](expansion.md) and the ADRs.

## Existing personas: more to do

The producer-plus-consumer model the scorecard serves is the same model the
comparable tools serve, which is corroborating rather than novel: the web
validator was "jointly created ... for both transit data producers (such as
transit agencies) and consumers (such as journey-planning apps)," and the grading
scheme names data producers and data consumers as its two audiences. The new use
cases below sit on top of artifacts the pipeline already produces.

- **Transit manager — procurement and board reporting.** A vendor-accountability
  record already exists (`vendors.py`). Two new surfaces ride on it: RFP language an
  agency can paste into a vendor solicitation, and a board-meeting one-pager (the
  grade, the trend, the three fixes) generated from the dated artifacts.
- **Program liaison — call prep and cohort movement.** The rollups already carry
  worst-first ordering and common fixes; an agency-call worksheet and a
  month-over-month cohort movement view are renders on top.
- **Data team / researcher — machine-readable everything.** Transitland's v2 API
  outputs JSON, GeoJSON, CSV, vector tiles, and static maps, "ideal ... in web or
  mobile apps, maps, data visualizations, GIS analyses, and travel demand models,"
  which is the demand signal for programmatic access. The scorecard already
  publishes JSON and CSV (`dataset.py`); the missing format is GeoJSON.

## New personas worth serving

| Persona | Evidence | The hook |
|---|---|---|
| FTA / state-DOT policy staff | GTFS is a federal obligation: RY2023 requires a web-hosted feed for fixed-route NTD reporters; every RY2026 submission needs a stable `agency_id` per represented reporter and a P-50 crosswalk, though the value need not equal the NTD ID; shapes.txt phases in by reporter type; certified submissions are treated as definitive. FTA flagged unresolved feed-identity problems (agencies with multiple datasets or brandings, rural agencies sharing one regional feed). | A national, NTD-keyed readiness view that surfaces exactly the feed-identity and freshness gaps FTA documented in its own rulemaking. |
| Disability / accessibility advocates | Peer-reviewed work (Journal of Transport Geography, 2023) finds powered and manual wheelchair users reach 59% and 75% fewer accessible stops. The open `gtfs-accessibility-validator` checks the exact fields (wheelchair_boarding, wheelchair_accessible, pathways, levels, tts_stop_name) the California guidelines require. | A national accessibility-coverage index built from the completeness category the pipeline already computes. |
| App developers / trip-planner companies | Named demand for a "shared understanding of a dataset's quality before putting it into production." | Open machine-readable artifacts plus the live-grade badge already shipped. |
| Academic transit researchers | A long-run national archive (Transitland versions; the scorecard's own dated artifacts) supports quality-over-time study. Note: Transitland historic versions need a paid or free-academic plan. | A citable, versioned national dataset with a stable reference. |
| Journalists / civic tech | No comparable organization targets riders or the press directly. | A national "state of transit data" snapshot off existing aggregate stats. |

## Features for the general public

This is genuinely empty space: MobilityData, Cal-ITP, and Transitland serve
producers, consumers, and developers, not riders or advocates. The product
principle that small agencies are never shamed holds, so these are framed as
transparency, not a ranking to lose.

- A rider-readable "is my agency's feed healthy?" lookup, leading with the silent
  failure that drops an agency from trip planners: an expired feed.
- An accessibility-coverage map a rider or advocate can actually read.
- A national "state of transit data" page for civic tech and the press.

## Research and policy uses

- **Compliance-reform evidence.** A national daily dataset can quantify the
  feed-identity and freshness problems FTA named in the RY2025/RY2026 rulemaking,
  which is directly useful to the people writing the next rule.
- **State-mandate support.** Mapping the grade to specific California Transit Data
  Guidelines tiers gives an agency and its liaison a per-agency read against the
  state's own bar (already partly served by [`crosswalk.md`](crosswalk.md)).
- **Realtime quality is the open dataset.** The canonical validators cover Schedule
  and GBFS but not GTFS-Realtime. There is funded precedent (a TRB/CUTR Transit
  IDEA study validated 162 RT feed endpoints) but no living national RT-quality
  monitor. The scorecard's realtime category, run nationally with plain-language
  grading, would be net-new.

## What did not survive verification

- The claim that only about 35% of NTD reporters had GTFS before the rule (implying
  the mandate brings two-thirds of agencies into GTFS for the first time) did not
  survive the refute pass. Do not cite a specific size for the newly-mandated
  population.

## Caveats

- For RY2026, agency_id presence and the P-50 crosswalk are required, while
  equality to the five-digit NTD ID is not. Shapes.txt phases in by reporter
  type. Build to that current-policy distinction, not the older shorthand that
  called agency_id itself optional. Two FTA-related
  claims passed only 2-1 and rest on FTA's "can leverage / will enhance" intent
  language, not delivered capability.
- Several primary sources (federalregister.gov, mobilitydatabase.org,
  mobilitydata.org, interline.io) returned HTTP 403 through the research proxy;
  their wording was corroborated through search extraction and secondary mirrors
  rather than direct fetch. Operator scale figures (6,000+ feeds, terabytes) are
  self-reported.
- No claim independently verified the single-digit-dollars-a-month ceiling for any
  expanded feature; that stays a design constraint, not a finding.

## Open questions

1. The licensing and rate-limit terms for consuming Mobility Database feeds and
   Transitland historic versions at national scale, and whether they permit
   republishing derived grades.
2. Whether FTA's enhanced P-50 collection exposes raw GTFS bytes (not just URLs),
   which would let the scorecard ingest NTD-submitted feeds directly, crosswalked
   by NTD ID.
3. How many of the cataloged feeds publish GTFS-Realtime, i.e. the addressable size
   of a national realtime-quality dataset.
4. Which rider-facing and advocate features have validated demand versus assumed
   demand, given comparable tools target producers and developers, not riders.

## What this turned into

A first slice shipped from this research, each over data the pipeline already
produces (see [ADR 0017](decisions/0017-persona-surfaces.md)):

- `/ntd/` — a national NTD certification-readiness page for FTA and state-DOT
  staff, reading the published `ntd.json`.
- `/access/` plus `api/v1/accessibility.json` — a national accessibility-data
  coverage view for advocates, backed by the pure `access.py` module.
- `/procurement/` — a copy-paste contract/RFP clause for an agency manager.

Most other recommendations were already shipped (machine-readable JSON/CSV/Parquet,
the national map GeoJSON, the liaison/board one-page brief, the equity overlay,
vendor accountability), so they were not rebuilt.

The two bigger bets followed in a second slice (see
[ADR 0018](decisions/0018-national-rt-and-ntd-crosswalk.md)):

- `/realtime/` plus `api/v1/realtime.json` — a national realtime-reliability view
  rolled up from the uptime and lag samples the monitor already records, without
  standing up a continuous polling fleet.
- `scorecard ntd-crosswalk` — populates `ntd_id` across the registry from the
  Transitland Atlas (matched by feed URL), turning ADR 0016's ID-alignment check
  on past the two pilots. The one remaining bet left for later is *continuous*,
  high-cadence national realtime archiving, which is the feature that forces a
  backend.

## Sources

- Mobility Database. https://mobilitydatabase.org/
- Transitland / Interline, APIs for developers.
  https://www.interline.io/transitland/apis-for-developers/
- MobilityData, web GTFS Schedule Validator release.
  https://mobilitydata.org/new-web-based-version-of-gtfs-schedule-validator-released/
- MobilityData, gtfs-grading-scheme.
  https://github.com/MobilityData/gtfs-grading-scheme
- BlinkTag, gtfs-accessibility-validator.
  https://github.com/BlinkTagInc/gtfs-accessibility-validator
- FTA, NTD Reporting Changes and Clarifications (RY2023).
  https://www.federalregister.gov/documents/2023/03/03/2023-04379/national-transit-database-reporting-changes-and-clarifications
- FTA, NTD Reporting Changes for RY2025 and RY2026.
  https://www.federalregister.gov/documents/2025/07/10/2025-12813/national-transit-database-reporting-changes-and-clarifications-for-report-years-2025-and-2026
- Journal of Transport Geography (2023), transit access and mobility disability.
  https://www.sciencedirect.com/science/article/abs/pii/S0966692323000613
