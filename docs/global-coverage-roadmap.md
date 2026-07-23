# Global coverage roadmap

Last updated: 2026-07-17

This is the multi-region coverage plan. It sits above the Europe-specific
[`global-expansion.md`](global-expansion.md), which owns the European GTFS beta
gate in detail, and it inherits the operating gates in [`roadmap.md`](roadmap.md)
and the product principles in [`product-roadmap.md`](product-roadmap.md). Where
they conflict, those documents win; this one sequences the regions and names the
gate each region must pass before it is curated.

## Why this document exists

The service began as a Yolo County pilot, grew to national United States and
Canadian coverage, and now carries a reviewed European cohort and a handful of
worldwide canaries. "Support other regions" is easy to say and easy to get
wrong. It is not one job. It is at least four:

1. curating official, openly licensed feeds a region already publishes;
2. sourcing feeds a region publishes somewhere other than the Mobility Database;
3. deciding whether a region needs its own bounded beta gate or is served by
   ordinary coverage growth; and
4. deciding when a region must not be curated by this project at all until a
   local steward owns consent, licensing, and regional context.

These have different evidence and different gates. This roadmap keeps them
separate so the map never fills faster than the review behind it.

## Principles that do not move

- **One universal scoring core.** Every region is scored by the same GTFS
  Schedule rubric and the same canonical MobilityData validator. Regional
  policy modules (United States NTD, Canadian equity) stay conditional on the
  country and never change another region's grade. Adding a region must not
  touch weights, thresholds, or the scoring profile
  ([ADR 0026](decisions/0026-internationalization.md),
  [ADR 0035](decisions/0035-worldwide-defaults-regional-modules.md)).
- **Defensibility before breadth.** A region is curated in the order its feeds
  can be defended: official first-party source, reviewed reuse terms, retained
  attribution, checked identity. A larger flag count is never the reason to
  relax that order.
- **Coverage is not a success measure.** Feed count, country count, and map
  fill are distribution facts, not proof the tool helped anyone. The success
  measures stay the remediation and decision-support outcomes in the product
  roadmap. This document exists to grow coverage *honestly*, not to make growth
  the goal.
- **The local-steward gate is real, not a formality.** For any region where the
  data is community-mapped, where informal transit dominates, or where reuse
  and consent cannot be established from a public official source, this project
  does not curate until a named local steward owns licensing, source
  verification, and the regional consent or partnership requirement
  ([`roadmap.md`](roadmap.md) "Later: demand-gated options"). This is a values
  commitment: a tool built in California does not arrive uninvited to grade the
  Global South's transit data.
- **Never a census.** A regional cohort, however large, is a reviewed sample.
  The interface states the regional denominator beside every filter and export
  and never describes a feed-record count as an agency, operator, or coverage
  census of a country or region.
- **Fail closed.** Unclear reuse terms, unreachable sources, unverifiable
  identity, and out-of-cap archives are excluded and the exclusion is recorded,
  not quietly dropped.

## The coverage landscape

The Mobility Database catalog, the project's main discovery source, is heavily
weighted toward Europe and North America. A 2026-07 pass over the catalog found,
among active feeds with an open, non-key-gated download and no contrary official
flag, roughly: 920 in the United States and Canada, 390 across 35 European
countries, 38 in Oceania (almost all Australia and New Zealand), 25 across nine
Asian countries, 29 across Latin America, 10 across the Middle East, and 9
across Africa.

That distribution is the plan's central constraint. It does not mean those
regions publish little transit data. It means they publish it somewhere else:
national and city open-data portals, regional aggregators, and
community-mapping projects that never registered with the Mobility Database.
Sourcing, not curation effort, is the binding limit outside Europe and North
America. Each phase below names where a region's feeds actually live.

## Phases

The phases are ordered by defensibility, and each ships as its own reviewed
pull request. A later phase does not block on an earlier one, but the
partnership-gated phase never runs on catalog scraping alone.

### Phase 0 — shipped

The pilots, national United States and Canadian coverage, the reviewed European
cohort (148 feed records across 17 countries as of 2026-07-17, tracked against
the beta gate in `global-expansion.md`), and worldwide canaries in Japan,
Malaysia, New Zealand, Australia, and Uruguay. The registry, artifact pipeline,
per-country program pages, and the world coverage map already carry worldwide
locations; the portable location contract (ISO 3166 country and subdivision,
Unicode names, bidi isolation, locale formatting) is in place.

