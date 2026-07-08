#!/usr/bin/env python3
"""One version of the truth (RELEASE-AND-VERSIONING-STANDARD REL-02).

Parses the repo's hand-maintained version declarations and asserts they all
agree with `pipeline/pyproject.toml`'s `[project].version`, which is the
single source of truth (see the comment there). Catches drift the moment any
one of them is bumped without the others — the failure mode a 2026-07-05
audit found live (pyproject 0.1.0, CITATION.cff 0.1.0, server.json 1.0.0).

Run before committing a version bump:

    python3 pipeline/scripts/check_versions.py
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pipeline" / "pyproject.toml").read_text())
    version = data["project"]["version"]
    if not isinstance(version, str):
        raise TypeError("pipeline/pyproject.toml [project].version must be a string")
    return version


def _citation_version() -> str:
    text = (REPO_ROOT / "CITATION.cff").read_text()
    # A tiny, dependency-free scalar read (avoids a PyYAML round-trip for one line).
    match = re.search(r"(?m)^version:\s*(\S+)\s*$", text)
    if not match:
        raise ValueError("CITATION.cff has no top-level 'version:' line")
    return match.group(1).strip("\"'")


def _server_json_version() -> str:
    data = json.loads((REPO_ROOT / "server.json").read_text())
    version = data["version"]
    if not isinstance(version, str):
        raise TypeError("server.json 'version' must be a string")
    return version


def main() -> int:
    sources = {
        "pipeline/pyproject.toml [project].version": _pyproject_version(),
        "CITATION.cff version": _citation_version(),
        "server.json version": _server_json_version(),
    }
    versions = set(sources.values())
    if len(versions) == 1:
        print(f"OK  all version declarations agree: {versions.pop()}")
        return 0
    print("Version declarations disagree (REL-02):")
    for name, value in sources.items():
        print(f"  {value!r:<10} {name}")
    print(
        "\nPick one source of truth (pipeline/pyproject.toml today) and update the "
        "others to match."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
