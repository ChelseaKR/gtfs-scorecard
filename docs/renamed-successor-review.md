# Reading aid: retirements whose successor publishes under a different agency name

Prepared for review of pull request #272 (`fix(registry): stop publishing a
retired feed record beside its successor`), which records the Mobility
Database's own retirements in the registry so one agency stops carrying two
current grades.

**This is a reading aid, not a recommendation.** It exists so the 28 records
worth a second look can be read in a few minutes instead of by diffing 39
registry shards. Nothing here is a merge decision; that call is the
maintainer's.

## What was checked, and against what

Twenty-eight of the retirements in #272 send a reader from one agency's name to
a differently-named agency. Every one of them was re-derived from the registry
shards in the pull request itself: the retired record and its successor were
joined by `alias_of`, and their names, `mdb_id`, `subdivision_name`,
`organization_id` and feed URLs were compared side by side. The catalog CSV was
not re-fetched; `files.mobilitydatabase.org/robots.txt` returns
`User-agent: * / Disallow: /`, so the in-repo registry is the evidence used here.

Mechanical checks, all of which pass on the branch:

- All 28 retired records carry both `feed_status: deprecated` and an `alias_of`
  pointing at the successor named in the report.
- No successor of the 28 is itself deprecated or aliased, so none of these
  pairings leaves a reader on another retired page.
- The retired and successor `mdb_id` values match the redirects the report
  claims.
- Read on 2026-08-14, the branch's loaded registry holds 2,185 records, of which
  2,011 are canonical, which is what #272 states.

## The read

Categories are one reader's interpretation of the evidence in the table's last
column. "Unclear" means the in-repo evidence conflicts with itself or with the
name, not that the catalog is wrong.

| Category | Count |
| --- | --- |
| rename | 20 |
| merger | 5 |
| operator change | 0 |
| **unclear** | **3** |

### Read these three first

Each of the three is a case where the surviving record's *name* does not match
the surviving record's *feed*, or where two providers converge onto one record.
They are the top three rows of the table, with the reasoning in full.

1. **Norwalk Transit District (Connecticut) into Norwalk Transit System (California).**
   The one cross-state pairing in the set that is not explainable as a location
   typo. Two different cities named Norwalk both retire into the same record.
2. **Kayak Transit (CTUIR) into City of Milton-Freewater Public Transportation.**
   A tribal provider and a city provider converge on a record that carries the
   tribal feed under the city's name.
3. **The Current into Rockingham MOOver.** The successor carries a
   Southeast Vermont umbrella feed but is named for one local brand, while a
   separate MOOver record stays live.

## The 28

| Category | Retired record | Successor | Evidence and read |
| --- | --- | --- | --- |
| **UNCLEAR** | Kayak Transit (CTUIR) <br>`kayak-transit-ctuir` &middot; mdb-272 | City of Milton-Freewater Public Transportation <br>`city-of-milton-freewater-public-transportation-2189` &middot; mdb-2189 | The successor's feed URL is the CTUIR feed (`.../ctuir-or-us/ctuir-or-us.zip`) but the successor is NAMED for the City of Milton-Freewater. Separately, the real City of Milton-Freewater record (mdb-274, `.../milton-freewater-or-us/...`) retires into the SAME successor. So a tribal provider and a city provider collapse into one record that carries the tribe's feed under the city's name. |
| **UNCLEAR** | Norwalk Transit District <br>`norwalk-transit-district` &middot; mdb-529 | Norwalk Transit System (NTS) <br>`norwalk-transit-system-nts-2242` &middot; mdb-2242 | TWO DIFFERENT NORWALKS. The retired record is Norwalk Transit District in CONNECTICUT. The successor is filed as Norwalk Transit System (NTS) in CALIFORNIA (`organization_id: city-of-norwalk`), and California's own mdb-102 retires into it too. The successor's static feed is on `mystop.norwalktransit.com` while its realtime feeds are on `nts.rideralerts.com`, so the surviving record itself mixes hosts. This retirement would send a reader from a Connecticut agency to a page labelled California. |
| **UNCLEAR** | The Current <br>`the-current` &middot; mdb-428 | Rockingham MOOver <br>`rockingham-moover` &middot; mdb-2194 | The successor's feed is the `sevt-vt-us` umbrella feed, but the successor is NAMED Rockingham MOOver, and a SEPARATE live MOOver record (mdb-434, `dvtamoover-vt-us`) already exists, as does a third record on the same `sevt-vt-us--flex-v2` feed named Springfield MicroMoo. So The Current's readers land on a page named for one local brand of what looks like a multi-brand umbrella feed. |
| merger | Duarte Transit <br>`duarte-transit` &middot; mdb-105 | Foothill Transit <br>`foothill-transit` &middot; mdb-101 | Reads as a city shuttle absorbed into the regional operator. The successor is an older, larger, pre-existing record (mdb-101 < mdb-105) with no URL relationship to the retired feed. Nothing in the repo confirms the absorption; the catalog is the only evidence. |
| merger | Greater Glens Falls Transit <br>`greater-glens-falls-transit` &middot; mdb-542 | Capital District Transportation Authority (CDTA) <br>`capital-district-transportation-authority-cdta` &middot; mdb-538 | Local system into a regional authority. Successor is the older, larger pre-existing CDTA record (mdb-538 < mdb-542). A reader looking for Glens Falls will land on CDTA's page. |
| merger | High Desert Point <br>`high-desert-point` &middot; mdb-636 | Pacific Crest Bus Lines <br>`pacific-crest-bus-lines` &middot; mdb-133 | Reads as a route brand folded into its operator's record; both feeds sit on the Oregon/Trillium host under different slugs. Not an operator change as far as the repo shows, and the repo cannot confirm the operator relationship. |
| merger | Newburgh Beacon Shuttle (Leprechaun Lines) <br>`newburgh-beacon-shuttle-leprechaun-lines` &middot; mdb-584 | Leprechaun Lines <br>`leprechaun-lines` &middot; mdb-910 | Route brand into operator record; the retired record already names Leprechaun Lines in its own title, and both feeds are on the same 511NY bucket. |
| merger | Town of Telluride <br>`town-of-telluride` &middot; mdb-603 | San Miguel County <br>`san-miguel-county` &middot; mdb-2195 | Town service into the county record; Telluride sits in San Miguel County and both feeds are on Trillium under their own slugs. |
| rename | Avon Transit Flex <br>`avon-transit-2040` &middot; mdb-2040 | Avon Transit <br>`avon-transit-2433` &middot; mdb-2433 | Same town feed, service qualifier dropped. The retired record is the Trillium `--flex-v2` variant; the successor is the town's own combined feed. One agency, two feeds, now one. |
| rename | Birmingham Jefferson County Transit Authority <br>`birmingham-jefferson-county-transit-authority` &middot; mdb-339 | Birmingham Jefferson County Transit Authority (MAX) <br>`birmingham-jefferson-county-transit-authority-max-2263` &middot; mdb-2263 | Same host (`maxtransit.org`), MAX brand added to the name. The already-MAX-named mdb-1248 retires into the same successor, which is consistent. |
| rename | Bloom Tours <br>`bloom-tours` &middot; mdb-592 | Bloom Bus <br>`bloom-bus` &middot; mdb-2192 | Same private carrier, brand normalized Tours to Bus; the feed also moved off `mass.gov` onto Trillium. Name change and host change land together, so the pairing rests on the catalog. |
| rename | Boston Harbor Islands Ferries <br>`boston-harbor-islands-ferries-2073` &middot; mdb-2073 | Boston Harbor Islands Ferry <br>`boston-harbor-islands-ferry` &middot; mdb-2679 | Same NPS park unit (`/gtfs/boha/`), plural to singular. Note the retired record's URL is the Thompson Island ferry specifically, folded into a park-wide feed. SEE DATA NOTE 1. |
| rename | Boston Harbor Islands Ferries <br>`boston-harbor-islands-ferries` &middot; mdb-446 | Boston Harbor Islands Ferry <br>`boston-harbor-islands-ferry` &middot; mdb-2679 | Same park unit; legacy `nationalparkservice.github.io` host retired for `nps.gov`. SEE DATA NOTE 1. |
| rename | Cobb Community Transit (CCT) <br>`cobb-community-transit-cct` &middot; mdb-354 | CobbLinc <br>`cobblinc` &middot; mdb-3193 | Cobb County's CCT rebranded CobbLinc. Different host, but the successor's host (`cobb.rideralerts.com`) still names the county. |
| rename | CUE Bus <br>`cue-bus` &middot; mdb-2862 | Fairfax CUE Bus (CUE) <br>`fairfax-cue-bus-cue-2885` &middot; mdb-2885 | City of Fairfax CUE bus; the name gains the city. SEE DATA NOTE 2. |
| rename | Gloversville Transit Services <br>`gloversville-transit-services` &middot; mdb-540 | Gloversville Transit System <br>`gloversville-transit-system` &middot; mdb-2650 | Strongest evidence in the set: same 511NY S3 bucket, filename goes `Gloversville_Transit_Services.zip` to `Gloversville_Transit_System.zip`. |
| rename | HUT Airport Shuttle <br>`hut-airport-shuttle` &middot; mdb-635 | Oregon Express Shuttle <br>`oregon-express-shuttle` &middot; mdb-132 | Reads as a rebrand; both feeds on the Oregon/Trillium host. The successor record is older (mdb-132 < mdb-635), so this is a consolidation onto an existing record rather than a fresh one. |
| rename | JTRAN <br>`jtran` &middot; mdb-155 | City of Jackson (JTRAN) <br>`city-of-jackson-jtran` &middot; mdb-2652 | Same system, name gains the city; feed moved from Trillium to Passio. `jtran` appears on both sides. |
| rename | Middletown Area Transit <br>`middletown-area-transit` &middot; mdb-576 | Middletown Area Transit (MAT) <br>`middletown-area-transit-mat` &middot; mdb-551 | Name differs only by the (MAT) suffix. But the feed scope widens: `middletown-ct-us` becomes `ninetown-connecticut-us`, and the successor is the older record (mdb-551 < mdb-576). |
| rename | Mountain Line <br>`mountain-line-1148` &middot; mdb-1148 | Mountain Line Transit <br>`mountain-line-transit` &middot; mdb-1979 | Legacy `transitfeeds.com` mirror retired for the live `mountainline.syncromatics.com` feed; both records are Arizona. Worth knowing the name is not unique: the registry also carries a Montana `Mountain Line` and a West Virginia `Mountain Line Transit Authority`, neither touched here. |
| rename | Potomac and Rappahannock Transportation Commission (PRTC) <br>`potomac-and-rappahannock-transportation-commission-prtc` &middot; mdb-481 | Potomac and Rappahannock Transportation Commission (PRTC) Omniride <br>`potomac-and-rappahannock-transportation-commission-prtc-omniride` &middot; mdb-1156 | Same commission, OmniRide brand added; the feed follows the brand onto `omniride.com`. |
| rename | Redding Area Bus Authority (RABA) <br>`redding-area-bus-authority-raba` &middot; mdb-114 | Redding Area Bus Authority <br>`redding-area-bus-authority-3031` &middot; mdb-3031 | Name differs only by dropping the (RABA) suffix; same `organization_id: redding-area-bus-authority` on both sides. SEE DATA NOTE 3. |
| rename | San Mateo County Transit District (samTrans) <br>`san-mateo-county-transit-district-samtrans` &middot; mdb-49 | SamTrans <br>`samtrans` &middot; mdb-2708 | Same agency, same `samtrans.com` host, long name shortened to the brand. |
| rename | Sarasota County Area Transit <br>`sarasota-county-area-transit` &middot; mdb-327 | Breeze Transit <br>`breeze-transit` &middot; mdb-2260 | Reads as SCAT's Breeze rebrand. Both hosts change completely (`ftis.org` to `breezerider.tripsparkhost.com`), so the catalog is the only link between them. |
| rename | The JO <br>`the-jo` &middot; mdb-1160 | Johnson County Transit <br>`johnson-county-transit` &middot; mdb-2303 | Brand to legal name; the retired record is a `transitfeeds.com` legacy mirror. |
| rename | Transit Authority of River City (TARC) <br>`transit-authority-of-river-city-tarc` &middot; mdb-364 | Transit Authority of River City (TARC) Fixed Route <br>`transit-authority-of-river-city-tarc-2662` &middot; mdb-2662 | Same agency; the successor's name adds a mode qualifier. Worth noting the successor is scoped Fixed Route, so anything non-fixed-route the retired feed carried is not represented on the surviving page. |
| rename | UTA <br>`uta` &middot; mdb-1171 | Utah Transit Authority (UTA) <br>`utah-transit-authority-uta` &middot; mdb-170 | Abbreviation to full legal name. The retired record is a `transitfeeds.com` legacy mirror. |
| rename | UTA <br>`uta-2349` &middot; mdb-2349 | Utah Transit Authority (UTA) <br>`utah-transit-authority-uta` &middot; mdb-170 | Clearest duplicate in the set: same host, URLs differ only by the case of the filename (`gtfs.zip` vs `GTFS.zip`). |

## Data notes

These are observations about the records, not objections to the retirements.

**Data note 1 — Boston Harbor Islands Ferry is filed under New York.** The
successor record `boston-harbor-islands-ferry` (mdb-2679) carries
`subdivision_code: US-NY` while both retired records are `US-MA`. The feed
itself is on the National Park Service's Boston Harbor Islands path, so the
retirement reads as sound and the subdivision reads as wrong. It is worth
knowing that both Massachusetts records will redirect to a page labelled New
York.

**Data note 2 — the retired CUE Bus record lives in `registry/intake.yaml`.**
`cue-bus` (mdb-2862) sits in the intake file with no `subdivision_code`, and
retires into a Virginia record. It is the only one of the 28 whose retired side
is not in a state shard.

**Data note 3 — the Redding retirement creates a two-hop alias chain, and that
is legal.** Two hand-written records, `redding-area-bus-authority` and
`redding-area-bus-authority-raba-1972`, already aliased to
`redding-area-bus-authority-raba` on `main`, where it was a live record. This
pull request deprecates it. The loader walks alias chains transitively and
fails any chain that does not terminate at an active canonical feed
(`agencies.py`), and this chain terminates at `redding-area-bus-authority-3031`,
so it resolves. Noted because it is the only place in the 28 where an existing
hand-written alias changed meaning.

## Method

- Source of truth: the registry YAML shards as they stand on the pull request's
  branch, parsed with the same `agencies` schema the pipeline loads.
- The 28 were taken from the "Read these ones closely" section of the report the
  pull request generates, then re-joined against the full retirement table for
  their catalog ids, so the names and ids here are the branch's own, not
  retyped.
- Where a category rests on knowledge outside the repository, the evidence
  column says so.
