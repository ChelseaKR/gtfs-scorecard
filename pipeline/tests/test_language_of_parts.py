"""English passages on the Spanish page say that they are English (WCAG 3.1.2).

`/es/` declares `lang="es"`, so a screen reader reads it with a Spanish voice.
Anything left in English on that page has to carry `lang="en"` or it is read
with Spanish pronunciation rules. `hreflang` does not do this: it describes the
page a link goes to, not the words in the link.

Three passages are English there: the link back to the English site, the
footer's language link, and the theme control, whose labels theme.js writes in
English on every page.
"""

from __future__ import annotations

import re
from pathlib import Path

from scorecard_pipeline.render_site import _render_spanish_rider_page
from scorecard_pipeline.site_shell import FOOTER_HTML_ES

ROOT = Path(__file__).resolve().parents[2]
THEME_JS = ROOT / "web" / "src" / "theme.js"


def _anchor(html: str, text: str) -> str:
    match = re.search(rf"<a\b[^>]*>{re.escape(text)}</a>", html)
    assert match, f"no link reading {text!r}"
    return match.group(0)


def test_link_to_the_english_site_is_marked_english() -> None:
    link = _anchor(_render_spanish_rider_page(), "Read this site in English")
    assert 'lang="en"' in link.replace('hreflang="en"', "")


def test_footer_language_link_is_marked_english() -> None:
    link = _anchor(FOOTER_HTML_ES, "English")
    assert 'lang="en"' in link.replace('hreflang="en"', "")


def test_spanish_links_are_not_marked_english() -> None:
    # The mark belongs on English words only. A Spanish label that points at
    # an English page keeps the page's own language.
    link = _anchor(FOOTER_HTML_ES, "Accesibilidad (en inglés)")
    assert 'lang="en"' not in link.replace('hreflang="en"', "")


def test_theme_control_declares_english_on_a_page_in_another_language() -> None:
    source = THEME_JS.read_text(encoding="utf-8")
    mount = source[source.index("function mount(host)") :]
    # The control reads the page language and marks its own host element.
    assert re.search(r"documentElement\.getAttribute\(\"lang\"\)", mount)
    assert re.search(r"host\.setAttribute\(\"lang\", \"en\"\)", mount)
