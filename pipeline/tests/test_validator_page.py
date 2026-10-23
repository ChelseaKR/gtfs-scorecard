"""The /gtfs-validator/ explainer page (docs/gtfs-validator.md).

The page exists to answer "gtfs validator" / "gtfs feed validator" searches
honestly, so these tests pin four things: it renders to the SEO contract, it is
in the sitemap with a date taken from the document (never the clock), nothing
orphans it, and every claim on it is backed by a source already in the repo.
Each guard carries a negative control that asserts its sabotage applied, so a
control that silently no-ops cannot read as a pass.
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_DOC = _REPO / "docs" / "gtfs-validator.md"
_FIXTURE = Path(__file__).parent / "fixtures" / "golden_site"
_URL = "https://gtfsscorecard.org/gtfs-validator/"
_SEO = json.loads((_REPO / "site-seo.json").read_text())

#: (phrase on the page, repo source file, phrase in that source). A page phrase
#: with no matching source phrase is a claim the repo does not back.
_CLAIMS: list[tuple[str, str, str]] = [
    (
        "not an official compliance determination",
        "web/about/index.html",
        "data-quality lens, not an official compliance determination",
    ),
    (
        "scores on top of that validator rather than re-validating feeds",
        "web/about/index.html",
        "scores on top of the canonical",
    ),
    (
        "scores on top of that validator rather than re-validating feeds",
        "web/about/index.html",
        "rather than re-validating feeds",
    ),
    ("most common failure", "web/about/index.html", "most common failure is quiet"),
    (
        "The validator owns the specification and best-practice notices",
        "docs/rubric.md",
        "The validator owns specification and best-practice notices",
    ),
    ("The scorecard reads those notice codes", "docs/rubric.md", "consumes those notice codes"),
    (
        "links users back to the validator's own rule documentation",
        "docs/rubric.md",
        "links users back to\ntheir canonical rule documentation",
    ),
    (
        "five questions: required files, expiry, wheelchair fields, fares, and stop names",
        "web/check/index.html",
        "required files, expiry, wheelchair fields, fares, and stop names",
    ),
    ("nothing is uploaded", "web/check/index.html", "nothing is uploaded"),
    (
        "This is a preview, not the full validation",
        "web/check/index.html",
        "A preview, not the full validation",
    ),
    (
        "Hosted instant scoring is not enabled",
        "pipeline/src/scorecard_pipeline/pages_tools.py",
        "hosted instant scoring is not enabled",
    ),
    (
        "runs the MobilityData validator, and returns the grade and top fixes as a comment",
        "web/try.html",
        "runs the MobilityData validator, and returns the grade and top fixes as a comment",
    ),
    ("it needs Java 17 and uv", "web/try.html", "It needs Java 17 and uv"),
    (
        "fail a build when a feed drops below a grade",
        "web/try.html",
        "fail a CI build when a feed drops below a grade",
    ),
    ("checked daily", "web/index.html", "Public feeds checked daily"),
    (
        "A missing realtime feed does not lower the grade",
        "web/index.html",
        "A missing realtime feed does not lower the grade",
    ),
    (
        "Letter grades are A at 90 and above, B at 80, C at 70, D at 60, and F below 60",
        "docs/rubric.md",
        "A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F below",
    ),
    ("Correctness (35%)", "docs/rubric.md", "| Correctness | 35% |"),
    ("Freshness (20%)", "docs/rubric.md", "| Freshness | 20% |"),
    (
        "Rider experience completeness (25%)",
        "docs/rubric.md",
        "| Rider experience completeness | 25% |",
    ),
    ("Realtime quality (20%)", "docs/rubric.md", "| Realtime quality | 20% |"),
    ("12 for an error", "docs/rubric.md", "| ERROR | 12 |"),
    ("4 for a warning", "docs/rubric.md", "| WARNING | 4 |"),
    ("0.5 for an info", "docs/rubric.md", "| INFO | 0.5 |"),
    (
        "Five hundred instances of one warning is one fix",
        "docs/rubric.md",
        "Five hundred\ninstances of one warning is one fix",
    ),
    ("valid GTFS when left empty", "docs/rubric.md", "valid GTFS when left empty"),
    (
        "the top three are written in plain language with an effort hint",
        "docs/rubric.md",
        "imperative plain language with an effort hint",
    ),
    (
        "they are not an official MobilityData grade",
        "docs/rubric.md",
        "not presented as an official MobilityData grade",
    ),
    (
        "Outside California, a score is a feed-quality assessment under this published profile, "
        "not a local compliance determination",
        "docs/rubric.md",
        "A score outside California is a feed-quality assessment under this published profile, "
        "not a local compliance determination",
    ),
    (
        "does not certify a feed against any guideline",
        "docs/crosswalk.md",
        "does not certify a feed against any\nguideline",
    ),
]
_SOURCES = sorted({source for _, source, _ in _CLAIMS})


def _flat(text: str) -> str:
    """Collapse markup, Markdown links and whitespace so phrases compare as prose."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<(script|style).*?</\1>", "", text, flags=re.S)
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def _body(markdown: str) -> str:
    return markdown.split("---\n", 2)[2]


