# Global expansion and European GTFS beta gate

Last updated: 2026-07-17

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

The configured registry snapshot after the reviewed breadth wave contains
1,163 feed records: 1,139 in the United States, three in Canada, two in
Australia, three in France, two in Italy, and one each in Belgium, Switzerland,
Denmark, Estonia, Spain, Finland, Great Britain, Ireland, Japan, Malaysia, New
Zealand, Poland, Portugal, and Uruguay. The public scored count is a separate,
smaller number reported by the status API; configured and published feed records
are not interchangeable.

The 15 records whose primary catalog location is in 12 European countries are
reviewed canaries. They cover bus, tram, metro, ferry, national multimodal, and
GTFS-Flex demand-responsive service. The country and mode controls prove that
the data model and interface can carry worldwide locations; they are not
country or regional samples.

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
Ireland, and Italy. The next bounded wave adds nine records across Belgium,
Switzerland, Denmark, Estonia, Spain, Finland, Great Britain, Poland, and
Portugal. That produces 15 reviewed feed records across 12 countries, with France
the largest country at 20%. Country breadth and balance therefore pass, while
the 250-record threshold still fails by design. Freshness, translation,
location, and identity remain executable per-record gates rather than claims
inferred from the registry. The source rows are public so a consumer can audit
what “reviewed” means.

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

Two changes landed the same day. The executable gate surface merged in the
morning (PR #116): the document at `/api/v1/global-coverage.json`, its JSON
schema, the status page section, and the finder's regional denominator.
Country program pages for every non-US registry country followed in the
afternoon (PR #121).

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
