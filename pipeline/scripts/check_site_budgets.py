#!/usr/bin/env python3
"""Enforce deterministic byte budgets on generated HTML pages."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path, PurePosixPath
from typing import Any


def validate_pattern(pattern: str, *, allow_glob: bool) -> None:
    """Reject paths that can escape the generated-site root."""
    if not pattern:
        raise ValueError("budget path must not be empty")
    if "\\" in pattern:
        raise ValueError(f"budget path must use POSIX separators: {pattern!r}")
    path = PurePosixPath(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"budget path must stay inside the site root: {pattern!r}")
    if not allow_glob and glob.has_magic(pattern):
        raise ValueError(f"required budget path must not contain a glob: {pattern!r}")


def _budget_mapping(config: dict[str, Any], key: str, *, allow_glob: bool) -> dict[str, int]:
    raw = config.get(key)
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"{key!r} must be a non-empty object")

    budgets: dict[str, int] = {}
    for pattern, limit in raw.items():
        if not isinstance(pattern, str):
            raise ValueError(f"{key!r} keys must be strings")
        validate_pattern(pattern, allow_glob=allow_glob)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError(f"budget for {pattern!r} must be a positive integer")
        budgets[pattern] = limit
    return budgets


def load_config(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    """Load and validate the page-size budget file."""
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read budget config {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("budget config must be a JSON object")
    if config.get("schema_version") != 1:
        raise ValueError("budget config schema_version must be 1")

    required = _budget_mapping(config, "required", allow_glob=False)
    patterns = _budget_mapping(config, "patterns", allow_glob=True)
    return required, patterns


def _overage(path: Path, site_root: Path, limit: int) -> str | None:
    size = path.stat().st_size
    if size <= limit:
        return None
    relative = path.relative_to(site_root).as_posix()
    return f"{relative}: {size:,} bytes exceeds {limit:,}-byte budget"


def check_site(
    site_root: Path,
    required: dict[str, int],
    patterns: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Return structural failures separately from advisory-eligible overages."""
    if not site_root.is_dir():
        return [f"site root does not exist or is not a directory: {site_root}"], []

    structural_failures: list[str] = []
    overages: list[str] = []
    for relative, limit in required.items():
        path = site_root / relative
        if not path.is_file():
            structural_failures.append(f"required generated page is missing: {relative}")
            continue
        if violation := _overage(path, site_root, limit):
            overages.append(violation)

    for pattern, limit in patterns.items():
        matches = sorted(path for path in site_root.glob(pattern) if path.is_file())
        if not matches:
            structural_failures.append(f"generated-page pattern matched no files: {pattern}")
            continue
        overages.extend(
            violation
            for path in matches
            if (violation := _overage(path, site_root, limit)) is not None
        )
    return structural_failures, overages


def budget_headroom(
    site_root: Path,
    required: dict[str, int],
    patterns: dict[str, int],
) -> list[tuple[str, str, int, int]]:
    """(budget, largest matching page, its bytes, the limit) for every budget.

    A budget that passes says nothing about how close it came. `**/index.html`
    is set at 3,407,872 bytes and the largest page it matches in this repository
    is 504,251, so it has never been within a factor of six of firing: passing
    and being unable to fail look identical from the outside. Printing the
    tightest page under each budget makes the slack a number somebody can read
    off a build log and act on, without this check inventing a policy about what
    the right number is.
    """
    rows: list[tuple[str, str, int, int]] = []
    for pattern, limit in (*required.items(), *patterns.items()):
        if glob.has_magic(pattern):
            matches = [path for path in site_root.glob(pattern) if path.is_file()]
        else:
            candidate = site_root / pattern
            matches = [candidate] if candidate.is_file() else []
        if not matches:
            continue
        largest = max(matches, key=lambda path: path.stat().st_size)
        rows.append(
            (pattern, largest.relative_to(site_root).as_posix(), largest.stat().st_size, limit)
        )
    return sorted(rows, key=lambda row: row[2] / row[3], reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    try:
        required, patterns = load_config(args.config)
    except ValueError as exc:
        parser.error(str(exc))

    structural_failures, overages = check_site(args.site_root, required, patterns)
    if structural_failures or overages:
        print("Generated-site byte budgets failed:")
        for violation in (*structural_failures, *overages):
            print(f"- {violation}")
        # Exit 1 is reserved for size overages, which data-refresh deploys may
        # treat as advisory. Missing pages and malformed coverage always block.
        return 2 if structural_failures else 1

    checked_count = len(required) + sum(
        1 for pattern in patterns for path in args.site_root.glob(pattern) if path.is_file()
    )
    print(f"Generated-site byte budgets passed ({checked_count} checks).")
    print("Largest page under each budget, tightest first:")
    for pattern, relative, size, limit in budget_headroom(args.site_root, required, patterns):
        used = 100 * size / limit
        print(f"- {pattern}: {used:.0f}% of {limit:,} bytes ({relative}, {size:,})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
