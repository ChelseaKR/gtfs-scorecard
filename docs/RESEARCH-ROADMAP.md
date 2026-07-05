# Research roadmap: from the synthetic persona panel

> A triaged backlog derived from the synthetic persona panel in
> [`USER-RESEARCH.md`](USER-RESEARCH.md), turned into remediations (close gaps in
> what exists), expansions (new capability), a sequence, and a first sprint.
>
> **This document complements, and does not replace, the existing roadmap docs.**
> Read it alongside them; it cross-references rather than restates:
> - [`roadmap.md`](roadmap.md) — multiyear infrastructure and scaling plan (capacity).
> - [`product-roadmap.md`](product-roadmap.md) — multiyear user-value plan.
> - [`feature-roadmap.md`](feature-roadmap.md) — the near-term, ship-next feature list.
> - [`service-plan.md`](service-plan.md) — scorecard-to-service stages (monitor,
>   crosswalk, supporter workspace, compliance hook).
> - [`expansion.md`](expansion.md) and [`expansion-research.md`](expansion-research.md)
>   — the large-feature build plan and the persona/policy research behind it.
> - [`crosswalk.md`](crosswalk.md), [`conformance.md`](conformance.md),
>   [`vpat.md`](vpat.md), [`section-508-plan.md`](section-508-plan.md),
>   [`listing-policy.md`](listing-policy.md), and the ADRs in `decisions/`.
>
> Because the repo already ships a wide surface and already plans most of what the
> panel asked for, the honest finding is that **this roadmap mostly corroborates
> existing plans and finds a small number of genuinely net-new items.** Every item
> is tagged `[corroborates …]` (independent triangulation onto an existing plan or
> shipped feature) or `[NET-NEW]` (surfaced only by the panel).

## How to read the tags and scales

- **`[corroborates X]`** — the panel independently arrived at something already
  shipped, already planned in doc X, or already covered by an ADR. The value is
  prioritization and the persona evidence, not novelty.
