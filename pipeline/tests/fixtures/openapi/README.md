# Vendored OpenAPI 3.1 meta-schema

`oas-3.1-schema-2022-10-07.json` is the official JSON Schema for OpenAPI 3.1
documents, published by the OpenAPI Initiative. It is copied here unmodified so
`tests/test_openapi_contract.py` can check `web/api/v1/openapi.yaml` without a
network fetch or a new dependency.

- Source: <https://spec.openapis.org/oas/3.1/schema/2022-10-07>
- `$id`: `https://spec.openapis.org/oas/3.1/schema/2022-10-07`
- Retrieved: 2026-09-10
- SHA-256: `da01ba28852cac0de53893797cb8d1942bc3b05084f526dcc216717dec314ed0`
  (the test pins it, so an edit to this copy fails rather than passing quietly)
- Licence: Apache License, Version 2.0, the licence of the
  [OpenAPI Specification repository](https://github.com/OAI/OpenAPI-Specification).
  This repository is under the same licence; see `LICENSE` at its root.

This is the variant "without schema validation": it checks the structure of an
OpenAPI document (paths, operations, responses, parameters, components) and
deliberately does not validate the JSON Schemas embedded in it. The schemas this
project publishes are checked separately, as Draft 2020-12, by
`tests/test_schemas.py`.
