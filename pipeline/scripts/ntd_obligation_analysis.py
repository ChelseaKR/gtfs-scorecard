#!/usr/bin/env python3
"""EXP-16 analysis: cross-sectional comparison of feed-quality scores between
agencies matched to an NTD ID (our proxy for an NTD GTFS-reporting obligation)
and agencies not matched, using this repo's own daily-scored artifact data.

Pure stdlib (no numpy/scipy in the pipeline venv). Implements:
  - descriptive stats (n, mean, median, stdev, quartiles)
  - Mann-Whitney U with normal approximation (continuity-corrected) for p
  - Welch's t-test with a normal-approximation p-value (large n on both sides)
  - rank-biserial correlation (effect size for Mann-Whitney)
  - Cohen's d (effect size for the mean comparison)

See docs/research/EXP-16-ntd-policy-effect-study.md for the write-up, the
honest-caveats framing, and the citations behind the "obligation proxy" this
script uses (ntd_id presence in the agency registry). This is a one-off research
script, not a maintained pipeline module, and it is not wired into CI.

Run from the repo root:
    python3 pipeline/scripts/ntd_obligation_analysis.py
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from scorecard_pipeline.agencies import read_agencies  # noqa: E402

ARTIFACTS_DIR = ROOT / "data" / "artifacts"


def load_registry() -> list[dict[str, object]]:
    return [asdict(agency) for agency in read_agencies()]


def latest_artifact(agency_id: str) -> dict[str, Any] | None:
    d = ARTIFACTS_DIR / agency_id
    if not d.is_dir():
        return None
    dated = sorted(p for p in d.glob("*.json") if p.stem.count("-") == 2)
    if not dated:
        return None
    latest = dated[-1]
    try:
        loaded: dict[str, Any] = json.loads(latest.read_text())
        return loaded
    except (json.JSONDecodeError, OSError):
        return None


def mean(xs: list[float]) -> float:
    return statistics.mean(xs) if xs else float("nan")


def median(xs: list[float]) -> float:
    return statistics.median(xs) if xs else float("nan")


def quartiles(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return (float("nan"), float("nan"))
    q = statistics.quantiles(sorted(xs), n=4, method="inclusive")
    return (q[0], q[2])  # Q1, Q3


def describe(xs: list[float], label: str) -> None:
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if n == 0:
        print(f"  {label}: n=0")
        return
    q1, q3 = quartiles(xs)
    sd = statistics.pstdev(xs) if n > 1 else 0.0
    print(
        f"  {label}: n={n}  mean={mean(xs):.1f}  median={median(xs):.1f}  "
        f"sd={sd:.1f}  IQR=[{q1:.1f}, {q3:.1f}]  min={min(xs):.1f}  max={max(xs):.1f}"
    )


def mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float, float]:
    """Return (U, z, rank-biserial correlation). Normal approximation with
    continuity correction and an average-rank tie correction, valid for the
    sample sizes here (no scipy available in this environment)."""
    labeled = [(v, 0) for v in a] + [(v, 1) for v in b]
    labeled.sort(key=lambda t: t[0])

    ranks = [0.0] * len(labeled)
    i = 0
    while i < len(labeled):
        j = i
        while j < len(labeled) and labeled[j][0] == labeled[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j

    n1, n2 = len(a), len(b)
    r1 = sum(r for (_v, g), r in zip(labeled, ranks, strict=True) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    # Tie correction for the variance term.
    tie_term = 0.0
    i = 0
    while i < len(labeled):
        j = i
        while j < len(labeled) and labeled[j][0] == labeled[i][0]:
            j += 1
        t = j - i
        if t > 1:
            tie_term += t**3 - t
        i = j
    n_total = n1 + n2
    mu_u = n1 * n2 / 2.0
    sigma_u = (
        math.sqrt((n1 * n2 / 12.0) * ((n_total + 1) - tie_term / (n_total * (n_total - 1))))
        if n_total > 1
        else 0.0
    )
    if sigma_u == 0:
        z = 0.0
    else:
        # Continuity correction toward the mean.
        z = (u1 - mu_u + 0.5) / sigma_u if u1 < mu_u else (u1 - mu_u - 0.5) / sigma_u
    rank_biserial = 1 - (2 * u) / (n1 * n2) if n1 * n2 else 0.0
    return u1, z, rank_biserial


def normal_sf_two_sided(z: float) -> float:
    """Two-sided p-value from a standard normal z, via erf."""
    return math.erfc(abs(z) / math.sqrt(2))


def welch_t(a: list[float], b: list[float]) -> tuple[float, float, float, float]:
    n1, n2 = len(a), len(b)
    m1, m2 = mean(a), mean(b)
    v1 = statistics.variance(a) if n1 > 1 else 0.0
    v2 = statistics.variance(b) if n2 > 1 else 0.0
    se = math.sqrt(v1 / n1 + v2 / n2) if n1 and n2 else float("nan")
    t = (m1 - m2) / se if se else float("nan")
    # Welch-Satterthwaite df (reported, not used for a t-table lookup here; p
    # is approximated via the standard normal, reasonable given n well > 30 on
    # both sides).
    if v1 or v2:
        df = (v1 / n1 + v2 / n2) ** 2 / (
            (v1**2 / (n1**2 * (n1 - 1)) if n1 > 1 else 0)
            + (v2**2 / (n2**2 * (n2 - 1)) if n2 > 1 else 0)
        )
    else:
        df = float("nan")
    n_total = n1 + n2
    if n_total > 2:
        pooled_sd = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n_total - 2))
    else:
        pooled_sd = float("nan")
    cohens_d = (m1 - m2) / pooled_sd if pooled_sd else float("nan")
    p = normal_sf_two_sided(t) if not math.isnan(t) else float("nan")
    return t, df, p, cohens_d


Group = list[tuple[dict[str, Any], dict[str, Any]]]


def scores(group: Group, path: list[str]) -> list[float]:
    out = []
    for _agency, art in group:
        v: object = art
        ok = True
        for p in path:
            if isinstance(v, dict) and p in v:
                v = v[p]
            else:
                ok = False
                break
        if ok and isinstance(v, int | float):
            out.append(float(v))
    return out


def measured_scores(group: Group, cat: str) -> list[float]:
    out = []
    for _agency, art in group:
        c = art.get("categories", {}).get(cat, {})
        if c.get("status") == "measured" and isinstance(c.get("score"), int | float):
            out.append(float(c["score"]))
    return out


def load_groups() -> tuple[Group, Group]:
    registry = load_registry()
    print(f"Registry entries: {len(registry)}")

    rows = []
    missing_artifact = 0
    for agency in registry:
        art = latest_artifact(str(agency["id"]))
        if art is None:
            missing_artifact += 1
            continue
        rows.append((agency, art))
    print(
        f"Registry entries with at least one scored artifact: {len(rows)} "
        f"(no artifact found for {missing_artifact})"
    )

    us_rows = [(a, art) for a, art in rows if a.get("country", "US") != "CA"]
    ca_count = len(rows) - len(us_rows)
    print(f"Excluded as non-US (NTD is a US program): {ca_count}")
    print(f"US-scoped analysis set: {len(us_rows)}")

    obligated = [(a, art) for a, art in us_rows if a.get("ntd_id")]
    not_obligated = [(a, art) for a, art in us_rows if not a.get("ntd_id")]
    print(f"\nNTD-ID-matched (obligation proxy = True): {len(obligated)}")
    print(f"Not matched (obligation proxy = False):   {len(not_obligated)}")
    return obligated, not_obligated


def report_overall_score(obligated: Group, not_obligated: Group) -> None:
    print("\n=== Overall score ===")
    ob = scores(obligated, ["overall", "score"])
    nob = scores(not_obligated, ["overall", "score"])
    describe(ob, "NTD-ID-matched")
    describe(nob, "Not matched")
    u1, z, rb = mann_whitney_u(ob, nob)
    p_mw = normal_sf_two_sided(z)
    print(f"  Mann-Whitney U={u1:.0f}  z={z:.2f}  p={p_mw:.4g}  rank-biserial r={rb:.3f}")
    t, df, p_t, d = welch_t(ob, nob)
    print(f"  Welch t={t:.2f}  df~{df:.0f}  p={p_t:.4g}  Cohen's d={d:.3f}")


def report_grade_distribution(obligated: Group, not_obligated: Group) -> None:
    print("\n=== Grade distribution ===")
    for label, group in [("NTD-ID-matched", obligated), ("Not matched", not_obligated)]:
        grades = [art.get("overall", {}).get("grade") for _a, art in group]
        c = Counter(grades)
        n = len(grades)
        parts = [f"{g}:{c[g]} ({100 * c[g] / n:.0f}%)" for g in ["A", "B", "C", "D", "F"] if g in c]
        print(f"  {label} (n={n}): {', '.join(parts)}")


def report_category_scores(obligated: Group, not_obligated: Group) -> None:
    print("\n=== Category scores (measured only) ===")
    categories = [
        ("Correctness", "correctness"),
        ("Freshness", "freshness"),
        ("Rider-experience completeness", "completeness"),
        ("Realtime", "realtime"),
    ]
    for cat, key in categories:
        ob = measured_scores(obligated, key)
        nob = measured_scores(not_obligated, key)
        print(f"-- {cat} --")
        describe(ob, "NTD-ID-matched")
        describe(nob, "Not matched")
        if ob and nob:
            _u1, z, rb = mann_whitney_u(ob, nob)
            p_mw = normal_sf_two_sided(z)
            print(f"  Mann-Whitney z={z:.2f}  p={p_mw:.4g}  rank-biserial r={rb:.3f}")


def report_rate(
    obligated: Group,
    not_obligated: Group,
    title: str,
    predicate: Callable[[dict[str, Any]], bool],
) -> None:
    print(f"\n=== {title} ===")
    for label, group in [("NTD-ID-matched", obligated), ("Not matched", not_obligated)]:
        n = len(group)
        hits = sum(1 for _a, art in group if predicate(art))
        print(f"  {label}: {hits}/{n} ({100 * hits / n:.0f}%)")


def report_size_proxy(obligated: Group, not_obligated: Group) -> None:
    print("\n=== Size proxy: stop_count (a resourcing / urbanicity proxy) ===")
    describe(scores(obligated, ["geo", "stop_count"]), "NTD-ID-matched")
    describe(scores(not_obligated, ["geo", "stop_count"]), "Not matched")


def report_breakdown(obligated: Group, not_obligated: Group, title: str, path: list[str]) -> None:
    print(f"\n=== {title} ===")
    for label, group in [("NTD-ID-matched", obligated), ("Not matched", not_obligated)]:
        n = len(group)
        values = []
        for _a, art in group:
            v: object = art
            for p in path:
                v = v.get(p, {}) if isinstance(v, dict) else {}
            values.append(v if v != {} else None)
        c = Counter(values)
        parts = [f"{k}:{v} ({100 * v / n:.0f}%)" for k, v in c.most_common()]
        print(f"  {label} (n={n}): {', '.join(parts)}")


def main() -> None:
    obligated, not_obligated = load_groups()
    report_overall_score(obligated, not_obligated)
    report_grade_distribution(obligated, not_obligated)
    report_category_scores(obligated, not_obligated)
    report_rate(
        obligated,
        not_obligated,
        "Realtime-publication rate (a resourcing / urbanicity proxy)",
        lambda art: art.get("categories", {}).get("realtime", {}).get("status") == "measured",
    )
    report_size_proxy(obligated, not_obligated)
    report_breakdown(
        obligated,
        not_obligated,
        "Confidence level (measurement completeness)",
        ["confidence", "level"],
    )
    report_rate(
        obligated,
        not_obligated,
        "Feed reachability (own URL vs mirror fallback)",
        lambda art: bool(art.get("feed", {}).get("reachable")),
    )
    report_breakdown(
        obligated,
        not_obligated,
        "NTD certification readiness (published/valid/current pillars)",
        ["ntd_readiness", "status"],
    )


if __name__ == "__main__":
    main()