- **`[NET-NEW]`** — not found in the existing docs or ADRs during the ground-truth read.
- **Priority.** P0 now · P1 next · P2 soon · P3 opportunistic.
- **Effort.** S ≈ an afternoon to a couple of days · M ≈ a week or two · L ≈ a month+.
- **Personas.** Reference the roster in [`USER-RESEARCH.md`](USER-RESEARCH.md#persona-roster).

## Research basis

All accessed 2026-06-30. High-stakes claims were cross-checked against two or more
sources; the repo's own `expansion-research.md` independently verified several of these.

**Spec and validator (the layer the tool sits on).**
- GTFS Schedule Reference and Best Practices.
  https://gtfs.org/documentation/schedule/reference/ ·
  https://gtfs.org/documentation/schedule/schedule-best-practices/
- GTFS Realtime Reference (TripUpdates, VehiclePositions, Alerts).
  https://gtfs.org/documentation/realtime/reference/
- Canonical GTFS Schedule Validator, rules and severities (ERROR = reference
  violation, WARNING = best practice, INFO = quality signal).
  https://gtfs-validator.mobilitydata.org/rules.html ·
  https://github.com/MobilityData/gtfs-validator
- MobilityData GTFS Grading Scheme: a validator-"valid" feed "may contain undetected
  qualitative errors that are unsuitable for rider-facing purposes."
  https://github.com/MobilityData/gtfs-grading-scheme/blob/main/scheme.md

**Why small agencies struggle (capacity, vendor dependence).**
- National RTAP free GTFS Builder and rural/tribal GTFS support (the capacity gap the
  scorecard's audience lives in).
  https://www.nationalrtap.org/Technology-Tools/GTFS-Builder ·
  https://www.nationalrtap.org/Technology-Tools/GTFS-Builder/Support
- Transit app, guidelines for producing GTFS static data (consumer-side expectations
  small agencies are held to).
  https://resources.transitapp.com/article/458-guidelines-for-producing-gtfs-static-data-for-transit

**The federal obligation (why a manager cannot ignore the feed).**
- FTA, NTD Reporting Changes and Clarifications, RY2023 (public GTFS required for
  fixed-route reporters).
  https://www.federalregister.gov/documents/2023/03/03/2023-04379/national-transit-database-reporting-changes-and-clarifications
- FTA, NTD Reporting Changes for RY2025 and RY2026, final rule (agency_id ↔ NTD ID
  handled internally via the P-50 form, after 15 of 18 commenters opposed a mandated
  agency-side change).
  https://www.federalregister.gov/documents/2025/07/10/2025-12813/national-transit-database-reporting-changes-and-clarifications-for-report-years-2025-and-2026
- Proposed rule (the stronger October 2024 version that was softened).
  https://www.federalregister.gov/documents/2024/10/31/2024-25341/national-transit-database-proposed-reporting-changes-and-clarifications-for-report-years-2025-and
- Corroborating secondary reads: Eno Center, "A Fistful of Data."
  https://enotrans.org/article/a-fistful-of-data-fta-updates-transit-database-reporting-requirements/ ·
  Interline, "US National Transit Database to collect GTFS URLs."
  https://www.interline.io/blog/us-ntd-reporting-gtfs/

**How feeds reach riders (the feared consequence behind freshness).**
- Google Transit Partners: an expired feed means trips stop appearing; keep the feed
  current; feed requirements and best practices.
  https://support.google.com/transitpartners/answer/10761734 ·
  https://support.google.com/transitpartners/answer/6394315 ·
  https://support.google.com/transitpartners/answer/6377351
- Google, quality benchmarks for realtime transit data.
  https://support.google.com/transitpartners/answer/7529583
- Apple Maps is consumed via the same canonical feed path; agencies route through the
  Mobility Database and aggregators rather than a documented direct upload.
  https://gtfs.org/getting-started/publish/

**The state bar the rubric maps to.**
- California Transit Data Guidelines (Compliance vs Beyond-Compliance tiers; Features
  checklist) and Minimum GTFS Guidelines v2.0.
  https://dot.ca.gov/cal-itp/california-transit-data-guidelines ·
  https://dot.ca.gov/cal-itp/california-minimum-general-transit-feed-specification-gtfs-guidelines-v2_0 ·
  https://dot.ca.gov/cal-itp/critical-gtfs-validation-errors
- Cal-ITP monthly GTFS quality reports (the existing, technical, California-only
  precedent).
  https://reports.calitp.org/ · https://reports.dds.dot.ca.gov/

**Data-quality and accessibility literature.**
- Devunuri & Lehe, "A Survey of Errors in GTFS Static Feeds from the United States,"
  *Findings* (2024): 21% of 632 feeds had an error, ten error types = 90% of
  occurrences, shape-distance and fare errors dominate. Supports the per-code,
  concentration-aware rubric.
  https://findingspress.org/article/116694-a-survey-of-errors-in-gtfs-static-feeds-from-the-united-states
- Disparities in public transit accessibility for people with mobility disabilities,
  *Journal of Transport Geography* (2023): missing accessible infrastructure and data
  sharply reduces reachable stops and opportunity.
  https://www.sciencedirect.com/science/article/abs/pii/S0966692323000613
- BlinkTag gtfs-accessibility-validator (checks the exact fields the rubric scores).
  https://github.com/BlinkTagInc/gtfs-accessibility-validator

## Remediation backlog (close gaps in what exists)

| ID | Remediation | Personas | Pri | Effort | Evidence / tag |
|---|---|---|---|---|---|
| R1 | **Resilient feed fetching** — browser-realistic User-Agent + `Accept`, retry/backoff on 403/429, fall back to Mobility Database `direct_download`; record "feed unreachable" as a neutral state distinct from a low grade | A1,A2,B1,D1,E4,F2 | P0 | M | `[corroborates feature-roadmap.md "Resilient feed fetching"]` — ~1/3 of real feeds 403 today |
| R2 | **Public self-serve claim + verify endpoint** so an agency turns on its own expiry/regression alerts (the built `notify.py`/SES loop's missing front door) | A1,F1,F2 | P0 | M | `[corroborates service-plan.md Stage 1 / ADR 0004]` |
| R3 | **Tiered expiry lead-time alerts (60/30/14/7 days)** so a subscriber sees a ramp, not a cliff-edge warning | A1,F1,E2 | P0 | S | `[corroborates feature-roadmap.md "Expiry forecasting"]`; Google guidance on staying current |
| R4 | **Show which findings cleared between runs** ("fixed since last check" by name) so a manager sees a specific fix land | A1,F1 | P0 | S | `[corroborates feature-roadmap.md / product-roadmap.md]` — strongest retention signal |
| R5 | **Per-vendor fix instructions** — name the exact export setting in the detected scheduling tool, not a generic description | A1,B1,F1 | P1 | M | `[corroborates product-roadmap.md Yr1 / service-plan.md Stage 4]` · ✅ Implemented 2026-07-01 (`tool_profiles.py`: producing tool detected from the feed host, named on the fix surfaces) |
| R6 | **Human assistive-technology pass to fill the VPAT functional-performance log** (NVDA+Firefox, VoiceOver+Safari; status/loading messages; map exceptions re-verified) | E3,E2 | P1 | M | `[corroborates section-508-plan.md Phase 2 / vpat.md "verification in Phase 2"]` — the AAA claim is asserted where it should be demonstrated |
| R7 | **Audit NTD-readiness copy against the RY2025/2026 final rule** so the `agency_id` flag never implies a mandated agency-side change (FTA handles it via P-50), and handle multi-dataset / shared-regional-feed agencies | E1,C2 | P1 | S | `[corroborates expansion-research.md caveat / ADR 0016]`; final rule · ✅ Implemented 2026-06-30 (working tree, uncommitted) |
| R8 | **Keep "states it, does not certify usability" unmissable in the UI** on the accessibility sub-score, conformance mark, and NTD flag (not only in docs) | E2,E3,E1,A3 | P1 | S | `[corroborates conformance.md / rubric.md framing]` `[NET-NEW: enforce in UI, not just prose]` |
| R9 | **Visible validator-version stamp + methodology changelog with effective dates** on the rubric/methodology page | C1,D3,E4 | P1 | S | `[corroborates roadmap.md "rubric fairness" / rubric.md "Last verified"]` `[NET-NEW: surface in UI]` · ✅ Implemented 2026-06-30 (working tree, uncommitted) |
| R10 | **Expired section in every program rollup** (lapsed vs long-expired, worst-first) and a cohort filter to lapsed feeds | F1,D2 | P1 | S | `[corroborates feature-roadmap.md "Recurring stale-feed report"]` |
| R11 | **Realtime freshness alongside schedule freshness** — flag a stale RT header with the same lapsed framing, never a missing-feed zero | A2,D1,F1 | P2 | S | `[corroborates feature-roadmap.md "Realtime freshness"]` |
| R12 | **`mdb_id` pinning in the registry** so re-discovery is exact and follows the catalog when a URL moves | F2,D1 | P2 | S | `[corroborates feature-roadmap.md "Pin Mobility Database ids"]` |
| R13 | **"Still operating?" `operating_note` for the long-expired bucket** so a confirmed-running feed reads as recoverable, not defunct | A2,F1 | P2 | S | `[corroborates feature-roadmap.md / listing-policy.md]` |
| R14 | **Liaison-ready outreach copy block** on each expired scorecard ("copy a note to the agency": what lapsed, rider impact, the one setting) | F1,A1 | P2 | S | `[corroborates feature-roadmap.md "Liaison-ready outreach copy"]` |
| R15 | **Recognize shared regional feeds and FTA-waived reporters** so a tribal/rural agency on a shared feed is not flagged for identity or coverage it does not own | A2,E1 | P2 | M | `[NET-NEW]` — FTA named these as the hard identity cases |
| R16 | **Ridership-weighted views** in rollups/leaderboard so a high-ridership low-grade feed ranks above a tiny one | D2,F1,E4 | P3 | S | `[corroborates ADR 0021]` · ✅ Implemented 2026-07-04 (`ridership.load_ridership`/`annual_trips_for`; the rollup attention list and the pulse "needs attention"/"lowest scoring" boards tie-break by NTD annual trips, with a "Riders/yr" column; degrades to unweighted order when the snapshot is absent) |

## Expansion backlog (new capability)

| ID | Expansion | Personas | Pri | Effort | Evidence / tag |
|---|---|---|---|---|---|
| E1 | **Supporter workspace** — saved cohorts, per-agency private notes, one-click call-prep export, shared-fix detection ("one setting fixes these five"), month-over-month cohort movement | F1,D2 | P1 | L | `[corroborates service-plan.md Stage 3 / product-roadmap.md Yr2]` — puts the supporter in the tool daily |
| E2 | **Rider-/manager-facing "will riders see my feed?" surface** — a plain lookup leading with expiry risk, tying the grade to Google/Apple/Transit ingestion in human terms | A1,D4,E2,E4 | P1 | M | `[corroborates expansion-research.md "Features for the general public" / crosswalk.md]`; Google expiry guidance |
| E3 | **Press methodology + "claims you may/may not make" explainer**, with size-band/ridership context shown beside any comparison | E4,C1 | P1 | S | `[NET-NEW]` (extends `/how-to-read/`); guards the no-shaming principle on the leaderboard |
| E4 | **Vendor-facing constructive worklist** — all feeds a vendor produces in one private view, framed as fixes, not public exposure | B1 | P1 | M | `[NET-NEW]` (turns the internal vendor signal in `vendors.py` outward, carefully) |
| E5 | **Acceptance-test / certificate deliverable for procurement** — clause tied to the conformance mark + state guideline, `scorecard try --min-grade` as a vendor gate, a dated certificate artifact | A3,B1 | P1 | M | `[corroborates expansion-research.md "procurement and board reporting" / conformance.md / ci-action.md]` |
| E6 | **Board-meeting one-pager** generated from the dated artifacts (grade, trend, three fixes), distinct from the liaison call brief | A1,F1 | P2 | S | `[corroborates expansion-research.md "more to do"]` (call brief shipped; board one-pager not) |
| E7 | **Citable, versioned dataset release** — a tagged release with a data dictionary, methodology version stamp, and stable reference (DOI-style) for researchers | D3 | P2 | M | `[NET-NEW]` — the dataset exists; a citable, pinned reference does not |
| E8 | **Change-feed / webhook on grade or expiry change** so a consumer subscribes instead of re-polling the catalog | D1,B1 | P2 | M | `[corroborates product-roadmap.md Yr3 "webhook on a grade change"]` |
| E9 | **Readable accessibility-coverage map** for riders and advocates, surfacing wheelchair, pathways/levels, and station step-free signals as one picture, with the usability caveat loud | E2,D4 | P2 | M | `[corroborates expansion-research.md "accessibility-coverage map" / ADR 0009]` |
| E10 | **Tract-level equity refinement wired live** and a custom cohort drawn to an MPO/region boundary | D2 | P2 | M | `[corroborates ADR 0015 remaining step / expansion.md Phase C]` |
| E11 | **Per-state guideline profiles** so the rubric cites the right authority per state, with non-California programs shown as resources | C2,E1 | P2 | L | `[corroborates service-plan.md Stage 6 / crosswalk.md / roadmap.md Yr3]` |
| E12 | **Benchmarking percentiles by size band**, shown privately and framed as encouragement, never a ranking | A1,F1,D2 | P3 | M | `[corroborates roadmap.md Yr2 / product-roadmap.md "Benchmarking with care"]` |
| E13 | **Spanish (and structured i18n) for the rider-facing surfaces first**, ahead of full UI translation | D4,E2 | P3 | M | `[corroborates roadmap.md Yr3 i18n / docs/standards INTERNATIONALIZATION-STANDARD]` `[NET-NEW: rider-surface-first ordering]` |
| E14 | **Continuous high-cadence national realtime archiving fleet** — the one remaining bet that forces a backend, beyond the serverless RT monitor already shipped | D1,E1 | P3 | L | `[corroborates expansion.md Phase B "always-on worker-fleet tier" / ADR 0018]` |

## Sequenced roadmap

The sequence threads the panel's findings through the existing plan rather than
beside it. Each phase is checked against the unchanging principles in
[`product-roadmap.md`](product-roadmap.md): fixes not failures, no shaming, score on
top of the canonical validator, accessibility prominent.

- **Phase 0 — Make the built work live (the deployment tail).** R1, R2, R3, R4. The
  panel's loudest, most consistent finding is that the retention loop is built but its
  front door and its reliability are not. Resilient fetching makes the grades
  trustworthy; the claim/verify endpoint plus tiered alerts plus the cleared-findings
  diff make someone come back. Nothing here is new code-shaped risk; it is finishing.
- **Phase 1 — Make the claims true and legible.** R6, R7, R8, R9, R5. Fill the VPAT
  functional-performance log with a human AT pass; audit NTD copy to the final rule;
  keep "states it, not certifies it" loud in the UI; stamp the validator version and
  methodology changelog; name the per-vendor export setting. Cheap, credibility-first,
  and aligned with who reviews this tool.
- **Phase 2 — Give each audience its own view.** E1 (supporter workspace), E2 (rider/
  manager "will riders see me?"), E5 (procurement certificate), E3 (press methodology),
  E6 (board one-pager), R10/R13/R14 (the expired-feed liaison loop). Renders over data
  that already exists, each unlocking one underserved role.
- **Phase 3 — Deepen the data product.** E4 (vendor worklist), E7 (citable dataset),
  E8 (change-feed), E9 (accessibility map), E10 (tract equity), E11 (per-state
  profiles), E12 (benchmarking), R11/R12/R15/R16. The capacity for all of this is in
  [`roadmap.md`](roadmap.md) Years 2–3.
- **Phase 4 — The remaining backend bet.** E13 (rider-first i18n), E14 (continuous RT
  fleet). Gated on demand, exactly as the existing docs gate them.

## Recommended first sprint

Highest leverage, mostly already-built infrastructure, all checked against the
no-shaming and accessibility-first principles. Ship these:

1. **R1 — resilient feed fetching.** The grades cannot be trusted while a third of
   real feeds 403. This unblocks the manager (a blocked feed must not read as her
   fault), the app developer (ingestion gating), and national coverage itself
   (`feature-roadmap.md` calls it the coverage prerequisite).
2. **R2 + R3 — public claim/verify endpoint and tiered expiry alerts.** Turns the
   built-but-dark retention loop on. The expiry-to-dropped-from-Maps consequence is the
   one every persona names; lead-time tiers give the warning while there is calm time
   to re-export.
3. **R4 — cleared-findings diff.** The strongest retention signal: a manager who
   changed one setting sees that specific fix land by name. Small, and it closes the
   loop R2/R3 opens.
4. **R6 — human AT pass to fill the VPAT log.** The accessibility specialist's core
   ask and the project's own values statement. The site claims AAA; the
   functional-performance evidence should exist to back it. An afternoon of real AT
   time converts an assertion into proof.
5. **R7 + R8 — NTD copy accuracy and the "states it, not certifies it" caveat in the
   UI.** Cheap, protects trust with the oversight, steward, and advocate audiences, and
   keeps the tool from overclaiming an obligation or a usability guarantee it cannot make.

Bundle the afternoon-sized wins alongside: **R9** (version stamp), **R10** (expired
rollup section), **R14** (outreach copy block).

## Traceability matrix (persona → findings)

| Persona | Remediations | Expansions |
|---|---|---|
| A1 Inherited-feed manager | R1, R3, R4, R5 | E2, E6 |
| A2 Rural/tribal flex coordinator | R1, R11, R13, R15 | — |
| A3 Procurement officer | R8 | E5 |
| B1 Vendor engineer | R1, R5 | E4, E5, E8 |
| C1 MobilityData steward | R9 | E3 |
| C2 State-program steward | R7 | E11 |
| D1 App ingestion engineer | R1, R11, R12 | E8, E14 |
| D2 MPO / planner | R10, R16 | E1, E10, E12 |
| D3 Researcher | R9 | E7 |
| D4 Rider (indirect) | — | E2, E9, E13 |
| E1 NTD oversight | R7, R15 | E14 |
| E2 Advocate | R3, R8 | E2, E9 |
| E3 Accessibility specialist | R6, R8 | — |
| E4 Journalist | R1, R9, R16 | E2, E3 |
| F1 Liaison | R2, R3, R4, R5, R10, R13, R14 | E1, E6, E12 |
| F2 Owner/maintainer | R1, R2, R12 | — |

## Validate with real users / risks

This backlog is built on synthetic interviews. Before committing engineering time
beyond the first sprint, test the load-bearing assumptions with real people, one per
group, starting with the two reachable, already-served roles.

- **Does the retention loop actually retain (R2–R4)?** Watch one real liaison and two
  or three real managers over a month. Do they return after an alert? Is the
  cleared-findings diff the moment that matters? If they do not come back, no amount of
  workspace polish (E1) helps.
- **Is the no-shaming framing robust to a real journalist (E3, E4)?** Show the
  leaderboard and a draft methodology page to a reporter. Watch whether they reach for
  the unfair ranking anyway. If the framing fails with a sympathetic reader, the public
  surfaces need rethinking, not just a caveat.
- **Will a real vendor accept a vendor-facing view (E4)?** This is the persona the
  project has least contact with, and the one where the value/risk balance is most
  uncertain. Interview one before building; a vendor worklist could be a distribution
  channel or a relationship-ender.
- **Does the rider surface (E2/E9/E13) serve a real rider, or the maintainer's idea of
  one?** The rider is an indirect beneficiary by design; a rider-facing surface is a
  hypothesis with no current user. Validate demand before building, or accept that the
  rider is served only through the agency.
- **Is the AT pass (R6) genuinely done by an assistive-tech user?** The repo can script
  the walkthrough but cannot substitute for a real NVDA/VoiceOver session; the
  functional-performance claim is only as good as the human who runs it.

**Risks to name.** (1) Scope drift: every expansion is a temptation to become a feed
editor, a validator, or a general platform; check each against the inherited-feed
manager and the liaison. (2) The cost guardrail: anything always-on (E14, a real
backend) must justify itself against single-digit dollars a month. (3) Overclaiming:
the conformance mark, the accessibility number, and the NTD flag each measure published
data, not compliance or usability; the credibility of the whole tool rests on that
caveat staying loud (R8). (4) Adopting a coarse fix from this synthetic panel as if it
were validated demand.

## Honest limits

This roadmap inherits every limitation of the synthetic panel it is built on (see
[`USER-RESEARCH.md`](USER-RESEARCH.md#honest-limits-of-this-exercise)). It cannot tell
you which items have real demand, how many of each user exist, or what they would adopt
or pay for. Its main contribution is not new ideas, the existing roadmap docs already
hold most of these, but a persona-evidenced *prioritization* and a clear separation of
"finish what is built" (Phase 0) from "build something new." The single most important
takeaway is the cross-cutting one: the scorecard's highest-leverage work right now is
operational, closing the gap between built and live, not adding surfaces. Treat the
`[NET-NEW]` items (R8-in-UI, R9-in-UI, R15, E3, E4, E7, E13-ordering) as the only places
this exercise meaningfully extends the existing plan, and validate them before
committing.
