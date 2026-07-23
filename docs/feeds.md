# Hand-verified feed references

Source endpoints, licenses, and polling etiquette for the original Yolo County
pilots and the first worldwide canaries. This page is the hand-verified
reference; the full registry has more than 1,700 feed records, still mostly in
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

## Sixth reviewed European wave

This wave on 2026-07-18 again led with non-United-Kingdom sources and added 20
records, taking the reviewed European cohort from 165 to 185 across 20
countries. No United Kingdom feed was added. Each candidate passed a live
license read, a mechanical download and current-calendar preflight, a size
check under the archive cap, and an ISO 3166-2 subdivision review. After the
additions the United Kingdom is 18.4% of the cohort (34 of 185) and France, the
largest country, is 22.2% (41 of 185), both under the 40% ceiling.

- **Bulgaria (one record)**: Sofia's Center for Urban Mobility, the nineteenth
  country. The municipal open data portal urbandata.sofia.bg names CC BY-SA for
  the same GTFS the earlier wave had found unlicensed on the operator page.
- **Croatia (one record)**: Zagreb's ZET, the twentieth country, under the Open
  Licence of the Republic of Croatia. The Mobility Database's ZET row is
  deprecated, so the direct download is ZET's own current endpoint.
- **France (eleven records)**: DiviaMobilités (Dijon), ilévia (Lille), Ametis
  (Amiens), Transvilles (Valenciennes), Impulsyon (La Roche-sur-Yon), STAS
  (Saint-Étienne), T2C (Clermont-Ferrand), TAO (Orléans), Soléa (Mulhouse),
  Citalis (La Réunion), and Tango (Nîmes), which opens Occitanie. All are
  Licence Ouverte 2.0 as recorded on the National Access Point; each uses the
  point's current resource permalink rather than a dated snapshot.
- **Spain (three records)**: Renfe's Cercanías/Rodalies commuter rail and its
  high-speed and long-distance rail, both CC BY 4.0 on data.renfe.com, and EMT
  Málaga's city bus network under CC BY 4.0, distinct from the tracked Metro de
  Málaga.
- **Italy (two records)**: ATP Nuoro (Sardinia) and Bologna's Marconi Express
  people-mover, both under CC BY through Regione Sardegna and TPER. The operator
  endpoints do not serve a fetchable archive, so the direct download is
  MobilityData's hosted mirror.
- **Germany (two records)**: MVV München under CC BY, and MDV under CC BY 4.0,
  which opens Saxony. MVV's own file path rotates, so it uses the hosted mirror.

Rejections again outnumbered additions, and the reasons are the review:

- **No stable current download**: the Luxembourg national aggregate and the
  Austrian ÖBB rail feed. Luxembourg publishes only dated weekly snapshots (the
  newest still valid but version-pinned), and no ÖBB path served the current
  2025/2026 period.
- **Over the size guard**: the Entur Norway national aggregate, 606 MiB, well
  past the archive cap and too heavy to be one feed record.
- **Non-commercial license**: OASA Athens on data.gov.gr is CC BY-NC.
- **No reviewable open license**: HŽ Passenger Transport, BKK Budapest, TPBI
  Bucharest and the external.gtfs.ro-hosted Romanian city feeds, the Cyprus
  Motion feeds, and the Slovak ŽSR rail feed.
- **ODbL with special conditions**: French networks such as TCAT Troyes and
  Irigo Angers on the National Access Point.
- **Expired calendar or dead host**: Metro de Madrid and Metrotenerife (stale),
  Junta de Extremadura (expired), and Generalitat Valenciana intercity (DNS
  failure).

## Seventh reviewed European wave

This wave on 2026-07-18 again led with non-United-Kingdom sources and added 15
records, taking the reviewed European cohort from 185 to 200 across 22
countries. No United Kingdom feed was added. Each candidate passed a live
license read, a mechanical download and current-calendar preflight, a size
check under the archive cap, and an ISO 3166-2 subdivision review. After the
additions the United Kingdom is 17.0% of the cohort (34 of 200) and France, the
largest country, is 20.5% (41 of 200), both under the 40% ceiling.

- **Norway (eleven records)**: the twenty-first country, opened with one county
  transport authority per mainland fylke: Ruter (Oslo), Kolumbus (Rogaland),
  FRAM (Møre og Romsdal), the Nordland county authority, Brakar (Viken),
  Innlandstrafikk (Innlandet), VKT (Vestfold og Telemark), Agder
  Kollektivtrafikk, Skyss (Vestland), AtB (Trøndelag), and Snelandia (Troms og
  Finnmark). All are Entur per-operator GTFS exports under the Norwegian Licence
  for Open Government Data (NLOD) 2.0. Entur's national aggregate is a separate
  download that runs past the archive cap, so each per-operator slice is scored
  on its own.
- **Slovakia (one record)**: the twenty-second country, opened with Dopravný
  podnik Bratislava (DPB) on the city open data portal data.bratislava.sk, whose
  ArcGIS item records CC BY 4.0.
- **Latvia (two records)**: Rīgas satiksme (Rīga bus, tram, and trolleybus) and
  Pasažieru vilciens (the Vivi domestic rail network), both CC0 1.0 on
  data.gov.lv, distinct from the tracked ATD national bus aggregate.
- **Czechia (one record)**: Plzeňské městské dopravní podniky (PMDP) in Plzeň
  under CC BY 4.0 on opendata.plzen.eu, opening the Plzeňský kraj.

Rejections again outnumbered additions, and the reasons are the review:

- **No reviewable open license**: the Netherlands OVapi national aggregate
  (license blank in the Mobility Database and Transitland, NDOV redirects to a
  no-license host), HŽPP Croatian rail (license and portal pages 404), Strætó
  bs in Iceland, Tartu in Estonia, the Lithuanian stops.lt city feeds, GTT
  Torino (feed current and stable but the GTT license pages return 404 and 403),
  and the small Aytos feed in Bulgaria.
- **Non-commercial or no-derivatives**: OASA Athens (CC BY-NC), SNCB Belgian
  rail (signed non-commercial contract), and VMT Mittelthüringen (CC BY-ND).
- **Registration or key walled**: the Swedish Trafiklab regional feeds (SL,
  Skånetrafiken, Västtrafik, and others, all API-key gated), the Slovenian
  National Access Point feeds on b2b.nap.si (CC BY-SA 4.0 but HTTP 401), De Lijn
  in Flanders, and the Austrian national access point, whose GTFS carries a
  custom licence agreement and exposes only sample data.
- **No stable current download**: the Luxembourg official ATP feed, which
  publishes only weekly-dated snapshots with per-release resource ids and no
  rolling latest URL, unchanged from the sixth wave, and the German HVV Hamburg
  and VRR Rhein-Ruhr feeds, whose Mobility Database URLs are version-pinned
  snapshots that already expired in December 2025.
- **Aggregator or community-mirror host**: the mkuran.pl-hosted Polish feeds
  (Warszawa, Bydgoszcz, and others) and the Katowice ZTM feed, whose download
  URL rotates every forty minutes and is served through a CKAN API rather than a
  stable archive.
- **Access blocked from the pipeline network**: Wrocław (the download host
  returns HTTP 403) and Kraków (the terms page returns HTTP 403, so the license
  cannot be reviewed).
- **Expired, broken, or already present**: Metro do Porto (stale 2024 snapshot),
  TUB Braga (feed missing agency.txt), the Slovak DZK Košice line (rotating URL
  and an out-of-scope seasonal tourist railway), and the Irish TFI operator
  feeds, which are already tracked.

## Eighth reviewed European wave

This wave on 2026-07-18 again led with non-United-Kingdom sources and added 51
records, taking the reviewed European cohort from 200 to 251 across the same 22
countries. No United Kingdom feed was added. The wave reaches the 250-record
beta threshold. Each candidate passed a live license read, a mechanical
download and current-calendar preflight, a size check under the archive cap,
and an ISO 3166-2 subdivision review. After the additions France, the largest
country, is 27.1% of the cohort (68 of 251) and the United Kingdom is 13.5% (34
of 251), both under the 40% ceiling.

- **France (twenty-seven records)**: urban networks on the national access
  point transport.data.gouv.fr, each recorded as Licence Ouverte 2.0. They span
  ten regions, from Palmbus (Cannes) and Zest (Menton) in PACA through Filibus
  (Chartres), TRACE (Colmar), Ritmo (Haguenau), Izilo (Lorient), Idelis (Pau),
  and Occitanie networks (Agglobus Rodez, Citibus Narbonne, Sète, TLP
  Tarbes-Lourdes) to Normandy (Transurbain Évreux, Astrobus Lisieux, DeepMob
  Dieppe) and Hauts-de-France (TUC Cambrai, Corolis Beauvais, Pastel
  Saint-Quentin, TIC Compiègne). Each uses the point's stable resource
  permalink.
