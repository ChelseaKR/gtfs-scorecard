# Hand-verified feed references

Source endpoints, licenses, and polling etiquette for the original Yolo County
pilots and the first worldwide canaries. This page is the hand-verified
reference; the full registry has more than 1,150 feed records, still mostly in
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

- **Morebus, Great Britain (`GB-BCP`)** is a bus feed with four GoSouthCoast
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
named: Spain, France, Great Britain, Germany, and Italy. Provider source,
reuse terms, current download, service calendar, archive size, and feed
identity were checked on 2026-07-17. Candidates were drawn from the Mobility
Database catalog, mechanically preflighted (live ZIP, required GTFS files,
size caps, calendar coverage), and then reviewed for reuse terms and identity.
More candidates were rejected than added; the rejection reasons are listed in
[global-expansion.md](global-expansion.md).

- **Great Britain (ten records)**: Nottingham City Transport, Reading Buses,
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
