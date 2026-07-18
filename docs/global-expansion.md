# Global expansion and European GTFS beta gate

Last updated: 2026-07-18

This plan separates four jobs that are easy to collapse into “go global”:
measuring multilingual GTFS, curating representative coverage, localizing the
scorecard interface, and removing assumptions tied to one country. They have
different evidence and release gates.

## What prompted this pass

One consumer-side participant in MobilityData Slack tried the feature finder,
confirmed that its accessibility detail supports their decision, and then named
two blockers: translations and European coverage. They also reported looking in
the primary navigation before finding the feature links near the bottom of the
page.

This is one qualitative source, not a market-size result. The findings are
directional:

| Finding | Evidence strength | Product response |
| --- | --- | --- |
| The feature finder was hard to discover. | High within the observed session; low prevalence confidence. | Put **Feed features** in primary navigation and deep-link to the focused finder. |
| The feature detail fits a real consumer decision. | Direct statement from one participant; medium confidence for this segment. | Keep row-level filters, evidence, CSV, and API aligned. |
| Rider-facing translations matter to consumers. | Concrete requested capability from one participant; low frequency confidence. | Measure `translations.txt`, expose language tags, and add language filtering without changing grades. |
| European coverage is a use blocker. | Explicit blocker for this participant; high impact and low generalizability. | Define a European GTFS beta gate before making regional claims. |

The response is deliberately smaller than a full international launch. It fixes
the observed navigation problem and adds the requested GTFS signal now. It does
not turn two European canaries into a representative dataset.

## Current baseline

The configured registry snapshot after the third depth wave and the parallel
Nordic-Baltic and Central Europe waves contains 1,296 feed records: 1,139 in
the United States, three in Canada, two in Australia, thirty-four in the
United Kingdom, twenty-eight in France, nineteen in Italy, sixteen in Spain,
fourteen in Finland, thirteen in Germany, six in Ireland, five in Poland,
two each in Switzerland, Czechia, Estonia, and Portugal, one each in
Austria, Belgium, Denmark, Latvia, and Lithuania, and one each in Japan,
Malaysia, New Zealand, and Uruguay. The public scored count is a separate,
smaller number reported by the status API; configured and published feed
records are not interchangeable.

The 148 records whose primary catalog location is in 17 European countries are
individually reviewed. They cover bus, tram, metro, light rail, regional rail,
ferry, national multimodal, and GTFS-Flex demand-responsive service. The
country and mode controls prove that the data model and interface can carry
worldwide locations; they are not country or regional samples. One French
record, Car Jaune, is located in La Réunion, an overseas department that the
country-code cohort rule counts as France.

The portable core already supports:

- ISO 3166-1 countries and ISO 3166-2 subdivisions;
- Unicode agency and place names, bidirectional isolation, and right-to-left
  document direction;
- locale-aware dates, numbers, and collation in the browser;
- removal of U.S.-only NTD and equity modules from non-U.S. agency pages; and
- one universal GTFS Schedule scoring profile, with regional rules kept outside
  the grade.

The full interface is still English. `/es/` is a reviewed Spanish-first lookup,
not a translated scorecard product. Feed translation measurement and interface
localization are separate: a French GTFS feed can publish `translations.txt`
even while this website remains in English.

## Translation capability contract