- **Norway (nine records)**: six national operators published through Entur
  under NLOD 2.0 that are distinct from the county-authority feeds. They are Vy
  (national rail), Go-Ahead Norge and SJ Nord (rail concessions), Vy Express and
  NOR-WAY Bussekspress (express coach), and Flytoget (airport express). The wave
  also adds three more county authorities, Østfold kollektivtrafikk, Farte
  (Telemark), and Svipper (Troms). The national operators carry no subdivision;
  the Entur national aggregate stays out over the archive cap.
- **Ireland (seven records)**: further National Transport Authority per-operator
  files under CC BY 4.0. They are TFI Local Link, Citylink, JJ Kavanagh, Dublin
  Coach, Wexford Bus, Matthews Coach Hire, and Swords Express (Dublin).
- **Italy (four records)**: three resources of Regione Toscana's CC BY dataset
  (GEST's Florence tramway, TFT's Arezzo rail and bus, and Autolinee Toscane's
  regional bus) and ATM Messina in Sicilia, published under CC BY on the Comune
  di Messina open data portal.
- **Germany (two records)**: VVS Stuttgart (CC BY 4.0) and SWU Ulm (CC0 1.0),
  both read on MobiData BW, the Baden-Württemberg state mobility portal. SWU
  operates within the tracked DING association but is a distinct operator-level
  feed under its own licence.
- **Portugal (one record)**: Metropolitano de Lisboa under CC BY 4.0 on the
  national portal dados.gov.pt, using the portal's stable latest-version
  redirect.
- **Poland (one record)**: MPK Legnica under CC BY 4.0 on dane.gov.pl, from a
  stable first-party City of Legnica endpoint, opening the Dolnośląskie
  voivodeship.

Rejections again outnumbered additions, and the reasons are the review:

- **No reviewable open license**: the Netherlands as a whole (the national
  portal returns no GTFS dataset, and OVapi/GOVI/NDOV stay license-blank),
  Belgium beyond the tracked TEC (De Lijn behind a registration wall with an
  unclear license, STIB API-key gated, SNCB non-commercial), Romania in full
  (data.gov.ro unreachable, CTP Cluj gated behind the third-party Tranzy
  platform with no named license, TPBI and the external.gtfs.ro mirrors
  unlicensed), Białystok and Olomouc (stable first-party feeds but no locatable
  license), SMTUC Coimbra, LVB Leipzig, and Stadtwerke Münster.
- **Non-commercial, no-derivatives, or share-alike outside the allowlist**:
  GTT Torino (operator pages CC BY-NC), VBN Bremen (CC BY-SA plus a form gate),
  and DPO Ostrava's portal default of CC BY-SA.
- **No stable or first-party download**: TUS Santander (the CKAN resource URL
  returns HTML, not the archive), AUVASA Valladolid (only a raw-IP HTTP endpoint
  on a nonstandard port), Regione Piemonte (SmartDataNet API endpoints, no
  stable GTFS zip), Matera (an http third-party content host with no archive
  form), Olsztyn and Kalisz (dated snapshots), and the Slovak IDS BK feed
  (third-party community host).
- **Access blocked or unreachable from the pipeline network**: Kraków's terms
  page (HTTP 403), Rzeszów's license portal, RMV Hessen, the Dresden and
  Austrian portals (anti-bot walls), and several Spanish municipal portals
  (Sevilla, Palma, Valencia FGV, Gijón, Córdoba, Donostia, Zaragoza, Murcia,
  Bilbao/CTB), whose licenses could not be read.
- **Expired calendar or out of scope**: Citéa (Valence Romans), Sillages (Pays
  de Grasse), and Elios (Grand Villeneuvois) in France; Águeda in Portugal
  (2018-2019 snapshots); and Via Bastia, held out because Corse has no ISO
  3166-2 subdivision in the registry vocabulary.

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

Deferred with recorded reasons: Transport for NSW gates its Sydney bulk
download behind a registered account. The ACT (Transport Canberra) host
returns HTTP 403 to the pipeline, and Metlink Wellington publishes no stated
reuse license. Each is revisited when its blocker clears.

Tasmania's earlier hold cleared on 2026-07-22. The
[Tasmanian Government GTFS page](https://www.transport.tas.gov.au/public_transport/gtfs-data)
now links one stable, keyless statewide aggregate and explicitly applies
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The current 15 MiB
archive passed the canonical validator preflight with 288 routes, 17,138 trips,
six publishers in `agency.txt`, and bus and ferry service. `feed_info.txt`
states service through 2026-09-30. The registry counts this aggregate as one
feed record, not six agencies.

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
- **Technical holds:** Hong Kong's official `static.data.gov.hk` feed was held
  here until the frequency-based freshness review documented later in this
  file; that review has now passed and the feed is admitted as a country-only
  canary. Taiwan's TDX feed for Taipei Metro
  (`tdx.transportdata.tw`) requires OAuth client credentials, which this pipeline
  does not ingest.

## Asia-Pacific breadth wave (second pass)

A second, portal-driven pass at non-Japan Asia-Pacific, aimed at new countries
and new cities rather than depth. It went past the Transitland sweep above to
the national open-data portals named for each target country: South Korea's
data.go.kr, India's first-party transit portals, Taiwan's TDX, and the
Australian state and New Zealand regional catalogs. The gate was the same
fail-closed test used above: an official first-party publisher, an explicit open
license that permits reuse including commercial use, a keyless direct download
the pipeline can fetch, and a live current calendar. Every candidate was
preflighted on 2026-07-18 and deleted after inspection.

Two records were added, both new Malaysian subdivisions on the same official
platform used above (`data.gov.my`, published under CC BY 4.0 and Malaysia's
Government Open Data Terms of Use 1.0, which permits reuse including commercial
use with attribution). Each preflighted as a valid archive with the GTFS core
tables and a current calendar through 2026-10-16:

- **BAS.MY Johor Bahru** (`MY-01`), operated by Causeway Link. The Johor Bahru
  stage bus network.
- **BAS.MY Melaka** (`MY-04`), operated by Causeway Link. The Melaka stage bus
  network.

These two town networks also appear in the Mobility Database, so the
Transitland sweep above left them out under its stricter "not already in the
catalog" gate. This wave admits official, openly licensed feeds for subdivisions
the registry does not yet carry, with `data.gov.my` as the first-party source,
so Johor (`MY-01`) and Melaka (`MY-04`) enter as new sub-national coverage.

No new country qualified. The reasons are the point, and they cluster:

- **API-key, OAuth, or registration walls (rejected):** South Korea's KTDB
  serves GTFS-based data only through an application and data-request process,
  and its published set is frozen at a March 2023 reference date; data.go.kr
  carries no keyless GTFS download. India's Open Transit Data Delhi
  (`otd.delhi.gov.in`) gates its static GTFS behind a usage form and a terms
  agreement rather than a stable direct URL, and Bengaluru, Mumbai, and Chennai
  surface only through aggregators. New Zealand's Christchurch (Environment
  Canterbury) serves GTFS through the Metro developer portal and a
  data-agreement wall. Singapore's LTA DataMall and New South Wales' Open Data
  Hub both require developer keys, and Transport for NSW is also over the
  download cap. Taiwan's TDX requires OAuth client credentials.
- **Official but no explicit open license (fail closed):** New Zealand's Metlink
  (Greater Wellington) publishes a clean, current, keyless GTFS at
  `static.opendata.metlink.org.nz`, but the dataset carries a liability
  disclaimer that reserves rights and grants no reuse permission, not CC BY or a
  named open license. Sri Lanka's National Transport Commission has GTFS
  development work but no first-party open-data download with a resolvable
  license. Waikato Regional Council (BUSIT) exposes no dataset-level open license
  for its feed.
- **Host blocks automated download, or an unstable URL (rejected):** Transport
  Canberra's older ACTION feed on `data.act.gov.au` (CC BY 4.0) now 403s, and
  its current MyWay+ GTFS requires an access key.
- **Resolved after this review:** Tasmania replaced its challenged, dated,
  share-alike download with the stable keyless CC BY 4.0 aggregate documented
  in the Oceania section. That new first-party evidence cleared the earlier
  exclusion; it was not inferred from the old URL.
- **Community, aggregator, or non-first-party (partnership-gated, not
  curation):** Indonesia has no official city GTFS beyond the catalog's
  TransJakarta; other cities are community exports. The Manila feed is community
  and app-challenge data. Vietnam's Hanoi feed is hosted by the World Bank data
  catalog and split into time-of-day files rather than a first-party Vietnamese
  source, and Ho Chi Minh City publishes none. Nepal and Bangladesh have only
  community-mapped data. These wait for the roadmap's partnership-gated phase.
