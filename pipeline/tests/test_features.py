"""Tests for the row-level consumer feature dataset."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.features import build_feature_dataset, feature_measurements


def _artifact(*, measured: bool = True) -> dict[str, Any]:
    details = (
        {
            "stops": 20,
            "wheelchair_boarding_pct": 95.0,
            "wheelchair_accessible_pct": 60.0,
            "accessibility": {"score": 80.0},
            "flex": {"has_flex": True},
            "fares": {"model": "v2"},
            "pathways": {"has_pathways": True, "has_step_free": False},
            "cemv": {"supported": False},
            "translations": {
                "has_translations": True,
                "translation_count": 3,
                "languages": ["fr", "nl"],
                "translated_tables": ["routes", "stops"],
                "feed_lang": "mul",
            },
        }
        if measured
        else {}
    )
    return {
        "agency": {"id": "sample", "name": "Sample Transit", "state": "California"},
        "categories": {
            "completeness": {
                "status": "measured" if measured else "not_yet_measured",
                "details": details,
            }
        },
        "mode_profile": (
            {
                "measured": True,
                "primary_mode": "ferry",
                "modes": [
                    {"key": "bus", "label": "Bus"},
                    {"key": "ferry", "label": "Ferry"},
                ],
                "has_ferry": True,
                "ferry_only": False,
            }
            if measured
            else None
        ),
    }


def test_feature_measurements_preserve_capabilities_and_accessibility_depth() -> None:
    row = feature_measurements(_artifact())

    assert row["capabilities_measured"] is True
    assert row["accessibility_measured"] is True
    assert row["has_accessibility"] is True
    assert row["wheelchair_boarding_pct"] == 95.0
    assert row["wheelchair_accessible_pct"] == 60.0
    assert row["accessibility_band"] == "most"
    assert row["has_flex"] is True
    assert row["has_fares"] is True
    assert row["has_fares_v2"] is True
    assert row["fare_model"] == "v2"
    assert row["has_pathways"] is True
    assert row["has_step_free"] is False
    assert row["has_cemv"] is False
    assert row["translations_measured"] is True
    assert row["has_translations"] is True
    assert row["translation_count"] == 3
    assert row["translation_languages"] == ["fr", "nl"]
    assert row["translated_tables"] == ["routes", "stops"]
    assert row["feed_lang"] == "mul"
    assert row["modes_measured"] is True
    assert row["primary_mode"] == "ferry"
    assert row["modes"] == ["bus", "ferry"]
    assert row["has_ferry"] is True
    assert row["ferry_only"] is False


def test_feature_measurements_keep_unmeasured_distinct_from_absent() -> None:
    row = feature_measurements(_artifact(measured=False))

    assert row["capabilities_measured"] is False
    assert row["accessibility_measured"] is False
    assert row["has_accessibility"] is None
    assert row["wheelchair_boarding_pct"] is None
    assert row["has_fares"] is None
    assert row["has_flex"] is None
    assert row["translations_measured"] is False
    assert row["has_translations"] is None
    assert row["modes_measured"] is False
    assert row["primary_mode"] is None
    assert row["modes"] is None
    assert row["has_ferry"] is None


def test_build_feature_dataset_publishes_every_row_and_guarded_counts() -> None:
    measured = {
        "id": "b",
        "name": "Beta Transit",
        "country": "CA",
        # Score-comparison eligibility is a separate contract. Feature
        # measurements remain useful while a new rubric is rolling out.
        "comparison_eligible": False,
        **feature_measurements(_artifact()),
    }
    unknown = {
        "id": "a",
        "name": "Alpha Transit",
        "country": "US",
        "comparison_eligible": False,
        **feature_measurements(_artifact(measured=False)),
    }

    payload = build_feature_dataset(
        [measured, unknown],
        "2026-07-16T00:00:00+00:00",
        {"eligible_count": 0},
    )

    assert payload["feed_record_count"] == 2
    assert payload["comparison_eligible_count"] == 0
    assert payload["capability_measured_count"] == 1
    assert payload["accessibility_measured_count"] == 1
    assert payload["translation_measured_count"] == 1
    assert payload["mode_measured_count"] == 1
    assert [row["id"] for row in payload["feeds"]] == ["a", "b"]
    assert payload["feeds"][1]["country_name"] == "Canada"
    assert payload["feeds"][0]["has_fares"] is None
    assert payload["feeds"][1]["translation_languages"] == ["fr", "nl"]
    assert payload["feeds"][1]["modes"] == ["bus", "ferry"]
    assert payload["filter_semantics"]["translation_language"] == (
        "exact case-insensitive BCP 47 tag in translation_languages"
    )
    assert payload["filter_semantics"]["mode"] == "selected mode key must be present in modes"
