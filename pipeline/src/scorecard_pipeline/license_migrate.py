"""Propose structured ``license`` blocks from the free-text ``license_note`` (issue #372).

``scorecard license-migrate`` is a dry run unless ``--apply`` is given, and it
proposes only what the note itself supports:

- A note that names exactly one license in ``license_audit.CLASSES`` gets a block
  for that license, with ``share_alike`` and ``attribution_required`` taken from
  the vocabulary, ``redistribution_allowed: unknown`` (a note says nothing about
  redistributing feed bytes), and ``status: unreviewed``.
- Every other note gets ``id: unknown``, every term ``unknown``, and
  ``status: needs_review`` with the reason in ``reviewer_note``. Nothing is
  guessed, and an ``unknown`` is never turned into a permissive value.
- A record that already carries a block is left alone, so a second run proposes
  nothing (``already_structured``).

The migration never writes ``status: reviewed``, ``reviewed_by`` or
``reviewed_on``: a pattern is not a review. It also never fills ``terms_url``,
``retrieved_on`` or ``attribution``, which need someone to read the terms.

``--apply`` edits the registry shards as text, inserting the block after each
record's last field so comments and field order survive, and it verifies every
edit by re-reading the YAML before it writes a byte: each record must equal its
old self plus exactly the proposed ``license`` mapping. If any record cannot be
placed or verified, nothing is written. The report names the mode, so a dry run
cannot be mistaken for an applied one.
"""

from __future__ import annotations

import copy
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .agencies import registry_paths
from .config import TRI_UNKNOWN, Agency, LicenseBlock
from .license_audit import (
    CLASSES,
    LINK_ONLY,
    MORE_THAN_ONE_LICENSE,
    NO_LICENSE_STATED,
    NO_NOTE,
    NOT_IN_VOCABULARY,
    UNKNOWN,
    Classification,
    classify_note,
)
from .license_ledger import (
    STATUS_NEEDS_REVIEW,
    STATUS_UNREVIEWED,
    block_to_mapping,
    block_to_yaml_lines,
    check_block,
)

OUTCOME_PROPOSED = "proposed"
OUTCOME_NEEDS_REVIEW = "needs_review"
OUTCOME_ALREADY = "already_structured"
OUTCOMES = (OUTCOME_PROPOSED, OUTCOME_NEEDS_REVIEW, OUTCOME_ALREADY)

_REASON_TEXT = {
    NO_NOTE: "license_note is empty",
    NO_LICENSE_STATED: "license_note says no license is stated",
    LINK_ONLY: "license_note is only a link",
    NOT_IN_VOCABULARY: "license_note names terms the vocabulary does not hold",
}
_BY_ID = {c.id: c for c in CLASSES}

#: A record starts at two spaces of indent; its fields sit at four.
_RECORD_START = re.compile(r"^  - id:\s*[\"']?([a-z0-9][a-z0-9_-]*)[\"']?\s*(?:#.*)?$")
_FIELD_INDENT = 4


class MigrationError(RuntimeError):
    """The registry text could not be edited safely; nothing was written."""


@dataclass(frozen=True)
class MigrationEntry:
    """What the migration proposes for one record, and why."""

    agency_id: str
    country: str
    canonical: bool
    outcome: str
    block: LicenseBlock | None
    detail: str


def _reviewer_reason(reading: Classification) -> str:
    if reading.reason == MORE_THAN_ONE_LICENSE:
        return f"license_note names more than one license: {', '.join(reading.named)}"
    return _REASON_TEXT.get(reading.reason, f"license_note could not be mapped ({reading.reason})")


