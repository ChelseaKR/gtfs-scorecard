"""Tests for the finding -> authoritative-rule mapping.

These keep the table well-formed and pinned to reality: every mapped code has a
fix page, every fix page is mapped, and every link is shaped like a real,
verified rule URL (the live resolution was verified by hand when the table was
built; see docs/decisions/0024-validator-rule-links.md). No network here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scorecard_pipeline.rule_links import (
    BEST_PRACTICE,
    BEST_PRACTICES_PAGE,
    REALTIME_REFERENCE,
    REALTIME_REFERENCE_PAGE,
    REFERENCE,
    RULE_LINKS,
    SCHEDULE_REFERENCE_PAGE,
    VALIDATOR,
    VALIDATOR_RULES_PAGE,
    rule_link_for,
    validator_rule_url,
)

_NON_VALIDATOR_BASE_BY_KIND = {
    BEST_PRACTICE: BEST_PRACTICES_PAGE,
    REFERENCE: SCHEDULE_REFERENCE_PAGE,
    REALTIME_REFERENCE: REALTIME_REFERENCE_PAGE,
}

FIXES_DIR = Path(__file__).resolve().parents[2] / "docs" / "fixes"


def _fix_page_codes() -> set[str]:
    return {p.stem for p in FIXES_DIR.glob("*.md") if p.stem != "README"}


def test_every_mapped_code_has_a_fix_page() -> None:
    missing = sorted(code for code in RULE_LINKS if not (FIXES_DIR / f"{code}.md").exists())
    assert not missing, f"RULE_LINKS references codes with no docs/fixes page: {missing}"


def test_every_fix_page_is_mapped() -> None:
    # The fix pages are exactly the findings worth linking to a rule; if a new
    # page is added without a mapping, this fails so the table can't silently rot.
    unmapped = sorted(_fix_page_codes() - set(RULE_LINKS))
    assert not unmapped, f"docs/fixes pages with no rule mapping: {unmapped}"


def test_every_authored_article_has_valid_dates() -> None:
    from scorecard_pipeline.render_site import _parse_authored_markdown

    paths = sorted(FIXES_DIR.glob("*.md"))
    fix_paths = [path for path in paths if path.stem != "README"]
    assert len(fix_paths) == 40
    for path in fix_paths:
        document = _parse_authored_markdown(path.read_text(), str(path))
        assert document.body.lstrip().startswith("# "), path

    crosswalk = FIXES_DIR.parent / "crosswalk.md"
    document = _parse_authored_markdown(crosswalk.read_text(), str(crosswalk))
    assert document.body.lstrip().startswith("# How the grade maps to the standards")


def test_validator_links_are_anchored_to_a_notice() -> None:
    for code, link in RULE_LINKS.items():
        if link.kind != VALIDATOR:
            continue
        notice = link.canonical or code
        assert link.url == validator_rule_url(notice), code
        assert link.url.startswith(f"{VALIDATOR_RULES_PAGE}#")
        assert link.url.endswith("-rule"), code


def test_scorecard_validator_codes_name_their_canonical_notice() -> None:
    # A scorecard_* code that maps to a validator notice diverges from the
    # notice name, so it must carry the canonical alias for the reader.
    for code, link in RULE_LINKS.items():
        if link.kind == VALIDATOR and code.startswith("scorecard_"):
            assert link.canonical, f"{code} maps to a validator notice but names no alias"
            assert not link.canonical.startswith("scorecard_"), code


def test_non_validator_links_point_to_gtfs_org_sections() -> None:
    for code, link in RULE_LINKS.items():
        if link.kind == VALIDATOR:
            continue
        base = _NON_VALIDATOR_BASE_BY_KIND[link.kind]
        assert link.url.startswith(f"{base}#"), code


def test_all_urls_are_https() -> None:
    for code, link in RULE_LINKS.items():
        assert link.url.startswith("https://"), code


def test_every_link_has_a_human_authority_label() -> None:
    for code, link in RULE_LINKS.items():
        assert link.authority.strip(), code


def test_fallback_builds_validator_link_for_uncurated_notice() -> None:
    # A raw validator notice with no curated fix page still resolves to its rule.
    link = rule_link_for("some_future_notice")
    assert link is not None
    assert link.kind == VALIDATOR
    assert link.url == "https://gtfs-validator.mobilitydata.org/rules.html#some_future_notice-rule"


def test_fallback_is_none_for_uncurated_scorecard_code() -> None:
    assert rule_link_for("scorecard_some_future_metric") is None


def test_fallback_returns_curated_entry_when_present() -> None:
    assert rule_link_for("expired_calendar") is RULE_LINKS["expired_calendar"]


@pytest.mark.parametrize("code", sorted(RULE_LINKS))
def test_table_entries_are_frozen_and_complete(code: str) -> None:
    link = RULE_LINKS[code]
    assert link.kind in {VALIDATOR, BEST_PRACTICE, REFERENCE, REALTIME_REFERENCE}
    assert link.url
