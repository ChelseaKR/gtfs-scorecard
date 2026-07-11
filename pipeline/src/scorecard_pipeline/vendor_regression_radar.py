"""A standing cross-corpus radar for same-day vendor regressions.

`roadmap.md` Year 2 names catching "the day a vendor software update quietly
breaks fare data for forty customers at once" as a private vendor signal, and
`anomaly.py` already flags an implausible step in one agency's own history.
What is missing is the corpus-wide version: a daily scan, grouped by detected
producing tool (`tool_profiles.py`) and notice code, that asks whether a code
appeared today for an unusual share of one tool's cohort at once. A shared
export change looks like several agencies behind the same tool acquiring the
same new finding on the same day; one agency's ordinary churn does not.

The output is deliberately two-tier (docs/ideation/03-expansions.md, EXP-07):
a private per-vendor worklist that names the affected agencies and is routed
internally, ready to forward to a vendor contact, and a public de-identified
aggregate digest that names the tool and the scale but never an agency. Only
the digest is fit for the public site; outward vendor-facing framing (actually
contacting a vendor) is a separate step, gated on a live vendor-interview
partnership (RR:E4) this module does not perform.

This module is pure over already-loaded artifact dicts, mirroring `anomaly.py`
and `fixlog.py`: it reads the same dated-artifact findings the pipeline already
writes and computes on them, so it adds no new fetch or storage and stays
testable without disk.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .tool_profiles import ToolProfile, detect_tool

# The "freshness" category carries calendar-countdown findings (e.g. "expires
# within 30 days") that cross their threshold on a schedule set by each feed's
# own service window, not by anything the producing tool changed. Agencies
# behind one shared host often republish on a similar cadence, so those
# countdowns cross in step across a whole cohort on an ordinary day — a real
# same-day correlation, but one with nothing to do with a vendor export
# regression, and a worklist that named it as one would misdirect the one
# email a manager sends.
_EXCLUDED_CATEGORIES = frozenset({"freshness"})

# The same countdown problem also shows up as raw validator notices filed
# under "correctness" rather than "freshness" (docs/rubric.md's category split
# is about scoring weight, not about what is calendar-driven), so the category
# exclusion above is not sufficient on its own. These specific codes are
# excluded by name for the same reason, wherever they're categorized:
# scorecard_* mirrors metrics.py's freshness findings; the rest are the
# gtfs-validator notices for the same calendar-countdown condition
# (rule_links.py).
_EXCLUDED_CODES = frozenset(
    {
        "scorecard_feed_expired",
        "scorecard_feed_expiring_soon",
        "scorecard_no_expiry_date",
        "feed_expiration_date7_days",
        "feed_expiration_date30_days",
        "expired_calendar",
    }
)

# A cohort must have at least this many agencies scored both today and
# yesterday before a same-day pattern says anything about the tool rather than
# a couple of agencies' unrelated feed changes.
MIN_COHORT_SIZE = 3

# Share of an eligible cohort that must newly show a code today before it
# reads as a shared regression rather than ordinary day-to-day churn.
MIN_SPIKE_SHARE = 0.25

# Absolute floor alongside the share: two agencies out of a four-agency cohort
# is 50%, but is still just two agencies having a bad day independently.
MIN_SPIKE_AGENCIES = 3


@dataclass(frozen=True)
class AgencyRun:
    """One agency's paired before/after dated artifacts for a single scan.

    `prev_artifact` is the most recent dated artifact strictly before
    `curr_artifact`'s snapshot date, or `None` for an agency scanned for the
    first time (it contributes no signal either way — there is nothing to
    compare against yet). `agency_id`/`agency_name` identify the agency for the
    private worklist only; the public digest never carries them.
    """

    agency_id: str
    agency_name: str
    static_url: str | None
    curr_artifact: dict[str, Any]
    prev_artifact: dict[str, Any] | None = None


@dataclass(frozen=True)
class VendorRegression:
    """A same-day spike in one notice code within one producing-tool cohort."""

    tool_key: str
    tool_name: str
    code: str
    what: str
    date: str
    cohort_size: int
    new_agencies: int
    affected_ids: tuple[str, ...]
    affected_names: tuple[str, ...]
    fix_path: str
    request_lede: str


def _regression_codes(artifact: dict[str, Any]) -> dict[str, str]:
    """Map each finding code to its 'what' text, across measured categories
    other than `_EXCLUDED_CATEGORIES`, and excluding `_EXCLUDED_CODES`.

    Mirrors `fixlog.finding_codes` (a code counts only when its category was
    actually measured, so an unmeasured category is never read as a finding
    appearing or clearing) but additionally drops calendar-countdown findings
    that would otherwise correlate across a cohort for reasons having nothing
    to do with the producing tool.
    """
    out: dict[str, str] = {}
    for key, cat in artifact.get("categories", {}).items():
        if key in _EXCLUDED_CATEGORIES or cat.get("status") != "measured":
            continue
        for f in cat.get("findings", []):
            code = f.get("code")
            if code and code not in _EXCLUDED_CODES:
                out.setdefault(str(code), str(f.get("what", "")))
    return out


def _cohorts(runs: list[AgencyRun]) -> dict[str, tuple[ToolProfile, list[AgencyRun]]]:
    """Group runs by detected producing tool.

    Hosts that match no documented tool profile (generic hosting, an agency's
    own website) carry no producing-tool signal and are excluded on purpose:
    the same-day shape there says nothing about a shared export tool, and
    could not be routed to a vendor contact if it did.
    """
    grouped: dict[str, tuple[ToolProfile, list[AgencyRun]]] = {}
    for run in runs:
        profile = detect_tool(run.static_url)
        if profile is None:
            continue
        _, members = grouped.setdefault(profile.key, (profile, []))
        members.append(run)
    return grouped


def detect_regressions(
    runs: list[AgencyRun],
    *,
    min_cohort: int = MIN_COHORT_SIZE,
    min_spike_share: float = MIN_SPIKE_SHARE,
    min_spike_agencies: int = MIN_SPIKE_AGENCIES,
) -> list[VendorRegression]:
    """Same-day spikes in a notice code's incidence within a producing-tool cohort.

    For each detected tool with at least `min_cohort` agencies comparable today
    (both a current and a prior dated artifact), finds codes that are new since
    the prior artifact — present in `curr_artifact`'s measured findings, absent
    from `prev_artifact`'s — for a share of that cohort at or above
    `min_spike_share`, with at least `min_spike_agencies` agencies. Both
    thresholds must hold: the share guards a small cohort where two agencies
    already look like "most of it", and the absolute floor guards a large
    cohort where a low share could still be two agencies coinciding.

    Findings are read via `_regression_codes`, so a code counts only when its
    category was actually measured in both runs (the same rule the fix-receipt
    diff uses, and for the same reason: an unmeasured category must never be
    read as a finding appearing or clearing) and excludes calendar-countdown
    categories that correlate across a cohort for reasons unrelated to the
    producing tool (see `_EXCLUDED_CATEGORIES`).

    Returns regressions most-affected-cohort first, then tool, then code, so a
    worklist reader sees the widest-reaching pattern first.
    """
    out: list[VendorRegression] = []
    for tool_key, (profile, members) in _cohorts(runs).items():
        comparable = [r for r in members if r.prev_artifact is not None]
        if len(comparable) < min_cohort:
            continue
        by_code: dict[str, list[AgencyRun]] = defaultdict(list)
        what_by_code: dict[str, str] = {}
        date = ""
        for run in comparable:
            prev_codes = set(_regression_codes(run.prev_artifact))  # type: ignore[arg-type]
            curr_codes = _regression_codes(run.curr_artifact)
            date = str(run.curr_artifact.get("snapshot_date", "")) or date
            for code in set(curr_codes) - prev_codes:
                by_code[code].append(run)
                what_by_code.setdefault(code, curr_codes[code])
        cohort_size = len(comparable)
        for code, affected in by_code.items():
            share = len(affected) / cohort_size
            if len(affected) < min_spike_agencies or share < min_spike_share:
                continue
            out.append(
                VendorRegression(
                    tool_key=tool_key,
                    tool_name=profile.name,
                    code=code,
                    what=what_by_code[code],
                    date=date,
                    cohort_size=cohort_size,
                    new_agencies=len(affected),
                    affected_ids=tuple(sorted(r.agency_id for r in affected)),
                    affected_names=tuple(sorted(r.agency_name for r in affected)),
                    fix_path=profile.fix_path,
                    request_lede=profile.request_lede,
                )
            )
    out.sort(key=lambda r: (-r.new_agencies, r.tool_key, r.code))
    return out


def render_private_worklist(regressions: list[VendorRegression]) -> str:
    """Markdown per-vendor worklist: which agencies, which code, and the
    forwardable request text (`tool_profiles.request_lede`).

    Internal only. This is the routing artifact for RR:E4 vendor-constructive
    outreach, not something a rider or the public site ever sees, and it must
    never be written to a public path (mirroring `vendors.py`'s operator
    reports).
    """
    lines = ["# Vendor regression worklist (private, internal only)", ""]
    if not regressions:
        lines.append("No same-day vendor-regression pattern detected in this scan.")
        lines.append("")
        return "\n".join(lines)

    lines.append(
        "_Do not publish. Named agencies below are for internal routing to the "
        "producing tool's contact; the public digest for the same scan carries "
        "no agency names._"
    )
    lines.append("")

    by_tool: dict[str, list[VendorRegression]] = defaultdict(list)
    for r in regressions:
        by_tool[r.tool_key].append(r)

    for tool_key in sorted(by_tool, key=lambda k: -sum(r.new_agencies for r in by_tool[k])):
        items = by_tool[tool_key]
        lines.append(f"## {items[0].tool_name}")
        lines.append("")
        lines.append(items[0].request_lede)
        lines.append("")
        for r in items:
            what = (r.what or "no description on record").rstrip(".")
            lines.append(
                f"- **{r.code}** — {what}. New on "
                f"{r.new_agencies} of {r.cohort_size} feeds since the prior check "
                f"(first seen {r.date})."
            )
            lines.append(f"  - Agencies: {', '.join(r.affected_names)}")
        lines.append("")
    return "\n".join(lines)


def load_runs(agency_ids: list[str] | None = None) -> list[AgencyRun]:
    """Build today's `AgencyRun`s from the dated artifacts already on disk.

    For each agency directory under `artifacts_dir()`, reads the two most
    recent dated files (`YYYY-MM-DD.json`): the newest as `curr_artifact`, the
    one before it as `prev_artifact`. An agency with only one dated artifact on
    record gets `prev_artifact=None` and contributes no signal yet. A corrupt or
    unreadable dated file is skipped, mirroring the tolerance `publish.py`'s
    reindex uses at national scale — one bad file must not drop an agency from
    the scan.
    """
    import json

    from .config import AGENCIES, artifacts_dir
    from .publish import RESERVED_ARTIFACT_DIRS

    root = artifacts_dir()
    if not root.exists():
        return []
    wanted = set(agency_ids) if agency_ids is not None else None
    runs: list[AgencyRun] = []
    for agency_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if agency_dir.name in RESERVED_ARTIFACT_DIRS:
            continue
        # An S3-hydrated tree can hold directories for agencies no registry
        # version lists; the radar reads only listed agencies.
        if AGENCIES and agency_dir.name not in AGENCIES:
            continue
        if wanted is not None and agency_dir.name not in wanted:
            continue
        dated = sorted(agency_dir.glob("[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json"))
        artifacts: list[dict[str, Any]] = []
        for path in dated:
            try:
                artifacts.append(json.loads(path.read_text()))
            except (OSError, ValueError):
                continue
        if not artifacts:
            continue
        curr = artifacts[-1]
        prev = artifacts[-2] if len(artifacts) >= 2 else None
        runs.append(
            AgencyRun(
                agency_id=agency_dir.name,
                agency_name=str(curr.get("agency", {}).get("name", agency_dir.name)),
                static_url=curr.get("feed", {}).get("static_url"),
                curr_artifact=curr,
                prev_artifact=prev,
            )
        )
    return runs


def render_public_digest(regressions: list[VendorRegression]) -> str:
    """De-identified aggregate digest: names the tool and the scale, never an
    agency. This is the only form of this radar's output fit for the public
    site or an outward vendor-facing framing; naming a vendor constructively in
    that outward framing is gated on the RR:E4 vendor-interview partnership and
    is not performed here.
    """
    lines = ["# National anomaly digest", ""]
    if not regressions:
        lines.append("No correlated same-day regression was detected across tracked feeds today.")
        lines.append("")
        return "\n".join(lines)

    for r in regressions:
        what = (r.what or f"notice {r.code}").rstrip(".")
        lines.append(
            f"- A **{what}** regression appeared in ~{r.new_agencies} feeds produced by "
            f"{r.tool_name} on {r.date}. No agency is named; the pattern points at the "
            "producing tool, not at any one feed."
        )
    lines.append("")
    lines.append(
        "_This digest is aggregate and de-identified by design: it never names an agency as "
        "failing. It is a constructive, corpus-wide heads-up, not a public ranking._"
    )
    lines.append("")
    return "\n".join(lines)
