# Ideation: large-scale fixes and expansions

Drafted 2026-07-01. This folder holds a layer of planning the existing documents
deliberately do not: structural, large-scale fixes and longer-horizon expansions,
generated from a fresh full read of the code, the CI surface, and the published
data contract.

## How this relates to the existing planning set

The repo already carries an unusually complete planning stack. This folder does
not restate it; it references it by ID and goes past it.

- [`../roadmap.md`](../roadmap.md), [`../product-roadmap.md`](../product-roadmap.md),
  [`../feature-roadmap.md`](../feature-roadmap.md) — the multiyear capacity, value,
  and ship-next plans.
- [`../RESEARCH-ROADMAP.md`](../RESEARCH-ROADMAP.md) and
  [`../USER-RESEARCH.md`](../USER-RESEARCH.md) — the 2026-06-30 synthetic-persona
  pass; its R1–R16 and E1–E14 items are cited here as `RR:R#` / `RR:E#`.
- [`../expansion-ideation-2026-07.md`](../expansion-ideation-2026-07.md) and
  [`../expansion-research-2026-07.md`](../expansion-research-2026-07.md) — the July
  horizon scan, much of which shipped the same day (MCP server, /query/, /check/,
  dataset releases, NTD RY2026 triage, Canada).
- [`../follow-ups.md`](../follow-ups.md) — the operational checklist (S3 cutover,
  fan-out compute) this folder builds on rather than repeats.

Everything here is intended to be net-new relative to that set. Where an idea
extends an existing item, the existing ID is named and the delta is stated.

## Contents

| File | What it holds |
| --- | --- |
| [`01-deep-dive.md`](01-deep-dive.md) | Current-state assessment from a fresh read: architecture, genuine strengths, observed structural debt, portfolio position |
| [`02-large-scale-fixes.md`](02-large-scale-fixes.md) | FIX-01…FIX-13: deep structural fixes (correctness, provenance, architecture, testing, operability) |
| [`03-expansions.md`](03-expansions.md) | EXP-01…EXP-17 across three horizons: deepen the core, adjacent capabilities, transformative bets |
| [`04-impact-and-sequencing.md`](04-impact-and-sequencing.md) | Impact × effort matrix, dependencies, a Now/Next/Later sequence beyond the existing roadmaps, and the human/legal/SME/real-data gates |
| [`05-sweep-2026-07-10.md`](05-sweep-2026-07-10.md) | Dated sweep: mobile performance evidence, eight candidates considered, four implemented |
| [`06-sweep-2026-07-12.md`](06-sweep-2026-07-12.md) | Demo-readiness check against live CI and pipeline evidence, plus FIX-14…15 and EXP-18…21 |

## What this folder is not

These are ideas for evaluation, not commitments. Nothing here has been validated
with a real user, costed against the single-digit-dollars-a-month guardrail, or
approved by the maintainer. Several items are explicitly gated on humans, real
data, or partners; per the portfolio ethos, those gates are declared rather than
worked around, and nothing below should be built by faking its gate.
