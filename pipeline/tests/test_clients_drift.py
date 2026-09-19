"""The typed clients under ``clients/`` are current with the OpenAPI description (#370).

The clients are generated, so they can go stale in two ways: someone edits
``web/api/v1/openapi.yaml`` or a published schema and does not regenerate, or
someone edits generated code by hand. Two checks cover them, and they are split
by what they cost.

* This file runs in ``make verify``, which is merge-blocking, and needs no
  generator. It catches the common failure, a changed description or schema
  with no regeneration, by comparing the committed bundle
  (``clients/openapi.bundled.json``) with what the description and schemas
  produce, and by checking that ``clients/GENERATED.json`` names that bundle and
  the pinned generator versions. Everything downstream of the bundle is
  deterministic, so a matching stamp is a matching client.
* ``.github/workflows/clients.yml`` runs the generators and diffs the output
  byte for byte (``make clients-check``). That is the check that sees a hand edit
  inside generated code, and a generator whose output moved under an unchanged
  pin. It also runs ``make clients-control``, which proves the check fails.

The negative controls below run the same function the real test runs, on a copy
of the description or a schema that changed without regeneration, so a check
that stopped noticing would fail here rather than pass over an empty set.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENTS = REPO_ROOT / "clients"
SCRIPTS = REPO_ROOT / "pipeline" / "scripts"
SCHEMAS = REPO_ROOT / "web" / "schemas"
OPENAPI = REPO_ROOT / "web" / "api" / "v1" / "openapi.yaml"
GENERATED_PY = CLIENTS / "python" / "src" / "gtfs_scorecard_client" / "generated"
GENERATED_TS = CLIENTS / "typescript" / "src" / "generated" / "schema.ts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = _load("generate_clients")


def _spec_paths() -> set[str]:
    document = json.loads((CLIENTS / "openapi.bundled.json").read_text(encoding="utf-8"))
    return set(document["paths"])


# --- the cheap drift check, and its negative controls --------------------------


def test_the_committed_clients_are_current_with_the_description_and_schemas() -> None:
    reasons = generator.stale_reasons()
    assert not reasons, (
        "the OpenAPI description, a published schema or a generator pin changed and the "
        "clients were not regenerated. Run `make clients` and commit the result:\n  "
        + "\n  ".join(reasons)
    )


def test_a_description_that_changed_without_regeneration_is_caught(tmp_path: Path) -> None:
    changed = generator.mutated_description(tmp_path)
    assert changed.read_text() != OPENAPI.read_text(), "the control did not change the input"
    reasons = generator.stale_reasons(spec=changed)
    assert any("openapi.bundled.json is not what" in reason for reason in reasons), reasons


def test_a_schema_that_changed_without_regeneration_is_caught(tmp_path: Path) -> None:
    changed = generator.mutated_schemas(tmp_path)
    before = (SCHEMAS / "artifact.schema.json").read_text()
    assert (changed / "artifact.schema.json").read_text() != before
    reasons = generator.stale_reasons(schemas=changed)
    assert any("openapi.bundled.json is not what" in reason for reason in reasons), reasons


def test_a_bundle_edited_by_hand_is_caught_by_the_stamp(tmp_path: Path) -> None:
    for name in ("openapi.bundled.json", "GENERATED.json"):
        (tmp_path / name).write_bytes((CLIENTS / name).read_bytes())
    bundle = tmp_path / "openapi.bundled.json"
    bundle.write_text(bundle.read_text().replace('"GTFS Scorecard read API"', '"Edited"'))
    reasons = generator.stale_reasons(tmp_path)
    assert any("does not name the committed bundle" in reason for reason in reasons), reasons


def test_a_generator_pin_that_moved_without_regeneration_is_caught(tmp_path: Path) -> None:
    for name in ("openapi.bundled.json", "GENERATED.json"):
        (tmp_path / name).write_bytes((CLIENTS / name).read_bytes())
    stamp_file = tmp_path / "GENERATED.json"
    stamp = json.loads(stamp_file.read_text())
    stamp["generators"]["openapi-typescript"] = "0.0.0"
    stamp_file.write_text(json.dumps(stamp))
    reasons = generator.stale_reasons(tmp_path)
    assert any("pinned generator versions" in reason for reason in reasons), reasons


def test_the_stamp_and_the_bundle_agree_on_disk() -> None:
    stamp = json.loads((CLIENTS / "GENERATED.json").read_text())
    digest = hashlib.sha256((CLIENTS / "openapi.bundled.json").read_bytes()).hexdigest()
    assert stamp["bundle_sha256"] == digest


# --- the generators are pinned exactly ------------------------------------------


def test_each_generator_is_pinned_to_an_exact_version() -> None:
    py = tomllib.loads((CLIENTS / "python" / "pyproject.toml").read_text())
    ts = json.loads((CLIENTS / "typescript" / "package.json").read_text())
    dev = py["dependency-groups"]["dev"]
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.+-]*", dep) for dep in dev), dev
    tooling = {**ts["devDependencies"], **ts["dependencies"]}
    inexact = {n: v for n, v in tooling.items() if not re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", v)}
    assert not inexact, f"unpinned npm dependencies: {inexact}"
    assert all("==" in requirement for requirement in py["build-system"]["requires"])


def test_the_generators_are_dev_tooling_and_never_runtime_dependencies() -> None:
    py = tomllib.loads((CLIENTS / "python" / "pyproject.toml").read_text())
    runtime = " ".join(py["project"]["dependencies"])
    assert "openapi-python-client" not in runtime
    ts = json.loads((CLIENTS / "typescript" / "package.json").read_text())
    assert "openapi-typescript" not in ts["dependencies"]
    assert "openapi-typescript" in ts["devDependencies"]


def test_the_pipeline_and_the_web_app_gain_no_dependency_from_the_clients() -> None:
    pipeline = tomllib.loads((REPO_ROOT / "pipeline" / "pyproject.toml").read_text())
    everything = json.dumps(pipeline)
    for name in ("openapi-python-client", "openapi-typescript", "openapi-fetch"):
        assert name not in everything, f"pipeline/pyproject.toml now depends on {name}"
    assert not (REPO_ROOT / "web" / "package.json").exists()
    assert not (REPO_ROOT / "package.json").exists()


def test_each_client_ships_the_repository_licence() -> None:
    """A published package carries its own copy; a copy that drifted would mislicense it."""
    licence = (REPO_ROOT / "LICENSE").read_bytes()
    for client in ("python", "typescript"):
        assert (CLIENTS / client / "LICENSE").read_bytes() == licence, client


# --- coverage of the description ------------------------------------------------


def test_every_described_path_is_in_both_generated_clients() -> None:
    paths = _spec_paths()
    assert len(paths) >= 50
    python_sources = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted((GENERATED_PY / "api").rglob("*.py"))
    )
    typescript = GENERATED_TS.read_text(encoding="utf-8")
    missing_py = sorted(p for p in paths if f'"url": "{p}"' not in python_sources)
    missing_ts = sorted(p for p in paths if f'"{p}": {{' not in typescript)
    assert not missing_py, f"no generated Python operation for {missing_py}"
    assert not missing_ts, f"no generated TypeScript path for {missing_ts}"


def test_the_generated_python_has_one_endpoint_module_per_described_path() -> None:
    modules = [p for p in (GENERATED_PY / "api").rglob("*.py") if p.name != "__init__.py"]
    assert len(modules) == len(_spec_paths())


def test_the_hand_written_files_live_outside_the_generated_tree() -> None:
    """`make clients` deletes and rewrites `generated/`. These must survive it."""
    package = GENERATED_PY.parent
    for hand_written in ("__init__.py", "guard.py", "session.py", "py.typed"):
        assert (package / hand_written).is_file(), hand_written
        assert GENERATED_PY not in (package / hand_written).parents
    assert (CLIENTS / "typescript" / "src" / "guard.ts").is_file()
    assert (CLIENTS / "typescript" / "src" / "index.ts").is_file()


def test_the_generated_typescript_still_carries_its_generator_header() -> None:
    marker = "This file was auto-generated by openapi-typescript."
    assert marker in GENERATED_TS.read_text(encoding="utf-8")


# --- the schema_version guards ---------------------------------------------------


def _description_major() -> str:
    document = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    return str(document["info"]["x-artifact-schema-version-major"])


def test_both_guards_support_the_major_the_description_names() -> None:
    python_guard = (GENERATED_PY.parent / "guard.py").read_text(encoding="utf-8")
    typescript_guard = (CLIENTS / "typescript" / "src" / "guard.ts").read_text(encoding="utf-8")
    py_match = re.search(r'^SUPPORTED_SCHEMA_MAJOR = "([^"]+)"', python_guard, re.MULTILINE)
    ts_match = re.search(r'export const SUPPORTED_SCHEMA_MAJOR = "([^"]+)"', typescript_guard)
    assert py_match and ts_match, "a guard no longer declares SUPPORTED_SCHEMA_MAJOR"
    assert py_match.group(1) == _description_major()
    assert ts_match.group(1) == _description_major()


# --- the recorded responses ------------------------------------------------------


def _manifest() -> dict[str, Any]:
    loaded = json.loads((CLIENTS / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_manifest_names_a_recording_or_a_reason_for_every_described_path() -> None:
    manifest = _manifest()
    responses: dict[str, str | None] = manifest["responses"]
    assert set(responses) == _spec_paths(), (
        "clients/fixtures/manifest.json and the description disagree about which paths exist: "
        f"{sorted(set(responses) ^ _spec_paths())}"
    )
    unrecorded = {path for path, file in responses.items() if file is None}
    assert unrecorded == set(manifest["not_recorded"])
    for path, file in responses.items():
        if file is not None:
            assert (REPO_ROOT / file).is_file(), f"{path}: {file} does not exist"


def test_the_recorded_artifacts_are_real_files_that_validate_against_the_schema() -> None:
    validator = Draft202012Validator(json.loads((SCHEMAS / "artifact.schema.json").read_text()))
    files = sorted((CLIENTS / "fixtures" / "artifacts").glob("*.json"))
    assert len(files) >= 6
    for file in files:
        errors = [e.message for e in validator.iter_errors(json.loads(file.read_text()))]
        assert not errors, f"{file.name}: {errors[:3]}"
    versions = {json.loads(f.read_text())["schema_version"] for f in files}
    assert len(versions) >= 3, "the recordings should span more than one schema version"


@pytest.mark.parametrize(
    ("document", "schema"),
    [
        ("rollup-vermont.json", "rollup"),
        ("rollup-index.json", "rollup-index"),
        ("by-location.json", "by-location"),
        ("coverage.json", "coverage"),
        ("catalog-trimmed.json", "catalog"),
    ],
)
def test_the_recorded_documents_validate_against_their_schemas(document: str, schema: str) -> None:
    validator = Draft202012Validator(json.loads((SCHEMAS / f"{schema}.schema.json").read_text()))
    body = json.loads((CLIENTS / "fixtures" / "documents" / document).read_text())
    errors = [e.message for e in validator.iter_errors(body)]
    assert not errors, f"{document}: {errors[:3]}"
