"""The landing page's focus ring matches the surface it is drawn on.

`web/index.html` carries its own styles. Its focus ring comes in two colors:
`--focus-page` for the light page and `--focus-dark` for the pine bands. Which
one a link gets is decided by a short list of band selectors, and that list
has to follow the bands. When it does not, the ring is still drawn but cannot
be seen: dark blue on pine measured 1.6:1 and amber on the light pilot band
1.3:1, against the 3:1 WCAG 1.4.11 asks of a focus indicator.

This reads the page's inline stylesheet. For each band that holds links, the
last background the cascade gives it decides which ring it must use.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LANDING = ROOT / "web" / "index.html"

# Bands that contain links or buttons. `footer` is the page footer.
BANDS = (".home-header", ".workflow-run", ".movement", "footer")
DARK_BACKGROUNDS = {"var(--pine)"}


def _styles() -> str:
    html = LANDING.read_text(encoding="utf-8")
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S))
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _last_background(css: str, selector: str) -> str:
    """The background the last plain rule for ``selector`` declares."""
    found = ""
    for match in re.finditer(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^{{}}]*)\}}", css):
        declared = re.search(r"(?<![-a-z])background\s*:\s*([^;]+);", match.group(1))
        if declared:
            found = declared.group(1).strip()
    assert found, f"{selector} declares no background"
    return found


def _dark_ring_selectors(css: str) -> set[str]:
    """The band selectors whose descendants take the dark-surface ring."""
    bands: set[str] = set()
    for match in re.finditer(r"([^{}]+)\{\s*outline-color:\s*var\(--focus-dark\);?\s*\}", css):
        for selector in match.group(1).split(","):
            bands.add(selector.replace(":focus-visible", "").strip())
    return bands


def test_each_band_gets_the_ring_that_shows_on_it() -> None:
    css = _styles()
    dark_ring = _dark_ring_selectors(css)
    for band in BANDS:
        is_dark = _last_background(css, band) in DARK_BACKGROUNDS
        if is_dark:
            assert band in dark_ring, (
                f"{band} is a pine band, but links in it get the page's dark "
                "blue focus ring, which does not show on pine"
            )
        else:
            assert band not in dark_ring, (
                f"{band} is a light band, but links in it get the amber focus "
                "ring, which does not show on a light surface"
            )
