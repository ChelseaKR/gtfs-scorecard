"""The structured license block, its validation, and an advisory lint (issue #372).

Every registry record carries a free-text ``license_note``. ``license_audit``
reads that prose as data. This module defines what a *structured* ``license``
block looks like once a curator (or the reviewed migration in
``license_migrate``) writes one beside the note:

.. code-block:: yaml

    license:
      id: CC-BY-4.0               # closed vocabulary, see LICENSE_IDS
      attribution_required: true  # true, false, or unknown
      redistribution_allowed: unknown
      share_alike: false
      status: unreviewed          # unreviewed, needs_review, or reviewed

Three rules shape it.

**Absence is never a value.** Each term a license states (attribution,
redistribution, share-alike) is required and takes ``true``, ``false``, or the
string ``unknown``. There is no default and no ``null``, so a term nobody
measured cannot read as a permissive one, and ``id: unknown`` is a recorded
state, not a hole. A block that says ``unknown`` for the license but ``true``
for a term is reported as inconsistent.

**Share-alike is a recorded fact, and it is admitted.** ``share_alike`` says what
the license states. Owner decision, 2026-09-19: a feed whose license requires
share-alike is admitted, with a reuse notice (``license_notice``). Nothing in
this module excludes or flags a share-alike feed for being share-alike.

**The lint is advisory, always.** ``lint_ledger`` reports records that lack a
block or carry an inconsistent one. Nothing here reads its findings to admit,
score, or publish a feed, and the CLI verb exits 0 whatever it finds. Turning it
into an admission rule is a separate change that waits on the migration, and it
would not refuse share-alike.

The parser is the source of truth. ``json_schema`` derives the committed
``registry/license.schema.json`` from the same constants, and a test holds the
two to the same verdict on a battery of blocks.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .config import Agency, LicenseBlock, Tri, utc_today
from .license_audit import CLASSES, UNKNOWN, classify_note

# --- the vocabulary ------------------------------------------------------------

#: A curator judged the terms bespoke. ``license_audit`` never emits it: deciding
#: that a note describes bespoke terms is a reading, not a pattern.
PROPRIETARY_TERMS = "proprietary-terms"
#: A named license outside the vocabulary. Needs ``name``.
OTHER = "other"

#: The closed set of ``id`` values. The license classes come from
#: ``license_audit.CLASSES`` so the audit and the ledger cannot drift apart.
LICENSE_IDS: tuple[str, ...] = (*(c.id for c in CLASSES), PROPRIETARY_TERMS, OTHER, UNKNOWN)
# A tuple, not a set: a malformed `id` (a list) must fail validation, not raise.
NAME_REQUIRED_IDS: tuple[str, ...] = (OTHER, PROPRIETARY_TERMS)

STATUS_UNREVIEWED = "unreviewed"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_REVIEWED = "reviewed"
#: ``unreviewed``: a mapping nobody has confirmed (what the migration proposes
#: for an unambiguous note). ``needs_review``: the note could not be mapped, or
#: a curator flagged the block. ``reviewed``: a named person confirmed it.
STATUSES: tuple[str, ...] = (STATUS_UNREVIEWED, STATUS_NEEDS_REVIEW, STATUS_REVIEWED)

TRI_KEYS: tuple[str, ...] = ("attribution_required", "redistribution_allowed", "share_alike")
REQUIRED_KEYS: tuple[str, ...] = ("id", *TRI_KEYS, "status")
OPTIONAL_KEYS: tuple[str, ...] = (
    "name",
    "terms_url",
    "retrieved_on",
    "attribution",
    "reviewed_by",
    "reviewed_on",
    "reviewer_note",
)
#: Every key, in the order the migration writes them.
BLOCK_KEYS: tuple[str, ...] = (
    "id",
    "name",
    "terms_url",
    "retrieved_on",
    "attribution_required",
    "attribution",
    "redistribution_allowed",
    "share_alike",
    "status",
    "reviewed_by",
    "reviewed_on",
    "reviewer_note",
)
TEXT_KEYS: tuple[str, ...] = ("name", "attribution", "reviewed_by", "reviewer_note")
DATE_KEYS: tuple[str, ...] = ("retrieved_on", "reviewed_on")

ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_PATTERN = re.compile(r"^https?://[^\s/]+\S*$")

_VOCABULARY = {c.id: c for c in CLASSES}


class LicenseBlockError(ValueError):
    """A license block is malformed; the message names every problem."""


# --- validation -----------------------------------------------------------------


def _text_problem(key: str, value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return f"license.{key} must be a non-empty string"
    return None


def _date_problem(key: str, value: object, today: dt.date) -> str | None:
    if isinstance(value, dt.date):
        # PyYAML reads an unquoted 2026-09-19 as a date, not a string.
        return f"license.{key} must be a quoted ISO date string (YYYY-MM-DD)"
    if not isinstance(value, str) or not ISO_DATE_PATTERN.fullmatch(value):
        return f"license.{key} must be an ISO date (YYYY-MM-DD)"
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        return f"license.{key} must be a valid ISO date"
    if parsed > today:
        return f"license.{key} must not be in the future"
    return None


def _url_problem(value: object) -> str | None:
    if isinstance(value, str) and URL_PATTERN.fullmatch(value):
        return None
    return f"license.terms_url must be an http(s) URL, got {value!r}"


def _tri_problem(key: str, value: object) -> str | None:
    if isinstance(value, bool) or value == UNKNOWN:
        return None
    return f"license.{key} must be true, false, or unknown, got {value!r}"


def _field_problems(raw: dict[str, Any], today: dt.date) -> list[str]:
    """Problems with each key that is present, checked one key at a time."""
    problems: list[str | None] = []
    if "id" in raw and raw["id"] not in LICENSE_IDS:
        problems.append(f"license.id must be one of {list(LICENSE_IDS)}, got {raw['id']!r}")
    problems.extend(_tri_problem(k, raw[k]) for k in TRI_KEYS if k in raw)
    if "status" in raw and raw["status"] not in STATUSES:
        problems.append(f"license.status must be one of {list(STATUSES)}, got {raw['status']!r}")
    problems.extend(_text_problem(k, raw[k]) for k in TEXT_KEYS if k in raw)
    problems.extend(_date_problem(k, raw[k], today) for k in DATE_KEYS if k in raw)
    if "terms_url" in raw:
        problems.append(_url_problem(raw["terms_url"]))
    return [p for p in problems if p]


def _cross_problems(raw: dict[str, Any]) -> list[str]:
    """Rules that tie one key to another. Structural, so the schema states them too."""
    problems: list[str] = []
    if raw.get("id") in NAME_REQUIRED_IDS and "name" not in raw:
        problems.append(f"license.name is required when license.id is {raw['id']!r}")
    if raw.get("status") == STATUS_REVIEWED:
        missing = [k for k in ("reviewed_by", "reviewed_on") if k not in raw]
        if missing:
            problems.append(
                f"a reviewed license needs {', '.join('license.' + k for k in missing)}"
            )
    else:
        stray = [k for k in ("reviewed_by", "reviewed_on") if k in raw]
        if stray and "status" in raw:
            problems.append(
                f"{', '.join('license.' + k for k in stray)} may only be set when "
                "license.status is 'reviewed'; a review nobody did must not be recorded"
            )
    return problems


def check_block(
    raw: object, *, today: dt.date | None = None
) -> tuple[LicenseBlock | None, list[str]]:
    """Validate one ``license`` mapping; the block (or None) and every problem found.

    Strict: unknown keys, missing required keys, a term that is not exactly
    ``true``, ``false`` or ``unknown``, a non-vocabulary ``id``, and a future
    date are all problems. Nothing is defaulted and nothing is coerced.
    """
    if not isinstance(raw, dict):
        return None, ["license must be a mapping of the recorded terms"]
    day = today or utc_today()
    problems: list[str] = []
    stray = sorted(str(k) for k in raw if k not in BLOCK_KEYS)
    if stray:
        problems.append(f"unknown license field(s): {', '.join(stray)}")
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        problems.append(f"license missing required field(s): {', '.join(missing)}")
    problems.extend(_field_problems(raw, day))
    problems.extend(_cross_problems(raw))
    if problems:
        return None, problems
    values: dict[str, Any] = {k: raw[k] for k in BLOCK_KEYS if k in raw}
    for key in (*TEXT_KEYS, *DATE_KEYS, "terms_url"):
        if key in values:
            values[key] = values[key].strip()
    return LicenseBlock(**values), []


def parse_block(raw: object, *, today: dt.date | None = None) -> LicenseBlock:
    """The validated block, or :class:`LicenseBlockError` naming every problem."""
    block, problems = check_block(raw, today=today)
    if block is None:
        raise LicenseBlockError("; ".join(problems))
    return block


def block_to_mapping(block: LicenseBlock) -> dict[str, Any]:
    """The block as a plain mapping in canonical key order, empty optionals left out."""
    mapping: dict[str, Any] = {}
    for key in BLOCK_KEYS:
        value = getattr(block, key)
        if key in REQUIRED_KEYS or value != "":
            mapping[key] = value
    return mapping


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    # Only the closed vocabularies are written bare. Anything else is quoted, so
    # YAML cannot read a word such as "no" or "on" as a boolean.
    if text in LICENSE_IDS or text in STATUSES:
        return text
    # A JSON string is a valid double-quoted YAML scalar.
    return json.dumps(text, ensure_ascii=False)


def block_to_yaml_lines(block: LicenseBlock, *, indent: int) -> list[str]:
    """The block as YAML text lines, ``license:`` first, at the given indent."""
    pad = " " * indent
    lines = [f"{pad}license:"]
    lines.extend(f"{pad}  {k}: {_yaml_scalar(v)}" for k, v in block_to_mapping(block).items())
    return lines


# --- the JSON Schema ------------------------------------------------------------


def json_schema() -> dict[str, Any]:
    """The JSON Schema of a ``license`` block, derived from the constants above.

    Structural rules only: types, the closed vocabulary, required keys, and the
    two conditional rules. Real calendar dates and "not in the future" need the
    parser, which stays the source of truth. ``registry/license.schema.json`` is
    this function's output, and a test fails when the two differ.
    """
    text = {"type": "string", "pattern": r"\S"}
    date = {"type": "string", "pattern": ISO_DATE_PATTERN.pattern}
    tri = {"enum": [True, False, UNKNOWN]}
    properties: dict[str, Any] = {
        "id": {"enum": list(LICENSE_IDS)},
        "name": text,
        "terms_url": {"type": "string", "pattern": URL_PATTERN.pattern},
        "retrieved_on": date,
        "attribution_required": tri,
        "attribution": text,
        "redistribution_allowed": tri,
        "share_alike": tri,
        "status": {"enum": list(STATUSES)},
        "reviewed_by": text,
        "reviewed_on": date,
        "reviewer_note": text,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Registry license block",
        "description": (
            "The structured `license` block of a registry record (issue #372). It records "
            "what a license states and never decides whether the project may list the feed. "
            "Every term is true, false, or unknown; there is no default, so an unmeasured "
            "term cannot read as a permissive one. Generated from "
            "pipeline/src/scorecard_pipeline/license_ledger.py; the parser there also checks "
            "real calendar dates and that a date is not in the future."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": list(REQUIRED_KEYS),
        "properties": {k: properties[k] for k in BLOCK_KEYS},
        "allOf": [
            {
                "if": {
                    "properties": {"id": {"enum": list(NAME_REQUIRED_IDS)}},
                    "required": ["id"],
                },
                "then": {"required": ["name"]},
            },
            {
                "if": {
                    "properties": {"status": {"const": STATUS_REVIEWED}},
                    "required": ["status"],
                },
                "then": {"required": ["reviewed_by", "reviewed_on"]},
                "else": {
                    "not": {"anyOf": [{"required": ["reviewed_by"]}, {"required": ["reviewed_on"]}]}
                },
            },
        ],
    }


def render_schema() -> str:
    """``json_schema`` as the exact text committed at ``registry/license.schema.json``."""
    return json.dumps(json_schema(), indent=2, ensure_ascii=False) + "\n"


# --- the advisory lint ----------------------------------------------------------

NO_LICENSE_BLOCK = "no_license_block"
LICENSE_UNKNOWN = "license_unknown"
NEEDS_REVIEW_STATUS = "needs_review_status"
UNKNOWN_WITH_FACTS = "unknown_with_facts"
SHARE_ALIKE_MISMATCH = "share_alike_mismatch"
ATTRIBUTION_MISMATCH = "attribution_mismatch"
NOTE_DISAGREES = "note_disagrees"
ATTRIBUTION_TEXT_WITHOUT_REQUIREMENT = "attribution_text_without_requirement"

#: Findings about a block that says something false or contradictory.
INCONSISTENT_KINDS = (
    UNKNOWN_WITH_FACTS,
    SHARE_ALIKE_MISMATCH,
    ATTRIBUTION_MISMATCH,
    NOTE_DISAGREES,
    ATTRIBUTION_TEXT_WITHOUT_REQUIREMENT,
)
#: Findings about a record that has no usable answer yet.
INCOMPLETE_KINDS = (NO_LICENSE_BLOCK, LICENSE_UNKNOWN, NEEDS_REVIEW_STATUS)
KINDS = (*INCONSISTENT_KINDS, *INCOMPLETE_KINDS)

ADVISORY_NOTICE = (
    "ADVISORY ONLY. This report changes nothing about which feeds are admitted, scored, "
    "or published, and the exit status is 0 whatever it finds."
)


@dataclass(frozen=True)
class LedgerFinding:
    agency_id: str
    kind: str
    detail: str


def _note_reading(agency: Agency) -> str:
    """What the audit reads in the free-text note, for a curator's first look."""
    reading = classify_note(agency.license_note)
    if reading.known:
        return f"license_note reads as {reading.license}"
    return f"license_note is unknown ({reading.reason})"


