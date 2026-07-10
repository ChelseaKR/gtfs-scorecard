"""Build bounded, fix-framed support campaigns for an agency cohort."""

from __future__ import annotations

import datetime as dt
from typing import Any

CAMPAIGN_SCHEMA_VERSION = "1.0"

CAMPAIGNS: dict[str, dict[str, Any]] = {
    "calendar-renewal": {
        "name": "Calendar renewal",
        "goal": "Every targeted feed publishes at least 30 days of service ahead.",
        "codes": {
            "scorecard_feed_expired",
            "scorecard_feed_expiring_soon",
            "expired_calendar",
            "feed_expiration_date7_days",
            "feed_expiration_date30_days",
        },
    },
    "accessibility-fields": {
        "name": "Accessibility fields",
        "goal": "Every targeted feed publishes known wheelchair values for stops and trips.",
        "codes": {
            "scorecard_wheelchair_boarding_unknown",
            "scorecard_wheelchair_accessible_unknown",
        },
    },
    "rider-information": {
        "name": "Rider information",
        "goal": "Every targeted feed publishes the rider-facing names and destinations it needs.",
        "codes": {
            "missing_trip_headsign",
            "missing_route_long_name",
            "mixed_case_recommended_field",
        },
    },
}


def _matching_findings(artifact: dict[str, Any], codes: set[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for category in artifact.get("categories", {}).values():
        if category.get("status") != "measured":
            continue
        findings.extend(f for f in category.get("findings", []) if f.get("code") in codes)
    return findings


def build_program_campaign(
    *,
    rollup_id: str,
    rollup_name: str,
    kind: str,
    artifacts: list[dict[str, Any]],
    as_of: dt.date,
) -> dict[str, Any]:
    """Build an agency worklist and explicit success measure for one campaign.

    Worklists omit grade and score. A campaign is about clearing one bounded
    condition across a cohort, not comparing agencies with one another.
    """
    if kind not in CAMPAIGNS:
        raise ValueError(f"unknown campaign kind: {kind}")
    definition = CAMPAIGNS[kind]
    codes = definition["codes"]
    targets: list[dict[str, Any]] = []
    for artifact in artifacts:
        matches = _matching_findings(artifact, codes)
        if kind == "calendar-renewal":
            days = (
                artifact.get("categories", {})
                .get("freshness", {})
                .get("details", {})
                .get("days_until_expiry")
            )
            if isinstance(days, (int, float)) and not isinstance(days, bool) and days <= 30:
                matches = matches or [
                    {
                        "code": "calendar_coverage_below_30_days",
                        "what": f"The feed has {int(days)} days of service ahead.",
                        "fix": "Republish with at least 30 days of service ahead.",
                        "count": 1,
                    }
                ]
        if not matches:
            continue
        agency = artifact.get("agency", {})
        agency_id = str(agency.get("id", ""))
        targets.append(
            {
                "agency_id": agency_id,
                "agency_name": str(agency.get("name", agency_id)),
                "scorecard_url": f"https://gtfsscorecard.org/agency/{agency_id}/",
                "snapshot_date": artifact.get("snapshot_date"),
                "findings": [
                    {
                        "code": str(finding.get("code", "")),
                        "instances": int(finding.get("count", 0)),
                        "observed": str(finding.get("what", "")),
                        "fix": str(finding.get("fix", "")),
                    }
                    for finding in matches
                ],
            }
        )
    targets.sort(key=lambda target: (target["agency_name"].casefold(), target["agency_id"]))
    total = len(artifacts)
    target_count = len(targets)
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign": {"kind": kind, "name": definition["name"], "goal": definition["goal"]},
        "rollup": {"id": rollup_id, "name": rollup_name},
        "baseline": {
            "as_of": as_of.isoformat(),
            "agencies_checked": total,
            "agencies_targeted": target_count,
            "agencies_already_clear": total - target_count,
        },
        "success_measure": {
            "target": "0 agencies remaining with a campaign finding",
            "retest": (
                "Rebuild this campaign after feeds republish; a target leaves only after a "
                "measured run clears every campaign finding."
            ),
        },
        "targets": targets,
        "fairness_note": (
            "This is a support worklist, not an agency ranking. It omits grades and scores and "
            "covers one fix theme at a time."
        ),
    }


def render_program_campaign_markdown(campaign: dict[str, Any]) -> str:
    """Render a call-ready campaign plan for a program liaison."""
    meta = campaign["campaign"]
    baseline = campaign["baseline"]
    lines = [
        f"# {meta['name']} campaign: {campaign['rollup']['name']}",
        "",
        f"**Goal:** {meta['goal']}",
        "",
        f"Baseline ({baseline['as_of']}): {baseline['agencies_targeted']} of "
        f"{baseline['agencies_checked']} agencies need this fix; "
        f"{baseline['agencies_already_clear']} are already clear.",
        "",
        "## Agency worklist",
        "",
    ]
    if not campaign["targets"]:
        lines.extend(["No agency currently needs this campaign fix.", ""])
    for target in campaign["targets"]:
        lines.extend([f"### {target['agency_name']}", "", target["scorecard_url"], ""])
        for finding in target["findings"]:
            lines.append(f"- `{finding['code']}`: {finding['observed']} **Fix:** {finding['fix']}")
        lines.append("")
    lines.extend(
        [
            "## Closeout",
            "",
            f"- [ ] {campaign['success_measure']['target']}",
            f"- [ ] {campaign['success_measure']['retest']}",
            "",
            f"_{campaign['fairness_note']}_",
            "",
        ]
    )
    return "\n".join(lines)
