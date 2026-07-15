#!/usr/bin/env python3
"""Corpus numbers quoted in prose must track their named denominator (FIX-15).

The registry and the published artifact index are intentionally independent:
removed feed records can retain historical scorecard pages. A single tolerance
between those populations hides drift instead of explaining it. Each prose
rule therefore names whether it means configured feed records or published
scorecards with numeric latest scores.

Narrative pages use a stable hundred-record floor such as "more than 1,100" and
link to generated status output for the exact current count. Historical planning
notes may still use an approximate exact figure. Each rule names the file, exact
phrase pattern, denominator, and comparison mode. A missing pattern fails too,
so rewording a sentence cannot silently drop the figure out of this check.

Run before committing doc edits that quote corpus figures:

    python3 pipeline/scripts/check_doc_stats.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pipeline" / "src"))

from scorecard_pipeline.agencies import read_agencies  # noqa: E402

# Approximate prose uses "about" or a rounded ``~`` figure. One percent allows
# that rounding while still catching a meaningful change in either independent
# population. Floor claims advance in hundred-record steps.
TOLERANCE = 0.01
FLOOR_BUCKET = 100

# (file, pattern, denominator, mode). A missing pattern fails so rewording
# cannot silently drop the check.
RULES: list[tuple[str, str, str, str]] = [
    (
        r"README.md",
        r"registry contains\s+more than ([\d,]+)\s+curated\s+feed\s+records",
        "registry",
        "floor",
    ),
    (
        r"README.md",
        r"with more than ([\d,]+)\s+numeric\s+scorecards published",
        "scored",
        "floor",
    ),
    (r"README.md", r"carries\s+more than ([\d,]+)\s+curated", "registry", "floor"),
    (
        r"docs/feeds.md",
        r"full registry has more than ([\d,]+)\s+feed records",
        "registry",
        "floor",
    ),
    (
        r"docs/support.md",
        r"more than ([\d,]+)\s+configured feed records\s+in the current worldwide coverage",
        "registry",
        "floor",
    ),
    (r"docs/follow-ups.md", r"At ~([\d,]+)\s+configured feeds", "registry", "approx"),
    (
        r"docs/roadmap.md",
        r"more than ([\d,]+)\s+configured feed records in the current worldwide",
        "registry",
        "floor",
    ),
    (
        r"docs/roadmap.md",
        r"numeric current scores for more than ([\d,]+) of them",
        "scored",
        "floor",
    ),
    (
        r"docs/product-roadmap.md",
        r"tracks more than ([\d,]+)\s+curated feed records",
        "registry",
        "floor",
    ),
    (
        r"docs/product-roadmap.md",
        r"scores published for more than ([\d,]+) of them",
        "scored",
        "floor",
    ),
    (
        r"docs/feature-roadmap.md",
        r"about ([\d,]+)\s+published\s+scorecard pages",
        "pages",
        "approx",
    ),
    (
        r"CLAUDE.md",
        r"~([\d,]+)\s+published scorecards, still concentrated",
        "pages",
        "approx",
    ),
    (
        r"web/support/index.html",
        r"more than\s+([\d,]+)\s+configured feed records in the current worldwide coverage",
        "registry",
        "floor",
    ),
]


def registry_count() -> int:
    return len(read_agencies())


def published_counts() -> tuple[int, int]:
    data = json.loads((REPO_ROOT / "data" / "artifacts" / "index.json").read_text())
    entries = data.get("agencies", {})
    scored = sum(
        bool(entry.get("history"))
        and isinstance(entry["history"][-1].get("score"), (int, float))
        and not isinstance(entry["history"][-1].get("score"), bool)
        for entry in entries.values()
    )
    return len(entries), scored


def main() -> int:
    pages, scored = published_counts()
    counts = {"registry": registry_count(), "pages": pages, "scored": scored}
    failures: list[str] = []
    for rel_path, pattern, denominator, mode in RULES:
        text = (REPO_ROOT / rel_path).read_text()
        match = re.search(pattern, text)
        if match is None:
            failures.append(
                f"{rel_path}: no match for {pattern!r} — the sentence moved; "
                "update the rule in this script alongside the doc edit"
            )
            continue
        quoted = int(match.group(1).replace(",", ""))
        count = counts[denominator]
        if mode == "floor":
            valid = quoted < count < quoted + FLOOR_BUCKET
            allowed = f"more than {quoted:,} and fewer than {quoted + FLOOR_BUCKET:,}"
        else:
            low = count * (1 - TOLERANCE)
            high = count * (1 + TOLERANCE)
            valid = low <= quoted <= high
            allowed = f"{low:,.0f}–{high:,.0f}"
        if not valid:
            failures.append(
                f"{rel_path}: quotes {quoted:,} but {denominator} has {count:,} "
                f"entries (allowed {allowed}); refresh the figure"
            )
    if not failures:
        print(
            f"OK  {len(RULES)} corpus claims match their denominator policy "
            f"(registry {counts['registry']:,}; "
            f"published pages {counts['pages']:,}; scored latest {counts['scored']:,})"
        )
        return 0
    print(
        "Corpus figures drifted from their named denominators "
        f"(registry {counts['registry']:,}; published pages {counts['pages']:,}; "
        f"scored latest {counts['scored']:,}) (FIX-15):"
    )
    for failure in failures:
        print(f"  {failure}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
