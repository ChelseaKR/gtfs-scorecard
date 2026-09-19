# @gtfs-scorecard/client

A typed TypeScript client for the [GTFS Scorecard](https://gtfsscorecard.org)
read API. The types are generated from the API's OpenAPI description
([`web/api/v1/openapi.yaml`](../../web/api/v1/openapi.yaml)) with
[openapi-typescript](https://openapi-ts.dev), the requests go through
[openapi-fetch](https://openapi-ts.dev/openapi-fetch/), and a small hand-written
layer adds a `schema_version` guard.

**Status: not published.** There is no `@gtfs-scorecard/client` on npm yet.
Publishing needs an npm organization and a trusted publisher set up by the
repository owner; the exact steps are in
[docs/typed-clients.md](../../docs/typed-clients.md). Until then, build it from a
checkout:

```sh
cd clients/typescript
npm ci --ignore-scripts
npm run build          # writes dist/
npm pack               # or: npm install ../path/to/clients/typescript
```

The one runtime dependency is `openapi-fetch`, which has none of its own beyond
type helpers. Node 18 or newer, or any runtime with `fetch`.

## Use

The scorecard publishes static files, so there is no key and nothing to sign in
to.

```ts
import { createScorecardClient } from "@gtfs-scorecard/client";

const client = createScorecardClient(); // https://gtfsscorecard.org; pass { baseUrl } for a fork

const { data, error } = await client.GET("/data/artifacts/{agency_id}/latest.json", {
  params: { path: { agency_id: "unitrans" } },
});
if (data) {
  console.log(data.overall.grade, data.overall.score);
  const realtime = data.categories.realtime;
  console.log(realtime.status, realtime.score); // "not_yet_measured", undefined
}
```

Every path in the description is a key of `paths`, so the path string, its
parameters and the shape of `data` are all checked by the compiler.

CSV, Parquet, SVG, Atom and YAML responses are not JSON. Ask for them with
`parseAs`:

```ts
const { data: csv } = await client.GET("/catalog.csv", { parseAs: "text" });
const { data: parquet } = await client.GET("/api/v1/agencies.parquet", { parseAs: "arrayBuffer" });
```

## A value that was not measured is never a number

The scorecard says so when it could not measure something, and the types keep
that distinction:

| On the wire | In the type | Example |
|---|---|---|
| The field is absent | `T \| undefined` | `categories.realtime.score` when the category is `not_yet_measured` |
| The field is JSON `null` | `T \| null` | `catalog.agencies[].realtime`, `national_percentile` |
| The field is a number | `number` | `0` only when the scorecard measured zero |

Compare with `=== undefined`, `=== null` and `=== 0` explicitly. Do not test
truthiness: `undefined`, `null` and a measured `0` are all falsy, and only one
of them means "no data".

## The `schema_version` guard

`docs/api.md` asks consumers to treat a change in the major version as a
breaking change. `createScorecardClient()` does that for you: any JSON response
that carries a `schema_version` whose major version is not the one this client
was generated against rejects with `UnsupportedSchemaVersionError` before you
read it.

```ts
import { checkSchemaVersion } from "@gtfs-scorecard/client";

checkSchemaVersion({ schema_version: "1.19" }); // fine: same major version
checkSchemaVersion({ schema_version: "2.0" }); // throws UnsupportedSchemaVersionError
```

`createScorecardClient({ guard: false })` turns it off. The guard checks every
document that carries a `schema_version`, including the ones versioned
separately from the artifact (`dataset.json`), so a major change in any of them
asks for a new client.

## What is typed, and what is not

Nine operations name a published JSON Schema and are typed field by field: the
per-agency artifact (`latest.json` and `<date>.json`), the catalog, the
directory, the coverage counts, the global-coverage gate, the location rollups,
one rollup, and the rollup index. The other JSON operations are typed as an
object without listing its fields, and `docs/api.md` is the field contract. A
field added in a later minor version is present at runtime and absent from the
types until you upgrade.

## Regenerating

`src/generated/schema.ts` is never edited by hand. From the repository root:

```sh
make clients        # regenerate after the description or a schema changes
make clients-check  # regenerate to a temp directory and fail on any difference
make clients-test   # type-check and run the contract tests against recorded responses
```

The data is offered under CC BY 4.0. Attribute it as `GTFS Scorecard
(gtfsscorecard.org)`. A grade is a derived data-quality signal, not a
compliance determination.
