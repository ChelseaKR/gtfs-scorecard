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
        "comparison": comparison,
        "filter_semantics": {
            "selected_features": "all selected features must be published",
            "translation_language": ("exact case-insensitive BCP 47 tag in translation_languages"),
            "accessibility_thresholds": (
                "minimum share of stops or trips with a stated wheelchair field"
            ),
            "unknown_values": "excluded when their field is used as a filter",
        },
        "feeds": feeds,
    }
