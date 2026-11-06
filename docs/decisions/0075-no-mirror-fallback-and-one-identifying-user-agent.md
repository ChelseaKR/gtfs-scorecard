# ADR 0075: No mirror fallback, one identifying User-Agent for every request, and catalog hosts only where robots.txt allows

**Status:** Accepted (2026-11-05). Decided by the maintainer (option a). 0073
and 0074 are taken by the IndexNow and finding-fragment branches.

## Context

ADR 0070 (merged 2026-10-19) made feed requests identify the project and read
robots.txt first, and stopped reading `files.mobilitydatabase.org`, whose
robots.txt is `User-agent: * / Disallow: /`. Three gaps remained.

- The daily fetch still fell back to a Mobility Database hosted copy when a
  feed's own URL failed. Copies on `files.mobilitydatabase.org` were refused,
  but a copy on another host was still fetched and graded as the agency's feed.
- Several clients sent their own User-Agent strings without a link
  (`gtfs-scorecard/1.0 (equity)`, `gtfs-scorecard-mcp`, `gtfs-scorecard-submit`)
  or none at all (the map builders, webhook posts, a local OTP check), and the
  OTP QA workflow downloaded feeds with plain `curl`.
- ADR 0070 exempted `api.mobilitydatabase.org` from robots.txt. On 2026-11-05
  its `/robots.txt` answered 302 to a sign-in page.

The published store on 2026-11-05 (2,499 `latest.json` files read from
gtfsscorecard.org) showed what the old behavior left behind:

- 829 artifacts record the old Chrome User-Agent. Every one was last downloaded
  on or before 2026-10-19, the day #523 merged; none fetched since carries it.
  They are a true record of how those bytes were fetched and are not rewritten.
- 133 published grades were scored from mirror copies: 117 from
  `files.mobilitydatabase.org` and 16 from `storage.googleapis.com`. All were
  fetched on or before 2026-10-19. 99 of the copies have already ended service.

## Decision

1. **No mirror fallback.** `fetch._download_from_origin` asks the URL on file
   and nothing else. When it fails, the run records the feed as unreachable
   ("couldn't download") and grades nothing from anyone else's bytes.
   `mobilitydb.hosted_mirror_url` is removed, and the daily fetch no longer
   reads the catalog at all.
2. **Freshness of a mirror copy is not measured.** The freshness sweep holds
   freshness out of any artifact whose `fetch.source` is `mirror`: the
   category becomes `not_yet_measured` with a summary that says the feed URL
   could not be downloaded, and the grade is computed over the categories that
   were measured, the way unmeasured realtime is. It is never shown as 0 or as
   fresh, and it is held once and then left alone. When PR #560 lands, these
   grades also carry its "partial: freshness not measured" mark.
3. **One User-Agent.** `user_agent.USER_AGENT` is
   `gtfs-scorecard/<version> (+https://gtfsscorecard.org/fetcher/)`. `net`
   fills it in when a caller sends none and raises `BrowserUserAgentError`
   before sending a browser-like or anonymous one. The Lambdas and standalone
   scripts carry a literal of the same shape. A test-suite guard on
   `http.client.HTTPConnection.putheader` fails any test that writes a
   browser-like User-Agent to a socket, and a scan of the source trees fails on
   any other literal.
4. **Catalog and data hosts only where robots.txt allows.** Every catalog CSV
   read checks the host's robots.txt first. The weekly discover job reads the
   `storage.googleapis.com` export (`/robots.txt` 404, no rules, checked
   2026-11-05; the file was last updated 2026-10-27). The Mobility Database API
   is not called: `catalog_api.load_api_catalog` pauses with a message, and the
   validator-report reuse in `feedapi.py` is skipped. The same robots check now
   runs before the equity overlay reads (Census, TIGERweb, Statistics Canada).

## Measured effect on published grades

The sweep's new rule was run against the 133 published mirror-scored
artifacts. Two (`anaheim-resort-transportation-art`, `mdv-mitteldeutscher`)
grade an archive with no stops or trips, which the sweep already refuses to
re-date, so they do not change. The other 131 scores change, and 81 letter
grades change: 35 F to D, 21 F to C, 8 C to D, 7 D to F, 4 D to C, 3 D to B,
1 B to C, 1 C to A, 1 A to B. A copy that had ended service stops pulling the
grade down; a current copy stops pulling it up. A record whose own URL answers
again on a later run is regraded from its own feed, which replaces these
numbers. A local sweep over the production corpus on 2026-11-06 held 130 of
the 131; the last, `atd-latvia-national`, had no readable end date and is
held after the fix this measurement found.

