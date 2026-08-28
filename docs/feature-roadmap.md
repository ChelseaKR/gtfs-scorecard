# Feature roadmap

Last updated: 2026-07-25

The multiyear arc across all of these is [`multiyear-plan.md`](multiyear-plan.md).

This is the ordered delivery list for the next 90 days. It implements the
proof-first direction in [`product-roadmap.md`](product-roadmap.md) and uses the
operating gates in [`roadmap.md`](roadmap.md). Earlier FIX, EXP, and RR lists are
research history, not parallel queues.

## Status

The previous feature list shipped across more than 2,100 published scorecard pages.
Daily scorecards, program rollups, alerts, finding-clearance records,
provenance, data contracts, the read API, MCP server, badges, and the reusable
Action and its Marketplace listing are available. They now support the work
below.

The active constraint is not missing dashboard surface. It is the lack of real
evidence that an accepted request can be linked to a comparable change in the
intended published feed.

## Active sequence

Work through this list in order. Do not start later product expansion to fill a
participant or release dependency.

### 1. Publish and verify `v1.4.0`

Status: completed 2026-07-25. The signed release and the project's first public
[Marketplace listing](https://github.com/marketplace/actions/gtfs-scorecard-gate)
are live, and both supported refs passed the
[downstream consumer check](https://github.com/ChelseaKR/gtfs-scorecard-action-smoke/actions/runs/30167946534).

Done means:

- immutable `v1.4.0` and signed floating `v1` tags point to the intended commit;
- the release carries the manifest signature, certificate, SBOM, VEX, and
  provenance assets;
- the Marketplace listing is publicly visible in Code quality and Testing;
- clean downstream runs succeed against both tags and produce JSON and HTML.

### 2. Recruit and contract the pilot

Status: active.

Recruit one support-program liaison and two feed maintainers or vendors. Agree
on feed identity, owner role, existing handoff channel, privacy boundary, and
what a valid recheck means. Select recurring findings with a concrete export or
data change.

Wasco Dial-a-Ride is one evidence-backed recruitment lead because its official
Caltrans DDS archive is still the January 2022 upload and scores as expired.
Participation and feed identity still require explicit confirmation.

Done means at least two participants accept a named request and the project has
six suitable requests available for the 90-day window.

### 3. Produce the first closure receipt manually

Status: depends on a participant request.

Use shipped provenance and private evidence paths. Preserve before and after
bytes, tool versions, feed identity, and the finding fingerprint. Link the
accepted action privately. Count a closure only after the intended feed is
rechecked under a comparable measurement contract.

Done means an independent reviewer can reproduce the receipt. A finding that
merely disappears is still a finding clearance.

### 4. Remove the smallest repeated friction

Status: evidence-gated.

After the first manual cycle, automate only a step that repeatedly consumes
time or creates evidence risk. Candidate work includes a private request
manifest, a receipt schema, or one handoff adapter. Do not build a generic
workflow UI before the pilot identifies the actual channel.

Done means the change reduces hands-on support time without weakening the
identity or comparability checks.

### 5. Complete six requests and audit the outcome

Status: depends on steps 2 through 4.

Run three cycles, audit every claimed closure, interview participants, and
measure time to owner and hands-on support. Apply the pass and stop conditions in
[`roadmap.md`](roadmap.md#5-decide-at-day-90).

Done means the project has a documented decision to automate, narrow, change,
or stop the workflow. Marketplace installs and scorecard traffic do not decide
this gate.

## Queue after a passing pilot

This queue is ordered but not active:

1. Publish the open receipt schema and verifier.
2. Build the agency-owned quality passport.
3. Rank pilot notice playbooks by observed evidence.
4. Productize one existing handoff integration.
5. Add the procurement acceptance record.
6. Extend program views with privacy-safe aggregate outcomes.

Each item must remain independently shippable and must preserve the fail-closed
receipt contract.

## Maintenance lane

Keep daily scoring, security, accessibility, source curation, and release health
green. Complete renderer decomposition, registry sharding, queue-backed compute,
or hosted scoring only when the measurable triggers in
[`roadmap.md`](roadmap.md#maintenance-with-explicit-triggers) fire.

One direct consumer-feedback slice is also in this lane because it repairs an
existing surface without changing a grade or adding a service:

- **Shipped 2026-07-16:** primary navigation to the feature finder,
  `translations.txt` detection and language filtering, aligned API and CSV
  fields, a visible coverage limitation, mode-aware language, the ungraded
  ferry profile, and the auditable European beta gate.
- **Shipped 2026-07-17:** the reviewed European depth wave (27 records from
  the Spain, France, United Kingdom, Germany, and Italy queues; the cohort is
  now 42 records in 13 countries, with rejections documented), and the
  interface-localization readiness layer (app string catalog, `en-XA`
  pseudolocale preview, right-to-left browser check, hardcoded-string and
  directional-CSS ratchets; ADR 0038).
- **Shipped 2026-07-25:** Mobility Database proposal receipts now account for
  every recognized Schedule source row with a versioned mechanical disposition
  ledger. Schema 1.2 validates receipts before either output is written and
  binds each external identity to the public registry record that currently
  carries it. Proposals remain separate from human identity, rights,
  attribution, and admission decisions (ADR 0043).
- **Shipped 2026-08-27:** the alert stack reads a planned service boundary
  from the published scorecard, closing EXP-04's open RR:R3 half. A campus or
  seasonal feed at the end of a service period is no longer told by email that
  trip planners have dropped it, on the same morning its page calls the same
  event a planned transition. Wording only, on the opt-in alert channel and the
  weekly cohort digest: no tier, ordering, grade, or public page moved
  (ADR 0047).
- **Shipped 2026-08-27:** the plain-language readability gate now reads every
  finding the scorecard publishes, not only the curated validator translations.
  The findings the pipeline authors itself (accessibility, completeness, fares,
  flexible service, pathways, routability, realtime, freshness) were half the
  finding copy on an agency page and had never been measured by the gate that
  exists to measure it; 23 strings missed the existing bars and were rewritten.
  The inventory refuses a `Finding(...)` site whose copy it cannot read, so the
  gate's coverage cannot narrow again silently. No threshold, score, grade or
  schema moved (ADR 0048).
- **Shipped 2026-08-27:** the complexity register is checked against ruff
  instead of by hand (#309), and the published weight-sensitivity study grades
  the published score rather than the raw weighted average (#310). Both were
  controls that read as enforcement and could not fail over the thing they
  covered (ADR 0050).
- **Shipped 2026-08-27:** a render failure names the feed it happened to
  (#308). Re-raised with the slug, never swallowed; whether one bad artifact
  should abort the whole site render is left as a separate product call.
- **Next only through curation:** work the European candidate queue toward the
  beta gate in [`global-expansion.md`](global-expansion.md). Feed count alone
  does not pass source, license, identity, freshness, or country-spread review.
  Sweden needs Trafiklab API credentials before any record can be reviewed.
- **Still steward-gated:** full interface localization (a production language
  needs a named steward; the engineering prerequisites are in place) and any
  NeTEx ingestion.

## Not on the ship list

- More general score, map, viewer, catalogue, or validation surfaces.
- Public agency or vendor rankings.
- A public raw-feed or continuous cross-agency realtime archive.
- Broad international expansion without the source, license, identity, and
  local-steward gates.
- Consumer-app scraping, multimodal health scoring, or a replacement ticket
  system.
- AI-generated repair or automatic closure in the trusted path.

Revisit this file when a pilot cycle finishes or a maintenance trigger fires.
Otherwise the order does not change.
