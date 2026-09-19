#!/usr/bin/env python3
"""Generate the typed clients from the OpenAPI description, or prove they are current (#370).

Everything under ``clients/`` that a person did not write is written here:

* ``clients/openapi.bundled.json``, the description with its schema references
  resolved (``bundle_openapi.py``);
* ``clients/python/src/gtfs_scorecard_client/generated/``, from
  ``openapi-python-client``;
* ``clients/typescript/src/generated/schema.ts``, from ``openapi-typescript``;
* ``clients/GENERATED.json``, which names the bundle's digest and the two
  generator versions that produced the rest.

    python3 pipeline/scripts/generate_clients.py            # regenerate in place
    python3 pipeline/scripts/generate_clients.py --check    # exit 1 on any drift
    python3 pipeline/scripts/generate_clients.py --control  # prove --check can fail

``--check`` generates into a temporary directory and compares it with the
committed tree byte for byte. It never modifies the working tree, and it
catches what the cheap digest test in ``tests/test_clients_drift.py`` cannot: a
hand edit inside generated code, and a generator whose output changed under an
unchanged pin.

``--control`` is the negative control. It changes a copy of the description, a
copy of a published schema, and a copy of the committed generated code, and
requires ``--check`` to fail for each. A drift check that passes on a stale tree
is worse than none, so CI runs this beside the check itself.

Needs ``uv`` and, for the TypeScript half, ``npm ci --ignore-scripts`` already
run in ``clients/typescript`` (``make clients`` does both).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENTS = REPO_ROOT / "clients"
PY_PROJECT = CLIENTS / "python"
TS_PROJECT = CLIENTS / "typescript"
GENERATED_PY = Path("python/src/gtfs_scorecard_client/generated")
GENERATED_TS = Path("typescript/src/generated/schema.ts")
BUNDLE_NAME = Path("openapi.bundled.json")
STAMP_NAME = Path("GENERATED.json")

# Tool caches written next to generated code by a post-hook; never part of it.
IGNORED_PARTS = frozenset({".ruff_cache", "__pycache__"})


def _load_bundler() -> ModuleType:
    path = Path(__file__).with_name("bundle_openapi.py")
    spec = importlib.util.spec_from_file_location("bundle_openapi", path)
    if spec is None or spec.loader is None:  # pragma: no cover - the file sits beside this one
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def pinned_generators() -> dict[str, str]:
    """The exact generator versions the two client projects declare."""
    py = tomllib.loads((PY_PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    pin = next(
        (
            dep.split("==", 1)[1]
            for dep in py["dependency-groups"]["dev"]
            if dep.startswith("openapi-python-client==")
        ),
        None,
    )
    ts = json.loads((TS_PROJECT / "package.json").read_text(encoding="utf-8"))
    ts_pin = ts["devDependencies"].get("openapi-typescript")
    if pin is None or ts_pin is None:
        raise SystemExit("a generator is not pinned to an exact version in its project file")
    return {"openapi-python-client": pin, "openapi-typescript": ts_pin}


def stamp_text(bundle_text: str) -> str:
    stamp = {
        "note": (
            "Written by pipeline/scripts/generate_clients.py. Ties every generated file under "
            "clients/ to the bundle and the generator versions that produced it."
        ),
        "bundle": "openapi.bundled.json",
        "bundle_sha256": hashlib.sha256(bundle_text.encode("utf-8")).hexdigest(),
        "generators": pinned_generators(),
    }
    return json.dumps(stamp, indent=2) + "\n"


def _run(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(  # noqa: S603 - argv is built here from fixed names and repo paths
        argv,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(argv)}")
    return result.stdout


# openapi-python-client 0.29.1 reads a model with `d = dict(src_dict)` and then
# `d.pop("<json key>")` for each property. The grade distributions carry a
# property named "D" (grade D), which the generator writes as the Python name
# `d`, so `d = d.pop("D")` replaces the dict it is still reading from and the
# next line, `f = d.pop("F")`, fails with "'int' object has no attribute 'pop'".
# `by-location.json` and every rollup hit it, and it surfaced only because the
# contract test parses those documents. The local is renamed `_d` in a copy of
# the model template at generation time. The upstream file is patched, not
# forked, so a new generator version brings its own template, and a version
# whose template no longer matches these patterns stops here instead of
# silently generating unpatched code. Each entry is (old, new, expected count).
SHADOWED_LOCAL_PATCHES = (
    ("        d = dict(src_dict)\n", "        _d = dict(src_dict)\n", 1),
    ("""'d.pop("' +""", """'_d.pop("' +""", 2),
    ("in d.items():", "in _d.items():", 1),
    ("additional_properties = d\n", "additional_properties = _d\n", 1),
)


def patched_model_template(upstream: str) -> str:
    """The generator's model template with its `d` local renamed, or a clear refusal."""
    patched = upstream
    for old, new, expected in SHADOWED_LOCAL_PATCHES:
        found = patched.count(old)
        if found != expected:
            raise SystemExit(
                f"the pinned generator's model.py.jinja no longer contains {old!r} {expected} "
                f"time(s) (found {found}). Read the new template: the `d` shadowing may be "
                "fixed upstream, and this patch may be droppable."
            )
        patched = patched.replace(old, new)
    return patched


