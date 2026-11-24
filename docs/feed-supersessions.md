# Superseded feed records in the Mobility Database

Run 2026-11-23. Source: mobilitydatabase.org catalog CSV.

The Mobility Database marks a replaced feed record `deprecated` and names the record that replaced it. Where both records are tracked here, the retired one is set to `feed_status: deprecated` with `alias_of` pointing at its successor: its dated artifacts stay available for reproducibility and its scorecard URL redirects, but it stops publishing a second current grade under the same agency's name.

- **0** retired records resolve to a successor published here.
- **85** retired records do not, and keep their own page.

- **1** of those retirements are **held for review**: the successor is in a different state, or carries a name that does not read as this agency renamed. They are not recorded until a decision for each is in `supersession-review.yaml`.

## Held for review

Each of these is a retirement the catalog asks for where the two records do not look like one agency. Read the pair, then record the decision in `supersession-review.yaml` at the repository root: `retire` if it is the same agency or a real merger, `keep_separate` if it is not. Until then the retirement is not written, and the build fails if one is written without a decision.

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
- Anaheim Resort Transportation (ART) (`anaheim-resort-transportation-art`, mdb-100): the catalog names no successor it still calls current.
- Arvin Transit (`arvin-transit`, mdb-216): the successor record is not published here. It points at mdb-2233.
- Baldwin Park Transit (`baldwin-park-transit`, mdb-219): the successor record is not published here. It points at mdb-2247.
- Beloit Transit (`beloit-transit`, mdb-392): the successor record is not in this catalog export. It points at tld-77.
- Biddeford Saco Old Orchard Beach Transit (`biddeford-saco-old-orchard-beach-transit`, mdb-2300): the successor record is not in this catalog export. It points at tld-4756.
- Blue Star Bus (`blue-star-bus`, mdb-256): the catalog names no successor it still calls current.
- Boulder County (`boulder-county`, mdb-880): the successor record is not published here. It points at mdb-2191.
- Breeze Transit (`breeze-transit`, mdb-2260): the successor record is not in this catalog export. It points at tld-351_1.
- Broward County Transit (`broward-county-transit`, mdb-330): the successor record is not published here. It points at mdb-3534.
- Buc Shuttle (`buc-shuttle`, mdb-371): the catalog names no successor it still calls current.
- Butte Regional Transit (B-Line) (`butte-regional-transit-b-line`, mdb-241): the successor record is not in this catalog export. It points at ntd-90208.
- Camarillo Area Transit (`camarillo-area-transit`, mdb-297): the successor record is not published here. It points at mdb-2234.
- Cascades East Transit (CET) (`cascades-east-transit-cet`, mdb-138): the successor record is not in this catalog export. It points at tld-170.
- Casco Bay Lines (`casco-bay-lines`, mdb-1): the successor record is not published here. It points at mdb-3537.
- CATABUS (`centre-county-transit-authority-cata`, mdb-1236): the successor record is not in this catalog export. It points at tld-366.
- Catholic Community Services (`catholic-community-services`, mdb-2158): the catalog names no successor it still calls current.
- Catholic Community Services (`catholic-community-services-2159`, mdb-2159): the catalog names no successor it still calls current.
- Catholic Community Services (`catholic-community-services-2160`, mdb-2160): the catalog names no successor it still calls current.
- Chapel Hill Transit (CHT) (`chapel-hill-transit-cht`, mdb-376): the successor record is not in this catalog export. It points at tld-89.
- City of Glendale (`city-of-glendale`, mdb-1245): the successor record is not in this catalog export. It points at tld-471.
- City of Lompoc Transit (COLT) (`city-of-lompoc-transit-colt`, mdb-919): the successor record is not in this catalog export. It points at tld-1654.
- City of Sierra Vista (`city-of-sierra-vista`, mdb-145): the successor record is not in this catalog export. It points at tld-679.
- City of Tracy (TRACER) (`city-of-tracy-tracer`, mdb-877): the successor record is not published here. It points at mdb-3099.
- Clallam Transit System (`clallam-transit-system`, mdb-279): the successor record is not published here. It points at mdb-3532.
- COAST Transportation (`coast-transportation`, mdb-2162): the catalog names no successor it still calls current.
- Columbia County Public Transportation (`columbia-county-public-transportation`, mdb-2168): the catalog names no successor it still calls current.
- Community in Motion (`community-in-motion`, mdb-2163): the catalog names no successor it still calls current.
- Eastside Friends of Seniors (`eastside-friends-of-seniors`, mdb-2166): the catalog names no successor it still calls current.
- El Paso Transportation Authority (`el-paso-transportation-authority`, mdb-3202): the successor record is not published here. It points at mdb-3419.
- Elevated Transit (`elevated-transit`, mdb-1207): the catalog names no successor it still calls current.
- Elk Grove Transit (`elk-grove-transit`, mdb-2136): the successor record is not published here. It points at mdb-3620.
- Fredericksburg Regional Transit (`fredericksburg-regional-transit-2430`, mdb-2430): the successor record is not published here. It points at mdb-3433.
- Glendale Beeline (`glendale-beeline`, mdb-1280): the successor record is not published here. It points at mdb-3177.
- GoDurham (`godurham`, mdb-377): the successor record is not in this catalog export. It points at tld-98.
- GoWal (`gowal`, mdb-610): the catalog names no successor it still calls current.
- Hawai'i Mass Transit Agency (Hele-On Bus) (`hawai-i-mass-transit-agency-hele-on-bus`, mdb-557): the successor record is not published here. It points at mdb-2608.
- Hopelink Transportation (`hopelink-transportation`, mdb-2167): the catalog names no successor it still calls current.
- Intercity Transit (`intercity-transit-2289`, mdb-2289): the catalog names no successor it still calls current.
- JAUNT Inc (`jaunt-inc`, mdb-1324): the successor record is not in this catalog export. It points at tld-4144.
- Jump Around Carson (`jump-around-carson`, mdb-95): the successor record is not in this catalog export. It points at tld-688.
- Kalamazoo Metro Transit (`kalamazoo-metro-transit-2070`, mdb-2070): the successor record is not in this catalog export. It points at tld-674.
- Kicéo (Vannes) (`kiceo-vannes`, mdb-656): the successor record is not in this catalog export. It points at tdg-82553.
- Knoxville Area Transit (KAT) (`knoxville-area-transit-kat`, mdb-1121): the successor record is not published here. It points at mdb-3512.
- Lakeland Area Mass Transit (`lakeland-area-mass-transit`, mdb-321): the successor record is not in this catalog export. It points at tld-5899.
- LakeXpress (`lakexpress`, mdb-342): the successor record is not in this catalog export. It points at tld-942.
- Lehigh and Northampton Transportation Authority (LANTA) (`lehigh-and-northampton-transportation-authority-lanta`, mdb-506): the successor record is not in this catalog export. It points at ntd-30010.
- LimoLiner (`limoliner`, mdb-438): the catalog names no successor it still calls current.
- Madison County Transit (`madison-county-transit-1145`, mdb-1145): the successor record is not in this catalog export. It points at tld-4136.
- Massachusetts Area Express (MAX) (`massachusetts-area-express-max`, mdb-431): the catalog names no successor it still calls current.
- MATBUS (`matbus`, mdb-1285): the successor record is not in this catalog export. It points at ntd-80003.
- Memphis Area Transit Authority (`memphis-area-transit-authority-2352`, mdb-2352): the successor record is not in this catalog export. It points at tld-1655.
- Metropolitan Area Commuter System (`metropolitan-area-commuter-system`, mdb-232): the successor record is not published here. It points at mdb-3523.
- Metropolitan Tulsa Transit Authority (MTTA) (`metropolitan-tulsa-transit-authority-mtta`, mdb-184): the successor record is not in this catalog export. It points at tld-235.
- Mountain Rides Transportation Authority (MRTA) (`mountain-rides-transportation-authority-mrta`, mdb-143): the successor record is not published here. It points at mdb-2282.
- Niagara Frontier Transportation Authority (NFTA) (`niagara-frontier-transportation-authority-nfta`, mdb-465): the successor record is not in this catalog export. It points at tld-401.
- Palo Verde Valley Transit Agency (`palo-verde-valley-transit-agency`, mdb-18): the successor record is not published here. It points at mdb-2190.
- Paratransit Services (`paratransit-services`, mdb-2176): the catalog names no successor it still calls current.
- Petaluma Transit (`petaluma-transit`, mdb-72): the successor record is not published here. It points at mdb-2947.
- Puget Sound Consolidated GTFS (`metro-transit-intercity-transit-city-of-seattle-community-transit-pierce-transit-sound-transit-washington-state-ferries-seattlecentermonorail-everett-transit-seattle-children-s-hospital`, mdb-1080): the catalog names no successor it still calls current.
- Puget Sound Educational Service District (`puget-sound-educational-service-district`, mdb-2177): the catalog names no successor it still calls current.
- Ridgerunner (`ridgerunner`, mdb-311): the successor record is not published here. It points at mdb-2279.
- Roosevelt Island Operating Corporation Tramway (RIOC Tramway) (`roosevelt-island-operating-corporation-tramway-rioc-tramway`, mdb-1109): the successor record is not in this catalog export. It points at tld-3364.
- Réseau Mistral (Toulon) (`reseau-mistral-toulon`, mdb-1820): the successor record is not in this catalog export. It points at tdg-79560.
- Sacramento Regional Transit (SacRT) (`sacramento-regional-transit-sacrt`, mdb-1296): the successor record is not published here. It points at mdb-2137.
- San Juan Capistrano Free Weekend Trolley (`san-juan-capistrano-free-weekend-trolley`, mdb-596): the successor record is not published here. It points at mdb-2235.
- San Mateo County Transit District (samTrans) (`san-mateo-county-transit-district-samtrans`, mdb-49): the successor record is not published here. It points at mdb-2708.
- Seastreak Ferry (`seastreak-ferry`, mdb-549): the successor record is not in this catalog export. It points at ntd-20226.
- SEMO (Seine-Eure) (`semo-seine-eure`, mdb-1838): the successor record is not in this catalog export. It points at tdg-81338.
- Service Discontinued (`dc-circulator`, mdb-486): the catalog names no successor it still calls current.
- Sonoma-Marin Area Rail Transit (SMART) (`sonoma-marin-area-rail-transit-smart`, mdb-815): the successor record is not published here. It points at mdb-3222.
- Sound Generations: Hyde Shuttle (`sound-generations-hyde-shuttle`, mdb-2183): the catalog names no successor it still calls current.
- South County Transit Link (`south-county-transit-link-2203`, mdb-2203): the successor record is not published here. It points at mdb-3622.
- St Lawrence County Public Transit (`st-lawrence-county-public-transit`, mdb-5): the successor record is not published here. It points at mdb-2608.
- Taft Area Transit (`taft-area-transit`, mdb-821): the successor record is not published here. It points at mdb-2236.
- Transfort – City of Fort Collins (Transfort) (`transfort-city-of-fort-collins-transfort`, mdb-179): the successor record is not published here. It points at mdb-3521.
- Tri Delta Transit (`tri-delta-transit`, mdb-1323): the successor record is not published here. It points at mdb-1974.
- Verkehrsverbund Hegau-Bodensee (VHB) (`vhb-hegau-bodensee`, mdb-914): the successor record is not published here. It points at mdb-2393.
- VIA Metropolitan Transit (VIA) (`via-metropolitan-transit-via-2348`, mdb-2348): the successor record is not in this catalog export. It points at tld-217.
- Virginia Railway Express (VRE) (`virginia-railway-express-vre`, mdb-478): the successor record is not in this catalog export. It points at tld-61.
- Wave Transit (`wave-transit`, mdb-1110): the successor record is not published here. It points at mdb-3536.
- West Berkeley Shuttle (`west-berkeley-shuttle`, mdb-622): the successor record is not published here. It points at mdb-2238.
- Western Reserve Transit Authority (`western-reserve-transit-authority`, mdb-922): the successor record is not in this catalog export. It points at tld-1717.
- Wichita Transit (`wichita-transit`, mdb-185): the successor record is not in this catalog export. It points at tld-395.
- Xpress (`xpress-2355`, mdb-2355): the successor record is not published here. It points at mdb-2426.

