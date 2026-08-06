"""Tests for the corpus-figure gate (FIX-15) and its ungated-figure sweep.

The registered-rule half of `check_doc_stats.py` only checks claims somebody
remembered to register. The sweep is the half that catches the ones nobody did,
so these tests are mostly about proving it actually flags an unregistered figure
rather than passing vacuously.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "pipeline" / "scripts" / "check_doc_stats.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_doc_stats", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


doc_stats = _load()


# --- the sweep finds what the rule list does not ---------------------------


def test_sweep_flags_a_corpus_figure_no_rule_covers() -> None:
    # The CLAUDE.md failure in one line: a real-looking sentence, a real
    # denominator, and nothing anywhere that would notice it going stale.
    found = doc_stats.ungated_figures(
        "docs/not-a-real-doc.md", "The registry tracks 1,500 feed records today.\n"
    )
    assert len(found) == 1
    assert "1,500 feed records" in found[0]
    assert "docs/not-a-real-doc.md:1" in found[0]
    # The message has to say what to do, or it just blocks the commit.
    assert "RULES" in found[0] and "POINT_IN_TIME" in found[0]


def test_sweep_reports_the_line_the_figure_is_on() -> None:
    text = "intro\n\nfiller\n\nAbout 2,400 configured feeds are tracked.\n"
    (finding,) = doc_stats.ungated_figures("docs/not-a-real-doc.md", text)
    assert ":5:" in finding


def test_sweep_accepts_a_figure_an_existing_rule_checks() -> None:
    # README's registry sentence is registered, so the sweep must stay quiet on
    # it; otherwise every gated figure would have to be declared twice.
    readme = (ROOT / "README.md").read_text()
    assert "curated" in readme
    assert doc_stats.ungated_figures("README.md", readme) == []


def test_sweep_accepts_a_figure_declared_point_in_time() -> None:
    expansion = (ROOT / "docs" / "global-expansion.md").read_text()
    assert "1,296 feed records" in expansion
    assert doc_stats.ungated_figures("docs/global-expansion.md", expansion) == []


# --- and does not cry wolf -------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "See https://example.org/data/2500-feeds for the list.\n",
        "Read `1500 feeds` from the fixture.\n",
        "The [catalog](https://x.test/1200-agencies) is upstream.\n",
        '<a href="/reports/3000-feeds">report</a>\n',
    ],
)
def test_sweep_ignores_figures_inside_identifiers(text: str) -> None:
    assert doc_stats.ungated_figures("docs/not-a-real-doc.md", text) == []


def test_sweep_ignores_years_and_small_numbers() -> None:
    assert doc_stats.ungated_figures("docs/x.md", "In 2026 feeds improved.\n") == []
    # 26 countries, 12 shards, 3 fixes: real numbers, not corpus populations.
    assert doc_stats.ungated_figures("docs/x.md", "Across 26 agencies this held.\n") == []


# --- the declarations stay honest ------------------------------------------


def test_every_point_in_time_declaration_still_matches() -> None:
    # A declaration that has stopped matching is an exemption with nothing under
    # it, which is exactly where a drifting figure could hide.
    import re

    for rel_path, pattern, reason in doc_stats.POINT_IN_TIME:
        text = (ROOT / rel_path).read_text()
        assert re.search(pattern, text), f"{rel_path}: {pattern!r} ({reason}) matches nothing"


def test_point_in_time_declarations_each_state_a_reason() -> None:
    for rel_path, _pattern, reason in doc_stats.POINT_IN_TIME:
        assert reason.strip(), f"{rel_path}: a point-in-time exemption must say why"


# --- scope ------------------------------------------------------------------


def test_sweep_covers_the_documents_that_carry_public_corpus_figures() -> None:
    swept = set(doc_stats.swept_docs())
    for rel_path in (
        "README.md",
        "CLAUDE.md",
        "docs/roadmap.md",
        "docs/product-roadmap.md",
        "docs/feeds.md",
        "docs/support.md",
        "web/support/index.html",
    ):
        assert rel_path in swept, rel_path


def test_sweep_never_reads_private_working_notes() -> None:
    # *.local.md is gitignored private context (CLAUDE.local.md and friends).
    assert not [rel for rel in doc_stats.swept_docs() if rel.endswith(".local.md")]


def test_sweep_skips_the_dated_record_documents() -> None:
    swept = set(doc_stats.swept_docs())
    assert "CHANGELOG.md" not in swept
    # Subdirectories of docs/ are dated records; refreshing them would falsify
    # the history they exist to hold.
    assert not [rel for rel in swept if rel.startswith("docs/decisions/")]
    assert not [rel for rel in swept if rel.startswith("docs/ideation/")]


def test_optional_rules_name_only_files_that_may_be_absent() -> None:
    # AGENTS.md is excluded from the repo, so it cannot be a required rule --
    # that is the whole reason OPTIONAL_RULES exists. Anything tracked belongs
    # in RULES, where a missing file is a failure rather than a skip.
    for rel_path, _pattern, _denominator, _mode in doc_stats.OPTIONAL_RULES:
        exclude = (ROOT / ".git" / "info" / "exclude").read_text()
        assert f"/{rel_path}" in exclude, f"{rel_path} is tracked; use RULES"
