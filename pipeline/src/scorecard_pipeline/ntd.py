"""FTA National Transit Database GTFS-readiness assessment.

Since Report Year 2023, every NTD reporter with fixed-route or deviated-fixed-
route service must publish and maintain a public, valid, current GTFS feed and
certify it annually on the D-10 form, and FTA periodically checks that the
published link is viable and current
(https://transit.dot.gov/ntd/recent-ntd-developments-frequently-asked-questions-0).

This turns the scores and feed-identity fields the pipeline already reads into a
plain-language answer to the question a small agency actually faces at
certification time: is my feed in shape to certify? Four pillars mirror the
Report Year 2026 requirement:

- Published: the feed is reachable at a public URL.
- Valid: it has no validator errors that would break a rider's trip.
- Current: the service calendar has not lapsed.
- Identified: agency.txt provides the stable agency_id value that is crosswalked
  to the reporter's NTD ID on the P-50 form.

This is a readiness signal that maps the grade onto the federal requirement, not
an official determination or legal advice. The official assessment is the
agency's own D-10 and P-50 filing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import expiry_status, resolve_service_horizon_status

READY = "ready"
AT_RISK = "at_risk"
NOT_READY = "not_ready"
# A dimension nobody measured for this feed. Deliberately outside the three
# verdicts above, because it is neither a pass nor something the agency can act
# on. Reporting an unmeasured dimension as "at risk" put a "Needs attention"
# badge next to genuine failures and invited a reader to conclude their own feed
# had a defect we had never looked at. An unmeasured pillar therefore carries
# this status, is left out of the overall verdict, and is named in the summary.
NOT_CHECKED = "not_checked"

# Ranks the three verdicts we can actually reach. NOT_CHECKED is absent on
# purpose: membership in this mapping is what "we measured it" means.
_RANK = {READY: 0, AT_RISK: 1, NOT_READY: 2}


@dataclass(frozen=True)
class Pillar:
    key: str  # published | valid | current | agency_id
    status: str  # ready | at_risk | not_ready
    detail: str


@dataclass(frozen=True)
class NtdReadiness:
    status: str  # the worst pillar's status
    pillars: list[Pillar]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the artifact so the web app and public API read a
        precomputed verdict instead of re-deriving it (the frontend stays a thin
        renderer of published JSON)."""
        return {
            "status": self.status,
            "summary": self.summary,
            "pillars": [
                {"key": p.key, "status": p.status, "detail": p.detail} for p in self.pillars
            ],
        }


def _published(artifact: dict[str, Any]) -> Pillar:
    feed = artifact.get("feed", {})
    url = str(feed.get("static_url", ""))
    if feed.get("reachable") is False or not url:
        return Pillar("published", NOT_READY, "The feed could not be retrieved from a public URL.")
    return Pillar("published", READY, "Published at a public URL.")


def _valid(artifact: dict[str, Any]) -> Pillar:
    correctness = artifact.get("categories", {}).get("correctness", {})
    if correctness.get("status") != "measured":
        return Pillar("valid", AT_RISK, "Validation has not run for this feed yet.")
    errors = sum(
        1 for f in correctness.get("findings", []) if str(f.get("severity", "")).upper() == "ERROR"
    )
    if errors:
        plural = "s" if errors != 1 else ""
        return Pillar("valid", AT_RISK, f"{errors} validator error{plural} to resolve.")
    return Pillar("valid", READY, "Passes validation with no errors.")


def _current(artifact: dict[str, Any]) -> Pillar:
    details = artifact.get("categories", {}).get("freshness", {}).get("details", {})
    days = details.get("days_until_expiry")
    status = expiry_status(days)
    if status == "current":
        if (
            resolve_service_horizon_status(details, artifact.get("snapshot_date"))
            == "unusually_distant"
        ):
            return Pillar(
                "current",
                READY,
                "The published window is current, but its service end date is unusually "
                "distant; confirm that date is intentional.",
            )
        return Pillar("current", READY, f"Service data covers the next {days} days.")
    if status == "expiring_soon":
        return Pillar(
            "current", AT_RISK, f"Service data runs out in {days} days; renew before you certify."
        )
    if status in ("lapsed", "stale"):
        return Pillar(
            "current",
            NOT_READY,
            f"Service data expired {-int(days)} days ago, so FTA would find the link out of date.",
        )
    return Pillar(
        "current", NOT_READY, "No service end date could be read, so currency is unknown."
    )


