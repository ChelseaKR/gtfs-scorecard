# 0. Record architecture decisions

## Status

Accepted

## Context

gtfs-scorecard makes consequential, hard-to-reverse decisions — the validator
runtime, where artifacts live, the `pipeline/` + `web/` + `infra/` repo split,
scoring-profile contracts, branch-protection rules. The reasoning behind a
structural choice must not live only in a commit message or a closed PR
thread, or a later change will either re-litigate a settled question or
unknowingly reverse a decision made for a reason nobody re-reads.

This repo has practiced this from early on: a substantial ADR log already
exists at [`docs/decisions/`](../decisions/), starting with
[0001-validator-runtime.md](../decisions/0001-validator-runtime.md). The
shared portfolio standards anchor the practice at `docs/adr/`; this record
formalizes the practice at that path without rewriting history.

## Decision

We will record architecture decisions in **Architecture Decision Records
(ADRs)** using the format described by Michael Nygard.

- Each ADR is a short Markdown file, numbered and named
  `NNNN-title-in-kebab-case.md`.
- Each ADR has the sections **Title**, **Status**, **Context**, **Decision**,
  and **Consequences**.
- **Status** is one of *Proposed*, *Accepted*, *Deprecated*, or *Superseded*.
  A superseded ADR is not deleted; it is marked superseded and points to the
  ADR that replaces it, and the replacement points back.
- ADRs are immutable once accepted, except to change their status. A new
  decision is a new ADR, not an edit to an old one.
- This repo's substantive ADR log lives at `docs/decisions/` (ADRs 0001
  onward), the location it has used since the project started. That log is
  kept where it is — its numbers are cross-referenced throughout the repo
  (README, standards audits, code comments) and accepted ADRs are immutable.
  `docs/adr/` holds this anchor record at the portfolio-standard path and
  points to the working log.

## Consequences

- The reasoning behind structural decisions is preserved and versioned
  alongside the code it explains.
- Writing an ADR is a small, deliberate friction on consequential change —
  intended, since it makes reversing a load-bearing decision a visible act
  rather than an accident.
- Anyone arriving via the portfolio-standard `docs/adr/` path is routed to
  the full log in `docs/decisions/` instead of finding nothing.
