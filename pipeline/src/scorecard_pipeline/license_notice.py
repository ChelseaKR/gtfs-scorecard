"""The reuse notice for a feed whose recorded license is share-alike (issue #372).

Owner decision, 2026-09-19: a feed whose license requires share-alike is
admitted, with a notice. The notice does not change what is listed, scored, or
published. It tells a reader, in plain words, which license the feed is under
and what share-alike asks of anyone who reuses the data.

The trigger is narrow on purpose. A notice exists only when a record's
structured ``license`` block affirmatively says ``share_alike: true`` for a
license it names. Every other state has no notice and is never rewritten into
one:

- no block, so nothing is recorded;
- ``id: unknown``, so nothing is known, and an unknown license is neither
  share-alike nor permissive;
- ``share_alike: false`` or ``share_alike: unknown``;
- a block that contradicts its own license class (``CC-BY-4.0`` marked
  share-alike), which ``scorecard license-lint`` reports and which would
  otherwise make the notice name a license as share-alike that it is not.

Absence must not render as a value, so an empty notice means only "no
share-alike license is recorded", never "permissive" and never "known".

The functions here are pure. The scorecard page and the flat export both call
them, so the two carry the same words.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Final

from .config import Agency, LicenseBlock
from .license_audit import CLASSES, UNKNOWN
from .license_ledger import OTHER, PROPRIETARY_TERMS

#: How each share-alike class is named to a reader. A test holds this to the
#: share-alike classes in ``license_audit.CLASSES``, so a new one cannot ship
#: without a name.
LICENSE_NAMES: Final[dict[str, str]] = {
    "ODbL-1.0": "Open Database License (ODbL) 1.0",
    "CC-BY-SA-4.0": "Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)",
    "CC-BY-SA-3.0": "Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0)",
    "CC-BY-SA": "Creative Commons Attribution-ShareAlike (CC BY-SA, version not recorded)",
}

_SHARE_ALIKE_CLASSES = {c.id for c in CLASSES if c.share_alike}

TITLE: Final = "Reuse notice: this feed's license is share-alike"
WHAT_IT_ASKS: Final = (
    "Share-alike is a condition of that license. If you copy, adapt, or build on "
    "this data and share the result, you must share it under the same license and "
    "credit the source."
)
WHERE_TO_READ: Final = "The exact conditions are in the publisher's license terms."
LINK_TEXT: Final = "Read the license terms for this feed"


@dataclass(frozen=True)
class LicenseNotice:
    """What a reader sees for one share-alike feed."""

    license_id: str
    license_name: str
    terms_url: str
    attribution: str

    @property
    def title(self) -> str:
        return TITLE

    @property
    def sentences(self) -> tuple[str, ...]:
        """The notice as plain sentences, in reading order."""
        lines = [f"This feed is published under the {self.license_name}.", WHAT_IT_ASKS]
        if self.attribution:
            lines.append(f"The publisher asks for this credit: {self.attribution}")
        lines.append(WHERE_TO_READ)
        return tuple(lines)

    def export_text(self) -> str:
        """One line for a flat-export field: the same words the page uses."""
        return "Share-alike license. " + " ".join(self.sentences)


def notice_for_block(block: LicenseBlock | None) -> LicenseNotice | None:
    """The notice for a structured block, or None unless it says share-alike.

    See the module docstring for every state that returns None.
    """
    if block is None or block.share_alike is not True or block.id == UNKNOWN:
        return None
    if block.id in (OTHER, PROPRIETARY_TERMS):
        name = block.name
    elif block.id in _SHARE_ALIKE_CLASSES:
        name = LICENSE_NAMES.get(block.id, block.id)
    else:
        # Marked share-alike but the license class is not: a contradiction the
        # lint reports. Naming it here would state something false.
        return None
    if not name:
        return None
    return LicenseNotice(
        license_id=block.id,
        license_name=name,
        terms_url=block.terms_url,
        attribution=block.attribution,
    )


def notice_for_agency(agency: Agency | None) -> LicenseNotice | None:
    """The notice for a registry record, or None."""
    return notice_for_block(agency.license_block) if agency is not None else None


def notice_html(notice: LicenseNotice) -> str:
    """The notice as an accessible section for a scorecard page.

    A labelled region with a real heading and full sentences, so it reads the
    same to a screen reader, a keyboard user, and a reader who cannot tell
    colours apart: meaning comes from the heading and the words, never from a
    colour or an icon. The link says what it opens. No new CSS is needed, and
    none is added, so the page's stylesheet is unchanged.
    """
    paragraphs = [f"<p>{escape(line)}</p>" for line in notice.sentences]
    if notice.terms_url:
        link = f'<a href="{escape(notice.terms_url, quote=True)}">{escape(LINK_TEXT)}</a>'
        paragraphs.append(f"<p>{link}.</p>")
    return (
        '<section class="license-notice" aria-labelledby="license-notice-h">'
        f'<h2 class="section-title" id="license-notice-h">{escape(notice.title)}</h2>'
        + "".join(paragraphs)
        + "</section>"
    )