- **Resolved after this review:** on 2026-07-22, the official `data.gov.my`
  API republished Alor Setar, Kota Bharu, Kuala Terengganu, and Kuching with
  390 to 804 trips apiece and service through 2026-12-31. Each small archive
  passed the canonical validator preflight and is now admitted as one feed
  record in Kedah, Kelantan, Terengganu, or Sarawak. This decision uses the new
  bytes; it does not reinterpret the earlier zero-trip stubs.
- **Still held on freshness:** Ipoh and both Seremban feeds carry service only
  on the day they are fetched, with no `calendar_dates` extension, so they
  remain out until the official API publishes a usable future window.

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

## Japan gtfs-data.jp third wave

A third pass over the same national repository ([gtfs-data.jp](https://gtfs-data.jp/),
operated by AIGID). The two prior waves lifted Japan to 65 records across 40
prefectures. This wave only goes deeper: it adds distinct new operators inside
prefectures already represented, because the seven prefectures still missing after
the second wave carry no feed at all in the catalog. Forty records were added,
lifting Japan from 65 to 105 records, still across 40 prefectures. Every candidate
is a distinct operator not already tracked, confirmed official, openly licensed,
and mechanically preflighted on 2026-07-18: a valid archive with the GTFS core
tables and a current, non-expired service calendar, within the ingestion size caps,
and absent from the Mobility Database. Each download was deleted after the check.

The license mix of the 40 is 35 CC BY 4.0, 3 CC0 1.0, and 2 CC BY 2.1 JP, the same
three admitted licenses as the second wave, with the exact version stated in each
record's `license_note` and attribution. The two bare "CC-BY" feeds with no
resolvable version stayed rejected.

Thirty prefectures deepened, each operator distinct from those already tracked
(license in parentheses where not CC BY 4.0):

- **Hokkaido (`JP-01`)**: Nemuro Kotsu (CC0 1.0).
- **Aomori (`JP-02`)**: Goshogawara City Community Bus.
- **Iwate (`JP-03`)**: Ichinoseki City Bus.
- **Miyagi (`JP-04`)**: Takeya Kotsu.
- **Yamagata (`JP-06`)**: Sakata City Bus, Yamagata Railway.
- **Fukushima (`JP-07`)**: Motomiya City Community Bus, Shin-Joban Kotsu.
- **Ibaraki (`JP-08`)**: Ryugasaki City Community Bus.
- **Tochigi (`JP-09`)**: Ashikaga City Route Bus.
- **Gunma (`JP-10`)**: Annaka City An-Bus, Nagai Bus.
- **Chiba (`JP-12`)**: Nagareyama Green Bus.
- **Tokyo (`JP-13`)**: Tachikawa City Kururin Bus, Ogasawara Village Bus.
- **Kanagawa (`JP-14`)**: Ninomiya Town Community Bus.
- **Niigata (`JP-15`)**: Kamo City Kamon Bus.
- **Toyama (`JP-16`)**: Imizu City Kitokito Bus (CC0 1.0), Manyosen (CC0 1.0).
- **Ishikawa (`JP-17`)**: Nonoichi City Community Bus.
- **Yamanashi (`JP-19`)**: Hokuto City Bus.
- **Nagano (`JP-20`)**: Chikuma City Loop Bus, Kiso Town Public Transport (CC BY 2.1 JP).
- **Gifu (`JP-21`)**: Gifu City Community Bus, Akechi Railway.
- **Shizuoka (`JP-22`)**: Hamamatsu Bus, Iwata routes.
- **Aichi (`JP-23`)**: Seto City Community Bus, Chita Bus.
- **Mie (`JP-24`)**: Iga City Community Bus, Ise Railway.
- **Shiga (`JP-25`)**: Omihachiman City Akakon Bus.
- **Hyogo (`JP-28`)**: Takasago City Joton Bus (CC BY 2.1 JP).
- **Wakayama (`JP-30`)**: Meiko Bus.
- **Okayama (`JP-33`)**: Niimi City Bus.
- **Tokushima (`JP-36`)**: Tokushima City Bus, Asa Coast Railway DMV.
- **Kagawa (`JP-37`)**: Seisan Kanko Takamatsu Airport Limousine.
- **Kochi (`JP-39`)**: Aki City Genki Bus.
- **Fukuoka (`JP-40`)**: Koga City Bus.
- **Kumamoto (`JP-43`)**: Sanko Bus.

The wave reaches past municipal community buses into first-party private operators
and rail. It adds five rail feeds (Yamagata Railway, Akechi Railway, Ise Railway,
the Manyosen light rail, and the Asa Coast Railway dual-mode vehicle service) and
several regional bus companies (Nemuro Kotsu, Takeya Kotsu, Shin-Joban Kotsu, Nagai
Bus, Chita Bus, Meiko Bus, and Kyushu Sanko Bus).

The exclusions carry the discipline:

- **Seven priority prefectures still empty:** Fukui (`JP-18`), Kyoto (`JP-26`),
  Tottori (`JP-31`), Hiroshima (`JP-34`), Yamaguchi (`JP-35`), Ehime (`JP-38`), and
  Miyazaki (`JP-45`) carry zero feeds anywhere in the catalog, first-party or
  otherwise. This was confirmed by scanning the prefecture field of every one of
  the roughly 596 catalog records. They stay unrepresented; no aggregator mirror
  (busmaps.jp, opentrans.it) was used.
- **Vein not exhausted:** after this wave the catalog still lists on the order of
  240 more admitted-license operators not yet tracked. The wave was capped for
  review quality, not for lack of supply.
- **One feed per operator:** operators that publish only line-level exports were
  passed over for whole-network feeds elsewhere. Nakatsu City (Oita) publishes its
  community bus as eighteen separate line feeds, and Saitama City publishes its
  circulators as per-ward and per-route shared-taxi feeds; neither yields a single
  whole-network feed, so both were skipped.
- **Discontinued and expired:** the feeds the catalog flags as discontinued were
  excluded by construction, and any feed whose service calendar had already ended
  by the 2026-07-18 review was dropped.

## Japan gtfs-data.jp fourth wave

A fourth pass over the same national repository ([gtfs-data.jp](https://gtfs-data.jp/),
operated by AIGID). The three prior waves lifted Japan to 105 records across 40
prefectures. This wave goes deeper again inside prefectures already represented,
because the seven prefectures still missing after the third wave carry no feed at
all in the catalog. Forty records were added, lifting Japan from 105 to 145
records, still across 40 prefectures. Every candidate is a distinct operator not
already tracked, confirmed official, and mechanically preflighted on 2026-07-18:
the download was opened, its GTFS core tables and a current, non-expired service
calendar were confirmed, its size was checked against the standard ingestion
caps, and the archive was deleted after the check.

The wave leans toward first-party private operators. About twenty of the forty
are private bus and rail companies rather than municipal community buses, and it
adds two rail feeds: the Toyama Chitetsu city tram and the Kumamoto Electric
Railway train lines. The license mix of the forty is 35 CC BY 4.0, 3 CC BY 2.1 JP,
and 2 CC0 1.0, the same three admitted licenses as before, with the exact version
stated in each record's `license_note` and attribution.

Twenty-five prefectures deepened, each operator distinct from those already
tracked (license in parentheses where not CC BY 4.0):

- **Hokkaido (`JP-01`)**: Ganu Area Shiokaze Line.
- **Aomori (`JP-02`)**: Shimokita Kotsu, Towada Kanko Dentetsu.
- **Iwate (`JP-03`)**: Oshu City Community Bus.
- **Yamagata (`JP-06`)**: Yamako Bus, Shonai Kotsu.
- **Ibaraki (`JP-08`)**: Otone Kotsu, Namegata City Bus.
- **Tochigi (`JP-09`)**: Nikko City Bus.
- **Gunma (`JP-10`)**: Oizumi Town Aozora Bus.
- **Chiba (`JP-12`)**: Keisei Bus Chiba West.
- **Tokyo (`JP-13`)**: Kozushima Village Bus.
- **Niigata (`JP-15`)**: Itoigawa Bus, Joetsu City Bus (CC BY 2.1 JP).
- **Toyama (`JP-16`)**: Toyama Chitetsu City Tram (CC0 1.0).
- **Ishikawa (`JP-17`)**: Uchinada Town Community Bus.
- **Yamanashi (`JP-19`)**: Ichikawamisato Town Community Bus.
- **Nagano (`JP-20`)**: Chikuma Bus, Ueda Bus.
- **Gifu (`JP-21`)**: Kitaena Kotsu, Tono Railway Ena Bus.
- **Aichi (`JP-23`)**: Aoi Kotsu, Kariya City Karimaru Bus.
- **Mie (`JP-24`)**: Matsusaka City Community Transport.
- **Shiga (`JP-25`)**: Koka City Community Bus, Takashima City Community Bus.
- **Hyogo (`JP-28`)**: Ono City Ran-Ran Bus (CC BY 2.1 JP), Tatsuno City
  Community Bus (CC BY 2.1 JP).
- **Wakayama (`JP-30`)**: Chuki Bus, Ryujin Bus.
- **Okayama (`JP-33`)**: Kagamino Town Bus, Hayashima Town Community Bus.
- **Tokushima (`JP-36`)**: Tokushima Bus, Matsushige Town Community Bus.
- **Kochi (`JP-39`)**: JR Shikoku Bus (Kochi branch), Kochi Tobu Kotsu.
- **Fukuoka (`JP-40`)**: Amagi Kanko Bus, Taiyo Kotsu.
- **Kumamoto (`JP-43`)**: Kumamoto Bus, Kumamoto Electric Railway (CC0 1.0).

The exclusions carry the discipline:

- **Capped at forty for review quality:** the pass turned up 54 preflight-clean
  new operators, more than the wave admits. The forty were chosen to keep the
  cohort broad across prefectures and weighted toward private and rail operators.
  Thirteen valid municipal feeds that preflighted cleanly were held for a later
  wave rather than stacked here, among them Hiranai Town and Shinjo City,
  Otawara City, Narita City, Arakawa City, Takaoka City, Shiojiri City, Gujo
  City, Minamichita Town, the Tsu Airport Line shuttle, Tosa City, Yanagawa
  City, and Otama Village.
- **Not a public network:** the Radiant City Yokohama feed (Daishinto, Kanagawa)
  is a shuttle for a single residential complex rather than a public network, so
  it was left out.
- **One feed per operator:** operators that publish only line-level or area-level
  exports were passed over for whole-network feeds elsewhere. Nakatsu City (Oita)
  publishes eighteen separate line feeds, Saitama City publishes its circulators
  as per-ward and per-route shared-taxi feeds, Shizuoka City publishes five
  district feeds, and Ugo Kotsu (Akita) publishes two area feeds with no single
  whole-network feed. None yields one feed for the whole network, so all were
  skipped.
- **Unversioned or ambiguous license:** the catalog's two feeds under a bare
  "CC-BY", with no resolvable version, stayed rejected. Only the three named,
  versioned Creative Commons licenses were admitted.
- **Discontinued and expired:** the feeds the catalog flags as discontinued were
  excluded by construction, and feeds whose service calendar had already ended by
  the 2026-07-18 review were filtered out before the shortlist. Every record kept
  carries a calendar current at review time.
- **Seven priority prefectures still empty:** Fukui (`JP-18`), Kyoto (`JP-26`),
  Tottori (`JP-31`), Hiroshima (`JP-34`), Yamaguchi (`JP-35`), Ehime (`JP-38`),
  and Miyazaki (`JP-45`) still carry zero feeds under an admitted license
  anywhere in the catalog. They stay unrepresented; no aggregator mirror
  (busmaps.jp, opentrans.it) was used.
- **Vein still deep:** after this wave the catalog still lists more than 250
  admitted-license operators not yet tracked. The wave was capped for review
  quality, not for lack of supply.

## Japan gtfs-data.jp fifth wave

A fifth pass over the same national repository ([gtfs-data.jp](https://gtfs-data.jp/),
operated by AIGID). The four prior waves lifted Japan to 145 records across 40
prefectures. This wave again goes deeper inside prefectures already represented,
because the seven prefectures still missing carry no admitted-license feed in the
catalog. Forty records were added, lifting Japan from 145 to 185 records, still
across the same 40 prefectures. Every candidate is a distinct operator not already
tracked, confirmed official through the repository, and mechanically preflighted on
2026-07-18: the download was opened, its GTFS core tables and a current, non-expired
service calendar were confirmed by reading calendar.txt and calendar_dates.txt
directly, its size was checked against the standard ingestion caps, and the archive
was deleted after the check.

The license mix of the forty is 34 CC BY 4.0, 4 CC0 1.0, and 2 CC BY 2.1 JP, the
same three admitted licenses as before, with the exact version stated in each
record's `license_note` and attribution. About a quarter of the forty are private
operators rather than municipal community buses, including Mogamigawa Kotsu,
Kusakaru Kotsu, Hachiman Kanko Bus, Kenko Hokubu Kotsu, and Seikatsu Bus Yokkaichi.
Three water services join the cohort: the Meitetsu Kaijo Kanko high-speed boats to
the Mikawa Bay islands, the Tsu Airport Line ferry, and the Kochi prefectural ferry.

Nineteen prefectures deepened, each operator distinct from those already tracked
(license in parentheses where not CC BY 4.0):

- **Hokkaido (`JP-01`)**: Ishikari City Itsumo AI on-demand transit (CC0 1.0).
- **Aomori (`JP-02`)**: Hiranai Town Community Bus, Kuroishi City Platto-go, Towada
  City Community Bus.
- **Yamagata (`JP-06`)**: Mogamigawa Kotsu, Shinjo City Bus, Tsuruoka City Bus.
- **Fukushima (`JP-07`)**: Otama Village Commuter Bus.
- **Tochigi (`JP-09`)**: Nasushiobara City Community Bus, Otawara City Bus.
- **Chiba (`JP-12`)**: Katori City Loop Bus (CC0 1.0), Narita City Community Bus.
- **Tokyo (`JP-13`)**: Arakawa Sakura Bus, Katsushika Sakura Bus.
- **Toyama (`JP-16`)**: Nanto City Bus (CC0 1.0), Takaoka City Public Bus (CC0 1.0).
- **Nagano (`JP-20`)**: Kusakaru Kotsu, Shiojiri Step-kun Bus, Nagano City Bus.
- **Gifu (`JP-21`)**: Gujo City Bus, Hachiman Kanko Bus, Ogaki City Bus (Meihan
  Kintetsu).
- **Aichi (`JP-23`)**: Meitetsu Kaijo Kanko Ferry, Minamichita Umikko Bus.
- **Mie (`JP-24`)**: Seikatsu Bus Yokkaichi, Tsu Airport Line, Yokkaichi City Bus.
- **Shiga (`JP-25`)**: Higashiomi Chokotto Bus, Nagahama Nishiazai Wagon.
- **Hyogo (`JP-28`)**: Himeji island community buses (CC BY 2.1 JP), Minami-Awaji
  Ran-Ran Bus (CC BY 2.1 JP).
- **Wakayama (`JP-30`)**: Iwade City Loop Bus.
- **Okayama (`JP-33`)**: Nagi Town Bus.
- **Tokushima (`JP-36`)**: Tokushima Bus Nanbu, Miyoshi City Bus.
- **Kochi (`JP-39`)**: Kenko Hokubu Kotsu, Kochi Prefectural Ferry, Tosa City Dragon
  Bus.
- **Fukuoka (`JP-40`)**: Kama City Bus, Yanagawa City Community Bus.

The exclusions carry the discipline:

- **Expired current calendar:** Nanbu Town (Yamanashi) advertised a 2026-to-2027
  window in the catalog metadata, but its `rid=current` archive still held a
  calendar.txt that ended 2026-03-31, already expired at the 2026-07-18 review. It
  was rejected. Reading the calendar by hand rather than trusting the metadata is
  what caught it.
- **One operator per municipality:** the Hachinohe City Nango community bus was held
  back because Hachinohe is already tracked through its transportation bureau's city
  bus, a separate publisher slug for the same municipality.
- **Not a public network:** the Radiant City Yokohama shuttle (Daishinto, Kanagawa)
  remains excluded as a single residential complex's service, consistent with the
  fourth wave.
- **One feed per operator:** operators that publish only line-level or area-level
  exports were passed over. Nakatsu City (Oita) publishes eighteen line feeds,
  Saitama City publishes per-ward and per-route shared-taxi feeds, and Minami-Shinshu
  publishes eleven area feeds. None yields one feed for the whole network.
- **Unversioned or ambiguous license:** the catalog's two feeds under a bare
  "CC-BY", with no resolvable version, stayed rejected. Only the three named,
  versioned Creative Commons licenses were admitted.
- **Discontinued and expired:** the feeds the catalog flags as discontinued were
  excluded by construction, and feeds whose service calendar had already ended by
  the review were filtered out before the shortlist.
- **Seven priority prefectures still empty:** Fukui (`JP-18`), Kyoto (`JP-26`),
  Tottori (`JP-31`), Hiroshima (`JP-34`), Yamaguchi (`JP-35`), Ehime (`JP-38`),
  and Miyazaki (`JP-45`) still carry zero feeds under an admitted license anywhere
  in the catalog. They stay unrepresented; no aggregator mirror was used.
- **Capped for review quality:** the preflight cleared fifty new operators after
  dedup. Forty were kept, weighted toward breadth across prefectures and toward
  private and water operators, and the remaining ten were held for a later wave.
  After this wave the catalog still lists well over 200 admitted-license operators
  not yet tracked.

## Latin America breadth wave (2026-07-18)

A breadth pass aimed at broadening Latin American coverage past the three
records already carried (Belo Horizonte's two networks, Rio de Janeiro, and
Montevideo), prioritizing new countries and new cities under the same
fail-closed and partnership-gated bar as every wave above. The review read the
full Latin American slice of the Mobility Database catalog (55 GTFS rows across
ten countries), rechecked the four URLs earlier waves deferred (Mexico City,
Guadalajara, Santiago DTPM, Bogotá SIMUR), and probed several municipal
open-data portals directly. Every reachable candidate was preflighted: the zip
was downloaded, its core tables and `calendar.txt` window read by hand, its size
checked, and the archive deleted.

**No records were added.** The bar for this wave is an official first-party feed
with a resolvable open license, a current service calendar, a stable
non-rotating URL, and a host the pipeline can actually reach. No Latin American
candidate cleared all four at once, and the reason is a consistent regional
pattern: the feeds that stay current republish under dated URLs, while the feeds
that keep a stable URL have gone stale. The rejections are the deliverable.

- **Expired service calendar (stable URL, active agency, window already ended):**
  Fortaleza's ETUFOR bus feed (`dados.fortaleza.ce.gov.br`, calendar ends
  2026-07-03), Porto Alegre's EPTC feed (`dadosabertos.poa.br`, ends 2025-12-12),
  the ARCE metropolitan-Ceará feed (ends 2025-12-31), the Aguascalientes state
  feed (ends 2025-12-31), and Buenos Aires' colectivos feed
  (`cdn.buenosaires.gob.ar`, a roughly 200 MiB archive last modified in 2019).
  All are official and reachable; none is current. ETUFOR is the closest miss,
  expired by about two weeks and from an agency that republishes quarterly, and
  is worth a recheck later.
- **Dated or rotating URL with no stable alias:** Santiago's DTPM feed
  (`GTFS_YYYYMMDD.zip` under `dtpm.cl/descargas/gtfs`) and Bogotá's SIMUR feed
  (a `gtfs-estaticos` Google Cloud bucket whose every object is dated, refreshed
  daily). Both are official and current, both wait on a canonical stable URL, and
  both were deferred for this same reason by the earlier official wave.
- **Host unreachable or broken from the fetch environment, so the pipeline could
  not fetch them either:** Mexico City's SEMOVI feed (`datos.cdmx.gob.mx` times
  out at the connection, and the older `setravi` S3 mirror returns access-denied),
  Guadalajara's Jalisco-state feed (`datos.jalisco.gob.mx` serves no public A
  record), and the METROFOR Fortaleza-metro feed (expired TLS certificate).
