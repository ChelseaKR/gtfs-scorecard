"""Successors for feed records the registry dedupe removed as duplicates.

The 2026-07-11 dedupe (#69) dropped 320 records that duplicated a kept
record's feed URL apart from the URL scheme. Their scorecard pages had been
public, and search engines kept sending readers to them after they started
answering 404. ``removed-duplicate-ids.yaml`` at the repository root records
each removed id with the record it duplicated, so the renderer can point the
old URL at the successor's current scorecard instead of a dead page.

This module only reads and validates that file. Resolution against the
current registry and published set happens in ``render_site``, which owns the
alias rules every other redirect follows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

REMOVED_TWINS_FILENAME = "removed-duplicate-ids.yaml"
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class RemovedTwin:
    """One removed record id and the kept record it duplicated."""

    id: str
    kept: str


def read_removed_twins(root: Path) -> list[RemovedTwin]:
    """Read and validate the removed-twin file under ``root``.

    A missing file means there is nothing to redirect. A present but
    malformed file raises ``ValueError``: a quietly empty list would turn
    every listed URL back into a 404 with nothing saying why.
    """
    path = root / REMOVED_TWINS_FILENAME
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError(f"{path}: expected a mapping with schema_version: 1")
    rows = raw.get("twins")
    if not isinstance(rows, list):
        raise ValueError(f"{path}: 'twins' must be a list")
    twins: list[RemovedTwin] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"id", "kept"}:
            raise ValueError(f"{path}: twins[{index}] must have exactly 'id' and 'kept'")
        removed_id, kept = str(row["id"]), str(row["kept"])
        if not (_SLUG.match(removed_id) and _SLUG.match(kept)):
            raise ValueError(f"{path}: twins[{index}] ids must be lowercase slugs")
        if removed_id == kept:
            raise ValueError(f"{path}: twins[{index}] cannot name itself as its successor")
        if removed_id in seen:
            raise ValueError(f"{path}: twins[{index}] repeats id {removed_id!r}")
        seen.add(removed_id)
        twins.append(RemovedTwin(removed_id, kept))
    return twins


def load_removed_twins() -> list[RemovedTwin]:
    """Removed twins on record for this checkout."""
    from .config import repo_root

    return read_removed_twins(repo_root())
