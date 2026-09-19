# Typed clients for the read API

Two clients generated from [`web/api/v1/openapi.yaml`](../web/api/v1/openapi.yaml)
and the published schemas in [`web/schemas/`](../web/schemas):

- [`python/`](python): `gtfs-scorecard-client`, built on `openapi-python-client`
- [`typescript/`](typescript): `@gtfs-scorecard/client`, built on `openapi-typescript`
  and `openapi-fetch`

Neither is published. [docs/typed-clients.md](../docs/typed-clients.md) explains
how they are generated and kept current, what the tests prove, and the exact
steps the repository owner takes to publish them.

| | |
|---|---|
| `openapi.bundled.json` | The description with its schema references resolved. What the generators read. Generated. |
| `GENERATED.json` | The bundle's digest and the generator versions. Generated. |
| `fixtures/` | Recorded responses the contract tests serve. `manifest.json` names the file behind every documented path. |
| `python/`, `typescript/` | The packages. Their `generated/` directories are generated; the rest is written by hand. |

```sh
make clients          # regenerate after the description or a schema changes
make clients-check    # regenerate to a temp directory, fail on any difference
make clients-control  # prove clients-check fails when it should
make clients-test     # contract tests for both clients
make clients-build    # build both packages, publishing neither
```

`fixtures/artifacts/` holds real per-agency artifacts copied unchanged from
`data/artifacts/`, and `fixtures/documents/` holds other recorded documents.
`catalog-trimmed.json` is the published catalog cut to five rows, chosen to
include a measured realtime score of zero and several nulls; its other fields
are unchanged. The data is offered under CC BY 4.0: attribute it as
`GTFS Scorecard (gtfsscorecard.org)`.
