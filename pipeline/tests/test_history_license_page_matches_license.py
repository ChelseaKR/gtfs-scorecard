"""The history page's license summary must not claim to be the license itself.

ADR 0063 and ``docs/history-tables.md`` record the sold license as
``LICENSE_TEXT`` (the file that ships in the zip as ``LICENSE.md``). The
landing page carries a shorter, plain-language summary of it. The page used to
say the summary was "the same words" as ``LICENSE.md``; it never was (it drops
"in whole or in substantial part" and rephrases every clause), and the existing
test only held the doc to the module. These tests hold the page to the module:
the summary has the same clauses in the same order, and the page may claim
"the same words" only if each clause really is verbatim.
"""

from __future__ import annotations

import re
from pathlib import Path

from scorecard_pipeline.history_export import LICENSE_TEXT

_PAGE = Path(__file__).resolve().parents[2] / "web" / "data" / "history" / "index.html"


def _normalize(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _license_section(page: str) -> str:
    match = re.search(r'<section[^>]*id="license">(.*?)</section>', page, re.S)
    assert match, "the history page has no #license section"
    return match.group(1)


def _page_clause_headings(page: str) -> list[str]:
    section = _license_section(page)
    return [h.rstrip(".") for h in re.findall(r"<li><strong>(.*?)</strong>", section, re.S)]


def _page_clause_bodies(page: str) -> list[str]:
    section = _license_section(page)
    return [_normalize(b) for b in re.findall(r"<li>(.*?)</li>", section, re.S)]


def _license_clauses(text: str) -> list[tuple[str, str]]:
    flat = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?:^| )(\d+)\. ", flat)[1:]
    clauses = []
    for i in range(0, len(parts), 2):
        body = parts[i + 1].strip()
        heading, _, rest = body.partition(". ")
        clauses.append((heading, rest.strip()))
    return clauses


def _claims_verbatim(page: str) -> bool:
    match = re.search(r"<code>LICENSE\.md</code></strong>(.*?)</li>", page, re.S)
    assert match, "the page no longer describes LICENSE.md in its list of files"
    return "same words" in _normalize(match.group(1))


def _summary_is_verbatim(page: str, license_text: str) -> bool:
    bodies = _page_clause_bodies(page)
    clauses = _license_clauses(license_text)
    if len(bodies) != len(clauses):
        return False
    return all(rest in _normalize(body) for body, (_, rest) in zip(bodies, clauses, strict=True))


def test_the_page_summarizes_the_same_clauses_in_the_same_order() -> None:
    page = _PAGE.read_text()
    headings = [h for h, _ in _license_clauses(LICENSE_TEXT)]
    assert len(headings) == 7
    assert _page_clause_headings(page) == headings


def test_the_page_claims_same_words_only_if_the_clauses_are_verbatim() -> None:
    page = _PAGE.read_text()
    if _claims_verbatim(page):
        assert _summary_is_verbatim(page, LICENSE_TEXT), (
            "the page says LICENSE.md is 'the same words' as its license section, "
            "but the clauses differ; say 'summarizes' or make them verbatim"
        )


def test_the_governing_text_is_named_on_the_page() -> None:
    page = _PAGE.read_text()
    match = re.search(r"<code>LICENSE\.md</code></strong>(.*?)</li>", page, re.S)
    assert match
    assert "governs" in _normalize(match.group(1))


def test_negative_control_the_old_claim_is_caught() -> None:
    page = _PAGE.read_text()
    old = (
        "the terms the tables are sold under, the\n        same words as "
        '<a href="#license">the license section</a> on this page.</li>'
    )
    # Rebuild the pre-fix sentence in place of the current one.
    current = re.search(r"(<code>LICENSE\.md</code></strong>)(.*?)(</li>)", page, re.S)
    assert current
    sabotaged = page.replace(current.group(2), ": " + old[: -len("</li>")], 1)
    assert sabotaged != page, "the sabotage did not apply"
    assert _claims_verbatim(sabotaged), "the control must trigger the claim"
    assert not _summary_is_verbatim(sabotaged, LICENSE_TEXT), "the control must be detectable"


def test_negative_control_a_reordered_page_is_caught() -> None:
    page = _PAGE.read_text()
    first = "<li><strong>One organization.</strong>"
    second = "<li><strong>No redistribution of the package.</strong>"
    assert first in page and second in page
    swapped = page.replace(first, "@@A").replace(second, first).replace("@@A", second)
    assert swapped != page, "the sabotage did not apply"
    headings = [h for h, _ in _license_clauses(LICENSE_TEXT)]
    assert _page_clause_headings(swapped) != headings


def test_negative_control_a_verbatim_summary_would_pass() -> None:
    clauses = _license_clauses(LICENSE_TEXT)
    items = "".join(f"<li><strong>{h}.</strong> {rest}</li>" for h, rest in clauses)
    page = f'<section id="license"><ol>{items}</ol></section>'
    assert _summary_is_verbatim(page, LICENSE_TEXT)
    tampered = page.replace("in whole or in substantial part, ", "")
    assert tampered != page, "the sabotage did not apply"
    assert not _summary_is_verbatim(tampered, LICENSE_TEXT)
