"""A national time series: is GTFS data quality getting better?

Each agency's scorecard trends its own score over time. Nobody has asked the
question one level up: across the country, is transit data quality improving? The
published index already holds every agency's dated history, so this derives a
national daily series from it, with no new stored state. For each date the corpus
has seen, it carries each agency's most recent score as of that date forward and
averages, so the national line is smooth even though agencies are not all checked
on the same days.

It is pure over the index the site already trends from, so the series is
reproducible and adds no per-agency work. It reports the national average score,
the grade mix, and the share of feeds whose service had expired, per date. It
changes no grade; it is a measure of the whole, not of any one agency.
"""

from __future__ import annotations

from typing import Any

from ._stats import _GRADES


def _as_of(sorted_history: list[dict[str, Any]], date: str) -> dict[str, Any] | None:
    """The agency's most recent history point on or before ``date``.

    ``sorted_history`` must be sorted ascending by date. The latest qualifying
    point is the carried-forward value for that date. None when the agency had no
    check yet on that date.
    """
    latest: dict[str, Any] | None = None
    for h in sorted_history:
        if str(h.get("date", "")) <= date:
            latest = h
        else:
            break
    return latest


def as_of_points(index: dict[str, Any], *, min_coverage: float = 0.8) -> list[dict[str, Any]]:
    """Derive the national daily series from the published index.

    For every date any agency was checked, carries each agency's latest score as
    of that date forward and reports the national average score, the grade
    distribution, and the share of feeds whose service had expired
    (days_until_expiry at or below zero), plus how many agencies are counted.
    Sorted by date.

    Early dates when the corpus was still being assembled would otherwise make the
    national average swing on composition, not quality: two pilot feeds averaging
    in the high seventies is not comparable to a thousand feeds averaging in the
    low sixties, and charting that as a "decline" would be plain wrong. So dates
    whose agency count is below ``min_coverage`` of the series' peak are dropped,
    leaving the window where the cohort is stable enough to compare. A date with no
    scored agency is dropped too.
    """
    agencies = index.get("agencies") or {}
    all_dates = sorted(
        {str(h.get("date")) for v in agencies.values() for h in (v.get("history") or [])}
    )

    # Pre-sort each agency's history once, outside the date loop, to avoid an
    # O(N×D) repeated sort where N is agencies and D is dates.
    sorted_histories = [
        sorted(v.get("history") or [], key=lambda p: str(p.get("date", "")))
        for v in agencies.values()
    ]

    # Rows rescored under the current rubric from an earlier record
    # (rescore_history.py) are counted per date, so a series that mixes them
    # with native rows says how much of each point is rescored.
    has_rescored = any("rescored_from_rubric" in h for history in sorted_histories for h in history)

    raw: list[dict[str, Any]] = []
    for date in all_dates:
        scores: list[float] = []
        rescored = 0
        grades = dict.fromkeys(_GRADES, 0)
        expired = 0
        for sorted_history in sorted_histories:
            latest = _as_of(sorted_history, date)
            if latest is None or latest.get("score") is None:
                continue
            scores.append(float(latest["score"]))
            if latest.get("rescored_from_rubric"):
                rescored += 1
            g = latest.get("grade")
            if g in grades:
                grades[g] += 1
            du = latest.get("days_until_expiry")
            if isinstance(du, int | float) and not isinstance(du, bool) and du <= 0:
                expired += 1
        if not scores:
            continue
        n = len(scores)
        point: dict[str, Any] = {
            "date": date,
            "agency_count": n,
            "average_score": round(sum(scores) / n, 1),
            "grade_distribution": grades,
            "expired_pct": round(expired / n * 100, 1),
        }
        if has_rescored:
            point["rescored_agency_count"] = rescored
        raw.append(point)

    if not raw:
        return []
    peak = max(p["agency_count"] for p in raw)
    threshold = peak * min_coverage
    return [p for p in raw if p["agency_count"] >= threshold]


def top_improvers(
    index: dict[str, Any],
    *,
    window_days: int = 90,
    min_checks: int = 3,
    top: int = 10,
) -> list[dict[str, Any]]:
    """Agencies that improved the most in the last ``window_days``.

    Compares each agency's score at the start of the window (or earliest
    available) to its most recent score. Only agencies with at least
    ``min_checks`` total observations are included (a single lucky outlier
    should not top the list). Returns the top improvers sorted by score
    delta descending, with their names, grades, and the actual dates compared.
    """
    import datetime as dt

    agencies = index.get("agencies") or {}
    all_dates = sorted(
        {str(h.get("date")) for v in agencies.values() for h in (v.get("history") or [])}
    )
    if not all_dates:
        return []

    cutoff = all_dates[-1]  # most recent date in the corpus
    # Window start: the date closest to window_days before the cutoff
    try:
        cutoff_dt = dt.date.fromisoformat(cutoff)
        window_start = str(cutoff_dt - dt.timedelta(days=window_days))
    except ValueError:
        return []

    results = []
    for aid, v in agencies.items():
        history = sorted(v.get("history") or [], key=lambda p: str(p.get("date", "")))
        if len(history) < min_checks:
            continue
        latest_h = history[-1]
        latest_score = latest_h.get("score")
        if latest_score is None:
            continue

        # Find the earliest point at or after window_start (or the oldest point)
        window_points = [h for h in history if str(h.get("date", "")) >= window_start]
        baseline = window_points[0] if window_points else history[0]
        baseline_score = baseline.get("score")
        if baseline_score is None:
            continue

        delta = round(float(latest_score) - float(baseline_score), 1)
        if delta <= 0:
            continue  # only improvements

        results.append(
            {
                "id": aid,
                "name": v.get("name", aid),
                "score_start": round(float(baseline_score), 1),
                "score_end": round(float(latest_score), 1),
                "grade_end": latest_h.get("grade", ""),
                "delta": delta,
                "date_start": str(baseline.get("date", "")),
                "date_end": str(latest_h.get("date", "")),
            }
        )

    results.sort(key=lambda r: (-r["delta"], r["name"]))
    return results[:top]


def trend_summary(points: list[dict[str, Any]]) -> dict[str, Any]:
    """First-to-last movement over the series, for the page's headline.

    Reports the first and last dates and average scores and the rounded change, or
    a neutral shape when there are fewer than two points to compare.
    """
    if len(points) < 2:
        return {"points": len(points), "score_delta": None, "first": None, "last": None}
    first, last = points[0], points[-1]
    return {
        "points": len(points),
        "score_delta": round(last["average_score"] - first["average_score"], 1),
        "first": {"date": first["date"], "average_score": first["average_score"]},
        "last": {"date": last["date"], "average_score": last["average_score"]},
    }
