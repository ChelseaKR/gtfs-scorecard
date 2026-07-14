# Ideation archive: large-scale fixes and expansions

> **Status: historical planning record.** Drafted beginning 2026-07-01 and
> superseded as an active sequence on 2026-07-14. Many items shipped, some were
> partially absorbed into the service, and the remaining expansion ideas now
> sit behind the proof and demand gates in [`../roadmap.md`](../roadmap.md).

This folder preserves the structural analysis, candidate designs, and dated
sweeps that informed the service. It is useful evidence for why a capability
exists and what risks were identified. It is not a backlog to execute from top
to bottom.

## Current planning source

Use these documents for current decisions:

- [`../feature-roadmap.md`](../feature-roadmap.md): the ordered 90-day delivery
  list.
- [`../product-roadmap.md`](../product-roadmap.md): the product value and proof
  gates.
- [`../roadmap.md`](../roadmap.md): infrastructure, operating triggers, and
  demand-gated options.
- [`../competitive-positioning.md`](../competitive-positioning.md): why verified
  remediation is the current wedge and where neighboring projects already
  serve the market.

Do not start an item from this archive unless it is promoted into the current
roadmap with a named user, dependency, success measure, and stop condition.

## How this relates to the earlier planning set

The repo already carried a broad planning stack when this folder was drafted:

- `RESEARCH-ROADMAP.md` and `USER-RESEARCH.md` held the 2026-06-30
  synthetic-persona pass. Their R and E items are cited here as `RR:R#` and
  `RR:E#`.
- `expansion-ideation-2026-07.md` and `expansion-research-2026-07.md` held the
  July horizon scan. Much of it shipped quickly, including the MCP server,
  query and check tools, dataset releases, NTD triage, and Canada coverage.
- `follow-ups.md` held the operational S3 and compute work this folder assumed.

The status annotations inside each candidate remain the most precise record of
what shipped. The impact ranking and Now/Next/Later sequence in
[`04-impact-and-sequencing.md`](04-impact-and-sequencing.md) are preserved as a
dated snapshot and must not override the current roadmap.

## Contents

| File | What it holds |
| --- | --- |
| [`01-deep-dive.md`](01-deep-dive.md) | 2026-07 architecture, strengths, structural debt, and portfolio assessment |
| [`02-large-scale-fixes.md`](02-large-scale-fixes.md) | FIX-01 through FIX-13 structural candidates and their later status notes |
| [`03-expansions.md`](03-expansions.md) | EXP-01 through EXP-17 candidate expansions and their later status notes |
| [`04-impact-and-sequencing.md`](04-impact-and-sequencing.md) | The superseded impact matrix, dependencies, sequence, and declared gates |
| [`05-sweep-2026-07-10.md`](05-sweep-2026-07-10.md) | Mobile-performance evidence and the decisions taken from that sweep |
| [`06-sweep-2026-07-12.md`](06-sweep-2026-07-12.md) | Demo-readiness evidence plus FIX-14 through FIX-15 and EXP-18 through EXP-21 |

## Boundaries that still apply

The original warnings remain useful. These ideas were not automatically
validated with a real user, approved for infrastructure spend, or cleared for
public data redistribution. Human, partner, licence, and longitudinal-data gates
must still be satisfied rather than worked around.
