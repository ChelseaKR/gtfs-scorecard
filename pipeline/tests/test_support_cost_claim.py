"""The support copy states the measured S3 cost, dated, not a stale estimate.

The public support page and its repository copy once said the core service costs
"single-digit dollars a month", then quoted the September 2026 S3 charge after
the runs that caused most of it had been changed. Cost Explorer showed $43.66 of
S3 charges in us-west-2 for October 2026, $29.88 of it data transfer out, and a
rate of about $9 to $10.50 a month over November 1 to 5, 2026. These tests keep
both copies from drifting back to an unmeasured claim or to the September
figure, and keep the five-day rate from reading as a month's bill.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_COPIES = (_REPO / "web" / "support" / "index.html", _REPO / "docs" / "support.md")

_RATE = "about $9 to $10.50 a month"
_RATE_WINDOW = "November 1 to 5, 2026"
_LAST_FULL_MONTH = ("October 2026", "$43.66", "$29.88")
_SUPERSEDED = ("$28.35", "$17.26", "$8.80", "$2.29")
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
    assert _RATE in text
    assert _RATE_WINDOW in text
    assert "Cost Explorer" in text
    for part in _LAST_FULL_MONTH:
        assert part in text


@pytest.mark.parametrize("path", _COPIES, ids=lambda p: p.name)
def test_copy_does_not_quote_the_superseded_september_figure(path: Path) -> None:
    text = _text(path)
    for figure in _SUPERSEDED:
        assert figure not in text


@pytest.mark.parametrize("path", _COPIES, ids=lambda p: p.name)
def test_copy_says_the_rate_is_not_a_bill_and_states_no_total(path: Path) -> None:
    text = _text(path)
    assert "not a month's bill" in text
    assert "states no total" in text


@pytest.mark.parametrize("path", _COPIES, ids=lambda p: p.name)
def test_negative_control_stale_sentence_is_caught(path: Path) -> None:
    """Sabotage the copy, assert the sabotage applied, then assert it is caught."""
    original = _text(path)
    assert _stale_hits(original) == []
    sabotaged = original.replace(_RATE, "single-digit dollars a month")
    assert sabotaged != original
    assert _stale_hits(sabotaged) != []
    assert _RATE in original
    assert _RATE not in sabotaged
