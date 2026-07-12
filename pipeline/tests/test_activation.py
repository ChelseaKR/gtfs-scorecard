"""Safety tests for bounded manual agency activation selections."""

from __future__ import annotations

import pytest

from scorecard_pipeline.activation import ActivationTargetError, parse_activation_targets

KNOWN = {"agency-one", "agency_two", "third"}


def test_accepts_comma_newline_and_whitespace_separators_in_order() -> None:
    assert parse_activation_targets("agency-one, agency_two\n\tthird", KNOWN) == [
        "agency-one",
        "agency_two",
        "third",
    ]


@pytest.mark.parametrize("raw", ["", "  \n,\t, "])
def test_rejects_empty_selection(raw: str) -> None:
    with pytest.raises(ActivationTargetError, match="at least one"):
        parse_activation_targets(raw, KNOWN)


def test_rejects_unknown_id() -> None:
    with pytest.raises(ActivationTargetError, match=r"unknown agency.*missing"):
        parse_activation_targets("agency-one missing", KNOWN)


@pytest.mark.parametrize(
    "raw", ["Agency-One", "agency/one", "agency.one", "agenc" + chr(0x0443) + "-one"]
)
def test_rejects_malformed_or_confusable_id(raw: str) -> None:
    with pytest.raises(ActivationTargetError, match="malformed agency"):
        parse_activation_targets(raw, KNOWN)


def test_rejects_exact_duplicate() -> None:
    with pytest.raises(ActivationTargetError, match="duplicate agency"):
        parse_activation_targets("agency-one agency-one", KNOWN)


def test_rejects_duplicate_after_unicode_and_case_normalization() -> None:
    with pytest.raises(ActivationTargetError, match="after normalization"):
        parse_activation_targets("agency-one AGENCY-ONE", KNOWN)


def test_rejects_more_than_twenty_five_targets() -> None:
    ids = {f"agency-{number}" for number in range(26)}
    with pytest.raises(ActivationTargetError, match="at most 25"):
        parse_activation_targets(" ".join(sorted(ids)), ids)


def test_accepts_exactly_twenty_five_targets() -> None:
    ids = {f"agency-{number}" for number in range(25)}
    assert len(parse_activation_targets(" ".join(sorted(ids)), ids)) == 25