def _upstream_model_template(uv: str) -> str:
    stdout = _run(
        [
            uv,
            "run",
            "--project",
            str(PY_PROJECT),
            "--locked",
            "--only-group",
            "dev",
            "python",
            "-c",
            "import pathlib, openapi_python_client as m; "
            "print(pathlib.Path(m.__file__).parent / 'templates' / 'model.py.jinja')",
        ],
        cwd=PY_PROJECT,
    )
    return Path(stdout.strip()).read_text(encoding="utf-8")


def _generate_python(bundle: Path, out_dir: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required to run openapi-python-client")
    with tempfile.TemporaryDirectory(prefix="gtfs-clients-py-") as scratch:
        target = Path(scratch) / "generated"
        templates = Path(scratch) / "templates"
        templates.mkdir()
        (templates / "model.py.jinja").write_text(
            patched_model_template(_upstream_model_template(uv)), encoding="utf-8"
        )
        _run(
            [
                uv,
                "run",
                "--project",
                str(PY_PROJECT),
                "--locked",
                "--only-group",
                "dev",
                "openapi-python-client",
                "generate",
                "--path",
                str(bundle),
                "--meta",
                "none",
                "--config",
                str(PY_PROJECT / "generator.yml"),
                "--custom-template-path",
                str(templates),
                "--output-path",
                str(target),
                "--overwrite",
            ],
            cwd=Path(scratch),
            env={"RUFF_NO_CACHE": "true"},
        )
        if out_dir.exists():
            shutil.rmtree(out_dir)
        shutil.copytree(target, out_dir, ignore=shutil.ignore_patterns(*IGNORED_PARTS))


def _generate_typescript(bundle: Path, out_file: Path) -> None:
    tool = TS_PROJECT / "node_modules" / ".bin" / "openapi-typescript"
    if not tool.exists():
        raise SystemExit(
            "openapi-typescript is not installed; "
            "run `npm ci --ignore-scripts` in clients/typescript"
        )
    out_file.parent.mkdir(parents=True, exist_ok=True)
    _run([str(tool), str(bundle), "-o", str(out_file)], cwd=TS_PROJECT)


def generate(dest: Path, *, spec: Path | None = None, schemas: Path | None = None) -> None:
    """Write every derived file under ``dest`` (a ``clients/``-shaped directory)."""
    bundler = _load_bundler()
    bundle_text: str = bundler.render(spec or bundler.OPENAPI_PATH, schemas or bundler.SCHEMAS_DIR)
    bundle = dest / BUNDLE_NAME
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(bundle_text, encoding="utf-8")
    _generate_python(bundle, dest / GENERATED_PY)
    _generate_typescript(bundle, dest / GENERATED_TS)
    (dest / STAMP_NAME).write_text(stamp_text(bundle_text), encoding="utf-8")


def _derived_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for rel in (BUNDLE_NAME, STAMP_NAME, GENERATED_TS):
        if (root / rel).is_file():
            files[rel.as_posix()] = root / rel
    generated = root / GENERATED_PY
    if generated.is_dir():
        for path in sorted(generated.rglob("*")):
            if path.is_file() and not IGNORED_PARTS.intersection(path.parts):
                files[path.relative_to(root).as_posix()] = path
    return files


def compare(fresh: Path, committed: Path) -> list[str]:
    """One line per file that differs between a fresh generation and the committed tree."""
    fresh_files, committed_files = _derived_files(fresh), _derived_files(committed)
    problems: list[str] = []
    for name in sorted(fresh_files.keys() | committed_files.keys()):
        if name not in committed_files:
            problems.append(f"missing from the commit: {name}")
        elif name not in fresh_files:
            problems.append(f"in the commit but no longer generated: {name}")
        elif fresh_files[name].read_bytes() != committed_files[name].read_bytes():
            problems.append(f"differs: {name}")
    return problems


def _first_diff(fresh: Path, committed: Path, problems: list[str], limit: int = 40) -> str:
    for line in problems:
        if line.startswith("differs: "):
            name = line.removeprefix("differs: ")
            a = (committed / name).read_text(encoding="utf-8").splitlines()
            b = (fresh / name).read_text(encoding="utf-8").splitlines()
            diff = difflib.unified_diff(
                a, b, f"committed/{name}", f"regenerated/{name}", lineterm=""
            )
            return "\n".join(list(diff)[:limit])
    return ""


def check(
    *,
    spec: Path | None = None,
    schemas: Path | None = None,
    committed: Path = CLIENTS,
    show_diff: bool = True,
) -> list[str]:
    """Regenerate into a temporary directory and list every difference from ``committed``."""
    with tempfile.TemporaryDirectory(prefix="gtfs-clients-check-") as scratch:
        fresh = Path(scratch)
        generate(fresh, spec=spec, schemas=schemas)
        problems = compare(fresh, committed)
        if problems and show_diff:
            sample = _first_diff(fresh, committed, problems)
            if sample:
                sys.stderr.write(sample + "\n")
    return problems


def stale_reasons(
    root: Path = CLIENTS, *, spec: Path | None = None, schemas: Path | None = None
) -> list[str]:
    """The drift that needs no generator, so an ordinary test run can catch it.

    Two things: the committed bundle is not what the description and schemas
    produce, or ``GENERATED.json`` does not name that bundle and the pinned
    generator versions. Everything downstream of the bundle is deterministic
    given those, which is why this is enough to tell a contributor to run
    ``make clients``. It cannot see a hand edit inside generated code; ``check``
    does.
    """
    bundler = _load_bundler()
    expected: str = bundler.render(spec or bundler.OPENAPI_PATH, schemas or bundler.SCHEMAS_DIR)
    bundle = root / BUNDLE_NAME
    committed = bundle.read_text(encoding="utf-8") if bundle.is_file() else None
    reasons: list[str] = []
    if committed != expected:
        reasons.append(
            "clients/openapi.bundled.json is not what web/api/v1/openapi.yaml and "
            "web/schemas/ produce"
        )
    stamp_file = root / STAMP_NAME
    stamp = json.loads(stamp_file.read_text(encoding="utf-8")) if stamp_file.is_file() else {}
    if stamp.get("bundle_sha256") != hashlib.sha256((committed or "").encode("utf-8")).hexdigest():
        reasons.append("clients/GENERATED.json does not name the committed bundle")
    if stamp.get("generators") != pinned_generators():
        reasons.append("clients/GENERATED.json does not name the pinned generator versions")
    return reasons


def mutated_description(scratch: Path) -> Path:
    """A copy of the description with one operation added and nothing regenerated."""
    text = (REPO_ROOT / "web" / "api" / "v1" / "openapi.yaml").read_text(encoding="utf-8")
    marker = "  /api/v1/index.json:\n"
    if marker not in text:  # pragma: no cover - guards the control against a moved marker
        raise SystemExit("--control cannot find its insertion point in openapi.yaml")
    added = (
        "  /api/v1/negative-control.json:\n"
        "    get:\n"
        "      operationId: getNegativeControl\n"
        "      summary: Added by --control to prove the drift check can fail.\n"
        "      responses:\n"
        '        "200": {$ref: "#/components/responses/JsonObject"}\n'
    )
    path = scratch / "openapi.yaml"
    path.write_text(text.replace(marker, added + marker, 1), encoding="utf-8")
    return path


def mutated_schemas(scratch: Path) -> Path:
    """A copy of the published schemas with one optional field added to the artifact."""
    target = scratch / "schemas"
    shutil.copytree(REPO_ROOT / "web" / "schemas", target)
    path = target / "artifact.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["properties"]["negative_control"] = {"type": "string"}
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return target


def _hand_edited_copy(scratch: Path) -> Path:
    """A copy of the committed derived files with one generated model edited by hand."""
    target = scratch / "committed"
    for name, path in _derived_files(CLIENTS).items():
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target / name)
    model = target / GENERATED_PY / "models" / "artifact.py"
    model.write_text(model.read_text(encoding="utf-8") + "\n# edited by hand\n", encoding="utf-8")
    return target


