# Superseded feed records in the Mobility Database

Run 2026-10-26. Source: mobilitydatabase.org catalog CSV.

The Mobility Database marks a replaced feed record `deprecated` and names the record that replaced it. Where both records are tracked here, the retired one is set to `feed_status: deprecated` with `alias_of` pointing at its successor: its dated artifacts stay available for reproducibility and its scorecard URL redirects, but it stops publishing a second current grade under the same agency's name.

- **0** retired records resolve to a successor published here.
- **104** retired records do not, and keep their own page.

- **2** of those retirements are **held for review**: the successor is in a different state, or carries a name that does not read as this agency renamed. They are not recorded until a decision for each is in `supersession-review.yaml`.

## Held for review

Each of these is a retirement the catalog asks for where the two records do not look like one agency. Read the pair, then record the decision in `supersession-review.yaml` at the repository root: `retire` if it is the same agency or a real merger, `keep_separate` if it is not. Until then the retirement is not written, and the build fails if one is written without a decision.

### MATBUS (`matbus`) to City of Fargo (`city-of-fargo`)

- Catalog redirect: mdb-1285 to ntd-80003
- Held because the successor's name does not read as a rename of this one.

```yaml
  - agency_id: matbus
    successor_id: city-of-fargo
    flags: [name_not_a_rename]
    decision: retire  # or keep_separate
    evidence: >-
      why this pairing is right, or why it is not
```

### Norwalk Transit System (NTS) (`norwalk-transit-system-nts`) to Norwalk Transit District (`norwalk-transit-system-nts-2242`)

- Catalog redirect: mdb-102 to mdb-2242
- Held because the successor is in a different state or province.

```yaml
  - agency_id: norwalk-transit-system-nts
    successor_id: norwalk-transit-system-nts-2242
    flags: [different_subdivision]
    decision: retire  # or keep_separate
    evidence: >-
      why this pairing is right, or why it is not
```

## Retired, with no successor we publish

These stay published on their own record. The catalog has retired the feed source, so the grade describes a feed the agency may no longer publish; deciding what to say on those pages is a curator call, not a mechanical one.