## Retired, with a successor we do not track yet

The catalog retired the record each of these is tracked on and names one current record that replaced it. The edit keeps the scorecard and its history and moves `static_gtfs_url` and `mdb_id` to the successor (ADR 0069). Nothing is added and no page is created.

- **5** are ready: open, the same agency by the review rules, and allowed by the successor host's robots.txt.
- **26** are held for a person, with the reason.

- City of Tracy (TRACER) (`city-of-tracy-tracer`): mdb-877 to mdb-3099, now https://s3.amazonaws.com/etatransit.gtfs/tracer.etaspot.net/gtfs.zip
- Clallam Transit System (`clallam-transit-system`): mdb-279 to mdb-3532, now https://irp.cdn-website.com/0eaf265e/files/uploaded/clallam_transit_gtfs.zip
- El Paso Transportation Authority (`el-paso-transportation-authority`): mdb-3202 to mdb-3419, now https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/11511/GTFS_EPCT.zip
- Metropolitan Area Commuter System (`metropolitan-area-commuter-system`): mdb-232 to mdb-3523, now https://fnsb.gov/DocumentCenter/View/24935/General-Transit-Feed-Specification-2025zip
- Xpress (`xpress-2355`): mdb-2355 to mdb-2426, now https://gamobility.info/wp-content/uploads/2025/02/Google_Transit.zip

