"""The skip link is called the same thing on every page (WCAG 3.2.4).

The landing page carries its own markup and called it "Skip to content"; the
shared shell, on every other page, calls it "Skip to main content". A control
that does one job should have one name wherever it appears, so a reader who
learns it once, or says it to a voice-control tool, finds it again.
"""

from __future__ import annotations

import re
from pathlib import Path

from scorecard_pipeline.site_shell import _page

ROOT = Path(__file__).resolve().parents[2]
LANDING = ROOT / "web" / "index.html"

_SKIP = re.compile(r'<a class="skip(?:-link)?" href="#main">([^<]+)</a>')


def test_landing_page_and_shell_use_one_skip_link_label() -> None:
    shell = _page(title="t", description="d", canonical="https://gtfsscorecard.org/x/", body="")
    shell_label = _SKIP.findall(shell)
    landing_label = _SKIP.findall(LANDING.read_text(encoding="utf-8"))
    assert shell_label == ["Skip to main content"]
    assert landing_label == shell_label
