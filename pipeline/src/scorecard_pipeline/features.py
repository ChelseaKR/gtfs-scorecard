"""Consumer-facing per-feed feature and accessibility measurements.

The national adoption and accessibility endpoints answer aggregate questions.
Consumers also need the rows behind those totals so they can shortlist feeds by
capability, completeness threshold, and geography. This module keeps that
row-level contract separate from the rollups while reusing their extraction
rules, so "unknown" never becomes "does not publish" and the directory, CSV
export, and public API cannot disagree.
"""

from __future__ import annotations

from typing import Any

from . import DATA_ATTRIBUTION, DATA_LICENSE, SCHEMA_VERSION
from .access import band_for, coverage_record
from .adoption import adoption_record
from .location import country_name


def feature_measurements(artifact: dict[str, Any]) -> dict[str, Any]:
    """Extract filterable capability and accessibility values from one artifact.

    Capability and accessibility availability are tracked separately because an
    older artifact can carry one detail block without the other. Missing values
    remain ``None``; a consumer must not interpret an unmeasured feed as a
    measured feed that does not publish the feature.
    """
    adoption = adoption_record(artifact)
    coverage = coverage_record(artifact)
    raw_profile = artifact.get("mode_profile")
    mode_profile = (
        raw_profile
        if isinstance(raw_profile, dict) and raw_profile.get("measured") is True
        else None
    )
    mode_rows = mode_profile.get("modes") if mode_profile else None
    modes = (
        [
            row["key"]
            for row in mode_rows
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        ]
        if isinstance(mode_rows, list)
        else None
    )
    raw_ferry_profile = artifact.get("ferry_profile")
    ferry_profile = (
        raw_ferry_profile
        if isinstance(raw_ferry_profile, dict) and raw_ferry_profile.get("measured") is True
        else None
    )
    ferry_hierarchy = ferry_profile.get("terminal_hierarchy", {}) if ferry_profile else {}
    ferry_stop_access = ferry_profile.get("stop_access", {}) if ferry_profile else {}
    ferry_accessibility = ferry_profile.get("accessibility", {}) if ferry_profile else {}
    ferry_terminals = (
        ferry_accessibility.get("terminals", {}) if isinstance(ferry_accessibility, dict) else {}
    )
    ferry_trips = (
        ferry_accessibility.get("trips", {}) if isinstance(ferry_accessibility, dict) else {}
    )
    ferry_bikes = ferry_profile.get("bikes", {}) if ferry_profile else {}
    ferry_cars = ferry_profile.get("cars", {}) if ferry_profile else {}
    ferry_fares = ferry_profile.get("fares", {}) if ferry_profile else {}
    ferry_realtime = ferry_profile.get("realtime", {}) if ferry_profile else {}

    boarding = coverage.get("wheelchair_boarding_pct") if coverage else None
    accessible = coverage.get("wheelchair_accessible_pct") if coverage else None
    has_accessibility = (
        (isinstance(boarding, int | float) and float(boarding) > 0)
        or (isinstance(accessible, int | float) and float(accessible) > 0)
        if coverage
        else None
    )

    return {
        "capabilities_measured": adoption is not None,
        "accessibility_measured": coverage is not None,
        "has_accessibility": has_accessibility,
        "wheelchair_boarding_pct": boarding,
        "wheelchair_accessible_pct": accessible,
        "accessibility_band": band_for(float(boarding)) if boarding is not None else None,
        "has_flex": adoption.get("has_flex") if adoption else None,
        "has_fares": adoption.get("has_fares") if adoption else None,
        "has_fares_v2": adoption.get("has_fares_v2") if adoption else None,
        "fare_model": adoption.get("fare_model") if adoption else None,
        "has_pathways": adoption.get("has_pathways") if adoption else None,
        "has_step_free": adoption.get("has_step_free") if adoption else None,
        "has_cemv": adoption.get("has_cemv") if adoption else None,
        "translations_measured": (adoption.get("translations_measured") if adoption else False),
        "has_translations": adoption.get("has_translations") if adoption else None,
        "translation_count": adoption.get("translation_count") if adoption else None,
        "translation_languages": (adoption.get("translation_languages") if adoption else None),
        "translated_tables": adoption.get("translated_tables") if adoption else None,
        "feed_lang": adoption.get("feed_lang") if adoption else None,
        "modes_measured": mode_profile is not None,
        "primary_mode": mode_profile.get("primary_mode") if mode_profile else None,
        "modes": modes,
        "has_ferry": mode_profile.get("has_ferry") if mode_profile else None,
        "ferry_only": mode_profile.get("ferry_only") if mode_profile else None,
        "ferry_profile_measured": ferry_profile is not None,
        "ferry_route_count": ferry_profile.get("route_count") if ferry_profile else None,
        "ferry_trip_count": ferry_profile.get("trip_count") if ferry_profile else None,
        "ferry_terminal_count": (
            ferry_hierarchy.get("boarding_location_count")
            if isinstance(ferry_hierarchy, dict)
            else None
        ),
        "ferry_stop_access_stated_pct": (
            ferry_stop_access.get("stated_pct") if isinstance(ferry_stop_access, dict) else None
        ),
        "ferry_terminal_accessibility_stated_pct": (
            ferry_terminals.get("stated_pct") if isinstance(ferry_terminals, dict) else None
        ),
        "ferry_trip_accessibility_stated_pct": (
            ferry_trips.get("stated_pct") if isinstance(ferry_trips, dict) else None
        ),
        "ferry_bikes_stated_pct": (
            ferry_bikes.get("stated_pct") if isinstance(ferry_bikes, dict) else None
        ),
        "ferry_bikes_allowed_pct": (
            ferry_bikes.get("allowed_pct") if isinstance(ferry_bikes, dict) else None
        ),
        "ferry_cars_stated_pct": (
            ferry_cars.get("stated_pct") if isinstance(ferry_cars, dict) else None
        ),
        "ferry_cars_allowed_pct": (
            ferry_cars.get("allowed_pct") if isinstance(ferry_cars, dict) else None
        ),
        "ferry_fare_model": (ferry_fares.get("model") if isinstance(ferry_fares, dict) else None),
        "ferry_realtime_kinds": (
            ferry_realtime.get("configured_kinds") if isinstance(ferry_realtime, dict) else None
        ),
    }


