# Expansion ideation, July 2026: where the app could go next

A horizon-scan of directions for overhauling and expanding the scorecard, from
both the user's side and the technical side. It complements the existing planning
set rather than restating it: [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md) holds
the persona-evidenced near-term backlog (R and E item ids below refer to it),
[`feature-roadmap.md`](feature-roadmap.md) the ship-next list,
[`roadmap.md`](roadmap.md) and [`product-roadmap.md`](product-roadmap.md) the
multiyear capacity and value plans, and [`expansion-research.md`](expansion-research.md)
the verified competitive research. This document asks a different question: if
the project were rethought from scratch today, which larger bets would be worth
it, and in what order?

Method: a July 2026 web pass over the GTFS ecosystem, federal reporting policy,
international open-data programs, and the AI-tooling landscape, read against
what the repo already ships. Claims that drive a recommendation carry a source.

## What changed around the tool (the why-now signals)

1. **The scorecard's exact audience becomes federally obligated this report
   year.** FTA's NTD rule requires valid GTFS from full reporters starting RY2025
   and from reduced, rural, and tribal reporters in RY2026, with a waiver
   available only to agencies showing they are pursuing technical assistance
   ([Federal Register, July 2025](https://www.federalregister.gov/documents/2025/07/10/2025-12813/national-transit-database-reporting-changes-and-clarifications-for-report-years-2025-and-2026);
   [Eno Center summary](https://enotrans.org/article/a-fistful-of-data-fta-updates-transit-database-reporting-requirements/)).
   Thousands of small agencies that never had a compliance reason to care about
   feed quality now have one, dated this year.
2. **The spec is growing in exactly the directions the rubric already watches.**
   The canonical validator's v7 line validates GTFS-Flex fully and covers
   Fares v2 rider categories; community votes are active on contactless-payment
   signalling (cEMV), demand-responsive updates, and deprecating
   `TripUpdate.schedule_relationship = ADDED`
   ([MobilityData](https://gtfs.org/blog/author/mobilitydata/),
   [validator releases](https://github.com/MobilityData/gtfs-validator/releases)).
   Adoption of optional features is becoming measurable, and this repo already
   detects flex, fares, and pathways per feed.
3. **AI agents became a mainstream data consumer.** The Model Context Protocol
   is now the de facto integration layer for LLM agents, with support from every
   major provider and thousands of public server implementations
   ([MCP overview](https://en.wikipedia.org/wiki/Model_Context_Protocol);
   [Anthropic announcement](https://www.anthropic.com/news/model-context-protocol)).
   Scientific and civic datasets are shipping official MCP servers (for example
   [Open Targets](https://blog.opentargets.org/official-open-targets-mcp/)).
   The site already publishes `llms.txt`; the natural next step is a queryable
   agent interface over the same artifacts.
4. **Other countries run the program this tool approximates.** England's Bus
   Open Data Service publishes timetables, fares, and vehicle locations
   nationally and pairs them with a free analytics service for operators and
   authorities ([BODS](https://en.wikipedia.org/wiki/Bus_Open_Data_Service)).
   The EU mandates NeTEx and SIRI in national access points while GTFS stays the
   de facto planning format ([Open Data Hub Day 2025](https://pretalx.com/open-data-hub-day-2025/talk/8AMFQP/)).
   There is both a model to learn from and a coverage frontier to expand into.

## A. Deepen: from reporting problems to fixing them

The scorecard tells an agency what is wrong and what to change. The next altitude
is helping them do the change and prove it worked.

- **The compliance moment (build first).** An "NTD RY2026" campaign surface for
  rural and tribal reporters: a landing page and program-rollup view that says
  who in a state is ready to certify, what the waiver path is, and which single
  fix would make a feed submittable. All of the data exists (ntd_readiness,
  program rollups, outreach notes). This is a timing play: the audience is
  looking for exactly this in the next two report cycles and nowhere else frames
  it in plain language. Extends R7 and the shipped NTD pages; effort S to M.
- **A pre-publish check for the person exporting the feed.** `scorecard try`
  already gates a feed in CI, but the manager exporting from scheduling software
  does not run CI. A drag-and-drop page that reads a GTFS zip client-side and
  answers the five questions that matter before publishing (does it parse, when
  does it expire, are wheelchair fields present, are fares present, do stops
  have names) would close the loop at the moment of export. Client-side keeps
  the static-site model and keeps feeds private. Not the full Java validator;
  a deliberately small preview that names when the canonical validator will
  still be the authority. Effort M.
- **Comparable finding clearance as a product.** R4's finding diff shipped. The
  stronger version is a dated, linkable record that finding X was present through
  one check and absent from the next complete, compatible check. It is suitable
  for a board packet or NTD narrative when it states that causal attribution
  requires a separate action record. Cheap render over existing history; pairs
  with E6's board one-pager.
- **Vendor worklists (E4), with the procurement hook (E5).** The research
  roadmap already scopes these. The ideation-level point: together they change
  who the user is. Most small-agency feeds are vendor exports, so the shortest
  path to fixing a thousand feeds is a few dozen vendor dashboards plus contract
  language that references the conformance mark. Validate with one vendor before
  building, as the roadmap warns.

## B. Widen: coverage as the moat

- **Canada next.** Same standard, same validator, and the Mobility Database
  already catalogs Canadian feeds. The blocker is small and technical: the
  registry and artifacts carry no country field today (a speculative Canada
  filter was cut from the map for exactly this reason). Add `country` to
  `agencies.yaml` and the artifact schema, teach state handling to treat
  provinces as peers, and the whole rendered surface follows. Effort M, no new
  architecture.
- **England as a study, not a port.** BODS timetables are published in GTFS, so
  scoring English operators is technically near-free once fetching handles the
  BODS API. The real question is positioning: ABOD already gives operators
  analytics, so the scorecard's plain-language fix framing is the differentiator
  to test there, not coverage itself.
- **The EU via crosswalk, not conversion.** NeTEx and SIRI are legally required
  in EU access points while riders' apps still run on GTFS. Scoring NeTEx
  natively would be a rewrite; the leverage is the crosswalk pattern this repo
  already uses for standards: score the GTFS representation, state clearly what
  it does and does not say about the NeTEx source of truth. Do not attempt
  before Canada proves the multi-country rendering.
- **Global South stays a bounded pilot.** ADR 0028 is accepted and
  partnership-gated; nothing here changes it.

## C. Open the platform: the dataset is a second product

- **Make the artifact store the source of truth, then make it citable.** The
  operational path is already written down (S3 cutover steps in
  [`follow-ups.md`](follow-ups.md)). Once artifacts stop being git files, two
  things unlock: bounded history at any scale, and versioned dataset releases
  with a data dictionary and a DOI-style stable reference (E7). A national
  daily panel of feed quality does not exist publicly anywhere; researchers are
  a real audience with zero serving cost.
- **Parquet-first analytics, queryable in the browser.** The repo already
  publishes `agencies.parquet`. The overhaul version: publish the full history
  as partitioned Parquet and embed DuckDB-WASM on a "query the dataset" page,
  so a journalist or MPO analyst can run SQL against national feed-quality
  history with no backend added. This is the same static-first principle,
  applied to analytics.
- **An MCP server over the scorecard.** Expose read-only tools (look up an
  agency, fetch its findings and fixes, query the catalog, fetch the fix
  knowledge base) so agent-based assistants can answer "why did my grade drop
  and what do I tell my vendor" grounded in the published artifacts. Serverless
  or run-locally packaging keeps cost at zero; the JSON contract already exists.
  This is cheap, differentiating, and reversible.
- **Push, not poll (E8).** A change feed (RSS/Atom plus a webhook) on grade or
  expiry transitions turns consumers from daily re-crawlers into subscribers.
  RSS is static-publishable today; webhooks can ride the existing alerts stack.

## D. Extend the measurement: from published data to lived service

- **Adoption scoring, carefully.** Flex, Fares v2, pathways, and (once voted)
  cEMV are now detectable and validator-covered. Keep them as celebrated
  adoption signals rather than graded categories, so an agency without fares
  data is behind on features, not failing. The compare page and map filters
  started this; a national "who has adopted what" page completes it.
- **Realtime accuracy is the next honest frontier.** Today the rubric measures
  RT presence and freshness. With the continuous archive (E14, ADR 0018) the
  measurable question becomes "did the predictions match what happened".
  England's ABOD already reports on this class of metric nationally. This is
  the one direction that justifies always-on compute; it stays demand-gated,
  but it is where the measurement should eventually go because riders feel
  prediction error, not header lag.
- **Trip-plannability at sample scale.** The OTP wiring is now in place
  (`_otp_section`, gated). A weekly batch that runs a small OD sample for the
  worst and best feeds would put a "can a rider actually plan a trip" number on
  real pages for the cost of one CI job plus a containerized OTP.

## E. Overhaul the plumbing only where the seams already show

The static-first architecture has held to about 1,200 agencies and should be
kept; every direction above is chosen to preserve it. The known seams and their
prepared answers: artifact history in git (S3 cutover, written), the Actions
matrix ceiling (fan-out compute in `infra/compute`, written, migration-shaped),
and fetch hostility from government WAFs (resilient fetching, shipped). The
honest overhaul finding is that the pipeline does not need rethinking; the
product around it does.

## Sequencing recommendation

1. **Now:** NTD RY2026 campaign surface; Canada country plumbing; MCP server;
   change feed. All small, all on existing data.
2. **Next:** pre-publish drag-and-drop check; Parquet + DuckDB query page;
   dataset releases with a citable reference; adoption overview page.
3. **Later, demand-gated:** vendor worklists after one vendor interview; OTP
   sample batch; England study; RT accuracy once the archive bet is funded.
4. **Not now:** EU NeTEx scoring, anything resembling a feed editor, any
   always-on backend without a named user asking.

## Deliberate no's, restated

The scope risks named in the research roadmap still bind: no feed editing, no
punitive public rankings, no platform ambitions that displace the canonical
validator, and no always-on infrastructure ahead of demand. Each direction above
was checked against the two people the tool exists for, the manager who
inherited the feed and the liaison preparing for the call. Anything that does
not shorten their path to a fixed feed is a distraction, however interesting.

## Implementation status — 2026-07-01

Executed the same day, one PR per item. Tier 1: NTD RY2026 triage on /ntd/ with
the one-fix-from-ready list (#221); Canada plumbing was already shipped by the
recovered Canada pilot (#211–#217, restored in #222 after main lost them); the
read-only MCP server, `scorecard-mcp` (#223); the Atom change feed predated this
doc (`changes/feed.xml`). Tier 2: the /query/ in-browser SQL page (#225); the
/check/ pre-publish page (#226); monthly citable dataset releases (#224); the
adoption overview predated this doc (/adoption/). The OTP sample batch shipped
2026-07-02: the "hosted OTP" gate dissolved once `otp-qa.yml` built a throwaway
containerized OTP per feed, so the workflow now runs weekly — a select job picks
the best and worst scored feeds from the index (`otp_batch.select_best_worst`)
and a fan-out job builds, serves, and samples each one. Still open, per this
doc's own gates: vendor worklists (interview a vendor first), the England study,
RT prediction accuracy (needs the archive bet), and everything under "Not now".
