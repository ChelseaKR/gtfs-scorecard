"""Guardrails for public cross-feed summaries and named change views.

Every scorecard remains public and searchable.  Aggregate score summaries and
named change views use a narrower cohort: one current-rubric snapshot per
resolved feed identity.  Absolute rankings and individual percentiles are not
published; this module exists to keep the comparison surfaces that remain from
quietly mixing methodologies or counting duplicate feed records twice.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from . import RUBRIC_VERSION, SCORING_PROFILE_ID
from .config import Agency
from .fetch import (
    FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE,
    RAW_READER_ARCHIVE_PROFILE,
)
from .identity import normalized_feed_url, normalized_mdb_id
from .validate import VALIDATOR_VERSION

MIN_PUBLIC_COMPARISON_COHORT = 20
REQUIRED_CATEGORIES = ("correctness", "freshness", "completeness")
ALL_CATEGORIES = (*REQUIRED_CATEGORIES, "realtime")


def reader_archive_profile(record: dict[str, Any]) -> str:
    """Versioned Scorecard reader view; contradictions fail closed.

    Older artifacts carried only ``reader_archive_normalized`` (or neither
    field), so those shapes still resolve deterministically. Once an explicit
    profile is present, every explicit statement must agree before the record
    can participate in a producer-contract comparison.
    """
    fetch = record.get("fetch")
    embedded = fetch if isinstance(fetch, dict) else {}
    supported = (
        RAW_READER_ARCHIVE_PROFILE,
        FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE,
    )
    direct_present = "reader_archive_profile" in record
    embedded_present = "reader_archive_profile" in embedded
    direct_value = record.get("reader_archive_profile")
    nested_value = embedded.get("reader_archive_profile")

    direct: str | None = None
    if direct_present:
        if not isinstance(direct_value, str) or direct_value not in supported:
            return ""
        direct = direct_value
    nested: str | None = None
    if embedded_present:
        if not isinstance(nested_value, str) or nested_value not in supported:
            return ""
        nested = nested_value
    if direct is not None and nested is not None and direct != nested:
        return ""

    explicit = direct if direct is not None else nested
    normalized_present = "reader_archive_normalized" in embedded
    normalized = embedded.get("reader_archive_normalized")
    if normalized_present and not isinstance(normalized, bool):
        return ""
    implied = (
        FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE
        if normalized is True
        else RAW_READER_ARCHIVE_PROFILE
    )
    if explicit is not None:
        if normalized_present and explicit != implied:
            return ""
        return explicit
    return implied


def _required_contract_field(
    record: dict[str, Any],
    field: str,
    required: str | None,
    missing_reason: str,
    mismatch_reason: str,
) -> list[str]:
    if required is None:
        return []
    value = str(record.get(field) or "").strip()
    if not value:
        return [missing_reason]
    if value != required:
        return [mismatch_reason]
    return []


def _producer_contract_exclusions(
    record: dict[str, Any],
    required_rubric_version: str | None,
    required_scoring_profile_id: str | None,
    required_validator_version: str | None,
    required_reader_archive_profile: str | None,
) -> list[str]:
    reasons = _required_contract_field(
        record,
        "rubric_version",
        required_rubric_version,
        "rubric_version_missing",
        "rubric_version_mismatch",
    )
    if required_scoring_profile_id is not None:
        reasons.extend(
            _required_contract_field(
                record,
                "scoring_profile_id",
                required_scoring_profile_id,
                "scoring_profile_missing",
                "scoring_profile_mismatch",
            )
        )
        reasons.extend(
            _required_contract_field(
                record,
                "scoring_profile_rubric_version",
                required_rubric_version,
                "scoring_profile_rubric_missing",
                "scoring_profile_rubric_mismatch",
            )
        )
    reasons.extend(
        _required_contract_field(
            record,
            "validator_version",
            required_validator_version,
            "validator_version_missing",
            "validator_version_mismatch",
        )
    )
    if (
        required_reader_archive_profile is not None
        and reader_archive_profile(record) != required_reader_archive_profile
    ):
        reasons.append("reader_archive_profile_mismatch")
    return reasons


def comparison_exclusions(
    record: dict[str, Any],
    *,
    required_rubric_version: str | None = None,
    required_scoring_profile_id: str | None = None,
    required_validator_version: str | None = None,
    required_reader_archive_profile: str | None = RAW_READER_ARCHIVE_PROFILE,
) -> tuple[str, ...]:
    """Reasons a latest-record row is not suitable for a public comparison.

    The underlying record remains in the open dataset. Exclusion only affects
    ranked and percentile surfaces, where comparing a long-stale or partially
    measured feed with a current, fully measured feed would overstate meaning.
    """
    reasons: list[str] = []
    if not isinstance(record.get("score"), (int, float)) or isinstance(record.get("score"), bool):
        reasons.append("score_not_measured")
    if not (record.get("date") or record.get("snapshot_date")):
        reasons.append("snapshot_date_missing")
    reasons.extend(
        _producer_contract_exclusions(
            record,
            required_rubric_version,
            required_scoring_profile_id,
            required_validator_version,
            required_reader_archive_profile,
        )
    )
    for category in REQUIRED_CATEGORIES:
        if not isinstance(record.get(category), (int, float)) or isinstance(
            record.get(category), bool
        ):
            reasons.append(f"{category}_not_measured")
    days = record.get("days_until_expiry")
    if isinstance(days, (int, float)) and not isinstance(days, bool) and days < -365:
        reasons.append("service_data_long_expired")
    return tuple(reasons)


def comparison_eligible(record: dict[str, Any]) -> bool:
    return not comparison_exclusions(record)


def measured_category_signature(record: dict[str, Any]) -> tuple[str, ...]:
    """Ordered measured-category set that determines the overall denominator."""
    return tuple(
        category
        for category in ALL_CATEGORIES
        if isinstance(record.get(category), (int, float))
        and not isinstance(record.get(category), bool)
    )


def producer_contract(
    record: dict[str, Any],
) -> tuple[str, str, str, str, str, tuple[str, ...]]:
    """Comparable producer contract for either an artifact or history point."""
    embedded_profile = record.get("scoring_profile") or {}
    if not isinstance(embedded_profile, dict):
        embedded_profile = {}
    categories = record.get("categories") or {}
    measured: list[str] = []
    if isinstance(categories, dict):
        for category in ALL_CATEGORIES:
            value = categories.get(category)
            if (isinstance(value, dict) and value.get("status") == "measured") or (
                isinstance(value, (int, float)) and not isinstance(value, bool)
            ):
                measured.append(category)
    return (
        str(record.get("rubric_version") or ""),
        str(record.get("scoring_profile_id") or embedded_profile.get("id") or ""),
        str(
            record.get("scoring_profile_rubric_version")
            or embedded_profile.get("rubric_version")
            or ""
        ),
        str(record.get("validator_version") or ""),
        reader_archive_profile(record),
        tuple(measured),
    )


def same_producer_contract(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """True only when a transition cannot be explained by producer changes."""
    left_contract = producer_contract(left)
    right_contract = producer_contract(right)
    return bool(all(left_contract[:5]) and left_contract[5] and left_contract == right_contract)


def current_producer_contract_suffix(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Contiguous suffix safe for score/finding transition claims."""
    if not records:
        return []
    latest = records[-1]
    start = len(records) - 1
    while start > 0 and same_producer_contract(records[start - 1], latest):
        start -= 1
    return records[start:]