### Phase 1 — Oceania official (in progress)

Australia and New Zealand publish official government GTFS through mature
open-data programs under Creative Commons Attribution or equivalent. They are
anglophone, first-party, and openly licensed, so they raise no local-steward
concern; they are the same kind of record as an official European feed. The
first wave curates the readily fetchable state and metro feeds — the Queensland
TransLink networks, the Northern Territory, Tasmania, Western Australia, and the
New Zealand metros — and defers the Sydney and Melbourne bundles and any
national aggregate that exceeds the ingestion size cap to the large-feed shard
work below.

Gate: official government or provider source, an explicit open license
(commonly CC BY 4.0), retained attribution, checked identity, within the
ingestion caps.

Tasmania's previous license and fetchability hold cleared on 2026-07-22. The
Tasmanian Government now publishes one stable, keyless statewide aggregate on
its official transport site under CC BY 4.0. A full preflight found a valid
15 MiB archive for six listed publishers, bus and ferry routes, explicit
`feed_info.txt` dates, and service through 2026-09-30. The registry counts the
aggregate as one feed record, not six agencies.

### Phase 2 — Latin America official first-party

Several Latin American authorities publish official GTFS under national
"datos abiertos" or Creative Commons licenses through their own portals, only
some of which are mirrored in the Mobility Database. The phase curates the
official, openly licensed city and regional feeds — the strongest candidates
are the metropolitan authorities that run their own open-data programs — and
records the exclusions where a feed is community-hosted, key-gated, or lacks
readable terms. It does not attempt whole-country coverage and it does not treat
a metropolitan feed as national coverage.

Gate: official authority source, an explicit open or datos-abiertos license
with retained attribution, checked identity, within caps. A community-hosted or
terms-silent feed is deferred to the partnership-gated phase, not force-fit
here.

### Phase 3 — Asia-Pacific and Middle East official

Parts of Asia publish official GTFS through national data programs (for example
Japan's national GTFS data service and Singapore's transit authority), and
several Middle Eastern authorities publish under open terms. The phase curates
those official, openly licensed feeds and records the many large systems that
are key-gated, registration-walled, or published only through a consumer app as
exclusions. It does not infer permission from a feed merely appearing in a
catalog.

Gate: as Phase 2. Regions where the dominant standard is not GTFS, or where the
official feed is only reachable behind an account, are out of scope for this
phase and noted for the alternative-catalog work below.

The Hong Kong Transport Department aggregate is now the phase's frequency-based
schedule canary. DATA.GOV.HK publishes the keyless GTFS under terms permitting
commercial and non-commercial reuse with attribution. Its calendar runs to
2099, so admission required a full scorecard preflight: freshness remains
measured, explicitly labels the horizon unusually distant, and deducts for
missing `feed_info.txt` dates rather than treating the end date as evidence of
active maintenance. Hong Kong has no ISO 3166-2 child in the portable location
vocabulary, which exercises the supported country-only location contract.

Four BAS.MY town feeds cleared an earlier data-quality hold on 2026-07-22.
Malaysia's official open API republished Alor Setar, Kota Bharu, Kuala
Terengganu, and Kuching with hundreds of trips and service through 2026-12-31.
All four keyless archives passed the canonical validator preflight under the
same CC BY 4.0 platform and now add reviewed coverage in Kedah, Kelantan,
Terengganu, and Sarawak.

Five official Japanese networks passed another bounded depth review on
2026-07-23: Kamishihoro Town Autonomous Bus, Konan Railway, Tsukubane-go,
Awaji Jenova Line, and Hokushin Bus. They use the three already admitted
versioned Creative Commons licenses and add one record in each of five
previously represented prefectures. The loop deliberately rejected Tsuku Bus:
its current archive still gives four required GTFS files `.csv` names, so the
canonical validator cannot recognize a usable service calendar. This is
regional depth from an official source, not a new-country or census claim.

Five additional licensed Japanese records passed an operational-depth review
on 2026-07-23: JR East's Tsugaru Line replacement bus, Mizuho Town's
reservation-based Choi-Soko service, Toyama Chitetsu's regional bus network,
Toba City's island ferries, and Kochi's airport shared taxi. The set adds
replacement-service, demand-responsive, regional-bus, ferry, airport-link, and
keyless realtime evidence without changing the 40-prefecture denominator.
Japan now has 235 reviewed feed records in the catalog. The seven prefectures
without an admitted source remain empty; no unclear-license feed or mirror was
used to change that count.

