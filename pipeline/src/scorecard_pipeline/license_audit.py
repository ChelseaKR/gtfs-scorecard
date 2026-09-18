"""What the registry says about reuse terms, counted from its own notes.

Every registry record carries a free-text ``license_note``. Nothing in the
pipeline could read those notes as data, so the one number an owner decision
depends on was quoted by hand, and quoted wrong. ``docs/follow-ups.md`` says 160
records are share-alike. Parsing the notes for any share-alike wording gives
132, and that count still includes notes that mention a share-alike license
only to say it does not apply (issue #372, "Measured 2026-09-11").

This module classifies each note into one license from a closed vocabulary,
and only when the note is unambiguous:

- A note naming exactly one license in :data:`CLASSES` gets that license.
- A note naming more than one gets ``unknown`` with ``more_than_one_license``
  and keeps the list of what it named. "Datenlizenz Deutschland ... no ODbL
  condition apply" names two, and deciding which one binds is a curator's
  reading, not a pattern's.
- Every other note gets ``unknown`` with a reason saying why: it states no
  license, it is only a link, or it names terms this vocabulary does not hold.

Nothing is guessed, and ``unknown`` is never counted as open or as closed.

The audit is a report. It reads the committed registry, does no network I/O,
and never fails: the share-alike policy it would measure against is an open
owner decision (``docs/follow-ups.md``, "Decide the share-alike question for
records already listed"), so it reports ``undecided`` rather than a verdict.
The structured per-record ``license`` block, its migration, and a ``lint
--strict`` admission rule are later parts of the same issue.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .config import Agency

# --- the vocabulary ------------------------------------------------------------


@dataclass(frozen=True)
class LicenseClass:
    """One license the audit can name, and what it asks of a reuser.

    ``id`` is the SPDX identifier where one exists. ``subsumes`` names an
    unversioned class that this versioned one makes redundant in the same note:
    "CC BY 4.0 ... published under CC BY" names one license, not two.
    """

    id: str
    share_alike: bool
    attribution_required: bool
    patterns: tuple[str, ...]
    subsumes: str = ""


# Order is presentation order only; matching tries every class.
CLASSES: tuple[LicenseClass, ...] = (
    LicenseClass(
        "ODbL-1.0",
        share_alike=True,
        attribution_required=True,
        patterns=(
            r"\bODbL\b",
            r"\bOpen Database Licen[cs]e\b",
            r"opendatacommons\.org/licenses/odbl",
        ),
    ),
    LicenseClass(
        "CC-BY-SA-4.0",
        share_alike=True,
        attribution_required=True,
        patterns=(
            r"\bCC[\s-]*BY[\s-]*SA[\s-]*4\.0\b",
            r"\bAttribution[\s-]*Share[\s-]*Alike[\s-]*4\.0\b",
        ),
        subsumes="CC-BY-SA",
    ),
    LicenseClass(
        "CC-BY-SA-3.0",
        share_alike=True,
        attribution_required=True,
        patterns=(
            r"\bCC[\s-]*BY[\s-]*SA[\s-]*3\.0\b",
            r"\bAttribution[\s-]*Share[\s-]*Alike[\s-]*3\.0\b",
        ),
        subsumes="CC-BY-SA",
    ),
    # Named without a version. Still share-alike: every CC BY-SA version is.
    LicenseClass(
        "CC-BY-SA",
        share_alike=True,
        attribution_required=True,
        patterns=(r"\bCC[\s-]*BY[\s-]*SA\b(?![\s-]*\d)",),
    ),
    LicenseClass(
        "CC-BY-4.0",
        share_alike=False,
        attribution_required=True,
        patterns=(
            r"\bCC[\s-]*BY[\s-]*4\.0\b",
            r"\bCreative Commons Attribution[\s-]*4\.0\b",
            r"creativecommons\.org/licenses/by/4\.0",
        ),
        subsumes="CC-BY",
    ),
    LicenseClass(
        "CC-BY-2.1-JP",
        share_alike=False,
        attribution_required=True,
        patterns=(r"\bCC[\s-]*BY[\s-]*2\.1[\s-]*(?:JP|Japan)\b",),
        subsumes="CC-BY",
    ),
    LicenseClass(
        "CC-BY",
        share_alike=False,
        attribution_required=True,
        patterns=(
            r"\bCC[\s-]*BY\b(?![\s-]*(?:SA|NC|ND|\d))",
            r"\bCreative Commons Attribution\b(?![\s-]*(?:Share|Non|No|\d))",
        ),
    ),
    LicenseClass(
        "CC0-1.0",
        share_alike=False,
        attribution_required=False,
        patterns=(r"\bCC0\b", r"creativecommons\.org/publicdomain/zero"),
    ),
    LicenseClass(
        "etalab-2.0",
        share_alike=False,
        attribution_required=True,
        patterns=(r"\bLicence Ouverte\b", r"\bEtalab\b"),
    ),
    LicenseClass(
        "NLOD-2.0",
        share_alike=False,
        attribution_required=True,
        patterns=(r"\bNLOD\b", r"\bNorwegian Licen[cs]e for Open Government Data\b"),
    ),
    LicenseClass(
        "DL-DE-BY-2.0",
        share_alike=False,
        attribution_required=True,
        patterns=(r"\bDatenlizenz Deutschland\W+Namensnennung\W+2\.0\b", r"dl-de/by-2-0"),
    ),
    LicenseClass(
        "DL-DE-ZERO-2.0",
        share_alike=False,
        attribution_required=False,
        patterns=(r"\bDatenlizenz Deutschland\W+Zero\b", r"dl-de/zero-2-0"),
    ),
    LicenseClass(
        "OGL-UK-3.0",
        share_alike=False,
        attribution_required=True,
        patterns=(r"\bOpen Government Licen[cs]e\W+v(?:ersion\s*)?3\.0\b",),
    ),
    # Anchored to the start of the note. Several Canadian municipalities publish
    # their own license "based on version 2.0 of the Open Government Licence -
    # Canada", and that sentence names the municipal license, not this one.
    LicenseClass(
        "OGL-Canada-2.0",
        share_alike=False,
        attribution_required=True,
        patterns=(r"^\s*Open Government Licen[cs]e\W+Canada\b",),
    ),
    LicenseClass(
        "ODC-By-1.0",
        share_alike=False,
        attribution_required=True,
        patterns=(r"opendatacommons\.org/licenses/by\b", r"\bOpen Data Commons Attribution\b"),
    ),
    # A work in the public domain by law. "Public domain dedication" is how CC0
    # describes itself, and is left to the CC0 class.
    LicenseClass(
        "public-domain",
        share_alike=False,
        attribution_required=False,
        patterns=(r"\bpublic domain\b(?![\s-]*dedication)",),
    ),
)

UNKNOWN = "unknown"

# Why a note has no class. Each says something true about the note.
NO_NOTE = "no_note"
NO_LICENSE_STATED = "no_license_stated"
LINK_ONLY = "link_only"
NOT_IN_VOCABULARY = "not_in_vocabulary"
MORE_THAN_ONE_LICENSE = "more_than_one_license"

_BY_ID: dict[str, LicenseClass] = {c.id: c for c in CLASSES}
_COMPILED: tuple[tuple[LicenseClass, tuple[re.Pattern[str], ...]], ...] = tuple(
    (c, tuple(re.compile(p, re.IGNORECASE) for p in c.patterns)) for c in CLASSES
)
_NO_LICENSE_RE = re.compile(r"^\s*No stated data licen[cs]e\b", re.IGNORECASE)
_LINK_ONLY_RE = re.compile(r"^\s*Licen[cs]e:\s*\S+\s*$", re.IGNORECASE)
# The plain text search issue #372's 2026-09-11 measurement used. A note it
# matches that names no share-alike license is reported in its own bucket, so a
# mention the vocabulary cannot read is listed rather than dropped.
_SHARE_ALIKE_WORDING_RE = re.compile(
    r"\bodbl\b|open database licen[cs]e|by[- ]sa\b|share[- ]?alike", re.IGNORECASE
)

SHARE_ALIKE_POLICY = "undecided"
SHARE_ALIKE_POLICY_SOURCE = (
    'docs/follow-ups.md, "Decide the share-alike question for records already listed"'
)
BASIS = (
    "The license_note of every registry record, classified by "
    "license_audit.CLASSES. A note naming more than one license is unknown, never "
    "a guess. No structured license block exists yet."
)


# --- classification -------------------------------------------------------------


@dataclass(frozen=True)
class Classification:
    """The license one note names, or ``unknown`` with the reason."""

    license: str
    reason: str = ""
    named: tuple[str, ...] = ()
    share_alike_wording: bool = False

    @property
    def known(self) -> bool:
        return self.license != UNKNOWN

    @property
    def share_alike(self) -> bool | None:
        """``None`` when the license is unknown: not share-alike is not the same."""
        if not self.known:
            return None
        return _BY_ID[self.license].share_alike

    @property
    def names_share_alike(self) -> bool:
        """Whether any license the note names is share-alike, classified or not."""
        return any(_BY_ID[license].share_alike for license in self.named)


def _named(note: str) -> tuple[str, ...]:
    found = [c.id for c, patterns in _COMPILED if any(p.search(note) for p in patterns)]
    subsumed = {_BY_ID[license].subsumes for license in found} - {""}
    return tuple(license for license in found if license not in subsumed)


def classify_note(note: str | None) -> Classification:
    """Classify one ``license_note``. Unambiguous or ``unknown``, never a guess."""
    text = (note or "").strip()
    if not text:
        return Classification(UNKNOWN, NO_NOTE)
    wording = bool(_SHARE_ALIKE_WORDING_RE.search(text))
    named = _named(text)
    if len(named) == 1:
        return Classification(named[0], named=named, share_alike_wording=wording)
    if len(named) > 1:
        return Classification(UNKNOWN, MORE_THAN_ONE_LICENSE, named, wording)
    if _NO_LICENSE_RE.search(text):
        return Classification(UNKNOWN, NO_LICENSE_STATED, share_alike_wording=wording)
    if _LINK_ONLY_RE.search(text):
        return Classification(UNKNOWN, LINK_ONLY, share_alike_wording=wording)
    return Classification(UNKNOWN, NOT_IN_VOCABULARY, share_alike_wording=wording)


# --- the audit ------------------------------------------------------------------


def _count(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def license_audit(agencies: Iterable[Agency]) -> dict[str, Any]:
    """Count every registry record by the license its note names.

    Covers every record, retired aliases included, because the question in
    ``docs/follow-ups.md`` is about what the registry holds. ``canonical``
    counts say how many of those are currently published.
    """
    rows = sorted(
        ((agency, classify_note(agency.license_note)) for agency in agencies),
        key=lambda row: row[0].id,
    )
    share_alike = [(a, c) for a, c in rows if c.share_alike is True]
    alongside = [(a, c) for a, c in rows if not c.known and c.names_share_alike]
    wording_only = [(a, c) for a, c in rows if c.share_alike_wording and not c.names_share_alike]
    return {
        "basis": BASIS,
        "records": len(rows),
        "canonical_records": sum(1 for a, _ in rows if a.is_canonical_feed),
        "by_license": _count(c.license for _, c in rows),
        "unknown_by_reason": _count(c.reason for _, c in rows if not c.known),
        "vocabulary": [
            {
                "id": c.id,
                "share_alike": c.share_alike,
                "attribution_required": c.attribution_required,
            }
            for c in CLASSES
        ],
        "share_alike": {
            "policy": SHARE_ALIKE_POLICY,
            "policy_source": SHARE_ALIKE_POLICY_SOURCE,
            "records": len(share_alike),
            "canonical_records": sum(1 for a, _ in share_alike if a.is_canonical_feed),
            "by_country": _count(a.country for a, _ in share_alike),
            "by_license": _count(c.license for _, c in share_alike),
            "ids": [a.id for a, _ in share_alike],
            # Not counted above, and not dropped either: a curator decides which
            # license binds. They are listed so that happens.
            "named_with_another_license": [
                {"id": a.id, "country": a.country, "named": list(c.named)} for a, c in alongside
            ],
            "mentioned_without_a_share_alike_license": [
                {"id": a.id, "country": a.country, "license": c.license} for a, c in wording_only
            ],
        },
    }


def render_text(report: dict[str, Any]) -> str:
    """The audit as plain lines for a terminal."""
    sa = report["share_alike"]
    lines = [
        f"License audit: {report['records']} registry records "
        f"({report['canonical_records']} canonical).",
        f"Basis: {report['basis']}",
        "",
        "Records by license:",
    ]
    lines.extend(f"  {license:<16} {count:>6}" for license, count in report["by_license"].items())
    lines.append("Unknown, by reason:")
    lines.extend(
        f"  {reason:<22} {count:>6}" for reason, count in report["unknown_by_reason"].items()
    )
    lines.extend(
        [
            "",
            f"Share-alike policy: {sa['policy']} ({sa['policy_source']}).",
            f"Share-alike as the only named license: {sa['records']} records "
            f"({sa['canonical_records']} canonical).",
        ]
    )
    lines.extend(f"  {country:<4} {count:>6}" for country, count in sa["by_country"].items())
    alongside = sa["named_with_another_license"]
    lines.append(
        f"Share-alike named alongside another license, for a curator: {len(alongside)} records."
    )
    lines.extend(
        f"  {row['id']} ({row['country']}): {', '.join(row['named'])}" for row in alongside
    )
    wording = sa["mentioned_without_a_share_alike_license"]
    lines.append(
        f"Share-alike terms mentioned, no share-alike license named: {len(wording)} records."
    )
    lines.extend(f"  {row['id']} ({row['country']}): {row['license']}" for row in wording)
    return "\n".join(lines) + "\n"