def _duplicate_values(values: Iterable[tuple[str, str]]) -> set[str]:
    """Record ids participating in a repeated, non-empty identity value."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for value, record_id in values:
        key = value.strip()
        if key:
            grouped[key].append(record_id)
    return {
        record_id
        for record_ids in grouped.values()
        if len(set(record_ids)) > 1
        for record_id in record_ids
    }


def _identity_exclusions(
    records: list[dict[str, Any]], agencies: Iterable[Agency] | None
) -> dict[str, set[str]]:
    """Per-record identity reasons for a public comparison cohort.

    Curated aliases and inactive records are excluded directly.  Unresolved
    repeated Mobility Database ids, normalized URLs, or exact feed-byte hashes
    exclude every ambiguous member rather than guessing which record is the
    canonical one.  The records still remain in the directory and open data.
    """
    reasons: dict[str, set[str]] = defaultdict(set)
    record_ids = {str(record.get("id") or "") for record in records}
    canonical_agencies: list[Agency] = []
    if agencies is not None:
        by_id = {agency.id: agency for agency in agencies}
        for record_id in record_ids:
            agency = by_id.get(record_id)
            if agency is None:
                reasons[record_id].add("identity_not_in_registry")
            elif not agency.is_canonical_feed:
                reasons[record_id].add("noncanonical_feed_record")
            else:
                canonical_agencies.append(agency)

        duplicate_ids = _duplicate_values(
            (normalized_mdb_id(str(agency.mdb_id or "")), agency.id)
            for agency in canonical_agencies
        )
        duplicate_ids.update(
            _duplicate_values(
                (normalized_feed_url(agency.static_gtfs_url), agency.id)
                for agency in canonical_agencies
            )
        )
        for record_id in duplicate_ids:
            reasons[record_id].add("duplicate_feed_identity")

    # Two distinct registry URLs can still resolve to the same feed bytes (for
    # example an old endpoint and its replacement).  The current snapshot hash
    # is the strongest available evidence that those rows are the same feed.
    duplicate_hash_ids = _duplicate_values(
        (str(record.get("feed_sha256") or ""), str(record.get("id") or "")) for record in records
    )
    for record_id in duplicate_hash_ids:
        reasons[record_id].add("duplicate_feed_identity")
    return reasons


def build_comparison_cohort(
    records: Iterable[dict[str, Any]],
    *,
    agencies: Iterable[Agency] | None = None,
    rubric_version: str = RUBRIC_VERSION,
    scoring_profile_id: str = SCORING_PROFILE_ID,
    validator_version: str = VALIDATOR_VERSION,
    required_reader_archive_profile: str = RAW_READER_ARCHIVE_PROFILE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return one current producer/category contract plus public metadata."""
    rows = list(records)
    identity_reasons = _identity_exclusions(rows, agencies)
    evaluated: list[tuple[dict[str, Any], set[str]]] = []
    signature_counts: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        record_id = str(row.get("id") or "")
        reasons = set(
            comparison_exclusions(
                row,
                required_rubric_version=rubric_version,
                required_scoring_profile_id=scoring_profile_id,
                required_validator_version=validator_version,
                required_reader_archive_profile=required_reader_archive_profile,
            )
        ) | identity_reasons.get(record_id, set())
        evaluated.append((row, reasons))
        if not reasons:
            signature_counts[measured_category_signature(row)] += 1

    # Overall scores with and without realtime use different denominators. Use
    # the largest homogeneous current-contract cohort; prefer more measured
    # categories only when cohort sizes tie. Metadata makes that choice visible.
    selected_signature = max(
        signature_counts,
        key=lambda signature: (signature_counts[signature], len(signature), signature),
        default=(),
    )

    eligible: list[dict[str, Any]] = []
    exclusion_counts: dict[str, int] = {}
    for row, reasons in evaluated:
        if not reasons and measured_category_signature(row) != selected_signature:
            reasons.add("measured_category_set_mismatch")
        if not reasons:
            eligible.append(row)
            continue
        for reason in sorted(reasons):
            exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
    return eligible, {
        "eligible_count": len(eligible),
        "excluded_count": len(rows) - len(eligible),
        "required_rubric_version": rubric_version,
        "required_scoring_profile_id": scoring_profile_id,
        "required_validator_version": validator_version,
        "required_reader_archive_profile": required_reader_archive_profile,
        "required_measured_categories": list(selected_signature),
        "measured_category_cohorts": {
            "+".join(signature): count for signature, count in sorted(signature_counts.items())
        },
        "exclusion_counts": exclusion_counts,
        "absolute_rankings_published": False,
        "individual_percentiles_published": False,
        "note": (
            "Score aggregates and named changes use one current producer contract, raw "
            "reader archive profile, and measured-category set across canonical feed records, "
            "with unresolved duplicate identities removed. "
            "Absolute rankings and individual percentiles are not published."
        ),
    }
