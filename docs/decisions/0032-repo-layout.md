# 0032 — Repo layout: `pipeline/` + `web/` + `infra/`, no root `pyproject.toml`

Status: accepted
Date: 2026-07-05

## Context

`CODE-QUALITY-STANDARD.md` (CQ-25/CQ-26) expects a single root-level Python
project manifest, and its named remediation for this repo reads "lift
`gtfs-scorecard` config and `uv.lock` to repo root." A 2026-07-05 conformance
audit scored CQ-25 PARTIAL (exactly one `pyproject.toml` exists, but it lives
at `pipeline/pyproject.toml`, not the repo root) and CQ-26 PARTIAL (the
`pipeline/`+`web/`+`infra/` split is real and sensible, but no ADR had ever
declared it, despite 29 other ADRs existing for smaller decisions). CQ-45
requires exactly this kind of standard-scope deviation to be recorded in an
ADR rather than left implicit.

The repo is not a single Python project wearing a monorepo layout by
accident. It genuinely ships three independently-shaped things:

- `pipeline/` — the only real Python project: fetch, validate, score,
  publish. Has its own `pyproject.toml`, `uv.lock`, `src/` + `tests/` layout,
  console scripts (`scorecard`, `scorecard-mcp`).
- `web/` — a deliberately no-build vanilla-JS static frontend. No
  `package.json`, no bundler, no Node toolchain anywhere in the repo (verified
  by the audit). It reads only pre-computed JSON that `pipeline/` publishes.
- `infra/` — Terraform modules (`artifacts`, `submit`, `compute`,
  `instant-score`, `alerts`), each independently applicable, most not yet
  applied (see `README.md`'s "Roadmap status: built vs deployed" table).

A root-level `pyproject.toml` would describe only `pipeline/` (the only
component that is Python), while implying — incorrectly — that the whole
repo is one Python project. `web/` and `infra/` have no meaningful shared
tooling with `pipeline/` to hoist into a root manifest.

## Decision

Keep the three-way split, and keep the single `pyproject.toml` at
`pipeline/pyproject.toml` rather than the repo root:

- Every CI workflow that touches Python sets `working-directory: pipeline`
  explicitly (`ci.yml`, `a11y.yml`, `e2e.yml`, `security.yml`'s
  Python-dependent jobs) — this is the SEC-42 pattern the audit credited as
  "fixed since June."
- The root `Makefile` delegates into `pipeline/` (`cd pipeline && uv run
  ...`) so `make verify` is the same one command regardless of the layout
  question underneath it.
- `pipeline/.python-version` and `pipeline/uv.lock` stay scoped to
  `pipeline/`, since that is the only directory `uv` needs to manage.
- This ADR is the CQ-26 declaration the standard requires; CQ-25 stays
  PARTIAL by design (one manifest, correctly placed for what this repo
  actually is, not at the path a single-Python-project assumption expects).

## Consequences

- A contributor cloning the repo runs `cd pipeline && uv sync`, not `uv sync`
  from the root — documented in `CONTRIBUTING.md` and `README.md`'s
  Quickstart.
- Tooling that assumes a root manifest (some "single Python repo" mechanical
  checks) will under-detect this repo's Python project; the audit already
  flagged and manually corrected for this (see AUDIT.md's Tier-1 notes on
  `single_pyproject`/`coverage_threshold_set`).
- If `web/` ever grows a real build step (a bundler, TypeScript), it gets its
  own manifest (`web/package.json`) rather than merging into the Python one —
  the same "each component owns its own toolchain" principle extends forward.
- If `infra/` Terraform ever needs shared root-level tooling (a single
  `terraform fmt`/`validate` entrypoint across modules), add it to the
  `Makefile` the same way `pipeline/` is delegated to, not by inventing a
  fourth layout pattern.