def _identified(artifact: dict[str, Any]) -> Pillar:
    """Whether agency.txt provides an agency_id for the RY2026 P-50 crosswalk.

    The scorecard can establish presence from the feed, but it cannot establish
    from the feed alone that a value stayed stable across reporting years or
    that the reporter entered the crosswalk on P-50. The detail says exactly
    which part was observed and leaves those filing facts to the reporter.
    """
    alignment = artifact.get("ntd_id_alignment")
    if not isinstance(alignment, dict):
        return Pillar(
            "agency_id",
            NOT_CHECKED,
            "agency_id presence has not been checked for this feed yet, so this row "
            "says nothing about your agency_id either way.",
        )
    values = alignment.get("feed_agency_ids")
    ids = [str(value).strip() for value in values] if isinstance(values, list) else []
    ids = [value for value in ids if value]
    if not ids:
        return Pillar(
            "agency_id",
            NOT_READY,
            "agency.txt has no nonblank agency_id. Every RY2026 NTD GTFS submission "
            "needs a stable value unique among the reporters represented in the feed, "
            "crosswalked to each reporter's NTD ID on the P-50 form.",
        )
    return Pillar(
        "agency_id",
        READY,
        "agency.txt provides agency_id. For RY2026, keep one stable value for each NTD "
        "reporter represented in the feed and crosswalk each value on the P-50 form.",
    )


def assess(artifact: dict[str, Any]) -> NtdReadiness:
    """Assess a feed's readiness to certify for the NTD GTFS requirement.

    The overall verdict is the worst *measured* pillar. A pillar we never
    measured is reported as ``not_checked`` and left out of the roll-up, so the
    verdict is never derived from an input nobody looked at, in either
    direction: it cannot manufacture a problem, and it cannot be quietly counted
    as a pass. ``_summary`` names any unmeasured pillar so a "ready" chip never
    implies a check that did not run.
    """
    pillars = [_published(artifact), _valid(artifact), _current(artifact), _identified(artifact)]
    measured = [p for p in pillars if p.status in _RANK]
    status = max(measured, key=lambda p: _RANK[p.status]).status if measured else NOT_CHECKED
    return NtdReadiness(status, pillars, _summary(status, pillars))


def presented_readiness(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """Present current readiness wording from the stored artifact inputs.

    Recomputing lets older artifacts gain the RY2026 agency_id presence pillar
    immediately, without waiting for every feed to be rescored.
    """
    stored = artifact.get("ntd_readiness")
    if not isinstance(stored, dict):
        return None
    return assess(artifact).to_dict()


def _summary(status: str, pillars: list[Pillar]) -> str:
    unchecked = [p.key for p in pillars if p.status == NOT_CHECKED]
    if status == NOT_CHECKED:
        return (
            "None of the RY2026 feed checks have run for this feed yet, so there is no "
            "readiness reading to report. Your own D-10 and P-50 filings are the official check."
        )
    unchecked_note = ""
    if unchecked:
        unchecked_note = (
            f" We have not checked {_join_keys(unchecked)} for this feed, so it is left out "
            "of this reading rather than counted for or against you."
        )
    if status == READY:
        if unchecked:
            held = _join_keys([p.key for p in pillars if p.status == READY])
            return (
                f"Every RY2026 feed check we ran holds here ({held})."
                f"{unchecked_note} Only your own D-10 and P-50 filings make readiness "
                "official; this is a heads-up, not a determination."
            )
        return (
            "Published at a public URL, valid, current, and identified with agency_id: "
            "the four feed checks for RY2026 all hold here. Only your own D-10 and P-50 "
            "filings make that official; this is a heads-up, not a determination."
        )
    problems = " ".join(p.detail for p in pillars if p.status not in (READY, NOT_CHECKED))
    if status == NOT_READY:
        return f"Resolve this before you certify on the D-10. {problems}{unchecked_note}"
    return f"This feed is close to NTD-ready. {problems}{unchecked_note}"


def _join_keys(keys: list[str]) -> str:
    """Join pillar keys for prose, without an Oxford-comma list of one."""
    if len(keys) == 1:
        return keys[0]
    return f"{', '.join(keys[:-1])} and {keys[-1]}"


# NTD ID alignment: a feed's agency_id versus the agency's NTD ID.
ALIGNED = "aligned"
MISMATCH = "mismatch"
MISSING = "missing"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class NtdIdAlignment:
    """Whether a feed's agency_id matches the agency's NTD ID.

    Every RY2026 NTD GTFS submission must provide a stable ``agency_id`` value,
    unique among the reporters represented in the feed, and crosswalk that value
    to the reporter's NTD ID on the P-50 form. The value does not have to equal
    the five-digit NTD ID. Equality is an optional convention that can make joins
    convenient, so the scorecard surfaces it without treating a difference as an
    error or a score deduction.

    ``status`` is one of ``aligned``, ``mismatch``, ``missing``, or ``unknown``.
    The equality comparison is framed neutrally: it carries no score deduction,
    and when we have no NTD ID on file the status is ``unknown`` rather than a
    failure. Missing agency_id is different because presence itself is required.
    """

    status: str
    detail: str
    fix: str  # the concrete action; empty when none is needed or possible
    ntd_id: str  # the NTD ID we checked against; empty when unknown
    feed_agency_ids: list[str]  # distinct agency_id values found in the feed

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status,
            "detail": self.detail,
            "feed_agency_ids": list(self.feed_agency_ids),
        }
        if self.ntd_id:
            out["ntd_id"] = self.ntd_id
        if self.fix:
            out["fix"] = self.fix
        return out


