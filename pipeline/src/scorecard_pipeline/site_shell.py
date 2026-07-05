"""The site shell: the HTML document, primary nav, and shared page atoms.

Extracted from render_site.py (the first slice of breaking up that module):
everything here is the chrome every page shares — the <head>/<body> shell with
its SEO and accessibility furniture (_page), the primary nav and its
single-source item list (_NAV_ITEMS, sync_static_navs), escaping, breadcrumbs,
and the category constants the whole site labels things with. Page renderers
import from here; nothing here reads artifacts.

render_site re-exports these names, so existing imports keep working.
"""

# ruff: noqa: E501  (long inline-HTML lines, matching render_site)
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from .config import artifacts_dir

BASE_URL = "https://gtfsscorecard.org"

CATEGORY_LABELS = {
    "correctness": "Correctness",
    "freshness": "Freshness",
    "completeness": "Rider experience",
    "realtime": "Realtime quality",
}
CATEGORY_ORDER = ["correctness", "freshness", "completeness", "realtime"]
SEVERITY_LABELS = {"ERROR": "Error", "WARNING": "Warning", "INFO": "Info"}


def _repo_root() -> Path:
    return artifacts_dir().parent.parent


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


# Six stops, one per question, instead of a flat list of every page: find an
# agency, take the nation's pulse, open a dimensional lens, act with a tool,
# learn how to read the thing, and who made it. The pages those groups absorb
# stay reachable from each hub (and from _NAV_SECTION_PREFIXES for wayfinding).
_NAV_ITEMS = [
    ("Agencies", "/agencies/"),
    ("National pulse", "/pulse/"),
    ("Focus areas", "/focus/"),
    ("Tools", "/tools/"),
    ("How to read", "/how-to-read/"),
    ("About", "/about/"),
]

# Which nav stop a non-hub path belongs to, so the bar still shows where you
# are when you are inside a section's pages.
_NAV_SECTION_PREFIXES = {
    "/agency/": "/agencies/",
    "/fix/": "/agencies/",
    "/program/": "/agencies/",
    "/app/": "/agencies/",
    "/map/": "/agencies/",
    "/routes/": "/agencies/",
    "/problems/": "/pulse/",
    "/ntd/": "/focus/",
    "/realtime/": "/focus/",
    "/equity/": "/focus/",
    "/adoption/": "/focus/",
    "/compare/": "/tools/",
    "/check/": "/tools/",
    "/query/": "/tools/",
    "/procurement/": "/tools/",
    "/accessibility/": "/how-to-read/",
    "/data/": "/how-to-read/",
    "/concept/": "/how-to-read/",
    "/press/": "/how-to-read/",
}


def _nav_active(path: str) -> str:
    """Which _NAV_ITEMS href is the current section for a site-relative path.
    Pages inside a section (an agency page, a focus lens, a tool) light up
    their hub's stop."""
    active = ""
    for _, href in _NAV_ITEMS:
        if path.startswith(href):
            active = href
    if not active:
        for prefix, hub in _NAV_SECTION_PREFIXES.items():
            if path.startswith(prefix):
                return hub
    return active


def _nav_stops_html(active: str | None) -> str:
    """The <nav> of wayfinding stops, with the active section filled
    (aria-current). The single source of the primary nav's item set (_NAV_ITEMS),
    shared by the generated header (_nav_html) and the hand-authored static pages
    (sync_static_navs, guarded by tests/test_static_nav.py) so the bar cannot
    drift between them."""
    parts = []
    for label, href in _NAV_ITEMS:
        cur = ' aria-current="page"' if href == active else ""
        parts.append(
            f'<a class="nav-stop" href="{href}"{cur}>'
            f'<span class="pip" aria-hidden="true"></span>{label}</a>'
        )
    return f'<nav class="nav-stops" aria-label="Primary">{"".join(parts)}</nav>'