- **Dead or non-GTFS download:** Oaxaca's SEMOVI feed (the recorded asset path
  now returns the application shell) and Curitiba's URBS data (the official portal
  publishes URBS's own JSON web-service format, not a GTFS zip; the GTFS builds
  are community conversions). Medellín Metro's ArcGIS document is not publicly
  downloadable (403) and its listed data is from 2024.
- **No resolvable open license:** the Chilean regional operator feeds on
  `datos.gob.cl` (Coquimbo, Rancagua, Talca, Temuco), Aguascalientes, and Peru's
  Aeroexpreso carry no license a reviewer can confirm.
- **OSM-derived, out regardless of license:** the Movimex feeds for Jilotepec and
  Toluca (Estado de México), both licensed under the OpenStreetMap copyright,
  which marks their data as derived from OpenStreetMap.
- **Private operator, not a public-transit authority:** Daytrip Shuttle (Costa
  Rica and Cancún), a door-to-door tourist shuttle whose route URLs carry
  marketing tracking parameters; its calendar is also expired.
- **Registration-walled:** São Paulo's SPTrans feed, behind a developer sign-in.
- **No GTFS published:** Recife (the open-data portal returns no GTFS dataset),
  Brasília (DFTrans was dissolved and the DF portal carries no current feed),
  Mérida's Va y Ven, the Panamá Metro, Guayaquil's Metrovía, and Quito.
