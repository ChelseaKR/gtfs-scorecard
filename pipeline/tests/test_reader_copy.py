"""Tests for the reader-copy inventory and the plain-language gate over it.

The point of the inventory is that the readability gate cannot pass a string it
never looked at. So most of these tests are about the refusal path: a
``Finding(...)`` site whose copy cannot be read has to raise, and the shapes
that are allowed to be deferred have to be exactly the two documented ones and
nothing that merely resembles them.

The last test runs the real gate over the real inventory, so a copy regression
fails the suite as well as `make verify`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.notices import TRANSLATIONS
from scorecard_pipeline.reader_copy import (
    COPY_FIELDS,
    MAX_VARIANTS,
    RUNTIME_VALUE,
    UnreadableCopy,
    authored_finding_copy,
    curated_copy,
    reader_copy,
)

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "pipeline" / "scripts" / "check_readability.py"

PREAMBLE = "from scorecard_pipeline.metrics import Finding\n\n\n"


def _load_gate() -> Any:
    spec = importlib.util.spec_from_file_location("check_readability", GATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _package(tmp_path: Path, body: str, name: str = "sample.py") -> Path:
    """Write one synthetic module into an otherwise empty package directory."""
    pkg = tmp_path / "pkg"
    pkg.mkdir(exist_ok=True)
    (pkg / name).write_text(PREAMBLE + body, encoding="utf-8")
    return pkg


def _finding(**fields: str) -> str:
    """Source text for one Finding(...) call with the given field expressions."""
    defaults = {
        "code": '"sample_code"',
        "severity": '"INFO"',
        "count": "1",
        "what": '"What is wrong."',
        "why": '"Why a rider cares."',
        "fix": '"What to do next."',
        "effort": '"One field."',
        "deduction": "0.0",
    }
    defaults.update(fields)
    args = ", ".join(f"{key}={value}" for key, value in defaults.items())
    return f"def build():\n    return Finding({args})\n"


def _texts(pkg: Path) -> dict[str, str]:
    strings, _ = authored_finding_copy(pkg)
    return {s.label: s.text for s in strings}


def test_real_package_is_fully_accounted_for() -> None:
    """Every Finding() site in the shipped package reads, defers, or raises."""
    strings, deferred = reader_copy()
    authored = [s for s in strings if s.provenance == "authored"]
    curated = [s for s in strings if s.provenance == "curated"]
    assert authored, "the authored family must not be empty"
    assert len(curated) == len(TRANSLATIONS) * len(COPY_FIELDS)
    # Both deferral reasons are in use, and each one names why.
    assert {site.provenance for site in deferred} == {"curated_table", "republished"}
    assert all(site.reason for site in deferred)


def test_authored_family_covers_the_scoring_modules() -> None:
    """The families the gate used to miss are the ones now measured."""
    strings, _ = authored_finding_copy()
    modules = {s.origin.split(":")[0] for s in strings}
    for expected in (
        "accessibility.py",
        "completeness.py",
        "fares.py",
        "flex.py",
        "metrics.py",
        "pathways.py",
        "routability.py",
        "rt.py",
    ):
        assert expected in modules


def test_curated_copy_matches_the_translation_table() -> None:
    strings = curated_copy()
    sample = strings[0]
    assert getattr(TRANSLATIONS[sample.label.rsplit(".", 1)[0]], sample.field) == sample.text
    assert all(s.provenance == "curated" for s in strings)


def test_plain_literal_is_measured(tmp_path: Path) -> None:
    pkg = _package(tmp_path, _finding())
    assert _texts(pkg)["sample_code.what"] == "What is wrong."


def test_fstring_placeholder_becomes_a_runtime_stand_in(tmp_path: Path) -> None:
    pkg = _package(tmp_path, _finding(what='f"{count} of {total} stops."'))
    assert _texts(pkg)["sample_code.what"] == f"{RUNTIME_VALUE} of {RUNTIME_VALUE} stops."


def test_concatenated_literals_are_joined(tmp_path: Path) -> None:
    pkg = _package(tmp_path, _finding(what='"Dates are missing" + " (the file is absent)."'))
    assert _texts(pkg)["sample_code.what"] == "Dates are missing (the file is absent)."


def test_conditional_copy_is_measured_every_way_it_can_read(tmp_path: Path) -> None:
    """A sentence that reads two ways is two strings, not one lucky one."""
    pkg = _package(tmp_path, _finding(fix='"No action needed." if ok else "Add a level."'))
    texts = _texts(pkg)
    assert texts["sample_code.fix#1"] == "No action needed."
    assert texts["sample_code.fix#2"] == "Add a level."


def test_name_assigned_once_in_the_function_resolves(tmp_path: Path) -> None:
    body = (
        "def build():\n"
        '    detail = "It includes an elevator." if ok else "No elevator."\n'
        '    return Finding(code="sample_code", severity="INFO", count=1,\n'
        '                   what=f"Paths are mapped. {detail}", why="Why.", fix="Fix.",\n'
        '                   effort="None.", deduction=0.0)\n'
    )
    pkg = _package(tmp_path, body)
    texts = _texts(pkg)
    assert texts["sample_code.what#1"] == "Paths are mapped. It includes an elevator."
    assert texts["sample_code.what#2"] == "Paths are mapped. No elevator."


def test_name_assigned_twice_is_ambiguous_and_refused(tmp_path: Path) -> None:
    """Two assignments means the inventory cannot know which sentence ships."""
    body = (
        "def build():\n"
        '    detail = "First."\n'
        '    detail = "Second."\n'
        '    return Finding(code="sample_code", severity="INFO", count=1,\n'
        '                   what=detail, why="Why.", fix="Fix.",\n'
        '                   effort="None.", deduction=0.0)\n'
    )
    pkg = _package(tmp_path, body)
    with pytest.raises(UnreadableCopy, match="cannot read what="):
        authored_finding_copy(pkg)


def test_unreadable_expression_raises_naming_file_line_and_field(tmp_path: Path) -> None:
    pkg = _package(tmp_path, _finding(why="build_the_sentence()"))
    with pytest.raises(UnreadableCopy) as excinfo:
        authored_finding_copy(pkg)
    message = str(excinfo.value)
    assert "sample.py:" in message
    assert "cannot read why=" in message


def test_absent_field_raises_rather_than_passing_vacuously(tmp_path: Path) -> None:
    body = (
        "def build():\n"
        '    return Finding(code="sample_code", severity="INFO", count=1,\n'
        '                   why="Why.", fix="Fix.", effort="None.", deduction=0.0)\n'
    )
    pkg = _package(tmp_path, body)
    with pytest.raises(UnreadableCopy, match="has no what="):
        authored_finding_copy(pkg)


def test_translation_field_is_deferred_with_its_reason(tmp_path: Path) -> None:
    pkg = _package(tmp_path, _finding(what="t.what", why="t.why", fix="t.fix"))
    strings, deferred = authored_finding_copy(pkg)
    assert not strings
    assert {site.field for site in deferred} == set(COPY_FIELDS)
    assert all(site.provenance == "curated_table" for site in deferred)
    assert all("notices.translate" in site.reason for site in deferred)


def test_attribute_of_another_name_is_not_a_deferral_loophole(tmp_path: Path) -> None:
    """`what=t.summary` is not curated wording, so it must not slip through."""
    pkg = _package(tmp_path, _finding(what="t.summary"))
    with pytest.raises(UnreadableCopy, match="cannot read what="):
        authored_finding_copy(pkg)


@pytest.mark.parametrize("expression", ['d["what"]', 'd.get("what", "")'])
def test_republished_copy_is_deferred(tmp_path: Path, expression: str) -> None:
    pkg = _package(tmp_path, _finding(what=expression))
    strings, deferred = authored_finding_copy(pkg)
    assert [s.label for s in strings] == ["sample_code.why", "sample_code.fix"]
    assert [site.provenance for site in deferred] == ["republished"]


@pytest.mark.parametrize("expression", ['d["summary"]', 'd.get("summary", "")', "d.get()"])
def test_republication_of_a_different_key_is_refused(tmp_path: Path, expression: str) -> None:
    """Reading back some other field is not the documented replay shape."""
    pkg = _package(tmp_path, _finding(what=expression))
    with pytest.raises(UnreadableCopy, match="cannot read what="):
        authored_finding_copy(pkg)


def test_too_many_readings_is_refused_rather_than_expanded(tmp_path: Path) -> None:
    """A site with more readings than MAX_VARIANTS fails loudly, not silently."""
    branch = '("a" if p else "b")'
    expression = " + ".join([branch] * 4)
    assert MAX_VARIANTS < 2**4
    pkg = _package(tmp_path, _finding(what=expression))
    with pytest.raises(UnreadableCopy, match="cannot read what="):
        authored_finding_copy(pkg)


def test_a_non_string_constant_is_refused(tmp_path: Path) -> None:
    pkg = _package(tmp_path, _finding(fix="None"))
    with pytest.raises(UnreadableCopy, match="cannot read fix="):
        authored_finding_copy(pkg)


def test_finding_built_at_module_level_uses_module_scope(tmp_path: Path) -> None:
    body = (
        'HEADLINE = "Service data ended."\n'
        'SAMPLE = Finding(code="sample_code", severity="INFO", count=1,\n'
        '                 what=HEADLINE, why="Why.", fix="Fix.",\n'
        '                 effort="None.", deduction=0.0)\n'
    )
    pkg = _package(tmp_path, body)
    assert _texts(pkg)["sample_code.what"] == "Service data ended."


def test_site_without_a_literal_code_is_labelled_by_module_and_line(tmp_path: Path) -> None:
    pkg = _package(tmp_path, _finding(code="group.code"))
    labels = set(_texts(pkg))
    assert any(label.startswith("sample.py:") for label in labels)


def test_the_gate_measures_the_whole_inventory_and_passes() -> None:
    """The published copy clears the bars the gate exists to enforce."""
    gate = _load_gate()
    strings, _ = reader_copy()
    failures = [f for s in strings for f in gate.check_text(s.label, s.text)]
    assert not failures, "\n".join(failures)


def test_the_gate_still_fails_a_string_that_misses_a_bar() -> None:
    """Proof the bars bite: a long, dense sentence is reported, not tolerated."""
    gate = _load_gate()
    dense = (
        "Notwithstanding the aforementioned considerations, the comprehensive "
        "reconciliation of interdependent scheduling artifacts necessitates "
        "substantial administrative intervention prior to subsequent publication "
        "of the operational calendar."
    )
    assert len(gate.check_text("synthetic", dense)) == 2