- Altamont Corridor Express (`altamont-corridor-express`, mdb-1133): the successor record is not published here. It points at mdb-2684.
- Aléop (Pays de la Loire) (`aleop-pays-de-la-loire`, mdb-1096): the successor record is not published here. It points at tdg-80721.
- Aléop Yeu-Continent (Île d'Yeu ferry) (`aleop-yeu-continent`, mdb-1257): the successor record is not published here. It points at tdg-82641.
- Anaheim Resort Transportation (ART) (`anaheim-resort-transportation-art`, mdb-100): the catalog names no successor it still calls current.
- Arvin Transit (`arvin-transit`, mdb-216): the successor record is not published here. It points at mdb-2233.
- Baldwin Park Transit (`baldwin-park-transit`, mdb-219): the successor record is not published here. It points at mdb-2247.
- Beach Cities Transit (`beach-cities-transit`, mdb-803): the successor record is not published here. It points at mdb-1999.
- Bellflower Bus (`bellflower-bus`, mdb-227): the successor record is not published here. It points at mdb-3095.
- Beloit Transit (`beloit-transit`, mdb-392): the successor record is not published here. It points at tld-77.
- Bibus (Brest) (`bibus-brest`, mdb-999): the successor record is not published here. It points at tdg-81559.
- Biddeford Saco Old Orchard Beach Transit (`biddeford-saco-old-orchard-beach-transit`, mdb-2300): the successor record is not published here. It points at tld-4756.
- Blue Star Bus (`blue-star-bus`, mdb-256): the catalog names no successor it still calls current.
- Boulder County (`boulder-county`, mdb-880): the successor record is not published here. It points at mdb-2191.
- Breeze Transit (`breeze-transit`, mdb-2260): the successor record is not published here. It points at tld-351_1.
- Broward County Transit (`broward-county-transit`, mdb-330): the successor record is not published here. It points at mdb-3534.
- Buc Shuttle (`buc-shuttle`, mdb-371): the catalog names no successor it still calls current.
- Butte Regional Transit (B-Line) (`butte-regional-transit-b-line`, mdb-241): the successor record is not published here. It points at ntd-90208.
- Camarillo Area Transit (`camarillo-area-transit`, mdb-297): the successor record is not published here. It points at mdb-2234.
- Capital Trailways (`capital-trailways`, mdb-1308): the catalog names no successor it still calls current.
- Car Jaune (La Réunion) (`car-jaune-reunion`, mdb-2458): the successor record is not published here. It points at tdg-80934.
- Cara'bus (Royan) (`carabus-royan`, mdb-2842): the successor record is not published here. It points at tdg-82361.
- Cars Régionaux 23 — Creuse (`cars-regionaux-23-creuse`, mdb-2686): the successor record is not published here. It points at tdg-82330.
- Cascades East Transit (CET) (`cascades-east-transit-cet`, mdb-138): the successor record is not published here. It points at tld-170.
- Casco Bay Lines (`casco-bay-lines`, mdb-1): the successor record is not published here. It points at mdb-3537.
- CATABUS (`centre-county-transit-authority-cata`, mdb-1236): the successor record is not published here. It points at tld-366.
- Champaign Urbana Mass Transit District (MTD) (`champaign-urbana-mass-transit-district-mtd`, mdb-388): the successor record is not published here. It points at ntd-50060.
- Chapel Hill Transit (CHT) (`chapel-hill-transit-cht`, mdb-376): the successor record is not published here. It points at tld-89.
- Choletbus (`choletbus`, mdb-1789): the successor record is not published here. It points at tdg-79352.
- City of Glendale (`city-of-glendale`, mdb-1245): the successor record is not published here. It points at tld-471.
- City of Lompoc Transit (COLT) (`city-of-lompoc-transit-colt`, mdb-919): the successor record is not published here. It points at tld-1654.
- City of Sierra Vista (`city-of-sierra-vista`, mdb-145): the successor record is not published here. It points at tld-679.
- City of Tracy (TRACER) (`city-of-tracy-tracer`, mdb-877): the successor record is not published here. It points at mdb-3099.
- Clallam Transit System (`clallam-transit-system`, mdb-279): the successor record is not published here. It points at mdb-3532.
- CRTM — Red de EMT (Madrid city bus) (`crtm-red-de-emt`, mdb-993): the successor record is not published here. It points at mdb-2720.
- DiviaMobilités (Dijon) (`divia-dijon`, mdb-2153): the successor record is not published here. It points at tdg-80742.
- El Paso Transportation Authority (`el-paso-transportation-authority`, mdb-3202): the successor record is not published here. It points at mdb-3419.
- Elevated Transit (`elevated-transit`, mdb-1207): the catalog names no successor it still calls current.
- Eurostar (`eurostar`, mdb-2431): the successor record is not published here. It points at tdg-82199.
- Fil Bleu (Tours) (`fil-bleu-tours`, mdb-1987): the successor record is not published here. It points at tdg-80694.
- Fredericksburg Regional Transit (`fredericksburg-regional-transit-2430`, mdb-2430): the successor record is not published here. It points at mdb-3433.
- Ginko (Besançon) (`ginko-besancon`, mdb-1116): the successor record is not published here. It points at tdg-80590.
- Glendale Beeline (`glendale-beeline`, mdb-1280): the successor record is not published here. It points at mdb-3177, tld-471.
- Glendora Transportation Division (`glendora-transportation-division`, mdb-609): the successor record is not published here. It points at mdb-3097.
- GoDurham (`godurham`, mdb-377): the successor record is not published here. It points at tld-98.
- GoWal (`gowal`, mdb-610): the catalog names no successor it still calls current.
- Hawai'i Mass Transit Agency (Hele-On Bus) (`hawai-i-mass-transit-agency-hele-on-bus`, mdb-557): the successor record is not published here. It points at mdb-2608.
- Huntington Park Express (`huntington-park-express`, mdb-558): the successor record is not published here. It points at mdb-2648.
- ilévia (Métropole Européenne de Lille) (`ilevia-lille`, mdb-2152): the successor record is not published here. It points at tdg-81995.
- Impulsyon (La Roche-sur-Yon) (`impulsyon-la-roche-sur-yon`, mdb-2005): the successor record is not published here. It points at tdg-79520.
- JAUNT Inc (`jaunt-inc`, mdb-1324): the successor record is not published here. It points at tld-4144.
- Jump Around Carson (`jump-around-carson`, mdb-95): the successor record is not published here. It points at tld-688.
- Kalamazoo Metro Transit (`kalamazoo-metro-transit-2070`, mdb-2070): the successor record is not published here. It points at tld-674.
- Kicéo (Vannes) (`kiceo-vannes`, mdb-656): the successor record is not published here. It points at tdg-82553.
- Knoxville Area Transit (KAT) (`knoxville-area-transit-kat`, mdb-1121): the successor record is not published here. It points at mdb-3512.
- Lakeland Area Mass Transit (`lakeland-area-mass-transit`, mdb-321): the successor record is not published here. It points at tld-5899.
- LakeXpress (`lakexpress`, mdb-342): the successor record is not published here. It points at tld-942.
- LE MET' (Metz) (`le-met-metz`, mdb-1298): the successor record is not published here. It points at tdg-80725.
- Lehigh and Northampton Transportation Authority (LANTA) (`lehigh-and-northampton-transportation-authority-lanta`, mdb-506): the successor record is not published here. It points at ntd-30010.
- Lignes d'Azur (Nice) (`lignes-dazur-nice`, mdb-845): the successor record is not published here. It points at tdg-82136, tdg-82137, tdg-82285.
- LimoLiner (`limoliner`, mdb-438): the catalog names no successor it still calls current.
- Madison County Transit (`madison-county-transit-1145`, mdb-1145): the successor record is not published here. It points at tld-4136.
- Marinéo (Boulogne-sur-Mer) (`marineo-boulogne`, mdb-1876): the successor record is not published here. It points at tdg-51449.
- Massachusetts Area Express (MAX) (`massachusetts-area-express-max`, mdb-431): the catalog names no successor it still calls current.
- Memphis Area Transit Authority (`memphis-area-transit-authority-2352`, mdb-2352): the successor record is not published here. It points at tld-1655.
- Metropolitan Area Commuter System (`metropolitan-area-commuter-system`, mdb-232): the successor record is not published here. It points at mdb-3523.
- Metropolitan Tulsa Transit Authority (MTTA) (`metropolitan-tulsa-transit-authority-mtta`, mdb-184): the successor record is not published here. It points at tld-235.
- Mountain Rides Transportation Authority (MRTA) (`mountain-rides-transportation-authority-mrta`, mdb-143): the successor record is not published here. It points at mdb-2282.
- Métropole Aix-Marseille-Provence networks (`aix-marseille-provence`, mdb-2133): the successor record is not published here. It points at tdg-39601.
- Neobus (Ouest Vosgien) (`neobus-ouest-vosgien`, mdb-1839): the successor record is not published here. It points at tdg-79814.
- Niagara Frontier Transportation Authority (NFTA) (`niagara-frontier-transportation-authority-nfta`, mdb-465): the successor record is not published here. It points at tld-401.
- Ondéa (Aix-les-Bains) (`ondea-aix-les-bains`, mdb-600): the successor record is not published here. It points at tdg-71223.
- Orizo (Grand Avignon) (`orizo-grand-avignon`, mdb-1878): the successor record is not published here. It points at tdg-9279.
- Palo Verde Valley Transit Agency (`palo-verde-valley-transit-agency`, mdb-18): the successor record is not published here. It points at mdb-2190.
- Petaluma Transit (`petaluma-transit`, mdb-72): the successor record is not published here. It points at mdb-2947.
- Renfe (Alta Velocidad, Larga y Media Distancia) (`renfe-alta-larga-media`, mdb-2620): the successor record is not published here. It points at tdg-82386.
- RIDE Sitka (`ride-sitka`, mdb-1293): the catalog names no successor it still calls current.
- Ridgerunner (`ridgerunner`, mdb-311): the successor record is not published here. It points at mdb-2279.
- Roosevelt Island Operating Corporation Tramway (RIOC Tramway) (`roosevelt-island-operating-corporation-tramway-rioc-tramway`, mdb-1109): the successor record is not published here. It points at tld-3364.
- Rosemead Explorer (`rosemead-explorer`, mdb-806): the successor record is not published here. It points at mdb-3098.
- Réseau Léo (Communauté d'Agglomération de l'Auxerrois) (`leo-auxerrois`, mdb-642): the successor record is not published here. It points at tdg-78934.
- Réseau Mistral (Toulon) (`reseau-mistral-toulon`, mdb-1820): the successor record is not published here. It points at tdg-79560.
- Réseau Stan (Nancy) (`stan-nancy`, mdb-1256): the successor record is not published here. It points at tdg-81346.
- Réseau urbain Cap Cotentin (`cap-cotentin`, mdb-1840): the successor record is not published here. It points at tdg-79831.
- Sacramento Regional Transit (SacRT) (`sacramento-regional-transit-sacrt`, mdb-1296): the successor record is not published here. It points at mdb-2137.
- San Juan Capistrano Free Weekend Trolley (`san-juan-capistrano-free-weekend-trolley`, mdb-596): the successor record is not published here. It points at mdb-2235.
- San Mateo County Transit District (samTrans) (`san-mateo-county-transit-district-samtrans`, mdb-49): the successor record is not published here. It points at mdb-2708.
- Seastreak Ferry (`seastreak-ferry`, mdb-549): the successor record is not published here. It points at ntd-20226.
- SEMO (Seine-Eure) (`semo-seine-eure`, mdb-1838): the successor record is not published here. It points at tdg-81338.
- Service Discontinued (`dc-circulator`, mdb-486): the catalog names no successor it still calls current.
- Sonoma-Marin Area Rail Transit (SMART) (`sonoma-marin-area-rail-transit-smart`, mdb-815): the successor record is not published here. It points at mdb-3222.
- St Lawrence County Public Transit (`st-lawrence-county-public-transit`, mdb-5): the successor record is not published here. It points at mdb-2608.
- T'MM (Moselle et Madon) (`tmm-moselle-madon`, mdb-2738): the successor record is not published here. It points at tdg-82388.
- Taft Area Transit (`taft-area-transit`, mdb-821): the successor record is not published here. It points at mdb-2236.
- Transfort – City of Fort Collins (Transfort) (`transfort-city-of-fort-collins-transfort`, mdb-179): the successor record is not published here. It points at mdb-3521.
- Transports Bordeaux Métropole (TBM) (`tbm-bordeaux-metropole`, mdb-2622): the successor record is not published here. It points at tdg-83024.
- Tri Delta Transit (`tri-delta-transit`, mdb-1323): the successor record is not published here. It points at mdb-1974.
- Verkehrsverbund Hegau-Bodensee (VHB) (`vhb-hegau-bodensee`, mdb-914): the successor record is not published here. It points at mdb-2393.
- VIA Metropolitan Transit (VIA) (`via-metropolitan-transit-via-2348`, mdb-2348): the successor record is not published here. It points at tld-217.
- Virginia Railway Express (VRE) (`virginia-railway-express-vre`, mdb-478): the successor record is not published here. It points at tld-61.
- Wave Transit (`wave-transit`, mdb-1110): the successor record is not published here. It points at mdb-3536.
- West Berkeley Shuttle (`west-berkeley-shuttle`, mdb-622): the successor record is not published here. It points at mdb-2238.
- Western Reserve Transit Authority (`western-reserve-transit-authority`, mdb-922): the successor record is not published here. It points at tld-1717.
- Wichita Transit (`wichita-transit`, mdb-185): the successor record is not published here. It points at tld-395.
- Xpress (`xpress-2355`, mdb-2355): the successor record is not published here. It points at mdb-2426.

## Retired, with a successor we do not track yet

The catalog retired the record each of these is tracked on and names one current record that replaced it. The edit keeps the scorecard and its history and moves `static_gtfs_url` and `mdb_id` to the successor (ADR 0069). Nothing is added and no page is created.

- **19** are ready: open, the same agency by the review rules, and allowed by the successor host's robots.txt.
- **55** are held for a person, with the reason.

- Beloit Transit (`beloit-transit`): mdb-392 to tld-77, now https://passio3.com/beloit/passioTransit/gtfs/google_transit.zip
- Biddeford Saco Old Orchard Beach Transit (`biddeford-saco-old-orchard-beach-transit`): mdb-2300 to tld-4756, now https://gtfs.remix.com/bsoob_transit_biddeford_me_us.zip
- Broward County Transit (`broward-county-transit`): mdb-330 to mdb-3534, now https://www.arcgis.com/sharing/rest/content/items/acd9791dc1fd49a8aaeaab261dd61b89/data
- Cascades East Transit (CET) (`cascades-east-transit-cet`): mdb-138 to tld-170, now https://passio3.com/cet/passioTransit/gtfs/google_transit.zip
- Casco Bay Lines (`casco-bay-lines`): mdb-1 to mdb-3537, now https://gtfs.remix.com/Casco_Bay_Lines_Portland_ME_USA.zip
- City of Sierra Vista (`city-of-sierra-vista`): mdb-145 to tld-679, now https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/12009/VistaTransit_AZ_GTFS.zip
- City of Tracy (TRACER) (`city-of-tracy-tracer`): mdb-877 to mdb-3099, now https://s3.amazonaws.com/etatransit.gtfs/tracer.etaspot.net/gtfs.zip
- Clallam Transit System (`clallam-transit-system`): mdb-279 to mdb-3532, now https://irp.cdn-website.com/0eaf265e/files/uploaded/clallam_transit_gtfs.zip
- El Paso Transportation Authority (`el-paso-transportation-authority`): mdb-3202 to mdb-3419, now https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/11511/GTFS_EPCT.zip
- GoDurham (`godurham`): mdb-377 to tld-98, now https://godurham.rideralerts.com/InfoPoint/GTFS-Zip.ashx
- Kalamazoo Metro Transit (`kalamazoo-metro-transit-2070`): mdb-2070 to tld-674, now https://trackmybus.kmetro.org/InfoPoint/GTFS-Zip.ashx
- Lakeland Area Mass Transit (`lakeland-area-mass-transit`): mdb-321 to tld-5899, now https://passio3.com/citrusconn/passioTransit/gtfs/google_transit.zip
- Lehigh and Northampton Transportation Authority (LANTA) (`lehigh-and-northampton-transportation-authority-lanta`): mdb-506 to ntd-30010, now https://realtimelanta.availtec.com/InfoPoint/gtfs-zip.ashx
- Metropolitan Area Commuter System (`metropolitan-area-commuter-system`): mdb-232 to mdb-3523, now https://fnsb.gov/DocumentCenter/View/24935/General-Transit-Feed-Specification-2025zip
- Metropolitan Tulsa Transit Authority (MTTA) (`metropolitan-tulsa-transit-authority-mtta`): mdb-184 to tld-235, now https://tulsa.rideralerts.com/InfoPoint/GTFS-Zip.ashx
- Niagara Frontier Transportation Authority (NFTA) (`niagara-frontier-transportation-authority-nfta`): mdb-465 to tld-401, now https://metro.nfta.com/__googletransit/google_transit.zip
- Roosevelt Island Operating Corporation Tramway (RIOC Tramway) (`roosevelt-island-operating-corporation-tramway-rioc-tramway`): mdb-1109 to tld-3364, now https://data.trilliumtransit.com/gtfs/rooseveltisland-ny-us/rooseveltisland-ny-us.zip
- VIA Metropolitan Transit (VIA) (`via-metropolitan-transit-via-2348`): mdb-2348 to tld-217, now http://www.viainfo.net/BusService/google_transit.zip
- Western Reserve Transit Authority (`western-reserve-transit-authority`): mdb-922 to tld-1717, now https://myvalleystops.wrtaonline.com/InfoPoint/gtfs-zip.ashx

### Held

- Altamont Corridor Express (`altamont-corridor-express`): mdb-1133 to mdb-2684 (http://api.511.org/transit/datafeeds?operator_id=CE). Held: the successor needs a key, is marked unofficial, or has no usable URL.
- Aléop (Pays de la Loire) (`aleop-pays-de-la-loire`): mdb-1096 to tdg-80721 (https://www.data.gouv.fr/api/1/datasets/r/916752e4-5daa-48bd-8bc1-4dd8d64f1d4a). Held: not fetched: the successor host's robots.txt disallows this path.
- Aléop Yeu-Continent (Île d'Yeu ferry) (`aleop-yeu-continent`): mdb-1257 to tdg-82641 (https://www.data.gouv.fr/api/1/datasets/r/b57c66f2-ecaf-4934-a530-753bcb8aad04). Held: the successor's name does not read as a rename of this one.
- Baldwin Park Transit (`baldwin-park-transit`): mdb-219 to mdb-2247 (https://baldwinpark.tectransit.com/api/public/fixedRoute/gtfs). Held: the successor host's /robots.txt could not be read.
- Bibus (Brest) (`bibus-brest`): mdb-999 to tdg-81559 (https://www.data.gouv.fr/api/1/datasets/r/8c7b32d0-6481-4bb8-b903-c50a04c72fec). Held: the successor's name does not read as a rename of this one.
- Butte Regional Transit (B-Line) (`butte-regional-transit-b-line`): mdb-241 to ntd-90208 (https://planmyride.blinetransit.com/gtfsrealtime/google_transit.zip). Held: the successor is in a different state or province.
- Camarillo Area Transit (`camarillo-area-transit`): mdb-297 to mdb-2234 (https://gtfs.calitp.org/production/CamarilloGTFS.zip). Held: the successor host's /robots.txt redirects somewhere else.
- Car Jaune (La Réunion) (`car-jaune-reunion`): mdb-2458 to tdg-80934 (https://transport.data.gouv.fr/resources/80934/download?token=xdgqKBTAzhw4DSPz6zeGc4c5eW0LhwztcGv4-vpzP4U). Held: the successor's name does not read as a rename of this one.
- Cara'bus (Royan) (`carabus-royan`): mdb-2842 to tdg-82361 (https://www.data.gouv.fr/api/1/datasets/r/3af621da-a600-4da9-92c4-dfd994b22c31). Held: the successor's name does not read as a rename of this one.
- Cars Régionaux 23 — Creuse (`cars-regionaux-23-creuse`): mdb-2686 to tdg-82330 (https://www.data.gouv.fr/api/1/datasets/r/b3f2f823-fe55-4265-9efe-605d8156dea2). Held: the successor's name does not read as a rename of this one.
- CATABUS (`centre-county-transit-authority-cata`): mdb-1236 to ntd-30054 (https://catabus.com/wp-content/uploads/google_transit.zip). Held: not fetched: the successor host's robots.txt disallows this path.
- Champaign Urbana Mass Transit District (MTD) (`champaign-urbana-mass-transit-district-mtd`): mdb-388 to ntd-50060 (https://developer.mtd.org/gtfs/google_transit.zip). Held: a curator note names the host this record is tracked on.
- Chapel Hill Transit (CHT) (`chapel-hill-transit-cht`): mdb-376 to tld-89 (http://mychtransit.org/gtfs). Held: the successor host serves a web page, not rules, at /robots.txt.
- Choletbus (`choletbus`): mdb-1789 to tdg-79352 (https://www.data.gouv.fr/api/1/datasets/r/71e8ee8e-0b55-40a1-a297-21ef89aba4dc). Held: not fetched: the successor host's robots.txt disallows this path.
- City of Glendale (`city-of-glendale`): mdb-1245 to tld-471 (https://www.glendaleca.gov/home/showdocument?id=29549). Held: the successor's name does not read as a rename of this one.
- CRTM — Red de EMT (Madrid city bus) (`crtm-red-de-emt`): mdb-993 to mdb-2720 (https://www.arcgis.com/sharing/rest/content/items/1a25440bf66f499bae2657ec7fb40144/data). Held: the successor's name does not read as a rename of this one.
- DiviaMobilités (Dijon) (`divia-dijon`): mdb-2153 to tdg-80742 (https://www.data.gouv.fr/api/1/datasets/r/e0dbd217-15cd-4e28-9459-211a27511a34). Held: the successor's name does not read as a rename of this one; a curator note names the host this record is tracked on.
- Eurostar (`eurostar`): mdb-2431 to tdg-82199 (https://www.data.gouv.fr/api/1/datasets/r/bfd97acd-63f3-4ea4-bfe8-70e4c7fd8d13). Held: the successor is in a different country.
- Fil Bleu (Tours) (`fil-bleu-tours`): mdb-1987 to tdg-80694 (https://www.data.gouv.fr/api/1/datasets/r/198b7602-5e74-4d88-b6bc-483af85a2430). Held: the successor's name does not read as a rename of this one.
- Fredericksburg Regional Transit (`fredericksburg-regional-transit-2430`): mdb-2430 to mdb-3433 (https://www.fredericksburgva.gov/DocumentCenter/View/31122/FXBGO-GTFS---CY2026). Held: the successor host's /robots.txt answered 403, which the robots policy treats as off-limits.
- Ginko (Besançon) (`ginko-besancon`): mdb-1116 to tdg-80590 (https://www.data.gouv.fr/api/1/datasets/r/e18e0aeb-8805-47fd-bcdb-c226d21c96fe). Held: the successor's name does not read as a rename of this one.
- Glendale Beeline (`glendale-beeline`): mdb-1280 to mdb-3177 (https://www.glendaleca.gov/home/showdocument?id=29549). Held: the catalog's redirects reach more than one current record.
- Hawai'i Mass Transit Agency (Hele-On Bus) (`hawai-i-mass-transit-agency-hele-on-bus`): mdb-557 to mdb-2608 (https://www.heleonbus.hawaiicounty.gov/home/showpublisheddocument/307470/638458319827900000). Held: the successor host's /robots.txt answered 403, which the robots policy treats as off-limits.
- ilévia (Métropole Européenne de Lille) (`ilevia-lille`): mdb-2152 to tdg-81995 (https://www.data.gouv.fr/api/1/datasets/r/c9e5dd3f-8eed-4ad7-aec2-915240599cf6). Held: the successor's name does not read as a rename of this one.
- Impulsyon (La Roche-sur-Yon) (`impulsyon-la-roche-sur-yon`): mdb-2005 to tdg-79520 (https://www.data.gouv.fr/api/1/datasets/r/735f1b54-94ee-4a21-b378-05c2b44ad70f). Held: the successor's name does not read as a rename of this one; a curator note names the host this record is tracked on.
- Jump Around Carson (`jump-around-carson`): mdb-95 to tld-688 (https://www.carson.org/home/showpublisheddocument/88322/638424553550370000). Held: the successor host's /robots.txt could not be read.
- Kicéo (Vannes) (`kiceo-vannes`): mdb-656 to tdg-82553 (https://www.data.gouv.fr/api/1/datasets/r/565533c0-64ae-44d6-9dfa-169be5b805c6). Held: the successor's name does not read as a rename of this one.
- Knoxville Area Transit (KAT) (`knoxville-area-transit-kat`): mdb-1121 to mdb-3512 (https://knoxville.syncromatics.com/gtfs). Held: a curator note names the host this record is tracked on.
- LE MET' (Metz) (`le-met-metz`): mdb-1298 to tdg-80725 (https://www.data.gouv.fr/api/1/datasets/r/92af6161-1b1a-4e0b-8f60-d97f213d993a). Held: the successor's name does not read as a rename of this one.
- Marinéo (Boulogne-sur-Mer) (`marineo-boulogne`): mdb-1876 to tdg-51449 (https://www.data.gouv.fr/api/1/datasets/r/579e4f5e-2916-4b95-90b8-f675943d0136). Held: the successor's name does not read as a rename of this one.
- Mountain Rides Transportation Authority (MRTA) (`mountain-rides-transportation-authority-mrta`): mdb-143 to mdb-2282 (https://apps.itd.idaho.gov/apps/pt/mrtagtfs.zip). Held: the successor host's /robots.txt redirects somewhere else.
- Métropole Aix-Marseille-Provence networks (`aix-marseille-provence`): mdb-2133 to tdg-39601 (https://www.data.gouv.fr/api/1/datasets/r/ab931edc-0bc1-4c66-960a-dc546b46df03). Held: the successor's name does not read as a rename of this one.
- Neobus (Ouest Vosgien) (`neobus-ouest-vosgien`): mdb-1839 to tdg-79814 (https://www.data.gouv.fr/api/1/datasets/r/e25586ac-9c14-4872-b00e-e66cd23d4413). Held: the successor's name does not read as a rename of this one.
- Ondéa (Aix-les-Bains) (`ondea-aix-les-bains`): mdb-600 to tdg-71223 (https://www.data.gouv.fr/api/1/datasets/r/b4e8d98c-e17a-4fb0-857f-8cb618039b2a). Held: the successor's name does not read as a rename of this one.
- Petaluma Transit (`petaluma-transit`): mdb-72 to mdb-2947 (http://api.511.org/transit/datafeeds?operator_id=PE). Held: the successor needs a key, is marked unofficial, or has no usable URL.
- Renfe (Alta Velocidad, Larga y Media Distancia) (`renfe-alta-larga-media`): mdb-2620 to tdg-82386 (https://www.data.gouv.fr/api/1/datasets/r/eae0fa46-087a-4018-ada9-d8add124e635). Held: the successor's name does not read as a rename of this one.
- Réseau Léo (Communauté d'Agglomération de l'Auxerrois) (`leo-auxerrois`): mdb-642 to tdg-78934 (https://transport.data.gouv.fr/resources/78934/download?token=xdgqKBTAzhw4DSPz6zeGc4c5eW0LhwztcGv4-vpzP4U). Held: the successor's name does not read as a rename of this one.
- Réseau Mistral (Toulon) (`reseau-mistral-toulon`): mdb-1820 to tdg-79560 (https://www.data.gouv.fr/api/1/datasets/r/b0789d9e-5077-4124-b6b2-773353ada8cf). Held: the successor's name does not read as a rename of this one.
- Réseau urbain Cap Cotentin (`cap-cotentin`): mdb-1840 to tdg-79831 (https://www.data.gouv.fr/api/1/datasets/r/2e97c9b3-a59f-42dd-9b9e-a232fa771f21). Held: not fetched: the successor host's robots.txt disallows this path.
- San Juan Capistrano Free Weekend Trolley (`san-juan-capistrano-free-weekend-trolley`): mdb-596 to mdb-2235 (https://gtfs.calitp.org/production/SanJuanCapistranoGTFS.zip). Held: the successor host's /robots.txt redirects somewhere else.
- San Mateo County Transit District (samTrans) (`san-mateo-county-transit-district-samtrans`): mdb-49 to mdb-2708 (http://api.511.org/transit/datafeeds?operator_id=SM). Held: the successor needs a key, is marked unofficial, or has no usable URL; a curator note names the host this record is tracked on.
- Seastreak Ferry (`seastreak-ferry`): mdb-549 to ntd-20226 (https://seastreak.com/api/transit/google_transit.zip). Held: the successor is in a different state or province.
- SEMO (Seine-Eure) (`semo-seine-eure`): mdb-1838 to tdg-81338 (https://transport.data.gouv.fr/resources/81338/download?token=xdgqKBTAzhw4DSPz6zeGc4c5eW0LhwztcGv4-vpzP4U). Held: the successor's name does not read as a rename of this one.
- Sonoma-Marin Area Rail Transit (SMART) (`sonoma-marin-area-rail-transit-smart`): mdb-815 to mdb-3222 (http://api.511.org/transit/datafeeds?operator_id=SA). Held: the successor needs a key, is marked unofficial, or has no usable URL.
- St Lawrence County Public Transit (`st-lawrence-county-public-transit`): mdb-5 to mdb-2608 (https://www.heleonbus.hawaiicounty.gov/home/showpublisheddocument/307470/638458319827900000). Held: the successor is in a different state or province; the successor's name does not read as a rename of this one.
- T'MM (Moselle et Madon) (`tmm-moselle-madon`): mdb-2738 to tdg-82388 (https://transport.data.gouv.fr/resources/82388/download?token=xdgqKBTAzhw4DSPz6zeGc4c5eW0LhwztcGv4-vpzP4U). Held: the successor's name does not read as a rename of this one.
- Taft Area Transit (`taft-area-transit`): mdb-821 to mdb-2236 (https://gtfs.calitp.org/production/TaftGTFS.zip). Held: the successor host's /robots.txt redirects somewhere else.
- Transfort – City of Fort Collins (Transfort) (`transfort-city-of-fort-collins-transfort`): mdb-179 to mdb-3521 (https://ridetransfort.com/wp-content/uploads/transfort_gtfs.zip). Held: a curator note names the host this record is tracked on.
- Transports Bordeaux Métropole (TBM) (`tbm-bordeaux-metropole`): mdb-2622 to tdg-83024 (https://www.data.gouv.fr/api/1/datasets/r/10b87ffe-e6bb-494d-93df-bb6019e223d9). Held: the successor's name does not read as a rename of this one.
- Tri Delta Transit (`tri-delta-transit`): mdb-1323 to mdb-1974 (http://api.511.org/transit/datafeeds?operator_id=3D). Held: the successor needs a key, is marked unofficial, or has no usable URL.
- Verkehrsverbund Hegau-Bodensee (VHB) (`vhb-hegau-bodensee`): mdb-914 to mdb-2393 (https://www.nvbw.de/fileadmin/user_upload/service/open_data/fahrplandaten_mit_liniennetz/bwgesamt.zip). Held: the successor's name does not read as a rename of this one.
- Virginia Railway Express (VRE) (`virginia-railway-express-vre`): mdb-478 to tld-61 (https://gtfs.vre.org/containercdngtfsupload/google_transit.zip). Held: the successor host's /robots.txt answered 400, which the robots policy treats as off-limits.
- Wave Transit (`wave-transit`): mdb-1110 to mdb-3536 (https://wave.connexionz.net/rtt/public/resource/gtfs.zip). Held: the successor's name does not read as a rename of this one.
- West Berkeley Shuttle (`west-berkeley-shuttle`): mdb-622 to mdb-2238 (https://gtfs.calitp.org/production/WestBerkeleyShuttleGTFS.zip). Held: the successor host's /robots.txt redirects somewhere else.
- Wichita Transit (`wichita-transit`): mdb-185 to tld-395 (https://bus.wichitatransit.org/InfoPoint/gtfs-zip.ashx). Held: a curator note names the host this record is tracked on.
