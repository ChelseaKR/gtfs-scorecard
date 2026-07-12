"""A national view of the most common GTFS problems.

Every agency's scorecard lists that feed's findings (validator notices and the
scorecard's own plain-language checks), each already rewritten as a fix. Across
the corpus those findings answer a question no single scorecard can: what are the
most widespread GTFS problems in the country, how many feeds hit each, and what is
the one fix? This rolls the per-agency findings up into that picture, a standing
"state of GTFS quality" knowledge base that also tells each fix guide how common
its problem is.

It is pure over the findings the renderer already reads, so the artifact is
reproducible and adds no per-agency work. Prevalence is the share of tracked feeds
carrying a finding, framed as how many agencies share the same fixable problem,
never as a ranking of who is worst. It changes no grade.

This rollup deliberately has no geographic breakdown. Its input is a list of
finding lists with agency identity and location already removed, so attaching a
country afterward would require guessing. A future country split must begin with
an identity-carrying input rather than force location rows onto this contract.
"""

from __future__ import annotations

from typing import Any

from .notices import TRANSLATIONS

# Findings the scorecard synthesizes carry a "scorecard_" code prefix; everything
# else is a canonical MobilityData validator notice. Surfacing the source lets the
# page say which problems the validator flags versus which the scorecard adds.
SCORECARD_PREFIX = "scorecard_"


