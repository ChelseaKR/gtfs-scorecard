"""A missing address gets the site's own page, not the host's.

GitHub Pages serves `/404.html` for any address it cannot find. With no such
file it served its stock page: no site name, no navigation, no page language,
gray text at low contrast and a logo link with no name (axe: 6 rules, 18
nodes, on 2026-11-17). A reader who followed an old link had no way on except
the browser's back button.

The page is built by the shared shell like every other page, so it carries
the header, the navigation, the skip link, the language and the themes, and
it is held to the same checks. Three things are particular to it:

- It is served at whatever address was asked for, at any depth, so nothing
  in it may be a relative address.
- It is not a page to find in a search engine: `noindex`, and not in the
  sitemap.
- Its links have to lead somewhere a lost reader can start again.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from scorecard_pipeline.render_site import _render_not_found_page

ROOT = Path(__file__).resolve().parents[2]
GOLDENS = Path(__file__).parent / "goldens"

TITLE = "Page not found — GTFS Scorecard"
HEADING = "Page not found."
TEXT = (
    "Nothing is published at this address. The link may be out of date, or the page may have moved."
)
# The approved labels, and where each goes. "Find an agency" is the primary
# nav's own label for the directory, so it goes where that goes. "Search
# scorecards" goes to the app, whose search box is labeled "Search scorecards
# by agency name, country, or subdivision".
LINKS = [
    ("Find an agency", "/agencies/"),
    ("Search scorecards", "/app/"),
    ("Go to the home page", "/"),
]


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[tuple[str, str]] = []
        self.main_links: list[tuple[str, str]] = []
        self.h1: list[str] = []
        self._in_main = 0
        self._in_h1 = False
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        for name in ("href", "src"):
            if attr.get(name) is not None and tag in {"a", "link", "script", "img"}:
                self.references.append((tag, str(attr[name])))
        if tag == "main":
            self._in_main += 1
        if tag == "h1":
            self._in_h1 = True
            self.h1.append("")
        if tag == "a" and self._in_main:
            self._href = str(attr.get("href") or "")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "main":
            self._in_main -= 1
        if tag == "h1":
            self._in_h1 = False
        if tag == "a" and self._href is not None:
            self.main_links.append(("".join(self._text).strip(), self._href))
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._in_h1:
            self.h1[-1] += data
        if self._href is not None:
            self._text.append(data)


def _parsed() -> tuple[str, _Page]:
    html = _render_not_found_page()
    page = _Page()
    page.feed(html)
    return html, page


def test_the_page_carries_the_approved_words() -> None:
    html, page = _parsed()
    assert f"<title>{TITLE}</title>" in html
    assert page.h1 == [HEADING]
    assert TEXT in re.sub(r"\s+", " ", html)
    assert page.main_links == LINKS


def test_the_page_is_built_on_the_shared_shell() -> None:
    html, _ = _parsed()
    assert '<html lang="en">' in html
    assert '<a class="skip-link" href="#main">Skip to main content</a>' in html
    assert '<header class="site-header">' in html
    assert '<nav class="nav-stops" aria-label="Primary">' in html
    assert '<main id="main"' in html
    assert '<footer class="site-footer">' in html
    # The theme script and the saved-theme snippet, like every other page.
    assert 'src="/src/theme.js"' in html
    assert 'localStorage.getItem("scorecard-theme")' in html
    # A missing page is nobody's current section.
    assert "aria-current" not in html


def test_nothing_on_the_page_is_a_relative_address() -> None:
    # The host serves this file at the address that was asked for, at any
    # depth. "src/styles.css" would be looked for under the missing folder.
    _, page = _parsed()
    assert page.references
    relative = [
        (tag, ref)
        for tag, ref in page.references
        if not ref.startswith(("/", "https://", "http://", "#", "mailto:"))
    ]
    assert not relative, f"relative addresses on the 404 page: {relative}"


def test_the_page_is_kept_out_of_search_results() -> None:
    html, _ = _parsed()
    assert '<meta name="robots" content="noindex,follow">' in html
    config = json.loads((ROOT / "site-seo.json").read_text(encoding="utf-8"))
    assert "/404.html" in config["noindex_path_patterns"]


def test_the_site_render_writes_it_where_the_host_looks_and_not_in_the_sitemap() -> None:
    # The goldens are a full render of the fixture site.
    rendered = GOLDENS / "404.html"
    assert rendered.is_file(), "render_site does not write 404.html at the site root"
    assert rendered.read_text(encoding="utf-8") == _render_not_found_page()
    assert "404" not in (GOLDENS / "sitemap.xml").read_text(encoding="utf-8")


def test_the_committed_site_carries_the_page() -> None:
    # web/ is what the browser tests serve, and what a deploy starts from.
    assert (ROOT / "web" / "404.html").read_text(encoding="utf-8") == _render_not_found_page()


def test_the_axe_gate_opens_it() -> None:
    config = json.loads((ROOT / ".pa11yci.json").read_text(encoding="utf-8"))
    urls = [entry if isinstance(entry, str) else entry["url"] for entry in config["urls"]]
    assert "http://127.0.0.1:8080/404.html" in urls
