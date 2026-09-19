# gtfs-scorecard-client

A typed Python client for the [GTFS Scorecard](https://gtfsscorecard.org) read
API. The endpoint functions and models are generated from the API's OpenAPI
description ([`web/api/v1/openapi.yaml`](../../web/api/v1/openapi.yaml)); a small
hand-written layer adds a `schema_version` guard.

**Status: not published.** There is no `gtfs-scorecard-client` on PyPI yet.
Publishing needs a PyPI trusted publisher registered by the repository owner;
the exact steps are in [docs/typed-clients.md](../../docs/typed-clients.md).
Until then, install from a checkout:

```sh
pip install ./clients/python
# or, straight from GitHub:
pip install "git+https://github.com/ChelseaKR/gtfs-scorecard#subdirectory=clients/python"
```

Requires Python 3.11 or newer. Runtime dependencies are `httpx` and `attrs`.

## Use

The scorecard publishes static files, so there is no key and nothing to sign
in to.

```python
from gtfs_scorecard_client import make_client
from gtfs_scorecard_client.generated.api.artifacts import get_agency_latest

client = make_client()  # https://gtfsscorecard.org; pass base_url= for a fork
artifact = get_agency_latest.sync(agency_id="unitrans", client=client)

print(artifact.overall.grade, artifact.overall.score)
for name in ("correctness", "freshness", "completeness", "realtime"):
    category = getattr(artifact.categories, name)
    print(name, category.status.value, category.score)
# ...
# realtime not_yet_measured <gtfs_scorecard_client.generated.types.Unset object at 0x...>
```

Every operation is a module under `gtfs_scorecard_client.generated.api.<tag>`
with `sync`, `sync_detailed`, `asyncio` and `asyncio_detailed`. `sync_detailed`
returns the status code and headers as well as the parsed body.

## A value that was not measured is never zero

The scorecard says so when it could not measure something, and the models keep
that distinction:

| On the wire | In the model | Example |
|---|---|---|
| The field is absent | `UNSET` | `categories.realtime.score` when the category is `not_yet_measured` |
| The field is JSON `null` | `None` | `catalog.agencies[].realtime`, `national_percentile` |
| The field is a number | the number | `0` only when the scorecard measured zero |

Test for absence with `isinstance(value, Unset)` or `value is UNSET`, and for a
null with `value is None`. Do not use truthiness: `UNSET` is falsy, and so is a
real `0`. `to_dict()` writes an `UNSET` field as absent and a `None` as `null`,
so a parsed document round-trips to the bytes it came from.

## The `schema_version` guard

`docs/api.md` asks consumers to treat a change in the major version as a
breaking change. `make_client()` does that for you: any JSON response that
carries a `schema_version` whose major version is not the one this client was
generated against raises `UnsupportedSchemaVersion` before a model is built.

```python
from gtfs_scorecard_client import UnsupportedSchemaVersion, check_schema_version

check_schema_version({"schema_version": "1.19"})   # fine: same major version
check_schema_version({"schema_version": "2.0"})    # raises UnsupportedSchemaVersion
```

`make_client(guard=False)` turns it off. The guard checks every document that
carries a `schema_version`, including the ones versioned separately from the
artifact (`dataset.json`), so a major change in any of them asks for a new
client.

## Fields added after this client was generated

A minor version adds fields, and the guard lets it through. What happens to a
field the client has never heard of depends on the model: where the schema
allows extra properties, the model keeps them in `additional_properties`; where
the schema is closed, which includes the per-agency artifact at its top level,
the field is ignored and does not appear in `to_dict()`. Reading it takes a
newer client.

## What is typed, and what is not

Nine operations name a published JSON Schema, and their responses are typed
models: the per-agency artifact (`latest.json` and `<date>.json`), the catalog,
the directory, the coverage counts, the global-coverage gate, the location
rollups, one rollup, and the rollup index. The other operations describe a JSON
object without listing its fields, so their `parsed` value is a model whose
`additional_properties` holds the document, and `docs/api.md` is the field
contract. CSV and YAML responses come back as text. Parquet, SVG and Atom
responses are not modeled, so `parsed` is `None` and the bytes are in
`sync_detailed(...).content`.

## Regenerating

Nothing under `src/gtfs_scorecard_client/generated/` is edited by hand. From the
repository root:

```sh
make clients        # regenerate after the description or a schema changes
make clients-check  # regenerate to a temp directory and fail on any difference
make clients-test   # run the contract tests against recorded responses
```

The data is offered under CC BY 4.0. Attribute it as `GTFS Scorecard
(gtfsscorecard.org)`. A grade is a derived data-quality signal, not a
compliance determination.