| Record | Now | After | Copy service ends |
| --- | --- | --- | --- |
| Aléop Yeu-Continent (Île d'Yeu ferry) (`aleop-yeu-continent`) | B 81.6 | C 77.7 | in 56 days |
| Altamont Corridor Express (`altamont-corridor-express`) | F 46.8 | D 62.5 | 674 days ago |
| Areawide Community Transportation System (`areawide-community-transportation-system`) | F 57.2 | C 76.3 | 401 days ago |
| Beach Cities Transit (`beach-cities-transit`) | D 62.2 | C 77.7 | 1404 days ago |
| Bell Gardens Trolley (`bell-gardens-trolley`) | F 49.6 | D 66.1 | 674 days ago |
| Bellflower Bus (`bellflower-bus`) | F 51.3 | D 68.5 | 674 days ago |
| Bethesda Circulator (`bethesda-circulator`) | F 54.6 | C 72.8 | 765 days ago |
| Blacksburg Transit (`blacksburg-transit`) | F 52.0 | D 69.3 | 97 days ago |
| Blue & Gold Fleet (`blue-gold-fleet`) | F 53.9 | C 71.8 | 942 days ago |
| Blue Star Bus (`blue-star-bus`) | F 53.6 | C 71.4 | 2865 days ago |
| Broward County Transit (`broward-county-transit`) | D 65.4 | B 87.2 | 40 days ago |
| Capital District Transportation Authority (CDTA) (`capital-district-transportation-authority-cdta`) | C 74.0 | A 92.6 | 68 days ago |
| Capital Trailways (`capital-trailways`) | F 46.7 | D 62.3 | 802 days ago |
| Cascades East Transit (CET) (`cascades-east-transit-cet`) | F 48.5 | D 64.6 | 926 days ago |
| Casco Bay Lines (`casco-bay-lines`) | F 52.8 | C 70.3 | 146 days ago |
| Citrus County Transit (`citrus-county-transit-2257`) | F 48.4 | D 64.6 | 674 days ago |
| City of Bell (La Campana) (`city-of-bell-la-campana-2249`) | F 55.0 | C 73.3 | 674 days ago |
| City of Glendale (`city-of-glendale`) | F 49.1 | D 65.5 | 1527 days ago |
| City of Lompoc Transit (COLT) (`city-of-lompoc-transit-colt`) | F 45.8 | D 61.1 | 948 days ago |
| Cudahy Area Rapid Transit (`cudahy-area-rapid-transit-2248`) | F 47.1 | D 62.8 | 278 days ago |
| Culver City Bus (`culver-city-bus`) | D 60.1 | C 75.1 | 116 days ago |
| DC Streetcar (`dc-streetcar-2223`) | F 57.2 | C 76.3 | 493 days ago |
| DowneyLINK (`downeylink`) | D 61.1 | C 76.3 | 674 days ago |
| ECO Transit (`eco-transit-2061`) | F 45.6 | D 60.8 | 1300 days ago |
| El Segundo Transportation (`el-segundo-transportation-2210`) | F 51.5 | D 68.6 | 881 days ago |
| Elevated Transit (`elevated-transit`) | F 53.6 | C 71.4 | 3444 days ago |
| Elk Grove Transit (`elk-grove-transit`) | F 51.4 | D 64.2 | 669 days ago |
| exo Chambly-Richelieu-Carignan (`exo-chambly-richelieu-carignan`) | C 72.0 | D 63.2 | in 59 days |
| exo La Presqu'Île (`exo-la-presquile`) | C 72.1 | D 63.3 | in 59 days |
| exo L'Assomption (`exo-lassomption`) | C 73.2 | D 64.9 | in 59 days |
| exo Laurentides (`exo-laurentides`) | D 69.4 | F 59.8 | in 59 days |
| exo Le Richelain / Roussillon (`exo-le-richelain-roussillon`) | C 70.3 | D 61.0 | in 59 days |
| exo Ville de Sainte-Julie (`exo-sainte-julie`) | D 66.8 | F 56.3 | in 59 days |
| exo Sorel-Varennes (`exo-sorel-varennes`) | D 66.8 | F 56.3 | in 59 days |
| exo Sud-Ouest (`exo-sud-ouest`) | D 69.4 | F 59.8 | in 59 days |
| exo Terrebonne-Mascouche (`exo-terrebonne-mascouche`) | D 66.8 | F 56.3 | in 59 days |
| exo (commuter rail network) (`exo-trains`) | D 67.1 | F 56.7 | in 59 days |
| exo Vallée du Richelieu (`exo-vallee-du-richelieu`) | C 70.3 | D 61.0 | in 59 days |
| Express Arrow (`express-arrow`) | F 49.9 | D 66.6 | 948 days ago |
| Get Around Town Express (`get-around-town-express`) | F 51.3 | D 68.5 | 674 days ago |
| Glendale Beeline (`glendale-beeline`) | F 49.1 | D 65.5 | 1527 days ago |
| Glendora Transportation Division (`glendora-transportation-division-3097`) | F 53.8 | C 71.8 | 97 days ago |
| Grand Valley Transit (`grand-valley-transit`) | F 55.2 | C 73.6 | 365 days ago |
| Greensboro Transit Authority (GTA) (`greensboro-transit-authority-gta`) | F 47.6 | D 63.5 | 615 days ago |
| Hawai'i Mass Transit Agency (Hele-On Bus) (`hawai-i-mass-transit-agency-hele-on-bus`) | F 51.9 | D 69.2 | 1046 days ago |
| Huntington Park Express (`huntington-park-express`) | F 49.6 | D 66.1 | 674 days ago |
| Jamestown S'klallam (`jamestown-s-klallam`) | F 55.5 | C 74.0 | 2226 days ago |
| Klamath Shuttle (`klamath-shuttle`) | F 51.1 | D 68.2 | 1522 days ago |
| Livermore Amador Valley Transit Authority (`livermore-amador-valley-transit-authority`) | F 58.3 | C 77.7 | 189 days ago |
| Lynwood Trolley / Breeze (`lynwood-trolley-breeze`) | F 51.3 | D 68.5 | 674 days ago |
| Metro Sul do Tejo (`metro-sul-do-tejo`) | A 90.6 | B 87.5 | in 1153 days |
| Morro Bay Transit (`morro-bay-transit-2059`) | F 48.0 | D 64.0 | 523 days ago |
| Mountain Express (MtnExp) (`mountain-express-mtnexp`) | F 55.8 | C 74.4 | 1249 days ago |
| Cuyahoga Valley Scenic Railroad (`national-park-service`) | D 60.7 | B 81.0 | 2930 days ago |
| Palo Verde Valley Transit Agency (`palo-verde-valley-transit-agency`) | D 61.7 | C 77.1 | 674 days ago |
| Puget Sound Express (`puget-sound-express`) | F 53.7 | C 71.7 | 2595 days ago |
| RIDE Sitka (`ride-sitka`) | F 52.9 | C 70.6 | 1770 days ago |
| Ridgecrest Transit (`ridgecrest-transit`) | F 52.3 | D 69.8 | 461 days ago |
| Rochester City Lines (`rochester-city-lines`) | F 51.0 | D 68.0 | 3961 days ago |
| Rockford Mass Transit District (`rockford-mass-transit-district`) | F 45.1 | D 60.1 | 1146 days ago |
| Rosemead Explorer (`rosemead-explorer`) | F 51.3 | D 68.5 | 674 days ago |
| Roseville Transit (`roseville-transit`) | C 72.8 | D 67.7 | in 56 days |
| Sacramento Regional Transit (SacRT) (`sacramento-regional-transit-sacrt`) | F 51.1 | D 63.9 | 670 days ago |
| San Clemente Trolley (`san-clemente-trolley`) | C 71.2 | D 67.7 | in 8821 days |
| Sandia Shuttle (`sandia-shuttle`) | F 49.4 | D 65.8 | 1405 days ago |
| Sanford Trolley (`sanford-trolley`) | F 57.0 | C 76.0 | 1770 days ago |
| Selah Transit (`selah-transit`) | D 62.4 | B 83.2 | 218 days ago |
| Shore Line East (`shore-line-east`) | F 47.9 | D 63.9 | 674 days ago |
| Sierra Madre Gateway Coach (`sierra-madre-gateway-coach-2251`) | F 54.1 | C 72.1 | 674 days ago |
| South County Transit Link (`south-county-transit-link-2203`) | F 48.2 | D 64.3 | 309 days ago |
| South Florida Regional Transportation Authority (Tri-Rail) (`south-florida-regional-transportation-authority-tri-rail`) | F 56.7 | C 75.6 | 309 days ago |
| South Lane Wheels (`south-lane-wheels`) | F 52.1 | D 69.5 | 1161 days ago |
| SouthWest POINT (`southwest-point`) | F 48.5 | D 64.7 | 1939 days ago |
| SunTran (`suntran-2354`) | F 55.7 | C 74.3 | 173 days ago |
| SunTran Utah (`suntran-utah`) | D 63.2 | F 56.0 | in 1547 days |
| Torrance Transit (`torrance-transit`) | F 54.3 | C 72.4 | 1027 days ago |
| Tri Delta Transit (`tri-delta-transit`) | F 50.2 | D 67.0 | 1770 days ago |
| UTrans (`utrans`) | F 48.6 | D 64.8 | 522 days ago |
| Wave Transit (`wave-transit`) | C 70.9 | D 63.5 | in 56 days |
| UNCW Seahawk Shuttle (`wave-transit-2026`) | F 48.2 | D 64.3 | 546 days ago |
| Xpress (`xpress-2355`) | F 57.5 | C 76.7 | 488 days ago |
| Advance Transit (AT) (`advance-transit-at`) | F 42.3 | F 56.4 | 1324 days ago |
| Allegany County Transit (`allegany-county-transit`) | F 25.1 | F 33.4 | 2289 days ago |
| Anaheim Resort Transportation (ART) (`anaheim-resort-transportation-art`) | F 48.1 | F 48.1 | unchanged: archive with no stops or trips, held back from sweeps |
| Autotransporta direkcija (ATD) national routes (`atd-latvia-national`) | F 27.9 | F 37.2 | not recorded |
| Birmingham Jefferson County Transit Authority (MAX) (`birmingham-jefferson-county-transit-authority-max-2263`) | F 34.8 | F 46.4 | 523 days ago |
| CATABUS (`centre-county-transit-authority-cata`) | F 22.0 | F 29.3 | 1902 days ago |
| Cherriots (`cherriots`) | F 23.8 | F 31.7 | 307 days ago |
| City of San Luis Obispo Transit (`city-of-san-luis-obispo-transit`) | B 88.2 | B 86.4 | in 57 days |
| Compton Renaissance (`compton-renaissance`) | F 37.1 | F 49.5 | 1405 days ago |
| Corpus Christi Regional Transportation Authority (`corpus-christi-regional-transportation-authority`) | F 40.9 | F 54.5 | 523 days ago |
| Cortland County Public Transportation (`cortland-county-public-transportation`) | F 35.4 | F 47.2 | 585 days ago |
| Dana Point Trolley (`dana-point-trolley`) | D 69.8 | D 65.9 | in 8821 days |
| Eau Claire Transit (`eau-claire-transit`) | F 31.0 | F 41.3 | 309 days ago |
| Essex Bus Network (`essex-bus-network`) | F 35.7 | F 33.1 | in 26 days |
| Fairfax CUE Bus (CUE) (`fairfax-cue-bus-cue-2885`) | D 67.8 | D 62.0 | in 8821 days |
| Fredericksburg Regional Transit (`fredericksburg-regional-transit-2430`) | F 38.6 | F 51.5 | 584 days ago |
| Glendora Transportation Division (`glendora-transportation-division`) | F 36.1 | F 48.1 | 1405 days ago |
| Gold Coast Transit, South Coast Area Transit (`gold-coast-transit-south-coast-area-transit`) | F 43.6 | F 54.5 | 669 days ago |
| Green Bay Metro (`green-bay-metro`) | F 26.9 | F 35.8 | 2135 days ago |
| HDPT (`harrisonburg-department-of-public-transportation-hdpt`) | F 30.4 | F 40.5 | 2007 days ago |
| IndyGo (`indygo`) | F 37.4 | F 49.8 | 985 days ago |
| Interurban Trolley (`interurban-trolley`) | B 83.6 | B 80.3 | in 56 days |
| JAUNT Inc (`jaunt-inc`) | F 38.0 | F 50.6 | 1405 days ago |
| Knoxville Area Transit (KAT) (`knoxville-area-transit-kat`) | F 56.8 | F 47.3 | in 26719 days |
| Lakes Region Explorer (`lakes-region-explorer`) | D 66.9 | D 60.8 | in 906 days |
| Lane Transit District (LTD) (`lane-transit-district-ltd`) | F 39.2 | F 49.0 | 278 days ago |
| Madison County Transit (`madison-county-transit-1145`) | F 7.0 | F 9.4 | 1643 days ago |
| Massachusetts Ferry Service (`massachusetts-ferry-service`) | F 40.6 | F 54.1 | 5788 days ago |
| MATBUS (`matbus`) | F 41.2 | F 55.0 | 1359 days ago |
| Mitteldeutscher Verkehrsverbund (MDV) (`mdv-mitteldeutscher`) | F 31.3 | F 31.3 | unchanged: archive with no stops or trips, held back from sweeps |
| Memphis Area Transit Authority (`memphis-area-transit-authority-2352`) | F 40.3 | F 53.8 | 605 days ago |
| Metro Rock Island County Metropolitan Mass Transit District (`metro-rock-island-county-metropolitan-mass-transit-district`) | F 34.8 | F 46.5 | 151 days ago |
| Mountain Line Transit Authority (`mountain-line-transit-authority`) | B 84.0 | B 80.8 | in 56 days |
| Mountain Metropolitan Transit (`mountain-metropolitan-transit-2356`) | F 44.3 | F 59.0 | 404 days ago |
| Münchner Verkehrs- und Tarifverbund (MVV) (`mvv-munchen`) | F 40.6 | F 54.1 | 97 days ago |
| Niagara Frontier Transportation Authority (NFTA) (`niagara-frontier-transportation-authority-nfta`) | F 29.7 | F 39.5 | 873 days ago |
| Pinellas Suncoast Transit Authority (PSTA) (`pinellas-suncoast-transit-authority-psta`) | F 34.2 | F 45.5 | 152 days ago |
| Rabbit Transit (`rabbit-transit`) | F 34.6 | F 46.1 | 1405 days ago |
| Rīgas satiksme (`rigas-satiksme`) | F 55.5 | F 45.7 | in 238 days |
| Rio de Janeiro municipal transport (SMTR) (`rio-de-janeiro-transportes`) | F 57.4 | F 45.4 | in 56 days |
| Shreveport and Bossier City (`shreveport-and-bossier-city`) | F 34.7 | F 22.1 | in 26719 days |
| STCP (Sociedade de Transportes Colectivos do Porto) (`stcp-porto`) | F 42.0 | F 56.0 | 309 days ago |
| Tideline Water Taxi (`tideline-water-taxi`) | F 40.3 | F 53.8 | 1284 days ago |
| Transfort – City of Fort Collins (Transfort) (`transfort-city-of-fort-collins-transfort`) | F 39.9 | F 53.2 | 908 days ago |
| Transtejo Soflusa (TTSL) (`transtejo-soflusa`) | A 98.8 | A 98.4 | in 269 days |
| Virginia Railway Express (VRE) (`virginia-railway-express-vre`) | F 28.3 | F 35.3 | 706 days ago |
| Washington Metropolitan Area Transit Authority (WMATA) Bus (`washington-metropolitan-area-transit-authority-wmata`) | C 78.3 | C 71.1 | in 142 days |
| Washington Metropolitan Area Transit Authority (WMATA) Rail (`washington-metropolitan-area-transit-authority-wmata-1847`) | F 35.3 | F 47.1 | 13 days ago |
| Westchester County Bee-Line System (WCDOT) (`westchester-county-bee-line-system-wcdot-2353`) | F 30.4 | F 40.5 | 431 days ago |
| Western Reserve Transit Authority (`western-reserve-transit-authority`) | F 17.0 | F 22.6 | 2161 days ago |
| Wichita Transit (`wichita-transit`) | F 11.7 | F 15.6 | 1175 days ago |
| Yuma County Intergovernmental Public Transportation Authority (YCIPTA) (`yuma-county-intergovernmental-public-transportation-authority-ycipta`) | D 68.0 | D 64.0 | in 57 days |

## Consequences

- The daily fetch makes one request per feed (after robots.txt) and none to
  the catalog.
- `discover.yml` no longer needs `MOBILITY_FEED_API_TOKEN`; the secret can be
  deleted. `catalog_api.py` stays so the API can be used again if its host ever
  serves rules that allow it.
- The Statistics Canada CIMD service answers `User-agent: * / Disallow: /`, so
  `scorecard canada-equity` now stops before a request and keeps the committed
  overlay. `api.census.gov` and `tigerweb.geo.census.gov` answered an HTML
  "Request Rejected" page at `/robots.txt` to the identifying User-Agent, which
  robots_policy treats as off-limits, so `scorecard equity` stops the same way.
  Both workflows will fail until the maintainer decides how to source them.
- Two registry records, `tper-marconi-express` and `atp-nuoro`, list a
  Mobility Database bucket on `storage.googleapis.com` as their own feed URL.
  That host allows us, so they are unchanged here; whether a catalog copy
  should be a record's URL at all is a curator decision.