def unbacked(markdown: str, read: Callable[[str], str]) -> list[str]:
    """Return every claim, and every number, the repo sources do not back."""
    page = _flat(_body(markdown))
    found: list[str] = []
    for phrase, source, source_phrase in _CLAIMS:
        if _flat(phrase) not in page:
            continue  # phrase not on this page, so nothing to back
        if _flat(source_phrase) not in _flat(read(source)):
            found.append(f"unbacked claim: {phrase!r} (source {source})")
    corpus = " ".join(_flat(read(source)) for source in _SOURCES)
    corpus += " " + _flat(read("web/try.html")) + _flat(read("web/index.html"))
    for number in sorted(set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"\]\([^)]*\)", "]", page)))):
        if not re.search(rf"(?<![\d.]){re.escape(number)}(?![\d])", corpus):
            found.append(f"unbacked number: {number}")
    return found


def _read(rel: str) -> str:
    return (_REPO / rel).read_text()


def _render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_doc: bool = True,
    now: dt.datetime | None = None,
) -> Path:
    root = tmp_path / "golden_site"
    shutil.copytree(_FIXTURE, root)
    if with_doc:
        shutil.copy(_DOC, root / "docs" / "gtfs-validator.md")
    monkeypatch.setenv("SCORECARD_ROOT", str(root))
    from scorecard_pipeline.render_site import render_site

    render_site(now=now or dt.datetime(2026, 7, 3, tzinfo=dt.UTC))
    return root / "web"


def _title(page: str) -> str:
    match = re.search(r"<title>(.*?)</title>", page, re.S)
    assert match is not None
    return html_lib.unescape(match.group(1))


def _internal_links(page: str) -> set[str]:
    return {h for h in re.findall(r'href="(/[^"#]*)', page) if h != "/"}


def inbound(pages: list[Path], target: str) -> list[Path]:
    """The pages that link to ``target``: an empty result is an orphan."""
    needle = f'href="{target}"'
    return [path for path in pages if needle in path.read_text()]


def test_the_page_meets_the_seo_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    web = _render(tmp_path, monkeypatch)
    page = (web / "gtfs-validator" / "index.html").read_text()
    title = _title(page)
    low, high = _SEO["title_length"]
    assert low <= len(title) <= high, title
    description = re.search(r'<meta name="description" content="([^"]*)"', page)
    assert description is not None
    dlow, dhigh = _SEO["description_length"]
    assert dlow <= len(html_lib.unescape(description.group(1))) <= dhigh
    assert page.count("<h1") == 1
    assert f'<link rel="canonical" href="{_URL}">' in page
    assert len(_internal_links(page)) >= 3
    ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page)
    assert [json.loads(block)["@type"] for block in ld] == ["TechArticle"]
    assert 'content="noindex' not in page


def test_title_and_description_are_unique_among_all_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web = _render(tmp_path, monkeypatch)
    pages = {p: p.read_text() for p in web.rglob("*.html")}
    pages[_REPO / "web" / "index.html"] = _read("web/index.html")
    mine = web / "gtfs-validator" / "index.html"
    own_title = _title(pages[mine])
    own_desc = re.search(r'name="description" content="([^"]*)"', pages[mine]).group(1)  # type: ignore[union-attr]
    for path, page in pages.items():
        if path == mine:
            continue
        assert _title(page) != own_title, path
        assert own_desc not in page, path
    # Negative control: a duplicate title elsewhere is detected by the same scan.
    clone = web / "clone.html"
    clone.write_text(pages[mine])
    assert clone.read_text() != "" and _title(clone.read_text()) == own_title
    assert any(_title(p.read_text()) == own_title for p in web.rglob("*.html") if p != mine)


def test_a_title_over_60_characters_is_caught() -> None:
    high = _SEO["title_length"][1]
    real = f"{_title('<title>GTFS validator and the scorecard grade — GTFS Scorecard</title>')}"
    assert len(real) <= high
    sabotaged = real + " and a long tail that overruns the limit"
    assert len(sabotaged) > high  # the sabotage applied
    assert not (_SEO["title_length"][0] <= len(sabotaged) <= high)