_PUBLIC_KEYS = (
    "id",
    "name",
    "mdb_id",
    "country",
    "subdivision_code",
    "subdivision_name",
    "grade",
    "score",
    "snapshot_date",
    "scorecard_url",
    "feed_url",
    "comparison_eligible",
    "capabilities_measured",
    "accessibility_measured",
    "has_accessibility",
    "wheelchair_boarding_pct",
    "wheelchair_accessible_pct",
    "accessibility_band",
    "has_flex",
    "has_fares",
    "has_fares_v2",
    "fare_model",
    "has_pathways",
    "has_step_free",
    "has_cemv",
    "translations_measured",
    "has_translations",
    "translation_count",
    "translation_languages",
    "translated_tables",
    "feed_lang",
    "modes_measured",
    "primary_mode",
    "modes",
    "has_ferry",
    "ferry_only",
    "ferry_profile_measured",
    "ferry_route_count",
    "ferry_trip_count",
    "ferry_terminal_count",
    "ferry_stop_access_stated_pct",
    "ferry_terminal_accessibility_stated_pct",
    "ferry_trip_accessibility_stated_pct",
    "ferry_bikes_stated_pct",
    "ferry_bikes_allowed_pct",
    "ferry_cars_stated_pct",
    "ferry_cars_allowed_pct",
    "ferry_fare_model",
    "ferry_realtime_kinds",
)


def build_feature_dataset(
    records: list[dict[str, Any]], generated_at: str, comparison: dict[str, Any]
) -> dict[str, Any]:
    """Build the versioned row-level feature API from enriched directory rows."""
    feeds: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda row: (str(row.get("name", "")).casefold(), row["id"])):
        row = {key: record.get(key) for key in _PUBLIC_KEYS}
        country = str(record.get("country") or "US")
        row["country"] = country
        row["country_name"] = country_name(country)
        feeds.append(row)

    comparable = [row for row in feeds if row.get("comparison_eligible") is True]
    return {
        "schema_version": SCHEMA_VERSION,
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": generated_at,
        "feed_record_count": len(feeds),
        "comparison_eligible_count": len(comparable),
        "capability_measured_count": sum(row.get("capabilities_measured") is True for row in feeds),
        "accessibility_measured_count": sum(
            row.get("accessibility_measured") is True for row in feeds
        ),
        "translation_measured_count": sum(
            row.get("translations_measured") is True for row in feeds
        ),
        "mode_measured_count": sum(row.get("modes_measured") is True for row in feeds),
        "ferry_profile_measured_count": sum(
            row.get("ferry_profile_measured") is True for row in feeds
        ),
        "comparison": comparison,
        "filter_semantics": {
            "selected_features": "all selected features must be published",
            "translation_language": ("exact case-insensitive BCP 47 tag in translation_languages"),
            "mode": "selected mode key must be present in modes",
            "ferry_profile": (
                "ferry schedule fields use ferry routes and trips only; fare and realtime "
                "fields describe the whole feed"
            ),
            "accessibility_thresholds": (
                "minimum share of stops or trips with a stated wheelchair field"
            ),
            "unknown_values": "excluded when their field is used as a filter",
        },
        "feeds": feeds,
    }