def propose(agency: Agency) -> MigrationEntry:
    """The block proposed for one record: mechanical, or ``needs_review``."""
    if agency.license_block is not None:
        return MigrationEntry(
            agency.id,
            agency.country,
            agency.is_canonical_feed,
            OUTCOME_ALREADY,
            None,
            f"already carries a license block ({agency.license_block.id})",
        )
    reading = classify_note(agency.license_note)
    if reading.known:
        vocab = _BY_ID[reading.license]
        block = LicenseBlock(
            id=reading.license,
            attribution_required=vocab.attribution_required,
            redistribution_allowed=TRI_UNKNOWN,
            share_alike=vocab.share_alike,
            status=STATUS_UNREVIEWED,
        )
        return MigrationEntry(
            agency.id,
            agency.country,
            agency.is_canonical_feed,
            OUTCOME_PROPOSED,
            block,
            "the license_note names one license in the vocabulary",
        )
    reason = _reviewer_reason(reading)
    block = LicenseBlock(
        id=UNKNOWN,
        attribution_required=TRI_UNKNOWN,
        redistribution_allowed=TRI_UNKNOWN,
        share_alike=TRI_UNKNOWN,
        status=STATUS_NEEDS_REVIEW,
        reviewer_note=reason,
    )
    return MigrationEntry(
        agency.id, agency.country, agency.is_canonical_feed, OUTCOME_NEEDS_REVIEW, block, reason
    )


def plan_migration(agencies: Iterable[Agency]) -> list[MigrationEntry]:
    """One entry per record, by id. Pure: reads records, writes nothing."""
    return sorted((propose(a) for a in agencies), key=lambda e: e.agency_id)


def migration_report(
    plan: list[MigrationEntry], *, applied: bool, files_changed: int = 0
) -> dict[str, Any]:
    """The plan as a JSON-ready report that says whether anything was written."""
    proposed = [e for e in plan if e.outcome == OUTCOME_PROPOSED and e.block]
    review = [e for e in plan if e.outcome == OUTCOME_NEEDS_REVIEW]
    return {
        "mode": "apply" if applied else "dry-run",
        "wrote_registry": applied and files_changed > 0,
        "files_changed": files_changed,
        "records": len(plan),
        "by_outcome": {o: sum(1 for e in plan if e.outcome == o) for o in OUTCOMES},
        "proposed_by_license": dict(
            sorted(Counter(e.block.id for e in proposed if e.block).items())
        ),
        "proposed_share_alike": sum(1 for e in proposed if e.block and e.block.share_alike is True),
        "needs_review_by_reason": dict(
            sorted(Counter(e.detail.split(":")[0] for e in review).items())
        ),
        "never_written": ["status: reviewed", "reviewed_by", "reviewed_on"],
        "rows": [
            {
                "agency_id": e.agency_id,
                "country": e.country,
                "canonical": e.canonical,
                "outcome": e.outcome,
                "license": e.block.id if e.block else "",
                "share_alike": e.block.share_alike if e.block else "",
                "detail": e.detail,
            }
            for e in plan
        ],
    }


