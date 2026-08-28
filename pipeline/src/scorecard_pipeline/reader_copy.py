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
import inspect
import re
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Literal

from .notices import TRANSLATIONS

#: The finding fields that make the plain-language promise. ``effort`` is
#: excluded for the reason the gate has always given: effort hints are
#: fragments ("One setting."), not prose.
COPY_FIELDS: tuple[str, ...] = ("what", "why", "fix")

#: The construction sites that carry reader-facing copy, and which of their
#: arguments carry it. A finding says what is wrong, why a rider cares and what
#: to do; a scored category leads with one summary sentence above its findings.
COPY_SITES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Finding", COPY_FIELDS),
    ("CategoryResult", ("summary",)),
)

#: Stand-in for a value the feed supplies at run time. One short, common word
#: so the substitution neither rescues nor sinks the sentence around it.
RUNTIME_VALUE = "12"

#: A conditional sentence can read two ways; a couple of nested conditionals can
#: read a few more. Past this the site is treated as unreadable and fails loudly
#: rather than expanding without bound.
MAX_VARIANTS = 8

#: How a string reached the reader.
Provenance = Literal["curated", "authored", "assembled", "curated_table", "republished", "produced"]


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


def _assignments(node: ast.AST) -> dict[str, list[ast.expr]]:
    """Every value assigned to each plain name inside ``node``.

    A summary sentence is usually chosen by an if/elif chain, so a name is
    assigned once per branch. All of them are readings the page can show, so
    all of them are measured. A name assigned anything the evaluator cannot
    read still makes the whole site unreadable rather than guessed at.
    """
    values: dict[str, list[ast.expr]] = {}

    def visit(inner: ast.AST) -> None:
        for child in ast.iter_child_nodes(inner):
            # A nested definition has its own scope; its assignments belong to
            # that scope, not to this one.
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            if isinstance(child, ast.Assign) and len(child.targets) == 1:
                target = child.targets[0]
                if isinstance(target, ast.Name):
                    values.setdefault(target.id, []).append(child.value)
            visit(child)

    visit(node)
    return values


def _joined_texts(
    node: ast.JoinedStr, scope: dict[str, list[ast.expr]], seen: frozenset[str]
) -> tuple[str, ...] | None:
    """Every reading of an f-string; interpolated values become RUNTIME_VALUE."""
    parts: list[tuple[str, ...]] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append((value.value,))
            continue
        if isinstance(value, ast.FormattedValue):
            inner = _literal_texts(value.value, scope, seen)
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


def _literal_texts(
    node: ast.expr, scope: dict[str, list[ast.expr]], seen: frozenset[str] = frozenset()
) -> tuple[str, ...] | None:
    """Every string this expression can evaluate to, or None if that is not knowable."""
    if isinstance(node, ast.Constant):
        return (node.value,) if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        return _joined_texts(node, scope, seen)
    if isinstance(node, ast.IfExp):
        body = _literal_texts(node.body, scope, seen)
        orelse = _literal_texts(node.orelse, scope, seen)
        if body is None or orelse is None:
            return None
        merged = body + orelse
        return merged if len(merged) <= MAX_VARIANTS else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_texts(node.left, scope, seen)
        right = _literal_texts(node.right, scope, seen)
        if left is None or right is None:
            return None
        return _combine([left, right])
    if isinstance(node, ast.Name):
        return _name_texts(node, scope, seen)
    return None


def _name_texts(
    node: ast.Name, scope: dict[str, list[ast.expr]], seen: frozenset[str]
) -> tuple[str, ...] | None:
    """Every reading of a name, one per assignment in the enclosing scope.

    A name already being resolved is not followed again, so a cyclic or
    self-referential binding reads as unreadable rather than recursing.
    """
    bound = scope.get(node.id)
    if not bound or node.id in seen:
        return None
    readings: tuple[str, ...] = ()
    for value in bound:
        texts = _literal_texts(value, scope, seen | {node.id})
        if texts is None:
            return None
        readings += texts
    return readings if len(readings) <= MAX_VARIANTS else None


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


def _is_call_to(node: ast.Call, name: str) -> bool:
    """A direct ``name(...)`` call: the shapes that carry authored reader copy."""
    return isinstance(node.func, ast.Name) and node.func.id == name


def _calls_to(tree: ast.Module, name: str) -> list[tuple[ast.Call, dict[str, list[ast.expr]]]]:
    """Every ``name(...)`` call in a module, each with its enclosing scope."""
    found: list[tuple[ast.Call, dict[str, list[ast.expr]]]] = []

    def walk(node: ast.AST, scope: dict[str, list[ast.expr]]) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            scope = {**scope, **_assignments(node)}
        if isinstance(node, ast.Call) and _is_call_to(node, name):
            found.append((node, scope))
        for child in ast.iter_child_nodes(node):
            walk(child, scope)

    walk(tree, _assignments(tree))
    return found


