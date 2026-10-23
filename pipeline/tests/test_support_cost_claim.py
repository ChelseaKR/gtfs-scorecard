"""The support copy states the measured S3 cost, dated, not a stale estimate.

The public support page and its repository copy once said the core service costs
"single-digit dollars a month". Cost Explorer showed $28.35 of S3 charges in
us-west-2 for September 2026. These tests keep both copies from drifting back to
an unmeasured claim and keep the figure's parts consistent with its total.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_COPIES = (_REPO / "web" / "support" / "index.html", _REPO / "docs" / "support.md")

_TOTAL = "$28.35"
_PARTS = ("$17.26", "$8.80", "$2.29")
_STALE = re.compile(r"single[- ]digit[- ]dollars?", re.IGNORECASE)


def _text(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _stale_hits(text: str) -> list[str]:
    return _STALE.findall(text)


@pytest.mark.parametrize("path", _COPIES, ids=lambda p: p.name)
def test_copy_has_no_unmeasured_single_digit_claim(path: Path) -> None:
    assert _stale_hits(_text(path)) == []


@pytest.mark.parametrize("path", _COPIES, ids=lambda p: p.name)
def test_copy_states_the_dated_measured_figure(path: Path) -> None:
    text = _text(path)
    assert _TOTAL in text
    assert "September 2026" in text
    assert "Cost Explorer" in text
    for part in _PARTS:
        assert part in text


def test_parts_sum_to_the_total() -> None:
    amounts = [float(p.lstrip("$")) for p in _PARTS]
    assert round(sum(amounts), 2) == float(_TOTAL.lstrip("$"))


@pytest.mark.parametrize("path", _COPIES, ids=lambda p: p.name)
def test_copy_says_cause_is_unmeasured_and_states_no_total(path: Path) -> None:
    text = _text(path)
    assert "not yet measured" in text
    assert "states no total" in text


@pytest.mark.parametrize("path", _COPIES, ids=lambda p: p.name)
def test_negative_control_stale_sentence_is_caught(path: Path) -> None:
    """Sabotage the copy, assert the sabotage applied, then assert it is caught."""
    original = _text(path)
    assert _stale_hits(original) == []
    sabotaged = original.replace(_TOTAL, "single-digit dollars a month")
    assert sabotaged != original
    assert _stale_hits(sabotaged) != []
    assert _TOTAL in original
    assert _TOTAL not in sabotaged
