"""The finding-clearance log: dated records of comparable feed-state changes.

The agency page shows when a finding is no longer reported by the next
compatible check, but that line is gone the next day. A manager assembling a
board packet or an NTD narrative may need the durable version: finding X was
present through date A and absent from the compatible check on date B, at a URL
they can cite. That record establishes feed state, not who changed it or why.

Receipts are computed in the collect step while ``rebuild_index`` is already
walking every dated artifact in date order, then written per agency as
``fixlog.json`` next to the badge. New receipts carry the complete producer
contract that was checked when the transition was observed, so they can outlive
pruned dated artifacts without turning a methodology change into a claimed
clearance.
Legacy receipts without that evidence survive only when both dated artifacts
are still available and reproduce the receipt; otherwise they fail closed.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .comparisons import producer_contract, same_producer_contract


def _producer_contract_evidence(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """Serializable evidence for the exact producer contract of ``artifact``."""
    rubric, profile, profile_rubric, validator, reader_profile, measured = producer_contract(
        artifact
    )
    if not all((rubric, profile, profile_rubric, validator, reader_profile)) or not measured:
        return None
    return {
        "rubric_version": rubric,
        "scoring_profile_id": profile,
        "scoring_profile_rubric_version": profile_rubric,
        "validator_version": validator,
        "reader_archive_profile": reader_profile,
        "measured_categories": list(measured),
    }


def _evidence_record(evidence: Any) -> dict[str, Any] | None:
    """Convert persisted evidence to the record shape comparison helpers use."""
    if not isinstance(evidence, dict):
        return None
    measured = evidence.get("measured_categories")
    if (
        not isinstance(measured, list)
        or not measured
        or not all(isinstance(category, str) and category for category in measured)
    ):
        return None
    record = {
        "rubric_version": evidence.get("rubric_version"),
        "scoring_profile_id": evidence.get("scoring_profile_id"),
        "scoring_profile_rubric_version": evidence.get("scoring_profile_rubric_version"),
        "validator_version": evidence.get("validator_version"),
        "reader_archive_profile": evidence.get("reader_archive_profile"),
        "categories": {category: {"status": "measured"} for category in measured},
    }
    return record if same_producer_contract(record, record) else None


def _receipt_identity(receipt: dict[str, Any]) -> tuple[str, str, str] | None:
    """Validated ``(code, last_seen, cleared)`` identity for one receipt."""
    code = receipt.get("code")
    last_seen = receipt.get("last_seen")
    cleared = receipt.get("cleared")
    if not isinstance(code, str) or not code:
        return None
    if not isinstance(last_seen, str) or not last_seen:
        return None
    if not isinstance(cleared, str) or not cleared:
        return None
    try:
        before_date = dt.date.fromisoformat(last_seen)
        cleared_date = dt.date.fromisoformat(cleared)
    except ValueError:
        return None
    if before_date >= cleared_date:
        return None
    return code, last_seen, cleared


def finding_codes(artifact: dict[str, Any]) -> dict[str, str]:
    """Map each finding code in an artifact to its 'what' text, across measured
    categories only, mirroring the agency page's finding-clearance diff so a
    receipt never claims absence in a category that simply went unmeasured."""
    return {code: what for code, (_cat, what) in _codes_with_category(artifact).items()}


def _codes_with_category(artifact: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Each measured finding code mapped to (category key, 'what' text)."""
    out: dict[str, tuple[str, str]] = {}
    for key, cat in artifact.get("categories", {}).items():
        if cat.get("status") == "measured":
            for f in cat.get("findings", []):
                code = f.get("code")
                if code:
                    out.setdefault(str(code), (str(key), str(f.get("what", ""))))
    return out


def _measured_keys(artifact: dict[str, Any]) -> set[str]:
    return {
        key
        for key, cat in artifact.get("categories", {}).items()
        if cat.get("status") == "measured"
    }


def diff_receipts(
    prev: dict[str, Any] | None,
    cur: dict[str, Any],
) -> list[dict[str, Any]]:
    """Receipts for findings present in ``prev`` and absent from comparable ``cur``.

    A receipt is minted only when the finding's category was actually measured
    in the current run under the same complete producer contract. A category
    that went unmeasured (a failed fetch or realtime outage) makes its findings
    invisible, and invisibility is not clearance. The receipt makes no causal
    claim about who changed the feed or why.

    Each receipt records the last date the finding was seen, the date of the
    compatible check that no longer reported it, the code, and the previous run's plain-language
    description (the wording the receipt's reader saw while it was open).
    """
    if not prev or not same_producer_contract(prev, cur):
        return []
    evidence = _producer_contract_evidence(cur)
    if evidence is None:
        return []
    current = finding_codes(cur)
    measured_now = _measured_keys(cur)
    last_seen = str(prev.get("snapshot_date", ""))
    verified = str(cur.get("snapshot_date", ""))
    return [
        {
            "code": code,
            "what": what,
            "last_seen": last_seen,
            "cleared": verified,
            "producer_contract": evidence,
        }
        for code, (cat_key, what) in _codes_with_category(prev).items()
        if code not in current and cat_key in measured_now
    ]


