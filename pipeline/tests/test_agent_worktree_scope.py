"""Nothing this repo gates on may read an agent's leftover worktree copy.

Coding agents check out working copies under `.claude/worktrees/`. They are
whole copies of this repository at whatever commit the agent started from, they
outlive the session that made them, and they are not shipped. A 2026-08-28
audit found 49 of them holding 41 GB.

Two things keep them out of every gate today, and neither one announced itself:

* `.gitignore` lists `.claude/worktrees/`, which is also what keeps Semgrep out
  of them, because `.semgrepignore` ends with `:include .gitignore` rather than
  naming the directory itself.
* Every scope in `make verify` names a directory. None of them walks the
  repository root, so none descends into `.claude/`.

Both are one edit away from stopping being true, and a gate that reads a stale
copy does not fail loudly. It reports on code that was never shipped: a lint
finding nobody can reproduce, a doc figure read off a superseded page, a secret
scan flagging a fixture deleted weeks ago. The tests below hold the two
conditions so that the edit which breaks them is the thing that fails.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_WORKTREES = ".claude/worktrees/"
GITIGNORE = ROOT / ".gitignore"
SEMGREPIGNORE = ROOT / ".semgrepignore"

# Trees holding code that `make verify` runs or checks. A recursive walk
# anchored at the repository root inside any of them would descend into
# `.claude/worktrees/`.
GATE_TREES = (
    Path("pipeline/scripts"),
    Path("pipeline/tests"),
    Path("scripts"),
)


def _gate_sources() -> list[Path]:
    return [
        path
        for tree in GATE_TREES
        for path in sorted((ROOT / tree).rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def _repo_root_anchors(module: ast.Module, source: Path) -> set[str]:
    """Names this module binds to the repository root itself.

    The idiom throughout this repo is ``NAME = Path(__file__).resolve()
    .parents[k]``. The name varies (ROOT, REPO_ROOT, REPO, _REPO), so the
    binding is recognised by evaluating the subscript against the real path of
    the file rather than by matching the name.
    """
    anchors: set[str] = set()
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        depth = _parents_index(node.value)
        if depth is None:
            continue
        if source.resolve().parents[depth] != ROOT:
            continue
        anchors.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return anchors


def _parents_index(value: ast.expr) -> int | None:
    """The ``k`` in a ``Path(__file__)[.resolve()].parents[k]`` expression."""
    if not isinstance(value, ast.Subscript):
        return None
    if not (isinstance(value.value, ast.Attribute) and value.value.attr == "parents"):
        return None
    if not (isinstance(value.slice, ast.Constant) and isinstance(value.slice.value, int)):
        return None
    return value.slice.value


def _string_bindings(module: ast.Module) -> dict[str, tuple[str, ...]]:
    """Every name in the module that provably holds one of a fixed set of strings.

    Enough to see through the two shapes a glob pattern is written in here: a
    module-level constant, and a loop variable over one. Anything else stays
    unresolved, and an unresolved pattern is treated as descending, because a
    pattern this cannot read is a pattern this cannot vouch for.
    """
    literals: dict[str, tuple[str, ...]] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        strings = _string_sequence(node.value, literals)
        if strings is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                literals[target.id] = strings

    bindings = dict(literals)
    for loop in ast.walk(module):
        if not isinstance(loop, ast.For) or not isinstance(loop.target, ast.Name):
            continue
        strings = _string_sequence(loop.iter, literals)
        if strings is not None:
            bindings[loop.target.id] = strings
    return bindings


def _string_sequence(
    value: ast.expr, literals: dict[str, tuple[str, ...]]
) -> tuple[str, ...] | None:
    """A tuple/list of string constants, a single string, or a name for either."""
    if isinstance(value, ast.Constant):
        return (value.value,) if isinstance(value.value, str) else None
    if isinstance(value, ast.Name):
        return literals.get(value.id)
    if isinstance(value, ast.Tuple | ast.List):
        items = [
            element.value
            for element in value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
        return tuple(items) if len(items) == len(value.elts) and items else None
    return None


def _descends(method: str, patterns: tuple[str, ...] | None) -> bool:
    """Whether the call walks below the directory it is anchored at.

    ``rglob`` always does. ``glob`` does only when a pattern says so with
    ``**``; a single-segment pattern such as ``*.md`` reads the root's own
    entries and stops, and a pattern whose leading segment is a literal name
    (``data/artifacts/*/latest.json``) descends into that named directory, not
    into `.claude/`.
    """
    if method == "rglob":
        return True
    if patterns is None:
        return True
    return any("**" in pattern for pattern in patterns)


def test_agent_worktrees_are_git_ignored() -> None:
    """`git add`, `git status` and Semgrep all rely on this one committed line.

    Asserted against the text of `.gitignore` rather than by running
    `git check-ignore`, which was the first way this was written and which
    could not fail. The Claude Code harness writes `**/.claude/worktrees/` into
    `.git/info/exclude`, so on a machine that has run an agent, deleting the
    committed line leaves `git check-ignore` answering yes. `.git/info/exclude`
    is per-clone and never committed. A fresh clone and CI have only the line
    below.
    """
    entries = {line.strip() for line in GITIGNORE.read_text().splitlines()}
    assert AGENT_WORKTREES in entries, (
        f"{AGENT_WORKTREES} is no longer listed in .gitignore. Leftover agent "
        "worktrees would show up in `git status`, be swept into a `git add`, "
        "and enter the Semgrep scan through .semgrepignore's `:include .gitignore`. "
        "A local .git/info/exclude may still hide that here and not in CI."
    )


def test_semgrepignore_still_defers_to_the_gitignore() -> None:
    """.semgrepignore never names `.claude/`; it inherits it."""
    text = SEMGREPIGNORE.read_text()
    assert ":include .gitignore" in text, (
        ".semgrepignore no longer includes .gitignore, so nothing keeps Semgrep "
        f"out of {AGENT_WORKTREES}. A repo-level .semgrepignore replaces "
        "Semgrep's defaults rather than extending them, so the directory has to "
        "be excluded here or named outright."
    )


def test_no_gate_walks_the_repository_root() -> None:
    """A root-anchored recursive walk reads every leftover worktree copy."""
    offenders: list[str] = []
    for source in _gate_sources():
        module = ast.parse(source.read_text())
        anchors = _repo_root_anchors(module, source)
        if not anchors:
            continue
        bindings = _string_bindings(module)
        for node in ast.walk(module):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr not in {"glob", "rglob"}:
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id in anchors):
                continue
            patterns = _string_sequence(node.args[0], bindings) if node.args else None
            if not _descends(func.attr, patterns):
                continue
            rel = source.relative_to(ROOT)
            shown = ", ".join(repr(p) for p in patterns) if patterns else "<unresolved>"
            offenders.append(f"{rel}:{node.lineno}: {func.value.id}.{func.attr}({shown})")

    assert not offenders, (
        "These walk the repository root recursively, which descends into "
        f"{AGENT_WORKTREES} and reports on code that was never shipped. Anchor "
        "the walk at the directory the gate is about:\n" + "\n".join(offenders)
    )
