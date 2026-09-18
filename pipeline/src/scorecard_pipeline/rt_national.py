"""A covered-set view of GTFS-Realtime reliability.

The realtime monitor records, per agency, a longitudinal series of uptime and
header-lag observations in ``data/rt-health`` (ADR 0012), and each agency page
already shows that agency's reliability (``render_site._rt_health_section``). What
the per-agency view cannot answer is the aggregate one a data team or a regional
program asks: of the agencies that publish a realtime feed, how many are actually
reliable, and how fresh is the data when it arrives?

This rolls the per-agency ``RtHealth`` summaries up into one covered-set picture:
a reliability-band distribution, median uptime and freshness, portable
country/subdivision groups, a U.S.-state breakdown, and the most reliable feeds.
It is pure over the summaries the monitor already produces, so the artifact is
reproducible and adds no polling. It also states when those summaries were
gathered (``observed_vintage``), because the document's own build stamp is not a
claim about the data in it.
It stays inside the serverless model: it reads the samples the Actions cron
already records and does not stand up a continuous worker fleet. Absence of a
realtime feed is shown as "not monitored", never as a zero, the same way a missing
realtime feed is neutral on a scorecard.

Reliability is the share of monitor runs where the feed responded (uptime); it is
not a grade input and changes no score.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ._stats import _median
from .config import current_agency_ids
from .location_rollups import portable_location_fields, portable_location_rollups

# Reliability bands by uptime (share of monitor runs the feed responded to). The
# breakpoints separate feeds a rider can count on from ones that flap, without
# pretending a single dropped sample is an outage. "Reliable" sits at 99% because
# realtime is meant to be always-on; "spotty" below 90% is where a rider would
# notice the gaps.
RELIABLE_THRESHOLD = 99.0
MOSTLY_THRESHOLD = 90.0

# An agency needs at least this many observations before it is ranked, so a feed
# monitored once does not top the "most reliable" list on a single lucky sample.
MIN_OBSERVATIONS = 3


def reliability_band(uptime_pct: float) -> str:
    """The reliability band for an uptime share.

    ``reliable`` at or above 99%, ``spotty`` below 90%, ``mostly`` in between.
    Three plain buckets so the covered-set picture reads without a chart.
    """
    if uptime_pct >= RELIABLE_THRESHOLD:
        return "reliable"
    if uptime_pct >= MOSTLY_THRESHOLD:
        return "mostly"
    return "spotty"


def observed_vintage(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """When the observations behind this rollup were actually taken.

    The rollup carries one build date and the rows it summarizes do not have to
    share it. ``rt-monitor.yml`` recorded nothing between 2026-09-05 and
    2026-09-08 while ``/realtime/`` and ``api/v1/realtime.json`` were rebuilt on
    the intraday cadence, stamped with the build date and describing a corpus
    nobody had sampled since the 5th (#389). Each member already knows its own
    ``last_ts``; this states it at the level a reader looks at.

    A national rollup has as many vintages as it has members, so three dates are
    reported rather than one: the newest observation anywhere in the corpus, the
    oldest member's newest observation, and the median of those per-member dates.
    The newest alone would hide a long tail of stale members behind one fresh
    one; the median says whether the corpus is mostly fresh with an outlier or
    mostly stale. All three are read off recorded timestamps, so — like the
    per-agency window, which names the date it ends — this needs no threshold
    for how stale is too stale, and cannot drift when the monitor stops. Every
    date published here is a date some feed record was actually observed on.

    Members that record no ``last_ts`` are counted, never quietly dropped from
    the denominator: a date nobody recorded is absence, and it says so.
    """
    dated = [
        int(summary["last_ts"])
        for summary in summaries
        if isinstance(summary.get("last_ts"), int) and not isinstance(summary.get("last_ts"), bool)
    ]
    undated = len(summaries) - len(dated)
    if not dated:
        return {
            "feed_records_dated": 0,
            "feed_records_undated": undated,
            "oldest_last_observation": None,
            "median_last_observation": None,
            "newest_last_observation": None,
        }
    # The older of the two middle dates when the count is even, rather than
    # their mean. Averaging two timestamps produces a date no feed record was
    # observed on -- a value invented by the arithmetic -- and erring toward the
    # older of the two never makes the corpus look fresher than it is.
    ordered = sorted(dated)
    median = ordered[(len(ordered) - 1) // 2]
    return {
        "feed_records_dated": len(dated),
        "feed_records_undated": undated,
        "oldest_last_observation": _utc_day(ordered[0]),
        "median_last_observation": _utc_day(median),
        "newest_last_observation": _utc_day(ordered[-1]),
    }


def _utc_day(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).date().isoformat()


def _with_portable_location(summary: dict[str, Any]) -> dict[str, Any]:
    """Carry explicit location, falling back to the loaded agency registry.

    The realtime monitor's historical summaries predate portable location
    fields. The site renderer loads the agency registry before aggregating, so
    this compatibility lookup lets those summaries publish honest country rows
    without changing the monitor's stored health schema.
    """
    source = summary
    if not summary.get("country"):
        from .config import AGENCIES

        agency = AGENCIES.get(str(summary.get("id") or ""))
        if agency is not None:
            source = {
                **summary,
                "country": agency.country,
                "subdivision_code": agency.subdivision_code,
                "subdivision_name": agency.subdivision_name,
            }
    return {**summary, **portable_location_fields(source)}


def _location_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Realtime reliability for one country or subdivision."""
    uptimes = [float(record["uptime_pct"]) for record in records]
    median = _median(uptimes)
    return {
        "feed_records": len(records),
        # v1 compatibility alias. These rows count feed records, not distinct
        # operating organizations.
        "agencies": len(records),
        "median_uptime_pct": round(median, 1) if median is not None else None,
        "reliable": sum(reliability_band(value) == "reliable" for value in uptimes),
    }


def national_rt(summaries: list[dict[str, Any]], *, top: int = 10) -> dict[str, Any]:
    """Roll per-agency realtime-health summaries up into the covered-set picture.

    Each summary carries at least id, name, state, observations, uptime_pct, and
    median_lag_seconds (the ``RtHealth`` fields plus identity). Agencies with no
    observations are dropped (they are not monitored, shown neutrally elsewhere).
    Reports how many agencies are monitored, the reliability-band distribution,
    median uptime and header lag, portable location groups, a U.S.-state
    breakdown, and the most reliable feeds (ranked by uptime then freshness,
    requiring a minimum number of observations). Pure and deterministic, safe
    to re-run. ``top`` caps the highlight list so the artifact stays light.
    """
    current_ids = set(current_agency_ids(str(summary.get("id") or "") for summary in summaries))
    monitored = [
        _with_portable_location(summary)
        for summary in summaries
        if str(summary.get("id") or "") in current_ids and int(summary.get("observations", 0)) > 0
    ]
    bands = {"reliable": 0, "mostly": 0, "spotty": 0}
    uptimes: list[float] = []
    lags: list[float] = []
    by_state: dict[str, dict[str, Any]] = {}
    for s in monitored:
        uptime = float(s["uptime_pct"])
        bands[reliability_band(uptime)] += 1
        uptimes.append(uptime)
        if s.get("median_lag_seconds") is not None:
            lags.append(float(s["median_lag_seconds"]))
        if s.get("country") != "US":
            continue
        state = s.get("state") or "Unlocated"
        bucket = by_state.setdefault(
            state, {"state": state, "agencies": 0, "_uptime": [], "reliable": 0}
        )
        bucket["agencies"] += 1
        bucket["_uptime"].append(uptime)
        if reliability_band(uptime) == "reliable":
            bucket["reliable"] += 1

    states = []
    for state in sorted(by_state, key=lambda s: (-by_state[s]["agencies"], s)):
        b = by_state[state]
        med = _median(b["_uptime"])
        states.append(
            {
                "state": state,
                "feed_records": b["agencies"],
                "agencies": b["agencies"],
                "median_uptime_pct": round(med, 1) if med is not None else None,
                "reliable": b["reliable"],
            }
        )

    rankable = [s for s in monitored if int(s.get("observations", 0)) >= MIN_OBSERVATIONS]
    most_reliable = sorted(
        rankable,
        key=lambda s: (
            -float(s["uptime_pct"]),
            float(s["median_lag_seconds"]) if s.get("median_lag_seconds") is not None else 1e9,
            s.get("name", s.get("id", "")),
        ),
    )[:top]

    median_uptime = _median(uptimes)
    median_lag = _median(lags)
    return {
        "monitored_feed_record_count": len(monitored),
        # When the rows were gathered, as distinct from when the document was
        # built. See observed_vintage: the payload's `generated_at` is a build
        # stamp and describes nothing about the observations (#389).
        "observed": observed_vintage(monitored),
        # v1 compatibility alias. The metric denominator is feed records.
        "monitored_count": len(monitored),
        "bands": bands,
        "median_uptime_pct": round(median_uptime, 1) if median_uptime is not None else None,
        "median_lag_seconds": int(median_lag) if median_lag is not None else None,
        "states": states,
        "countries": portable_location_rollups(monitored, _location_summary),
        "most_reliable": [
            {
                "id": s["id"],
                "name": s.get("name", s["id"]),
                "state": (s.get("state") or "Unlocated") if s["country"] == "US" else "",
                "country": s["country"],
                "subdivision_code": s["subdivision_code"],
                "subdivision_name": s["subdivision_name"],
                "uptime_pct": round(float(s["uptime_pct"]), 1),
                "median_lag_seconds": s.get("median_lag_seconds"),
            }
            for s in most_reliable
        ],
    }
