"""Build a reproducible, agency-scoped vendor remediation packet.

The packet turns a scorecard artifact into a constructive acceptance record:
what was observed, the exact feed bytes and tool versions behind the result,
what to change, and what a clean retest means. It deliberately contains no
cross-agency vendor ranking or inferred vendor identity.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .comparisons import producer_contract

PACKET_SCHEMA_VERSION = "1.1"


def _packet_id(artifact: dict[str, Any]) -> str:
    agency = artifact.get("agency", {})
    feed = artifact.get("feed", {})
    rubric, scoring_profile, profile_rubric, validator, reader_profile, measured = (
        producer_contract(artifact)
    )
    identity = "|".join(
        [
            str(agency.get("id", "")),
            str(artifact.get("snapshot_date", "")),
            str(feed.get("sha256", "")),
            rubric,
            scoring_profile,
            profile_rubric,
            validator,
            reader_profile,
            ",".join(measured),
        ]
    )
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


def _finding_category(
    artifact: dict[str, Any], fix: dict[str, Any], measured_categories: tuple[str, ...]
) -> str:
    """Resolve a top fix to the measured category that produced it."""
    explicit = str(fix.get("category") or "")
    if explicit in measured_categories:
        return explicit

    categories = artifact.get("categories") or {}
    if not isinstance(categories, dict):
        return ""
    code = str(fix.get("code") or "")
    for category in measured_categories:
        result = categories.get(category)
        if not isinstance(result, dict):
            continue
        findings = result.get("findings") or []
        if isinstance(findings, list) and any(
            isinstance(finding, dict) and str(finding.get("code") or "") == code
            for finding in findings
        ):
            return category
    return ""


def _acceptance_contract(
    acceptance_test: dict[str, Any],
) -> tuple[str, str, str, str, str, tuple[str, ...]] | None:
    measured = acceptance_test.get("measured_categories")
    if not isinstance(measured, list) or not all(isinstance(value, str) for value in measured):
        return None
    contract = (
        str(acceptance_test.get("rubric_version") or ""),
        str(acceptance_test.get("scoring_profile_id") or ""),
        str(acceptance_test.get("scoring_profile_rubric_version") or ""),
        str(acceptance_test.get("validator_version") or ""),
        str(acceptance_test.get("reader_archive_profile") or ""),
        tuple(measured),
    )
    if not all(contract[:5]) or not contract[5]:
        return None
    return contract


def _notice_instances(category_result: Any, notice_code: str) -> int | None:
    if not isinstance(category_result, dict) or category_result.get("status") != "measured":
        return None
    findings = category_result.get("findings")
    if not isinstance(findings, list):
        return None
    total = 0
    for finding in findings:
        if not isinstance(finding, dict) or str(finding.get("code") or "") != notice_code:
            continue
        count = finding.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return None
        total += count
    return total


def acceptance_test_passes(
    acceptance_test: dict[str, Any], candidate_artifact: dict[str, Any]
) -> bool:
    """Return whether a candidate satisfies a packet acceptance test.

    Acceptance is fail-closed: the complete producer contract must match, the
    source category must still be measured, and the notice count must equal the
    packet's expectation. Removing a category from measurement therefore cannot
    make its findings look resolved.
    """
    expected_contract = _acceptance_contract(acceptance_test)
    if expected_contract is None:
        return False
    if producer_contract(candidate_artifact) != expected_contract:
        return False

    category = str(acceptance_test.get("category") or "")
    if (
        not category
        or category not in expected_contract[5]
        or acceptance_test.get("required_category_status") != "measured"
    ):
        return False
    expected_instances = acceptance_test.get("expected_instances")
    if (
        not isinstance(expected_instances, int)
        or isinstance(expected_instances, bool)
        or expected_instances < 0
    ):
        return False
    notice_code = str(acceptance_test.get("notice_code") or "")
    if not notice_code:
        return False
    categories = candidate_artifact.get("categories") or {}
    if not isinstance(categories, dict):
        return False
    actual_instances = _notice_instances(categories.get(category), notice_code)
    return actual_instances == expected_instances


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
    rubric, scoring_profile, profile_rubric, validator, reader_profile, measured = (
        producer_contract(artifact)
    )

    work_items: list[dict[str, Any]] = []
    for fix in fixes:
        code = str(fix.get("code", ""))
        category = _finding_category(artifact, fix, measured)
        category_label = f"the {category} category" if category else "the source category"
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
                    "category": category,
                    "required_category_status": "measured",
                    "rubric_version": rubric,
                    "scoring_profile_id": scoring_profile,
                    "scoring_profile_rubric_version": profile_rubric,
                    "validator_version": validator,
                    "reader_archive_profile": reader_profile,
                    "measured_categories": list(measured),
                    "method": (
                        "Republish the feed and rerun the same rubric, scoring profile, "
                        "validator, reader archive profile, and measured-category set. "
                        f"Confirm {category_label} remains measured and this notice is absent."
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
            "validator_version": validator,
            "rubric_version": rubric,
            "scoring_profile_id": scoring_profile,
            "scoring_profile_rubric_version": profile_rubric,
            "reader_archive_profile": reader_profile,
            "measured_categories": list(measured),
            "artifact_schema_version": artifact.get("schema_version"),
        },
        "work_items": work_items,
        "completion": {
            "required": [
                "Publish corrected GTFS at the agency's canonical feed URL.",
                "Provide the new feed SHA-256 and publication date.",
                "Rerun the scorecard with the baseline rubric, scoring profile, validator, "
                "reader archive profile, and measured category set.",
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
        f"- Scoring profile: {baseline.get('scoring_profile_id') or 'not recorded'} "
        f"(rubric {baseline.get('scoring_profile_rubric_version') or 'not recorded'})",
        f"- Reader archive profile: {baseline.get('reader_archive_profile') or 'not recorded'}",
        f"- Measured categories: "
        f"{', '.join(baseline.get('measured_categories') or []) or 'not recorded'}",
        "",
        "## Requested work and acceptance tests",
        "",
    ]
    if not packet["work_items"]:
        lines.extend(["No remediation item is requested from this baseline.", ""])
    for item in packet["work_items"]:
        acceptance = item["acceptance_test"]
        category = acceptance.get("category") or "source category"
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
                "**Acceptance:** rerun under the baseline producer contract, confirm "
                f"`{category}` remains measured, and confirm `{item['notice_code']}` has "
                f"{acceptance['expected_instances']} instances.",
                "",
            ]
        )
    lines.extend(["## Completion evidence", ""])
    lines.extend(f"- [ ] {requirement}" for requirement in packet["completion"]["required"])
    lines.extend(["", f"_{packet['completion']['note']}_", ""])
    return "\n".join(lines)
