#!/usr/bin/env python3
"""Union one monitor run's rt-health records into a newer checkout of them.

`rt-monitor.yml` samples for hours and then pushes. When `main` has moved to
another run's observations in the meantime, the push is rejected and the two
sides hold different appends to the same files: every record conflicts, and a
rebase cannot resolve any of them. This unions the two histories instead, so a
rejected push costs a re-commit rather than the whole run's observations.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scorecard_pipeline.rt_health import merge_records


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Merge the rt-health records this run produced into the records of the "
            "checkout that won the push, keeping both sides' observations."
        )
    )
    parser.add_argument(
        "--ours",
        type=Path,
        required=True,
        help="directory holding this run's records (read, never written)",
    )
    parser.add_argument(
        "--into",
        type=Path,
        required=True,
        help="the checked-out data/rt-health to merge them into",
    )
    args = parser.parse_args()

    for label, directory in (("--ours", args.ours), ("--into", args.into)):
        if not directory.is_dir():
            print(f"{label} is not a directory: {directory}", file=sys.stderr)
            return 2

    ours = sorted(args.ours.glob("*.json"))
    if not ours:
        print(f"no rt-health records to merge from {args.ours}", file=sys.stderr)
        return 2
    changed = merge_records(args.ours, args.into)
    print(f"rt-health records merged: {len(changed)} of {len(ours)} carried new observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