def merge_receipts(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Union of receipts, keyed by (cleared date, code), oldest first.

    A finding can clear, come back, and clear again; those are distinct
    receipts. Re-running collect over the same dated files must not duplicate
    anything, and receipts already in the file survive even when the dated
    artifacts they came from are gone.
    """
    seen: dict[tuple[str, str], dict[str, Any]] = {
        (r.get("cleared", ""), r.get("code", "")): r for r in existing
    }
    for r in new:
        key = (r.get("cleared", ""), r.get("code", ""))
        prior = seen.get(key)
        # Prefer a provenance-bearing receipt over a legacy copy of the same
        # transition so the next reconciliation can survive artifact pruning.
        if prior is None or (
            _evidence_record(prior.get("producer_contract")) is None
            and _evidence_record(r.get("producer_contract")) is not None
        ):
            seen[key] = r
    return sorted(seen.values(), key=lambda r: (r.get("cleared", ""), r.get("code", "")))


def reconcile_receipts(
    existing: list[dict[str, Any]],
    artifacts_by_date: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate durable receipts against contract evidence or dated artifacts.

    A legacy receipt has no embedded producer contract. It is upgraded only when
    both its ``last_seen`` and ``cleared`` artifacts are available, use the same
    complete producer contract, and reproduce the claimed finding transition.
    If those artifacts are gone, the receipt is unverifiable and is dropped.

    A provenance-bearing receipt may outlive its dated artifacts. Whenever one
    or both artifacts are available, their contract must still match the stored
    evidence; when both are available the transition itself is re-derived.
    """
    reconciled: list[dict[str, Any]] = []
    for receipt in existing:
        identity = _receipt_identity(receipt)
        if identity is None:
            continue
        code, last_seen, cleared = identity
        before = artifacts_by_date.get(last_seen)
        after = artifacts_by_date.get(cleared)
        evidence_record = _evidence_record(receipt.get("producer_contract"))

        if before is not None and after is not None:
            if not same_producer_contract(before, after):
                continue
            candidate = next(
                (
                    item
                    for item in diff_receipts(before, after)
                    if item.get("code") == code
                    and item.get("last_seen") == last_seen
                    and item.get("cleared") == cleared
                ),
                None,
            )
            if candidate is None:
                continue
            if evidence_record is not None and not same_producer_contract(evidence_record, after):
                continue
            # Re-derived text and evidence are the authoritative version. This
            # also upgrades a valid legacy receipt in place.
            reconciled.append(candidate)
            continue

        # Missing dated evidence is acceptable only for a receipt that already
        # persisted a complete producer contract when it was minted.
        if evidence_record is None:
            continue
        available = before or after
        if available is not None and not same_producer_contract(evidence_record, available):
            continue
        reconciled.append(receipt)

    return merge_receipts([], reconciled)


def load_fixlog_candidates(agency_dir: Path) -> list[dict[str, Any]]:
    """Unreconciled receipt candidates, for ``rebuild_index`` only.

    Callers that publish or render receipts must use :func:`load_fixlog`, which
    validates these candidates against producer-contract evidence.
    """
    try:
        data = json.loads((agency_dir / "fixlog.json").read_text())
    except (FileNotFoundError, ValueError, OSError):
        return []
    receipts = data.get("receipts", []) if isinstance(data, dict) else []
    return [r for r in receipts if isinstance(r, dict)]


def _available_artifacts(agency_dir: Path) -> dict[str, dict[str, Any]]:
    """Identity-checked dated evidence available to a standalone reader."""
    artifacts: dict[str, dict[str, Any]] = {}
    paths = sorted(agency_dir.glob("[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json"))
    latest = agency_dir / "latest.json"
    if latest.exists():
        paths.append(latest)
    for path in paths:
        try:
            artifact = json.loads(path.read_text())
            date = str(artifact["snapshot_date"])
            parsed_date = dt.date.fromisoformat(date)
            agency_id = str(artifact["agency"]["id"])
        except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError, TypeError, ValueError):
            continue
        if parsed_date.isoformat() != date or agency_id != agency_dir.name:
            continue
        if path.name != "latest.json" and path.stem != date:
            continue
        artifacts[date] = artifact
    return artifacts


def load_fixlog(agency_dir: Path) -> list[dict[str, Any]]:
    """Validated receipts safe to publish, oldest first.

    Legacy receipts are upgraded only when local dated artifacts reproduce the
    transition. Provenance-bearing receipts can survive pruned history, while
    any available artifact must agree with their stored producer contract.
    """
    return reconcile_receipts(load_fixlog_candidates(agency_dir), _available_artifacts(agency_dir))
