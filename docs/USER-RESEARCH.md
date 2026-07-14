# User research: synthetic personas and simulated interviews

> [!WARNING]
> **These personas and interviews are synthetic.** They were generated as a
> structured way to pressure-test the scorecard from every stakeholder angle at
> once. No real person said any of this. Each "quote" is a hypothesis to validate
> with a real user, not evidence of demand. This is consistent with how the
> project labels its own synthetic and provisional material (see the "re-verify"
> notes in [`expansion.md`](expansion.md) and the adversarial-verification method
> in [`expansion-research.md`](expansion-research.md)). Do not prioritize a
> roadmap off this document alone; use it to design the questions for real
> discovery.
>
> **Last assembled: 2026-06-30.**

## Why do this at all

The scorecard already serves two named users well (the inherited-feed transit
manager and the program liaison). But it now ships a wide surface, NTD readiness,
a conformance mark, a public API, an accessibility-coverage view, an equity
overlay, a national realtime monitor, that touches stakeholders the two-user
framing never interviews. Role-playing the full cast forces the question "who is
each surface actually for, and where would they stall?" The synthesis lives in
[`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md), tagged so it complements the
existing roadmap docs rather than restating them.

## Method

- **Frame.** Everyone who touches a GTFS feed's quality, or the grade the
  scorecard puts on it: the agency that owns the feed, the vendor that produces
  it, the standards bodies that define "good," the apps and analysts that consume
  it, the oversight and audit roles that hold agencies to it, and the people who
  operate the tool. Personas are composite archetypes of these real segments.
- **Protocol.** Each card carries a **goal**, then a four-to-five line simulated
  interview: **Values today** (mapped only to features that actually exist in the
  repo), **Gets stuck**, **Wants next**, and **Adopts / walks**. Frictions feed
  the remediation backlog; wishes feed the expansion backlog in
  [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md).
- **Research basis.** Persona needs and the high-stakes claims behind them were
  checked against primary sources (access date 2026-06-30). The full cited
  evidence base is in [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md#research-basis);
  the load-bearing ones:
  - The NTD GTFS obligation that gives a small agency a non-optional reason to
    care: FTA requires fixed-route NTD reporters to publish and maintain a public
    GTFS feed from Report Year 2023
    ([FTA, RY2023 final rule](https://www.federalregister.gov/documents/2023/03/03/2023-04379/national-transit-database-reporting-changes-and-clarifications)),
    and the RY2026 policy requires a stable `agency_id` for every reporter
    represented in the feed, crosswalked to the five-digit NTD ID on P-50; the
    two values do not have to be equal
    ([FTA, 2026 NTD Full Reporting Policy Manual](https://www.transit.dot.gov/sites/fta.dot.gov/files/2026-06/2026-NTD-Full-Policy-Manual_0.pdf)).
  - The concrete feared consequence behind freshness: an expired feed stops a
    trip from appearing in Google Maps
    ([Google Transit Partners, general errors](https://support.google.com/transitpartners/answer/10761734),
    [keep your feed from expiration](https://support.google.com/transitpartners/answer/6394315)).
  - That a validator-clean feed can still be rider-wrong, which is the gap the
    plain-language layer fills: MobilityData's grading scheme notes a feed
    "flagged as valid by an automated validator may contain undetected
    qualitative errors that are unsuitable for rider-facing purposes"
    ([MobilityData GTFS Grading Scheme](https://github.com/MobilityData/gtfs-grading-scheme/blob/main/scheme.md)).
  - That errors are real but concentrated, so a per-code (not per-instance)
    rubric is defensible: 21% of 632 US feeds had at least one validator error,
    and ten error types accounted for 90% of occurrences
    ([Devunuri & Lehe, *Findings*, 2024](https://findingspress.org/article/116694-a-survey-of-errors-in-gtfs-static-feeds-from-the-united-states)).
- **Honest tag.** Where a persona's wish matches something already shipped or
  already planned, the roadmap marks it `[corroborates …]`; only genuinely new
  asks are `[NET-NEW]`. Independent triangulation onto an existing plan is a
  signal, not noise.

## How to read a persona

Each card is one role compressed to its decision: what they get from the tool as
it stands, the wall they hit, the next thing they would ask for, and the single
condition that flips them to adopting or walking away.

## Persona roster

| # | Persona | Group | Primary goal | Top friction |
|---|---|---|---|---|
| A1 | **Dolores** — manager, 18-bus city system, inherited the feed | Fix My Feed | Know if the vendor's feed is any good without learning GTFS | The official monthly report is technical; she can't tell what to do first |
| A2 | **Ray** — coordinator, rural + tribal dial-a-ride, fare-free | Fix My Feed | Not get dinged for running flexible, fare-free, seasonal service | Worries a demand-response feed reads as broken or empty |
| A3 | **Priya** — agency contracts/procurement officer | Fix My Feed | Write feed quality into the next vendor solicitation | No language to require a quality bar a vendor must hit |
| B1 | **Marcus** — engineer at a GTFS vendor serving many small agencies | Produce & Vendor | Ship feeds that pass before a client or app rejects them | A public grade on his clients' feeds could read as blame |
| C1 | **Lena** — MobilityData-style standards steward | Steward the Standard | Keep the ecosystem on the canonical validator and spec | Needs assurance the tool tracks, not forks, the rules |
| C2 | **Hiro** — state-program GTFS data steward (Cal-ITP-style) | Steward the Standard | See the grade map to the guideline agencies are held to | Wants the rubric legible against the state's own checklist |
| D1 | **Sam** — ingestion engineer at a trip-planner app | Consume the Data | Decide which feeds are safe to ingest, at scale | Needs one machine-readable pull, not one request per agency |
| D2 | **Aisha** — MPO / regional planner and modeler | Consume the Data | Use feed quality + equity to target where help goes | Quality and need data live in different places |
| D3 | **Tomas** — academic transit-data researcher | Consume the Data | Study how feed quality changes over time, citeably | No stable, versioned, citable reference for the dataset |
| D4 | **Gloria** — rider, no car, screen-reader user | Consume the Data | Trust that her bus shows up correctly in her app | She never sees the feed; she only feels it when it breaks |
| E1 | **Frank** — FTA / state-DOT NTD oversight staff | Assure & Audit | See which reporters meet the federal GTFS obligation | No NTD-keyed national readiness view |
| E2 | **Naomi** — transit / disability-access advocate | Assure & Audit | Push agencies to publish accessibility data riders need | Hard to show coverage gaps without shaming small agencies |
| E3 | **Wei** — accessibility specialist auditing the UI + VPAT | Assure & Audit | Confirm the AAA / 508 claim is real, not asserted | The VPAT's functional-performance log is still unfilled |
| E4 | **Dana** — journalist comparing agencies | Assure & Audit | Report a checkable claim about local transit data | A comparison view risks becoming a small-agency leaderboard |
| F1 | **Ramona** — program liaison / customer-success manager | Operate | Walk into an agency call knowing the three things to raise | Cohort prep is manual; no saved notes or call export |
| F2 | **Chelsea** — owner / maintainer | Operate | Keep it cheap, accessible, and worth a second visit | Most code is built; the gating work is human and operational |

---

## Group A — Fix My Feed (the agency improving its own feed)

### A1 — Dolores, manager of an 18-bus city system who inherited the feed
- **Goal.** Find out whether the GTFS her predecessor's vendor set up is healthy,
  and what to fix first, without becoming a GTFS expert.
- **Values today.** The plain-language **letter grade** with four category scores
  and the **"top 3 things to fix"** framed as fixes with effort hints; the
  **NTD certification-readiness** read (published, valid, current, agency_id present); the
  **notice-to-fix knowledge base** (`/fix/<code>/`) that turns a validator notice
  into one setting to change. "The state's monthly report lists `foreign_key_violation`
  and a 24-item checklist. This tells me my feed expires in 19 days and that's the
  thing that drops me from Google Maps."
- **Gets stuck.** The fix pages describe the change generically; she does not know
  which button in her specific scheduling tool does it. She is not sure the alert
  will reach her before the feed lapses, and there is no obvious way to turn alerts
  on from the page. She half-expects a low grade to feel like a judgment on her
  agency.
- **Wants next.** Per-vendor fix instructions that name the exact export setting
  in her tool; a self-serve "watch this feed, email me before it expires" button;
  a one-line "will riders still see me?" statement tying the grade to Google /
  Apple ingestion; a board-meeting one-pager she can paste into an agenda.
- **Adopts if** it tells her something before it bites and gives her the fix in her
  own tool's words. **Walks if** it reads like the official report, one more
  technical artifact she cannot act on.

### A2 — Ray, coordinator of a rural and tribal dial-a-ride, fare-free
- **Goal.** Publish good data for demand-response, fare-free, seasonal service
  without the tool treating "different" as "broken."
- **Values today.** The **`service_type: seasonal` / `demand_response`** handling
  so a between-seasons gap is scored fairly; **`fare_free: true`** crediting the
  fare component instead of docking it; **GTFS-Flex awareness** (ADR 0007) that
  checks whether a rider can actually book a trip; the neutral **"Not yet
  published"** for realtime rather than a zero. "Most tools assume a fixed-route
  city bus. This one knows a fare-free dial-a-ride isn't a failing feed."
- **Gets stuck.** He builds GTFS by hand (National RTAP's free GTFS Builder) and
  is not sure the scorecard's framing reaches a tribal agency that shares a
  regional feed or has an FTA waiver. The flex booking check can read as a demand
  for fields his small operation does not produce.
- **Wants next.** A path that recognizes a shared regional feed and a waived
  reporter without flagging them; the National RTAP support channel surfaced as a
  resource on the page; flex "how to book" rendered for the rider, not just
  checked for the producer.
- **Adopts if** the tool stays neutral about service that is legitimately
  different. **Walks if** "incomplete" gets confused with "non-standard."

### A3 — Priya, agency contracts and procurement officer
- **Goal.** Make the next vendor contract require a feed quality bar, so the
  agency stops inheriting feeds nobody can vouch for.
- **Values today.** The **`/procurement/` copy-paste RFP/contract clause**; the
  **conformance mark** (valid, current, accessible) as a bright-line credential a
  contract can name; the **CI Action / GitHub Marketplace gate** that fails a
  build below a `min-grade` so a vendor proves quality before delivery.
- **Gets stuck.** She needs the clause to reference a bar a vendor can be held to
  objectively, and a way to verify a delivered feed against it without running Java
  herself. She is unsure whether the conformance mark is recognized outside this
  tool.
- **Wants next.** Clause language tied to the conformance mark and to the state
  guideline by name; an acceptance-test recipe (`scorecard try --min-grade`) she
  can hand a vendor as a deliverable gate; a dated certificate artifact for the
  contract file.
- **Adopts if** it makes a vendor's quality contractually checkable. **Walks if**
  procurement does not recognize the output as a standard.

---

## Group B — Produce & Vendor (those who generate the feeds)

### B1 — Marcus, engineer at a GTFS vendor serving dozens of small agencies
- **Goal.** Catch feed problems before a client, an app, or a state report does,
  across all the agencies he produces for.
- **Values today.** The **CI Action** he can drop into his own publish pipeline to
  gate on grade and days-to-expiry; **`scorecard try`** for an instant grade on a
  zip before it ships; the **rule links** that point each finding at the canonical
  validator notice or GTFS Best Practice, so the fix is unambiguous; the **badge**
  a happy client can embed. "I can fail my own build on a bad feed before it
  reaches the agency's site."
- **Gets stuck.** The **vendor-accountability** signal and the stale-feed-by-vendor
  view are framed for the program, not for him; a public grade on his clients'
  feeds could read as naming-and-shaming the vendor. He wants the same view turned
  constructively toward fixing, not toward exposure.
- **Wants next.** A vendor-facing roll-up of all the feeds he produces, framed as
  a worklist; an auth-aware adapter so he can gate hosted/keyed feeds in CI; early
  warning when a software update of his quietly breaks one field across many client
  feeds at once.
- **Adopts if** it helps him fix his clients' feeds before anyone else notices.
  **Walks if** the vendor view becomes a public blame board.

---

## Group C — Steward the Standard (the ecosystem keepers)

### C1 — Lena, MobilityData-style standards steward
- **Goal.** Keep the community on one canonical validator and one spec, and not
  see a fork that diverges quietly.
- **Values today.** The hard guardrail that the scorecard **scores on top of the
  canonical validator and does not re-validate GTFS**; the **rule links** that send
  every finding back to the validator rules page, `gtfs.org` best practices, or the
  spec reference; the **Mobility Feed API reuse** (ADR 0011) that skips
  re-validating identical bytes; the explicit **crosswalk to the GTFS Grading
  Scheme's seven fields**. "It cites our notices and our version. It's a layer, not
  a competing validator."
- **Gets stuck.** Wants to know the pinned validator version (v8.0.1) and how fast
  the tool adopts a new release and new notices; worries a "grade" could be read as
  a competing authority to the validator's own output.
- **Wants next.** A visible validator-version stamp and changelog on the
  methodology; a clear statement that the grade is interpretation, not
  certification; an upstream path to feed real-world fix patterns back to the
  community knowledge base.
- **Adopts if** the tool stays a faithful, versioned layer over the canonical
  tools. **Walks if** it drifts into re-implementing or contradicting the validator.

### C2 — Hiro, state-program GTFS data steward (Cal-ITP-style)
- **Goal.** Give agencies a grade that maps cleanly to the state guideline they are
  actually measured against.
- **Values today.** The **`crosswalk.md` / "how this agency maps to the standards"**
  section tying the four categories to the California Transit Data Guidelines v4.0,
  the Minimum GTFS Guidelines, the Grading Scheme, Google/Apple, and the NTD
  obligation; the rubric's **anchoring to v4.0 compliance tiers**; the honest note
  that the grade is "a data-quality lens, not the official compliance determination."
- **Gets stuck.** The crosswalk is California-deep; agencies in states that run a
  GTFS program but no quality rubric (Colorado, Michigan, Minnesota, Oregon,
  Washington) get the program shown only as a resource, not as a bar the score maps
  to. The official monthly report and the scorecard tell overlapping but
  differently-shaped stories.
- **Wants next.** Per-state guideline profiles so the rubric cites the right
  authority per state; an explicit alignment with the monthly report so a manager is
  not confused by two numbers; a partnership posture toward the state program rather
  than a parallel one.
- **Adopts if** it amplifies the state's own bar in plainer language. **Walks if** it
  competes with the official report instead of translating it.

---

## Group D — Consume the Data (downstream consumers, ending with the rider)

### D1 — Sam, ingestion engineer at a trip-planner app
- **Goal.** Decide which of thousands of feeds are safe to put into production, and
  re-check cheaply.
- **Values today.** The **flat `/catalog.json` and `/catalog.csv`** (grade, score,
  feed URL, days-to-expiry, top fix) that answer in one request, not one per agency;
  the **versioned static `/api/v1/`** (agencies, per-state aggregates, national
  stats); the **`map.geojson`**; the **badge JSON**. "A shared read on a feed's
  quality before I ingest it is exactly the 'shared understanding before production'
  the validator's authors say they built for."
- **Gets stuck.** Roughly a third of real feeds currently fail an automated fetch
  (WAF / User-Agent 403s on government-hosted feeds), so a feed he could ingest may
  show as unreachable; he cannot subscribe to "tell me when this feed's grade or
  expiry changes," only re-poll.
- **Wants next.** Resilient fetching so a blocked feed scores instead of reading as
  unreachable; a change-feed or webhook on grade/expiry change; GeoJSON and a stable
  schema he can pin.
- **Adopts if** the catalog is reliable enough to gate ingestion. **Walks if** fetch
  gaps make the grades look unreliable.

### D2 — Aisha, MPO / regional planner and modeler
- **Goal.** Aim limited technical-assistance dollars at the agencies where poor
  data overlaps high need.
- **Values today.** The **`/equity/` overlay** (state-level ACS poverty,
  zero-vehicle, disability shares joined to grades); the **program rollups** with a
  worst-first attention queue; the **`dataset.parquet` / CSV / JSON** for her own
  analysis; the **national map** and **all-routes** views. "It flags high-need states
  carrying many low-grade feeds. That is a triage list."
- **Gets stuck.** Equity is state-level; she works at tract and corridor scale. The
  rollups are configured by cohort, not drawn to her MPO boundary out of the box.
- **Wants next.** The built tract-level equity refinement wired live; a custom cohort
  drawn to her region; ridership-weighted views so a big-ridership low-grade feed
  ranks above a tiny one.
- **Adopts if** it sharpens where her program spends time. **Walks if** the geography
  is too coarse to act on.

### D3 — Tomas, academic transit-data researcher
- **Goal.** Study national feed-quality change over time and cite it in a paper.
- **Values today.** The **dated per-agency artifacts** as a longitudinal record; the
  **national quality trend** (ADR 0020) and **`/trends/`**; the open
  **dataset.{json,csv,parquet}**; the documented, versioned read API.
- **Gets stuck.** There is no stable citable reference (a versioned release, a DOI,
  a data dictionary, a methodology version stamp) he can point a reviewer at; the
  rubric weights can change, and without a pinned methodology version his numbers are
  not reproducible.
- **Wants next.** A versioned, citable dataset release with a data dictionary; a
  methodology changelog with effective dates; a documented schema version on every
  artifact.
- **Adopts if** it is a credible, citable research substrate. **Walks if** the
  methodology shifts under him with no version to pin.

### D4 — Gloria, rider with no car who uses a screen reader
- **Goal.** Trust that her bus appears, on time and correctly, in the app she uses.
- **Values today (indirectly).** She never opens the scorecard. She benefits when an
  agency acts on the **freshness** warning before the feed expires and the app drops
  the route; when **`wheelchair_boarding`** is populated so her app knows a stop is
  accessible; when **headsigns and readable stop names** mean the app shows "Downtown"
  not "STOP 0041." The tool's whole value to her is upstream.
- **Gets stuck.** Nothing the scorecard publishes today is written for her. If she
  did land on it (from a journalist's story, an advocate's post), the agency page is
  built for the manager, not the rider, and the accessibility-coverage view is a data
  surface, not a "is my bus okay?" answer.
- **Wants next.** A rider-readable "is my agency's feed healthy?" lookup that leads
  with the expiry risk in human terms; the accessibility-coverage view made readable
  for a rider or advocate; Spanish, given who rides.
- **Adopts if** there is ever a surface that answers her question in her language.
  **Walks if** the tool stays entirely producer-facing (which is fine, but then she
  is served only through the agency).

---

## Group E — Assure & Audit (independent scrutiny and oversight)

### E1 — Frank, FTA / state-DOT NTD oversight staff
- **Goal.** See, nationally, which fixed-route reporters actually meet the federal
  GTFS obligation, and where the known feed-identity gaps are.
- **Values today.** The **`/ntd/` national certification-readiness page** reading
  `ntd.json`; the per-agency **NTD readiness** section (published, valid, current,
  agency_id present) and the **optional `agency_id`-to-NTD-ID equality flag** populated by
  **`scorecard ntd-crosswalk`** from the Transitland Atlas; the framing that the
  equality result carries no score. "This surfaces exactly the
  feed-identity and freshness gaps the rulemaking documented."
- **Gets stuck.** RY2026 requires a stable `agency_id` and P-50 crosswalk, but
  not equality to the NTD ID, so the copy must keep those two facts separate;
  agencies with multiple datasets, multiple brandings, or a
  shared regional feed are the exact identity cases FTA flagged and the hardest to
  match cleanly.
- **Wants next.** Readiness copy audited against final-rule (not proposed-rule)
  language; explicit handling of multi-dataset and shared-feed agencies; the national
  readiness counts exportable as evidence for the next rulemaking.
- **Adopts if** the readiness view is accurate to the final rule. **Walks if** it
  overstates an obligation agencies do not actually carry.

### E2 — Naomi, transit and disability-access advocate
- **Goal.** Press agencies to publish the accessibility data riders depend on,
  without shaming the small ones into defensiveness.
- **Values today.** Accessibility's **prominent placement** in the rubric (the two
  wheelchair components carry 40 of 100 rider-experience points) and the standalone
  **accessibility sub-score** (ADR 0006); the **`/access/` national
  accessibility-coverage view**; the **conformance mark's 90% accessibility floor**;
  the firm "**absence is shown neutrally, never a zero**" principle. The research she
  cites is real: mobility-disabled riders reach far fewer accessible stops when the
  data and infrastructure are missing
  ([J. Transport Geography, 2023](https://www.sciencedirect.com/science/article/abs/pii/S0966692323000613)).
- **Gets stuck.** The coverage view measures what the feed *states*, not whether a
  stop is physically usable; she needs that caveat to stay loud so a "90% accessible"
  number is not misread as 90% of stops being usable. The view is a data surface, not
  an advocacy-ready story.
- **Wants next.** A readable accessibility-coverage map for riders and advocates; the
  "states it, does not certify usability" caveat kept unmissable; the pathways/levels
  and station step-free signals surfaced together as one accessibility picture.
- **Adopts if** it moves agencies to publish the fields without shaming them. **Walks
  if** the number gets read as a usability guarantee it cannot make.

### E3 — Wei, accessibility specialist auditing the scorecard's own UI and VPAT
- **Goal.** Confirm the WCAG 2.2 AAA / Section 508 claim is real, not asserted.
- **Values today.** The **published VPAT (508 edition)** with per-criterion Supports
  / Partially Supports rulings and documented map exceptions; the **merge-blocking
  axe / Lighthouse / pa11y gate**; the **contrast gate across every theme**; the
  honest **Partially Supports** call on the national all-routes map. "This is a real
  AAA effort with documented exceptions, not a badge."
- **Gets stuck.** The VPAT's functional-performance rows (302.1 Without Vision) say
  "verification in Phase 2," and the manual assistive-technology results log in
  `accessibility-testing.md` is scripted but **awaiting a human AT pass**. The
  strongest claim is the one without lived-experience evidence behind it yet.
- **Wants next.** A dated NVDA+Firefox and VoiceOver+Safari walkthrough filling the
  results log; a screen-reader check of the live result-count and loading status
  messages; the map exceptions re-verified by an AT user.
- **Adopts if** the functional-performance log gets filled by a real AT session.
  **Walks if** the AAA claim stays asserted where it should be demonstrated.

### E4 — Dana, journalist comparing agencies
- **Goal.** Publish a checkable claim about how local transit data quality compares.
- **Values today.** The **`/leaderboard/`** and per-state aggregates; the **open,
  reproducible artifacts** anyone can re-pull; the **national "state of transit data"**
  framing in the problems and trends pages; the **`/how-to-read/`** explainer. "The
  numbers are public and reproducible, so I can cite them."
- **Gets stuck.** The product principle is "no leaderboard that shames small
  agencies," but a journalist's comparison is exactly the use that can turn the
  leaderboard into a ranking-to-lose; she needs the methodology and the caveats in
  plain language so a story does not misread a low grade as a bad agency.
- **Wants next.** A plain-language methodology and "what a grade does and does not
  mean" explainer written for press; a "claims you may and may not make" note; context
  (size band, ridership) shown next to any comparison so the story is fair.
- **Adopts if** she can publish a verifiable, fairly-framed claim. **Walks if** the
  tool either hides comparison or invites an unfair one.

---

## Group F — Operate (run the program and the tool)

### F1 — Ramona, program liaison / customer-success manager
- **Goal.** Open one screen before an agency check-in call that says how the data is
  doing and the three things to raise, across every agency she supports.
- **Values today.** The **program rollups** ("needs attention" when expiring or
  regressed, worst-first); the per-agency **printable call brief** (`/agency/<id>/brief/`);
  the **"what changed since last check"** summary; the **opt-in digest** (`notify.py`)
  filtered to just her agencies; the **liaison outreach copy** for an expired feed.
  "The rollup is my Monday worklist; the brief is what I bring to the call."
- **Gets stuck.** She cannot save private notes per agency, cannot draw a custom
  cohort to her own portfolio without editing YAML, and the shared-fix detection ("one
  export setting fixes these five agencies") is described but not yet a button. The
  public claim/verify endpoint that lets an agency turn on its own alerts is the
  missing piece of the retention loop.
- **Wants next.** The supporter workspace (saved cohorts, per-agency notes, one-click
  call-prep export, shared-fix detection); month-over-month cohort movement; the
  self-serve claim/verify endpoint live so agencies subscribe themselves.
- **Adopts if** it plans her week and prepares her calls. **Walks if** prep stays as
  manual as a spreadsheet.

### F2 — Chelsea, owner and maintainer
- **Goal.** Keep the tool cheap, accessible, and worth a second visit, without the
  scope creeping into a validator or a feed editor.
- **Values today.** The **static-artifact architecture** (no API server in the render
  path) that keeps hosting trivial; the **idempotent daily pipeline**; the **ADR
  trail** (0001–0024) recording every non-obvious call; the **CI gates** (ruff, mypy,
  pytest, axe) that make it hard to break; the discipline that **most of the roadmap
  is already built**, with the remaining work being operational, not code.
- **Gets stuck.** The gap between "built" and "live" is human and operational: the
  self-serve claim/verify endpoint, the human AT pass, resilient fetching so a third
  of feeds stop 403-ing, and tuning what counts as worth an alert. There is no view of
  whether agencies actually return.
- **Wants next.** Close the built-but-not-deployed items in priority order; a light
  signal of repeat visits and which fix pages are the organic entry points; keep the
  cost guardrail and the no-shaming principle intact as coverage grows.
- **Adopts** the discipline of shipping the operational tail over building new
  surfaces. **Walks** the project into trouble only by letting scope drift off the
  inherited-feed manager and the liaison.

---

## Cross-cutting themes (what the cast agrees on)

1. **The tool is feature-rich and deployment-poor.** The single most repeated
   friction across Dolores, Sam, Ramona, and Chelsea is not a missing feature; it is
   a built feature that is not yet live or not yet discoverable: the self-serve
   claim/verify endpoint, resilient fetching, the per-vendor fix wording, the human AT
   pass. The highest-leverage work is finishing the operational tail, not adding
   surfaces. This sharpens, rather than overturns,
   [`feature-roadmap.md`](feature-roadmap.md) and [`service-plan.md`](service-plan.md).
2. **Freshness is the load-bearing promise.** The expiry-to-dropped-from-Maps chain is
   the one consequence every agency-side and consumer-side persona names as concrete
   and feared. Lead-time alerts, predictive freshness, and the claim/verify loop that
   delivers them are the retention engine, corroborated by Google's own guidance.
3. **Frame as fix, never failure, holds the whole product together, and is fragile at
   scale.** The vendor (B1), the advocate (E2), and the journalist (E4) each describe a
   surface (vendor view, coverage view, leaderboard) that could tip into shaming. The
   no-leaderboard principle is a feature, and it needs explicit guardrails on exactly
   those three surfaces.
4. **"States it" is not "certifies it," and that caveat has to stay loud.** The
   accessibility-coverage number, the conformance mark, and the NTD readiness flag all
   measure what a feed *publishes*, not real-world usability or official compliance.
   Frank, Naomi, Wei, and Hiro independently insist the caveat stay unmissable; it is
   already in the docs and must stay in the UI.
5. **Each audience wants its own surface over the same artifacts.** The engine and the
   data are rich; the *views* are thin for some roles: a rider-readable lookup (Gloria),
   a vendor-facing worklist (Marcus), a press methodology page (Dana), a citable dataset
   release (Tomas), a supporter workspace (Ramona). Most are renders over data that
   already exists.
6. **Accuracy of claims about external obligations is a credibility lever.** Frank's NTD
   final-rule nuance and Hiro's per-state-guideline gap are both about the tool stating
   the external bar correctly. Getting the federal and state framing exactly right is
   cheap and protects trust.

## Honest limits of this exercise

This is simulated. It can surface plausible needs and obvious gaps, but it cannot tell
you which are real, how many of each user exist, or what any of them would pay or adopt.
It over-represents the maintainer's mental model of these roles and will miss what only a
real liaison, a real vendor, or a real rider would surprise you with. Several personas
(the vendor, the app developer, the rider) are roles the project has had little direct
contact with, so their cards are the least trustworthy and the most in need of real
discovery. Do not treat any "want" here as validated demand. The honest next step is
real conversations with at least one person in each group, starting with the two the
tool already serves (the inherited-feed manager and the liaison) because they are
reachable and their feedback is load-bearing.

The triaged backlog, the sequenced plan, the traceability matrix, and the validation
plan derived from these interviews are in
[`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md).