Five more licensed Japanese bus records passed a realtime-evidence review on
2026-07-23: Kaetsuno World Heritage Bus, Owari Asahi Asapy-go, Tokoname Gruun,
Mie Kotsu's Shima-area service, and Kumamoto Dentetsu Bus. Each official
catalog record supplies keyless TripUpdates and VehiclePositions endpoints.
The admission check confirmed current schedule archives and endpoint
responses, but does not treat a response as an uptime, prediction-quality, or
trip-coverage guarantee. Japan now has 240 reviewed feed records across the
same 40 prefectures.

### Phase 4 — partnership-gated regions

Much of the Global South's transit is informal — minibuses, matatus, colectivos,
angkot — and its GTFS, where it exists, is produced by community-mapping and
capacity-building projects, not by a government open-data portal. The largest
sources are the [Digital Transport for Africa](https://digitaltransport4africa.org/)
commons (managed by WRI and the Agence Française de Développement, feeds
typically under ODbL) and the Digital Matatus lineage of university and
community collaborations. These are community-produced, and a Northern-built
tool that assigns them a letter grade risks reading as a deficit judgement of
the community rather than feedback to an accountable publisher. This project
does not curate those feeds from a catalog.

The phase opens only when a named local steward — a regional program, a transit
authority, or the community project that produced the data — owns the licensing,
source verification, and consent, and agrees to operate or review the regional
cohort. It is governed by the bounded Global South pilot in
[ADR 0028](decisions/0028-global-south-pilot.md), and it adopts, by analogy, the
[CARE principles for data governance](https://www.gida-global.org/care)
(collective benefit, authority to control, responsibility, ethics) alongside the
project's existing no-shaming stance. Concretely:

- **Opt-in, not opt-out.** No public grade for a community-produced feed without
  the local steward's sign-off, and a standing removal right — the community's
  right to be off the scorecard, mirroring the humanitarian-mapping "right to
  invisibility."
- **Credit the steward.** The community or program that produced the data is
  named and attributed, never treated as an authorless source.
- **Support, not sanction.** For an informal feed, findings are framed as
  support and next steps, and the interface does not imply an accountable agency
  exists to act on them. An informal or demand-responsive feed is scored as its
  own kind of object, not as a defective fixed-route feed — the same reasoning
  that already treats a missing realtime feed as neutral rather than a zero.
- **Benefit stays local.** The most defensible posture is a cohort a local
  partner runs or co-owns, not a Northern-hosted ranking of Southern cities. The
  no-public-leaderboard rule holds especially here.

Gate: a named local steward accepts the licensing, source, identity, and
consent responsibility; the reuse of each feed is established from a source the
steward confirms; and the pilot stays bounded and labelled per ADR 0028. Absent
that, the region stays uncurated by design, and the roadmap says so rather than
leaving a silent gap. The Digital Matatus project is the precedent worth
following: it validated data with the operators and commuters it described and
planned an explicit handoff to a neutral local steward with a mandate to keep
the data open.

## Cross-cutting enablers

These unblock more than one phase and are sequenced by first need.

- **Large-feed tier (shipped).** The standard ingestion caps (256 MiB download,
  512 MiB single entry, 2 GiB total) correctly exclude very large aggregates,
  but a small number of official national and metropolitan feeds legitimately
  exceed them: their compressed download runs past 256 MiB, or a single table
  such as `stop_times.txt` expands past 512 MiB. A feed now opts in per record
  with `large_feed: true` after a curator confirms it is a real published feed.
  The tier raises the size ceilings to a bounded larger level (512 MiB download,
  2 GiB single entry, 4 GiB total), streams the download to disk with a bounded
  memory footprint (`net.safe_download`), and gives the validator an explicit
  heap ceiling (`SCORECARD_LARGE_FEED_HEAP`, default 6g). Every zip-bomb *shape*
  guard — the entry count, the compression-ratio check, and the
  central-directory-only inspection before the Java validator opens the bytes —
  stays exactly as strict; only the raw size ceilings move, and only for an
  opted-in feed. The first records on the tier are Israel's national feed,
  Melbourne (PTV), HSL Helsinki, Wiener Linien, and Carris Metropolitana — each
  a feed the standard caps rejected. A per-mode or per-region *split* of one
  oversized feed (distinct sub-records that each score) remains a possible
  future extension for feeds larger than the bounded tier; the tier unblocks
  every current target without it. Sydney (Transport for NSW) stays deferred on
  its registration wall, not on size.
- **Beta-gate generalization decision (decided,
  [ADR 0040](decisions/0040-beta-gate-europe-scoped.md)).** The European beta
  gate is Europe-coded by design (a closed country set and thresholds chosen for
  that market's addressable feeds). The question was whether the gate becomes a
  parameterized contract (region, country set, thresholds, denominators)
  evaluated by the same executable evidence, or whether other regions stay
  ordinary reviewed coverage with no beta label. ADR 0040 is the decision of
  record: the gate stays Europe-scoped and is not parameterized now; other
  regions remain ordinary reviewed coverage with their own disclosed
  denominators and no beta label until a named consumer asks for a specific
  region and that region's cohort meets a stated, executable, region-appropriate
  gate, exactly as a consumer named European coverage. The ADR records the
  `RegionGate` seam so a second region's beta is an actionable follow-up with its
  own ADR when it is needed.
- **Alternative-catalog ingestion (first source shipped).** For regions the
  Mobility Database does not cover, a reviewed way to discover feeds from other
  catalogs, national open-data portals, and regional aggregators, with the same
  identity and reuse review. This is what actually raises non-Western coverage;
  catalog curation alone cannot. The [Transitland](https://www.transit.land/)
  Atlas is now wired in as a second discovery source: `scorecard sync --source
  transitland` (or `all`) reads its keyless, CC-BY DMFR registry, emits the same
  `CatalogFeed` shape the Mobility Database sync uses, and flows through the same
  proposer, deduplication, and curator-review-before-registry workflow. It never
  writes the registry directly and never guesses a feed's country — DMFR carries
  no ISO location, so a Transitland candidate surfaces with its location blank
  for the same review every feed gets. Key-gated feeds are flagged and skipped
  exactly as with the Mobility Database. National open-data portals remain a
  further source to add the same way.
- **A named-license vocabulary for non-SPDX government terms.** Outside Europe,
  many official feeds carry a custom national open license with no SPDX
  identifier — Mexico's Términos de Libre Uso MX, Israel's government open terms,
  jurisdiction-ported Creative Commons (CC BY 2.5 AR, CC BY 3.0 CL) — and some
  official downloads carry no per-file license at all despite statutory openness.
  The reuse-evidence review handles these case by case today. A small controlled
  vocabulary of named government licenses, plus an explicit reviewer note for
  "openness established by statute, no per-file license," would keep those
  judgements auditable without auto-approving any of them.
- **Per-region coverage denominators (shipped).** The finder and exports
  disclose the United-States-heavy global denominator, and each region now also
  discloses its own. Filtering the directory to a country or subdivision states
  that place's reviewed-cohort size beside the location controls ("19 reviewed
  feed records in Italy"), read from the directory summary counts, framed as a
  cohort size and never as a census. The per-country program pages carry the
  same scope line, and the `/status/` page states the European cohort's
  denominator with a per-country breakdown. A remaining refinement is to carry
  the per-region denominator into the CSV export headers as it is added to more
  activated regions. **That refinement shipped in July 2026:** every feature
  finder CSV row now repeats the selected coverage scope, its reviewed-record
  denominator, the matching-record count, and the shareable filter URL. Keeping
  the context in columns preserves a rectangular RFC 4180 file for downstream
  analysis.

## Completion

This roadmap is "complete" when the defensible, openly licensed, in-cap official
feeds in every region are reviewed and either curated or excluded with a
recorded reason, the large-feed shard has a design, the beta-gate generalization
has a decision, and every region that requires a local steward is documented as
partnership-gated rather than silently missing. Completion is a state of honest,
reviewed coverage with named gates — not a target feed count.

## What this roadmap will not do

- Auto-curate community-mapped or informal-transit data without a local steward.
- Claim a regional cohort is a country or regional census.
- Relax the reuse, identity, license, or size gates to raise a flag count.
- Treat coverage growth as a success measure for the product.
- Ingest NeTEx-only or SIRI-only datasets; those remain a separate decision
  ([`global-expansion.md`](global-expansion.md)).
- Add a regional beta label before a named consumer needs it and the cohort
  meets a stated, executable gate.