def assess_id_alignment(feed_agency_ids: list[str], ntd_id: str) -> NtdIdAlignment:
    """Check a feed's agency_id against the agency's NTD ID.

    ``feed_agency_ids`` is the agency_id values read from agency.txt (see
    ``gtfs.read_agency_ids``); ``ntd_id`` is the curated NTD ID, empty when we
    do not have one. Presence is checked even when the NTD ID is unknown; the
    optional equality comparison is only possible when both values are present.
    """
    ids = [v.strip() for v in feed_agency_ids if v.strip()]
    ntd = ntd_id.strip()
    if not ids:
        crosswalk_target = f"NTD ID {ntd}" if ntd else "the reporter's NTD ID"
        return NtdIdAlignment(
            MISSING,
            "Your agency.txt sets no nonblank agency_id. Every RY2026 NTD GTFS "
            "submission needs a stable value unique among the reporters represented "
            "in the feed, crosswalked on the P-50 form.",
            "Add agency_id to agency.txt and use the same value wherever routes.txt "
            f"identifies that agency. Keep it stable, and enter its crosswalk to "
            f"{crosswalk_target} on P-50. It does not need to equal the five-digit NTD ID.",
            ntd,
            ids,
        )
    if not ntd:
        return NtdIdAlignment(
            UNKNOWN,
            "This feed provides agency_id. For RY2026, keep one stable value for each "
            "NTD reporter represented in the feed and crosswalk it on the P-50 form. "
            "The value does not need to equal the five-digit NTD ID; we do not have "
            "that ID on file, so the optional equality comparison is not checked yet.",
            "",
            "",
            ids,
        )
    if ntd in ids:
        return NtdIdAlignment(
            ALIGNED,
            f"This feed's agency_id also equals its NTD ID ({ntd}). Equality is "
            "allowed but not required; keep the value stable and retain the P-50 "
            "crosswalk.",
            "",
            ntd,
            ids,
        )
    found = ", ".join(ids)
    return NtdIdAlignment(
        MISMATCH,
        f"Your feed's agency_id is {found}; your National Transit Database ID is "
        f"{ntd}. A feed that serves several agencies (a shared regional feed) can "
        "legitimately carry more than one agency_id. The values do not need to equal "
        "the five-digit NTD ID, so this difference is allowed and carries no score.",
        f"Confirm that P-50 crosswalks agency_id {found} to NTD ID {ntd}, and keep "
        "the feed value stable. Do not change it solely to make the two values equal.",
        ntd,
        ids,
    )


@dataclass(frozen=True)
class ShapesReadiness:
    """Whether a feed's shapes.txt covers its trips, for the NTD shapes requirement.

    FTA's July 2025 final rule requires shapes.txt in the GTFS that NTD reporters
    publish: Full Reporters from Report Year 2025, and Reduced, Rural, and Tribal
    Reporters from Report Year 2026
    (https://www.federalregister.gov/documents/2025/07/10/2025-12813/national-transit-database-reporting-changes-and-clarifications-for-report-years-2025-and-2026).
    FTA estimated only just over a third of reporters already provided it when the
    rule was finalized.

    This checks the feed itself, not the agency's reporter type or reporting
    year, so a "not ready" result is a heads-up to check against your own NTD
    filing, never a claim that your agency is out of compliance today.

    ``status`` is one of ``ready``, ``at_risk``, or ``not_ready`` (the same
    vocabulary as the three certification pillars, so the badge styling matches).
    """

    status: str
    detail: str
    fix: str  # the concrete action; empty when none is needed
    total_trips: int
    trips_with_shape: int

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status,
            "detail": self.detail,
            "total_trips": self.total_trips,
            "trips_with_shape": self.trips_with_shape,
        }
        if self.fix:
            out["fix"] = self.fix
        return out


