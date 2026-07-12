#!/usr/bin/env python3
"""Corpus numbers quoted in prose must track the registry (ideation FIX-15).

The docs like to state how many feeds the service covers, and each figure was
true when written; the registry kept moving. A 2026-07-12 read found three
documents disagreeing (~1,140 vs about 1,450 vs 1,449). The registry itself,
`agencies.yaml`, is the one corpus count that is always current in git, so
every prose figure is checked against it within a tolerance that absorbs
normal registry growth between doc touch-ups.

Each rule names the file and the exact phrase pattern that carries the figure.
A missing pattern fails too: rewording a sentence must not silently drop the
figure out of this check. When the check fails, either refresh the quoted
number from the count it prints, or update the rule here if the sentence
moved.

Run before committing doc edits that quote corpus figures:

    python3 pipeline/scripts/check_doc_stats.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# Allow the registry to grow this much before quoted figures must be
# refreshed. 8% of ~1,150 is roughly ninety agencies, a few weeks of normal
# onboarding; docs/feature-roadmap.md's monthly recheck cadence fits inside.
TOLERANCE = 0.08

# (file, pattern, what the figure claims). Patterns use \s+ between words
# because prose wraps. Every capture group is a corpus-sized count compared
# against the registry; published-page counts are bounded by the registry
# since publishing was deduped against it (#69), so one tolerance serves all.
RULES: list[tuple[str, str]] = [
    (r"README.md", r"registry now contains\s+~([\d,]+)\s+feed\s+records"),
    (r"README.md", r"\(~([\d,]+)\s+with published\s+scorecard pages\)"),
    (r"README.md", r"carries\s+~([\d,]+)\s+curated"),
    (r"docs/feeds.md", r"~([\d,]+)\s+feed records across the US and Canada"),
    (r"docs/support.md", r"about ([\d,]+)\s+agencies across the US and Canada"),
    (r"docs/follow-ups.md", r"At ~([\d,]+)\s+agencies"),
    (r"docs/roadmap.md", r"~([\d,]+)\s+agencies across the US and Canada"),
    (r"docs/roadmap.md", r"\(~([\d,]+)\s+scored with published"),
    (
        r"docs/product-roadmap.md",
        r"About ([\d,]+)\s+US and Canadian agencies\s+scored daily",
    ),
    (r"docs/feature-roadmap.md", r"about ([\d,]+)\s+agencies scored daily"),
    (r"CLAUDE.md", r"~([\d,]+)\s+agencies tracked across the US and Canada"),
]


def registry_count() -> int:
    data = yaml.safe_load((REPO_ROOT / "agencies.yaml").read_text())
    agencies = data["agencies"]
    if not isinstance(agencies, list):
        raise TypeError("agencies.yaml 'agencies' must be a list of entries")
    return len(agencies)


def main() -> int:
    count = registry_count()
    low = count * (1 - TOLERANCE)
    high = count * (1 + TOLERANCE)
    failures: list[str] = []
    for rel_path, pattern in RULES:
        text = (REPO_ROOT / rel_path).read_text()
        match = re.search(pattern, text)
        if match is None:
            failures.append(
                f"{rel_path}: no match for {pattern!r} — the sentence moved; "
                "update the rule in this script alongside the doc edit"
            )
            continue
        quoted = int(match.group(1).replace(",", ""))
        if not low <= quoted <= high:
            failures.append(
                f"{rel_path}: quotes {quoted:,} but the registry has {count:,} "
                f"entries (allowed {low:,.0f}–{high:,.0f}); refresh the figure"
            )
    if not failures:
        print(
            f"OK  {len(RULES)} quoted corpus figures within {TOLERANCE:.0%} of "
            f"the registry ({count:,} entries)"
        )
        return 0
    print(f"Corpus figures drifted from the registry ({count:,} entries) (FIX-15):")
    for failure in failures:
        print(f"  {failure}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
