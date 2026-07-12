#!/usr/bin/env python3
"""Split agencies.yaml into per-state registry shards (ideation FIX-12).

One-time (but rerunnable) mechanical move: every entry that declares a
``state`` goes to ``registry/<country>/<state>.yaml``; entries without one
stay in agencies.yaml, which remains the intake file the submission flow and
docs/add-your-agency.md append to. The move is textual, not a YAML
round-trip, so each entry keeps its comments and hand-written formatting,
the same guarantee the registry's other textual editors make.

Run from the repo root:

    python3 pipeline/scripts/split_registry.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRY_RE = re.compile(r"^  - id:\s*(\S+)\s*$")

SHARD_HEADER = """\
# {title} agencies — one curated shard of the registry (FIX-12).
#
# The field reference lives at the top of agencies.yaml, and
# docs/add-your-agency.md explains how to add an agency (new entries land in
# agencies.yaml first; a curator moves them here once located). Every shard
# is merged with agencies.yaml at load time, and ids must be unique across
# all of them.
agencies:
"""


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def split_entry_blocks(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """The header (through ``agencies:``) and one comment-carrying block per entry."""
    starts = [i for i, line in enumerate(lines) if ENTRY_RE.match(line)]
    if not starts:
        raise SystemExit("agencies.yaml has no entries to split")
    # Pull each entry's immediately-preceding comment lines into its block.
    adjusted: list[int] = []
    for start in starts:
        while start > 0 and lines[start - 1].lstrip().startswith("#"):
            start -= 1
        adjusted.append(start)
    header = lines[: adjusted[0]]
    blocks: list[tuple[str, list[str]]] = []
    bounds = adjusted + [len(lines)]
    for i, start in enumerate(adjusted):
        block = lines[start : bounds[i + 1]]
        while block and not block[-1].strip():
            block.pop()
        match = next(m for line in block if (m := ENTRY_RE.match(line)))
        blocks.append((match.group(1), block))
    return header, blocks


def main() -> int:
    registry_file = REPO_ROOT / "agencies.yaml"
    text = registry_file.read_text()
    parsed = {
        entry["id"]: entry for entry in yaml.safe_load(text)["agencies"] if isinstance(entry, dict)
    }
    header, blocks = split_entry_blocks(text.splitlines())

    shards: dict[Path, list[list[str]]] = {}
    shard_titles: dict[Path, str] = {}
    intake: list[list[str]] = []
    for agency_id, block in blocks:
        entry = parsed.get(agency_id, {})
        state = str(entry.get("state") or "").strip()
        if not state:
            intake.append(block)
            continue
        country = str(entry.get("country") or "US").strip()
        path = REPO_ROOT / "registry" / country.lower() / f"{slug(state)}.yaml"
        shards.setdefault(path, []).append(block)
        shard_titles[path] = f"{state} ({country})"

    for path, shard_blocks in sorted(shards.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n\n".join("\n".join(block) for block in shard_blocks)
        path.write_text(SHARD_HEADER.format(title=shard_titles[path]) + body + "\n")

    intake_body = "\n\n".join("\n".join(block) for block in intake)
    registry_file.write_text("\n".join(header) + "\n" + intake_body + "\n")

    print(f"wrote {len(shards)} shards, kept {len(intake)} entries in agencies.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
