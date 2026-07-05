"""FTA National Transit Database GTFS-readiness assessment.

Since Report Year 2023, every NTD reporter with fixed-route or deviated-fixed-
route service must publish and maintain a public, valid, current GTFS feed and
certify it annually on the D-10 form, and FTA periodically checks that the
published link is viable and current
(https://transit.dot.gov/ntd/recent-ntd-developments-frequently-asked-questions-0).

This turns the scores the pipeline already computes into a plain-language answer
to the question a small agency actually faces at certification time: is my feed
in shape to certify? Three pillars mirror the requirement:

- Published: the feed is reachable at a public URL.
- Valid: it has no validator errors that would break a rider's trip.
- Current: the service calendar has not lapsed.

This is a readiness signal that maps the grade onto the federal requirement, not
an official determination or legal advice. The official assessment is the
agency's own D-10 certification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import expiry_status

READY = "ready"
AT_RISK = "at_risk"
NOT_READY = "not_ready"

_RANK = {READY: 0, AT_RISK: 1, NOT_READY: 2}


@dataclass(frozen=True)
class Pillar:
    key: str  # published | valid | current
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
    days = (
        artifact.get("categories", {})
        .get("freshness", {})
        .get("details", {})
        .get("days_until_expiry")
    )
    status = expiry_status(days)
    if status == "current":
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


def assess(artifact: dict[str, Any]) -> NtdReadiness:
    """Assess a feed's readiness to certify for the NTD GTFS requirement."""
    pillars = [_published(artifact), _valid(artifact), _current(artifact)]
    status = max(pillars, key=lambda p: _RANK[p.status]).status
    return NtdReadiness(status, pillars, _summary(status, pillars))


def _summary(status: str, pillars: list[Pillar]) -> str:
    if status == READY:
        return (
            "Published at a public URL, valid, and current: the three things the NTD "
            "GTFS requirement asks of a feed all hold here. Only your own D-10 "
            "certification makes that official; this is a heads-up, not a determination."
        )
    problems = " ".join(p.detail for p in pillars if p.status != READY)
    if status == NOT_READY:
        return f"Resolve this before you certify on the D-10. {problems}"
    return f"This feed is close to NTD-ready. {problems}"


# NTD ID alignment: a feed's agency_id versus the agency's NTD ID.
ALIGNED = "aligned"
MISMATCH = "mismatch"
MISSING = "missing"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class NtdIdAlignment:
    """Whether a feed's agency_id matches the agency's NTD ID.

    Setting GTFS ``agency_id`` to the agency's five-digit NTD ID lets a feed
    join cleanly to its National Transit Database record. The October 2024
    proposed rule would have required that alignment in the feed; the July 2025
    final rule did not adopt it, after most commenters opposed a mandated
    feed-side change, and instead links agency_id to the NTD ID on the agency's
    P-50 form. So this is an optional convenience the scorecard surfaces, never
    a federal requirement the agency has to meet in its GTFS.

    ``status`` is one of ``aligned``, ``mismatch``, ``missing``, or ``unknown``.
    It is framed as an optional improvement, not a penalty: it carries no score
    deduction, and when we have no NTD ID on file the status is ``unknown``
    rather than a failure.
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
    do not have one. The requirement and its phase-in are documented on
    ``NtdIdAlignment``.
    """
    ids = [v.strip() for v in feed_agency_ids if v.strip()]
    ntd = ntd_id.strip()
    if not ntd:
        return NtdIdAlignment(
            UNKNOWN,
            "Setting your GTFS agency_id to your five-digit NTD ID is an optional "
            "way to line a feed up with its National Transit Database record. FTA "
            "links the two on your P-50 form, so it is not a required feed change. "
            "We don't have your NTD ID on file, so this is not checked yet.",
            "",
            "",
            ids,
        )
    if ntd in ids:
        return NtdIdAlignment(
            ALIGNED,
            f"Your agency_id is set to your NTD ID ({ntd}), so this feed lines up "
            "with your National Transit Database record.",
            "",
            ntd,
            ids,
        )
    if not ids:
        return NtdIdAlignment(
            MISSING,
            "Your agency.txt sets no agency_id, so this feed can't be lined up "
            f"automatically with your National Transit Database record (NTD ID {ntd}).",
            f"Optionally set agency_id to {ntd} in agency.txt (and the matching "
            "agency_id in routes.txt) so the feed lines up with your NTD record. "
            "It is a convenience, not a required feed change: FTA also links the "
            "two on your P-50 form.",
            ntd,
            ids,
        )
    found = ", ".join(ids)
    return NtdIdAlignment(
        MISMATCH,
        f"Your feed's agency_id is {found}; your National Transit Database ID is "
        f"{ntd}. A feed that serves several agencies (a shared regional feed) can "
        "legitimately carry more than one agency_id, so a difference here is a "
        "heads-up, not an error.",
        f"Optionally set the agency_id for your service to {ntd} in agency.txt (and "
        "the matching agency_id in routes.txt) so the feed lines up with your NTD "
        "record. It is a convenience, not a required feed change: FTA also links "
        "agency_id to your NTD ID on your P-50 form.",
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
    """
    artifacts = [a for a in artifacts if a.get("agency", {}).get("country", "US") == "US"]
    total = len(artifacts)
    ready = at_risk = not_ready = 0
    by_state: dict[str, dict[str, int]] = {}
    for artifact in artifacts:
        status = assess(artifact).status
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


def one_fix_from_ready(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Feeds where a single fix would make the feed look ready to certify.

    Report year 2026 brings reduced, rural, and tribal reporters into the NTD
    GTFS requirement, and for a liaison triaging a portfolio the highest-leverage
    list is the feeds exactly one pillar short of ready. Each row carries that
    pillar's plain-language detail as the fix to forward to the agency. Worst
    status first, then by name, so the near-misses that would otherwise read
    "not ready" surface at the top.
    """
    rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        verdict = assess(artifact)
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
        "Readiness mirrors the published, valid, and current pillars. "
        "The official check is each agency's own D-10 certification."
    )
    return "\n".join(lines)
