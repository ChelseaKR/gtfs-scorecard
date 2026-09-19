# ADR 0059: Typed clients live in `clients/`, as projects of their own

**Status:** Accepted (2026-09-19)

## Context

Issue #370 asks for typed Python and TypeScript clients for the read API,
generated from its OpenAPI description. ADR 0032 records the repository as
three components, `pipeline/`, `web/` and `infra/`, each owning its toolchain,
with exactly one `pyproject.toml` (in `pipeline/`) and no Node toolchain
anywhere. It also says a new component goes into the Makefile "the same way
`pipeline/` is delegated to, not by inventing a fourth layout pattern."

The clients do not fit inside any of the three:

- They are separate distributions with their own names, their own version
  series and their own dependencies. A client's runtime dependencies are `httpx`
  and `attrs`, or `openapi-fetch`. Putting them in `pipeline/` would add those,
  and the two generators, to the pipeline's lockfile and to every image built
  from it. The point of the split in ADR 0032 is that each thing installs only
  what it uses.
- One of them is TypeScript. `web/` is a no-build static site and stays one.
  A `package.json` there would put a Node toolchain under the site the daily
  publish assembles.

## Decision

Add a fourth top-level directory, `clients/`, holding two independent projects:

- `clients/python`, one `pyproject.toml` and `uv.lock`, for
  `gtfs-scorecard-client`;
- `clients/typescript`, one `package.json` and `package-lock.json`, for
  `@gtfs-scorecard/client`.

Each owns its toolchain, as ADR 0032 already says of the other components, and
the root `Makefile` delegates to them (`make clients`, `clients-check`,
`clients-control`, `clients-test`, `clients-build`). This is that ADR's
principle applied once more, and it records the two places the ADR's text no
longer holds: the repository now has a second `pyproject.toml`, and a Node
toolchain, both confined to `clients/`.

The generators are pinned by exact version, are dev dependencies only, and run
under lockfiles. The pipeline's `pyproject.toml` and `uv.lock` do not change,
and `pipeline/tests/test_clients_drift.py` fails if they start to name a
generator. `web/` gains no `package.json`. The scripts that bundle the
description and run the generators sit in `pipeline/scripts/`, where the
repository's lint and type gates already reach them.

## Consequences

- `make verify` runs the cheap half of the drift check
  (`test_clients_drift.py`, no generator needed). The half that runs the
  generators is `.github/workflows/clients.yml`, which is path-filtered and so
  advisory. A required check that does not report on an unrelated pull request
  blocks it.
- A change to `web/api/v1/openapi.yaml` or a published schema now needs
  `make clients` in the same change. `make verify` says so when it is missing.
- The two client version series are independent of `pipeline/pyproject.toml`'s,
  so `check_versions.py` does not cover them. The publish workflow that does not
  exist yet needs its own check that a tag equals the package version.
- Dependency updates arrive for `clients/` like any other. A generator bump
  fails the drift check until the clients are regenerated.
- Nothing here publishes. `docs/typed-clients.md` lists the owner steps.