def _nav_html(canonical: str) -> str:
    """The primary wayfinding nav: the site's sections as stops on a route line,
    with the current page's stop filled (aria-current). The #theme-control slot is
    where theme.js mounts the colour-theme menu."""
    path = canonical.replace(BASE_URL, "") or "/"
    return (
        '<header class="site-header"><div class="wrap">'
        '<a class="brand" href="/"><span class="brand-mark" aria-hidden="true"></span>'
        '<span class="brand-name">GTFS&nbsp;Scorecard</span></a>'
        '<button class="nav-menu-btn" type="button" aria-expanded="false" '
        'aria-controls="nav-cluster"><span aria-hidden="true">☰</span> Menu</button>'
        '<div class="nav-cluster" id="nav-cluster">'
        f"{_nav_stops_html(_nav_active(path))}"
        '<div id="theme-control"></div>'
        "</div></div></header>"
    )


# Hand-authored static pages (not generated from artifacts) that nonetheless carry
# the shared primary nav. They are regenerated from _NAV_ITEMS by sync_static_navs
# and guarded by tests/test_static_nav.py, so the bar cannot drift between them and
# the generated header the way it did before. Value is the active section, if any.
STATIC_NAV_PAGES: dict[str, str | None] = {
    "submit.html": None,
    "subscribe.html": None,
    "try.html": None,
    "app/index.html": "/agencies/",
    "about/index.html": "/about/",
    "data/index.html": None,
}

# The one shared footer, single-sourced here so the generated pages and the
# hand-authored static pages can never drift apart (same mechanism as the nav).
FOOTER_HTML = """<footer class="site-footer">
    <div class="wrap">
      <p>An open-source data quality tool for small and rural transit agencies.</p>
      <p><strong>Agencies:</strong>
      <a href="/agencies/">Directory</a> ·
      <a href="/app/">Interactive app</a> ·
      <a href="/map/">Map</a> · <a href="/routes/">All routes</a></p>
      <p><strong>The nation:</strong>
      <a href="/pulse/">National pulse</a> ·
      <a href="/problems/">Common problems</a> ·
      <a href="/ntd/">NTD readiness</a> ·
      <a href="/realtime/">Realtime</a> · <a href="/equity/">Equity</a> ·
      <a href="/adoption/">What feeds publish</a></p>
      <p><strong>Tools:</strong>
      <a href="/compare/">Compare two agencies</a> ·
      <a href="/check/">Check a feed before you publish</a> ·
      <a href="/try.html">Score any feed now</a> ·
      <a href="/query/">Query the dataset</a> ·
      <a href="/subscribe.html">Feed-health alerts</a> ·
      <a href="/submit.html">Add your agency</a> ·
      <a href="/procurement/">For agencies: procurement</a></p>
      <p><a href="/about/">About</a> ·
      <a href="/how-to-read/">How to read a scorecard</a> ·
      <a href="/how-to-read/#glossary">Glossary</a> ·
      <a href="/press/">For reporters</a> ·
      <a href="/data/">Open data</a> ·
      <a href="/accessibility/">Accessibility</a> ·
      <a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/listing-policy.md">Listing &amp; removal policy</a></p>
    </div>
  </footer>"""


def _redirect_page(target: str, title: str) -> str:
    """A tiny static redirect for a retired URL: meta refresh plus a canonical
    link and a plain fallback link, so old bookmarks, papers, and crawlers all
    land on the page that absorbed this one. Written with no sitemap entry."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={esc(target)}">
  <link rel="canonical" href="{esc(target)}">
  <title>{esc(title)} — moved</title>
</head>
<body>
  <p>This page moved. Continue to <a href="{esc(target)}">{esc(title)}</a>.</p>
</body>
</html>
"""


# The one nav-stops block and one footer to replace in each static page.
_NAV_STOPS_RE = re.compile(r'<nav class="nav-stops".*?</nav>', re.DOTALL)
_FOOTER_RE = re.compile(r'<footer class="site-footer">.*?</footer>', re.DOTALL)


