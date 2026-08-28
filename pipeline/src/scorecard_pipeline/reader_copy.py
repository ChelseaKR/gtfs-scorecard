"""Every reader-facing finding string the pipeline can publish, in one inventory.

The product's promise is that a finding reads as plain language a transit
manager can act on: what is wrong, why a rider cares, what to do next. Two
families of copy carry that promise onto the same paragraph of the same agency
page.

1. **Curated validator wording** in :data:`notices.TRANSLATIONS`, one entry per
   MobilityData notice code.
2. **Findings the pipeline authors itself** -- accessibility, completeness,
   fares, flexible service, pathways, routability, realtime, freshness. These
   are written inline at each ``Finding(...)`` construction site.

``scripts/check_readability.py`` was written against the first family only, so
the second family has never been measured by the gate that exists to measure it.
This module supplies the whole inventory instead, and it reads the package
source rather than running the scorers: a scorer emits its finding only when a
feed trips it, so a fixture-driven sweep would under-cover precisely the rare
findings nobody re-reads.

**Fail closed.** A ``Finding(...)`` site whose copy this module cannot account
for raises :class:`UnreadableCopy`, naming the file, line and field. Copy that
is deliberately not measured here is returned as a :class:`DeferredSite` with
its reason, so the gate can print it. There is no third outcome where a string
is neither measured nor reported.

Two limits are deliberate and stated rather than hidden:

* A value interpolated at run time (a count, a stop name, a joined list) is
  substituted with :data:`RUNTIME_VALUE` before measuring. The gate is judging
  the sentence an author wrote, not the numbers a feed happens to produce.
* ``notices.translate`` falls back to a generated line for a notice code with no
  curated entry. That line is assembled from the code and a rule URL, so
  measuring it would measure the code, not the writing. It keeps the exclusion
  ``check_readability.py`` has always declared, and the curated-coverage metric
  on ``/problems/`` remains its measure. Sites that take their copy from
  ``translate`` are reported as deferred rather than dropped.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Literal

from .notices import TRANSLATIONS

#: The finding fields that make the plain-language promise. ``effort`` is
#: excluded for the reason the gate has always given: effort hints are
#: fragments ("One setting."), not prose.
COPY_FIELDS: tuple[str, ...] = ("what", "why", "fix")

#: Stand-in for a value the feed supplies at run time. One short, common word
#: so the substitution neither rescues nor sinks the sentence around it.
RUNTIME_VALUE = "12"

#: A conditional sentence can read two ways; a couple of nested conditionals can
#: read a few more. Past this the site is treated as unreadable and fails loudly
#: rather than expanding without bound.
MAX_VARIANTS = 8

#: How a string reached the reader.
Provenance = Literal["curated", "authored", "curated_table", "republished"]


class UnreadableCopy(Exception):
    """A ``Finding(...)`` site whose reader-facing copy cannot be accounted for.

    Raised rather than skipped. A site the inventory cannot read is a string the
    gate would silently pass, which is the failure this module exists to remove.
    """


@dataclass(frozen=True)
class CopyString:
    """One reader-facing string, ready to measure."""

    label: str
    field: str
    text: str
    provenance: Provenance
    origin: str


@dataclass(frozen=True)
class DeferredSite:
    """A field whose copy is measured elsewhere, or deliberately not measured.

    Carries its reason so the gate can print what it did not look at.
    """

    label: str
    field: str
    provenance: Provenance
    origin: str
    reason: str


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def _single_assignments(node: ast.AST) -> dict[str, ast.expr]:
    """Names assigned exactly once inside ``node``, mapped to their value.

    A name assigned more than once is ambiguous at this level of reading and is
    left out, which makes the site unreadable rather than guessed at.
    """
    counts: dict[str, int] = {}
    values: dict[str, ast.expr] = {}
    for child in ast.walk(node):
        if not isinstance(child, ast.Assign) or len(child.targets) != 1:
            continue
        target = child.targets[0]
        if not isinstance(target, ast.Name):
            continue
        counts[target.id] = counts.get(target.id, 0) + 1
        values[target.id] = child.value
    return {name: value for name, value in values.items() if counts[name] == 1}


def _joined_texts(node: ast.JoinedStr, scope: dict[str, ast.expr]) -> tuple[str, ...] | None:
    """Every reading of an f-string; interpolated values become RUNTIME_VALUE."""
    parts: list[tuple[str, ...]] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append((value.value,))
            continue
        if isinstance(value, ast.FormattedValue):
            inner = _literal_texts(value.value, scope)
            parts.append(inner if inner is not None else (RUNTIME_VALUE,))
            continue
        return None
    return _combine(parts)


def _combine(parts: list[tuple[str, ...]]) -> tuple[str, ...] | None:
    """Cartesian product of the readings of each part, bounded by MAX_VARIANTS."""
    total = 1
    for part in parts:
        total *= len(part)
    if total > MAX_VARIANTS:
        return None
    return tuple("".join(combo) for combo in product(*parts)) if parts else ("",)


def _literal_texts(node: ast.expr, scope: dict[str, ast.expr]) -> tuple[str, ...] | None:
    """Every string this expression can evaluate to, or None if that is not knowable."""
    if isinstance(node, ast.Constant):
        return (node.value,) if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        return _joined_texts(node, scope)
    if isinstance(node, ast.IfExp):
        body = _literal_texts(node.body, scope)
        orelse = _literal_texts(node.orelse, scope)
        if body is None or orelse is None:
            return None
        merged = body + orelse
        return merged if len(merged) <= MAX_VARIANTS else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_texts(node.left, scope)
        right = _literal_texts(node.right, scope)
        if left is None or right is None:
            return None
        return _combine([left, right])
    if isinstance(node, ast.Name):
        bound = scope.get(node.id)
        # An empty scope on the recursive call: a name bound to another name is
        # not followed, so a chain resolves to unreadable rather than to a guess.
        return None if bound is None else _literal_texts(bound, {})
    return None


def _is_translation_field(node: ast.expr, field: str) -> bool:
    """``t.what`` where the attribute is the field being filled: curated wording."""
    return isinstance(node, ast.Attribute) and node.attr == field


def _is_republished_field(node: ast.expr, field: str) -> bool:
    """``d["what"]`` or ``d.get("what", ...)``: copy read back from an artifact."""
    if isinstance(node, ast.Subscript):
        key = node.slice
        return isinstance(key, ast.Constant) and key.value == field
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr != "get" or not node.args:
            return False
        first = node.args[0]
        return isinstance(first, ast.Constant) and first.value == field
    return False


def _is_finding_call(node: ast.Call) -> bool:
    """A direct ``Finding(...)`` call, the one shape that authors finding copy."""
    return isinstance(node.func, ast.Name) and node.func.id == "Finding"


def _finding_calls(tree: ast.Module) -> list[tuple[ast.Call, dict[str, ast.expr]]]:
    """Every ``Finding(...)`` call in a module, each with its enclosing scope."""
    found: list[tuple[ast.Call, dict[str, ast.expr]]] = []

    def walk(node: ast.AST, scope: dict[str, ast.expr]) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            scope = {**scope, **_single_assignments(node)}
        if isinstance(node, ast.Call) and _is_finding_call(node):
            found.append((node, scope))
        for child in ast.iter_child_nodes(node):
            walk(child, scope)

    walk(tree, _single_assignments(tree))
    return found


def _site_label(call: ast.Call, module: str) -> str:
    """``code`` when the site states one literally, else the module and line."""
    for keyword in call.keywords:
        if keyword.arg == "code":
            texts = _literal_texts(keyword.value, {})
            if texts is not None and len(texts) == 1:
                return texts[0]
    return f"{module}:{call.lineno}"


def _read_field(
    call: ast.Call, field: str, scope: dict[str, ast.expr], label: str, origin: str
) -> tuple[list[CopyString], list[DeferredSite]]:
    """Account for one field of one ``Finding(...)`` site, or refuse to."""
    value = next((kw.value for kw in call.keywords if kw.arg == field), None)
    if value is None:
        raise UnreadableCopy(f"{origin}: Finding() has no {field}= to read")

    texts = _literal_texts(value, scope)
    if texts is not None:
        return _authored(texts, field, label, origin), []

    if _is_translation_field(value, field):
        return [], [
            DeferredSite(
                label=label,
                field=field,
                provenance="curated_table",
                origin=origin,
                reason=(
                    "takes its wording from notices.translate: the curated table is "
                    "measured above, and the generated fallback for an uncurated code "
                    "keeps its declared exclusion"
                ),
            )
        ]

    if _is_republished_field(value, field):
        return [], [
            DeferredSite(
                label=label,
                field=field,
                provenance="republished",
                origin=origin,
                reason="reads back copy from a published artifact, authored elsewhere",
            )
        ]

    raise UnreadableCopy(
        f"{origin}: cannot read {field}= for the plain-language gate. "
        "Write it as a literal, an f-string, or a conditional over literals, "
        "or take it from notices.translate."
    )


def _authored(texts: tuple[str, ...], field: str, label: str, origin: str) -> list[CopyString]:
    """One CopyString per reading; a conditional sentence is measured both ways."""
    if len(texts) == 1:
        return [
            CopyString(
                label=f"{label}.{field}",
                field=field,
                text=texts[0],
                provenance="authored",
                origin=origin,
            )
        ]
    return [
        CopyString(
            label=f"{label}.{field}#{index}",
            field=field,
            text=text,
            provenance="authored",
            origin=origin,
        )
        for index, text in enumerate(texts, start=1)
    ]


def authored_finding_copy(
    package_dir: Path | None = None,
) -> tuple[list[CopyString], list[DeferredSite]]:
    """Read every ``Finding(...)`` site in the package and account for its copy.

    Raises :class:`UnreadableCopy` on the first site that cannot be accounted
    for, naming the file, line and field.
    """
    root = package_dir if package_dir is not None else _package_dir()
    strings: list[CopyString] = []
    deferred: list[DeferredSite] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call, scope in _finding_calls(tree):
            origin = f"{path.name}:{call.lineno}"
            label = _site_label(call, path.name)
            for field in COPY_FIELDS:
                site_strings, site_deferred = _read_field(call, field, scope, label, origin)
                strings.extend(site_strings)
                deferred.extend(site_deferred)
    return strings, deferred


def curated_copy() -> list[CopyString]:
    """The curated validator-notice wording, exactly as published."""
    return [
        CopyString(
            label=f"{code}.{field}",
            field=field,
            text=getattr(TRANSLATIONS[code], field),
            provenance="curated",
            origin="notices.TRANSLATIONS",
        )
        for code in sorted(TRANSLATIONS)
        for field in COPY_FIELDS
    ]


def reader_copy(
    package_dir: Path | None = None,
) -> tuple[list[CopyString], list[DeferredSite]]:
    """Both families of reader-facing finding copy, plus what was deferred."""
    authored, deferred = authored_finding_copy(package_dir)
    return curated_copy() + authored, deferred
