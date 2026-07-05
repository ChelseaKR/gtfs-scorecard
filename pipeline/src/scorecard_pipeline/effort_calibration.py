"""Empirical fix-effort bands, calibrated from observed runs-to-clear.

The hand-authored effort hint next to each fix ("about an hour in your export
tool") is an editor's guess. Once the corpus has accumulated dated artifacts it
can say something the guess cannot: how long agencies *actually* took to clear
this exact notice code. This module derives that from the same dated-artifact
walk the fix log already runs (publish.rebuild_index), turning the history into
per-code runs-to-clear distributions.

An episode is one lifetime of a notice code on one feed: it opens the run the
code first appears and closes the run it disappears *while its category is
measured* — the same "verified gone, not merely unmeasured" rule the fix log
uses (fixlog.diff_receipts). A code that clears, returns, and clears again is
two episodes. An episode that never closes is "still open": it is honest to
count it, but it is not a fix, so it is excluded from the median.

Only codes with at least ``MIN_SAMPLES`` closed episodes earn a band; below that
floor the sample is too thin to quote and the hand-authored hint stands alone.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .fixlog import _codes_with_category, _measured_keys

# A code needs at least this many observed (closed) episodes before its
# empirical band is trustworthy enough to show beside the hand-authored hint.
MIN_SAMPLES = 5

# Rides along in the written data file so a future reader knows how to read it.
CALIBRATION_SCHEMA_NOTE = (
    "Per notice-code runs-to-clear stats derived from dated artifact history. "
    "median_days/p25/p75 are over closed episodes (a code seen, then verified "
    "gone while its category was measured); still_open counts never-cleared "
    f"episodes and is excluded from the median. Codes with fewer than "
    f"{MIN_SAMPLES} closed episodes get no effort band."
)


@dataclass(frozen=True)
class Episode:
    """One lifetime of a notice code on one feed.

    ``cleared`` is the ISO date the code was verified gone (its category
    measured that run), or ``None`` when the episode never closed.
    """

    code: str
    first_seen: str
    cleared: str | None


def agency_episodes(artifacts: Iterable[dict[str, Any]]) -> list[Episode]:
    """Episodes for a single agency from its dated artifacts in date order.

    Mirrors the fix log's measured-category rule: a code only "clears" when it
    is absent *and* the category it lived in was actually measured that run, so
    an unmeasured category (failed fetch, realtime outage) never reads as a fix.
    A code that recurs opens a fresh episode, so one code can yield several.
    """
    open_first_seen: dict[str, str] = {}
    open_cat: dict[str, str] = {}
    episodes: list[Episode] = []

    for artifact in artifacts:
        date = str(artifact.get("snapshot_date", ""))
        present = _codes_with_category(artifact)
        measured = _measured_keys(artifact)
        # Close episodes whose code has disappeared while its category is
        # measured — the verified-gone rule. A code missing only because its
        # category went unmeasured stays open.
        for code in list(open_first_seen):
            if code not in present and open_cat[code] in measured:
                episodes.append(Episode(code, open_first_seen[code], date))
                del open_first_seen[code]
                del open_cat[code]
        # Open a new episode for any code not already tracked; refresh the
        # remembered category for codes still open (a code can move categories).
        for code, (cat, _what) in present.items():
            if code not in open_first_seen:
                open_first_seen[code] = date
            open_cat[code] = cat

    for code, first_seen in open_first_seen.items():
        episodes.append(Episode(code, first_seen, None))
    return episodes


def _days_between(first_seen: str, cleared: str) -> int:
    return (dt.date.fromisoformat(cleared) - dt.date.fromisoformat(first_seen)).days


def _percentile(sorted_samples: list[int], q: float) -> int:
    """Linear-interpolated percentile over a sorted, non-empty sample, rounded
    to whole days (fractional days are noise for an effort hint)."""
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    pos = (len(sorted_samples) - 1) * (q / 100)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_samples[lo]
    value = sorted_samples[lo] * (hi - pos) + sorted_samples[hi] * (pos - lo)
    return round(value)


def stats_from_episodes(episodes: Iterable[Episode]) -> dict[str, dict[str, int]]:
    """Aggregate episodes into per-code runs-to-clear stats, code order sorted.

    Each code maps to ``{"samples": n, "still_open": k, "median_days": ...,
    "p25": ..., "p75": ...}``; the percentile keys are present only when at
    least one closed episode exists.
    """
    samples: dict[str, list[int]] = {}
    still_open: dict[str, int] = {}
    for ep in episodes:
        if ep.cleared is None:
            still_open[ep.code] = still_open.get(ep.code, 0) + 1
        else:
            samples.setdefault(ep.code, []).append(_days_between(ep.first_seen, ep.cleared))

    out: dict[str, dict[str, int]] = {}
    for code in sorted(set(samples) | set(still_open)):
        days = sorted(samples.get(code, []))
        entry: dict[str, int] = {"samples": len(days), "still_open": still_open.get(code, 0)}
        if days:
            entry["median_days"] = _percentile(days, 50)
            entry["p25"] = _percentile(days, 25)
            entry["p75"] = _percentile(days, 75)
        out[code] = entry
    return out


def build_clear_stats(
    index_walk: Iterable[Iterable[dict[str, Any]]],
) -> dict[str, dict[str, int]]:
    """Per-code runs-to-clear stats over a whole corpus.

    ``index_walk`` yields one dated-artifact sequence per agency (each already
    in date order), exactly the shape publish.rebuild_index walks.
    """
    episodes: list[Episode] = []
    for artifacts in index_walk:
        episodes.extend(agency_episodes(artifacts))
    return stats_from_episodes(episodes)


def _weeks(days: int) -> int:
    return max(1, round(days / 7))


def band_text(stats: Mapping[str, int]) -> str | None:
    """A plain-language empirical effort band, or ``None`` below the sample floor.

    Week-rounded from the median so the number reads like an estimate, not a
    false precision, and names the sample size so the reader can weigh it.
    """
    samples = int(stats.get("samples", 0))
    median = stats.get("median_days")
    if samples < MIN_SAMPLES or median is None:
        return None
    weeks = _weeks(int(median))
    unit = "week" if weeks == 1 else "weeks"
    return (
        f"Agencies here usually clear this within about {weeks} {unit} "
        f"(based on {samples} observed fixes)."
    )
