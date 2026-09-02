# Global coverage roadmap

Last updated: 2026-07-25

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

### The declared candidate universe

A 2026-07-25 snapshot puts a hard boundary around the current discovery
universe. [Mobility Database V2](https://files.mobilitydatabase.org/feeds_v2.csv)
(SHA-256
`86e46cb822b1aa11447837c2cdc87755ad8a6f571135d290095a62d4129a2834`)
contains 2,574 active, keyless Schedule rows.
[Transitland Atlas](https://github.com/transitland/transitland-atlas) at commit
[`1df848a`](https://github.com/transitland/transitland-atlas/commit/1df848a98107189e6df16bad2ec28825cfb8f4c6)
(archive SHA-256
`c3b93c14c7f4162eb9e8c386e8486f18c94cc2d4ecab07a5d10422e3e50afe30`)
contains 3,739 Schedule rows with a current, keyless URL.
After applying the project's scheme-insensitive endpoint normalization, their
union is about 5,092 endpoints before content, operator, aggregate, redirect,
identity, and reuse review. The current registry contains more than 2,600 feed
records.

A literal 100-fold increase from that registry would require more than 200,000
records, far beyond the current public-catalog supply and contrary to this
roadmap's curation rules. Here, a "100x coverage loop" means candidate-processing
leverage: record a disposition for at least 95% of a declared, deduplicated
eligible snapshot without weakening human review or auto-writing the registry.
The loop is:

```text
source snapshot and hash -> cheap preflight -> identity/content clustering ->
reuse decision -> 25-record canary -> three checks across seven days ->
recommendation audit and upstream catalogue corrections
```

Each new admission is paired with one legacy rights or identity audit until at
least 90% of the registry has current evidence. Duplicates, mirrors, aggregates,
and alternate URLs never count as extra coverage merely because they are extra
catalog rows.

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

Twenty official Japanese records passed a larger endpoint-kind review on
2026-07-23: thirteen CC0 services in Toyama and seven CC BY 4.0 services in
Mie. Every current schedule archive passed the canonical validator path. The
official catalog supplied 47 keyless realtime endpoints: all twenty records
publish TripUpdates and VehiclePositions, and the seven Mie records also
publish ServiceAlerts. Every endpoint returned a valid protobuf response
during admission, although many were header-only at that moment.

The public feature contract now distinguishes the exact endpoint kinds that
responded and whether the newest TripUpdates or VehiclePositions header was
fresh. This is latest-sample evidence, not continuous availability, rider
information content, prediction quality, or trip coverage. Japan now has 260
reviewed feed records across the same 40 prefectures. The batch adds regional
depth and new product evidence without changing the national-coverage claim.

An eleventh repository pass then admitted 119 official schedule records from
publishers with exactly one current feed. Every downloaded archive passed the
pinned canonical validator path, carried one of the three already reviewed
versioned Creative Commons licenses, and retained at least 60 days of effective
service. Two catalog records with expired calendars, one near-expiry record,
one private residential shuttle, and publishers represented only by several
line or area fragments stayed out. Japan now has 379 reviewed feed records
across the same 40 prefectures. This remains depth in a reviewed sample, not a
census or a claim of national coverage.

A portal-first exhaustion pass on 2026-07-23 then added 70 reviewed feed
records without weakening those gates. France's National Access Point supplied
57 local-network records under Licence Ouverte 2.0. Existing-country depth also
grew in Canada (four records), Germany (two), and the United Kingdom (two).
Official city and national portals opened four new country samples: Albania
(Tirana), Moldova (Ungheni), Serbia (Belgrade), and Ukraine (Kyiv and Lviv).
Every schedule archive passed the complete scorecard path and retained at least
60 days of effective service. Twenty-seven records also carry official,
keyless realtime endpoints. This is a reviewed source cohort, not a country
census.

The same pass exhausted the remaining plausible official/open catalog set and
kept its failures visible. Short or expired calendars excluded Canberra Light
Rail, Brussels STIB/MIVB, Luxembourg's national feed, and Metlink Wellington.
Unreachable or non-archive sources excluded METROFOR, four French local
networks, Mexico City, Hyderabad Metro, and several Portuguese feeds. Santiago
remained out because its official current-feed page did not state an explicit
commercial-reuse licence. Bogotá's very large feed did not complete a bounded
local score and its catalog licence is share-alike outside the project
allowlist. Ambiguous source/licence identity excluded Cascais and Barreiro.
These are future recheck targets, not silent omissions.

A 20-loop continuation on 2026-07-23 then admitted 11 more records. Cyprus
opened as a six-operator CC BY 4.0 sample, and TGSRTC Greater Hyderabad opened
India under the operator's explicit commercial and non-commercial reuse terms.
Existing-country depth added VBB's GTFS-Flex collection, Reus Transport, the
Creuse regional network, and Belgrade's suburban feed. All 11 archives
completed the pinned validator and full scorecard path with at least 60 days of
effective service.

The continuation also made its exhaustion results explicit. A 73-candidate
official/licensed catalog set yielded 55 local score artifacts and 18 bounded
source or archive failures before evidence review. Sardegna's eligible portal
feeds were already tracked. Duplicate Madrid and Sardegna records, GTT Torino's
non-commercial terms, Kraków's unresolved commercial licence, Bydgoszcz's
community-converter provenance, Portugal's source/licence mismatches, Bogotá's
share-alike licence, Santiago's unstated commercial grant, and short or expired
calendars in Australia, New Zealand, Belgium, Luxembourg, Canada, and Mexico
all stayed out. The pass increases the reviewed sample without loosening the
identity, reuse, validator, or calendar gates.

An API-level exhaustion of France's National Access Point followed on
2026-07-23. All 774 catalog datasets were considered, and all 331 currently
unmatched GTFS resources were run through the complete local scorecard and
60-day calendar gate. Of 147 mechanical passes, overlap and source review
retained 137: 136 French resources plus Tanéo in New Caledonia, which is
correctly modeled under ISO `NC`. Six regional aggregates, three duplicate or
superseded resource versions, and one anomalous stale export remained out.
France's reviewed European cohort grows by 136 records across 15 regions and
collectivities. Multiple resources belonging to one dataset share canonical
organization identity instead of being presented as extra operators.

The same loop opened Puerto Rico and Oman from official provider evidence.
Puerto Rico ATI explicitly invites developers and companies to use its
open-data GTFS. Mwasalat serves its current GTFS from its official Oman
National Transport Company domain, labels its route-data surface as open data,
and is covered by Oman's national license permitting commercial and
non-commercial reuse with attribution. Both feeds passed the validator and
calendar path. Grade was not an admission criterion.

The rejected set establishes the next boundary. Sweden's national Trafiklab
archive is useful but key-gated. Monaco and Iceland fell below the calendar
horizon; Luxembourg was stale and Taiwan returned 401. Mexico, Argentina, and
Chile did not supply a current candidate with the required source and
commercial-reuse chain. Community-produced African feeds remain
partnership-gated. The registry these waves produced, 2,185 records across 46
country codes on 2026-07-25, is a reviewed sample and not a census or
national-coverage claim. That figure records what the phase delivered and is
not refreshed as the registry grows.

A second National Access Point exhaustion ran on 2026-08-30, five weeks after
the first. Of 206 still-untracked open-licence GTFS datasets, it admitted 76
records under the unchanged licence, identity, validator, and 60-day calendar
gates, including Naolib (Nantes Métropole) as the first French record on the
bounded large-feed tier after a full local score under its raised limits. The
exclusion ledger is the larger half of the result: 100 candidates sat under
60 days of service ahead of the September rentrée refresh and are the
standing recheck queue, eight regional aggregates and seven alternate
publications of tracked networks were refused as non-coverage, six tracked
datasets were found publishing from rotated resource URLs (a `discover`
follow-up), five producer hosts were unreachable, and two calendars ending
9999-12-31 exposed a freshness date-arithmetic overflow now noted as pipeline
hardening work. Île-de-France Mobilités and TCL Lyon remain out under the
portal's restricted "Licence mobilités". The pass is recorded in
`docs/feeds.md`; it grows the reviewed French sample to 343 records and does
not change any census or gate claim.

A rentrée recheck on 2026-09-01 then admitted 14 of those deferred
candidates whose September exports had already landed, SETRAM (Le Mans)
among them, under the unchanged gates. Seventy-eight stay queued on short
calendars and the queue is expected to keep clearing through the month.
The recheck also moved the rotated-resource dedupe from hand review into
the candidate pool builder itself.

A twenty-lane parallel pass on 2026-09-01 admitted 390 reviewed records. Its
France lane overlapped the two exhaustion passes above, which ran on the same
portal in the same window; after reconciling the overlap the registry stands at
2,643 records across 48 country codes. It worked a declared
universe of 3,148 candidates — the Mobility Database and Transitland Atlas rows
not already tracked — and every candidate has a recorded disposition. Depth
dominated: Japan 196, Ireland 60, France 57, Canada 16, Spain 11, Norway 10.
Iceland and Luxembourg opened as new country codes, both on rechecks whose
earlier failure was a stale calendar rather than a licence. Five of Japan's
seven empty prefectures closed — Fukui, Tottori, Hiroshima, Ehime, Miyazaki —
after the pass established that gtfs-data.jp carries no feed in any of the
seven, so each had to come from its own prefectural portal.

Three feeds entered the large-feed tier by curator decision: Transport for
NSW's Greater Sydney bundle, whose registration wall is gone and whose 279 MiB
download is now keyless; the Bus Open Data Service London file under OGL 3.0;
and Naolib Nantes, which needs the tier for an oversized `stop_times.txt`
rather than for its 25 MiB download. Sydney and London are regional bundles
counted as one feed record each, following the Tasmania precedent, and each
says so in an `operating_note` rather than implying one accountable publisher.

The pass also recorded what stops coverage rather than only what advanced it.
Reuse terms, not feed availability, are the binding constraint in the United
States: of 336 candidates one lane examined, 236 were live archives inside the
calendar horizon and 206 of those publishers state no reuse terms anywhere on
their own domain. Two state clearinghouses decline explicitly — Virginia DRPT
("The agencies retain full rights to the data") and Colorado CDOT, whose
licence column reads "None" for every agency. Around 210 more candidates sit on
National RTAP's GTFS Builder host, whose terms grant rights to National RTAP
rather than to downstream reusers; because RTAP disclaims ownership, no
platform-level decision by RTAP can release them, and the grant has to come
from each uploading agency. Sweden stays closed after a full check: every
Samtrafiken path returns 403 and the national portal carries one GTFS dataset,
Trafiklab's, behind a key. Kosovo cannot be admitted at all — `XK` is a
user-assigned code the validator country contract rejects.

Two questions about records already in the registry came out of the pass and
are deliberately left open rather than settled inside it. 158 French records
cite ODbL while `docs/feeds.md` names ODbL French datasets as excluded, and
Estonia's national register is published as CC BY-SA 3.0 although two Estonian
records are listed. Both are the same question — share-alike records already
published — and both are recorded here for a decision of their own. This wave
applied the stricter reading to new admissions and changed nothing existing,
which left roughly 84 ODbL French datasets and 19 Estonian county feeds out.

A second, narrower pass on the same day worked only what the twenty lanes left
open: countries a lane stopped short on, hosts that were unreachable at the
time, and deferrals held for a curator. It added 6 records, taking the registry
to 2,581, and its value is mostly in what it settled rather than what it added.

Austria went from one record to two and is now understood. Its national portal
moved to the piveau stack, so there is no CKAN API; enumerating all 73,270
datasets through the working endpoint finds exactly three GTFS datasets. ÖBB is
admitted on the large-feed tier from the current 2026 resource. Every regional
Verkehrsverbund publishes instead on `data.mobilitaetsverbuende.at`, which is
enumerable anonymously but returns 401 on the file endpoint by documented
policy: 17 datasets, refreshed weekly, licence terms that already permit
commercial reuse with attribution, and a registration wall that one manually
created account would clear. That is a partnership and credential decision, and
it also needs code, because `static_gtfs_url` assumes a keyless URL.

De Lijn opens Flanders on the tier. West Midlands joins London from the Bus
Open Data Service after the twelve regional bundles were measured rather than
guessed: streaming each one and matching trips against the registry put
duplicated trip share at 0.03% for West Midlands and between 7% and 35% for the
other ten, so only the two regions that duplicate nothing were admitted. The
Irish small-operators bundle was rejected by the same measurement at about 81%
duplication.

Two large Japanese blocks stay out, and the reasoning matters more than the
outcome. `ckan.hoda.jp` is a real municipal venue rather than a private
re-host, but its GTFS is one third-party dataset in which 50 of 70 archives
name a single vendor as publisher on a manufactured uniform calendar window,
with no terms page and only a catalog licence field. OTTOP fails on reuse
terms, not on the local-steward gate: its terms impose indemnity, unilateral
amendment and discretionary access restriction, which CC BY 4.0 forbids a
licensor to add.

One gap in that pass's own record is worth stating. The Iberian lane's agent
was cut off by an infrastructure error three times and wrote its staging file
on the third attempt but never its report, so its 15 admissions are in the
registry and independently spot-checked, while its **rejections were never
written down**. Spain and Portugal are therefore the one part of the wave whose
"already looked at and refused" set does not exist. A later pass should expect
to re-derive it rather than assume those countries were documented as
exhaustively as the other nineteen lanes.

The pass also corrected the record in three places. A Japanese restriction
string that had looked like a licence term, and had held up two admissions, is
an export tool's own notice: it appears byte-identical in feeds from three
unrelated publishers on three portals, always immediately after the tool
version, always with the tool author's address in `feed_contact_email`. Two
hosts wave 1 recorded as NXDOMAIN resolve normally through public resolvers and
were local resolver artifacts. And several countries recorded as "unopened"
were reached and are now documented empty of GTFS: Panama, Peru, Mexico's
national portal, and Malta, whose absence is confirmed against five independent
sources including the European Commission's access-point register and an
Internet Archive sweep of 8,000 URLs per host. Romania's national portal is
still unreachable, but its European harvest holds 5,238 datasets and no GTFS,
which disproves rather than defers the hypothesis that it carried the missing
licences.

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