def _contradicts(recorded: Tri, stated: bool) -> bool:
    """A definite recorded value that disagrees with a definite stated one."""
    return isinstance(recorded, bool) and recorded is not stated


def _unknown_findings(agency: Agency, block: LicenseBlock) -> list[LedgerFinding]:
    """A block that records no license, or records facts about one it does not name."""
    if block.id == UNKNOWN:
        found = [
            LedgerFinding(agency.id, LICENSE_UNKNOWN, f"license.id is unknown ({block.status})")
        ]
        facts = [k for k in TRI_KEYS if getattr(block, k) != UNKNOWN]
        if facts:
            found.append(
                LedgerFinding(
                    agency.id,
                    UNKNOWN_WITH_FACTS,
                    f"license.id is unknown but {', '.join(facts)} is recorded as a fact; "
                    "nothing is known about an unknown license's terms",
                )
            )
        return found
    if block.status == STATUS_NEEDS_REVIEW:
        return [
            LedgerFinding(agency.id, NEEDS_REVIEW_STATUS, f"{block.id} is flagged needs_review")
        ]
    return []


def _vocabulary_findings(agency: Agency, block: LicenseBlock) -> list[LedgerFinding]:
    """A recorded fact that contradicts what the named license is known to state."""
    vocab = _VOCABULARY.get(block.id)
    if vocab is None:
        return []
    found: list[LedgerFinding] = []
    if _contradicts(block.share_alike, vocab.share_alike):
        found.append(
            LedgerFinding(
                agency.id,
                SHARE_ALIKE_MISMATCH,
                f"license.share_alike is {block.share_alike} but {block.id} is "
                f"{'' if vocab.share_alike else 'not '}share-alike",
            )
        )
    if _contradicts(block.attribution_required, vocab.attribution_required):
        found.append(
            LedgerFinding(
                agency.id,
                ATTRIBUTION_MISMATCH,
                f"license.attribution_required is {block.attribution_required} but {block.id} "
                f"{'requires' if vocab.attribution_required else 'does not require'} attribution",
            )
        )
    return found