- **Partnership-gated community, volunteer, or aggregator data, held out per the
  [global coverage roadmap](global-coverage-roadmap.md) regardless of license:**
  the MapaNica volunteer feeds (Managua, Estelí, and national Nicaragua), the
  Trufi Association feed (Trujillo, Peru), the Digital Transport GitLab feed
  (Santiago de los Caballeros, Dominican Republic, whose named provider is the
  municipality but whose data is community-mapped and community-hosted), the
  ColombiaGTFS GitHub builds (Cali's MIO and a Medellín community build), and
  personal GitHub repositories (Ibagué and Sincelejo in Colombia, Bagé in Brazil,
  and a national Honduras feed). These wait for a named local steward.

## Middle East and Africa breadth wave

A breadth pass across Turkey beyond İzmir, the Gulf, North Africa, and
sub-Saharan Africa under the [global coverage roadmap](global-coverage-roadmap.md)
Phases 3 and 4, aimed at new countries and new cities with one representative
feed each. The gate was fail-closed: admit only an official first-party
publisher with an explicit, resolvable open license (CC BY, CC0, or a confirmed
national open-data license that permits commercial reuse) whose feed downloads
as a single current GTFS archive within the ingestion caps. Sources were the
Mobility Database catalog, the Transitland Atlas, and the municipal open-data
portals named below, all checked by hand on 2026-07-18.

No candidate cleared the gate, so no record was added and the registry total is
unchanged at 1,609. That is the expected result here, not a shortfall. This
region carries the least official-open GTFS and the most community-mapped GTFS
in the catalog, and holding the partnership gate firmly is the point of the
review. The existing İzmir metro and tram records (CC BY 4.0, İzmir Metropolitan
Municipality) and the size-deferred Israel national feed remain the region's
only tracked entries. The rejections below are the deliverable.

Rejected or deferred, grouped by reason:

- **Official and openly licensed, but not a single GTFS archive.** İstanbul's
  İETT network is on the İstanbul Metropolitan Municipality open-data portal
  (`data.ibb.gov.tr`) under the İBB Açık Veri Lisansı, whose text equates it to
  CC BY 4.0 and permits commercial reuse, and it was current (updated
  2026-04-21). Both the İETT dataset and the wider public-transport dataset
  (metro, Marmaray, ferries) expose the GTFS tables only as separate `.csv`
  resources, with no bundled `.zip` of `.txt` files. The pipeline ingests one
  GTFS archive per feed, so an unbundled CSV-resource dataset fails preflight.
  Kocaeli (`veri.kocaeli.bel.tr`, CC BY, mdb 2710) publishes the same way; its
  catalog record notes "individual text files provided." Metro İstanbul publishes
  no separate GTFS of its own.
- **No reviewable open license (fail closed).** Abu Dhabi's Integrated Transport
  Centre feed (mdb 1329) states no license, and its catalog download is a
  session-scoped `pubftp.dmt.gov.ae` weblink rather than a stable URL; the ITC
  open-data page now returns 404. Isparta's private-operator feed
  (`ots.kentekspress.com.tr`, mdb 2381) states no license and its URL returns a
  redirect loop. Lagos State Waterways (mdb 3144) is current but carries no reuse
  license, as already recorded in the Africa licensing hold below.
- **Registration wall or non-first-party mirror.** Dubai RTA (mdb 904) is marked
  inactive and its only catalog download is a Transitland community archive, not
  a first-party file; the RTA GTFS itself sits behind Dubai Pulse registration.
- **Dead aggregator or no license.** Algeria's SNTF national rail (mdb 1199) and
  Tunisia's SRTMedenine (mdb 1158) resolve only to the defunct transitfeeds
  aggregator and state no license.
- **Non-commercial license.** Cairo Metro (mdb 3354 and 786) is served by
  Transport for Cairo under CC BY-NC-SA, which the project does not admit.
- **No official open GTFS found.** Qatar, Saudi Arabia, Bahrain, Kuwait, Jordan,
  and Oman have no GTFS in the Mobility Database, and their transport authorities
  publish through consumer apps or registration-gated portals rather than an open
  feed. Mwasalat (Oman) serves a current national feed with no published reuse
  license, as recorded in the Transitland non-Western sweep. Turkey's Bursa,
  Ankara, and Antalya portals did not resolve from the review environment and are
  not in the catalog as ingestible open feeds.

**Partnership-gated community data, held out by design.** The largest body of
African GTFS is community-mapped or survey-produced, and the roadmap's
partnership-gated phase keeps it out of catalog curation until a named local
steward owns licensing, source verification, and consent
([global coverage roadmap](global-coverage-roadmap.md) Phase 4,
[ADR 0028](decisions/0028-global-south-pilot.md)). Every sub-Saharan African
feed in the catalog resolves to a
[Digital Transport for Africa](https://digitaltransport4africa.org/) repository
on `git.digitaltransport4africa.org` or `gitlab.com/digitaltransport`, several
under ODbL: Abidjan (Côte d'Ivoire), Douala (Cameroon, Socatur), Addis Ababa
(Ethiopia), Accra and Kumasi (Ghana), Nairobi (Kenya, DigitalMatatus), Kampala
(Uganda, 14-seater paratransit), Kigali (Rwanda), Tétouan (Morocco, Vitalis),
and Stellenbosch (South Africa). Held out and logged even where openly licensed.
Two more sit in the same partnership-gated bucket: Morocco's ONCF national rail
(mdb 3049), whose only catalog download is a personal GitHub scrape under ODbL
rather than an ONCF-published feed, and Algoa Bus (South Africa, mdb 3133),
served from a personal Google Drive link with no license.

Cape Town's MyCiTi was checked as the roadmap named it. The City of Cape Town
open-data portal did not surface a first-party GTFS download, and the widely
mirrored South African feeds are produced by WhereIsMyTransport or GoMetro rather
than a municipal open-data program. They stay partnership-gated, and no South
African feed was added.

## Canada and Australia depth wave

A depth pass over two countries the registry already carried, adding official,
first-party, openly licensed GTFS Schedule feeds. Discovery ran across the
Mobility Database catalog, the Transitland Atlas, and Canadian and Australian
open-data portals. Every candidate was preflighted on 2026-07-18: the source zip
was downloaded, its `calendar.txt` and `calendar_dates.txt` window and size were
read, the archive was deleted, and the reuse licence was confirmed at the
publisher before any record was written. The gate was fail-closed, so a
candidate had to show a first-party publisher, a resolvable licence permitting
commercial reuse, a current service calendar, and a stable keyless download.
Sixty-nine records were added.

Australia added twelve records, all in Queensland. The TransLink GTFS dataset on
data.qld.gov.au (CC BY 4.0, © State of Queensland, Department of Transport and
Main Roads) carries a qconnect regional network export per town beyond the seven
already curated. Added: Magnetic Island (bus), North Stradbroke Island, Warwick
(Haidleys Panoramic Coaches), Gladstone (Buslink), Kilcoy (Christensens Bus and
Coach), Maleny-Landsborough (Glass House Country Coaches), Gympie (Polleys
Coaches), Bundaberg (Duffy's Buses), Innisfail, Bowen, Whitsundays (Whitsunday
Transit), and Rockhampton-Yeppoon. Each read as a valid archive with a current
calendar through September 2026. Rockhampton-Yeppoon is the dataset's
consolidated RKY export and has no Mobility Database id, so it enters as a
first-party feed without one.

Canada added fifty-seven records across five subdivisions:

- British Columbia (thirty-five): BC Transit regional systems across the
  province, from the Victoria and Kelowna networks to small community systems
  such as 100 Mile House and Salt Spring Island. The BC Transit Open Data Terms
  of Use grant a non-exclusive licence to use, reproduce, and redistribute the
  data including commercially, with attribution to BC Transit. It is a custom
  government licence, recorded as such rather than as Creative Commons.
- Québec (fourteen): the nine exo suburban sectors and the exo commuter-rail
  feed (CC BY 4.0 through Données Québec), plus RTC (Québec City), STS
  (Sherbrooke), STLévis, and Rouyn-Noranda, all CC BY 4.0.
- Ontario (six): Toronto Transit Commission and York Region Transit under their
  Open Government Licence variants, Oakville Transit under the Open Government
  Licence – Town of Oakville, Brampton Transit under CC BY 4.0, and GO Transit
  and UP Express under the Open Government Licence – Ontario (Metrolinx).
- Alberta (one): Calgary Transit under the Open Government Licence – City of
  Calgary, which grants commercial reuse.
- Nationwide (one): VIA Rail Canada, the intercity passenger rail network, under
  the Open Government Licence – Canada 2.0. It spans several provinces and is
  carried without a subdivision.

The review rejected or deferred more than it kept, and the reasons cluster:

- Expired service calendar (official and reachable, window already ended): Roam
  Transit (Banff, ended 2024-12), exo Haut-Saint-Laurent (2024-09), exo
  Roussillon (2023-07), and Moose Jaw Transit (2024-03).
- Dead or superseded download URL: the Youngs Bus Service (Yeppoon) and Sunbus
  Rockhampton catalog entries both 404 and are replaced by the consolidated
  Rockhampton-Yeppoon feed added above; Miramichi Transit's catalog URL also
  404s.
- Host unreachable or blocking automated fetch: Saskatoon Transit (HTTP 503) and
  MRC les Moulins (HTTP 403).
- Licence forbids or conditions commercial reuse (fail closed): Metrobus
  (St. John's) reserves the right to charge commercial users a fee, and the
  Société de transport de Laval restricts commercial and quasi-commercial use.
  Neither is an open commercial-reuse grant.
- Share-alike, held for consistency: Codiac Transpo (Moncton) publishes under
  CC BY-SA. Share-alike is not on the accepted licence list.
- Licence page not resolvable from the review environment (fail closed): Halifax
  Transit, Lethbridge Transit, Red Deer Transit, Durham Region Transit, Greater
  Sudbury Transit, Burlington Transit, Transit Windsor, City of Regina, and STO
  (Gatineau) each returned a 403, a 404, or a JavaScript or bot-challenged
  licence page, so the exact terms could not be read. They wait for a manual
  licence read.
- Licence unconfirmed in this pass (aggregator- or Metrolinx-hosted with no
  dataset-level licence surfaced): Cornwall, Belleville, and Milton Transit
  (served through metrolinx.tmix.se), Fredericton Transit (an ArcGIS item with
  no licence field), Medicine Hat Transit, Thunder Bay Transit, and RTL
  Longueuil (its conditions PDF 404s). These remain candidates for a later pass.
- Aggregator-hosted rather than first-party: Maritime Bus is served only from a
  Trillium mirror, not an operator or government portal.
- Already evaluated by the Asia-Pacific breadth wave and not re-litigated:
  Transport for New South Wales (key-gated and over the download cap), Transport
  Canberra (HTTP 403, and its MyWay+ feed needs a key). Tasmania's superseding
  first-party aggregate is documented separately because its source, URL, and
  licence all changed after this pass.

## United States small and rural depth wave

A pass aimed at small and rural US agencies that publish a first-party GTFS
under a reuse basis that can actually be confirmed, since most US public-agency
GTFS carries no stated license. Two sources cleared that bar. The Caltrans DDS
GTFS index (`gtfs.dds.dot.ca.gov`) hosts California agency feeds and states a
single site-wide Creative Commons Attribution 4.0 license. The National Park
Service GTFS program (`nps.gov/subjects/developer/gtfs.htm`) publishes park
transit feeds that are US Government works, and the NPS disclaimer places
NPS-created material in the public domain. Every candidate was mechanically
preflighted on 2026-07-18: the source zip was downloaded, confirmed to be a
valid archive with a current (non-expired) service calendar, checked for size,
then deleted. The subdivision was set to the ISO 3166-2 code, and each feed was
deduplicated against the registry by URL, agency name, and MDB id. The gate was
fail-closed.

Fourteen records were added across nine states.

Caltrans DDS, CC BY 4.0:

- **Artesia Transit** — California (`US-CA`). City fixed-route shuttle, calendar
  through 2028-04-30.
- **Maywood Express Shuttle** — California (`US-CA`). City shuttle, calendar
  through 2026-12-31.

National Park Service, public domain:

- **Island Explorer (Acadia National Park)** — Maine (`US-ME`), seasonal.
- **Bandelier National Monument Shuttle** — New Mexico (`US-NM`), seasonal.
- **Bryce Canyon Shuttle** — Utah (`US-UT`), seasonal.
- **Zion Canyon Shuttle** — Utah (`US-UT`), seasonal.
- **Denali National Park Courtesy Shuttle** — Alaska (`US-AK`), seasonal.
- **Going-to-the-Sun Road Shuttle (Glacier National Park)** — Montana (`US-MT`),
  seasonal.
- **Giant Forest Shuttle (Sequoia National Park)** — California (`US-CA`),
  seasonal.
- **Mariposa Grove Shuttle (Yosemite National Park)** — California (`US-CA`),
  seasonal.
- **Yosemite Valley Shuttle** — California (`US-CA`), year-round.
- **Harpers Ferry Shuttle** — West Virginia (`US-WV`), year-round.
- **Fort Matanzas Ferry** — Florida (`US-FL`), year-round.
- **Fort Sumter Ferry** — South Carolina (`US-SC`), year-round.

The review rejected more than it kept, and the rejections are the point:

- **Expired calendar:** the Yurok Tribe feed on Caltrans DDS ended 2026-06-28,
  and the Havasu Landing Resort ferry feed ended 2025-06-30 (and is a private
  resort service, not a public agency). Every DDS "Flex" dial-a-ride and
  paratransit feed reviewed (Manteca, Tulare County, Valley Express, Union City,
  MOVE Stanislaus) was frozen on a 2022 to 2024 calendar, the same stale DDS
  packaging already recorded for City of Wasco. The Grand Canyon South Rim
  Shuttle NPS feed had expired on 2026-05-22.
- **Already in the registry:** several NPS feeds are already carried, so they
  were skipped by URL match rather than added a second time (Dry Tortugas and
  Pensacola Bay City Ferry in Florida, Ship Island in Mississippi, Cape Lookout
  in North Carolina, Boston Harbor Islands in New York and Massachusetts, Rocky
  Mountain in Colorado, Alcatraz in California). The DDS-hosted Reds Meadow
  Shuttle for Devils Postpile is published by Trillium as Eastern Sierra Transit
  Authority, which is already tracked, so it was left out to avoid a duplicate.
- **Not small or rural:** the Statue of Liberty ferries are a high-volume urban
  NPS service, off theme for this wave, so they were not added even though the
  feed is current and public domain.

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

### Hong Kong frequency-based schedule canary

| | |
|---|---|
| GTFS Schedule | `https://static.data.gov.hk/td/pt-headway-en/gtfs.zip` |
| Location | Hong Kong (`HK`), with no ISO 3166-2 subdivision |
| Publisher | [Hong Kong Transport Department through DATA.GOV.HK](https://data.gov.hk/en-data/dataset/hk-td-tis_11-pt-headway-en) |
| Reuse terms | [DATA.GOV.HK Terms of Use 1.2](https://data.gov.hk/en/terms-and-conditions), permitting commercial and non-commercial reuse with attribution |
| Update cadence | Biweekly, as stated by DATA.GOV.HK |

The English aggregate was preflighted on 2026-07-22. It is a valid 13 MiB ZIP
with ten GTFS files, 2,455 routes, 82,692 trips, and bus, ferry, tram/light rail,
and funicular service. Fourteen publishers appear in `agency.txt`; this remains
one feed record, not a claim of fourteen separately curated agencies. The
archive uses `frequencies.txt`, has no `feed_info.txt`, and carries weekly
calendar rows from 2020 through 2099. A complete ad-hoc scorecard run with the
Hong Kong country flag produced an 85 freshness score: it deducted for the
missing validity declaration and labeled the 2099 horizon unusually distant.
That explicit warning resolves the earlier technical hold without implying that
the far-future calendar proves maintenance.

Community or informal feeds in lower- and middle-income countries follow the
partnership and consent gate in
[ADR 0028](decisions/0028-global-south-pilot.md); they are not added merely to
create a broader-looking map.

## Japan gtfs-data.jp sixth wave

A sixth pass over the same national repository ([gtfs-data.jp](https://gtfs-data.jp/),
operated by AIGID). The five prior waves lifted Japan to 185 records across 40
prefectures. This wave only goes deeper inside prefectures already represented,
because the seven prefectures still missing carry no admitted-license feed in the
catalog. Forty records were added, lifting Japan from 185 to 225 records, still
across the same 40 prefectures. Every candidate is a distinct operator not already
tracked, confirmed official through the repository, and mechanically preflighted on
2026-07-18: the download was opened, its GTFS core tables and a current, non-expired
service calendar were confirmed by reading calendar.txt and calendar_dates.txt
directly, its size was checked against the standard ingestion caps, and the archive
was deleted after the check.

The license mix of the forty is 34 CC BY 4.0, 4 CC0 1.0, and 2 CC BY 2.1 JP, the
same three admitted licenses as before, with the exact version stated in each
record's `license_note` and attribution. Six of the forty are first-party private
operators rather than municipal community buses: Toshin Kanko Bus (Nagano),
Shirotori Kotsu (Gifu), Busnet Tsu running the Gurutto-Tsu service (Mie), and Koryo
Kotsu, Kuroiwa Kanko, and Reihoku Kanko Jidosha (all Kochi).

Fifteen prefectures deepened, each operator distinct from those already tracked
(license in parentheses where not CC BY 4.0):

- **Aomori (`JP-02`)**: Shichinohe Town Community Bus, Fukaura Town Community Bus,
  Tsugaru City Community Transit.
- **Yamagata (`JP-06`)**: Yamagata City Bus, Sagae City Bus, Nanyo City Bus, Tendo
  City Bus.
- **Tochigi (`JP-09`)**: Mibu Town Community Bus, Yaita City Central Loop Bus.
- **Chiba (`JP-12`)**: Inzai City Route Bus.
- **Toyama (`JP-16`)**: Oyabe City Bus (CC0 1.0), Tonami City Bus (CC0 1.0).
- **Nagano (`JP-20`)**: Ueda City Orange Bus, Karuizawa Town Loop Bus, Toshin Kanko
  Bus (CC0 1.0).
- **Gifu (`JP-21`)**: Shirotori Kotsu, Tajimi City Kikyo Bus, Gero City Gero Bus,
  Nakatsugawa City Community Bus.
- **Aichi (`JP-23`)**: Chita City Aiai Bus, Tokai City Ran-Ran Bus, Shinshiro City
  S-Bus.
- **Mie (`JP-24`)**: Gurutto-Tsu Bus (Busnet Tsu), Nabari City Community Bus,
  Kameyama City Community Bus.
- **Shiga (`JP-25`)**: Yasu City Onori-Yasu Bus, Konan City Megurukun Bus.
- **Hyogo (`JP-28`)**: Sumoto City Community Bus (CC BY 2.1 JP), Sayo Town Community
  Bus (CC BY 2.1 JP).
- **Wakayama (`JP-30`)**: Katsuragi Town Community Bus (CC0 1.0).
- **Tokushima (`JP-36`)**: Yoshinogawa City Bus, Naka Town Bus.
- **Kochi (`JP-39`)**: Konan City Bus, Koryo Kotsu, Kuroiwa Kanko, Reihoku Kanko
  Jidosha.
- **Fukuoka (`JP-40`)**: Buzen City Bus, Ashiya Town Bus, Fukutsu Mini-Bus, Miyama
  City Community Bus.

The exclusions carry the discipline:

- **Expired calendar behind a future end date:** Nishiwaki City (Hyogo) advertised a
  window into 2027, but its `rid=current` archive held a calendar.txt whose weekday
  and Saturday service ended 2026-03-31, and its calendar_dates.txt carried only
  removals after that, so no service day remained at the review. It was rejected.
  Nanbu Town (Yamanashi) was rechecked and still served a calendar.txt ending
  2026-03-31, unchanged from the fifth wave. Both were caught by reading the calendar
  by hand rather than trusting the catalog's advertised end date.
- **Near-term expiry held for margin:** Shoo Town (Okayama) carried a catalog end
  date of 2026-08-31, about six weeks past the review. It was set aside for a later
  wave rather than admitted at the edge of its window.
- **One feed per operator:** operators that publish only line-level or area-level
  exports were passed over. Nakatsu City (Oita) publishes eighteen line feeds,
  Saitama City publishes per-route feeds, Minami-Shinshu publishes eleven area feeds,
  and private operators including Nagaden Bus and Mie Kotsu split their networks into
  per-region feeds. None yields one feed for the whole network.
- **Not a public network:** the Radiant City Yokohama shuttle (Daishinto, Kanagawa)
  remains excluded as a single residential complex's service, consistent with prior
  waves. It was the only single-feed Kanagawa candidate.
- **Unversioned license:** the catalog's two feeds under a bare "CC-BY", with no
  resolvable version, stayed rejected. Only the three named, versioned Creative
  Commons licenses were admitted.
- **Discontinued:** the feeds the catalog flags as discontinued were excluded by
  construction.
- **Seven priority prefectures still empty:** Fukui (`JP-18`), Kyoto (`JP-26`),
  Tottori (`JP-31`), Hiroshima (`JP-34`), Yamaguchi (`JP-35`), Ehime (`JP-38`),
  and Miyazaki (`JP-45`) still carry zero feeds under an admitted license anywhere
  in the catalog. They stay unrepresented; no aggregator mirror was used.
- **Capped for review quality:** the catalog listed 222 distinct new operators under
  an admitted license with a future service window in its metadata, after deduping
  against the registry. Forty-two were preflighted by hand for this wave, forty
  passed and were kept, and the rest of the pool is held for later waves.

## Japan gtfs-data.jp seventh wave

Five bounded follow-on loops were reviewed from Japan's national
[GTFS Data Repository](https://gtfs-data.jp/) on 2026-07-23. The repository's
[v2 API](https://docs.gtfs-data.jp/api.v2.html) supplied the current file,
publisher identity, service window, and exact Creative Commons license for each
record. This wave lifts Japan from 225 to 230 feed records across the same 40
prefectures. It adds regional depth, not a new claim of national coverage.

Each current archive was downloaded once, scored from the pinned local bytes,
and run through the canonical MobilityData validator before admission:

- **Hokkaido (`JP-01`)**: Kamishihoro Town Autonomous Bus, CC BY 4.0,
  service through 2026-10-31, score 76.0 (C).
- **Aomori (`JP-02`)**: Konan Railway, CC BY 4.0, service through
  2027-03-31, score 69.0 (D).
- **Ibaraki (`JP-08`)**: Tsukubane-go, CC BY 4.0, service through
  2026-12-31, score 80.1 (B).
- **Hyogo (`JP-28`)**: Awaji Jenova Line's Akashi–Iwaya passenger ferry,
  CC BY 2.1 JP, service through 2027-03-31, score 80.1 (B).
- **Okayama (`JP-33`)**: Hokushin Bus, CC0 1.0, service through
  2027-03-08, score 80.5 (B).

One candidate remained excluded. Tsuku Bus was rechecked because its catalog
window now runs through 2027-12-31, but the current archive names four required
GTFS tables `calendar.csv`, `calendar_dates.csv`, `shapes.csv`, and
`stop_times.csv`. The standard requires their `.txt` filenames, so the
canonical validator reports a missing required file and no usable service
calendar. The independently published Tsukubane-go feed passed; its admission
does not clear or conceal the Tsuku Bus hold.

## Japan gtfs-data.jp eighth wave

Five further records were selected from Japan's national
[GTFS Data Repository](https://gtfs-data.jp/) on 2026-07-23 for the different
operating questions they expose, rather than to inflate a prefecture count.
The repository's [v2 API](https://docs.gtfs-data.jp/api.v2.html) supplied each
publisher, current service window, exact Creative Commons license, and, where
present, official realtime endpoints. Japan moves from 230 to 235 reviewed feed
records across the same 40 prefectures, so this remains depth rather than a
national-coverage claim.

Each current archive passed the canonical MobilityData validator path from
pinned local bytes before admission:

- **Aomori (`JP-02`)**: JR East Tsugaru Line replacement bus, CC BY 4.0,
  service through 2027-04-30, score 75.3 (C).
- **Tokyo (`JP-13`)**: Mizuho Town Choi-Soko demand transit, CC BY 4.0,
  service through 2026-09-30, score 70.3 (C).
- **Toyama (`JP-16`)**: Toyama Chitetsu Bus, CC0 1.0, service through
  2027-05-25, score 68.2 (D). Its catalog-published TripUpdates and
  VehiclePositions both returned keyless protobuf responses and are recorded.
- **Mie (`JP-24`)**: Toba Municipal Ferry, CC BY 4.0, service through
  2028-01-31, score 65.5 (D).
- **Kochi (`JP-39`)**: Kochi Airport Shared Taxi, CC BY 4.0, service through
  2027-03-31, score 82.2 (B).

The two reservation-based services are explicitly marked as demand-responsive.
Their presence does not claim that a GTFS trip is bookable, available at the
requested time, or accessible. The replacement bus is described as published
and is not presented as restored rail service. Ferry and realtime fields remain
measured evidence, not a guarantee of vessel capacity or prediction quality.

## Japan gtfs-data.jp ninth wave

Five more records were reviewed from Japan's national
[GTFS Data Repository](https://gtfs-data.jp/) on 2026-07-23 to exercise a
bounded live-service workflow. The repository's
[v2 API](https://docs.gtfs-data.jp/api.v2.html) supplied each publisher,
current service window, exact Creative Commons license, and keyless realtime
endpoints. Japan moves from 235 to 240 reviewed feed records across the same 40
prefectures. This is regional depth, not a national-coverage claim.

Each current archive passed the canonical MobilityData validator path from
pinned local bytes before admission:

- **Toyama (`JP-16`)**: Kaetsuno World Heritage Bus, CC0 1.0, service through
  2027-03-31, score 79.6 (C).
- **Aichi (`JP-23`)**: Owari Asahi Asapy-go, CC BY 4.0, service through
  2026-11-30, score 73.3 (C).
- **Aichi (`JP-23`)**: Tokoname Gruun, CC0 1.0, service through 2026-12-31,
  score 75.1 (C).
- **Mie (`JP-24`)**: Mie Kotsu's Shima-area service, CC BY 4.0, service
  through 2026-10-23, score 65.5 (D).
- **Kumamoto (`JP-43`)**: Kumamoto Dentetsu Bus, CC BY 4.0, service through
  2026-10-24, score 65.9 (D).

All ten TripUpdates and VehiclePositions endpoints returned HTTP 200 and valid
protobuf responses during the admission check. Four pairs contained only a
small feed header at that moment. Endpoint reachability therefore means only
that a configured endpoint responded in the latest scorecard sample. It does
not establish continuous availability, prediction accuracy, or meaningful
scheduled-trip coverage. Those remain separate measured fields.

## Japan gtfs-data.jp tenth wave

Twenty official records were reviewed from Japan's national
[GTFS Data Repository](https://gtfs-data.jp/) on 2026-07-23 for a larger
endpoint-kind evidence loop. The repository's
[v2 API](https://docs.gtfs-data.jp/api.v2.html) supplied each publisher,
current service window, exact Creative Commons license, and keyless realtime
endpoints. Japan moves from 240 to 260 reviewed feed records across the same 40
prefectures. This is regional depth, not a national-coverage claim.

Each current archive passed the pinned canonical MobilityData validator path
from local bytes before admission:

- **Toyama (`JP-16`, CC0 1.0, service through 2027-03-31)**: Kaetsuno Himi
  City Loop Bus, 77.9 (C); Kaetsuno Route Bus, 75.2 (C); Kamiichi Town Bus,
  73.3 (C); Kurobe City Bus, 66.1 (D); Nyuzen Noran My Car, 76.2 (C); Asahi
  Town Bus, 75.0 (C); Toyama Yamada Community Bus, 75.1 (C); Toyama Fuchu
  Community Bus, 72.5 (C); Toyama Oyama Community Bus, 71.5 (C); Toyama
  Maidohaya Bus, 75.3 (C); Toyama Horikawa Minami Community Bus, 76.2 (C);
  Toyama Yatsuo Community Bus, 70.6 (C); and Toyama Kureha Ikiiki Bus,
  72.6 (C).
- **Mie (`JP-24`, CC BY 4.0)**: Ise Okage Bus, 73.7 (C), and Komono
  Kamoshika Bus, 68.9 (D), both with service through 2026-09-13; Mie Kotsu
  Iga, 74.2 (C); Matsusaka, 75.9 (C); Yokkaichi, 74.0 (C); Kuwana,
  69.8 (D); and Ise, 71.9 (C), each with service through 2026-10-23.

All twenty records publish TripUpdates and VehiclePositions. The seven Mie
records also publish ServiceAlerts, for 47 configured endpoints in total. All
47 returned HTTP 200 and a valid protobuf response during the admission check.
Most samples contained only a feed header at that moment; the Mie Kotsu Kuwana
TripUpdates and VehiclePositions samples contained entities. The product
therefore publishes exact latest-sample endpoint-kind reachability and header
freshness separately from scheduled-trip coverage. A response does not
establish continuous uptime, alert content, prediction accuracy, or rider
information availability.

## Unitrans (ASUCD / City of Davis)

| | |
|---|---|
| GTFS Schedule | `https://unitrans.ucdavis.edu/media/gtfs/Unitrans_GTFS.zip` |
| Status | Verified 200 (after one 301 redirect; always follow redirects) |
| Passenger realtime | [Unitrans moved arrival predictions and maps from UmoIQ to Swiftly on March 2, 2026](https://unitrans.ucdavis.edu/news/new-arrival-predictions-website-and-maps-unitrans-website). Google Maps, Apple Maps, and Transit were already consuming the Swiftly-provided information at announcement time. |
| GTFS-Realtime measurement | No public Swiftly GTFS-RT endpoint, agency key, or credential path was documented on the Unitrans GTFS or announcement pages when rechecked July 18, 2026. The scorecard therefore leaves realtime unmeasured rather than probing the retired UmoIQ integration or treating the unknown as a zero. |
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
- The prior UmoIQ endpoint record became stale when the public passenger system
  moved to Swiftly. Realtime scoring now requires a documented Swiftly endpoint
  and any required access terms. Until those are public, the category states
  that it is unmeasured and does not affect the grade.

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
