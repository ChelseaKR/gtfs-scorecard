"""Every surface that states the sponsor policy carries the sentences ADR 0071 records.

The disclosure rule and the conflict rules are promises to sponsors. They used to
disagree between the site and the GitHub Sponsors profile. These tests hold the
site, the repository docs and the ADR to the same sentences, and the negative
controls check that a surface that disagrees fails.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]

DISCLOSE_ON_REQUEST = "Sponsors are named on the /support/ page and in the repository if they ask to be."
ANON_COUNTED = "Anonymous sponsors are counted and their total is shown."
ALWAYS_NAMED = (
    "A sponsor that publishes a feed graded on this site, or sells GTFS products or "
    "services, is always named."
)
SHARE = (
    "The share of graded feed records that belong to a sponsor, or that a sponsor built, "
    "is published beside its name."
)
IDENTICAL = (
    "A feed a sponsor built or publishes is scored and framed identically to every other "
    "feed, by the same code and rubric."
)
TIERS = "Sponsorship is accepted only at the listed tiers."
DISPUTE = "No sponsorship is accepted while the sponsor has an open dispute about its own grade."
VENDOR = (
    "Vendors may sponsor this project; sponsors are listed on /support/ and are graded by "
    "the same rubric as every other vendor."
)

_FULL = (DISCLOSE_ON_REQUEST, ANON_COUNTED, ALWAYS_NAMED, SHARE, IDENTICAL, TIERS, DISPUTE, VENDOR)

SURFACES: dict[str, tuple[str, ...]] = {
    "web/support/index.html": _FULL,
    "docs/support.md": _FULL,
    "docs/decisions/0071-sponsors-whose-feeds-are-graded.md": _FULL,
    "SUPPORT.md": (DISCLOSE_ON_REQUEST, ANON_COUNTED, ALWAYS_NAMED, IDENTICAL),
    "web/about/index.html": (IDENTICAL,),
    "web/procurement/index.html": (VENDOR,),
}

_STALE = (
    "Sponsors are disclosed on this page and in the repository, always",
    "The first ones will be listed here",
    "anonymous is the default",
)


def _norm(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text)


def _read(rel: str) -> str:
    return _norm((_REPO / rel).read_text(encoding="utf-8"))


def missing(text: str, sentences: tuple[str, ...]) -> list[str]:
    return [s for s in sentences if s not in text]


@pytest.mark.parametrize("rel", SURFACES)
def test_surface_carries_its_sentences(rel: str) -> None:
    assert missing(_read(rel), SURFACES[rel]) == []


@pytest.mark.parametrize("rel", SURFACES)
def test_surface_has_no_stale_disclosure_claim(rel: str) -> None:
    text = _read(rel)
    if rel.endswith("0071-sponsors-whose-feeds-are-graded.md"):
        pytest.skip("the ADR quotes the superseded text on purpose")
    assert [s for s in _STALE if s in text] == []


def test_support_page_links_the_adr() -> None:
    raw = (_REPO / "web/support/index.html").read_text(encoding="utf-8")
    assert "0071-sponsors-whose-feeds-are-graded.md" in raw
    assert (_REPO / "docs/decisions/0071-sponsors-whose-feeds-are-graded.md").is_file()


# Negative controls. Each asserts the sabotage changed the text, so a no-op reads as a failure.


@pytest.mark.parametrize("rel", SURFACES)
def test_control_dropping_a_sentence_fails(rel: str) -> None:
    text = _read(rel)
    for sentence in SURFACES[rel]:
        broken = text.replace(sentence, "")
        assert broken != text, "sabotage did not apply"
        assert missing(broken, SURFACES[rel]) == [sentence]


@pytest.mark.parametrize("rel", ["web/support/index.html", "docs/support.md", "SUPPORT.md"])
def test_control_a_disagreeing_disclosure_default_fails(rel: str) -> None:
    text = _read(rel)
    broken = text.replace("is always named", "is named")
    assert broken != text, "sabotage did not apply"
    assert ALWAYS_NAMED in missing(broken, SURFACES[rel]) or missing(broken, SURFACES[rel])


def test_control_stale_always_claim_is_detected() -> None:
    text = _read("web/support/index.html") + " Sponsors are disclosed on this page and in the repository, always."
    assert [s for s in _STALE if s in text]