def render_rows(report: dict[str, Any]) -> str:
    """One tab-separated line per record: outcome, id, country, license, share-alike, detail."""
    lines = [
        "\t".join(
            (
                r["outcome"],
                r["agency_id"],
                r["country"],
                r["license"] or "-",
                f"share_alike={r['share_alike']}".lower() if r["license"] else "-",
                r["detail"],
            )
        )
        for r in report["rows"]
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def render_summary(report: dict[str, Any]) -> str:
    """The verdict, for stderr: the mode first, then what would change."""
    outcomes = report["by_outcome"]
    if report["mode"] == "dry-run":
        head = (
            "License migration DRY RUN: nothing was written. Re-run with --apply to write "
            "the blocks proposed below."
        )
    elif report["files_changed"]:
        head = f"License migration APPLIED: {report['files_changed']} registry file(s) written."
    else:
        head = "License migration APPLIED: nothing to write, the registry was left untouched."
    lines = [
        head,
        f"{report['records']} records: {outcomes[OUTCOME_PROPOSED]} proposed from a note "
        f"that names one license, {outcomes[OUTCOME_NEEDS_REVIEW]} need review, "
        f"{outcomes[OUTCOME_ALREADY]} already structured.",
        "Proposed by license: "
        + (", ".join(f"{k} {v}" for k, v in report["proposed_by_license"].items()) or "none")
        + ".",
        f"Of those, {report['proposed_share_alike']} state a share-alike license. That is a "
        "recorded fact, not a listing decision; the share-alike question is the owner's.",
        "Needs review, by reason: "
        + (", ".join(f"{k} ({v})" for k, v in report["needs_review_by_reason"].items()) or "none")
        + ".",
        "Every proposal is status unreviewed or needs_review; the migration never writes a "
        "reviewer or a review date.",
    ]
    return "\n".join(lines) + "\n"


# --- applying -------------------------------------------------------------------


def _record_spans(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Map each record id to its (first line, one past its last field line)."""
    starts = [(i, m.group(1)) for i, line in enumerate(lines) if (m := _RECORD_START.match(line))]
    spans: dict[str, tuple[int, int]] = {}
    for n, (start, agency_id) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        # Blank lines and shallow comments after the last field belong to the
        # next record (or the file); a comment at field depth stays with this one.
        while end - 1 > start and _is_trailer(lines[end - 1]):
            end -= 1
        spans[agency_id] = (start, end)
    return spans


def _is_trailer(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return stripped.startswith("#") and len(line) - len(line.lstrip()) < _FIELD_INDENT


def _insert(text: str, blocks: dict[str, LicenseBlock]) -> str:
    """The shard text with each block inserted after its record's last field."""
    lines = text.split("\n")
    spans = _record_spans(lines)
    for agency_id in blocks:
        if agency_id not in spans:
            raise MigrationError(f"could not find the record {agency_id!r} in the shard text")
    # Bottom-up so earlier line numbers stay valid.
    for agency_id in sorted(blocks, key=lambda a: spans[a][1], reverse=True):
        _, end = spans[agency_id]
        lines[end:end] = block_to_yaml_lines(blocks[agency_id], indent=_FIELD_INDENT)
    return "\n".join(lines)


def _verify(old: str, new: str, blocks: dict[str, LicenseBlock], label: str) -> None:
    """Every record equals its old self plus exactly its proposed mapping."""
    before = yaml.safe_load(old)["agencies"]
    after = yaml.safe_load(new)["agencies"]
    if len(before) != len(after):
        raise MigrationError(f"{label}: the edit changed the number of records")
    for was, now in zip(before, after, strict=True):
        expected = copy.deepcopy(was)
        block = blocks.get(was["id"])
        if block is not None:
            expected["license"] = block_to_mapping(block)
            checked, problems = check_block(now.get("license"))
            if checked is None:
                raise MigrationError(f"{label}: {was['id']}: {'; '.join(problems)}")
        if now != expected:
            raise MigrationError(f"{label}: record {was['id']!r} changed beyond its license block")


def _write_atomically(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def apply_migration(plan: list[MigrationEntry], *, root: Path | None = None) -> int:
    """Write the planned blocks into the registry shards; the number of files changed.

    Two passes: every shard is edited and verified in memory first, and only
    then are any written, so a failure leaves the registry as it was. Records
    that already carry a block are not in the plan's writable set, which is why
    a second run changes nothing.
    """
    writable = {e.agency_id: e.block for e in plan if e.outcome != OUTCOME_ALREADY and e.block}
    if not writable:
        return 0
    edits: list[tuple[Path, str]] = []
    placed: set[str] = set()
    for path in registry_paths(root):
        old = path.read_text(encoding="utf-8")
        ids_here = {m.group(1) for line in old.split("\n") if (m := _RECORD_START.match(line))}
        blocks = {a: b for a, b in writable.items() if a in ids_here}
        if not blocks:
            continue
        new = _insert(old, blocks)
        _verify(old, new, blocks, str(path))
        edits.append((path, new))
        placed |= set(blocks)
    missing = sorted(set(writable) - placed)
    if missing:
        raise MigrationError(
            f"{len(missing)} record(s) were not found in any registry shard: "
            f"{', '.join(missing[:5])}"
        )
    for path, new in edits:
        _write_atomically(path, new)
    return len(edits)
