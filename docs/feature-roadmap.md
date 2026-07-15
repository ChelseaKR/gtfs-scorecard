# Feature roadmap

Last updated: 2026-07-15

This is the ordered delivery list for the next 90 days. It implements the
proof-first direction in [`product-roadmap.md`](product-roadmap.md) and uses the
operating gates in [`roadmap.md`](roadmap.md). Earlier FIX, EXP, and RR lists are
research history, not parallel queues.

## Status

The previous feature list shipped across about 1,128 published scorecard pages.
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

### 1. Publish and verify `v1.2.1`

Status: completed 2026-07-15. The signed release and public
[Marketplace listing](https://github.com/marketplace/actions/gtfs-scorecard-gate)
are live, and both supported refs passed the
[downstream consumer check](https://github.com/ChelseaKR/gtfs-scorecard-action-smoke/actions/runs/29454018351).

Done means:

- immutable `v1.2.1` and signed floating `v1` tags point to the intended commit;
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

## Not on the ship list

- More general score, map, viewer, catalogue, or validation surfaces.
- Public agency or vendor rankings.
- A public raw-feed or continuous cross-agency realtime archive.
- Broad international expansion without a local steward.
- Consumer-app scraping, multimodal health scoring, or a replacement ticket
  system.
- AI-generated repair or automatic closure in the trusted path.

Revisit this file when a pilot cycle finishes or a maintenance trigger fires.
Otherwise the order does not change.
