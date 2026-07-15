# Hand-verified feed references

Source endpoints, licenses, and polling etiquette for the original Yolo County
pilots and the first worldwide canaries. This page is the hand-verified
reference; the full registry has more than 1,100 feed records, still mostly in
the United States and Canada, and lives in the explicit shards listed by
`registry/index.yaml`, with the discovery process documented in
`docs/feed-discovery.md`. Every URL below was verified with a live request on
the date stamped at the bottom of this page.

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

Last verified: 2026-07-12 · Recheck cadence: monthly, and before any demo.
