#!/usr/bin/env python3
"""Corpus numbers quoted in prose must track their named denominator (FIX-15).

The registry and the published artifact index are intentionally independent:
removed feed records can retain historical scorecard pages. A single tolerance
between those populations hides drift instead of explaining it. Each prose
rule therefore names whether it means configured feed records or published
scorecards with numeric latest scores.

Each rule names the file and the exact phrase pattern that carries the figure.
A missing pattern fails too: rewording a sentence must not silently drop the
figure out of this check. When the check fails, either refresh the quoted
number from the count it prints, or update the rule here if the sentence
moved.

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

# Prose uses "about" or a rounded ``~`` figure. One percent allows that rounding
# while still catching a meaningful change in either independent population.
TOLERANCE = 0.01

# (file, pattern, denominator). A missing pattern fails so rewording cannot
# silently drop the check.
RULES: list[tuple[str, str, str]] = [
    (r"README.md", r"registry now contains\s+~([\d,]+)\s+feed\s+records", "registry"),
    (r"README.md", r"\(~([\d,]+)\s+published\s+scorecard pages\)", "pages"),
    (r"README.md", r"carries\s+~([\d,]+)\s+curated", "registry"),
    (r"docs/feeds.md", r"~([\d,]+)\s+feed records across the US and Canada", "registry"),
    (r"docs/support.md", r"about ([\d,]+)\s+configured feeds across the US and Canada", "registry"),
    (r"docs/follow-ups.md", r"At ~([\d,]+)\s+configured feeds", "registry"),
    (r"docs/roadmap.md", r"~([\d,]+)\s+configured feeds across the US and Canada", "registry"),
    (r"docs/roadmap.md", r"\(~([\d,]+)\s+scored latest rows with published", "scored"),
    (
        r"docs/product-roadmap.md",
        r"About ([\d,]+)\s+US and Canadian scorecards have numeric latest scores",
        "scored",
    ),
    (r"docs/feature-roadmap.md", r"about ([\d,]+)\s+published scorecards", "pages"),
    (r"CLAUDE.md", r"~([\d,]+)\s+published scorecards across the US and Canada", "pages"),
    (
        r"web/support/index.html",
        r"about\s+([\d,]+)\s+configured feeds across the US and Canada",
        "registry",
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
    for rel_path, pattern, denominator in RULES:
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
        low = count * (1 - TOLERANCE)
        high = count * (1 + TOLERANCE)
        if not low <= quoted <= high:
            failures.append(
                f"{rel_path}: quotes {quoted:,} but {denominator} has {count:,} "
                f"entries (allowed {low:,.0f}–{high:,.0f}); refresh the figure"
            )
    if not failures:
        print(
            f"OK  {len(RULES)} quoted corpus figures within {TOLERANCE:.0%} of "
            f"their denominators (registry {counts['registry']:,}; "
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