### Held

- Altamont Corridor Express (`altamont-corridor-express`): mdb-1133 to mdb-2684 (http://api.511.org/transit/datafeeds?operator_id=CE). Held: the successor needs a key, is marked unofficial, or has no usable URL.
- Arvin Transit (`arvin-transit`): mdb-216 to mdb-2233 (https://gtfs.calitp.org/production/ArvinGTFS.zip). Held: the successor host's /robots.txt redirects somewhere else.
- Baldwin Park Transit (`baldwin-park-transit`): mdb-219 to mdb-2247 (https://baldwinpark.tectransit.com/api/public/fixedRoute/gtfs). Held: the successor host's /robots.txt could not be read.
- Broward County Transit (`broward-county-transit`): mdb-330 to mdb-3534 (https://www.arcgis.com/sharing/rest/content/items/acd9791dc1fd49a8aaeaab261dd61b89/data). Held: a curator note names the host this record is tracked on.
- Camarillo Area Transit (`camarillo-area-transit`): mdb-297 to mdb-2234 (https://gtfs.calitp.org/production/CamarilloGTFS.zip). Held: the successor host's /robots.txt redirects somewhere else.
- Casco Bay Lines (`casco-bay-lines`): mdb-1 to mdb-3537 (https://gtfs.remix.com/Casco_Bay_Lines_Portland_ME_USA.zip). Held: a curator note names the host this record is tracked on.
- Elk Grove Transit (`elk-grove-transit`): mdb-2136 to mdb-3620 (https://apps.sacrt.com/gtfs/eg/google_transit.zip). Held: a curator note names the host this record is tracked on.
- Fredericksburg Regional Transit (`fredericksburg-regional-transit-2430`): mdb-2430 to mdb-3433 (https://www.fredericksburgva.gov/DocumentCenter/View/31122/FXBGO-GTFS---CY2026). Held: the successor host's /robots.txt answered 403, which the robots policy treats as off-limits.
- Glendale Beeline (`glendale-beeline`): mdb-1280 to mdb-3177 (https://www.glendaleca.gov/home/showdocument?id=29549). Held: the successor host's /robots.txt answered 403, which the robots policy treats as off-limits.
- Hawai'i Mass Transit Agency (Hele-On Bus) (`hawai-i-mass-transit-agency-hele-on-bus`): mdb-557 to mdb-2608 (https://www.heleonbus.hawaiicounty.gov/home/showpublisheddocument/307470/638458319827900000). Held: the successor host's /robots.txt answered 403, which the robots policy treats as off-limits.
- Knoxville Area Transit (KAT) (`knoxville-area-transit-kat`): mdb-1121 to mdb-3512 (https://knoxville.syncromatics.com/gtfs). Held: a curator note names the host this record is tracked on.
- Mountain Rides Transportation Authority (MRTA) (`mountain-rides-transportation-authority-mrta`): mdb-143 to mdb-2282 (https://apps.itd.idaho.gov/apps/pt/mrtagtfs.zip). Held: the successor host's /robots.txt redirects somewhere else.
- Petaluma Transit (`petaluma-transit`): mdb-72 to mdb-2947 (http://api.511.org/transit/datafeeds?operator_id=PE). Held: the successor needs a key, is marked unofficial, or has no usable URL.
- Ridgerunner (`ridgerunner`): mdb-311 to mdb-2279 (https://www.ridgecrest-ca.gov/DocumentCenter/View/7499/Ridgecrest_gtfszip). Held: the successor's name does not read as a rename of this one.
- Sacramento Regional Transit (SacRT) (`sacramento-regional-transit-sacrt`): mdb-1296 to mdb-3621 (https://apps.sacrt.com/gtfs/srtd/google_transit.zip). Held: a curator note names the host this record is tracked on.
- San Juan Capistrano Free Weekend Trolley (`san-juan-capistrano-free-weekend-trolley`): mdb-596 to mdb-2235 (https://gtfs.calitp.org/production/SanJuanCapistranoGTFS.zip). Held: the successor host's /robots.txt redirects somewhere else.
- San Mateo County Transit District (samTrans) (`san-mateo-county-transit-district-samtrans`): mdb-49 to mdb-2708 (http://api.511.org/transit/datafeeds?operator_id=SM). Held: the successor needs a key, is marked unofficial, or has no usable URL; a curator note names the host this record is tracked on.
- Sonoma-Marin Area Rail Transit (SMART) (`sonoma-marin-area-rail-transit-smart`): mdb-815 to mdb-3222 (http://api.511.org/transit/datafeeds?operator_id=SA). Held: the successor needs a key, is marked unofficial, or has no usable URL.
- South County Transit Link (`south-county-transit-link-2203`): mdb-2203 to mdb-3622 (https://apps.sacrt.com/gtfs/SCTLink/google_transit.zip). Held: a curator note names the host this record is tracked on.
- St Lawrence County Public Transit (`st-lawrence-county-public-transit`): mdb-5 to mdb-2608 (https://www.heleonbus.hawaiicounty.gov/home/showpublisheddocument/307470/638458319827900000). Held: the successor is in a different state or province; the successor's name does not read as a rename of this one.
- Taft Area Transit (`taft-area-transit`): mdb-821 to mdb-2236 (https://gtfs.calitp.org/production/TaftGTFS.zip). Held: the successor host's /robots.txt redirects somewhere else.
- Transfort – City of Fort Collins (Transfort) (`transfort-city-of-fort-collins-transfort`): mdb-179 to mdb-3521 (https://ridetransfort.com/wp-content/uploads/transfort_gtfs.zip). Held: a curator note names the host this record is tracked on.
- Tri Delta Transit (`tri-delta-transit`): mdb-1323 to mdb-1974 (http://api.511.org/transit/datafeeds?operator_id=3D). Held: the successor needs a key, is marked unofficial, or has no usable URL.
- Verkehrsverbund Hegau-Bodensee (VHB) (`vhb-hegau-bodensee`): mdb-914 to mdb-2393 (https://www.nvbw.de/fileadmin/user_upload/service/open_data/fahrplandaten_mit_liniennetz/bwgesamt.zip). Held: the successor's name does not read as a rename of this one.
- Wave Transit (`wave-transit`): mdb-1110 to mdb-3536 (https://wave.connexionz.net/rtt/public/resource/gtfs.zip). Held: the successor's name does not read as a rename of this one; a curator note names the host this record is tracked on.
- West Berkeley Shuttle (`west-berkeley-shuttle`): mdb-622 to mdb-2238 (https://gtfs.calitp.org/production/WestBerkeleyShuttleGTFS.zip). Held: the successor host's /robots.txt redirects somewhere else.
