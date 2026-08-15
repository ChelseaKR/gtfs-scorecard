# Retirements that need a person: what is flagged, and why

A retirement is one record giving up its current grade to another: `alias_of`
plus `feed_status: deprecated`, written from the Mobility Database's own
`redirect.id`. It is the right thing to do when two records are one agency, and
it stops the site publishing two grades under one name. It is the wrong thing to
do when the two records are not one agency, and the failure is quiet: both
records are well-formed, the alias chain resolves, every other check passes, and
the site publishes one agency's feed under another agency's name.

That happened. A review of the retirements whose successor publishes under a
different name found three worth a second look, and the reason a person had to
find them by reading a table is that nothing in the pipeline was looking.

## What is flagged

Two shapes hold a retirement back until someone decides it. Both are computed
from the registry itself, so they apply to a retirement written by the weekly
sync and to one written by hand.

- **`different_subdivision` / `different_country`** — the successor is in
  another state, province or country. Agencies do rename themselves; they do not
  usually move across a state line while doing it. This is the flag that catches
  a pairing whose names look perfectly ordinary.
- **`name_not_a_rename`** — the successor's name has no distinctive word in
  common with the record retiring into it, is not its acronym, and is not it
  with a brand or a qualifier added or dropped. Generic words (transit,
  authority, district, regional, of, the) are ignored, and obvious plurals are
  folded, so "Gloversville Transit Services" to "Gloversville Transit System"
  passes and "Duarte Transit" to "Foothill Transit" does not. A name with
  nothing in common is a merger, an operator change, or a mistake, and all three
  change what the page means to the person reading it.

One more is reported and never blocks: **`subdivision_unknown`**, one side with
no subdivision recorded, so the two cannot be compared. That is a gap in the
registry rather than evidence of a wrong retirement, and failing the build on it
would only teach people to type a location in to clear the gate.

## Where the decision lives

`supersession-review.yaml`, at the repository root. Each entry names the retired
record, the successor, the flags exactly as the check computes them, a decision,
and the evidence it rests on:

- `retire` — one agency, or a real merger. The retirement stands.
- `keep_separate` — not the same agency. The record keeps its own page, and the
  weekly sync must not re-apply the catalog's redirect next month.

The evidence field is required. A decision with no stated reason is not
reviewable by the next person, so the file refuses it.

Two things enforce this:

- `scorecard supersessions` will not write a flagged retirement without an
  approving entry. It reports each held one instead, with the reasons and a
  ready-to-paste block, under "Held for review" in `docs/feed-supersessions.md`.
- `pipeline/scripts/check_supersession_review.py` runs in `make verify`, which
  is what CI runs. It fails while any flagged retirement in the registry has no
  decision, while a decision names a pairing the registry does not record, while
  a record marked `keep_separate` is retired anyway, and while an entry is left
  behind after its retirement or its flags have gone. It re-derives the flags
  from the registry rather than trusting the file, so the two cannot drift.

Entries arrive by pull request, which this repository's ruleset requires a code
owner to review. That review is the sign-off; the file is its record.

## What this found in the batch already recorded

Run against the batch of retirements as they were recorded, the rule holds
**fifteen**: **five** whose successor is in another state, and **ten** whose
successor's name does not read as a rename. Six more have a missing subdivision
on one side and are noted rather than held. The rest, the large majority, are
plain renames inside one state and apply exactly as before.

Every one of the five cross-state pairings turned out to be a real defect: one
undone retirement and three records published under the wrong state. All four
are corrected here, so nothing in the registry crosses a state line any more,
and what is left holding is the ten name changes, each with a decision and its
evidence in the review file.

