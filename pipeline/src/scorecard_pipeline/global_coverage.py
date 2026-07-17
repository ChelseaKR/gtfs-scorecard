"""Evidence-gated coverage readiness for a bounded European GTFS beta.

This module deliberately measures reviewed *feed records*, not operators,
agencies, routes, or all European public transport.  A registry record enters
the cohort only after a curator has approved explicit GTFS Schedule reuse
evidence.  The resulting document is an auditable readiness gate; it is not a
claim that GTFS Scorecard covers Europe or NeTEx.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from . import DATA_ATTRIBUTION, DATA_LICENSE
from .location import country_name, normalize_location

GLOBAL_COVERAGE_SCHEMA_VERSION = "1.0"
FRESHNESS_WINDOW_DAYS = 7

MIN_REVIEWED_FEED_RECORDS = 250
MIN_COUNTRIES = 12
MAX_LARGEST_COUNTRY_SHARE_PCT = 40.0
MIN_FRESH_SCORECARD_PCT = 95.0
REQUIRED_COMPLETE_PCT = 100.0

# EU27 plus the five explicitly included neighbouring markets.  Keep this
# closed and visible: expanding the gate's geography is a product decision,
# not a side effect of adding another registry record.
EUROPE_BETA_COUNTRY_CODES = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "CH",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GB",
        "GR",
        "HR",
        "HU",
        "IE",
        "IS",
        "IT",
        "LI",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
    }
)


def _field(value: object, name: str, default: object = None) -> object:
    """Read a dataclass-like or mapping-backed field without changing inputs."""
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _evidence_scope(evidence: object) -> list[str]:
    raw = _field(evidence, "scope", ())
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return []
    return sorted({item for item in raw if isinstance(item, str) and item})


def _is_reviewed_european_schedule_feed(agency: object) -> bool:
    country = str(_field(agency, "country", "") or "").strip().upper()
    evidence = _field(agency, "reuse_evidence")
    return (
        country in EUROPE_BETA_COUNTRY_CODES
        and str(_field(agency, "feed_status", "active") or "").strip().lower() == "active"
        and not str(_field(agency, "alias_of", "") or "").strip()
        and evidence is not None
        and _field(evidence, "decision") == "approved"
        and "gtfs_schedule" in _evidence_scope(evidence)
    )


def _indexed_rows(document: object, key: str) -> tuple[dict[str, dict[str, Any]], bool]:
    """Index public rows and report whether every row has one unique id."""
    if not isinstance(document, Mapping):
        return {}, False
    raw_rows = document.get(key)
    if not isinstance(raw_rows, list):
        return {}, False
    indexed: dict[str, dict[str, Any]] = {}
    valid = True
    for raw in raw_rows:
        if not isinstance(raw, dict):
            valid = False
            continue
        row_id = raw.get("id")
        if not isinstance(row_id, str) or not row_id or row_id in indexed:
            valid = False
            continue
        indexed[row_id] = raw
    return indexed, valid


def _parse_aware_datetime(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(dt.UTC)


def _reference_time(generated_at: str, now: dt.datetime | None) -> dt.datetime:
    candidate = now or _parse_aware_datetime(generated_at)
    if candidate is None:
        raise ValueError("generated_at must be an ISO 8601 timestamp with a UTC offset")
    if candidate.tzinfo is None or candidate.utcoffset() is None:
        raise ValueError("now must include a UTC offset")
    return candidate.astimezone(dt.UTC)


def _freshness_status(value: object, now: dt.datetime) -> tuple[bool, str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return False, "missing_retrieved_at"
    retrieved = _parse_aware_datetime(value)
    if retrieved is None:
        return False, "malformed_retrieved_at"
    age = now - retrieved
    if age < dt.timedelta(0):
        return False, "future_retrieved_at"
    if age > dt.timedelta(days=FRESHNESS_WINDOW_DAYS):
        return False, "stale_scorecard"
    return True, "fresh"


def _portable_location_valid(row: Mapping[str, Any] | None, agency: object) -> bool:
    if row is None:
        return False
    country = row.get("country")
    code = row.get("subdivision_code")
    name = row.get("subdivision_name")
    if not isinstance(country, str) or not country.strip():
        return False
    has_code = isinstance(code, str) and bool(code.strip())
    has_name = isinstance(name, str) and bool(name.strip())
    if has_code != has_name:
        return False
    raw_code = str(code) if isinstance(code, str) else ""
    raw_name = str(name) if isinstance(name, str) else ""
    normalized = normalize_location(country, raw_code, raw_name)
    agency_country = str(_field(agency, "country", "") or "").strip().upper()
    country_valid = (
        not normalized.issues
        and normalized.country == agency_country
        and normalized.country in EUROPE_BETA_COUNTRY_CODES
    )
    if not has_code and not has_name:
        return country_valid
    return (
        country_valid
        and normalized.subdivision_code == raw_code.strip().upper()
        and normalized.subdivision_name == " ".join(raw_name.strip().split())
    )


def _percentage(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator * 100.0 / denominator, 1)


def _ratio_met(numerator: int, denominator: int, threshold_pct: float, operator: str) -> bool:
    """Compare the raw ratio; display rounding must never decide readiness."""
    if denominator == 0:
        return False
    actual = numerator * 100
    threshold = threshold_pct * denominator
    if operator == ">=":
        return actual >= threshold
    if operator == "<=":
        return actual <= threshold
    raise ValueError(f"unsupported percentage operator {operator!r}")


def _criterion(
    key: str,
    label: str,
    actual: int | float | bool | None,
    threshold: int | float | bool,
    operator: str,
    unit: str,
    met: bool,
    *,
    numerator: int | None = None,
    denominator: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "key": key,
        "label": label,
        "actual": actual,
        "threshold": threshold,
        "operator": operator,
        "unit": unit,
        "met": met,
    }
    if numerator is not None:
        row["numerator"] = numerator
    if denominator is not None:
        row["denominator"] = denominator
    return row


def _public_evidence(evidence: object) -> dict[str, Any]:
    reviewed_on = _field(evidence, "reviewed_on", "")
    if isinstance(reviewed_on, (dt.date, dt.datetime)):
        reviewed_on = reviewed_on.isoformat()
    return {
        "decision": _field(evidence, "decision"),
        "source_kind": _field(evidence, "source_kind"),
        "provider_source_url": _field(evidence, "provider_source_url"),
        "terms_url": _field(evidence, "terms_url"),
        "scope": _evidence_scope(evidence),
        "attribution": _field(evidence, "attribution"),
        "reviewed_by": _field(evidence, "reviewed_by"),
        "reviewed_on": reviewed_on,
        "identity_reviewed": _field(evidence, "identity_reviewed") is True,
    }


_EXCEPTION_LABELS = {
    "missing_directory_record": "No published directory record",
    "missing_retrieved_at": "No scorecard retrieval timestamp",
    "malformed_retrieved_at": "Invalid scorecard retrieval timestamp",
    "future_retrieved_at": "Scorecard retrieval timestamp is in the future",
    "stale_scorecard": "Scorecard is older than the seven-day freshness window",
    "missing_feature_record": "No feature-finder record",
    "translations_not_measured": "Translation publication has not been measured",
    "invalid_portable_location": "Portable country and subdivision pair is incomplete or invalid",
    "identity_not_reviewed": "Feed identity has not been reviewed",
    "feature_denominator_not_disclosed": "Feature dataset does not disclose a valid denominator",
}


def _exception_rows(exceptions: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": _EXCEPTION_LABELS[key],
            "count": len(feed_ids) if key != "feature_denominator_not_disclosed" else 1,
            "feed_record_ids": sorted(feed_ids),
        }
        for key in _EXCEPTION_LABELS
        if (feed_ids := exceptions.get(key)) is not None
        if feed_ids or key == "feature_denominator_not_disclosed"
    ]


def _feature_denominator(
    features: Mapping[str, Any], feature_rows: dict[str, dict[str, Any]], ids_valid: bool
) -> tuple[int | None, bool]:
    declared = features.get("feed_record_count")
    if not isinstance(declared, int) or isinstance(declared, bool):
        return None, False
    disclosed = declared >= 0 and declared == len(feature_rows) and ids_valid
    return declared, disclosed


def _assess_feed_record(
    agency: object,
    directory_row: dict[str, Any] | None,
    feature_row: dict[str, Any] | None,
    evaluated_at: dt.datetime,
) -> tuple[dict[str, Any], list[str]]:
    feed_id = str(_field(agency, "id", ""))
    evidence = _field(agency, "reuse_evidence")
    exceptions: list[str] = []

    if directory_row is None:
        fresh = False
        freshness_status = "missing_directory_record"
    else:
        fresh, freshness_status = _freshness_status(directory_row.get("retrieved_at"), evaluated_at)
    if not fresh:
        exceptions.append(freshness_status)

    if feature_row is None:
        exceptions.append("missing_feature_record")
    translations_measured = (
        feature_row is not None and feature_row.get("translations_measured") is True
    )
    if not translations_measured:
        exceptions.append("translations_not_measured")

    portable_location = _portable_location_valid(directory_row, agency)
    if not portable_location:
        exceptions.append("invalid_portable_location")

    identity_reviewed = _field(evidence, "identity_reviewed") is True
    if not identity_reviewed:
        exceptions.append("identity_not_reviewed")

    return (
        {
            "id": feed_id,
            "name": str(_field(agency, "name", "")),
            "organization_id": str(_field(agency, "organization_id", "") or "") or None,
            "country": str(_field(agency, "country", "") or "").strip().upper(),
            "subdivision_code": str(
                directory_row.get("subdivision_code", "")
                if directory_row is not None
                else _field(agency, "subdivision_code", "")
            ),
            "subdivision_name": str(
                directory_row.get("subdivision_name", "")
                if directory_row is not None
                else _field(agency, "subdivision_name", "")
            ),
            "feed_url": _field(agency, "static_gtfs_url"),
            "scorecard_url": (directory_row or {}).get("scorecard_url"),
            "retrieved_at": (directory_row or {}).get("retrieved_at"),
            "fresh": fresh,
            "freshness_status": freshness_status,
            "feature_record_present": feature_row is not None,
            "translations_measured": translations_measured,
            "portable_location_valid": portable_location,
            "identity_reviewed": identity_reviewed,
            "reuse_evidence": _public_evidence(evidence),
        },
        exceptions,
    )


def build_global_coverage(
    agencies: Iterable[object],
    directory: Mapping[str, Any],
    features: Mapping[str, Any],
    generated_at: str,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build the evidence-gated European coverage-readiness document.

    ``directory`` and ``features`` are the already-published API documents.
    Joining those outputs ensures the gate assesses what consumers can actually
    see, while the registry remains authoritative for cohort membership and
    reuse permission.  ``now`` is injectable for deterministic freshness tests;
    when omitted, ``generated_at`` is the evaluation time.
    """
    evaluated_at = _reference_time(generated_at, now)
    directory_rows, _directory_ids_valid = _indexed_rows(directory, "agencies")
    feature_rows, feature_ids_valid = _indexed_rows(features, "feeds")
    declared_feature_count, feature_denominator_disclosed = _feature_denominator(
        features, feature_rows, feature_ids_valid
    )

    cohort = sorted(
        (agency for agency in agencies if _is_reviewed_european_schedule_feed(agency)),
        key=lambda agency: (
            str(_field(agency, "country", "")),
            str(_field(agency, "name", "")).casefold(),
            str(_field(agency, "id", "")),
        ),
    )
    denominator = len(cohort)
    country_counts = Counter(
        str(_field(agency, "country", "") or "").strip().upper() for agency in cohort
    )

    exceptions: dict[str, list[str]] = {}

    def note(key: str, feed_id: str = "") -> None:
        bucket = exceptions.setdefault(key, [])
        if feed_id:
            bucket.append(feed_id)

    if not feature_denominator_disclosed:
        note("feature_denominator_not_disclosed")

    records: list[dict[str, Any]] = []
    for agency in cohort:
        feed_id = str(_field(agency, "id", ""))
        record, record_exceptions = _assess_feed_record(
            agency,
            directory_rows.get(feed_id),
            feature_rows.get(feed_id),
            evaluated_at,
        )
        records.append(record)
        for key in record_exceptions:
            note(key, feed_id)

    fresh_count = sum(record["fresh"] is True for record in records)
    translations_measured_count = sum(record["translations_measured"] is True for record in records)
    portable_location_count = sum(record["portable_location_valid"] is True for record in records)
    identity_reviewed_count = sum(record["identity_reviewed"] is True for record in records)
    feature_record_count = sum(record["feature_record_present"] is True for record in records)

    countries: list[dict[str, Any]] = [
        {
            "country_code": code,
            "country_name": country_name(code, code),
            "feed_record_count": count,
            "share_pct": _percentage(count, denominator),
        }
        for code, count in sorted(country_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    largest_country = countries[0] if countries else None
    largest_country_count = int(largest_country["feed_record_count"]) if largest_country else 0
    largest_share = float(largest_country["share_pct"]) if largest_country else None

    fresh_pct = _percentage(fresh_count, denominator)
    translations_pct = _percentage(translations_measured_count, denominator)
    portable_location_pct = _percentage(portable_location_count, denominator)
    identity_reviewed_pct = _percentage(identity_reviewed_count, denominator)

    criteria = [
        _criterion(
            "reviewed_feed_records",
            "Reviewed European GTFS Schedule feed records",
            denominator,
            MIN_REVIEWED_FEED_RECORDS,
            ">=",
            "feed_records",
            denominator >= MIN_REVIEWED_FEED_RECORDS,
        ),
        _criterion(
            "countries",
            "Countries represented",
            len(countries),
            MIN_COUNTRIES,
            ">=",
            "countries",
            len(countries) >= MIN_COUNTRIES,
        ),
        _criterion(
            "largest_country_share",
            "Largest single-country share",
            largest_share,
            MAX_LARGEST_COUNTRY_SHARE_PCT,
            "<=",
            "percent",
            _ratio_met(
                largest_country_count,
                denominator,
                MAX_LARGEST_COUNTRY_SHARE_PCT,
                "<=",
            ),
            numerator=largest_country_count if largest_country else None,
            denominator=denominator if denominator else None,
        ),
        _criterion(
            "fresh_scorecards",
            "Scorecards retrieved within the inclusive seven-day window",
            fresh_pct,
            MIN_FRESH_SCORECARD_PCT,
            ">=",
            "percent",
            _ratio_met(fresh_count, denominator, MIN_FRESH_SCORECARD_PCT, ">="),
            numerator=fresh_count,
            denominator=denominator,
        ),
        _criterion(
            "translations_measured",
            "Translation publication measured",
            translations_pct,
            REQUIRED_COMPLETE_PCT,
            ">=",
            "percent",
            _ratio_met(translations_measured_count, denominator, REQUIRED_COMPLETE_PCT, ">="),
            numerator=translations_measured_count,
            denominator=denominator,
        ),
        _criterion(
            "portable_location",
            "Valid portable country and subdivision pair",
            portable_location_pct,
            REQUIRED_COMPLETE_PCT,
            ">=",
            "percent",
            _ratio_met(portable_location_count, denominator, REQUIRED_COMPLETE_PCT, ">="),
            numerator=portable_location_count,
            denominator=denominator,
        ),
        _criterion(
            "identity_reviewed",
            "Feed identity reviewed",
            identity_reviewed_pct,
            REQUIRED_COMPLETE_PCT,
            ">=",
            "percent",
            _ratio_met(identity_reviewed_count, denominator, REQUIRED_COMPLETE_PCT, ">="),
            numerator=identity_reviewed_count,
            denominator=denominator,
        ),
        _criterion(
            "feature_denominator_disclosed",
            "Feature finder discloses its feed-record denominator",
            feature_denominator_disclosed,
            True,
            "=",
            "boolean",
            feature_denominator_disclosed,
        ),
    ]
    ready = all(row["met"] for row in criteria)

    return {
        "schema_version": GLOBAL_COVERAGE_SCHEMA_VERSION,
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "license_scope": (
            "The license covers this derived GTFS Scorecard gate output. "
            "Each source feed's reuse terms are cited on its record."
        ),
        "generated_at": generated_at,
        "evaluated_at": evaluated_at.isoformat(timespec="seconds"),
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "scope": {
            "name": "Bounded European GTFS Schedule beta",
            "country_codes": sorted(EUROPE_BETA_COUNTRY_CODES),
            "unit": "feed_records",
            "selection": (
                "Active canonical registry records with approved reuse evidence "
                "whose scope includes gtfs_schedule"
            ),
        },
        "limitations": [
            "This gate does not claim coverage of all European transit.",
            "It covers GTFS Schedule feed records only; it does not assess NeTEx coverage.",
            "Feed-record counts are not counts of agencies, operators, routes, or services.",
            "Freshness describes the latest published scorecard retrieval, "
            "not the service calendar.",
        ],
        "methodology": {
            "freshness_window_days": FRESHNESS_WINDOW_DAYS,
            "freshness_window_inclusive": True,
            "future_timestamps_are_fresh": False,
            "translation_measurement": "translations_measured must be the boolean true",
            "empty_percentage": "null and criterion not met",
            "registry_permission_fields_not_used": [
                "license_note",
                "is_official",
                "mdb_id",
            ],
        },
        "cohort": {
            "feed_record_count": denominator,
            "country_count": len(countries),
            "feature_record_count": feature_record_count,
            "largest_country": largest_country,
        },
        "feature_finder": {
            "source_feed_record_count": declared_feature_count,
            "source_row_count": len(feature_rows),
            "reviewed_europe_feed_record_count": denominator,
            "reviewed_europe_feature_record_count": feature_record_count,
            "denominator_disclosed": feature_denominator_disclosed,
        },
        "criteria": criteria,
        "countries": countries,
        "exceptions": _exception_rows(exceptions),
        "records": records,
    }
