"""Build a reproducible, agency-scoped vendor remediation packet.

The packet turns a scorecard artifact into a constructive acceptance record:
what was observed, the exact feed bytes and tool versions behind the result,
what to change, and what a clean retest means. It deliberately contains no
cross-agency vendor ranking or inferred vendor identity.
"""

from __future__ import annotations

import hashlib
from typing import Any

PACKET_SCHEMA_VERSION = "1.0"


def _packet_id(artifact: dict[str, Any]) -> str:
    agency = artifact.get("agency", {})
    feed = artifact.get("feed", {})
    identity = "|".join(
        [
            str(agency.get("id", "")),
            str(artifact.get("snapshot_date", "")),
            str(feed.get("sha256", "")),
            str(artifact.get("rubric_version", "")),
            str(artifact.get("validator_version", "")),
        ]
    )
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


def build_evidence_packet(
    artifact: dict[str, Any],
    *,
    scorecard_url: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic vendor remediation packet for one artifact.

    The packet repeats the artifact's snapshot and generated timestamps rather
    than using the wall clock, so rerunning it over the same evidence produces
    byte-equivalent JSON after canonical serialization.
    """
    agency = artifact.get("agency", {})
    feed = artifact.get("feed", {})
    overall = artifact.get("overall", {})
    fixes = artifact.get("top_fixes") or []
    agency_id = str(agency.get("id", ""))
    canonical = scorecard_url or f"https://gtfsscorecard.org/agency/{agency_id}/"

    work_items: list[dict[str, Any]] = []
    for fix in fixes:
        code = str(fix.get("code", ""))
        work_items.append(
            {
                "priority": int(fix.get("rank", len(work_items) + 1)),
                "notice_code": code,
                "current_instances": int(fix.get("count", 0)),
                "severity": str(fix.get("severity", "INFO")),
                "observed": str(fix.get("what", "")),
                "rider_or_operational_impact": str(fix.get("why", "")),
                "requested_change": str(fix.get("fix", "")),
                "effort_hint": str(fix.get("effort", "")),
                "likely_owner": str(fix.get("owner", "Unassigned")),
                "acceptance_test": {
                    "notice_code": code,
                    "expected_instances": 0,
                    "method": (
                        "Republish the feed, rerun the same validator and rubric, "
                        "and confirm this notice is absent."
                    ),
                },
            }
        )

    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": _packet_id(artifact),
        "status": "open" if work_items else "no_action_requested",
        "agency": {"id": agency_id, "name": str(agency.get("name", agency_id))},
        "scorecard_url": canonical,
        "baseline": {
            "snapshot_date": artifact.get("snapshot_date"),
            "generated_at": artifact.get("generated_at"),
            "grade": overall.get("grade"),
            "score": overall.get("score"),
            "feed_url": feed.get("static_url"),
            "feed_sha256": feed.get("sha256"),
            "validator_version": artifact.get("validator_version"),
            "rubric_version": artifact.get("rubric_version"),
            "artifact_schema_version": artifact.get("schema_version"),
        },
        "work_items": work_items,
        "completion": {
            "required": [
                "Publish corrected GTFS at the agency's canonical feed URL.",
                "Provide the new feed SHA-256 and publication date.",
                "Rerun the scorecard with the baseline validator and rubric versions.",
                "Confirm every acceptance test above passes or document an agreed exception.",
            ],
            "note": (
                "This packet describes one agency's published feed. It is not a vendor ranking, "
                "contract determination, or claim about who caused a finding."
            ),
        },
    }


def render_evidence_packet_markdown(packet: dict[str, Any]) -> str:
    """Render a packet as forwardable Markdown without losing evidence IDs."""
    agency = packet["agency"]
    baseline = packet["baseline"]
    lines = [
        f"# GTFS remediation packet: {agency['name']}",
        "",
        f"Packet ID: `{packet['packet_id']}`  ",
        f"Baseline: {baseline.get('snapshot_date') or 'unknown date'} · "
        f"grade {baseline.get('grade') or '—'} ({baseline.get('score') or '—'} / 100)  ",
        f"Scorecard: {packet['scorecard_url']}",
        "",
        "## Evidence baseline",
        "",
        f"- Feed URL: {baseline.get('feed_url') or 'not recorded'}",
        f"- Feed SHA-256: `{baseline.get('feed_sha256') or 'not recorded'}`",
        f"- Validator: {baseline.get('validator_version') or 'not recorded'}",
        f"- Rubric: {baseline.get('rubric_version') or 'not recorded'}",
        "",
        "## Requested work and acceptance tests",
        "",
    ]
    if not packet["work_items"]:
        lines.extend(["No remediation item is requested from this baseline.", ""])
    for item in packet["work_items"]:
        lines.extend(
            [
                f"### {item['priority']}. {item['notice_code']}",
                "",
                f"**Observed:** {item['observed']} ({item['current_instances']} instances)",
                "",
                f"**Why it matters:** {item['rider_or_operational_impact']}",
                "",
                f"**Requested change:** {item['requested_change']}",
                "",
                f"**Effort hint:** {item['effort_hint']}",
                "",
                f"**Acceptance:** rerun and confirm `{item['notice_code']}` has 0 instances.",
                "",
            ]
        )
    lines.extend(["## Completion evidence", ""])
    lines.extend(f"- [ ] {requirement}" for requirement in packet["completion"]["required"])
    lines.extend(["", f"_{packet['completion']['note']}_", ""])
    return "\n".join(lines)