One limit is worth stating plainly. The retirement that was actually wrong
(California's mdb-102) was **not** itself cross-state, because the record it
pointed at was mislabelled as Californian too. What the flag caught was the
Connecticut record retiring into the same place, and reading that cluster is
what turned the California one up. A flag that makes someone look at a cluster
is doing its job even when the defect is one record over.

### The three that were read closely, and what the feeds say

Feed contents below come from this repository's committed artifacts
(`data/artifacts/<id>/latest.json`): the stop bounding box and the route names
the fetched feed actually carried. The catalog CSV was not re-fetched;
`files.mobilitydatabase.org/robots.txt` returns `User-agent: * / Disallow: /`.

**1. The two Norwalks — and the error is the other way round.** The retirement
that reads wrong from the metadata is Connecticut's mdb-529 into mdb-2242, a
record filed under California. The feeds say the opposite. mdb-2242's stops span
41.02-41.24N, 73.63-73.03W and its routes run to Norwalk Community College, SoNo
Station and Norwalk Hospital: it is the **Connecticut** agency's current feed,
mislabelled as California, with the California city's `organization_id` attached
to it. mdb-102, the record that also retires into it, is the genuine Los Angeles
County agency (33.87-34.07N, 118.13-117.96W; Cerritos College, Rio Hondo, 166th
Street).

So the Connecticut retirement is sound and the **California one is the error**.
mdb-2242 is now recorded as Connecticut, named for the Connecticut agency whose
feed it publishes, and moved into `registry/us/ct.yaml`; the California record
keeps its own page, with a standing `keep_separate` decision so the sync does
not re-apply the redirect.

**2. Kayak Transit (CTUIR) and the City of Milton-Freewater.** The successor
mdb-2189 carries the tribal provider's feed (path `ctuir-or-us`; routes Mission
Metro, Walla Walla Whistler, Hermiston Hopper, and the Nixyaawii Community
Shuttle) under the city's name, and the city's own record retires into it too.
The catalog can distinguish them — the feed path and the route list are
unambiguous — so the finding is not that they are indistinguishable but that the
record was named for the wrong one of the two. It is now named for the tribal
provider that publishes the feed. Both retirements stand: the CTUIR feed carries
a Milton - Freewater route, so the city's riders are represented in it, and the
city's own 48-stop feed has expired service data. The record's id still reads
`city-of-milton-freewater-public-transportation-2189` because an id is a public
URL and the address of that record's dated artifacts; the published name is what
a reader sees, and that is corrected.

**3. The Current, the MOOver, and what `sevt-vt-us` actually is.** The successor
mdb-2194 was named "Rockingham MOOver", one local brand. Its feed carries The
Current's entire route set (Springfield In-Town, Bellows Falls In-Town, the
Brattleboro Red, Blue and White lines, the Dartmouth and VA runs) together with
the MOOver's (Wilmington-West Dover, Mount Snow, Readsboro), so it is neither
brand alone. It is now named Southeast Vermont Transit, for the operation whose
feed it is. The MOOver's own record (mdb-434) is still current in the catalog
and keeps its page, though all nine of its routes appear in the successor's feed
as well.

### Errors the flag caught that nobody had reported

These three were not in anyone's review. They are the same class of harm as the
Norwalk case — a feed published under the wrong jurisdiction — and the
cross-state flag surfaced all three the first time it ran.

- **County Connection (CCCTA) was filed under Tennessee.** The successor record
  mdb-2421 sat in `registry/us/tn.yaml` while its feed covers Contra Costa
  County, California (37.66-38.02N, 122.19-121.78W; routes to Concord, Walnut
  Creek and Pleasant Hill BART). Corrected to California.
- **Southern Nevada's RTC was filed under California.** The retired record
  mdb-110's stops are the Las Vegas valley (35.96-36.31N, 115.33-114.83W), and
  its successor was already correctly in Nevada. Corrected to Nevada.
- **Boston Harbor Islands Ferry was filed under New York.** mdb-2679's stops are
  Boston Harbor (42.25-42.36N, 71.05-70.92W) and its routes are Georges Island,
  Peddocks Island, Spectacle Island and the Hingham run. Both records retiring
  into it are Massachusetts. Corrected to Massachusetts.

Each correction also clears the flag honestly: the pairing no longer crosses a
state line because the location was wrong, not because anyone signed it off.

## Left open, deliberately

- **The two Norwalk records list the same three realtime endpoints.** Both
  mdb-102 (California) and mdb-2242 (Connecticut) carry the same
  `nts.rideralerts.com` trip-update, vehicle-position and alert URLs. At most one
  of them can be right. Nothing in the committed data attributes them, so they
  are left exactly as they were and recorded here as an open question rather
  than reassigned on a guess.
- **Six retirements have no subdivision on one side** (CUE Bus, Long Island Rail
  Road, Springfield Mass Transit District, Cecil Transit twice, GoTriangle).
  Filling those in is registry work, not a retirement decision, so they are
  noted and not held.
- **The MOOver's own record duplicates part of the Southeast Vermont feed.** The
  catalog still calls mdb-434 current, so nothing here retires it. Whether it
  should keep a separate page is a curator call.
- **One Vermont record has the id `vtrans` and the name "Springfield
  MicroMoo"**, on the Southeast Vermont flex feed. Neither the id nor the name
  describes what it publishes. Left alone here because changing an id changes a
  public URL.

## Method

- The registry shards as they stand in this branch, parsed with the same schema
  the pipeline loads.
- Feed contents from the committed artifacts, which are what the site graded.
- The catalog's own CSV was not re-fetched, for the robots.txt reason above, so
  every claim here is checkable inside this repository.