The official GTFS Schedule reference defines `translations.txt` as the optional
file for customer-facing translations. It uses BCP 47 language tags, requires
`feed_info.txt` when translations are present, and recommends `feed_lang=mul`
when the source text itself is multilingual. See the
[GTFS Schedule reference](https://gtfs.org/documentation/schedule/reference/)
and [translation example](https://gtfs.org/documentation/schedule/examples/translations/).

The scorecard now records, for every newly scored feed:

- whether at least one row has both a language tag and translated value;
- the number of such rows;
- the distinct language tags;
- the GTFS tables named by those rows; and
- the feed's declared `feed_lang`, when present.

This is an adoption signal. It never changes a grade, and it does not claim that
every rider-facing value is translated or that the translation is accurate.
MobilityData's canonical validator remains responsible for structural errors.
Older artifacts without this measurement remain unknown until rescored.

## European source audit

The 2026-07-15 Mobility Database CSV contained 587 active GTFS Schedule rows in
the EU27 plus the United Kingdom, Switzerland, Norway, Iceland, and
Liechtenstein. Of those, 554 were marked official or had no contrary official
status, and 406 carried a provider-license URL that still needs human review.
The largest official-or-unspecified candidate groups were:

| Country | Candidates | With a license URL |
| --- | ---: | ---: |
| Spain | 147 | 127 |
| France | 83 | 72 |
| Sweden | 59 | 59 |
| United Kingdom | 42 | 40 |
| Italy | 41 | 19 |
| Germany | 38 | 25 |

These are discovery counts, not approved scorecard records. MobilityData makes
the catalog metadata available under CC0, but each feed keeps its provider's
own terms. A license URL is evidence to review, not permission inferred by the
scorecard. See the
[Mobility Database catalog documentation](https://github.com/MobilityData/mobility-database-catalogs)
and [current global catalog](https://mobilitydatabase.org/).

European National Access Points are a second source-discovery layer. The
European Commission says every EU Member State has a National Access Point for
travel and traffic data and publishes the
[current NAP list](https://transport.ec.europa.eu/transport-themes/smart-mobility/road/its-directive-and-action-plan/national-access-points_en).
Each provider's terms still apply.

## What “Europe” means here

This service scores GTFS Schedule and configured GTFS-Realtime. It does not
currently ingest NeTEx, SIRI, or every public-transport dataset available in
Europe. The EU multimodal-travel framework uses NeTEx, or a demonstrably
compatible and interoperable format, for applicable static public-transport
data at National Access Points. See the
[consolidated EU regulation](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A02017R1926-20240304)
and the [European Commission overview](https://transport.ec.europa.eu/transport-themes/smart-mobility/road/its-directive-and-action-plan/multimodal-travel-information_en).

The next release may therefore claim a **European GTFS beta** only. It must not
claim coverage of European public transport as a whole. NeTEx normalization is
a separate architecture and product decision.

## European GTFS beta gate

The public beta label becomes available only when all of these chosen product
thresholds hold:

1. At least 250 active GTFS Schedule feed records have a verified provider or
   official source, reviewed reuse terms, and retained attribution.
2. The cohort spans at least 12 European countries, and no single country holds
   more than 40% of the beta records.
3. At least 95% have a scorecard produced within the previous seven days; every
   exception is counted on the status page.
4. Every beta record carries the translation-capability measurement and the
   portable country/subdivision contract.
5. Duplicate endpoints, regional bundles, modal variants, and operator identity
   are reviewed before publication. A feed-record count is never described as a
   distinct-agency count.
6. The feature finder states the regional denominator and keeps the coverage
   limitation beside the filters and exports.

The gate is now executable rather than prose-only. The site publishes its
current result and reviewed evidence at `/api/v1/global-coverage.json`, shows
the same result on `/status/`, and repeats the regional feature denominator
beside the finder. A `not_ready` result is expected until every threshold is
met. It blocks the beta label without blocking the individual canary
scorecards.

The first reviewed European cohort contained six feed records across France,
Ireland, and Italy. The nine-record breadth wave added one record in each of
Belgium, Switzerland, Denmark, Estonia, Spain, Finland, the United Kingdom, Poland,
and Portugal. The 2026-07-17 depth wave then worked the named review queues and
added 27 records: ten Great Britain operators on the Passenger open-data
platform, seven in Spain, four in Italy, four in Germany, and two in France.
A second wave on 2026-07-17 added 21 more from the same queues: twelve
further Passenger-platform operators, five Baden-Württemberg network feeds
from NVBW's portal, three in France including the Yeu-Continent ferry, and
Trenitalia's regional rail resource from Regione Toscana's catalog.

A third wave the same day worked every remaining non-Swedish queue in
parallel and added 75 records: twenty in France after resolving canonical
live URLs on the National Access Point, twelve in Italy across seven regions,
eleven more Passenger-platform operators, nine in Spain with one in Portugal,
twelve in Finland (the Waltti city networks, Föli Turku, and Tampere), five
Irish operators from the National Transport Authority's per-operator files,
four in Poland, and Czechia's first two records (PID Prague and IDS JMK
Brno). Eleven of the wave's candidates turned out to duplicate records the
parallel Nordic-Baltic and Central Europe waves merged the same evening; the
duplicates were dropped in favor of the merged records. Together the waves
produce 148 reviewed feed records across 17 countries, with the United Kingdom
the largest country at 23%. Country breadth and balance pass with room, and
the 250-record threshold still fails by design. Freshness, translation,
location, and identity remain executable per-record gates rather than claims
inferred from the registry. The source rows are public so a consumer can audit
what “reviewed” means.

The depth wave rejected more candidates than it added, and the reasons are the
point of the review: a non-commercial-only license (GTT Torino), terms that
could not be read at all (Metro de Málaga's dead license file, MVG's unstated
terms, Grenoble's script-only license page), registration walls or bot
challenges in front of the terms or the download (RNV, Essex County Council,
Kent Fastrack), calendars already expired at review (both Renfe feeds, Metro
de Madrid, CRTM Cercanías, HVV, TCAT Troyes), dead or moved catalog URLs
(MVV, MDV, TPER, BreizhGo, Bibus, Kicéo, Hauts-de-France, Hobus, BlaBlaCar,
GVA intercity), one archive over the 512 MiB single-entry cap (Île-de-France
Mobilités), one duplicate of an already-listed dataset under a different URL
(Delcomar, already covered by the Sardegna minor-islands record), and one feed
whose only license-bearing URL is unreachable from the pipeline's own network
(AMT Genova). Sweden stays at zero because every catalog download there is
key-gated; it needs API credentials, not more review effort.

The second wave repeated the pattern. STP Brindisi states adherence to a
national open-data policy without naming a license; the Zenbus-published
French networks declare ODbL plus unread special conditions; two Passenger
operator pages had been removed; and several catalog endpoints returned dead
archives. Deeper review in the third wave later resolved two of its
exclusions: the Sardinian regional catalog was found to list ASPO Olbia's
operator-hosted archive as one of its CC BY 4.0 datasets, and Genoa's
municipal open-data record was found to name a reachable municipally hosted
AMT archive.

The third wave's rejections came from every country at once. Seventeen French
datasets on the National Access Point declare ODbL, including the Grenoble,
Toulouse, Montpellier, Rennes, and both regional Nouvelle-Aquitaine and
Occitanie aggregates, and Île-de-France Mobilités uses a custom Licence
Mobilités; TMB Barcelona gates its download behind personal API credentials;
Lisbon's municipal portal hard-blocks automated access, which alone gates
Carris, CP, and Transtejo; Carris Metropolitana's archive exceeds the 512 MiB
entry cap, as do both reviewed Austrian feeds (Wiener Linien and ÖBB) and
HSL Helsinki; Estonia's national register endpoint serves an error page, so
its aggregate exists only on a third-party mirror; Belgium's STIB, SNCB, and
De Waterbus are registration-gated, non-commercial, or contractual at the
source; Luxembourg's published archives are expired; and community rebuilds
on third-party hosts (a Katowice GitHub proxy, a Bydgoszcz community build,
Estonian Remix mirrors) were refused on identity grounds even where their
stated licenses were open. Norway's national aggregate stays size-deferred.

A same-day Nordic-Baltic wave adds eleven reviewed records: eight in Finland
(HSL and seven Waltti city feeds, all CC BY 4.0 per the providers' own
open-data statements), Estonia's national register aggregate, Latvia's ATD
national aggregate (CC0 per data.gov.lv), and Vilnius (JUDU's published
data-use terms). That brings the total to 74 reviewed feed records across 15
countries, with the United Kingdom the largest country at about 31%. Candidates
whose reuse terms could not be verified on a live provider or official-portal
page (Rīgas Satiksme, Kaunas, Klaipėda, and ELRON) stayed out, and Norway's
national aggregate remains deferred under the archive guard described below.
The 250-record threshold still fails by design.

A same-day Central Europe wave adds ten more reviewed records: Wiener Linien
(CC BY 4.0 on data.gv.at), the Swiss national timetable under the ODMCH
terms, PID Prague and IDS JMK (CC-BY per the providers' and Brno's portals),
the two gtfs.de national aggregates plus VRN and VRS under their stated
German data licences, and Poznań and Szczecin under ZTM's developer terms
and CC0. That brings the cohort to 84 reviewed feed records across 17
countries, with the United Kingdom the largest country at about 27%.

This wave did not relax ingestion limits to make the map look fuller. The
Swiss fixed-route national archive expands to about 3.0 GB and exceeds the
pipeline's 2 GiB safety cap, so the cohort uses the much smaller official SKI+
GTFS-Flex collection instead. The public Vienna archive was also deferred after
`stop_times.txt` expanded to about 609 MB, above the 512 MiB single-entry cap;
the bounded wave uses the preflighted Transtejo ferry feed instead. Norway's
national aggregate was deferred at about 588 MB compressed. Large feeds need a
separately designed shard, not an exception to the archive guard.

The threshold is intentionally below the 406 license-linked discovery rows so
manual review can reject stale, duplicate, restricted, or misidentified feeds.
It is intentionally above a canary cohort so a consumer can use the result for
a bounded product decision.

### Executable result on 2026-07-17

The published gate document reported `not_ready` with seven of eight criteria
met. The reviewed cohort held 15 of the 250 required feed records across 12 of
12 required countries, with France the largest country at 20.0% (3 of 15)
against the 40% ceiling. Fresh scorecards covered 100% of the cohort against
the 95% floor. Translation measurement, portable location, and identity review
each covered the full cohort, the feature finder disclosed its denominator,
and the exception list was empty. The record count is the only open criterion.

Two changes landed the same day (UTC). The executable gate surface merged
first (PR #116): the document at `/api/v1/global-coverage.json`, its JSON
schema, the status page section, and the finder's regional denominator.
Country program pages for every non-US registry country followed (PR #121).

That published result predates the depth waves described above. The
configured cohort now holds 63 reviewed records across 13 countries; the
published gate document reports the new arithmetic after the next scored
render, and the record count stays the only open criterion.

### Fifth European wave on 2026-07-18

A fifth wave led with non-United-Kingdom sources and added 16 reviewed feed
records, moving the European cohort from 149 to 165 records across 18
countries. It opened Slovenia as the eighteenth country with Ljubljana's LPP
feed, published on the national OPSI portal under CC BY 4.0. The rest is depth
in already-listed countries: nine in Germany (six Baden-Württemberg
association feeds and the Calw district feed on NVBW's Datenlizenz Deutschland
portal, VGN Nürnberg under CC BY-SA 3.0 as Bavaria's first record, AVV Aachen
under CC0, and the gtfs.de long-distance rail aggregate under CC BY 4.0), two
in France under the Licence Ouverte (SEMO in Normandie and the Zoom network in
Chalon-sur-Saône), two in Italy under CC BY 3.0 Italia (TPER's Bologna and
Ferrara networks, opening Emilia-Romagna), one in Spain (CRTM's interurban
network under the consortium licence), and one in Portugal under CC0 (STCP in
Porto). Every record carried a live license check, a mechanical download and
current-calendar preflight, and an ISO 3166-2 subdivision review.

The wave kept the balance criterion comfortable: the United Kingdom is now
20.6% of the cohort (34 of 165), well under the 40% ceiling, and Germany the
second-largest at 22. The 250-record threshold stays the only open criterion,
and it still fails by design.

## Delivery sequence

### Now: consumer decision support

- Measure `translations.txt` and expose languages through the artifact,
  adoption rollup, feature API, finder, and CSV.
- Put the finder in primary navigation and focus it on arrival.
- State the U.S.-heavy denominator beside the filters.
- Keep missing historical translation measurements unknown.

### Next: curated European GTFS cohort

- Build depth next within Spain, France, Sweden, the United Kingdom, Germany,
  and Italy because the discovery audit provides the largest review queues.
  Existing country canaries do not waive the license and identity gates for
  another feed.
- Cross-check provider pages and National Access Points, retain source and
  attribution evidence, and reject entries whose reuse terms remain unclear.
- Add country waves only after the existing worldwide canary checklist in
  [ADR 0026](decisions/0026-internationalization.md) passes.
- Publish progress against the beta gate, not a launch date.

The first ferry-focused wave added four European records after direct source,
calendar, identity, route-type, and reuse review, plus one Australian ferry
record. It is a product and ingestion canary, not the European beta. The wave
also documented four exclusions where access, mode, or freshness did not pass.

The nine-record breadth wave then added one reviewed record per new country.
Several are regional or national multi-operator aggregates, so they remain one
feed record each and never inflate an agency count. The next expansion decision
is depth and consumer usefulness, not another race to add flags.

### Later: full interface localization

- Externalize the interactive app's English strings into the existing reviewed
  catalog contract.
- Add a pseudolocale expansion pass and a full right-to-left browser pass before
  adding a production language.
- Require a named language steward and human review for public civic copy. Do
  not publish machine-translated scorecard advice as reviewed guidance.
- Keep locale quality, source coverage, and GTFS translation availability as
  separate denominators.

The engineering half of this gate shipped on 2026-07-17 (ADR 0038): the app
now has a reviewed English catalog (`locales/app.en.json`) rendered into a
generated strings module, a derived `en-XA` pseudolocale served behind an
explicit `?l10n=en-XA` preview request, browser tests that prove the preview
expands catalog strings without layout overflow and that an unsupported tag
fails closed to English, a right-to-left check on a rendered route, and two
ratchets that stop new hardcoded copy and new directional CSS from
accumulating. The steward requirement is unchanged: no production language
exists, and none may ship without named human review.

### Separate decision: NeTEx

Evaluate NeTEx-to-GTFS normalization only with a named European partner and a
bounded national profile. The evaluation must cover source fidelity, profile
variance, validator responsibility, attribution, runtime cost, and how a
converted feed is labeled. Until then, NeTEx-only datasets are out of scope.

## Beyond the Europe beta

Passing the European gate would not make the service global. The remaining
tracks each carry their own gate, and none of them opens as a side effect of
registry growth.

**Global South pilot.** [ADR 0028](decisions/0028-global-south-pilot.md)
bounds this to a labelled demonstrator of three to five agencies. Onboarding
any new country waits for confirmed data licensing and operator or community
consent. A partnership starts this track; registry additions alone do not.

**Per-country equity modules.** The US overlay is state-level ACS data and the
Canada overlay is the Statistics Canada CIMD
([ADR 0027](decisions/0027-canada-equity-cimd.md)). Each required its own data
sourcing, small-area geography, and presentation review. An equity module for
a new country is an engineering effort against a reviewed national data
source, not a configuration change.

**Interface localization.** Full-interface translation stays steward-gated
under [ADR 0026](decisions/0026-internationalization.md): a named language
steward and human review precede any production locale. The reviewed `/es/`
lookup shows the required scope; it is not a shortcut around it.

**NeTEx.** Out of scope, as decided above. NeTEx-only datasets wait for a
named European partner and a bounded national-profile evaluation.

**Operating cost at 2x and 5x feed count.** Actions minutes are free on a
public repository, so CI compute does not gate growth. The real cost lines are
storage. The tracked `data/artifacts` tree is about 500 MB at 1,163 configured
feed records and the repository's git history is about 1 GB. Since the
fail-closed publishing change (#102), run outputs go to S3 and Pages rather
than back into git, so the committed tree grows with curation and cutover
commits, not with every run. The S3 mirror holds every dated artifact under a
lifecycle expiration policy and is the durable record. At double the registry,
roughly 2,300 records, a fresh checkout carries about 1 GB of committed
artifacts. At five times, roughly 5,800 records, the committed bootstrap copy
needs a redesign before the registry grows further: artifact offload, partial
clone, or a thinner committed set. The S3 and CDN lines scale roughly linearly
with feed count.

## Evidence to collect

This plan needs more than the initial Slack response. Before changing the beta
gate, interview at least five consumer organizations operating in more than one
European country. Record the features they need, the minimum useful geographic
coverage, their treatment of regional bundles, and whether translation presence
or translation completeness drives the decision. Report counts and dissent;
do not convert one participant's blocker into a universal requirement.
