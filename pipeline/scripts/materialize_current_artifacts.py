#!/usr/bin/env python3
"""Restore validated current dated artifacts in a bounded local corpus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scorecard_pipeline.activation import (
    ActivationHydrationError,
    materialize_local_current_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate index/latest parity and materialize any missing current dated "
            "record as a byte-identical local copy of latest.json."
        )
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("data/artifacts"),
        help="local artifact root containing index.json (default: data/artifacts)",
    )
    args = parser.parse_args()
    try:
        materialized = materialize_local_current_artifacts(
            artifacts_root=args.artifacts_root.resolve()
        )
    except ActivationHydrationError as exc:
        print(f"Current artifact materialization failed: {exc}", file=sys.stderr)
        return 2
    print(f"Current artifact corpus is valid ({materialized} dated records materialized).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