def assess_shapes_readiness(total_trips: int, trips_with_shape: int) -> ShapesReadiness:
    """Assess shape coverage from a feed's own trip/shape counts.

    Takes the two counts directly (rather than a GTFS zip path) so the check is
    trivial to unit test and to recompute at render time from stored artifact
    fields, the same pattern ``assess_id_alignment`` uses for agency_id.
    """
    if total_trips == 0:
        return ShapesReadiness(
            NOT_READY,
            "trips.txt has no rows, so shape coverage can't be checked.",
            "",
            0,
            0,
        )
    if trips_with_shape == 0:
        return ShapesReadiness(
            NOT_READY,
            "No trips in this feed have a shape_id linked to a row in shapes.txt.",
            "Add shapes.txt with a shape_id for each trip's path, and set trips.shape_id "
            "to match. Reduced, Rural, and Tribal NTD reporters need this in their "
            "published GTFS starting Report Year 2026; Full Reporters needed it in "
            "Report Year 2025.",
            total_trips,
            0,
        )
    if trips_with_shape < total_trips:
        missing = total_trips - trips_with_shape
        return ShapesReadiness(
            AT_RISK,
            f"{trips_with_shape} of {total_trips} trips have a shape; {missing} do not.",
            "Fill in shapes.txt and trips.shape_id for the remaining trips so every trip "
            "has a path. Reduced, Rural, and Tribal NTD reporters need full coverage by "
            "Report Year 2026.",
            total_trips,
            trips_with_shape,
        )
    return ShapesReadiness(
        READY,
        f"All {total_trips} trips have a shape in shapes.txt.",
        "",
        total_trips,
        trips_with_shape,
    )


@dataclass(frozen=True)
class PortfolioSummary:
    """A program-level roll-up of NTD readiness across many agency feeds."""

    total: int
    ready: int
    at_risk: int
    not_ready: int
    pct_ready: float
    by_state: dict[str, dict[str, int]]


def _state_of(artifact: dict[str, Any]) -> str:
    state = str(artifact.get("agency", {}).get("state", "")).strip()
    return state or "Unlocated"


def portfolio_summary(artifacts: list[dict[str, Any]]) -> PortfolioSummary:
    """Roll up NTD readiness across a portfolio of agency feeds.

    A state DOT or Cal-ITP-style program lead supporting many agencies needs
    one number for their next briefing: what share of feeds are ready to
    certify. This runs the same per-feed ``assess`` used on every agency page
    and groups the result, including a per-state breakdown so a liaison can see
    where the gaps sit. State is read from ``agency.state``; feeds without one
    are grouped under "Unlocated" rather than dropped.

    NTD is a US-federal (FTA) requirement, so non-US feeds are excluded from the
    portfolio: ``agency.country`` defaults to "US" (existing artifacts are
    unaffected), and a feed marked otherwise (e.g. "CA") is dropped so it never
    counts toward a "% ready to certify" figure it cannot meet. See ADR 0026.

    A feed with a pillar we never measured is also left out, the same way
    ``shapes_portfolio_summary`` counts only feeds the shapes check ran for. Its
    readiness is unknown, so counting it either way would put an unmeasured feed
    behind a published percentage.
    """
    artifacts = [a for a in artifacts if a.get("agency", {}).get("country", "US") == "US"]
    total = 0
    ready = at_risk = not_ready = 0
    by_state: dict[str, dict[str, int]] = {}
    for artifact in artifacts:
        verdict = assess(artifact)
        if any(p.status == NOT_CHECKED for p in verdict.pillars):
            continue
        total += 1
        status = verdict.status
        state = _state_of(artifact)
        bucket = by_state.setdefault(state, {"ready": 0, "at_risk": 0, "not_ready": 0, "total": 0})
        bucket["total"] += 1
        if status == READY:
            ready += 1
            bucket["ready"] += 1
        elif status == AT_RISK:
            at_risk += 1
            bucket["at_risk"] += 1
        else:
            not_ready += 1
            bucket["not_ready"] += 1
    pct_ready = round(ready / total * 100, 1) if total else 0.0
    return PortfolioSummary(total, ready, at_risk, not_ready, pct_ready, by_state)


