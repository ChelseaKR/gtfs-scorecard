"""The lint and type gates have to cover the scripts that are themselves gates.

`make verify` runs six Python gates out of `pipeline/scripts/`. Until this test
existed, the `ruff check` line in that same target named four scripts by hand,
so 13 of the 17 files in `pipeline/scripts/` and all 3 in the repository root's
`scripts/` were never linted or format-checked, and `[tool.mypy] files` listed
only `src` and `tests`, so none of them was type-checked either. Widening the
scope surfaced 17 ruff findings, 7 files that ruff format would rewrite, and a
strict-mode type error inside `check_site_seo.py`'s own privacy gate.

A hand-written list of paths is a scope that narrows by omission and says
nothing when it does. These tests hold the directories instead.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"

# Directories whose Python files must all be inside the lint and format gates.
GATED_TREES = (
    Path("pipeline/src"),
    Path("pipeline/tests"),
    Path("pipeline/scripts"),
    Path("scripts"),
)


def _verify_recipe() -> str:
    """The body of the `verify:` target, up to the next target."""
    text = MAKEFILE.read_text()
    start = text.index("\nverify:\n") + 1
    rest = text[start + len("verify:\n") :]
    end = re.search(r"^[A-Za-z0-9_-]+:", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def _ruff_scopes(recipe: str, subcommand: str) -> set[Path]:
    """Every path argument handed to `ruff <subcommand>` in the recipe."""
    scopes: set[Path] = set()
    for line in recipe.splitlines():
        stripped = line.strip()
        if f"ruff {subcommand}" not in stripped:
            continue
        prefix = Path("pipeline") if stripped.startswith("cd pipeline &&") else Path()
        tail = stripped.split(f"ruff {subcommand}", 1)[1].split()
        skip_next = False
        for token in tail:
            if skip_next:
                skip_next = False
                continue
            if token == "--config":
                skip_next = True
                continue
            if token.startswith("-"):
                continue
            scopes.add(prefix / token)
    return scopes


def _python_files(tree: Path) -> list[Path]:
    return [
        p.relative_to(ROOT)
        for p in sorted((ROOT / tree).rglob("*.py"))
        if "__pycache__" not in p.parts
    ]


def _covered(path: Path, scopes: set[Path]) -> bool:
    return any(path == scope or scope in path.parents for scope in scopes)


def test_every_python_file_in_a_gated_tree_is_linted() -> None:
    scopes = _ruff_scopes(_verify_recipe(), "check")
    uncovered = [
        str(path)
        for tree in GATED_TREES
        for path in _python_files(tree)
        if not _covered(path, scopes)
    ]
    assert not uncovered, (
        f"make verify's `ruff check` does not reach these files, so nothing lints them: {uncovered}"
    )


def test_every_python_file_in_a_gated_tree_is_format_checked() -> None:
    scopes = _ruff_scopes(_verify_recipe(), "format")
    uncovered = [
        str(path)
        for tree in GATED_TREES
        for path in _python_files(tree)
        if not _covered(path, scopes)
    ]
    assert not uncovered, (
        f"make verify's `ruff format --check` does not reach these files: {uncovered}"
    )


def test_the_root_scripts_lint_passes_the_project_config() -> None:
    """There is no pyproject.toml above the repository root's `scripts/`, so a
    bare `ruff check scripts` there silently falls back to ruff's own defaults
    (E4/E7/E9/F) and reports clean. That is a false negative, not a pass: with
    the project's real select list the same directory had six findings."""
    recipe = _verify_recipe()
    root_lines = [
        line.strip()
        for line in recipe.splitlines()
        if line.strip().startswith("uv run --project pipeline ruff")
    ]
    assert root_lines, "nothing lints the repository root's scripts/"
    for line in root_lines:
        assert "--config pipeline/pyproject.toml" in line, (
            f"{line}: without --config, ruff uses its defaults and finds nothing"
        )


def test_mypy_checks_the_gate_scripts() -> None:
    config = tomllib.loads((ROOT / "pipeline" / "pyproject.toml").read_text())
    files = config["tool"]["mypy"]["files"]
    assert "scripts" in files, (
        "the scripts that make verify runs as gates must be type-checked; "
        "check_site_seo.py carried a strict-mode error inside its privacy gate "
        "for as long as they were not"
    )


def test_the_gates_verify_runs_are_all_inside_the_lint_scope() -> None:
    """Name them explicitly. A future edit that moves a gate script somewhere
    outside the gated trees should fail here rather than go quiet."""
    recipe = _verify_recipe()
    gates = [
        Path("pipeline") / m
        for m in re.findall(r"uv run python (scripts/[A-Za-z0-9_]+\.py)", recipe)
    ]
    assert len(gates) >= 5, gates
    check_scopes = _ruff_scopes(recipe, "check")
    format_scopes = _ruff_scopes(recipe, "format")
    for gate in gates:
        assert (ROOT / gate).is_file(), f"{gate} does not exist"
        assert _covered(gate, check_scopes), f"{gate} is a gate and is not linted"
        assert _covered(gate, format_scopes), f"{gate} is a gate and is not format-checked"


def test_the_coverage_floor_measures_the_largest_module() -> None:
    """`render_site.py` was outside `--cov-fail-under` on the argument that a
    percentage over templating glue measures markup. It is 3,132 statements,
    the largest module in the package, and it measures at 90% branch coverage
    from tests/test_render_site.py, so the argument did not hold. Omitted, its
    only independent gate was the golden suite, whose baseline it regenerates
    itself. Putting it in the floor cost nothing: the package still clears 92%.
    """
    config = tomllib.loads((ROOT / "pipeline" / "pyproject.toml").read_text())
    omit = config["tool"]["coverage"]["run"]["omit"]

    assert not any("render_site" in entry for entry in omit), (
        "render_site.py is back outside the coverage floor; it is the largest "
        "module in the package and the golden baseline is not an independent check"
    )


def test_the_coverage_floor_is_not_quietly_lowered() -> None:
    """A floor that moves down to meet the code is not a floor."""
    recipe = _verify_recipe()
    floors = re.findall(r"--cov-fail-under=(\d+)", recipe)
    assert floors, "make verify no longer sets a coverage floor"
    assert all(int(f) >= 92 for f in floors), f"the coverage floor dropped below 92: {floors}"
