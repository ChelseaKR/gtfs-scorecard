"""The OpenAPI description of the static read API holds to its prose contract (#370).

``web/api/v1/openapi.yaml`` is hand-maintained: nothing generates it, so nothing
keeps it true except these checks. They hold it five ways.

1. It is a valid OpenAPI 3.1 document under the official meta-schema, vendored
   in ``fixtures/openapi/`` and pinned by digest. That variant checks the
   document's structure and deliberately not the JSON Schemas inside it; the
   published schemas are checked as Draft 2020-12 by ``test_schemas.py``.
2. It describes exactly the paths ``docs/api.md`` documents, in both
   directions. A path documented and not described is a hole in the
   description; a path described and not documented is an endpoint nobody
   promised. Each direction has a floor, so a parser that stopped matching
   cannot report agreement over an empty set.
3. Every described path resolves to a file the golden site carries, or is named
   in ``NOT_IN_FIXTURE`` with the reason it cannot be. That list must equal the
   set that fails to resolve, so it cannot rot in either direction.
4. Every operation that names a JSON Schema is checked against the golden file
   for its path, so a ``$ref`` pointing at the wrong schema fails.
5. Its structure is what a static read API needs: GET only, unique operation
   ids, every path-template parameter declared, every reference resolvable, and
   licence, attribution and versions bound to the pipeline's own constants.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from scorecard_pipeline import DATA_ATTRIBUTION, DATA_LICENSE, SCHEMA_VERSION
from scorecard_pipeline.instance import BASE_URL
from scorecard_pipeline.publicapi import API_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPO_ROOT / "web" / "api" / "v1" / "openapi.yaml"
API_DOC = REPO_ROOT / "docs" / "api.md"
PAGES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pages.yml"
GOLDEN = Path(__file__).parent / "fixtures" / "golden_site"
META_SCHEMA_PATH = Path(__file__).parent / "fixtures" / "openapi" / "oas-3.1-schema-2022-10-07.json"
META_SCHEMA_SHA256 = "da01ba28852cac0de53893797cb8d1942bc3b05084f526dcc216717dec314ed0"

ARTIFACT_BASE = "/data/artifacts/"

# docs/api.md documents its paths in two tables whose bare paths have different
# bases. The first table's sit under the artifact base (its intro says so); the
# api/v1 table's sit at the site root. A leading slash is absolute in either.
TABLE_BASES = {
    "## Where the data lives": ARTIFACT_BASE,
    "## Versioned cross-agency API (`api/v1/`)": "/",
}
# Floors, set well under today's counts so that adding a path never means
# editing this file, and high enough that a parser matching nothing fails.
MIN_TABLE_PATHS = 15
MIN_DESCRIBED_PATHS = 40
MIN_SCHEMA_BACKED_OPERATIONS = 8

PLACEHOLDERS = {"<agency>": "{agency_id}", "<date>": "{date}", "<id>": "{rollup_id}"}
_PATH_SPAN = re.compile(r"`(/?[A-Za-z0-9_./<>-]+\.(?:json|csv|svg|xml|parquet|yaml))`")
_ANY_SPAN = re.compile(r"`([^`\n]+)`")

# One concrete golden-site sample per path-template parameter.
SAMPLE = {"{agency_id}": "unitrans", "{date}": "2026-07-02", "{rollup_id}": "california"}

# Described paths the golden site cannot carry, each with its reason. The
# resolution test requires this to equal the set that fails to resolve.
NOT_IN_FIXTURE = {
    "/data/artifacts/changes/latest.json": (
        "render_site writes it under data/artifacts; the goldens capture the web tree only"
    ),
    "/data/artifacts/changes/{date}.json": "same writer as changes/latest.json",
    "/data/artifacts/{agency_id}/badge.svg": (
        "publish() writes it at score time; the fixture holds artifacts, not a publish run"
    ),
    "/data/artifacts/{agency_id}/badge.json": "publish() writes it beside badge.svg",
    "/data/artifacts/rollups/{rollup_id}.csv": (
        "`scorecard rollups` writes it; the fixture carries the rollup JSON only"
    ),
    "/api/v1/ridership-impact.json": "conditional: written only when the NTD fetch succeeded",
}


def _openapi() -> dict[str, Any]:
    loaded = yaml.safe_load(OPENAPI_PATH.read_text())
    assert isinstance(loaded, dict), "openapi.yaml did not parse to a mapping"
    return loaded


def _to_url_path(span: str, base: str) -> str:
    for placeholder, template in PLACEHOLDERS.items():
        span = span.replace(placeholder, template)
    return span if span.startswith("/") else base + span


def documented_paths(text: str) -> dict[str, set[str]]:
    """First-column paths of each endpoint table in docs/api.md, as URL templates."""
    found: dict[str, set[str]] = {heading: set() for heading in TABLE_BASES}
    heading: str | None = None
    for line in text.splitlines():
        if line.startswith("#"):
            heading = line.strip() if line.strip() in TABLE_BASES else None
            continue
        if heading is None or not line.startswith("| `"):
            continue
        first_cell = line.split("|")[1]
        for span in _PATH_SPAN.findall(first_cell):
            found[heading].add(_to_url_path(span, TABLE_BASES[heading]))
    return found


def _doc_spellings(url_path: str) -> set[str]:
    """Every way docs/api.md may spell one described path in a code span."""
    spelled = url_path
    for placeholder, template in PLACEHOLDERS.items():
        spelled = spelled.replace(template, placeholder)
    spellings = {spelled, spelled.removeprefix("/")}
    if spelled.startswith(ARTIFACT_BASE):
        spellings.add(spelled.removeprefix(ARTIFACT_BASE))
    return spellings


def _golden_file(url_path: str) -> Path:
    concrete = url_path
    for template, value in SAMPLE.items():
        concrete = concrete.replace(template, value)
    if concrete.startswith(ARTIFACT_BASE):
        return GOLDEN / "data" / "artifacts" / concrete.removeprefix(ARTIFACT_BASE)
    if concrete.startswith("/schemas/") or concrete == "/api/v1/openapi.yaml":
        # Static source files: render_site never writes these, and pages.yml
        # copies web/ as it stands, so the checkout's web/ is what is served.
        return REPO_ROOT / "web" / concrete.removeprefix("/")
    return GOLDEN / "web" / concrete.removeprefix("/")


def _resolve(doc: dict[str, Any], node: Any) -> Any:
    while isinstance(node, dict) and str(node.get("$ref", "")).startswith("#/"):
        target: Any = doc
        for part in str(node["$ref"])[2:].split("/"):
            target = target[part]
        node = target
    return node


def _refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _refs(value)


def _schema_backed(doc: dict[str, Any]) -> dict[str, str]:
    """``{path: /schemas/ reference}`` for every operation whose 200 names a schema."""
    backed: dict[str, str] = {}
    for path, item in doc["paths"].items():
        response = _resolve(doc, item["get"]["responses"]["200"])
        for media in response.get("content", {}).values():
            ref = str((media.get("schema") or {}).get("$ref", ""))
            if ref.startswith("/schemas/"):
                backed[path] = ref
    return backed


def _meta_errors(document: dict[str, Any]) -> list[str]:
    meta = json.loads(META_SCHEMA_PATH.read_text())
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in Draft202012Validator(meta).iter_errors(document)
    ]


def test_the_vendored_meta_schema_is_the_published_one() -> None:
    digest = hashlib.sha256(META_SCHEMA_PATH.read_bytes()).hexdigest()
    assert digest == META_SCHEMA_SHA256, (
        f"{META_SCHEMA_PATH.name} has sha256 {digest}, not the published {META_SCHEMA_SHA256}; "
        "a vendored meta-schema that drifted checks something other than OpenAPI 3.1"
    )


def test_the_description_is_a_valid_openapi_3_1_document() -> None:
    doc = _openapi()
    assert str(doc.get("openapi", "")).startswith("3.1."), doc.get("openapi")
    errors = _meta_errors(doc)
    assert not errors, "openapi.yaml fails the OpenAPI 3.1 meta-schema:\n" + "\n".join(errors[:20])


def test_the_meta_schema_check_is_not_vacuous() -> None:
    """The validator accepts a minimal document and refuses two broken ones.

    Synthetic on purpose, so this control survives the real document being
    correct: a missing required ``info`` and a response without its required
    ``description`` must both be refused.
    """
    minimal: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {"/x.json": {"get": {"responses": {"200": {"description": "ok"}}}}},
    }
    assert _meta_errors(minimal) == []
    without_info = {key: value for key, value in minimal.items() if key != "info"}
    assert _meta_errors(without_info)
    without_description = deepcopy(minimal)
    without_description["paths"]["/x.json"]["get"]["responses"]["200"] = {}
    assert _meta_errors(without_description)


def test_every_documented_path_is_described() -> None:
    tables = documented_paths(API_DOC.read_text())
    for heading, paths in tables.items():
        assert len(paths) >= MIN_TABLE_PATHS, (
            f"docs/api.md table {heading!r} yielded {len(paths)} paths, under the floor of "
            f"{MIN_TABLE_PATHS}: the table parser has stopped matching, so agreement over "
            "it would mean nothing"
        )
    documented = {path for paths in tables.values() for path in paths}
    missing = sorted(documented - set(_openapi()["paths"]))
    assert not missing, (
        "docs/api.md documents paths that web/api/v1/openapi.yaml does not describe:\n"
        + "\n".join(missing)
    )


def test_every_described_path_is_documented() -> None:
    described = set(_openapi()["paths"])
    assert len(described) >= MIN_DESCRIBED_PATHS, (
        f"openapi.yaml describes {len(described)} paths, under the floor of {MIN_DESCRIBED_PATHS}"
    )
    spans = set(_ANY_SPAN.findall(API_DOC.read_text()))
    undocumented = sorted(path for path in described if not (_doc_spellings(path) & spans))
    assert not undocumented, (
        "web/api/v1/openapi.yaml describes paths docs/api.md never names:\n"
        + "\n".join(undocumented)
    )


def test_every_described_path_resolves_to_a_file_the_golden_site_carries() -> None:
    described = set(_openapi()["paths"])
    unresolved = {path for path in described if not _golden_file(path).is_file()}
    expected = set(NOT_IN_FIXTURE)
    assert unresolved == expected, (
        "described but missing from the golden site:\n"
        + "\n".join(sorted(unresolved - expected))
        + "\nnamed in NOT_IN_FIXTURE but present in the golden site or no longer described:\n"
        + "\n".join(sorted(expected - unresolved))
    )


def test_each_schema_backed_path_validates_its_golden_file() -> None:
    backed = _schema_backed(_openapi())
    assert len(backed) >= MIN_SCHEMA_BACKED_OPERATIONS, (
        f"only {len(backed)} operations name a /schemas/ file; the floor is "
        f"{MIN_SCHEMA_BACKED_OPERATIONS}"
    )
    failures: list[str] = []
    for path, ref in sorted(backed.items()):
        schema = json.loads((REPO_ROOT / "web" / ref.removeprefix("/")).read_text())
        golden = _golden_file(path)
        if not golden.is_file():
            failures.append(f"{path} -> {ref}: no golden file at {golden}")
            continue
        errors = list(Draft202012Validator(schema).iter_errors(json.loads(golden.read_text())))
        if errors:
            failures.append(f"{path} -> {ref}: {golden.name}: {errors[0].message[:200]}")
    assert not failures, "golden files fail the schema the description names:\n" + "\n".join(
        failures
    )


def test_every_schema_reference_names_a_published_schema_by_its_id() -> None:
    external = sorted({ref for ref in _refs(_openapi()) if not ref.startswith("#/")})
    assert external, "the description references no JSON Schema at all"
    problems: list[str] = []
    for ref in external:
        schema_file = REPO_ROOT / "web" / ref.removeprefix("/")
        if not ref.startswith("/schemas/") or not schema_file.is_file():
            problems.append(f"{ref}: not a file under web/schemas/")
            continue
        schema_id = json.loads(schema_file.read_text()).get("$id")
        if schema_id != BASE_URL + ref:
            problems.append(f"{ref}: the schema's $id is {schema_id!r}, not {BASE_URL + ref!r}")
    assert not problems, "\n".join(problems)


def test_every_internal_reference_resolves() -> None:
    doc = _openapi()
    internal = sorted({ref for ref in _refs(doc) if ref.startswith("#/")})
    assert internal, "the description has no internal references to check"
    broken: list[str] = []
    for ref in internal:
        try:
            _resolve(doc, {"$ref": ref})
        except (KeyError, TypeError):
            broken.append(ref)
    assert not broken, "internal references that resolve to nothing:\n" + "\n".join(broken)


def test_every_operation_is_a_get_with_a_unique_id_and_declared_parameters() -> None:
    doc = _openapi()
    owners: dict[str, str] = {}
    problems: list[str] = []
    for path, item in doc["paths"].items():
        methods = set(item) - {"summary", "description", "parameters", "servers"}
        if methods != {"get"}:
            problems.append(f"{path}: operations {sorted(methods)}; a static read API is GET only")
            continue
        operation = item["get"]
        operation_id = operation.get("operationId")
        if not operation_id:
            problems.append(f"{path}: no operationId")
        elif operation_id in owners:
            problems.append(f"{path}: operationId {operation_id} is also {owners[operation_id]}")
        else:
            owners[operation_id] = path
        templated = set(re.findall(r"\{([^}]+)\}", path))
        declared = {
            parameter["name"]
            for parameter in (_resolve(doc, p) for p in operation.get("parameters", []))
            if parameter.get("in") == "path"
        }
        if templated != declared:
            problems.append(f"{path}: template {sorted(templated)}, declared {sorted(declared)}")
        if "200" not in operation["responses"]:
            problems.append(f"{path}: no 200 response")
    assert not problems, "\n".join(problems)


def test_licence_attribution_and_versions_match_the_pipeline() -> None:
    info = _openapi()["info"]
    assert info["license"]["identifier"] == DATA_LICENSE
    assert info["x-attribution"] == DATA_ATTRIBUTION
    assert info["version"] == API_VERSION
    assert info["x-artifact-schema-version-major"] == SCHEMA_VERSION.split(".")[0]


def test_the_deploy_copies_web_as_it_stands() -> None:
    """The description is served only because pages.yml copies web/ wholesale.

    Compared as a whole command line with comment lines dropped, so a comment
    that mentions the command cannot satisfy it.
    """
    commands = [
        line.strip()
        for line in PAGES_WORKFLOW.read_text().splitlines()
        if not line.strip().startswith("#")
    ]
    assert "cp -r web/. _site/" in commands