def test_the_sitemap_lists_the_page_with_the_documents_own_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modified = re.search(r'date_modified: "(\d{4}-\d{2}-\d{2})"', _DOC.read_text())
    assert modified is not None
    web = _render(tmp_path, monkeypatch)
    sitemap = (web / "sitemap.xml").read_text()
    assert f"<url><loc>{_URL}</loc><lastmod>{modified.group(1)}</lastmod></url>" in sitemap


def test_the_sitemap_date_does_not_follow_the_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _render(tmp_path / "a", monkeypatch, now=dt.datetime(2026, 7, 3, tzinfo=dt.UTC))
    second = _render(tmp_path / "b", monkeypatch, now=dt.datetime(2031, 1, 9, tzinfo=dt.UTC))
    entry = re.compile(rf"<url><loc>{re.escape(_URL)}</loc>.*?</url>")
    one = entry.search((first / "sitemap.xml").read_text())
    two = entry.search((second / "sitemap.xml").read_text())
    assert one is not None and two is not None
    assert one.group(0) == two.group(0)


def test_without_the_document_the_page_is_not_in_the_sitemap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control for the sitemap test: the sabotage must remove the entry."""
    with_doc = _render(tmp_path / "with", monkeypatch)
    assert _URL in (with_doc / "sitemap.xml").read_text()
    without = _render(tmp_path / "without", monkeypatch, with_doc=False)
    assert not (tmp_path / "without" / "golden_site" / "docs" / "gtfs-validator.md").exists()
    assert _URL not in (without / "sitemap.xml").read_text()
    assert not (without / "gtfs-validator").exists()


def test_the_page_is_linked_from_home_about_and_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web = _render(tmp_path, monkeypatch)
    pages = [
        _REPO / "web" / "index.html",
        _REPO / "web" / "about" / "index.html",
        web / "tools" / "index.html",
    ]
    assert inbound(pages, "/gtfs-validator/") == pages


def test_an_orphaned_page_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: strip every link to the page and the check must see none."""
    web = _render(tmp_path, monkeypatch)
    pages = [p for p in web.rglob("*.html") if p.parent.name != "gtfs-validator"]
    scratch_home = web / "home-copy.html"
    scratch_home.write_text(_read("web/index.html"))
    pages.append(scratch_home)
    before = inbound(pages, "/gtfs-validator/")
    assert before, "expected the unsabotaged site to link the page"
    for path in before:
        path.write_text(path.read_text().replace('href="/gtfs-validator/"', 'href="/"'))
    assert not inbound(pages, "/gtfs-validator/")  # sabotage applied: now an orphan


def test_every_internal_link_on_the_page_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web = _render(tmp_path, monkeypatch)

    def exists(href: str) -> bool:
        rel = href.lstrip("/")
        for base in (web, _REPO / "web"):
            if (base / rel / "index.html").exists() or (base / rel).is_file():
                return True
        return False

    links = _internal_links((web / "gtfs-validator" / "index.html").read_text())
    pageish = {
        link
        for link in links
        if not link.startswith(("/src/", "/favicon", "/apple"))
        and not link.endswith((".png", ".ico", ".svg", ".js", ".css", ".xml"))
    }
    assert {"/check/", "/try.html", "/agencies/", "/crosswalk/", "/how-to-read/"} <= pageish
    missing = [link for link in pageish if not exists(link)]
    assert missing == []
    assert not exists("/no-such-page-validator/")  # the resolver can say no


def test_every_claim_on_the_page_is_backed_by_a_repo_source() -> None:
    assert unbacked(_DOC.read_text(), _read) == []
    # The claims table must actually be exercised by the real page.
    page = _flat(_body(_DOC.read_text()))
    assert sum(_flat(phrase) in page for phrase, _, _ in _CLAIMS) >= 25


def test_an_unbacked_claim_is_caught() -> None:
    original = _DOC.read_text()
    sabotaged = original.replace(
        "The scorecard is a data-quality lens",
        "The scorecard catches 2.7 times more errors than any other validator. "
        "The scorecard is a data-quality lens",
    )
    assert sabotaged != original  # the sabotage applied
    assert any("unbacked number: 2.7" in item for item in unbacked(sabotaged, _read))

    def source_changed(rel: str) -> str:
        text = _read(rel)
        return text.replace("hosted instant scoring is not enabled", "hosted scoring is on")

    pages_tools = "pipeline/src/scorecard_pipeline/pages_tools.py"
    assert source_changed(pages_tools) != _read(pages_tools)  # sabotage applied
    assert any("Hosted instant scoring" in item for item in unbacked(original, source_changed))