def _text_findings(agency: Agency, block: LicenseBlock) -> list[LedgerFinding]:
    """The block against its own credit text and against the free-text note."""
    found: list[LedgerFinding] = []
    if block.attribution and block.attribution_required is False:
        found.append(
            LedgerFinding(
                agency.id,
                ATTRIBUTION_TEXT_WITHOUT_REQUIREMENT,
                "license.attribution gives credit text but attribution_required is false",
            )
        )
    reading = classify_note(agency.license_note)
    if reading.known and block.id != UNKNOWN and reading.license != block.id:
        found.append(
            LedgerFinding(
                agency.id,
                NOTE_DISAGREES,
                f"license.id is {block.id} but license_note reads as {reading.license}",
            )
        )
    return found


def _block_findings(agency: Agency, block: LicenseBlock) -> list[LedgerFinding]:
    return [
        *_unknown_findings(agency, block),
        *_vocabulary_findings(agency, block),
        *_text_findings(agency, block),
    ]


def lint_ledger(agencies: Iterable[Agency]) -> list[LedgerFinding]:
    """Findings across the registry: no block, no answer yet, or a contradiction.

    Advisory. The result is a report; nothing consumes it to admit, score, or
    publish a feed. A record with an unknown license never lints clean, whether
    it has no block or a block that says ``unknown``.
    """
    findings: list[LedgerFinding] = []
    for agency in agencies:
        if agency.license_block is None:
            findings.append(LedgerFinding(agency.id, NO_LICENSE_BLOCK, _note_reading(agency)))
        else:
            findings.extend(_block_findings(agency, agency.license_block))
    order = {kind: i for i, kind in enumerate(KINDS)}
    findings.sort(key=lambda f: (order.get(f.kind, len(order)), f.agency_id))
    return findings


def ledger_report(agencies: Iterable[Agency]) -> dict[str, Any]:
    """The lint as a JSON-ready report, with the advisory notice inside it."""
    records = list(agencies)
    findings = lint_ledger(records)
    by_kind = {kind: 0 for kind in KINDS}
    for finding in findings:
        by_kind[finding.kind] = by_kind.get(finding.kind, 0) + 1
    with_block = [a for a in records if a.license_block is not None]
    flagged = {f.agency_id for f in findings}
    return {
        "advisory": True,
        "notice": ADVISORY_NOTICE,
        "records": len(records),
        "with_block": len(with_block),
        "without_block": len(records) - len(with_block),
        "by_status": {
            status: sum(
                1 for a in with_block if a.license_block and a.license_block.status == status
            )
            for status in STATUSES
        },
        "clean_records": sum(1 for a in records if a.id not in flagged),
        "by_kind": by_kind,
        "findings": [
            {"agency_id": f.agency_id, "kind": f.kind, "detail": f.detail} for f in findings
        ],
    }
