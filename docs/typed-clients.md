# Typed clients

Two clients for the [read API](api.md) live under `clients/`, generated from its
[OpenAPI description](../web/api/v1/openapi.yaml):

| | Python | TypeScript |
|---|---|---|
| Package name | `gtfs-scorecard-client` | `@gtfs-scorecard/client` |
| Directory | [`clients/python`](../clients/python) | [`clients/typescript`](../clients/typescript) |
| Generator | `openapi-python-client` | `openapi-typescript` (types) with `openapi-fetch` (requests) |
| Published | No | No |

Neither package is published. Publishing needs a registry account, and for PyPI
a trusted publisher, that only the repository owner can set up. The steps for
that are [at the end of this page](#publishing-owner-steps). Everything before
that step is built, tested and checked here.

The client reads the same files a browser would. There is no key, no session
and no write path, and the clients add none.

Why these live in a fourth top-level directory and not in `pipeline/` or `web/`:
[ADR 0059](decisions/0059-typed-clients-layout.md).

## What is generated and what is written by hand

| Path | Written by |
|---|---|
| `clients/openapi.bundled.json` | `pipeline/scripts/bundle_openapi.py` |
| `clients/python/src/gtfs_scorecard_client/generated/` | `openapi-python-client` |
| `clients/typescript/src/generated/schema.ts` | `openapi-typescript` |
| `clients/GENERATED.json` | `pipeline/scripts/generate_clients.py` |
| `clients/python/src/gtfs_scorecard_client/{__init__,guard,session}.py` | by hand |
| `clients/typescript/src/{index,guard}.ts` | by hand |
| `clients/fixtures/`, both `tests/` directories, both READMEs | by hand |

`make clients` deletes and rewrites the generated paths and leaves the rest.

The hand-written layer is small on purpose: a `schema_version` guard, and a
factory that turns it on. `docs/api.md` asks consumers to tolerate added fields
and to treat a change in the major version as a breaking change. The guard
raises (`UnsupportedSchemaVersion` in Python, `UnsupportedSchemaVersionError` in
TypeScript) when a JSON response carries a `schema_version` whose major version
is not the one the client was generated against. That major is written in each
guard and a test binds it to `x-artifact-schema-version-major` in the
description.

## The bundle

`openapi.yaml` refers to the published schemas with root-relative references such
as `$ref: /schemas/artifact.schema.json`. That works on the host that serves both
files and does not work for a generator running in a checkout. The bundle
resolves each reference into a component and hoists the schema's own `$defs`
beside it. Three small changes make the schemas readable by a generator without
changing what they accept:

- `$schema` and `$id` are dropped, because they would re-base the references.
- `title` becomes `x-title`, because a generator names a type from its title.
- An array schema with no `items` gets `"items": {}`, which is the same
  constraint stated out loud. The Python generator otherwise drops the whole
  model that contains it.

Keywords a generator cannot express (`if`, `then`, `not`, `dependentRequired`)
stay in the bundle and are ignored by it. A generated type is therefore never
stricter than the schema. The schema remains the validating contract.

One defect in the pinned Python generator is patched at generation time. It
reads a model with a local variable named `d`, and the grade distributions have
a property for grade D, so `by-location.json` and every rollup failed to parse.
`generate_clients.py` renames the local in a copy of the generator's template
and refuses to run if the template no longer matches, so a fixed release is
noticed rather than patched over. The patch is a few lines in that script.

## Keeping the clients true

Two checks, split by cost.

1. **In `make verify`, so merge-blocking.** `pipeline/tests/test_clients_drift.py`
   needs no generator. It fails when the committed bundle is not what the
   description and schemas produce, when `clients/GENERATED.json` does not name
   that bundle and the pinned generator versions, and when the manifest of
   recorded responses stops covering every described path. Everything after the
   bundle is deterministic, so a matching stamp means a matching client.
2. **In `.github/workflows/clients.yml`, advisory because it is path-filtered.**
   `make clients-check` regenerates into a temporary directory and compares every
   derived file byte for byte. It also sees a hand edit inside generated code and
   a generator whose output moved under an unchanged pin.

Both have negative controls, so a check that stopped noticing would fail rather
than pass over nothing. The controls change a copy of the description, a copy of
a schema, and a copy of the generated code, and require the check to fail for
each. `make clients-control` runs them against the real generators, and the
same functions run in `test_clients_drift.py` without them.

To change the API: edit `docs/api.md`, `openapi.yaml` and, where relevant, a
schema in the same change, then run `make clients` and commit everything it
wrote. If `make verify` says the clients are stale, that is the step it means.

### Supply chain

- Each generator is pinned to an exact version and is a dev dependency only.
  `openapi-python-client` is in the `dev` dependency group of
  `clients/python/pyproject.toml`; `openapi-typescript` is a `devDependency`.
  Neither is a runtime dependency of the published package.
- `clients/python/uv.lock` and `clients/typescript/package-lock.json` pin the
  transitive sets. Every command runs `uv ... --locked` or `npm ci`.
- `clients/typescript/.npmrc` sets `ignore-scripts=true`.
- The osv-scanner step of `security.yml` scans both lockfiles, and
  `clients.yml` runs `npm audit --audit-level=high`.
- `actions/setup-node` is pinned to a commit SHA like every other action here.
- The pipeline and the web app gain no dependency. The clients are separate
  projects, and a test fails if `pipeline/pyproject.toml` names a generator.
- Renovate raises pull requests for these dependencies like any other. A
  generator bump fails the drift check until `make clients` is run, which is the
  point of it.

## What the tests prove

`clients/fixtures/manifest.json` names a recorded response for every described
path. Most are the golden site the renderer produces for three agencies
(`pipeline/tests/fixtures/golden_site`). The rest are real files copied out of
`data/artifacts/`: six per-agency artifacts across schema versions 1.4, 1.14 and
1.17, a rollup, the rollup index, the location rollups, the coverage counts, a
trimmed catalog, one dated change list, a badge and a rollup CSV. One path,
`/api/v1/ridership-impact.json`, has no recording because the file is written
only when the daily NTD fetch succeeds; its documented 404 is tested instead.

No test touches a network. Both clients are pointed at an in-process transport
that serves those files.

- **Every documented response parses**, and the parsed Python model writes back
  the exact JSON it was read from. The TypeScript client returns exactly what
  was served, and the compiler checks the types.
- **An unmeasured value is never a number.** A `not_yet_measured` category has no
  `score`, which is `UNSET` in Python and `undefined` in TypeScript. An explicit
  null, as in the catalog's `realtime` for an agency with no realtime feed, is
  `None` and `null`. A measured zero, as in Anchorage's `realtime: 0.0`, stays a
  zero. A negative control turns the absent score into `0.0` and shows the
  round-trip comparison notices.
- **A `schema_version` major bump fails the guard**, a minor bump does not, and
  the guard covers both the synchronous and the asynchronous Python client.

## Limits, stated plainly

- **Nine operations are typed field by field.** They are the ones whose response
  names a published schema: the per-agency artifact (two paths), the catalog, the
  directory, the coverage counts, the global-coverage gate, the location
  rollups, one rollup and the rollup index. The other JSON operations are
  described as an object with no listed fields, so their models hold the
  document and `docs/api.md` stays the field contract. Typing them means
  publishing a schema for each first, which is a change to the API's contract and
  is not part of this work.
- **CSV and YAML come back as text. Parquet, SVG and Atom are not modeled**, and
  the bytes are still returned.
- **The artifact's schema is closed at the top level**, so a field added in a
  later minor version is ignored by the Python model, and present at runtime but
  untyped in TypeScript, until the client is regenerated.
- **Conditional schema rules are not in the types.** For example, a `measured`
  category must carry a `score`, but `score` is optional in the generated type.
  The published schema and the pipeline's validation enforce the rule; the client
  reads what the file says.
- **The generated Python is large**: about two hundred files, roughly twenty
  thousand lines, and most of it is one file per model. A reviewer does not need to
  read it. `make clients-check` regenerates it and reports any difference, and
  reading `clients/openapi.bundled.json` and `pipeline/scripts/bundle_openapi.py`
  covers what the generators were given.

## Publishing: owner steps

Nothing below has been done, and no workflow in this repository publishes.
These are steps for the repository owner. Where a step depends on a registry's
settings page, that page could not be read from here, and the step is written
from its documentation as last read; confirm it on the page.

### Decisions first

1. **Names.** `gtfs-scorecard-client` on PyPI and `@gtfs-scorecard/client` on npm
   both returned 404 (unclaimed) when checked on 2026-09-19. The npm scope
   `@gtfs-scorecard` needs an npm organization of that name; whether the
   organization name is free could not be checked without an account. If you pick
   different names, change `name` in `clients/python/pyproject.toml` and
   `clients/typescript/package.json`, and the READMEs.
2. **Tag scheme.** `release-sign.yml` runs on tags matching `v[0-9]+.[0-9]+.[0-9]+`.
   The clients have their own version series (currently `0.1.0`), so their tags
   should not match that pattern. A suggestion: `gtfs-scorecard-client-v0.1.0` and
   `gtfs-scorecard-client-npm-v0.1.0`. The version gate,
   `pipeline/scripts/check_versions.py`, covers only the pipeline, `CITATION.cff`
   and `server.json`, so the publish workflow needs its own check that the tag
   equals the package version.
3. **Version policy.** Suggested: `0.x` until a first outside user, then align the
   client's major version with the `schema_version` major it supports.

### PyPI

PyPI trusted publishing lets a project be created by its first publish, with no
API token stored anywhere.

1. Sign in at <https://pypi.org> with the account that should own the project.
   Two-factor authentication is required.
2. Open <https://pypi.org/manage/account/publishing/> and, under "Add a new
   pending publisher", choose GitHub and enter:
   - PyPI project name: `gtfs-scorecard-client`
   - Owner: `ChelseaKR`
   - Repository name: `gtfs-scorecard`
   - Workflow name: the file name of the publish workflow you will add in step 4,
     for example `publish-python-client.yml`
   - Environment name: `pypi`
3. In the repository's settings, create an environment named `pypi`. Add yourself
   as a required reviewer. Restrict its deployment tags to the tag scheme you
   chose.
4. Add the publish workflow in a separate pull request. It should follow the
   [release standard](standards/RELEASE-AND-VERSIONING-STANDARD.md): authorize the
   tag with the shared `release-authorize` workflow at a full commit SHA, check
   that the tag equals the version in `clients/python/pyproject.toml`, run
   `make clients-check clients-test` at the tagged commit, build with
   `uv build --project clients/python`, and publish from a checkout-free job with
   `id-token: write`, `environment: pypi` and `pypa/gh-action-pypi-publish`
   pinned to a commit SHA. No PyPI token should exist as a secret.
5. Create and push the signed tag, for example:
   `git tag -s gtfs-scorecard-client-v0.1.0 -m "gtfs-scorecard-client 0.1.0"` then
   `git push origin gtfs-scorecard-client-v0.1.0`. Sign with the key listed in
   `.github/release-signers`.
6. Approve the `pypi` environment deployment when the workflow asks.
7. Check it: `uvx --from gtfs-scorecard-client==0.1.0 python -c "import gtfs_scorecard_client"`.
   The pending publisher converts to a normal trusted publisher after the first
   upload.

### npm

As far as its documentation says, npm trusted publishing is configured on a
package that already exists, so the first version of the package is published by
hand and later versions from CI.

1. Sign in at <https://www.npmjs.com> and create the organization `gtfs-scorecard`
   (Add Organization; the free plan allows public packages). Turn on two-factor
   authentication for writes.
2. From a clean checkout of `main`, run the same checks the workflow runs, then
   publish the first version by hand:
   ```sh
   make clients-check clients-test clients-build
   cd clients/typescript
   npm ci --ignore-scripts
   npm run build
   npm publish --access public
   ```
   A publish from a laptop cannot carry a provenance statement; later ones from CI
   can.
3. On the package's settings page on npmjs.com, add a trusted publisher: GitHub
   Actions, owner `ChelseaKR`, repository `gtfs-scorecard`, the file name of the
   publish workflow, and an environment name such as `npm`. Create that
   environment in the repository with yourself as a required reviewer.
4. Add the publish workflow in a separate pull request, on the same lines as the
   PyPI one: authorize the tag, check the version, run the checks at the tagged
   commit, then publish from a checkout-free job with `id-token: write` using
   `npm publish --provenance --access public`. Trusted publishing needs a
   recent npm (11.5.1 or newer, from the documentation) and a matching Node
   release, so pin both.

### After publishing

- **`server.json` is not unblocked by these packages.** `packages[]` in
  `server.json` describes how to run the MCP server, which is the
  `scorecard-mcp` command inside `scorecard-pipeline`. A typed client does not
  contain it. Filling that field needs `scorecard-pipeline` itself published to
  PyPI, which is a larger decision with its own surface (see
  [mcp.md](mcp.md#registry-listing)) and is not made here. Issue #370 lists this
  as an acceptance item, and it cannot be met by publishing the clients.
- Update each README's "Status: not published" paragraph and add the install
  command.
- Add the packages to the release checklist ([release-checklist.md](release-checklist.md)).
