# Superseded feed records in the Mobility Database

Run 2026-08-31. Source: mobilitydatabase.org catalog CSV.

The Mobility Database marks a replaced feed record `deprecated` and names the record that replaced it. Where both records are tracked here, the retired one is set to `feed_status: deprecated` with `alias_of` pointing at its successor: its dated artifacts stay available for reproducibility and its scorecard URL redirects, but it stops publishing a second current grade under the same agency's name.

- **0** retired records resolve to a successor published here.
- **103** retired records do not, and keep their own page.

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

- Alameda-Contra Costa Transit District (AC Transit) (`alameda-contra-costa-transit-district-ac-transit`, mdb-1244): the successor record is not published here. It points at mdb-2455.
- Altamont Corridor Express (`altamont-corridor-express`, mdb-1133): the successor record is not published here. It points at mdb-2684.
- Aléop (Pays de la Loire) (`aleop-pays-de-la-loire`, mdb-1096): the successor record is not published here. It points at tdg-80721.
- Aléop Yeu-Continent (Île d'Yeu ferry) (`aleop-yeu-continent`, mdb-1257): the successor record is not published here. It points at tdg-82641.
- Arvin Transit (`arvin-transit`, mdb-216): the successor record is not published here. It points at mdb-2233.
- Baldwin Park Transit (`baldwin-park-transit`, mdb-219): the successor record is not published here. It points at mdb-2247.
- Beach Cities Transit (`beach-cities-transit`, mdb-803): the successor record is not published here. It points at mdb-1999.
- Bellflower Bus (`bellflower-bus`, mdb-227): the successor record is not published here. It points at mdb-3095.
- Beloit Transit (`beloit-transit`, mdb-392): the successor record is not published here. It points at tld-77.
- Bibus (Brest) (`bibus-brest`, mdb-999): the successor record is not published here. It points at tdg-81559.
- Biddeford Saco Old Orchard Beach Transit (`biddeford-saco-old-orchard-beach-transit`, mdb-2300): the successor record is not published here. It points at tld-4756.
- Birmingham Jefferson County Transit Authority (MAX) (`birmingham-jefferson-county-transit-authority-max-2263`, mdb-2263): the successor record is not published here. It points at mdb-3434.
- Blue Star Bus (`blue-star-bus`, mdb-256): the catalog names no successor it still calls current.
- Boulder County (`boulder-county`, mdb-880): the successor record is not published here. It points at mdb-2191.
- Breeze Transit (`breeze-transit`, mdb-2260): the successor record is not published here. It points at tld-351_1.
- Buc Shuttle (`buc-shuttle`, mdb-371): the catalog names no successor it still calls current.
- Butte Regional Transit (B-Line) (`butte-regional-transit-b-line`, mdb-241): the successor record is not published here. It points at ntd-90208.
- Camarillo Area Transit (`camarillo-area-transit`, mdb-297): the successor record is not published here. It points at mdb-2234.
- Capital Trailways (`capital-trailways`, mdb-1308): the catalog names no successor it still calls current.
- Car Jaune (La Réunion) (`car-jaune-reunion`, mdb-2458): the successor record is not published here. It points at tdg-80934.
- Cara'bus (Royan) (`carabus-royan`, mdb-2842): the successor record is not published here. It points at tdg-82361.
- Cars Régionaux 23 — Creuse (`cars-regionaux-23-creuse`, mdb-2686): the successor record is not published here. It points at tdg-82330.
- Cascades East Transit (CET) (`cascades-east-transit-cet`, mdb-138): the successor record is not published here. It points at tld-170.
- CATABUS (`centre-county-transit-authority-cata`, mdb-1236): the successor record is not published here. It points at tld-366.
- Champaign Urbana Mass Transit District (MTD) (`champaign-urbana-mass-transit-district-mtd`, mdb-388): the successor record is not published here. It points at ntd-50060.
- Chapel Hill Transit (CHT) (`chapel-hill-transit-cht`, mdb-376): the successor record is not published here. It points at tld-89.
- Chattanooga Area Regional Transportation Authority (CARTA) (`chattanooga-area-regional-transportation-authority-carta-2082`, mdb-2082): the successor record is not published here. It points at mdb-3474.
- Choletbus (`choletbus`, mdb-1789): the successor record is not published here. It points at tdg-79352.
- City of Glendale (`city-of-glendale`, mdb-1245): the successor record is not published here. It points at tld-471.
- City of Lompoc Transit (COLT) (`city-of-lompoc-transit-colt`, mdb-919): the successor record is not published here. It points at tld-1654.
- City of Sierra Vista (`city-of-sierra-vista`, mdb-145): the successor record is not published here. It points at tld-679.
- City of Tracy (TRACER) (`city-of-tracy-tracer`, mdb-877): the successor record is not published here. It points at mdb-3099.
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
- Lakeland Area Mass Transit (`lakeland-area-mass-transit`, mdb-321): the successor record is not published here. It points at tld-5899.
- LakeXpress (`lakexpress`, mdb-342): the successor record is not published here. It points at tld-942.
- LE MET' (Metz) (`le-met-metz`, mdb-1298): the successor record is not published here. It points at tdg-80725.
- Lehigh and Northampton Transportation Authority (LANTA) (`lehigh-and-northampton-transportation-authority-lanta`, mdb-506): the successor record is not published here. It points at ntd-30010.
- Lignes d'Azur (Nice) (`lignes-dazur-nice`, mdb-845): the successor record is not published here. It points at tdg-82136, tdg-82137, tdg-82285.
- LimoLiner (`limoliner`, mdb-438): the catalog names no successor it still calls current.
- Madison County Transit (`madison-county-transit-1145`, mdb-1145): the successor record is not published here. It points at tld-4136.
- Marinéo (Boulogne-sur-Mer) (`marineo-boulogne`, mdb-1876): the successor record is not published here. It points at tdg-51449.
- Massachusetts Area Express (MAX) (`massachusetts-area-express-max`, mdb-431): the catalog names no successor it still calls current.
- MATBUS (`matbus`, mdb-1285): the successor record is not published here. It points at ntd-80003.
- Memphis Area Transit Authority (`memphis-area-transit-authority-2352`, mdb-2352): the successor record is not published here. It points at tld-1655.
- Metropolitan Tulsa Transit Authority (MTTA) (`metropolitan-tulsa-transit-authority-mtta`, mdb-184): the successor record is not published here. It points at tld-235.
- Monroe County Transportation Authority (MCTA) (`monroe-county-transportation-authority-mcta`, mdb-523): the successor record is not published here. It points at mdb-3460.
- Mountain Rides Transportation Authority (MRTA) (`mountain-rides-transportation-authority-mrta`, mdb-143): the successor record is not published here. It points at mdb-2282.
- Métropole Aix-Marseille-Provence networks (`aix-marseille-provence`, mdb-2133): the successor record is not published here. It points at tdg-39601.
- Neobus (Ouest Vosgien) (`neobus-ouest-vosgien`, mdb-1839): the successor record is not published here. It points at tdg-79814.
- Niagara Frontier Transportation Authority (NFTA) (`niagara-frontier-transportation-authority-nfta`, mdb-465): the successor record is not published here. It points at tld-401.
- Ondéa (Aix-les-Bains) (`ondea-aix-les-bains`, mdb-600): the successor record is not published here. It points at tdg-71223.
- Orizo (Grand Avignon) (`orizo-grand-avignon`, mdb-1878): the successor record is not published here. It points at tdg-9279.
- Palo Verde Valley Transit Agency (`palo-verde-valley-transit-agency`, mdb-18): the successor record is not published here. It points at mdb-2190.
- Pasažieru vilciens (Vivi) (`pasazieru-vilciens-vivi`, mdb-2015): the successor record is not published here. It points at mdb-3385.
- Petaluma Transit (`petaluma-transit`, mdb-72): the successor record is not published here. It points at mdb-2947.
- Renfe (Alta Velocidad, Larga y Media Distancia) (`renfe-alta-larga-media`, mdb-2620): the successor record is not published here. It points at tdg-82386.
- RIDE Sitka (`ride-sitka`, mdb-1293): the catalog names no successor it still calls current.
- Ridgerunner (`ridgerunner`, mdb-311): the successor record is not published here. It points at mdb-2279.
- Roosevelt Island Operating Corporation Tramway (RIOC Tramway) (`roosevelt-island-operating-corporation-tramway-rioc-tramway`, mdb-1109): the successor record is not published here. It points at tld-3364.
- Rosemead Explorer (`rosemead-explorer`, mdb-806): the successor record is not published here. It points at mdb-3098.
- Réseau Léo (Communauté d'Agglomération de l'Auxerrois) (`leo-auxerrois`, mdb-642): the successor record is not published here. It points at tdg-78934.
- Réseau Stan (Nancy) (`stan-nancy`, mdb-1256): the successor record is not published here. It points at tdg-81346.
- Réseau urbain Cap Cotentin (`cap-cotentin`, mdb-1840): the successor record is not published here. It points at tdg-79831.
- Rīgas satiksme (`rigas-satiksme`, mdb-884): the successor record is not published here. It points at mdb-3502.
- San Juan Capistrano Free Weekend Trolley (`san-juan-capistrano-free-weekend-trolley`, mdb-596): the successor record is not published here. It points at mdb-2235.
- Santa Rosa CityBus (`santa-rosa-citybus`, mdb-73): the successor record is not published here. It points at mdb-1986.
- Seastreak Ferry (`seastreak-ferry`, mdb-549): the successor record is not published here. It points at ntd-20226.
- Service Discontinued (`dc-circulator`, mdb-486): the catalog names no successor it still calls current.
- Sonoma-Marin Area Rail Transit (SMART) (`sonoma-marin-area-rail-transit-smart`, mdb-815): the successor record is not published here. It points at mdb-3222.
- St Lawrence County Public Transit (`st-lawrence-county-public-transit`, mdb-5): the successor record is not published here. It points at mdb-2608.
- Stanislaus Regional Transit (StaRT) (`stanislaus-regional-transit-start`, mdb-87): the successor record is not published here. It points at mdb-2273.
- T'MM (Moselle et Madon) (`tmm-moselle-madon`, mdb-2738): the successor record is not published here. It points at tdg-82388.
- Taft Area Transit (`taft-area-transit`, mdb-821): the successor record is not published here. It points at mdb-2236.
- Thousand Oaks Transit (`thousand-oaks-transit`, mdb-33): the successor record is not published here. It points at mdb-2237.
- Transports Bordeaux Métropole (TBM) (`tbm-bordeaux-metropole`, mdb-2622): the successor record is not published here. It points at tdg-83024.
- Tri Delta Transit (`tri-delta-transit`, mdb-1323): the successor record is not published here. It points at mdb-1974.
- Verkehrsverbund Hegau-Bodensee (VHB) (`vhb-hegau-bodensee`, mdb-914): the successor record is not published here. It points at mdb-2393.
- VIA Metropolitan Transit (VIA) (`via-metropolitan-transit-via-2348`, mdb-2348): the successor record is not published here. It points at tld-217.
- Virginia Breeze (`virginia-breeze`, mdb-1328): the successor record is not published here. It points at mdb-3506.
- Virginia Railway Express (VRE) (`virginia-railway-express-vre`, mdb-478): the successor record is not published here. It points at tld-61.
- West Berkeley Shuttle (`west-berkeley-shuttle`, mdb-622): the successor record is not published here. It points at mdb-2238.
- Western Reserve Transit Authority (`western-reserve-transit-authority`, mdb-922): the successor record is not published here. It points at tld-1717.
- Wichita Transit (`wichita-transit`, mdb-185): the successor record is not published here. It points at tld-395.
- Xpress (`xpress-2355`, mdb-2355): the successor record is not published here. It points at mdb-2426.
- Zoom (Le Grand Chalon) (`zoom-grand-chalon`, mdb-658): the successor record is not published here. It points at tdg-82664.
