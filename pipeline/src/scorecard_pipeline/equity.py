"""Equity overlay: whose riders are most exposed to bad transit data.

A data gap is not equally consequential everywhere. A feed that drops out of trip
planners hurts most where riders have the fewest alternatives: low-income areas,
households without a car, and people with disabilities (docs/expansion.md,
Phase C). This overlays American Community Survey indicators onto the scorecard so
a state program can prioritize data-quality help by need, not just by grade.

This module is the analysis core plus a thin Census fetch. It works at state
granularity, joining ACS state indicators to each agency by its state, which is
coarse but fully wireable from a handful of public ACS queries (the Census API
requires a free key, CENSUS_API_KEY — keyless requests now redirect to a
missing-key page). The
refinement to tract-level overlays (point-in-polygon of each stop against Census
tracts) is the documented escalation in ADR 0015; the classifier here is the same
shape a tract-level producer would feed.

The classifier and overlay are pure and unit-tested against fixture indicators;
fetching ACS is a thin call.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .comparisons import build_comparison_cohort
from .config import Agency

# ACS thresholds for the "high need" band of each indicator, as a percentage.
# Rough national-reference cutoffs, kept as named constants so a program can tune
# them; they decide only prioritization, never a grade.
POVERTY_HIGH = 18.0  # percent of people below the poverty line
ZERO_VEHICLE_HIGH = 12.0  # percent of households with no vehicle available
DISABILITY_HIGH = 15.0  # percent of the civilian population with a disability

HIGH = "high"
MODERATE = "moderate"
LOWER = "lower"
UNKNOWN = "unknown"

# A grade at or below this counts as a data-quality gap for the overlay's
# "vulnerable riders exposed to weak data" prioritization.
LOW_GRADE = {"D", "F"}


@dataclass(frozen=True)
class EquityIndicators:
    """ACS transit-need indicators for one area. Any value may be missing."""

    poverty_pct: float | None = None
    zero_vehicle_pct: float | None = None
    disability_pct: float | None = None

    def high_count(self) -> int:
        """How many indicators sit in their high-need band."""
        flags = [
            self.poverty_pct is not None and self.poverty_pct >= POVERTY_HIGH,
            self.zero_vehicle_pct is not None and self.zero_vehicle_pct >= ZERO_VEHICLE_HIGH,
            self.disability_pct is not None and self.disability_pct >= DISABILITY_HIGH,
        ]
        return sum(1 for f in flags if f)

    def has_data(self) -> bool:
        return any(
            v is not None for v in (self.poverty_pct, self.zero_vehicle_pct, self.disability_pct)
        )


def need_tier(indicators: EquityIndicators) -> str:
    """Classify an area's transit-need into a tier.

    High when two or more indicators are in their high band, moderate when one is,
    lower when data is present but none are, and unknown when no indicator is
    available. Two-of-three for "high" avoids flagging an area on a single
    indicator alone.
    """
    if not indicators.has_data():
        return UNKNOWN
    count = indicators.high_count()
    if count >= 2:
        return HIGH
    if count == 1:
        return MODERATE
    return LOWER


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def build_overlay(
    dataset_rows: list[dict[str, Any]],
    states_by_agency: dict[str, str],
    state_indicators: dict[str, EquityIndicators],
    *,
    agencies: Iterable[Agency] | None = None,
) -> dict[str, Any]:
    """Join ACS need tiers to guarded feed-score summaries, by state.

    Coverage counts retain every located feed record. Median score, D/F share,
    and the priority worklist use only the same current producer and identity
    contract as other public cross-feed summaries. A missing comparable cohort
    therefore yields ``None`` score fields instead of silently reusing stale or
    duplicate records.
    """
    comparable_rows, comparison = build_comparison_cohort(dataset_rows, agencies=agencies)
    coverage_by_state: dict[str, int] = {}
    for row in dataset_rows:
        state = states_by_agency.get(str(row.get("id") or ""))
        if not state:
            continue
        coverage_by_state[state] = coverage_by_state.get(state, 0) + 1

    comparable_by_state: dict[str, dict[str, Any]] = {}
    for row in comparable_rows:
        state = states_by_agency.get(str(row.get("id") or ""))
        if not state:
            continue
        bucket = comparable_by_state.setdefault(state, {"scores": [], "low": 0, "count": 0})
        bucket["count"] += 1
        if isinstance(row.get("score"), (int, float)):
            bucket["scores"].append(float(row["score"]))
        if row.get("grade") in LOW_GRADE:
            bucket["low"] += 1

    states_out: list[dict[str, Any]] = []
    for state in sorted(coverage_by_state):
        b = comparable_by_state.get(state, {"scores": [], "low": 0, "count": 0})
        indicators = state_indicators.get(state, EquityIndicators())
        tier = need_tier(indicators)
        median = _median(b["scores"])
        low_share = round(b["low"] / b["count"] * 100, 1) if b["count"] else None
        states_out.append(
            {
                "state": state,
                "need_tier": tier,
                # agency_count stays as a v1 compatibility alias. It counts
                # located feed records, not necessarily distinct agencies.
                "agency_count": coverage_by_state[state],
                "feed_record_count": coverage_by_state[state],
                "comparison_eligible_count": b["count"],
                "median_score": round(median, 1) if median is not None else None,
                "low_grade_share": low_share,
                "indicators": {
                    "poverty_pct": indicators.poverty_pct,
                    "zero_vehicle_pct": indicators.zero_vehicle_pct,
                    "disability_pct": indicators.disability_pct,
                },
            }
        )

    # Where vulnerable riders meet weak data: high-need states with a guarded
    # score denominator, highest D/F share first. States without a comparable
    # score cohort remain in ``states`` but make no quality-priority claim.
    priority = sorted(
        (
            state
            for state in states_out
            if state["need_tier"] == HIGH and state["comparison_eligible_count"] > 0
        ),
        key=lambda state: (-float(state["low_grade_share"]), state["state"]),
    )
    return {
        "states": states_out,
        "priority": priority,
        "comparison": comparison,
        "notes": (
            "Need tiers are from ACS poverty, zero-vehicle, and disability shares, "
            "joined by state. Score summaries use one current producer contract across "
            "canonical, non-duplicate feed records. They prioritize data-quality help; "
            "they never change a grade."
        ),
    }


# --- thin Census ACS fetch ----------------------------------------------------

# ACS 5-year variables, by state. The Census API requires a free key
# (CENSUS_API_KEY); keyless requests redirect to a missing-key page. Poverty and
# disability are percentages from subject tables; the
# zero-vehicle share is computed from the detailed table B08201 (no-vehicle
# households over total households), which is stable across years and unambiguous
# (the data-profile vehicle line shifts between vintages).
ACS_YEAR = "2022"
_POVERTY_VAR = "S1701_C03_001E"  # percent below poverty
_DISABILITY_VAR = "S1810_C03_001E"  # percent with a disability
_ZV_TOTAL = "B08201_001E"  # households (denominator)
_ZV_NONE = "B08201_002E"  # households with no vehicle available


def _to_float(value: str) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # The Census API uses large negative sentinels for missing/suppressed cells.
    return f if f > -1000 else None


def parse_acs(
    subject_rows: list[list[str]], detail_rows: list[list[str]]
) -> dict[str, EquityIndicators]:
    """Combine an ACS subject response and a detailed-table response into
    per-state indicators, keyed by the state's full name (the NAME column).

    Each response is the Census API's array-of-arrays: a header row then data
    rows. Columns are matched by name, so the order the API returns them in does
    not matter. The zero-vehicle share is computed from the no-vehicle and total
    household counts.
    """
    poverty: dict[str, float | None] = {}
    disability: dict[str, float | None] = {}
    if subject_rows:
        header = subject_rows[0]
        name_i = header.index("NAME")
        pov_i = header.index(_POVERTY_VAR) if _POVERTY_VAR in header else None
        dis_i = header.index(_DISABILITY_VAR) if _DISABILITY_VAR in header else None
        for row in subject_rows[1:]:
            name = row[name_i]
            if pov_i is not None:
                poverty[name] = _to_float(row[pov_i])
            if dis_i is not None:
                disability[name] = _to_float(row[dis_i])

    zero_vehicle: dict[str, float | None] = {}
    if detail_rows:
        header = detail_rows[0]
        name_i = header.index("NAME")
        total_i = header.index(_ZV_TOTAL) if _ZV_TOTAL in header else None
        none_i = header.index(_ZV_NONE) if _ZV_NONE in header else None
        for row in detail_rows[1:]:
            if total_i is None or none_i is None:
                continue
            total = _to_float(row[total_i])
            none = _to_float(row[none_i])
            if total and none is not None and total > 0:
                zero_vehicle[row[name_i]] = round(none / total * 100, 1)

    states = set(poverty) | set(disability) | set(zero_vehicle)
    return {
        name: EquityIndicators(
            poverty_pct=poverty.get(name),
            zero_vehicle_pct=zero_vehicle.get(name),
            disability_pct=disability.get(name),
        )
        for name in states
    }


def _fetch_acs_rows(url: str) -> list[list[str]]:
    """Fetch one Census API query, returning its array-of-arrays.

    Retries on transient/WAF failures and sends a descriptive User-Agent. The
    Census API requires a key: a keyless request 302-redirects to an HTML
    missing-key page, so a non-JSON response raises a clear error naming what
    came back rather than a bare JSONDecodeError.
    """
    import json

    from .net import safe_get

    headers = {"User-Agent": "gtfs-scorecard/1.0 (equity overlay)"}
    body = safe_get(url, headers=headers, timeout=60, retries=2).decode().strip()
    try:
        rows = json.loads(body)
    except ValueError as exc:
        snippet = body[:160] or "<empty body>"
        raise ValueError(
            "Census returned non-JSON. The Census API requires a key (a keyless request "
            "redirects to missing_key.html); set a free CENSUS_API_KEY "
            f"(https://api.census.gov/data/key_signup.html). Body starts: {snippet!r}"
        ) from exc
    if not isinstance(rows, list):
        raise ValueError(f"Census response was not an array: {str(rows)[:120]!r}")
    return rows


def fetch_state_indicators(year: str = ACS_YEAR) -> dict[str, EquityIndicators]:
    """Fetch per-state ACS indicators from the Census API.

    Requires a free ``CENSUS_API_KEY`` (env var): the Census API redirects
    keyless requests to a missing-key page. Sign up at
    https://api.census.gov/data/key_signup.html and set it as a repo secret.
    """
    import os

    base = f"https://api.census.gov/data/{year}/acs/acs5"
    subject_url = f"{base}/subject?get=NAME,{_POVERTY_VAR},{_DISABILITY_VAR}&for=state:*"
    detail_url = f"{base}?get=NAME,{_ZV_TOTAL},{_ZV_NONE}&for=state:*"
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if key:
        suffix = f"&key={key}"
        subject_url += suffix
        detail_url += suffix
    return parse_acs(_fetch_acs_rows(subject_url), _fetch_acs_rows(detail_url))


def render_overlay(overlay: dict[str, Any]) -> str:
    """A markdown equity report for a program lead."""
    priority = overlay.get("priority", [])
    lines = ["# Equity overlay: where weak data meets high need", ""]
    comparable_count = int((overlay.get("comparison") or {}).get("eligible_count") or 0)
    if comparable_count == 0:
        lines.append(
            "Score-based priority is unavailable until current-contract checks create a "
            "comparable cohort. ACS need tiers remain available below."
        )
    elif not priority:
        lines.append(
            "No state currently meets the high-need threshold (two or more of the ACS "
            "poverty, zero-vehicle, and disability indicators in their high band), or the "
            "ACS data has not loaded."
        )
    else:
        lines.append("High-need states (ACS), ordered by the share of feeds on a D or F grade:")
        lines.append("")
        lines.append("| State | Low-grade share | Comparable feeds | Median score |")
        lines.append("| --- | --- | --- | --- |")
        for s in priority:
            lines.append(
                f"| {s['state']} | {s['low_grade_share']}% | "
                f"{s['comparison_eligible_count']} "
                f"| {s['median_score']} |"
            )
    lines.append("")
    lines.append(str(overlay.get("notes", "")))
    return "\n".join(lines)