def _is_produced_field(node: ast.expr) -> str | None:
    """``summary=_realtime_summary(...)``: assembled by a registered producer.

    Returns the producer label, or None when the call is to something the
    registry does not measure. A call to an unregistered function is not a
    deferral; it raises like any other unaccountable shape.
    """
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return None
    return node.func.id if node.func.id in producer_labels() else None


def _site_label(call: ast.Call, module: str) -> str:
    """``code`` when the site states one literally, else the module and line."""
    for keyword in call.keywords:
        if keyword.arg == "code":
            texts = _literal_texts(keyword.value, {})
            if texts is not None and len(texts) == 1:
                return texts[0]
    return f"{module}:{call.lineno}"


def _read_field(
    call: ast.Call, field: str, scope: dict[str, list[ast.expr]], label: str, origin: str
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

    produced = _is_produced_field(value)
    if produced is not None:
        return [], [
            DeferredSite(
                label=label,
                field=field,
                provenance="produced",
                origin=origin,
                reason=(
                    f"assembled at run time by {produced}, which the producer registry "
                    "measures over an exhaustive input set"
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
        "take it from notices.translate, or register the function that assembles "
        "it as a producer in reader_copy's producer registry."
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
    """Read every reader-copy construction site in the package and account for it.

    Raises :class:`UnreadableCopy` on the first site that cannot be accounted
    for, naming the file, line and field.
    """
    root = package_dir if package_dir is not None else _package_dir()
    strings: list[CopyString] = []
    deferred: list[DeferredSite] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for site, fields in COPY_SITES:
            for call, scope in _calls_to(tree, site):
                origin = f"{path.name}:{call.lineno}"
                label = _site_label(call, path.name)
                for field in fields:
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
    """Every reader-facing string the scorecard publishes, plus what was deferred.

    Three families: the curated validator wording, the copy authored at a
    construction site, and the copy assembled at run time by a registered
    producer. A synthetic ``package_dir`` reads only the construction sites, so
    a test can exercise the source reader without the shipped producers.
    """
    authored, deferred = authored_finding_copy(package_dir)
    if package_dir is not None:
        return curated_copy() + authored, deferred
    return curated_copy() + authored + assembled_copy(), deferred


# --- copy assembled at run time ----------------------------------------------
#
# Some reader copy is not written whole at one site. `rt._realtime_summary`
# joins clauses chosen by what the sampling window contained, and
# `consequence.consequence_line` appends a sentence per number it actually has.
# Reading that from source would mean re-implementing the assembly, so it is
# measured the other way: run the producer over an input set that reaches every
# branch, and measure every distinct sentence it can emit.
#
# The guarantee source reading gives (no rare path missed) is kept by asserting
# it directly. Every authored fragment in the producer's own source has to turn
# up in at least one enumerated output. A new branch with new wording that the
# input set does not reach raises `UnmeasuredFragment` naming the fragment, so
# the input set cannot quietly fall behind the code.


class UnmeasuredFragment(Exception):
    """A producer's authored fragment that no enumerated output contained."""


@dataclass(frozen=True)
class Producer:
    """One run-time assembler of reader copy, with the inputs that exhaust it."""

    label: str
    outputs: Callable[[], list[str]]
    sources: tuple[Callable[..., Any], ...]


def _is_docstring(node: ast.AST, tree: ast.AST) -> bool:
    body = getattr(tree, "body", None)
    if not body or not isinstance(body[0], ast.Expr):
        return False
    return body[0].value is node


def authored_fragments(fn: Callable[..., Any]) -> list[str]:
    """Every authored string in a function's source, docstring excluded.

    Two shapes count as authored: a lettered literal containing a space (a
    phrase somebody wrote), and either branch of a conditional expression (the
    one-word alternatives a sentence picks between, like "behind" and "ahead
    of"). A dict key or a comparison string is neither, so an identifier is
    never mistaken for prose.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    chosen = {
        id(branch)
        for node in ast.walk(tree)
        if isinstance(node, ast.IfExp)
        for branch in (node.body, node.orelse)
    }
    fragments: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if _is_docstring(node, tree.body[0]):
            continue
        text = node.value
        if not re.search("[A-Za-z]", text):
            continue
        if " " in text or id(node) in chosen:
            fragments.append(text)
    return fragments


def _normalize(text: str) -> str:
    """Collapse run-time numbers so two outputs differing only in counts are one."""
    return re.sub(r"[0-9][0-9,.]*", RUNTIME_VALUE, text)


def assembled_copy() -> list[CopyString]:
    """Every distinct sentence the registered producers can emit.

    Raises :class:`UnmeasuredFragment` when a producer's source contains
    authored wording that no enumerated output reached.
    """
    strings: list[CopyString] = []
    for producer in _producers():
        outputs = [_normalize(text) for text in producer.outputs()]
        for source in producer.sources:
            for fragment in authored_fragments(source):
                if not any(_normalize(fragment) in output for output in outputs):
                    raise UnmeasuredFragment(
                        f"{producer.label}: no enumerated output contains "
                        f"{fragment!r} from {source.__name__}. Extend the producer's "
                        "input set until every branch is reached."
                    )
        for index, text in enumerate(sorted(set(outputs)), start=1):
            strings.append(
                CopyString(
                    label=f"{producer.label}#{index}",
                    field="summary",
                    text=text,
                    provenance="assembled",
                    origin=producer.label,
                )
            )
    return strings


def producer_labels() -> frozenset[str]:
    """Function names the producer registry measures."""
    return frozenset(producer.label for producer in _producers())


def _realtime_summary_outputs() -> list[str]:
    """Every realtime summary the sampling window can produce.

    The clauses are chosen by four independent conditions: whether trip
    coverage was measurable, whether the window fell outside service hours,
    whether vehicle plausibility was measurable, and whether drift ran behind
    or ahead. The product of those reaches every branch.
    """
    from .rt import RtSample, RtWindow, _realtime_summary
    from .rt_drift import DriftStats

    window = RtWindow(samples=[RtSample(kind="trip_updates", fetched_at=0, ok=True)] * 6)
    details: dict[str, object] = {"coverage_pct": 88.9, "vehicles_on_route_pct": 95.0}
    kinds = ("trip_updates", "vehicle_positions")
    outputs: list[str] = []
    for coverage, scheduled in ((0.889, {"t1"}), (None, set()), (None, {"t1"})):
        for plausible in (0.95, None):
            for drift in (
                DriftStats(
                    observations=9, median_seconds=42, p90_abs_seconds=90, on_time_share=0.8
                ),
                DriftStats(
                    observations=9, median_seconds=-42, p90_abs_seconds=90, on_time_share=0.8
                ),
                None,
            ):
                outputs.append(
                    _realtime_summary(
                        window, kinds, 2, details, scheduled, coverage, plausible, drift
                    )
                )
    # One configured feed and a single sample, so both singular readings are
    # reached too.
    one_sample = RtWindow(samples=[RtSample(kind="vehicle_positions", fetched_at=0, ok=True)])
    outputs.append(
        _realtime_summary(one_sample, ("vehicle_positions",), 1, details, None, None, 0.95, None)
    )
    return outputs


def _reach_sentence_outputs() -> list[str]:
    """Every reach sentence: absent for each recorded reason, then each share shape."""
    from .consequence import _REACH_ABSENCE, Reach, reach_sentence

    outputs: list[str] = []
    for reason in (*_REACH_ABSENCE, "a reason with no recorded sentence"):
        outputs.append(reach_sentence(Reach(basis="stops", basis_label="stops", reason=reason)))
    for affected, total, share in ((0, 9850, 0.0), (9850, 9850, 1.0)):
        outputs.append(
            reach_sentence(
                Reach(
                    basis="stops",
                    basis_label="stops",
                    affected=affected,
                    total=total,
                    share=share,
                )
            )
        )
    # Partial shares: under 1%, a middling share, and nearly all.
    for affected, share in ((3, 0.0003), (4925, 0.5), (9847, 0.9997)):
        outputs.append(
            reach_sentence(
                Reach(
                    basis="stops",
                    basis_label="stops",
                    affected=affected,
                    total=9850,
                    share=share,
                )
            )
        )
    return outputs


def _consequence_prose_outputs() -> list[str]:
    """Every consequence line and absence note, over known and unknown numbers."""
    from .consequence import (
        _NEED_ABSENCE,
        _RIDERSHIP_ABSENCE,
        Consequence,
        Reach,
        Ridership,
        ServedAreaNeed,
        absence_notes,
        consequence_line,
    )

    known_reach = Reach(basis="stops", basis_label="stops", affected=12, total=9850, share=0.0012)
    outputs: list[str] = []
    for ridership in (Ridership(annual_rider_trips=412_009, ntd_id="90015"), Ridership()):
        for need in (ServedAreaNeed(tier="high", scale="us_acs"), ServedAreaNeed()):
            outputs.append(
                consequence_line(
                    Consequence(
                        code="stop_too_far_from_shape",
                        reach=known_reach,
                        ridership=ridership,
                        need=need,
                    )
                )
            )
    for reason in _RIDERSHIP_ABSENCE:
        outputs.extend(
            absence_notes(
                Consequence(
                    code="c",
                    reach=known_reach,
                    ridership=Ridership(reason=reason),
                    need=ServedAreaNeed(tier="high"),
                )
            )
        )
    for reason in _NEED_ABSENCE:
        outputs.extend(
            absence_notes(
                Consequence(
                    code="c",
                    reach=known_reach,
                    ridership=Ridership(annual_rider_trips=1),
                    need=ServedAreaNeed(reason=reason),
                )
            )
        )
    return outputs


def _producers() -> tuple[Producer, ...]:
    from .consequence import _percent_phrase, absence_notes, consequence_line, reach_sentence
    from .rt import _realtime_summary

    return (
        Producer("_realtime_summary", _realtime_summary_outputs, (_realtime_summary,)),
        Producer("reach_sentence", _reach_sentence_outputs, (reach_sentence, _percent_phrase)),
        Producer(
            "consequence_prose",
            _consequence_prose_outputs,
            (consequence_line, absence_notes),
        ),
    )
