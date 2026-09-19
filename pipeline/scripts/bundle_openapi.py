#!/usr/bin/env python3
"""Flatten the OpenAPI description into the one document the client generators read (#370).

``web/api/v1/openapi.yaml`` is the served description. It points at the
published JSON Schemas with root-relative references such as
``$ref: /schemas/artifact.schema.json``, which is right for a host that serves
both and useless to a code generator running on a laptop: it resolves the
reference against the file system, finds nothing, and either fails or falls
back to an untyped object.

This script resolves them. Every ``/schemas/<name>.schema.json`` reference is
replaced by a reference to a component of the same name, and each schema's own
``$defs`` are hoisted beside it. Three small changes make the schemas readable
by a generator without changing what they accept or refuse:

* ``$schema`` and ``$id`` are dropped, because they would re-base every
  reference that follows;
* ``title`` is renamed ``x-title``, because a generator names a type from its
  title and the published titles are prose;
* an array schema with no ``items`` gets ``"items": {}``, which is the same
  constraint said out loud (see ``_admit_untyped_items``).

Nothing else in either input is changed, added or removed. A keyword the
generators cannot express (``if``, ``then``, ``not``, ``dependentRequired``)
stays in the document for a reader and is ignored by the generator, so a
generated type is never stricter than the schema and the schema stays the
validating contract.

The output is deterministic: same inputs, same bytes. ``clients/`` commits it,
so a reviewer sees exactly what the generators were given, and
``tests/test_clients_drift.py`` fails when it is stale.

    python3 pipeline/scripts/bundle_openapi.py           # write it
    python3 pipeline/scripts/bundle_openapi.py --check   # exit 1 when stale
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPO_ROOT / "web" / "api" / "v1" / "openapi.yaml"
SCHEMAS_DIR = REPO_ROOT / "web" / "schemas"
BUNDLE_PATH = REPO_ROOT / "clients" / "openapi.bundled.json"

SCHEMA_REF = re.compile(r"^/schemas/(?P<file>[a-z0-9.-]+\.schema\.json)$")
DEFS_REF = re.compile(r"^#/\$defs/(?P<name>[A-Za-z0-9_-]+)$")

# Declarations that name the schema's own identity. Kept, they would make a
# generator resolve every later `$ref` against the published URL.
IDENTITY_KEYWORDS = frozenset({"$schema", "$id"})

# `title` becomes `x-title`. A generator names a type from its `title` when one
# exists, so "GTFS Scorecard national directory" would come out as
# `GtfsScorecardNationalDirectory` where the component is called `Directory`.
# The words are kept, under a name no validator reads.
RENAMED_KEYWORDS = {"title": "x-title"}

# JSON Schema keywords whose value is a map of name -> subschema, a single
# subschema, or a list of subschemas. Anything else (`enum`, `const`,
# `required`, `dependentRequired`, `default`, `examples`) is data, and is
# copied untouched: a property called "if" must not be read as a keyword.
SCHEMA_MAP_KEYWORDS = frozenset({"properties", "patternProperties", "$defs", "dependentSchemas"})
SCHEMA_KEYWORDS = frozenset(
    {
        "items",
        "additionalProperties",
        "unevaluatedProperties",
        "not",
        "if",
        "then",
        "else",
        "contains",
        "propertyNames",
    }
)
SCHEMA_LIST_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})


class BundleError(ValueError):
    """The description names a schema this script cannot place."""


def component_name(schema_file: str) -> str:
    """``rollup-index.schema.json`` -> ``RollupIndex``."""
    stem = schema_file.removesuffix(".schema.json")
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[-.]", stem) if part)


def _pascal(name: str) -> str:
    return name[:1].upper() + name[1:]


def _rewrite(node: Any, prefix: str) -> Any:
    """Copy one schema, rewriting its `#/$defs/x` references and dropping its identity."""
    if not isinstance(node, dict):
        return copy.deepcopy(node)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in IDENTITY_KEYWORDS:
            continue
        if key in RENAMED_KEYWORDS and isinstance(value, str):
            out[RENAMED_KEYWORDS[key]] = value
        elif key == "$ref" and isinstance(value, str):
            match = DEFS_REF.match(value)
            if match is None:
                raise BundleError(f"{prefix}: unsupported $ref {value!r}; only #/$defs/<name>")
            out[key] = f"#/components/schemas/{prefix}{_pascal(match['name'])}"
        elif key in SCHEMA_MAP_KEYWORDS and isinstance(value, dict):
            out[key] = {name: _rewrite(sub, prefix) for name, sub in value.items()}
        elif key in SCHEMA_KEYWORDS:
            out[key] = _rewrite(value, prefix)
        elif key in SCHEMA_LIST_KEYWORDS and isinstance(value, list):
            out[key] = [_rewrite(sub, prefix) for sub in value]
        else:
            out[key] = copy.deepcopy(value)
    return _admit_untyped_items(out)


def _admit_untyped_items(schema: dict[str, Any]) -> dict[str, Any]:
    """Write down the `items` an array schema leaves implicit.

    JSON Schema lets ``{"type": "array"}`` stand alone: any element is valid.
    The Python generator refuses it ("type array must have items or
    prefixItems defined") and drops the whole enclosing model, so every
    property of the artifact would disappear with it. ``"items": {}`` is the
    same constraint stated out loud, and validates exactly what the original
    validated.
    """
    kind = schema.get("type")
    is_array = kind == "array" or (isinstance(kind, list) and "array" in kind)
    if is_array and "items" not in schema and "prefixItems" not in schema:
        return {**schema, "items": {}}
    return schema


def _hoist(schema_file: str, schemas_dir: Path) -> dict[str, dict[str, Any]]:
    """One published schema as components: the root under its name, each `$defs` beside it."""
    path = schemas_dir / schema_file
    if not path.is_file():
        raise BundleError(f"{schema_file}: no such schema under {schemas_dir}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    prefix = component_name(schema_file)
    defs = schema.pop("$defs", {})
    hoisted = {prefix: _rewrite(schema, prefix)}
    for name, sub in defs.items():
        hoisted[f"{prefix}{_pascal(name)}"] = _rewrite(sub, prefix)
    return hoisted


def _replace_refs(node: Any, used: dict[str, str]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            match = SCHEMA_REF.match(ref)
            if match is not None:
                used[match["file"]] = component_name(match["file"])
                return {
                    **{k: _replace_refs(v, used) for k, v in node.items() if k != "$ref"},
                    "$ref": f"#/components/schemas/{component_name(match['file'])}",
                }
            if ref.startswith("/"):
                raise BundleError(f"unsupported root-relative $ref {ref!r}")
        return {k: _replace_refs(v, used) for k, v in node.items()}
    if isinstance(node, list):
        return [_replace_refs(v, used) for v in node]
    return node


def bundle(openapi_path: Path = OPENAPI_PATH, schemas_dir: Path = SCHEMAS_DIR) -> dict[str, Any]:
    """The description with every published-schema reference resolved into components."""
    spec = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    used: dict[str, str] = {}
    out = _replace_refs(spec, used)

    components = out.setdefault("components", {})
    schemas: dict[str, Any] = components.setdefault("schemas", {})
    for schema_file in sorted(used):
        for name, sub in _hoist(schema_file, schemas_dir).items():
            if name in schemas:
                raise BundleError(f"component {name!r} is already defined")
            schemas[name] = sub
    components["schemas"] = dict(sorted(schemas.items()))

    info = out.setdefault("info", {})
    info["x-bundle"] = {
        "note": (
            "Generated by pipeline/scripts/bundle_openapi.py from web/api/v1/openapi.yaml "
            "and web/schemas/. Do not edit; edit those and run `make clients`."
        ),
        "schemas": sorted(used),
    }
    return out  # type: ignore[no-any-return]


def render(openapi_path: Path = OPENAPI_PATH, schemas_dir: Path = SCHEMAS_DIR) -> str:
    """The bundle as committed: two-space JSON, keys in source order, trailing newline."""
    return json.dumps(bundle(openapi_path, schemas_dir), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 when the committed bundle is stale"
    )
    parser.add_argument("--out", type=Path, default=BUNDLE_PATH)
    args = parser.parse_args(argv)

    text = render()
    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.is_file() else None
        if current != text:
            print(
                f"{args.out} is stale. Run `make clients` and commit the result.", file=sys.stderr
            )
            return 1
        print(f"OK  {args.out} matches web/api/v1/openapi.yaml and web/schemas/")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