def sync_static_navs() -> list[Path]:
    """Rewrite the primary nav block and the footer of each hand-authored static
    page from the single canonical sources (_nav_stops_html, FOOTER_HTML), so the
    static pages cannot drift from the generated ones. Returns the paths that
    changed (empty when in sync). Run via `make sync-static-nav`;
    tests/test_static_nav.py fails CI on drift."""
    web = _repo_root() / "web"
    changed: list[Path] = []
    for rel, active in STATIC_NAV_PAGES.items():
        path = web / rel
        old = path.read_text()
        match = _NAV_STOPS_RE.search(old)
        if match is None:
            raise ValueError(f"{path}: expected one nav-stops block to sync, found none")
        new = old[: match.start()] + _nav_stops_html(active) + old[match.end() :]
        fmatch = _FOOTER_RE.search(new)
        if fmatch is None:
            raise ValueError(f"{path}: expected one site-footer block to sync, found none")
        new = new[: fmatch.start()] + FOOTER_HTML + new[fmatch.end() :]
        if new != old:
            path.write_text(new)
            changed.append(path)
    return changed


def _page(
    *,
    title: str,
    description: str,
    canonical: str,
    body: str,
    jsonld: dict[str, Any] | None = None,
    head_extra: str = "",
    wide: bool = False,
) -> str:
    """Wrap body in the full HTML document with SEO head tags. CSS and the
    interactive app are linked by absolute path from the site root. ``head_extra``
    injects page-specific head markup (e.g. a map library's stylesheet).
    ``wide`` widens the main column for pages whose value is tabular: prose
    keeps its own measure, tables get the screen (WCAG 1.4.8 line-length
    limits apply to prose, not data tables)."""
    ld = (
        f'\n  <script type="application/ld+json">{json.dumps(jsonld, separators=(",", ":"))}</script>'
        if jsonld
        else ""
    )
    ld += f"\n  {head_extra}" if head_extra else ""
    nav = _nav_html(canonical)
    main_class = "wrap wrap-wide" if wide else "wrap"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <link rel="canonical" href="{esc(canonical)}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{esc(canonical)}">
  <meta property="og:image" content="{BASE_URL}/og.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{BASE_URL}/og.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Overpass:ital,wght@0,600;0,700;0,900;1,600&family=Overpass+Mono:wght@400;500;600&family=Public+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap">
  <link rel="stylesheet" href="/src/styles.css">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='13' fill='%23204e3a'/%3E%3Ccircle cx='16' cy='16' r='5' fill='%23f2f3ee'/%3E%3C/svg%3E">{ld}
  <script>
    /* Apply the saved theme before first paint to avoid a flash (WCAG 1.4.8). */
    try {{
      var t = localStorage.getItem("scorecard-theme");
      if (t && ["light", "contrast", "dark"].indexOf(t) >= 0)
        document.documentElement.setAttribute("data-theme", t);
    }} catch (e) {{}}
  </script>
  <script src="/src/theme.js" defer></script>
  <script src="/src/nav.js" defer></script>
  <script src="/analytics.js" defer></script>
  <noscript><style>
    /* Without JS the menu button cannot expand the collapsed nav, so show the
       stacked nav permanently and hide the button (content stays operable
       without scripting). nav.js never runs here, so nothing double-toggles. */
    @media (max-width: 1400px) {{
      .nav-menu-btn {{ display: none !important; }}
      .nav-cluster {{ display: flex !important; position: static; }}
    }}
  </style></noscript>
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>
  {nav}
  <main id="main" class="{main_class}" tabindex="-1">
{body}
  </main>
  {FOOTER_HTML}
</body>
</html>
"""


def _grade_class(grade: str) -> str:
    return f"grade-{grade.lower()}"


def _breadcrumb(trail: list[tuple[str, str | None]]) -> str:
    """A WCAG 2.4.8 breadcrumb. ``trail`` is (label, href) pairs; the last item
    is the current page and carries aria-current with no link."""
    items = []
    for i, (label, href) in enumerate(trail):
        last = i == len(trail) - 1
        if href and not last:
            items.append(f'<li><a href="{esc(href)}">{esc(label)}</a></li>')
        else:
            items.append(f'<li><span aria-current="page">{esc(label)}</span></li>')
    return '<nav class="breadcrumb" aria-label="Breadcrumb"><ol>' + "".join(items) + "</ol></nav>"