def agency_findings(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """The distinct findings in one agency's artifact, across measured categories.

    Deduplicates by code within the agency (a code counts once per feed however
    many categories surface it) and keeps the per-feed instance count and the
    plain-language what/why/fix so the rollup can show a representative fix. Returns
    an empty list when nothing measured, so an unscored agency adds nothing.
    """
    by_code: dict[str, dict[str, Any]] = {}
    for cat in artifact.get("categories", {}).values():
        if cat.get("status") != "measured":
            continue
        for f in cat.get("findings", []) or []:
            code = f.get("code")
            if not code or code in by_code:
                continue
            by_code[code] = {
                "code": str(code),
                "severity": f.get("severity", ""),
                "count": int(f.get("count") or 0),
                "what": f.get("what", ""),
                "why": f.get("why", ""),
                "fix": f.get("fix", ""),
                "effort": f.get("effort", ""),
            }
    return list(by_code.values())


def national_problems(
    per_agency: list[list[dict[str, Any]]], *, total_agencies: int, top: int = 25
) -> dict[str, Any]:
    """Roll per-agency findings up into national problem prevalence.

    ``per_agency`` is one ``agency_findings`` list per scored agency.
    ``total_agencies`` is the full tracked count, so prevalence is the share of all
    feeds (not only the ones with findings). For each code it reports how many
    agencies carry it, the share that is, total instances across feeds, the
    severity, the source (validator or scorecard), and a representative
    plain-language what/why/fix. Ranked by agencies affected, then instances, then
    code for stability. Returns the top problems plus a code-to-prevalence map for
    the fix guides.
    """
    agencies: dict[str, int] = {}
    instances: dict[str, int] = {}
    meta: dict[str, dict[str, Any]] = {}
    for findings in per_agency:
        for f in findings:
            code = f["code"]
            agencies[code] = agencies.get(code, 0) + 1
            instances[code] = instances.get(code, 0) + int(f.get("count") or 0)
            # Keep the first representative copy with non-empty fix text.
            if code not in meta or (not meta[code].get("fix") and f.get("fix")):
                meta[code] = f

    def _pct(n: int) -> float:
        return round(n / total_agencies * 100, 1) if total_agencies else 0.0

    ranked_codes = sorted(agencies, key=lambda c: (-agencies[c], -instances.get(c, 0), c))
    problems = []
    for code in ranked_codes[:top]:
        m = meta[code]
        problems.append(
            {
                "code": code,
                "source": "scorecard" if code.startswith(SCORECARD_PREFIX) else "validator",
                "severity": m.get("severity", ""),
                "agencies": agencies[code],
                "prevalence_pct": _pct(agencies[code]),
                "instances": instances[code],
                "what": m.get("what", ""),
                "why": m.get("why", ""),
                "fix": m.get("fix", ""),
                "effort": m.get("effort", ""),
            }
        )

    # Instances ride along so the plain-language coverage metric can weight codes
    # by how often a reader actually encounters them, not just by distinct code.
    prevalence_by_code = {
        code: {
            "agencies": agencies[code],
            "prevalence_pct": _pct(agencies[code]),
            "instances": instances.get(code, 0),
        }
        for code in agencies
    }
    return {
        "total_agencies": total_agencies,
        "distinct_problems": len(agencies),
        "problems": problems,
        "prevalence_by_code": prevalence_by_code,
    }


def _is_curated(code: str) -> bool:
    """Whether a finding code carries vetted plain-language text.

    Validator notices are curated when ``notices.TRANSLATIONS`` has an entry;
    scorecard-synthesized findings (``scorecard_`` prefix) are authored in plain
    language by construction, so they always count as curated.
    """
    return code in TRANSLATIONS or code.startswith(SCORECARD_PREFIX)


def plain_language_coverage(rollup: dict[str, Any]) -> dict[str, Any]:
    """How much of the national findings population has curated plain language.

    Pure over a ``national_problems`` rollup. Coverage is computed two ways:
    ``distinct_code_coverage`` is the share of distinct codes with curated text,
    and ``instance_weighted_coverage`` is the share of all finding instances a
    reader sees nationally that carry it — the number that tells us whether the
    plain-language promise holds where people actually look. Also returns the
    curation queue: uncurated codes ranked by national instance count (then
    agencies affected, then code for stability), so editorial effort goes to the
    most-encountered gap first. An empty rollup is vacuously fully covered.
    """
    by_code: dict[str, Any] = rollup.get("prevalence_by_code", {})
    curated = {code for code in by_code if _is_curated(code)}
    total_instances = sum(int(by_code[c].get("instances") or 0) for c in by_code)
    curated_instances = sum(int(by_code[c].get("instances") or 0) for c in curated)

    def _pct(part: int, whole: int) -> float:
        return round(part / whole * 100, 1) if whole else 100.0

    queue: list[dict[str, Any]] = [
        {
            "code": code,
            "instances": int(by_code[code].get("instances") or 0),
            "agencies": int(by_code[code].get("agencies") or 0),
        }
        for code in by_code
        if code not in curated
    ]
    queue.sort(key=lambda q: (-q["instances"], -q["agencies"], q["code"]))
    return {
        "distinct_code_coverage": _pct(len(curated), len(by_code)),
        "instance_weighted_coverage": _pct(curated_instances, total_instances),
        "curated_codes": len(curated),
        "total_codes": len(by_code),
        "uncurated_queue": queue,
    }


def coverage_regression(previous: dict[str, Any] | None, current: dict[str, Any]) -> str | None:
    """Advisory message when instance-weighted coverage fell below the baseline.

    The FIX-08 governance loop's weekly check: coverage normally only rises
    (curation adds entries), so a fall means new high-volume notice codes are
    reaching readers with generic fallback text, and the curation queue is
    where the next editorial effort should go. Pure over the saved baseline
    and a fresh ``plain_language_coverage`` result; persisting the baseline is
    the caller's decision, the same split the portfolio digest uses. Returns
    None when there is no baseline yet or nothing regressed.
    """
    if not previous:
        return None
    prev = float(previous.get("instance_weighted_coverage", 0.0))
    cur = float(current["instance_weighted_coverage"])
    if cur >= prev:
        return None
    return (
        f"COVERAGE DROP: instance-weighted plain-language coverage fell to {cur}% "
        f"from {prev}% (baseline saved {previous.get('as_of', 'on an unknown date')}). "
        "New high-volume notice codes are reaching readers with generic fallback "
        "text; the curation queue on /problems/ shows which to translate next."
    )
