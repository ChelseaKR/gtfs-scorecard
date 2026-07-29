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
from .instance import BASE_URL as BASE_URL  # re-exported: render_site imports it from here

_SOCIAL_IMAGE_URL = f"{BASE_URL}/og.png"
_SOCIAL_IMAGE_ALT = "GTFS Scorecard: transit data quality for small agencies."
_SOCIAL_IMAGE_WIDTH = 1200
_SOCIAL_IMAGE_HEIGHT = 630

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
# agency, review coverage, find feeds by rider-facing feature, act with a tool,
# learn how to read the thing, and who made it. The pages those groups absorb
# stay reachable from each hub (and from _NAV_SECTION_PREFIXES for wayfinding).
_NAV_ITEMS = [
    ("Find an agency", "/agencies/"),
    ("Coverage", "/pulse/"),
    ("Feed features", "/app/#/?view=features"),
    ("Tools", "/tools/"),
    ("How it works", "/how-to-read/"),
    ("About", "/about/"),
]

_NAV_ITEMS_ES = [
    ("Agencias", "/agencies/"),
    ("Cobertura", "/pulse/"),
    ("Funciones GTFS", "/app/#/?view=features"),
    ("Herramientas", "/tools/"),
    ("Cómo leer", "/how-to-read/"),
    ("Acerca de", "/about/"),
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
    "/focus/": "/pulse/",
    "/ntd/": "/pulse/",
    "/realtime/": "/pulse/",
    "/equity/": "/pulse/",
    "/adoption/": "/app/#/?view=features",
    "/compare/": "/tools/",
    "/check/": "/tools/",
    "/query/": "/tools/",
    "/procurement/": "/tools/",
    "/accessibility/": "/how-to-read/",
    "/status/": "/how-to-read/",
    "/data/": "/how-to-read/",
    "/concept/": "/how-to-read/",
    "/press/": "/how-to-read/",
    "/support/": "/about/",
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


def _nav_stops_html(active: str | None, lang: str = "en") -> str:
    """The <nav> of wayfinding stops, with the active section filled
    (aria-current). The single source of the primary nav's item set (_NAV_ITEMS),
    shared by the generated header (_nav_html) and the hand-authored static pages
    (sync_static_navs, guarded by tests/test_static_nav.py) so the bar cannot
    drift between them."""
    parts = []
    items = _NAV_ITEMS_ES if lang == "es" else _NAV_ITEMS
    for label, href in items:
        cur = ' aria-current="page"' if href == active else ""
        parts.append(
            f'<a class="nav-stop" href="{href}"{cur}>'
            f'<span class="pip" aria-hidden="true"></span>{label}</a>'
        )
    aria_label = "Principal" if lang == "es" else "Primary"
    return f'<nav class="nav-stops" aria-label="{aria_label}">{"".join(parts)}</nav>'


def _nav_html(canonical: str, lang: str = "en") -> str:
    """The primary wayfinding nav: the site's sections as stops on a route line,
    with the current page's stop filled (aria-current). The #theme-control slot is
    where theme.js mounts the colour-theme menu."""
    path = canonical.replace(BASE_URL, "") or "/"
    menu = "Menú" if lang == "es" else "Menu"
    return (
        '<header class="site-header"><div class="wrap">'
        '<a class="brand" href="/"><span class="brand-mark" aria-hidden="true"></span>'
        '<span class="brand-name">GTFS&nbsp;Scorecard</span></a>'
        '<button class="nav-menu-btn" type="button" aria-expanded="false" '
        f'aria-controls="nav-cluster"><span aria-hidden="true">☰</span> {menu}</button>'
        '<div class="nav-cluster" id="nav-cluster">'
        f"{_nav_stops_html(_nav_active(path), lang)}"
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
    "support/index.html": "/about/",
    "fetcher/index.html": "/about/",
}

# The one shared footer, single-sourced here so the generated pages and the
# hand-authored static pages can never drift apart (same mechanism as the nav).
_US_TOOLS_FOOTER_SECTION = """          <li class="footer-subhead">United States tools</li>
          <li><a href="/ntd/">U.S. NTD readiness</a></li>
          <li><a href="/equity/">U.S. equity</a></li>
"""

FOOTER_HTML = f"""<footer class="site-footer">
    <div class="wrap">
      <div class="footer-intro">
        <a class="footer-brand" href="/">GTFS Scorecard</a>
        <p>An open-source data quality tool for small and rural transit agencies.</p>
      </div>
      <nav class="footer-grid" aria-label="Footer">
        <section aria-labelledby="footer-find-h">
          <h2 id="footer-find-h">Find a scorecard</h2>
          <ul>
            <li><a href="/agencies/">Agency directory</a></li>
            <li><a href="/app/">Interactive search</a></li>
            <li><a href="/map/">Agency map</a></li>
            <li><a href="/routes/">All routes</a></li>
            <li><a href="/compare/">Compare two agencies</a></li>
          </ul>
        </section>
        <section aria-labelledby="footer-improve-h">
          <h2 id="footer-improve-h">Improve a feed</h2>
          <ul>
            <li><a href="/fix/">GTFS errors &amp; fixes</a></li>
            <li><a href="/check/">Check before publishing</a></li>
            <li><a href="/try.html">Request a one-off score</a></li>
            <li><a href="/subscribe.html">Feed-health alerts</a></li>
            <li><a href="/submit.html">Add an agency</a></li>
            <li><a href="/claim/">Correct or claim a listing</a></li>
            <li><a href="/procurement/">Procurement language</a></li>
          </ul>
        </section>
        <section aria-labelledby="footer-explore-h">
          <h2 id="footer-explore-h">Explore the data</h2>
          <ul>
            <li><a href="/pulse/">Coverage overview</a></li>
            <li><a href="/problems/">Common problems</a></li>
            <li><a href="/realtime/">Realtime quality</a></li>
            <li><a href="/adoption/">What feeds publish</a></li>
            <li><a href="/focus/">Focus areas</a></li>
{_US_TOOLS_FOOTER_SECTION.rstrip()}
            <li><a href="/query/">Query the dataset</a></li>
            <li><a href="/data/">Open data</a></li>
          </ul>
        </section>
        <section aria-labelledby="footer-project-h">
          <h2 id="footer-project-h">Project</h2>
          <ul>
            <li><a href="/about/">About</a></li>
            <li><a href="/status/">Status</a></li>
            <li><a href="/support/">Get help or sponsor</a></li>
            <li><a href="/how-to-read/">How to read a scorecard</a></li>
            <li><a href="/how-to-read/#glossary">Glossary</a></li>
            <li><a href="/crosswalk/">Standards crosswalk</a></li>
            <li><a href="/press/">For reporters</a></li>
            <li><a href="/accessibility/">Accessibility</a></li>
            <li><a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/CONTRIBUTING.md">Contribute</a></li>
            <li><a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/listing-policy.md">Listing &amp; removal policy</a></li>
          </ul>
        </section>
      </nav>
    </div>
  </footer>"""

# Agency pages outside the United States keep all shared global navigation but
# do not foreground a policy tool that cannot apply to them. General pages keep
# the labelled U.S. section discoverable, and U.S. agency pages remain unchanged.
FOOTER_HTML_WITHOUT_US_TOOLS = FOOTER_HTML.replace(_US_TOOLS_FOOTER_SECTION.rstrip() + "\n", "")

FOOTER_HTML_ES = """<footer class="site-footer">
    <div class="wrap">
      <p>Herramienta de código abierto para revisar datos de transporte público.</p>
      <p><a href="/es/">Buscar una agencia</a> ·
      <a href="/agencies/" hreflang="en">Directorio completo (en inglés)</a> ·
      <a href="/accessibility/" hreflang="en">Accesibilidad (en inglés)</a> ·
      <a href="/" hreflang="en">English</a></p>
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
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="0; url={esc(target)}">
  <link rel="canonical" href="{esc(target)}">
  <link rel="stylesheet" href="/src/styles.css">
  <title>{esc(title)} — moved</title>
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>
  <main id="main" class="wrap" tabindex="-1">
    <h1 class="page-title">{esc(title)} moved.</h1>
    <p class="page-lede">Continue to <a href="{esc(target)}">{esc(title)}</a>.</p>
  </main>
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
    robots: str | None = None,
    wide: bool = False,
    lang: str = "en",
    country_code: str | None = None,
    main_modifier: str = "",
) -> str:
    """Wrap body in the full HTML document with SEO head tags. CSS and the
    interactive app are linked by absolute path from the site root. ``head_extra``
    injects page-specific head markup (e.g. a map library's stylesheet).
    ``wide`` widens the main column for pages whose value is tabular: prose
    keeps its own measure, tables get the screen (WCAG 1.4.8 line-length
    limits apply to prose, not data tables). On an agency-scoped page,
    ``country_code`` removes the labelled United States policy-tool links when
    they cannot apply; shared global links and all U.S. pages stay unchanged.
    ``main_modifier`` adds a page-family hook without replacing the shared
    container classes."""
    ld = (
        f'\n  <script type="application/ld+json">{json.dumps(jsonld, separators=(",", ":"))}</script>'
        if jsonld
        else ""
    )
    if robots:
        ld += f'\n  <meta name="robots" content="{esc(robots)}">'
    ld += f"\n  {head_extra}" if head_extra else ""
    nav = _nav_html(canonical, lang)
    main_class = "wrap wrap-wide" if wide else "wrap"
    if main_modifier:
        main_class += f" {esc(main_modifier)}"
    skip_label = "Saltar al contenido principal" if lang == "es" else "Skip to main content"
    if lang == "es":
        footer = FOOTER_HTML_ES
    elif country_code and country_code.strip().upper() != "US":
        footer = FOOTER_HTML_WITHOUT_US_TOOLS
    else:
        footer = FOOTER_HTML
    return f"""<!doctype html>
<html lang="{esc(lang)}">
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
  <meta property="og:image" content="{esc(_SOCIAL_IMAGE_URL)}">
  <meta property="og:image:width" content="{_SOCIAL_IMAGE_WIDTH}">
  <meta property="og:image:height" content="{_SOCIAL_IMAGE_HEIGHT}">
  <meta property="og:image:alt" content="{esc(_SOCIAL_IMAGE_ALT)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{esc(_SOCIAL_IMAGE_URL)}">
  <meta name="twitter:image:alt" content="{esc(_SOCIAL_IMAGE_ALT)}">
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
    @media (max-width: 1040px) {{
      .nav-menu-btn {{ display: none !important; }}
      .nav-cluster {{ display: flex !important; position: static; }}
    }}
  </style></noscript>
</head>
<body>
  <a class="skip-link" href="#main">{skip_label}</a>
  {nav}
  <main id="main" class="{main_class}" tabindex="-1">
{body}
  </main>
  {footer}
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
            content = f'<a itemprop="item" href="{esc(href)}"><span itemprop="name">{esc(label)}</span></a>'
        else:
            content = f'<span itemprop="name" aria-current="page">{esc(label)}</span>'
        items.append(
            '<li itemprop="itemListElement" itemscope '
            'itemtype="https://schema.org/ListItem">'
            f'{content}<meta itemprop="position" content="{i + 1}"></li>'
        )
    return (
        '<nav class="breadcrumb" aria-label="Breadcrumb"><ol itemscope '
        'itemtype="https://schema.org/BreadcrumbList">' + "".join(items) + "</ol></nav>"
    )
