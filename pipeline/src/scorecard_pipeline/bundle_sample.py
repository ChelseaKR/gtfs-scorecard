"""The Program Report Bundle's own sample: what a buyer sees before paying.

/bundle/ (web/bundle/index.html) describes the paid deliverable -- one
self-contained board report per agency a program supports, branded with the
program's name, logo, and accent color -- but until this module existed, a
cold visitor had to take that description on faith: nothing on the page
showed the actual format. This renders one real report through the exact
same code path a paid build uses (report.generate_report, the same function
bundle.build_bundle calls per agency), for one real, currently published
agency, with a placeholder program brand in place of a buyer's real one, and
the SAMPLE markers report.render_report adds only when asked. The score is
never fabricated: it is read from the same published artifact the free
per-agency report and a real paid bundle both read, so a change to that
agency's actual grade changes the sample the next time the site rebuilds
(pages.yml's "Render the program bundle sample" step runs this on every
deploy, alongside render-site).

Picking SAMPLE_AGENCY_ID by name, rather than "whichever agency sorts first"
or "the highest grade", keeps the choice legible and reviewable. Unitrans is
one of this project's two pilot agencies (CLAUDE.md) and has carried a
published scorecard since the pipeline's first phase.
"""

from __future__ import annotations

import base64
import datetime as dt
from pathlib import Path

from .config import AGENCIES
from .report import Brand, ReportError, SamplePageMeta, generate_report
from .site_shell import BASE_URL, _repo_root

SAMPLE_AGENCY_ID = "unitrans"

# A placeholder, not a real organization's name or mark: the point is to show
# where a buyer's own branding goes, not to imply one. "Your Program Name
# Here" reads as a form placeholder in every rendered spot it appears (cover,
# kicker, footer attribution), the same way a template's placeholder text
# does, so it cannot be mistaken for a real program.
SAMPLE_PROGRAM_NAME = "Your Program Name Here"
# Distinct from DEFAULT_ACCENT (report.py's own green) on purpose: choosing a
# different color is the easiest way to show the accent is a buyer's to pick,
# not fixed by the tool. Decorative only, per Brand's contract -- it colors a
# band and rules, never text.
SAMPLE_ACCENT = "#5b3a8e"
# A plain monogram card, not a logo lifted from anywhere: "YOUR LOGO" on a
# accent-filled rectangle, sized like a small program mark. Built inline so
# the sample never depends on a fetched or committed image file.
_SAMPLE_LOGO_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="64" '
    b'viewBox="0 0 220 64" role="img" aria-label="Placeholder logo">'
    b'<rect width="220" height="64" rx="6" fill="' + SAMPLE_ACCENT.encode("ascii") + b'"/>'
    b'<text x="110" y="38" font-family="Helvetica, Arial, sans-serif" '
    b'font-size="21" font-weight="700" fill="#ffffff" text-anchor="middle">'
    b"YOUR LOGO</text></svg>"
)

SAMPLE_CANONICAL_URL = f"{BASE_URL}/bundle/sample/"
SAMPLE_DESCRIPTION = (
    "A sample Program Report Bundle cover: one real, currently published agency's "
    "GTFS data-quality score, rendered with a placeholder program name, logo, and "
    "accent color. A purchased bundle covers every agency you choose, branded with "
    "your own program's name, logo, and accent color."
)

DEFAULT_SAMPLE_OUT = Path("web") / "bundle" / "sample" / "index.html"


def sample_brand() -> Brand:
    """The placeholder brand rendered onto the sample cover in place of a
    buyer's real one."""
    encoded = base64.b64encode(_SAMPLE_LOGO_SVG).decode("ascii")
    return Brand(
        name=SAMPLE_PROGRAM_NAME,
        logo_data_uri=f"data:image/svg+xml;base64,{encoded}",
        accent=SAMPLE_ACCENT,
    )


def _check_sample_agency_current() -> None:
    """Fail loudly, before rendering, if the chosen sample agency is no
    longer a live, canonical, currently-tracked scorecard.

    An empty process-global registry is the library/test compatibility mode
    (matching bundle.classify): nothing to check against, so the artifact
    tree alone decides, and generate_report already fails loudly if it has
    no published artifact to read."""
    if not AGENCIES:
        return
    agency = AGENCIES.get(SAMPLE_AGENCY_ID)
    if agency is None or not agency.is_canonical_feed:
        raise ReportError(
            f"the bundle sample's agency id {SAMPLE_AGENCY_ID!r} is no longer a "
            "current, canonical registry entry; pick a different real agency id "
            "in bundle_sample.SAMPLE_AGENCY_ID (never fabricate a score to keep "
            "this one working)"
        )


def build_bundle_sample(out: Path | None = None, *, now: dt.datetime | None = None) -> Path:
    """Render the on-site sample of a Program Report Bundle cover and write
    it to ``out`` (default: web/bundle/sample/index.html at the repo root).

    Raises ReportError, same as generate_report, if the sample agency has no
    published scorecard to read -- this never invents one."""
    _check_sample_agency_current()
    target = out or (_repo_root() / DEFAULT_SAMPLE_OUT)
    return generate_report(
        SAMPLE_AGENCY_ID,
        brand=sample_brand(),
        out=target,
        now=now,
        sample=True,
        sample_meta=SamplePageMeta(
            canonical_url=SAMPLE_CANONICAL_URL,
            description=SAMPLE_DESCRIPTION,
        ),
    )