def control() -> int:
    """Require ``check`` to fail on each way the clients can go stale."""
    with tempfile.TemporaryDirectory(prefix="gtfs-clients-control-") as scratch_name:
        scratch = Path(scratch_name)
        spec = mutated_description(scratch)
        schemas = mutated_schemas(scratch)
        edited = _hand_edited_copy(scratch)
        cases = {
            "a path added to openapi.yaml": check(spec=spec, show_diff=False),
            "a field added to artifact.schema.json": check(schemas=schemas, show_diff=False),
            "a hand edit inside generated code": check(committed=edited, show_diff=False),
        }
    blind = [name for name, problems in cases.items() if not problems]
    for name, problems in cases.items():
        print(f"{'BLIND' if not problems else 'caught'}: {name} ({len(problems)} files differ)")
    if blind:
        print("The drift check passed on a stale tree: " + "; ".join(blind), file=sys.stderr)
        return 1
    print("OK  the drift check fails on a stale description, a stale schema and a hand edit")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="exit 1 when the committed clients drift"
    )
    mode.add_argument("--control", action="store_true", help="prove --check fails on a stale tree")
    args = parser.parse_args(argv)

    if args.control:
        return control()
    if args.check:
        problems = check()
        if problems:
            print("\n".join(problems), file=sys.stderr)
            print(
                "The generated clients are stale. Run `make clients` and commit.", file=sys.stderr
            )
            return 1
        print("OK  the committed clients match a fresh generation")
        return 0
    generate(CLIENTS)
    print(f"regenerated the derived files under {CLIENTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
