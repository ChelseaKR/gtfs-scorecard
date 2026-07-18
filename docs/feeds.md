# Hand-verified feed references

Source endpoints, licenses, and polling etiquette for the original Yolo County
pilots and the first worldwide canaries. This page is the hand-verified
reference; the full registry has more than 1,300 feed records, still mostly in
the United States and Canada, and lives in the explicit shards listed by
`registry/index.yaml`, with the discovery process documented in
`docs/feed-discovery.md`. Every URL below was verified with a live request on
the date stamped at the bottom of this page.

The next European cohort is not selected by feed count alone. Its current
discovery audit, source hierarchy, license-review rule, and public beta gate are
in [global-expansion.md](global-expansion.md). The reviewed European records
remain canaries until that gate passes.

## First worldwide canaries

These feeds are official, openly reusable, and deliberately span three
continents. They exercise the same worldwide GTFS quality core as every other
agency. Country-specific policy fields do not apply unless a separate regional
module says so.

### Nasu Town Community Bus (Japan)

| | |
|---|---|
| GTFS Schedule | `https://api.gtfs-data.jp/v2/organizations/nasutown/feeds/nasutown/files/feed.zip?rid=current` |
| Location | Japan (`JP`), Tochigi (`JP-09`) |
| Status | Verified 200 and ZIP signature; 81 KB at verification time |
| License | [Nasu Town publishes the dataset under CC BY 4.0](https://www.town.nasu.lg.jp/0085/info-0000001422-1.html). |
| Update cadence | No fixed cadence stated. The verified release was published 2026-03-31 and covers service from 2026-04-01 through 2027-03-31. |

This is the highest-value language and scale canary: an official Japanese-name
feed for a small rural operator, close to the scorecard's primary audience.

### Adelaide Metro (Australia)

| | |
|---|---|
| GTFS Schedule | `https://gtfs.adelaidemetro.com.au/v1/static/latest/google_transit.zip` |
| Location | Australia (`AU`), South Australia (`AU-SA`) |
| Status | Verified 200 and ZIP signature; 18.9 MB at verification time |
| License | [Creative Commons Attribution](https://data.sa.gov.au/data/dataset/https-gtfs-adelaidemetro-com-au). Attribute Adelaide Metro, Department for Infrastructure and Transport, South Australia. |
| Update cadence | Daily, per the South Australian government data catalog. |

### Dublin Bus via Transport for Ireland (Ireland)

| | |
|---|---|
| GTFS Schedule | `https://www.transportforireland.ie/transitData/Data/GTFS_Dublin_Bus.zip` |
| Location | Ireland (`IE`), Dublin (`IE-D`) |
| Status | Verified 200 and ZIP signature; 18.6 MB at verification time |
| License | [National Transport Authority GTFS is CC BY 4.0](https://data.gov.ie/en_GB/dataset/nta-gtfs). |
| Update cadence | The catalog metadata is daily; operator files are replaced when timetables change. |

## Four-region worldwide cohort

These four feeds extend the canary set across Europe, Southeast Asia,
Oceania, and South America. Each comes from an official publisher under an
explicit open-data license. Their public names stay in the language used by
the operator; the scorecard does not replace those names with English ones.

### Réseau urbain l'Bus, Bernay (France)

| | |
|---|---|
| GTFS Schedule | `https://www.data.gouv.fr/api/1/datasets/r/9ffc26b2-d293-4ec5-9cf6-4690d542f019` |
| Location | France (`FR`), Normandie (`FR-NOR`) |
| Status | Verified after a redirect to the immutable ZIP; 1 route, 74 stops, and 14 trips at verification time |
| GTFS-Realtime | One combined, keyless stream for TripUpdates, VehiclePositions, and ServiceAlerts: `https://www.data.gouv.fr/api/1/datasets/r/622b4abe-e029-4a6b-bd59-ef849e9b005f` |
| License and source | [Licence Ouverte 2.0 through France's National Access Point](https://transport.data.gouv.fr/datasets/reseau-transport-urbain-de-bernay), published by Intercom Bernay Terres de Normandie |
| Update cadence | No fixed schedule is stated. The verified timetable covers service through 2026-12-31; the scorecard checks the canonical resource no more than daily. |

The realtime catalog declares all three GTFS-Realtime entity kinds at the
same URL. An off-hours verification sample contained alerts, so an empty
trip or vehicle sample is not treated as proof that those entity kinds have
stopped publishing.

### BAS.MY Kangar (Malaysia)

| | |
|---|---|
| GTFS Schedule | `https://api.data.gov.my/gtfs-static/mybas-kangar` |
| Location | Malaysia (`MY`), Perlis (`MY-09`) |
| Status | Verified after redirects to the current ZIP; 9 routes, 455 stops, and 344 trips at verification time |
| GTFS-Realtime | Keyless VehiclePositions: `https://api.data.gov.my/gtfs-realtime/vehicle-position/mybas-kangar` |
| License | [CC BY 4.0 applies to data on Malaysia's official open-data portal](https://data.gov.my/odin-self-assessment). |
| Operator source | [BAS.MY Kangar](https://bas.my/basmykangar.php) |
| Update cadence | No fixed schedule is stated. The stable API URL resolves to the current published object; the scorecard checks it no more than daily. The verified calendar covers service through 2026-12-31. |

The official operator describes the network as serving Perlis, so `MY-09`
is the primary subdivision. Some routes extend into Kedah. This is more
specific than the Mobility Database's current “Kedah” label and does not
imply that every stop lies within Perlis.

### Orbus, Otago (New Zealand)

| | |
|---|---|
| GTFS Schedule | `https://www.orc.govt.nz/transit/google_transit.zip` |
| Location | New Zealand (`NZ`), Otago (`NZ-OTA`) |
| Status | Verified after a redirect to the current dated ZIP; 80 routes, 908 stops, and 2,577 trips at verification time |
| Realtime status | [Orbus offers live bus tracking](https://www.orc.govt.nz/orbus/travel-with-us/using-the-bus/track-your-bus-in-real-time/), but no keyless public GTFS-Realtime endpoint was verified. The scorecard states this neutrally and does not deduct points. |
| License and source | [CC BY 4.0 under Otago Regional Council's GTFS terms](https://www.orc.govt.nz/privacy-and-tscs/) |
| Update cadence | No fixed release schedule is stated. The canonical URL redirects to the current dated release; the verified base calendar runs through 2027-12-31 and added service in `calendar_dates.txt` runs through 2028-01-27. |

### Servicios metropolitanos de ómnibus (Uruguay)

| | |
|---|---|
| GTFS Schedule | `https://catalogodatos.gub.uy/dataset/1d50ccf7-121d-48a7-951e-28a02858d24e/resource/9f44b654-751a-42a4-a481-af91b7c9a2e4/download` |
| Primary location | Uruguay (`UY`), Montevideo (`UY-MO`) |
| Status | Verified as a direct ZIP; 8 operators, 371 routes, 7,190 stops, and 7,549 trips at verification time |
| Realtime status | No public GTFS-Realtime endpoint was found. |
| License | Licencia de Datos Abiertos de Uruguay |
| Official sources | [MTOP dataset](https://catalogodatos.gub.uy/es/dataset/ministerio-de-transporte-y-obras-publicas-horarios-de-omnibus-en-lineas-interdepartamentales) and [GTFS resource record](https://catalogodatos.gub.uy/dataset/ministerio-de-transporte-y-obras-publicas-horarios-de-omnibus-en-lineas-interdepartamentales/resource/9f44b654-751a-42a4-a481-af91b7c9a2e4) |
| Update cadence | The official catalog states a semiannual update frequency. The filename-independent resource URL is the catalog's current download; the verified calendar covers service through 2026-12-25. |

This is a multi-operator metropolitan and interdepartmental feed. Montevideo
is its primary catalog location, not a boundary around its complete service
area. It is scored last and in isolation during activation because its
roughly 795,000 stop times make it the largest and most structurally varied
member of this cohort.

## Reviewed European breadth wave

These nine records add one evidence-reviewed feed in each new country. They
were selected for geographic and modal breadth, not to make a representative
European sample. Provider source, reuse terms, current download, service
calendar, mode, and feed identity were checked on 2026-07-16. A regional or
national aggregate still counts as one feed record.

- **Transtejo Soflusa, Portugal (`PT-11`)** publishes five ferry routes across
  the Tagus through one TTSL agency row. Portugal's
  [public-administration open-data catalog](https://dados.gov.pt/pt/organizations/transtejo-soflusa/)
  lists the Transtejo and Soflusa schedule datasets under CC0. The primary
  Lisboa subdivision is not a service boundary because the routes connect both
  sides of the river, including terminals in Setúbal.

- **Transport en Commun, Belgium (`BE-WAL`)** is one Wallonia aggregate with
  five TEC agency rows, tram, metro, bus, and some cross-border stops. Belgium's
  [National Access Point resource](https://transportdata.be/dataset/tec-gtfs/resource/ecd983c4-e48c-4078-85af-835640881dba)
  publishes it under CC0 1.0 Universal; the scorecard still credits SRWT/TEC.

- **Swiss demand-responsive services (`CH`)** is the official SKI+ GTFS-Flex
  collection: five operator rows, 12 demand-responsive bus routes, booking
  rules, and service through 2026-12-12. The
  [official dataset](https://data.opentransportdata.swiss/en/dataset/gtfsflex)
  and [ODMCH terms](https://opentransportdata.swiss/en/terms-of-use/) require
  source citation and current raw data. It is distinct from the fixed-route
  national archive, whose roughly 3.0 GB expanded size exceeds the pipeline's
  2 GiB security limit.

- **Morebus, United Kingdom (`GB-BCP`)** is a bus feed with four GoSouthCoast
  agency rows and service beyond its primary Bournemouth, Christchurch and
  Poole location. The operator's
  [open-data page](https://www.morebus.co.uk/open-data) publishes it under the
  [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- **Zarząd Transportu Miejskiego w Gdańsku, Poland (`PL-22`)** publishes a
  rolling, roughly 14-day bus and tram export through the
  [official TRISTAR dataset](https://ckan.multimediagdansk.pl/pl/dataset/tristar).
  Its [provider terms](https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/09cafa1b-604b-4408-ac48-5720319b72b7/download/regulamin-korzystania-z-danych.pdf)
  require source and date attribution. The catalog's conflicting CC0 label was
  not used as reuse evidence.

- **Tallinn public transport, Estonia (`EE-37`)** publishes bus and tram service
  through the reviewed TLT feed. Estonia's
  [public-transport open-data page](https://peatus.ee/content/Veebilehest%20ja%20%C3%BChistranspordi%20avaandmetest)
  permits reuse with the data origin cited and requires rider-facing data to be
  no more than seven days old. Alternate Tallinn exports are variants, not
  additional coverage.

- **Metro Bilbao, Spain (`ES-BI`)** publishes its subway timetable through the
  [official Bizkaia catalog](https://data.ctb.eus/en/dataset/horario-metro-bilbao)
  under [CC BY 4.0 terms](https://data.ctb.eus/en/pages/legal-notice). Active
  Mobility Database record 3052 replaces deprecated records 2683 and 1200;
  those predecessors are not separate feeds.

- **Waltti Kotka, Finland (`FI-09`)** is one regional bus feed with five
  operator rows and 151 routes. The
  [Waltti open-data terms](https://opendata.waltti.fi/docs) apply CC BY 4.0 and
  require source credit, a licence link, and disclosure of changes.

- **Rejseplanen, Denmark (`DK`)** is one national aggregate with 26 agency rows
  and bus, flex-bus, rail, metro, tram, and ferry service. The
  [official feed page](https://labs.rejseplanen.dk/hc/en-us/articles/21639730766877-Om-GTFS-Schedule-Static)
  and [Labs terms](https://labs.rejseplanen.dk/hc/en-us/articles/21553298043165-Retningslinjer-for-Labs)
  apply CC BY 4.0. Cross-border rows remain part of this one Danish feed record;
  the current legacy download is also monitored because newer access copy
  describes a request-based process.

The wave raises the reviewed European registry cohort from six to 15 feed
records across 12 countries. It clears the country-count and concentration
checks, but it remains well below the 250-record beta gate in
[global-expansion.md](global-expansion.md).

## Reviewed European depth wave

These 27 records work the depth queues that the 2026-07-15 discovery audit
named: Spain, France, the United Kingdom, Germany, and Italy. Provider source,
reuse terms, current download, service calendar, archive size, and feed
identity were checked on 2026-07-17. Candidates were drawn from the Mobility
Database catalog, mechanically preflighted (live ZIP, required GTFS files,
size caps, calendar coverage), and then reviewed for reuse terms and identity.
More candidates were rejected than added; the rejection reasons are listed in
[global-expansion.md](global-expansion.md).

- **United Kingdom (ten records)**: Nottingham City Transport, Reading Buses,
  Brighton & Hove Buses, Oxford Bus Company, Go North East, Cardiff Bus,
  Xplore Dundee, Blackpool Transport, Unilink (Southampton), and Southern
  Vectis all publish through the Passenger open-data platform
  (data.discoverpassenger.com) under the
  [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
  Each operator page states its own copyright line; each record tracks the
  rolling `dataset/current` download, which rolls over on a short cycle.
- **Spain (seven records)**: two CRTM network feeds (Madrid city bus and Metro
  Ligero) under the [Licencia CRTM](https://www.crtm.es/licencia-de-uso),
  which permits commercial reuse and transformation with CRTM cited; EMT
  València and TUVISA Vitoria-Gasteiz under CC BY 4.0 through their city
  portals; FGC and the Puente Bizkaia transporter bridge under CC BY 4.0
  through provider portals; and the TIB Mallorca consortium feed under CC BY
  4.0. TUVISA publishes rider-facing `translations.txt`.
- **Italy (four records)**: Roma Servizi per la Mobilità (CC BY-SA through
  Rome's municipal catalog, share-alike noted), AMAT Palermo and ATM Milano
  (CC BY 4.0 through their comune portals), and Regione Calabria's CORE
  regional aggregate (CC BY 4.0 via Italy's national catalog record).
- **Germany (four records)**: the VBB Berlin-Brandenburg aggregate (CC BY
  through Berlin's open data portal), bodo Verkehrsverbund and VAG Freiburg
  (Datenlizenz Deutschland - Namensnennung 2.0, with NVBW's OpenStreetMap
  shapes credit where it applies), and KVV Karlsruhe (CC0). Germany is a new
  registry country in this wave.
- **France (two records)**: Transports Bordeaux Métropole with its three
  public realtime feeds (Licence Ouverte 1.0, with the publisher's public
  open-data key embedded in the National Access Point URLs), and Car Jaune,
  the interurban network of La Réunion (Licence Ouverte 2.0, with one
  combined realtime stream).

## Second reviewed European depth wave

These 21 records continue the same queues, checked the same way on
2026-07-17. Rejection reasons are recorded in
[global-expansion.md](global-expansion.md).

- **United Kingdom (twelve records)**: Borders Buses, Carousel Buses, East
  Yorkshire, Go Cornwall Bus, Intalink, McGill's Buses, Metrobus, Newport
  Bus, Plymouth Citybus, Transdev Blazefield, Warrington's Own Buses, and
  Bluestar, all on the Passenger platform under the Open Government Licence
  v3.0 with per-operator copyright lines verified. The United Kingdom now sits at
  36.5% of the cohort, close to the 40% ceiling, so later waves lead
  elsewhere.
- **Germany (five records)**: the DING (Donau-Iller), OstalbMobil, VGF
  Freudenstadt, TGO Ortenau, and Kreisverkehr Schwäbisch-Hall network feeds
  from NVBW's open data portal under Datenlizenz Deutschland - Namensnennung
  2.0, with the network identities confirmed against the portal's own
  listing. Each association feed counts as one feed record.
- **France (three records)**: the Réseau Léo Auxerrois bus network and the
  Cap Cotentin network with its combined realtime stream (Licence Ouverte
  2.0), and the Aléop Yeu-Continent island ferry published by the Région des
  Pays de la Loire.
- **Italy (one record)**: Trenitalia's regional rail resource within Regione
  Toscana's multi-file open dataset (Creative Commons Attribution), named as
  one resource rather than the whole regional dataset.

## Third reviewed European depth wave

These 75 records came from working every remaining non-Swedish queue in
parallel on 2026-07-17: mechanical preflight of 223 candidates ran alongside
per-country reuse-terms review, and only the intersection was onboarded.
Rejection reasons are recorded in
[global-expansion.md](global-expansion.md).

- **France (twenty records)**: Licence Ouverte networks across ten regions,
  from CTS Strasbourg and Stan Nancy to Lignes d'Azur Nice, Réseau Mistral
  Toulon, the fourteen-network Aix-Marseille-Provence referential, and
  Eurostar's international rail feed. The review resolved current canonical
  URLs where the catalog held stale ones; seventeen ODbL datasets and the
  custom-licensed Île-de-France Mobilités aggregate were rejected.
- **Italy (twelve records)**: Trenord, ANM Napoli, ACTV Venezia's road and
  vaporetto networks, Trentino Trasporti, SGM Lecce, Toremar's island
  ferries, AMT Genova through Genoa's municipal record, and four Sardinian
  records tied to the regional CC BY 4.0 catalog.
- **United Kingdom (eleven records)**: further Passenger-platform operators
  from Borders Buses to Thames Valley Buses, each page and copyright line
  verified.
- **Finland (twelve records)**: the Waltti city networks plus Föli Turku and
  Tampere, all CC BY 4.0; identity review corrected one mislabeled regional
  package (Lahti, not Salo) and one wrong region code.
- **Spain (nine records) and Portugal (one)**: TITSA Tenerife, EMT Madrid,
  both TRAM Barcelona concessions, Metro de Málaga through the National
  Access Point's public record, Bizkaibus, EMT Fuenlabrada, the Generalitat
  de Catalunya interurban aggregate, and Guimabus in Portugal.
- **Ireland (five records)**: the National Transport Authority's per-operator
  CC BY 4.0 files for Bus Éireann, Irish Rail, Luas, Go-Ahead Ireland, and
  Aircoach; the national aggregate is deliberately not listed because it
  duplicates them.
- **Poland (four records) and Czechia (two)**: Szczecin (CC0), Poznań, SKM
  Trójmiasto, ZKM Gdynia, and the country's first Czech records, PID Prague
  and IDS JMK Brno.

## Fifth reviewed European wave

This wave on 2026-07-18 led with non-United-Kingdom sources and added 16
records, taking the reviewed European cohort from 149 to 165 across 18
countries. No United Kingdom feed was added. Each candidate passed a live
license check, a mechanical download and current-calendar preflight, a size
check under the archive cap, and an ISO 3166-2 subdivision review. Rejection
reasons are also summarized in [global-expansion.md](global-expansion.md).

- **Germany (nine records)**: six Baden-Württemberg association feeds on
  NVBW's Datenlizenz Deutschland - Namensnennung 2.0 portal (naldo, VPE, HNV,
  RVF, VHB, and the Landkreis Calw VGC feed), VGN Nürnberg under CC BY-SA 3.0
  as Bavaria's first record, AVV Aachen under CC0, and the gtfs.de
  long-distance rail aggregate under CC BY 4.0.
- **Slovenia (one record)**: LPP Ljubljana, the eighteenth country, published
  on the national OPSI portal under CC BY 4.0.
- **France (two records)**: SEMO in Normandie and the Zoom network in
  Chalon-sur-Saône, both Licence Ouverte 2.0 through the National Access Point.
- **Italy (two records)**: TPER's Bologna and Ferrara bus networks under CC BY
  3.0 Italia, opening Emilia-Romagna. Their download pins a dated version, so a
  curator refreshes the version parameter when TPER publishes a new archive.
- **Spain (one record)**: CRTM's interurban regional bus network under the
  consortium licence, a distinct feed from the tracked city bus and light rail.
- **Portugal (one record)**: STCP Porto under CC0, from the portal's current
  rolling resource rather than its dated snapshots.

Rejections outnumbered additions again, and the reasons are the review:

- **No explicit open license**: OASA Athens (data.gov.gr provides the data "as
  is" with no named license), HŽ Passenger Transport (data.gov.hr states no
  license exists), Sofia Traffic and BKK Budapest (custom municipal reuse
  rules, no named open license), and TPBI Bucharest, Carris Lisbon, and Metro
  Transportes do Sul (no license text on the portal).
- **ODbL or special conditions**: numerous French datasets on the National
  Access Point, including SURF Fougères, Proxim iTi, INTERCOM Sens, Brévibus,
  Tisséo Toulouse, and Île-de-France Mobilités.
- **Community rebuild or aggregator host**: the mkuran.pl-hosted Polish city
  feeds (Warszawa WTP, Toruń, Radom, and others) and the stops.lt Lithuanian
  city feeds, refused on identity even where the stated license was open.
- **Expired calendar**: Luxembourg's national aggregate (service ended six
  days before review), Navarra and Extremadura in Spain, and the three
  Sardinian ferry feeds.
- **Unreachable or access-blocked from the pipeline network**: Generalitat
  Valenciana intercity (DNS failure), ZTP Kraków and Burgos (portals block
  automated access to their terms), and ATP Nuoro and ATP Sassari (the
  operator hosts return an HTML page, not the archive).
- **Terms unverifiable**: the Slovak ŽSR national rail feed, whose license
  the national catalog serves only through a script-rendered page, stayed out
  to fail closed.

## Oceania coverage wave

The first coverage wave outside Europe and North America, curated under the
[global coverage roadmap](global-coverage-roadmap.md). Australia and New Zealand
publish official government GTFS through mature open-data programs, so these are
the same kind of record as an official European feed and raise no local-steward
concern. Source, reuse terms, current download, and identity were checked on
2026-07-17. Eleven records were added:

- **Queensland (six records)**: the TransLink South East Queensland network
  (Brisbane) and the Sunbus Cairns, Sunbus Townsville, Bus Queensland
  Toowoomba, Mackay, and Maryborough-Hervey Bay qconnect regional networks, all
  CC BY 4.0 as © State of Queensland (Department of Transport and Main Roads).
- **Western Australia (one record)**: Transperth (Perth), under the Public
  Transport Authority's custom Spatial Data Access terms — an attribution-only
  grant, noted as a custom government license rather than Creative Commons.
- **Northern Territory (two records)**: the Darwin and Alice Springs urban bus
  networks, CC BY 4.0 as © State of the Northern Territory.
- **New Zealand (two records)**: Auckland Transport and Baybus (Bay of Plenty),
  both CC BY 4.0 through their official open-data pages.

Deferred with recorded reasons: the Sydney (Transport for NSW) and Melbourne
(Public Transport Victoria) bundles both exceed the 256 MiB download cap and
wait on the large-feed shard; Transport for NSW also gates its bulk download
behind a registered account. The ACT (Transport Canberra) host returns HTTP 403
to the pipeline. Tasmania's per-city Metro feeds have moved to a single
Department of State Growth feed whose license page was unreachable and appears
to add a share-alike term, and Metlink Wellington publishes no stated reuse
license. Each is revisited when its blocker clears.

## Latin America and Asia-Pacific official wave

The next coverage waves under the
[global coverage roadmap](global-coverage-roadmap.md), Phases 2 and 3: official,
first-party, openly licensed feeds outside Europe, North America, and Oceania.
Source, reuse terms, current download, and identity were checked on 2026-07-17
against a parallel per-region license review of every candidate the Mobility
Database lists for these regions. Nine records were added:

- **Brazil (three records)**: Belo Horizonte's conventional and supplementary
  networks (BHTRANS) and Rio de Janeiro's municipal network (SMTR via data.rio),
  all CC BY through their municipal open-data portals.
- **Japan (three records)**: the Toei bus and subway networks (Tokyo
  Metropolitan Bureau of Transportation, CC BY 4.0 through the ODPT open-data
  center) and Donan Bus (southern Hokkaido, CC BY through the Hokkaido open-data
  platform), the same GTFS-JP open-data path as the existing Nasu Town canary.
- **Turkey (two records)**: the İzmir metro and tram networks, CC BY 4.0 under
  the İzmir Metropolitan Municipality open-data license.
- **Thailand (one record)**: the OTP Namtang multimodal feed for the Bangkok
  metropolitan network, CC BY 4.0 from the Office of Transport and Traffic
  Policy and Planning.

The review rejected or deferred far more than it added, and the reasons are the
point. Deferred on ingestion or freshness: Israel's national feed (a single
table exceeds the 512 MiB entry cap, so it joins the large-feed shard queue),
Sydney and Melbourne (over the download cap), and several stale or expired
official feeds (İstanbul İETT marked "will not be updated", İzmir IZBAN,
Fortaleza, Porto Alegre). Deferred on unstable URLs: Santiago's DTPM feed (its
stable alias serves a 2020 dataset while the current feed sits at a rotating
dated URL) and Bogotá's SIMUR feed (a rotating dated URL); both are
license-approved and wait on canonical-URL resolution. Rejected on access or
license: São Paulo and Singapore's LTA (registration walls), Flixbus and Cairo's
Transport for Cairo (private operators, non-commercial or partner-only terms),
and many feeds hosted on personal repositories or the defunct transitfeeds
aggregator rather than an official source.

The African candidates were held back entirely, as the roadmap's
partnership-gated phase requires. Every African GTFS the catalog lists is
community- or survey-produced — the Digital Transport for Africa repositories
for Addis Ababa, Kumasi, Douala, and Abidjan, and Transport for Cairo's
paratransit mapping — and this project does not curate community-mapped transit
data from a catalog. Those feeds wait for a named local steward.

## Transitland-sourced wave

The first wave curated from the second discovery source. The Transitland Atlas
(`scorecard sync --source transitland`) reads a keyless, CC-BY DMFR registry
that is strongest where the Mobility Database is thin, so it is the way to reach
coverage the catalog does not carry
([global coverage roadmap](global-coverage-roadmap.md), "alternative-catalog
ingestion"). The DMFR carries no ISO country, so each candidate's country,
subdivision, license, and identity were established by hand and verified against
both the operator's publication venue and the Mobility Database catalog on
2026-07-18. Only feeds the Mobility Database does not already carry were kept, so
the wave proves the source surfaces genuinely new coverage rather than
re-listing catalog feeds.

Five records were added, all official Japanese municipal feeds published as
GTFS-JP open data through the GTFS Data Repository ([gtfs-data.jp](https://gtfs-data.jp/),
operated by AIGID under the national "standard bus information format" program),
the same open-data path as the existing Nasu Town canary. Each download was
confirmed live, valid, and carrying a current service calendar; none appears in
the Mobility Database:

- **Toki City Community Bus (土岐市民バス)** — Gifu (`JP-21`), CC BY 4.0.
- **Higashine City Bus (東根市営バス)** — Yamagata (`JP-06`), CC BY 4.0.
- **Yonezawa City Bus (米沢市営バス)** — Yamagata (`JP-06`), CC BY 4.0.
- **Uozu Community Bus (魚津市民バス)** — Toyama (`JP-16`), CC0 1.0.
- **Naruto City Ferry (鳴門市営渡船)** — Tokushima (`JP-36`), CC BY 4.0.

The review rejected more than it kept, and the rejections are the point:

- **Already in the Mobility Database (not new coverage):** Mexico City SEMOVI,
  Santiago DTPM (Red Metropolitana de Movilidad), Bogotá Transmilenio/SIMUR
  (the proposed URL matched a catalog row and served a stale 2024 dataset), and
  Kochi Metro. These are official and open, but the catalog already carries the
  operator, so curating them would not demonstrate new coverage.
- **Not a current, valid feed:** Buenos Aires Subte (SBASE) returned a
  single-file archive with no GTFS tables — the portal shows its GTFS "under
  revision" — and Porto Alegre's EPTC feed was a valid archive whose service had
  expired in December 2025. Both fail the current-download gate.
- **No open license:** Puerto Rico's ATI (Autoridad de Transporte Integrado)
  publishes GTFS but under custom terms that reserve rights to the agencies and
  restrict reuse, not a Creative Commons or named open government license.
- **Community- or aggregator-hosted:** the African DMFR feeds (Abidjan, Accra,
  Douala, Nairobi minibus mapping, Cairo) are Digital Transport for Africa and
  university/community survey data under ODbL and stay held for the roadmap's
  partnership-gated phase; several Japanese city feeds were reachable only
  through third-party aggregator hosts (opentrans.it, busmaps.jp) rather than a
  first-party or national-portal source.

## Untracked US small-agency review (2026-07-18)

A short pass over untracked US feeds that were listed as open and active in the
Mobility Database catalog, prioritizing California. Each candidate was
mechanically preflighted: the source zip was downloaded, confirmed to be valid
GTFS with a current (non-expired) service calendar, and the archive deleted; the
subdivision was normalized to its ISO 3166-2 code; and the reuse license was
reviewed at the publisher before any approved reuse_evidence record was written.
The gate was fail-closed — a candidate had to show both a live current source and
a confirmable open license to be added. Of the eight California candidates only
one cleared it.

One record was added:

- **South County Transit Link (SCT/Link)** — California (`US-CA`), mdb 2203. The
  Galt-to-Sacramento service, hosted by Sacramento Regional Transit District
  (SacRT) at `iportal.sacrt.com`. The catalog's `direct_download` pointed at a
  stale path (`.../gtfs/SCTLink/southcountytransitlink-ca-us.zip`, 404); the live
  canonical source is `https://iportal.sacrt.com/GTFS/SCTLink/google_transit.zip`,
  verified as valid GTFS with service through 2026-12-31. SacRT's transit data
  portal (`sacrt.com/transit-data-portal`) grants non-exclusive rights to use,
  reproduce, and redistribute the data, reviewed for the reuse_evidence block. It
  is a second, agency-direct feed record for a service already carried through a
  Trillium mirror (`south-county-transit-link`, mdb 817).

Seven candidates were dropped, and the reasons are the point:

- **Cal-ITP host decommissioned, feed long expired:** Arvin Transit (mdb 2233),
  Camarillo Area Transit (2234), San Juan Capistrano Free Weekend Trolley (2235),
  Taft Area Transit (2236), and West Berkeley Shuttle (2238) were all given as
  `gtfs.calitp.org/production/*GTFS.zip`. That host now 301-redirects every path
  to the Caltrans DDS index (`gtfs.dds.dot.ca.gov`), the same migration already
  recorded for other California feeds in this repo. Only Arvin survived the
  migration to the DDS index, and its DDS copy has expired (service ended
  2025-05-31). The Mobility Database `latest` mirrors confirm abandonment: Arvin
  ends 2025-05-31, and Camarillo, San Juan Capistrano, Taft, and West Berkeley
  are frozen at 2021–2022 calendars. All five agencies remain carried through
  their live Trillium mirrors, so no coverage is lost.
- **Source URL unreachable, no open license:** Baldwin Park Transit (mdb 2247).
  Its only published source, `baldwinpark.tectransit.com`, no longer resolves
  (NXDOMAIN); Transitland reports a fetch error on the same URL, and the city
  page states no data license. The MDB `latest` mirror still shows a 2026
  calendar from the last successful crawl, but a dead source cannot be fetched
  daily. The agency is already carried through a Trillium mirror
  (`baldwin-park-transit`, mdb 219).
- **Cannot confirm a live feed:** Glendale Beeline (mdb 3177). The city host
  (`glendaleca.gov/home/showdocument?id=29549`) returns HTTP 403 to every
  automated client, and no MDB `latest` mirror is archived, so the source could
  not be verified. Glendale Beeline is already carried through a transitfeeds
  mirror (`glendale-beeline`, mdb 1280).

The optional other-state candidates (one each in Colorado, Idaho, Georgia,
Hawaii, and Washington) were not pursued in this pass: no source URLs were on
hand and the review deliberately kept its scope to the named California list.
## Japan gtfs-data.jp wave

A substantial wave curated directly from Japan's national GTFS Data Repository
([gtfs-data.jp](https://gtfs-data.jp/), operated by AIGID under the country's
"standard bus information format" / GTFS-JP program). The repository publishes a
machine-readable catalog (`https://api.gtfs-data.jp/v2/feeds`) of roughly 600
operator feeds, most of them small municipal networks, each carrying an explicit
open license, prefecture, calendar window, and stable download. The Mobility
Database barely indexes this source, so it is where new Japanese coverage
actually lives. The existing Toei, Donan Bus, Nasu Town, and the five
Transitland-sourced municipal records already draw on the same open-data path.

Eighteen records were added, one flagship feed per prefecture across eighteen
prefectures not previously represented in Japan. Every candidate was confirmed
to be an official municipality or municipal transit bureau, openly licensed
(CC BY 4.0 or CC0 1.0, read from the repository's per-feed license field), and
served as a live, non-key-gated GTFS zip. Each download was mechanically
preflighted on 2026-07-18: a valid archive with the required tables and a
service calendar current for the 2026 school year or later. None appears in the
Mobility Database.

CC BY 4.0:

- **Hachinohe City Bus (八戸市営バス)** — Aomori (`JP-02`).
- **Hanamaki City Community Bus (花巻市コミュニティバス)** — Iwate (`JP-03`).
- **Shichigahama Town Community Bus (七ヶ浜町民バス「ぐるりんこ」)** — Miyagi (`JP-04`).
- **Semboku City Bus (仙北市民バス)** — Akita (`JP-05`).
- **Ota City Bus (太田市営バス)** — Gunma (`JP-10`).
- **Kumagaya City Yuyu Bus (熊谷市ゆうゆうバス)** — Saitama (`JP-11`).
- **Yokosuka City Hamachan Bus (横須賀市ハマちゃんバス)** — Kanagawa (`JP-14`).
- **Tsubame City Community Bus (燕市コミュニティバス)** — Niigata (`JP-15`).
- **Hakusan City Community Bus (白山市コミュニティバス「めぐーる」)** — Ishikawa (`JP-17`).
- **Suwa City Karin-chan Bus (諏訪市かりんちゃんバス)** — Nagano (`JP-20`).
- **Shimada City Community Bus (島田市コミュニティバス)** — Shizuoka (`JP-22`).
- **Anjo City Ankuru Bus (安城市あんくるバス)** — Aichi (`JP-23`).
- **Tsu City Community Bus (津市コミュニティバス)** — Mie (`JP-24`).
- **Kusatsu City Mame Bus (草津市コミュニティバス「まめバス」)** — Shiga (`JP-25`).

CC0 1.0 (public domain dedication):

- **Yanaizu Town Community Bus (柳津町町民バス「ふれあい号」)** — Fukushima (`JP-07`).
- **Yuki City Loop Bus (結城市巡回バス)** — Ibaraki (`JP-08`).
- **Kimitsu City Community Bus (君津市コミュニティバス)** — Chiba (`JP-12`).
- **Kai City Bus (甲斐市民バス)** — Yamanashi (`JP-19`).

The wave was deliberately narrowed, and the choices are the point:

- **Failed preflight:** Tsukuba City's つくバス (`tsukubacity.TSUKUBUS`, Ibaraki)
  served an archive with no `trips.txt`, `stop_times.txt`, or service calendar,
  so it is not a scoreable schedule feed. Ibaraki is instead represented by Yuki
  City, whose archive preflighted cleanly. Nothing uncertain was kept.
- **Held for a cleaner license:** the catalog also lists 52 feeds under
  "CC BY 2.1 JP" and two under an unversioned "CC-BY". Only the current
  CC BY 4.0 and CC0 1.0 licenses were admitted, so every attribution string is
  exact.
- **One feed per operator:** several cities publish many route-level feeds
  (Saitama, Toyama, Nagano's 南信州 consortium, Mie's 三重交通). The wave takes a
  single representative municipal feed from a prefecture rather than stacking one
  operator's many exports, keeping the cohort broad instead of deep.
- **Already tracked:** the six gtfs-data.jp feeds already in the registry (Nasu
  Town, Higashine, Yonezawa, Uozu, Toki, Naruto) were excluded by construction.

## Transitland non-Western sweep

A second pass over the Transitland Atlas (`scorecard sync --source transitland`),
this time aimed only at the regions the Mobility Database is thinnest in and the
first Transitland wave did not cover: Latin America, non-Japan Asia-Pacific, the
Middle East, and Africa. Japan, Europe, the United States, Canada, Australia, and
New Zealand were excluded as already well covered. The Atlas carries no ISO
country, so each candidate's country was decoded from the geohash in its Onestop
id or inferred from the operator and URL, then confirmed by hand. Each survivor
was cross-checked against both the registry and the Mobility Database catalog,
and its source, license, and live download were verified on 2026-07-18. The gate
was fail-closed: only an official first-party publisher, an explicit open
license, and a live current feed that the Mobility Database does not already
carry could be added.

Six records were added, all from Malaysia's official open data platform
(`data.gov.my`, the Government of Malaysia's open data portal), which publishes
its datasets under CC BY 4.0. The Mobility Database carries only the smaller
BAS.MY town networks from this platform, so the country's two largest operators
were absent. Each download was preflighted on 2026-07-18 as a valid archive with
the GTFS core tables and a current service calendar:

- **Keretapi Tanah Melayu (KTMB)**, Malaysia national rail. The KTM Komuter
  commuter lines and intercity shuttle services across Peninsular Malaysia;
  carried as a national feed with no single subdivision.
- **Rapid KL bus network** (`MY-14`), Prasarana Malaysia Berhad. The Klang
  Valley city bus and BRT network.
- **Rapid Rail KL** (`MY-14`), Prasarana. The LRT, MRT, and monorail lines of
  the Klang Valley.
- **Rapid KL MRT feeder bus** (`MY-14`), Prasarana. The T-route feeder buses
  serving MRT and LRT stations.
- **Rapid Penang** (`MY-07`), Prasarana. The bus network on Penang island and
  the Seberang Perai mainland.
- **Rapid Kuantan** (`MY-06`), Prasarana. The Kuantan, Pahang bus network.

The sweep rejected far more than it kept, and the rejections are the point:

- **Already in the Mobility Database (not new coverage):** BAS.MY Johor Bahru /
  Causeway Link (`data.gov.my` `mybas-johor`); Subterráneos de Buenos Aires and
  Trenes Argentinos (`cdn.buenosaires.gob.ar`, mdb 6 and 647); Metrofor,
  Fortaleza (`metrofor.ce.gov.br`, mdb 2367); ESHOT İzmir bus
  (`eshot.gov.tr`, mdb 1823); TransJakarta (`gtfs.transjakarta.co.id`, mdb 1909);
  SNCFT, Tunisia national rail (`gps.sncft.com.tn`, mdb 1016); Hyderabad MMTS
  (`data.telangana.gov.in`, operator carried at mdb 921); DTPM Santiago / Red
  Metropolitana de Movilidad (mdb 987 and 2145); SIMUR Bogotá / Transmilenio
  feeders (mdb 2012, and its published file was a stale 2024 dataset); Mexico
  City's STC and SEMOVI systems (`datos.cdmx.gob.mx`, carried at mdb 1099 and
  1830); Kochi Metro / KMRL (mdb 1209); and the Jalisco and Puerto Vallarta Mi
  Transporte feeds (`datos.jalisco.gob.mx`, mdb 1925, 1926, 2034, 2366, whose
  files are also frozen at 2021 to 2022). These are official and open, but the
  catalog already carries the operator, so adding them would not demonstrate new
  coverage.
- **Official and current, but no explicit open license (fail closed):** Mwasalat
  (Oman National Transport Company) serves a live, current national feed at
  `avl.mwasalat.om`, and Mwasalat is the state transport company, but no reuse
  license is published for that feed. Córdoba, Argentina lists a "datos abiertos"
  GTFS at `gobiernoabierto.cordoba.gob.ar`, but the page states no license, its
  resource was last updated in March 2023, and no direct current download
  resolves from it. Puerto Rico's ATI publishes GTFS under custom terms that
  reserve rights rather than an open license.
- **Community- or aggregator-hosted (partnership-gated, not catalog curation):**
  the African Atlas feeds for Abidjan, Accra, Douala, and Nairobi are Digital
  Transport for Africa and university survey data on GitLab or GitHub under ODbL;
  Nicaragua's Managua and Estelí feeds come from the MapaNica community mapping
  project (`datos.mapanica.net`); Phnom Penh City Bus is served from a private
  app host (`citybus.kroma.asia`); and the Ubud shuttle, Bogor angkot, Kochi
  community transport, Patras proastiakos, and Manila feeds are personal GitHub
  or datahub.io exports. None is a first-party official source, so all wait for
  the roadmap's partnership-gated phase.
- **Not first-party, or behind a wall:** SPTrans São Paulo sits behind a
  developer registration wall; the "LTA Singapore" candidate was an app
  aggregator's mirror (`rushowl.app`), not the registration-walled official LTA
  DataMall; SãoPaulo's Transpiedade, Argentina's Mar Chiquita, and a Venezuela
  feed are private operator sites with no open license; and the Flixbus and
  Greyhound feeds are private intercity operators.
- **Technical holds:** Hong Kong's official `static.data.gov.hk` feed is open,
  but it stays a known technical canary (no ISO 3166-2 subdivision, and
  frequency-based schedules whose freshness handling is still under review, per
  the note in this file). Taiwan's TDX feed for Taipei Metro
  (`tdx.transportdata.tw`) requires OAuth client credentials, which this pipeline
  does not ingest.
## Japan gtfs-data.jp second wave

A deeper pass over the same national repository ([gtfs-data.jp](https://gtfs-data.jp/),
operated by AIGID). The first wave took one flagship feed per prefecture; this
wave goes deeper two ways: it reaches prefectures Japan did not yet have in the
registry, and it adds further municipal networks inside prefectures already
represented. A prefecture can hold several distinct city networks, and each is
one feed record. Thirty-eight records were added, lifting Japan from 27 records
across 25 prefectures to 65 across 40.

This wave also widens the license policy. The first wave admitted only CC BY 4.0
and CC0 1.0 and held back about 52 feeds under **CC BY 2.1 JP**. CC BY 2.1 JP is
a valid open Creative Commons Attribution license, the Japan jurisdiction port of
CC Attribution 2.1. It permits reuse with attribution, which is exactly what this
project needs, since it republishes metrics and attribution rather than raw data.
CC BY 2.1 JP feeds are therefore admitted here, with the exact license version
stated in each record's `license_note` and attribution. CC BY 4.0 and CC0 1.0
remain admitted. The license mix of the 38 is 30 CC BY 4.0, 5 CC0 1.0, and 3
CC BY 2.1 JP. Every candidate was confirmed to be an official municipality or a
first-party operator, and each download was mechanically preflighted on
2026-07-18: a valid archive with the GTFS core tables and a current, non-expired
service calendar, within the ingestion size caps, and absent from the Mobility
Database. The archive was deleted after each check.

Fifteen prefectures newly represented (license in parentheses):

- **Osaka (`JP-27`)**: Limon Bus, 神姫観光 (Shinki Kanko) (CC BY 4.0).
- **Hyogo (`JP-28`)**: Akashi City Tako Bus (CC BY 4.0), Kakogawa City Kako Bus
  (CC BY 2.1 JP), Takarazuka City Ran-Ran Bus (CC BY 2.1 JP).
- **Nara (`JP-29`)**: Yamatokoriyama City Community Bus and Yamatotakada City
  Kibou-go (both CC BY 4.0).
- **Wakayama (`JP-30`)**: Aridagawa Town, Kinokawa City, and Tanabe City
  community/residents buses (all CC BY 4.0).
- **Shimane (`JP-32`)**: Masuda City shared taxi (CC BY 4.0), scored on the
  Schedule rubric as a demand-response service.
- **Okayama (`JP-33`)**: Maniwa City Maniwa-kun (CC0 1.0) and Setouchi City Bus
  (CC BY 4.0).
- **Kagawa (`JP-37`)**: Mitoyo City (CC BY 4.0), Kanonji City Noriai Bus
  (CC0 1.0), Naoshima Town Bus (CC BY 4.0).
- **Kochi (`JP-39`)**: Tosaden Kotsu streetcar, Shimanto City Bus, and Sukumo
  City Yururin Bus (all CC BY 4.0).
- **Fukuoka (`JP-40`)**: Dazaifu City Mahoroba-go, Munakata City, Nogata City,
  and Tagawa City community buses (all CC BY 4.0).
- **Saga (`JP-41`)**: Imari City Imarin Bus (CC0 1.0).
- **Nagasaki (`JP-42`)**: Hirado City Fureai Bus (CC BY 4.0).
- **Kumamoto (`JP-43`)**: Kumamoto City tram, 熊本市交通局 (CC BY 2.1 JP) and
  Kumamoto Toshi Bus (CC BY 4.0).
- **Oita (`JP-44`)**: Kusu Town Community Bus (CC0 1.0).
- **Kagoshima (`JP-46`)**: Kagoshima City Ai Bus (CC BY 4.0).
- **Okinawa (`JP-47`)**: Yaese Town Bus and Yanbaru Express Bus (both CC BY 4.0).

Eight more within prefectures already covered, each a distinct city network from
the one already tracked: Misawa City Me-Bus (Aomori), Tsuchiura City Tsuchimaru
Bus (Ibaraki), Wako City Wakoba loop (Saitama), Yotsukaido City Yoppii (Chiba,
CC0 1.0), Chigasaki City Eboshi-go (Kanagawa), Fujieda City self-operated bus
(Shizuoka), Nagakute City N-Bus (Aichi), and Kuwana City K-Bus (Mie). All CC BY
4.0 except Yotsukaido.

The wave stayed fail-closed, and the exclusions are the point:

- **Unversioned or ambiguous license:** the catalog's two feeds under a bare
  "CC-BY", with no version, were rejected as before. Only the three named,
  versioned Creative Commons licenses were admitted.
- **Expired calendar:** several otherwise-open feeds carried a service window
  already ended by the 2026-07-18 review, including Ando Town (Nara), Susami Town
  (Wakayama), Wake Town (Okayama), and Kami Town, Kato City, and Yabu City
  (Hyogo). Each fails the current-calendar gate.
- **Discontinued:** the 24 feeds the catalog flags as discontinued were excluded
  by construction.
- **One feed per operator:** Nakatsu City (Oita) publishes its community bus as
  roughly eighteen separate line-level feeds. Rather than stack one operator's
  line exports, Oita is represented by Kusu Town's whole-network feed. Saitama's
  many single-route shared-taxi exports were likewise passed over for a clean
  city circulator elsewhere.
- **No admitted first-party feed:** Fukui (`JP-18`), Kyoto (`JP-26`), Tottori
  (`JP-31`), Hiroshima (`JP-34`), Yamaguchi (`JP-35`), Ehime (`JP-38`), and
  Miyazaki (`JP-45`) remain unrepresented, since the repository lists no feed for
  them under an admitted license. They wait for a first-party open feed rather
  than an aggregator mirror (busmaps.jp, opentrans.it), which stays out of scope.

## Reviewed ferry cohort

These five records were selected to exercise the ferry profile on current,
official feeds outside its U.S.-heavy baseline. A catalog listing alone did not
qualify a feed. Each source URL, service calendar, ferry route type, publisher,
and reuse terms was checked on 2026-07-16. The locations below are primary
catalog locations; several services cross borders.

### Magnetic Island Ferry, Translink (Australia)

| | |
|---|---|
| GTFS Schedule | `https://gtfsrt.api.translink.com.au/GTFS/MIF_GTFS.zip` |
| Location | Australia (`AU`), Queensland (`AU-QLD`) |
| Status | Verified as a direct ZIP with 1 ferry route, 2 terminals, and 92 trips; published service runs through 2026-09-15 |
| License and source | [CC BY 4.0 through Queensland's official dataset record](https://www.data.qld.gov.au/dataset/general-transit-feed-specification-gtfs-translink/resource/a7a3282c-ce87-4b4e-8b7b-70a4cc081ed6); attribute the State of Queensland and Department of Transport and Main Roads/Translink |
| Update cadence | The stable Translink URL serves the current release; the scorecard checks it no more than daily. |

### Brittany Ferries (France and international routes)

| | |
|---|---|
| GTFS Schedule | `https://transport.data.gouv.fr/resources/83427/download` |
| Primary location | France (`FR`), Bretagne (`FR-BRE`) |
| Status | Verified as a direct ZIP with 27 ferry routes, 12 boarding terminal locations, and 6,219 trips; published service runs through 2027-07-20 |
| License and source | [Licence Ouverte 2.0 through France's National Access Point](https://transport.data.gouv.fr/datasets/horaires-des-traversees-brittany-ferries), published by Brittany Ferries |
| Service area | Routes connect France, Spain, the United Kingdom, and Ireland. The primary location does not describe the complete service area. |

### Transmanche Ferries (France and United Kingdom)

| | |
|---|---|
| GTFS Schedule | `https://transport.data.gouv.fr/resources/83981/download` |
| Primary location | France (`FR`), Normandie (`FR-NOR`) |
| Status | Verified as a direct ZIP with the Dieppe–Newhaven ferry route, 2 terminals, and 1,409 trips; published service runs through 2027-01-03 |
| License and source | [Licence Ouverte 2.0 through France's National Access Point](https://transport.data.gouv.fr/datasets/transmanche-ferries), published by Syndicat mixte Atoumod for Transmanche Ferries |
| Update cadence | No fixed cadence is stated; the scorecard checks the stable resource no more than daily. |

### Sardegna–Corsica maritime services (Italy and France)

| | |
|---|---|
| GTFS Schedule | `https://www.sardegnamobilita.it/opendata/R_SARDEGTRASP_00010_1_dati_mare_corsica.zip` |
| Primary location | Italy (`IT`), Sardegna (`IT-88`) |
| Status | Verified as a direct ZIP with 4 ferry routes, 2 served boarding terminal locations, and 96 trips; published service runs through 2026-10-31 |
| Operators | Genova Trasporti Marittimi/Ichnusa Lines and Moby |
| License and source | [CC BY 4.0 under Sardegna Mobilità's open-data terms](https://www.sardegnamobilita.it/open-data); official dataset `R_SARDEG:TRASP_00010` is listed in the [maritime lines catalog](https://www.sardegnamobilita.it/open-data/linee) |

### Sardegna minor-island maritime services (Italy)

| | |
|---|---|
| GTFS Schedule | `https://www.sardegnamobilita.it/opendata/R_SARDEGTRASP_00006_1_dati_mare.zip` |
| Location | Italy (`IT`), Sardegna (`IT-88`) |
| Status | Verified as a direct ZIP with 7 ferry routes, 7 terminals, and 388 trips; published service runs through 2027-03-28 |
| Operators | Delcomar and Ensamar |
| License and source | [CC BY 4.0 under Sardegna Mobilità's open-data terms](https://www.sardegnamobilita.it/open-data); official dataset `R_SARDEG:TRASP_00006` has its own [minor-islands record](https://www.sardegnamobilita.it/open-data/isole-minori) |

The audit also rejected or deferred plausible-looking records. Sardinia
Ferries' live ZIP contains service dates from 2023 and is not current. The
Bizkaia Bridge feed uses the GTFS funicular route type, so it is not a ferry
profile candidate. Fred. Olsen Express and Baleària are legally reusable but
their official Spanish National Access Point downloads require authenticated
ingestion, which this pipeline does not yet implement. None is represented by
an unofficial mirror merely to increase the count.

### Africa licensing hold

Lagos remains outside the registry. Its ferry GTFS is current and the
[project identifies LASWA as a data partner](https://lagosferries.com/), but
the downloadable file has no explicit reuse license. The partnership and
consent gate in [ADR 0028](decisions/0028-global-south-pilot.md) requires us
to resolve that before publishing derived artifacts. We did not find a
current, official, explicitly licensed African substitute in this review;
expired licensed feeds and current feeds without clear reuse terms were not
added.

Hong Kong is the next technical canary because it has no ISO 3166-2 subdivision
and publishes frequency-based schedules. It remains out of production until the
freshness behavior for those schedules is reviewed. Community or informal feeds
in lower- and middle-income countries follow the partnership and consent gate in
[ADR 0028](decisions/0028-global-south-pilot.md); they are not added merely to
create a broader-looking map.

## Unitrans (ASUCD / City of Davis)

| | |
|---|---|
| GTFS Schedule | `https://unitrans.ucdavis.edu/media/gtfs/Unitrans_GTFS.zip` |
| Status | Verified 200 (after one 301 redirect; always follow redirects) |
| GTFS-Realtime | Published via UmoIQ (Cubic): trip updates, vehicle positions, and service alerts at `https://webservices.umoiq.com/api/gtfs-rt/v1/<kind>/unitrans`. All three endpoints exist but return 401 without a UmoIQ API key. |
| Mobility Database | `mdb-82` |
| transit.land | feed `f-9qc7-unitransdavis`, operator `o-9qc7-unitransdavis` |
| License | None stated. Site carries a UC Regents copyright. Treat as all-rights-reserved until the agency confirms terms. |
| Update cadence | Agency-stated: roughly every three months. The feed is produced in-house, not by a vendor. |
| Contact | jjflynn@ucdavis.edu (Mobility Database feed contact) |

Notes:
- The 301 target is a Drupal-internal path (`/sites/g/files/...`) that can
  change; always fetch the canonical `/media/gtfs/` URL.
- A keyless mirror exists at the Mobility Database latest bucket
  (`us-california-unitrans-gtfs-82.zip`), refreshed by MobilityData rather
  than the agency. Use only as a fallback.
- Realtime scoring for Unitrans (Phase 3) needs a UmoIQ API key. Until one is
  granted, the Realtime category will show "Not yet published" wording with a
  note that the agency does operate realtime tracking.

## Yolobus (Yolo County Transportation District)

| | |
|---|---|
| GTFS Schedule | `https://avl.yctd.org/RealTime/google_transit.zip` |
| Status | Verified 200, served as `application/x-zip-compressed` |
| GTFS-Realtime | No key required. TripUpdates `https://avl.yctd.org/RealTime/GTFS_TripUpdates.pb`, VehiclePositions `https://avl.yctd.org/RealTime/GTFS_VehiclePositions.pb`, ServiceAlerts `https://avl.yctd.org/RealTime/GTFS_ServiceAlerts.pb`. All three verified 200, `application/x-protobuf`. |
| Mobility Database | `mdb-1295` (stale; see warning below) |
| transit.land | feed `f-9qc7-yolobusyolocounty` (stale; see warning below) |
| License | None stated. `avl.yctd.org/TermsOfUse` covers only the rider-facing site. |
| Update cadence | Not stated. The feed is generated by the agency's TripSpark AVL system; the current zip's files are dated 2026-05-28. |

Warning — stale registries: the long-published URL
`http://www.yolobus.com/GTFS/google_transit.zip` died in October 2025. As of
the verification date, both the Mobility Database entry (mdb-1295) and
transit.land still point at it, and the MDB "latest" mirror is frozen at
2025-10-13. Fetch directly from `avl.yctd.org`, which is also what Cal-ITP's
monthly reports use. Reporting the correction to both registries is on the
backlog and would be a small useful contribution.

Feed quirks the pipeline must tolerate:
- No `feed_info.txt` (freshness falls back to the calendars).
- No `calendar.txt`; service is expressed entirely through
  `calendar_dates.txt` added-service exceptions.

## Polling etiquette

- Static GTFS: at most once per day per agency, with a descriptive
  User-Agent. Snapshots are archived under `data/raw/<agency>/<date>/` and
  re-runs reuse the day's snapshot instead of re-downloading.
- GTFS-Realtime (Phase 3): no more than one request per 30 to 60 seconds per
  endpoint, only during bounded demo capture windows, never as an unattended
  always-on poller.

## Primary sources

- Cal-ITP monthly GTFS quality reports: operator 351 (UC Davis / Unitrans)
  and operator 372 (Yolobus) at reports.dds.dot.ca.gov, which list the
  endpoint URLs above.
- Mobility Database catalogs CSV: share.mobilitydata.org/catalogs-csv,
  rows mdb-82 and mdb-1295.
- transit.land feed pages for the two Onestop IDs above.
- unitrans.ucdavis.edu/gtfs (agency GTFS page).

Last verified: 2026-07-16 · Recheck cadence: monthly, and before any demo.
