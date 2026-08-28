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

from scorecard_pipeline import reader_copy as reader_copy_module
from scorecard_pipeline.notices import TRANSLATIONS
from scorecard_pipeline.reader_copy import (
    COPY_FIELDS,
    MAX_VARIANTS,
    RUNTIME_VALUE,
    Producer,
    UnmeasuredFragment,
    UnreadableCopy,
    assembled_copy,
    authored_finding_copy,
    authored_fragments,
    curated_copy,
    producer_labels,
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
    assert [s for s in strings if s.provenance == "assembled"], "producers must contribute"
    # Every deferral reason is in use, and each one names why.
    assert {site.provenance for site in deferred} == {
        "curated_table",
        "republished",
        "produced",
    }
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


def test_every_branch_of_a_name_is_a_reading(tmp_path: Path) -> None:
    """A sentence chosen by an if/elif chain is measured once per branch.

    ADR 0048 refused a name assigned more than once. That refused the category
    summaries, which are chosen exactly that way, so ADR 0049 reads all of them
    instead. More coverage, not less: an unreadable assignment still refuses.
    """
    body = (
        "def build():\n"
        '    detail = "First."\n'
        "    if x:\n"
        '        detail = "Second."\n'
        '    return Finding(code="sample_code", severity="INFO", count=1,\n'
        '                   what=detail, why="Why.", fix="Fix.",\n'
        '                   effort="None.", deduction=0.0)\n'
    )
    pkg = _package(tmp_path, body)
    texts = _texts(pkg)
    assert texts["sample_code.what#1"] == "First."
    assert texts["sample_code.what#2"] == "Second."


def test_one_unreadable_branch_refuses_the_whole_name(tmp_path: Path) -> None:
    """A name is only as readable as its least readable assignment."""
    body = (
        "def build():\n"
        '    detail = "First."\n'
        "    if x:\n"
        "        detail = build_it()\n"
        '    return Finding(code="sample_code", severity="INFO", count=1,\n'
        '                   what=detail, why="Why.", fix="Fix.",\n'
        '                   effort="None.", deduction=0.0)\n'
    )
    pkg = _package(tmp_path, body)
    with pytest.raises(UnreadableCopy, match="cannot read what="):
        authored_finding_copy(pkg)


def test_a_name_bound_to_itself_refuses_rather_than_recursing(tmp_path: Path) -> None:
    body = (
        "def build():\n"
        '    detail = "First."\n'
        "    detail = detail\n"
        '    return Finding(code="sample_code", severity="INFO", count=1,\n'
        '                   what=detail, why="Why.", fix="Fix.",\n'
        '                   effort="None.", deduction=0.0)\n'
    )
    pkg = _package(tmp_path, body)
    with pytest.raises(UnreadableCopy, match="cannot read what="):
        authored_finding_copy(pkg)


def test_an_assignment_inside_a_nested_function_stays_in_its_own_scope(
    tmp_path: Path,
) -> None:
    """A helper's local must not become a reading of the outer sentence."""
    body = (
        "def build():\n"
        '    detail = "Outer."\n'
        "    def helper():\n"
        '        detail = "Inner."\n'
        "        return detail\n"
        '    return Finding(code="sample_code", severity="INFO", count=1,\n'
        '                   what=detail, why="Why.", fix="Fix.",\n'
        '                   effort="None.", deduction=0.0)\n'
    )
    pkg = _package(tmp_path, body)
    assert _texts(pkg)["sample_code.what"] == "Outer."


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


# --- copy assembled at run time (ADR 0049) ------------------------------------


def test_producers_cover_every_registered_assembler() -> None:
    """Each producer emits at least one sentence, and every fragment is reached."""
    strings = assembled_copy()
    labels = {s.label.split("#")[0] for s in strings}
    assert labels == producer_labels()
    assert all(s.provenance == "assembled" for s in strings)


def test_producer_labels_match_the_registry() -> None:
    assert "_realtime_summary" in producer_labels()
    assert "reach_sentence" in producer_labels()


def test_authored_fragments_reads_phrases_and_conditional_words() -> None:
    def sample(late: bool, count: int) -> str:
        """A docstring, which is not reader copy."""
        kind = "trip_updates"
        assert kind == "trip_updates"
        return f"Predictions ran {count}s {'behind' if late else 'ahead of'} schedule."

    fragments = authored_fragments(sample)
    assert "Predictions ran " in fragments
    assert "behind" in fragments
    assert "ahead of" in fragments
    # A docstring and a bare identifier are not prose.
    assert "A docstring, which is not reader copy." not in fragments
    assert "trip_updates" not in fragments


def test_an_unreached_fragment_raises_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The producer's input set cannot quietly fall behind its own wording."""

    def only_one_branch() -> str:
        return "The measured branch."

    def both_branches(second: bool) -> str:
        return "The unreached branch." if second else "The measured branch."

    producer = Producer("sample", lambda: [only_one_branch()], (both_branches,))
    monkeypatch.setattr(reader_copy_module, "_producers", lambda: (producer,))
    with pytest.raises(UnmeasuredFragment) as excinfo:
        assembled_copy()
    assert "The unreached branch." in str(excinfo.value)
    assert "both_branches" in str(excinfo.value)


def test_run_time_numbers_do_not_split_one_sentence_into_many(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two outputs differing only in counts are one measured sentence."""

    def sentence(n: int) -> str:
        return f"Sampled {n} times."

    producer = Producer("sample", lambda: [sentence(3), sentence(41)], (sentence,))
    monkeypatch.setattr(reader_copy_module, "_producers", lambda: (producer,))
    strings = assembled_copy()
    assert [s.text for s in strings] == [f"Sampled {RUNTIME_VALUE} times."]


def test_a_category_summary_from_an_unregistered_call_is_refused(tmp_path: Path) -> None:
    """Only a registered producer accounts for an assembled summary."""
    body = (
        "def build():\n"
        '    return CategoryResult(name="realtime", score=1.0,\n'
        "                          summary=some_other_builder(), findings=[])\n"
    )
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "sample.py").write_text(
        "from scorecard_pipeline.metrics import CategoryResult\n\n\n" + body, encoding="utf-8"
    )
    with pytest.raises(UnreadableCopy, match="cannot read summary="):
        authored_finding_copy(pkg)


def test_a_category_summary_from_a_registered_producer_is_deferred(tmp_path: Path) -> None:
    body = (
        "def build():\n"
        '    return CategoryResult(name="realtime", score=1.0,\n'
        "                          summary=_realtime_summary(), findings=[])\n"
    )
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "sample.py").write_text(
        "from scorecard_pipeline.metrics import CategoryResult\n\n\n" + body, encoding="utf-8"
    )
    strings, deferred = authored_finding_copy(pkg)
    assert not strings
    assert [site.provenance for site in deferred] == ["produced"]
    assert "_realtime_summary" in deferred[0].reason