def shapes_status(artifact: dict[str, Any]) -> str | None:
    """This feed's current shapes.txt readiness status, or None when the check
    has not run for it (non-US feeds, or artifacts that predate the check).

    Recomputed from the stored trip counts when they are present (the same
    pattern render_site's ``_current_shapes_readiness`` uses), so a threshold or
    wording change reaches every rollup without a rescore. Falls back to the
    stored status for older artifacts that kept only the verdict.
    """
    shapes = artifact.get("shapes_readiness")
    if not shapes:
        return None
    total = shapes.get("total_trips")
    with_shape = shapes.get("trips_with_shape")
    if isinstance(total, int) and isinstance(with_shape, int):
        return assess_shapes_readiness(total, with_shape).status
    stored = str(shapes.get("status", ""))
    return stored if stored in _RANK else None


def shapes_portfolio_summary(artifacts: list[dict[str, Any]]) -> PortfolioSummary:
    """Roll up shapes.txt readiness across a portfolio of agency feeds.

    The FTA shapes.txt requirement phases in by NTD reporter type (Full
    Reporters in Report Year 2025; Reduced, Rural, and Tribal Reporters in
    Report Year 2026), and a state program or a reporter wants the population
    picture: how many tracked feeds already carry a shape for every trip.
    Same shape as ``portfolio_summary`` so the two read identically: US-only
    (the requirement is FTA's; see ADR 0026), counted only where the check ran,
    grouped by state with unlocated feeds kept rather than dropped.
    """
    counted = [
        (status, _state_of(artifact))
        for artifact in artifacts
        if artifact.get("agency", {}).get("country", "US") == "US"
        and (status := shapes_status(artifact)) is not None
    ]
    total = len(counted)
    ready = at_risk = not_ready = 0
    by_state: dict[str, dict[str, int]] = {}
    for status, state in counted:
        bucket = by_state.setdefault(state, {"ready": 0, "at_risk": 0, "not_ready": 0, "total": 0})
        bucket["total"] += 1
        if status == READY:
            ready += 1
            bucket["ready"] += 1
        elif status == AT_RISK:
            at_risk += 1
            bucket["at_risk"] += 1
        else:
            not_ready += 1
            bucket["not_ready"] += 1
    pct_ready = round(ready / total * 100, 1) if total else 0.0
    return PortfolioSummary(total, ready, at_risk, not_ready, pct_ready, by_state)


def one_fix_from_ready(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Feeds where a single fix would make the feed look ready to certify.

    Report year 2026 adds the agency_id requirement to NTD GTFS submissions, and
    for a liaison triaging a portfolio the highest-leverage list is the feeds
    exactly one pillar short of ready. Each row carries that
    pillar's plain-language detail as the fix to forward to the agency. Worst
    status first, then by name, so the near-misses that would otherwise read
    "not ready" surface at the top.
    """
    rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        if artifact.get("agency", {}).get("country", "US") != "US":
            continue
        verdict = assess(artifact)
        if any(p.status == NOT_CHECKED for p in verdict.pillars):
            # An unmeasured pillar can be ruled neither in nor out, so this feed
            # is not knowably one fix from ready and must not be forwarded as if
            # it were.
            continue
        failing = [p for p in verdict.pillars if p.status != READY]
        if len(failing) != 1:
            continue
        pillar = failing[0]
        agency = artifact.get("agency", {})
        agency_id = str(agency.get("id", ""))
        rows.append(
            {
                "id": agency_id,
                "name": str(agency.get("name") or agency_id),
                "state": _state_of(artifact),
                "pillar": pillar.key,
                "fix": pillar.detail,
                "status": verdict.status,
            }
        )
    rows.sort(key=lambda r: (-_RANK.get(str(r["status"]), 0), str(r["name"]).lower()))
    return rows


def render_portfolio(summary: PortfolioSummary) -> str:
    """Render a portfolio readiness summary as markdown for a program lead."""
    if summary.total == 0:
        return "# NTD readiness across your portfolio\n\nNo agency feeds were assessed yet."
    lines = [
        "# NTD readiness across your portfolio",
        "",
        f"**{summary.pct_ready}% of {summary.total} feeds are ready to certify.**",
        "",
        f"- Ready: {summary.ready}",
        f"- At risk: {summary.at_risk}",
        f"- Not ready: {summary.not_ready}",
        "",
        "## By state",
        "",
        "| State | Ready | At risk | Not ready | Total |",
        "| --- | --- | --- | --- | --- |",
    ]
    for state in sorted(summary.by_state):
        counts = summary.by_state[state]
        lines.append(
            f"| {state} | {counts['ready']} | {counts['at_risk']} "
            f"| {counts['not_ready']} | {counts['total']} |"
        )
    lines.append("")
    lines.append(
        "Readiness mirrors the published, valid, current, and agency_id pillars. "
        "The official check is each agency's own D-10 and P-50 filing."
    )
    return "\n".join(lines)
