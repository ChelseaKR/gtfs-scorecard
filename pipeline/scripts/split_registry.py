#!/usr/bin/env python3
"""Perform the one-time manifest-backed agency-registry split (FIX-12).

The current registry has a safer explicit-manifest loader, while the earlier
reviewed mechanical split in PR #71 contains the location backfill needed to
place legacy US entries. This script combines those two reviewed inputs:

* current ``agencies.yaml`` is the only source of entry content;
* PR #71 head ``36423f1`` contributes only its id-to-state mapping;
* output is ``registry/index.yaml`` plus small country/subdivision shards and
  ``registry/intake.yaml`` for entries that remain honestly unlocated.

Entry blocks are moved textually, preserving comments and hand formatting.
Run from a clean repository root before the split is committed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_SRC = REPO_ROOT / "pipeline" / "src"
sys.path.insert(0, str(PIPELINE_SRC))

from scorecard_pipeline.location import normalize_subdivision  # noqa: E402

PR71_HEAD = "36423f197a2176e78fa395f6a5e583b4adc6de60"
ENTRY_RE = re.compile(r"^  - id:\s*(\S+)\s*$")

SHARD_HEADER = """\
# {title} — one manifest-listed shard of the GTFS Scorecard registry.
#
# The field reference and contribution workflow live in registry/README.md.
# Every id must be unique across every shard listed by registry/index.yaml.
agencies:
"""

INTAKE_HEADER = """\
# Intake and honestly unlocated agencies.
#
# New self-serve submissions land here. A curator may move an entry to its
# country/subdivision shard once its location has been verified.
agencies:
"""


def _git_text(treeish: str, path: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed git binary/tree; path comes from that tree
        ["/usr/bin/git", "show", f"{treeish}:{path}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _pr71_states() -> dict[str, str]:
    """Reviewed id-to-state data from PR #71; no entry content is imported."""
    listing = subprocess.run(  # noqa: S603 - fixed git binary and reviewed immutable tree
        ["/usr/bin/git", "ls-tree", "-r", "--name-only", PR71_HEAD],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    paths = [
        path
        for path in listing
        if path == "agencies.yaml"
        or (path.startswith("registry/") and path.endswith((".yaml", ".yml")))
    ]
    states: dict[str, str] = {}
    for path in paths:
        raw = yaml.safe_load(_git_text(PR71_HEAD, path)) or {}
        for entry in raw.get("agencies", []):
            if not isinstance(entry, dict):
                continue
            agency_id = str(entry.get("id") or "")
            state = str(entry.get("state") or "").strip()
            if agency_id and state:
                states[agency_id] = state
    return states


def _entry_blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    starts = [index for index, line in enumerate(lines) if ENTRY_RE.match(line)]
    if not starts:
        raise SystemExit("agencies.yaml has no entries to split")
    adjusted: list[int] = []
    for start in starts:
        while start > 0 and lines[start - 1].lstrip().startswith("#"):
            start -= 1
        adjusted.append(start)
    bounds = [*adjusted, len(lines)]
    blocks: list[tuple[str, list[str]]] = []
    for index, start in enumerate(adjusted):
        block = lines[start : bounds[index + 1]]
        while block and not block[-1].strip():
            block.pop()
        match = next(match for line in block if (match := ENTRY_RE.match(line)))
        blocks.append((match.group(1), block))
    return blocks


def _with_location(block: list[str], *, code: str, name: str) -> list[str]:
    if any(line.strip().startswith("subdivision_code:") for line in block):
        return block
    insert_at = next(index + 1 for index, line in enumerate(block) if line.startswith("    name:"))
    return [
        *block[:insert_at],
        f"    subdivision_code: {code}",
        f"    subdivision_name: {name}",
        *block[insert_at:],
    ]


def _slug(code: str) -> str:
    suffix = code.split("-", 1)[1] if "-" in code else code
    return re.sub(r"[^a-z0-9]+", "-", suffix.lower()).strip("-")


def main() -> int:
    source = REPO_ROOT / "agencies.yaml"
    if not source.is_file():
        raise SystemExit("agencies.yaml is absent; the manifest migration is already complete")
    text = source.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    entries = {
        str(entry["id"]): entry
        for entry in raw.get("agencies", [])
        if isinstance(entry, dict) and entry.get("id")
    }
    states = _pr71_states()
    shards: dict[Path, list[list[str]]] = {}
    titles: dict[Path, str] = {}
    intake: list[list[str]] = []

    for agency_id, original_block in _entry_blocks(text.splitlines()):
        entry = entries[agency_id]
        country = str(entry.get("country") or "US").strip().upper()
        code = str(entry.get("subdivision_code") or "").strip().upper()
        name = str(entry.get("subdivision_name") or "").strip()
        if not code:
            state = str(entry.get("state") or states.get(agency_id) or "").strip()
            code, name = normalize_subdivision(country, state)
        if not code or not name:
            intake.append(original_block)
            continue
        block = _with_location(original_block, code=code, name=name)
        relative = Path("registry") / country.lower() / f"{_slug(code)}.yaml"
        shards.setdefault(relative, []).append(block)
        titles[relative] = f"{name} ({country}) agencies"

    registry_root = REPO_ROOT / "registry"
    if registry_root.exists():
        raise SystemExit("registry/ already exists; refusing to overwrite a partial migration")
    for relative, blocks in sorted(shards.items()):
        path = REPO_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n\n".join("\n".join(block) for block in blocks)
        path.write_text(
            SHARD_HEADER.format(title=titles[relative]) + body + "\n",
            encoding="utf-8",
        )

    intake_path = registry_root / "intake.yaml"
    intake_body = "\n\n".join("\n".join(block) for block in intake)
    intake_path.write_text(INTAKE_HEADER + intake_body + "\n", encoding="utf-8")
    paths = [Path("registry/intake.yaml"), *sorted(shards)]
    manifest = "shards:\n" + "".join(f"  - {path.as_posix()}\n" for path in paths)
    (registry_root / "index.yaml").write_text(manifest, encoding="utf-8")
    source.unlink()

    print(f"wrote {len(shards)} located shards; kept {len(intake)} entries in intake")
    return 0


if __name__ == "__main__":
    sys.exit(main())
