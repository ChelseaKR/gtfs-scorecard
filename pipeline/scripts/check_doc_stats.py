#!/usr/bin/env python3
"""Corpus numbers quoted in prose must track their named denominator (FIX-15).

The registry and the published artifact index are intentionally independent:
removed feed records can retain historical scorecard pages. A single tolerance
between those populations hides drift instead of explaining it. Each prose
rule therefore names whether it means configured feed records or published
scorecards with numeric latest scores.

Narrative pages use a stable hundred-record floor such as "more than 2,100" and
link to generated status output for the exact current count. Historical planning
notes may still use an approximate exact figure. Each rule names the file, exact
phrase pattern, denominator, and comparison mode. A missing pattern fails too,
so rewording a sentence cannot silently drop the figure out of this check.

Three modes: ``floor`` for "more than N" prose, ``approx`` for a rounded figure
inside a one percent band, and ``exact`` for the rare sentence that must quote
the real number. ``exact`` is deliberately brittle. The European cohort figure
uses it because that number is the Europe beta gate's own denominator, and a
reader checking the gate cannot verify it against a rounded claim.

The check runs in both directions. Registered rules confirm the figures somebody
thought to register; the sweep (``ungated_figures``) reads the live-facing
documents looking for corpus-shaped figures and fails on any that no rule covers
and no ``POINT_IN_TIME`` declaration excuses. The second half exists because the
first cannot catch its own blind spot: CLAUDE.md's registry count sat at 1,286
while the registry grew past 2,100, and every *registered* claim stayed correct
throughout. A number nobody registered is the one that rots.

**The ``pages`` and ``scored`` denominators describe the committed snapshot,
not the live service.** They are read from ``data/artifacts/index.json``, which
stopped being written by automation when generated data moved to S3
(docs/follow-ups.md, "Stop committing generated data and pages"). What git
carries is a fallback snapshot kept for outages and forks, and it stands still
between deliberate refreshes while the deployed corpus keeps growing — the
cutover copy sat at 1,128 pages while the service passed 2,100. When the
snapshot lags, ``floor`` mode's ``quoted + FLOOR_BUCKET`` ceiling actively
rejects the larger, true live figure; the fix is never to loosen the gate but
to re-materialize the snapshot from the live corpus (the bounded ``aws s3
sync`` in ``.github/workflows/pages.yml``, then
``scripts/materialize_current_artifacts.py``), after which this same gate
forces every floored claim up to the refreshed denominator. Prose gated on
``pages`` or ``scored`` is a claim about the snapshot as of its last refresh;
the live counts live on ``/status/`` and ``/api/v1/stats.json``, which this
check cannot read because ``make verify`` is offline. ``registry``,
``europe_records`` and ``europe_countries`` are read from the registry YAML and
are not affected — those still track the real thing.

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
from scorecard_pipeline.global_coverage import EUROPE_BETA_COUNTRY_CODES  # noqa: E402

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
        r"more than ([\d,]+)\s+published\s+scorecard pages",
        "pages",
        "floor",
    ),
    (
        r"CLAUDE.md",
        r"more than ([\d,]+)\s+(?:>\s+)?published scorecards, still concentrated",
        "pages",
        "floor",
    ),
    # CLAUDE.md's scorecard count was gated; its registry count was not, and it
    # sat at an exact 1,286 while the registry grew past 2,100. Every gated
    # claim in this list stayed correct through that period, which is the whole
    # argument for gating a figure rather than trusting a doc edit to catch it.
    # (AGENTS.md carried the same stale figure. It is excluded from the repo, so
    # it is gated from OPTIONAL_RULES below rather than from here.)
    (
        r"CLAUDE.md",
        r"registry carries more than ([\d,]+)\s+curated feed",
        "registry",
        "floor",
    ),
    (
        r"web/support/index.html",
        r"more than\s+([\d,]+)\s+configured feed records in the current worldwide coverage",
        "registry",
        "floor",
    ),
    # This one quoted an exact 2,185 in the present tense, and the paragraph
    # under it multiplied that figure by 100. Both are now floors, so the scale
    # argument survives a growing registry instead of decaying with it.
    (
        r"docs/global-coverage-roadmap.md",
        r"current registry contains more than ([\d,]+)\s+feed\s+records",
        "registry",
        "floor",
    ),
    # The European cohort is the one public figure quoted exactly rather than
    # as a floor, because it is the denominator behind the Europe beta gate
    # (ADR 0040) and a reader checking the gate's geography needs the real
    # number, not a rounded one. Exact figures drift on the next admitted
    # record, so both halves of the sentence are checked.
    (
        r"README.md",
        r"a ([\d,]+)-record reviewed European cohort",
        "europe_records",
        "exact",
    ),
    (
        r"README.md",
        r"reviewed European cohort across ([\d,]+) countries",
        "europe_countries",
        "exact",
    ),
]


# --- the sweep -------------------------------------------------------------
#
# RULES above only checks claims somebody remembered to register, which cannot
# catch the next unregistered one. CLAUDE.md's 1,286 survived a doubling of the
# registry for exactly that reason: every gated figure stayed correct while the
# ungated one rotted. So the swept documents are also read the other way round —
# find every corpus-shaped figure, then fail on any that no rule covers and no
# declaration below excuses.

# Only documents that describe the service as it stands are swept. Subdirectories
# of docs/ (decisions, ideation, research, audits, fixes, standards) are dated
# records by construction: their figures are evidence of what was true when they
# were written, and refreshing them would falsify the record. The same goes for
# CHANGELOG.md, whose whole job is to state what a number used to be.
UNSWEPT_DOCS = ("CHANGELOG.md",)

# Below this, a number is not corpus-scale — "3 fixes", "26 countries", a port.
# The smallest population any rule here names is the European cohort at 528.
MIN_SWEPT_FIGURE = 500

_CORPUS_NOUN = (
    r"(?:curated|configured|published|reviewed|numeric)?\s*"
    r"(?:feed[-\s]records?|scorecard[-\s]pages?|scorecards?|feeds?|agencies|records?)"
)
FIGURE_RE = re.compile(rf"(\d{{1,3}}(?:,\d{{3}})+|\d{{3,}})[-\s]*\+?\s*{_CORPUS_NOUN}\b", re.I)
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
# Figures inside a URL, a code span, a link target, or an HTML attribute are
# identifiers, not claims about the corpus.
_MASK_RE = re.compile(r"https?://[^\s)>\]]+|`[^`\n]*`|\]\([^)\n]*\)|=\"[^\"\n]*\"")

# Rules for documents that may legitimately be missing from a checkout. AGENTS.md
# is excluded from the repo (.git/info/exclude), so naming it in RULES would fail
# every clean CI checkout — which is why it went ungated, and why it carried the
# same stale 1,286 CLAUDE.md did. Enforced when the file is there, skipped when
# it is not: a local `make verify` gates it, CI stays green without it.
OPTIONAL_RULES: list[tuple[str, str, str, str]] = [
    (r"AGENTS.md", r"registry carries more than ([\d,]+)\s+curated feed", "registry", "floor"),
    (r"AGENTS.md", r"more than ([\d,]+)\s+numeric\s+scorecards published", "scored", "floor"),
]

# Figures in swept documents that are legitimately fixed in time: a measurement
# with a date on it, an outcome of a completed wave, or somebody else's number.
# Each entry states why, and each must still match something — a declaration
# that has stopped matching is scaffolding, and failing on it keeps this list
# from becoming a place where real drift can hide.
POINT_IN_TIME: list[tuple[str, str, str]] = [
    (
        "docs/RESEARCH-ROADMAP.md",
        r"21% of ([\d,]+) feeds",
        "sample size of a cited external study (Findings, 2024), not this registry",
    ),
    (
        "docs/expansion-research.md",
        r"\(([\d,]+)\+ feeds, terabytes\)",
        "another operator's self-reported catalogue size",
    ),
    (
        "docs/expansion-ideation-2026-07.md",
        r"held to about ([\d,]+) agencies",
        "dated observation from the 2026-07 horizon scan",
    ),
    (
        "docs/renamed-successor-review.md",
        r"holds ([\d,]+) records",
        "one pull request's branch as read on a stated date, not the live registry",
    ),
    (
        "docs/feeds.md",
        r"moves the registry to ([\d,]+)\s+configured",
        "per-wave curation log: each line records where that wave landed",
    ),
    (
        "docs/feeds.md",
        r"and ([\d,]+) configured records across 40",
        "per-wave curation log: the global portal exhaustion wave's result",
    ),
    (
        "docs/feeds.md",
        r"([\d,]+) feed rows",
        "size of the Transitland Atlas snapshot at a pinned commit",
    ),
    (
        "docs/feeds.md",
        r"rises from 392 to ([\d,]+) records",
        "per-wave curation log: the France national-access-point wave's result",
    ),
    (
        "docs/global-expansion.md",
        r"waves contains ([\d,]+) feed records",
        "frozen 2026-07-18 baseline; the section says so and says why",
    ),
    (
        "docs/global-expansion.md",
        r"500 MB at ([\d,]+) configured",
        "storage measured on 2026-07-18, the anchor for the 2x/5x projections",
    ),
    (
        "docs/global-expansion.md",
        r"double the registry,\s*roughly ([\d,]+) records",
        "projection from the dated storage measurement, not a count",
    ),
    (
        "docs/global-expansion.md",
        r"five times, roughly ([\d,]+) records",
        "projection from the dated storage measurement, not a count",
    ),
    (
        "docs/global-coverage-roadmap.md",
        r"produced, ([\d,]+) records across 46",
        "outcome of the phase-3 waves on 2026-07-25; the sentence says so",
    ),
    (
        "docs/global-coverage-roadmap.md",
        r"would require more than ([\d,]+)\s*\n?records",
        "the 100x scale argument's own arithmetic, floored alongside its input",
    ),
]


def swept_docs() -> list[str]:
    """Live-facing authored documents, as repo-relative paths.

    Root and top-level `docs/` Markdown, plus the hand-authored static pages.
    Those come from ``STATIC_NAV_PAGES`` rather than a list restated here, so a
    new hand-authored page is swept the day it is added. `*.local.md` is
    gitignored private working context and is never read.
    """
    from scorecard_pipeline.site_shell import STATIC_NAV_PAGES  # noqa: PLC0415

    candidates = [p.name for p in REPO_ROOT.glob("*.md")]
    candidates += [f"docs/{p.name}" for p in (REPO_ROOT / "docs").glob("*.md")]
    candidates += [f"web/{page}" for page in STATIC_NAV_PAGES]
    return sorted(
        rel
        for rel in candidates
        if rel not in UNSWEPT_DOCS
        and not rel.endswith(".local.md")
        and (REPO_ROOT / rel).is_file()
    )


def _spans_covering(rel: str, text: str) -> list[tuple[int, int]]:
    """Character spans of every figure some rule or declaration already accounts for."""
    spans: list[tuple[int, int]] = []
    for rules in (RULES, OPTIONAL_RULES):
        for rule_path, pattern, _denominator, _mode in rules:
            if rule_path == rel:
                spans.extend(m.span(1) for m in re.finditer(pattern, text))
    for decl_path, pattern, _reason in POINT_IN_TIME:
        if decl_path == rel:
            spans.extend(m.span(1) for m in re.finditer(pattern, text))
    return spans


def ungated_figures(rel: str, text: str) -> list[str]:
    """Corpus-shaped figures in one document that nothing accounts for.

    Deliberately not a completeness claim. It reads "<number> <corpus noun>",
    so a figure split from its noun by an unexpected word or a blockquote
    marker slips through. It is a net under the registration discipline, not a
    replacement for it.
    """
    covered = _spans_covering(rel, text)
    masked = [m.span() for m in _MASK_RE.finditer(text)]
    findings: list[str] = []
    for match in FIGURE_RE.finditer(text):
        start, end = match.span(1)
        figure = match.group(1)
        if int(figure.replace(",", "")) < MIN_SWEPT_FIGURE or _YEAR_RE.fullmatch(figure):
            continue
        if any(low <= start and end <= high for low, high in (*masked, *covered)):
            continue
        line = text.count("\n", 0, start) + 1
        phrase = re.sub(r"\s+", " ", match.group(0)).strip()
        findings.append(
            f"{rel}:{line}: {phrase!r} quotes a corpus figure no rule checks. "
            "Add a RULES entry so it tracks its denominator, or a POINT_IN_TIME "
            "entry stating why it is fixed in time."
        )
    return findings


def registry_count() -> int:
    return len(read_agencies())


def europe_counts() -> tuple[int, int]:
    """Registry records in the Europe beta geography, and how many of those
    countries actually hold a record.

    The country tally counts countries *with records*, not the size of
    ``EUROPE_BETA_COUNTRY_CODES``: the gate's geography is a closed product
    decision listing more countries than the registry has reached, and the
    README sentence describes the cohort, not the gate's ambition. Reading the
    codes from the module rather than restating them here means widening the
    gate cannot leave this check measuring the old geography.
    """
    agencies = read_agencies()
    members = [a for a in agencies if (a.country or "") in EUROPE_BETA_COUNTRY_CODES]
    return len(members), len({a.country for a in members})


def published_counts() -> tuple[int, int, str]:
    """Pages and numerically-scored pages in the committed fallback snapshot.

    The third member is the newest scoring date anywhere in that snapshot, which
    dates the snapshot itself. It is printed with the counts because these two
    denominators are frozen (see the module docstring): a reader who sees only
    "published pages 1,128" will read it as the live corpus, and a reader who
    sees the date beside it cannot.
    """
    data = json.loads((REPO_ROOT / "data" / "artifacts" / "index.json").read_text())
    entries = data.get("agencies", {})
    scored = sum(
        bool(entry.get("history"))
        and isinstance(entry["history"][-1].get("score"), (int, float))
        and not isinstance(entry["history"][-1].get("score"), bool)
        for entry in entries.values()
    )
    dates = {
        str(point["date"])
        for entry in entries.values()
        for point in entry.get("history") or []
        if point.get("date")
    }
    return len(entries), scored, max(dates, default="unknown date")


def denominator_line(counts: dict[str, int], snapshot_date: str) -> str:
    """The one line both outcomes print, so both carry the same caveat.

    ``pages`` and ``scored`` are frozen (see the module docstring). Naming the
    snapshot and its date here, rather than in two separate f-strings, is what
    keeps a later edit to one branch from quietly dropping the caveat from it.
    """
    return (
        f"registry {counts['registry']:,}; "
        f"published pages {counts['pages']:,} and scored latest {counts['scored']:,} "
        f"in the committed fallback snapshot frozen at {snapshot_date}, "
        "not the live corpus; "
        f"Europe beta {counts['europe_records']:,} records across "
        f"{counts['europe_countries']:,} countries"
    )


def main() -> int:
    pages, scored, snapshot_date = published_counts()
    europe_records, europe_countries = europe_counts()
    counts = {
        "registry": registry_count(),
        "pages": pages,
        "scored": scored,
        "europe_records": europe_records,
        "europe_countries": europe_countries,
    }
    failures: list[str] = []
    checked = 0
    for rel_path, pattern, denominator, mode in (*RULES, *OPTIONAL_RULES):
        path = REPO_ROOT / rel_path
        if not path.is_file():
            # Only reachable for OPTIONAL_RULES; a missing required doc still
            # raises, because a rule naming a file that vanished is a real fault.
            continue
        checked += 1
        text = path.read_text()
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
        elif mode == "exact":
            valid = quoted == count
            allowed = f"exactly {count:,}"
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

    swept = swept_docs()
    for rel_path in swept:
        failures.extend(ungated_figures(rel_path, (REPO_ROOT / rel_path).read_text()))

    # A declaration that matches nothing is stale scaffolding, and a stale
    # exemption is where the next unnoticed figure would hide.
    for decl_path, pattern, reason in POINT_IN_TIME:
        path = REPO_ROOT / decl_path
        if not path.is_file() or not re.search(pattern, path.read_text()):
            failures.append(
                f"{decl_path}: POINT_IN_TIME pattern {pattern!r} ({reason}) matches "
                "nothing; the figure moved or went away, so drop the declaration"
            )

    line = denominator_line(counts, snapshot_date)
    if not failures:
        print(
            f"OK  {checked} corpus claims match their denominator policy; "
            f"{len(swept)} swept documents carry no ungated corpus figure "
            f"({len(POINT_IN_TIME)} declared point-in-time) ({line})"
        )
        return 0
    print(f"Corpus figures drifted from their named denominators ({line}) (FIX-15):")
    for failure in failures:
        print(f"  {failure}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
