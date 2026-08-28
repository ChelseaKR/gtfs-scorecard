#!/usr/bin/env python3
"""Plain-language readability gate for every finding the scorecard publishes.

The product's promise is that every curated finding reads as plain language a
non-developer transit manager can act on. This asserts that promise mechanically
for every ``what``/``why``/``fix`` string in the reader-copy inventory, the same
shape as the contrast gate: average sentence length must stay under
MAX_AVG_SENTENCE_WORDS, and a syllable-based Flesch reading-ease estimate must
stay above MIN_FLESCH. Pure Python, no dependencies. Run from pipeline/:

    uv run python scripts/check_readability.py

The inventory is ``scorecard_pipeline.reader_copy``, which covers three
families: the curated wording in ``notices.TRANSLATIONS``; the copy the pipeline
authors at a construction site, meaning every ``Finding(...)`` and the
``summary`` sentence on every scored ``CategoryResult(...)``; and the copy
assembled at run time by a registered producer, measured over an input set that
reaches every branch. Until 2026-08-27 this gate read only the first family.

Effort hints are excluded: they are fragments ("One setting."), not prose. The
generated fallback for an uncurated notice code is also excluded, because it is
assembled from the code and a rule URL rather than written; the curated-coverage
metric on /problems/ remains its measure. Both exclusions are printed, not
assumed: the inventory reports them as deferred sites with their reason, and a
site whose copy cannot be accounted for at all raises rather than passing.

The thresholds gate regressions in reader-facing text. Never loosen them to
admit one hard string; rewrite the string.
"""

from __future__ import annotations

import re
import sys

from scorecard_pipeline.reader_copy import CopyString, DeferredSite, reader_copy

# Plain-language bars. 22 words/sentence is the upper edge of "easy to follow"
# in most plain-writing guidance; Flesch 50 is the floor of "fairly difficult"
# (10th-12th grade), a lenient floor that still catches dense, clause-stacked
# rewrites. Tighten these as the corpus improves; never loosen them to admit
# one hard string — rewrite the string.
MAX_AVG_SENTENCE_WORDS = 22.0
MIN_FLESCH = 50.0

_WORD_RE = re.compile(r"[A-Za-z]+")
# Sentence breaks: terminal punctuation followed by whitespace or end-of-text.
# "feed_info.txt" never splits (no space after the dot); "e.g. ..." does, which
# only shortens the measured sentences — an acceptable, conservative error.
_SENTENCE_RE = re.compile(r"[.!?]+(?:\s+|$)")


def words(text: str) -> list[str]:
    """Alphabetic word tokens; identifiers like feed_info.txt split into parts."""
    return _WORD_RE.findall(text)


def sentences(text: str) -> list[str]:
    """Non-empty sentences, split on terminal punctuation before whitespace."""
    return [s for s in (p.strip() for p in _SENTENCE_RE.split(text)) if s]


def syllables(word: str) -> int:
    """Heuristic syllable count: vowel groups, minus a common silent final e."""
    w = word.lower()
    groups = len(re.findall(r"[aeiouy]+", w))
    if groups > 1 and w.endswith("e") and not w.endswith(("le", "ee", "ye")):
        groups -= 1
    return max(1, groups)


def avg_sentence_words(text: str) -> float:
    """Mean words per sentence; 0.0 for empty text."""
    sents = sentences(text)
    if not sents:
        return 0.0
    return sum(len(words(s)) for s in sents) / len(sents)


def flesch(text: str) -> float:
    """Flesch reading-ease estimate from the heuristic syllable counts.

    Higher is easier; 100.0 for empty text so a blank string never fails the
    floor (emptiness is a curation problem, not a readability one).
    """
    ws = words(text)
    if not ws:
        return 100.0
    sents = sentences(text) or [text]
    syl = sum(syllables(w) for w in ws)
    return 206.835 - 1.015 * (len(ws) / len(sents)) - 84.6 * (syl / len(ws))


def check_text(label: str, text: str) -> list[str]:
    """Per-string diagnostics for any threshold the text misses; empty = pass."""
    fails: list[str] = []
    avg = avg_sentence_words(text)
    if avg > MAX_AVG_SENTENCE_WORDS:
        fails.append(
            f"{label}: average sentence length {avg:.1f} words "
            f"(cap {MAX_AVG_SENTENCE_WORDS:.0f}) — split or shorten the sentences"
        )
    ease = flesch(text)
    if ease < MIN_FLESCH:
        fails.append(
            f"{label}: Flesch reading ease {ease:.1f} "
            f"(floor {MIN_FLESCH:.0f}) — use shorter, more common words"
        )
    return fails


def report_string(string: CopyString) -> list[str]:
    """Print one measured string's numbers; return its failures."""
    string_fails = check_text(string.label, string.text)
    print(
        f"{'OK ' if not string_fails else 'FAIL'} flesch {flesch(string.text):6.1f}  "
        f"avg-words {avg_sentence_words(string.text):5.1f}  "
        f"{string.provenance:9s} {string.label}"
    )
    return string_fails


def report_deferred(deferred: list[DeferredSite]) -> None:
    """Say what the gate did not measure, and why, rather than staying silent."""
    if not deferred:
        return
    print()
    print(f"Not measured here ({len(deferred)} fields):")
    for site in sorted(deferred, key=lambda d: (d.origin, d.field)):
        print(f"  - {site.origin} {site.field}= — {site.reason}")


def main() -> int:
    strings, deferred = reader_copy()
    fails: list[str] = []
    for string in sorted(strings, key=lambda s: (s.provenance, s.label)):
        fails.extend(report_string(string))
    report_deferred(deferred)

    families = ("curated", "authored", "assembled")
    counts = {family: sum(1 for s in strings if s.provenance == family) for family in families}
    print()
    if fails:
        print(f"{len(fails)} FAILURES:")
        for f in fails:
            print("  -", f)
        return 1
    breakdown = ", ".join(f"{counts[family]} {family}" for family in families)
    print(
        f"All {len(strings)} reader-facing strings clear the plain-language "
        f"bars (avg sentence <= {MAX_AVG_SENTENCE_WORDS:.0f} words, "
        f"Flesch >= {MIN_FLESCH:.0f}): {breakdown}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
