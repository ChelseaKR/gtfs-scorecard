"""Tests for rider-facing GTFS translation detection."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scorecard_pipeline.translations import detect_translations


def test_missing_translations_is_a_measured_negative(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    path = make_gtfs_zip(
        {
            "agency.txt": "agency_name,agency_url,agency_timezone\nA,https://example.org,Europe/Paris\n",
            "feed_info.txt": "feed_publisher_name,feed_publisher_url,feed_lang\nA,https://example.org,fr\n",
        }
    )

    profile = detect_translations(str(path))

    assert profile.has_translations is False
    assert profile.translation_count == 0
    assert profile.languages == ()
    assert profile.translated_tables == ()
    assert profile.feed_lang == "fr"


def test_detects_languages_tables_and_unicode_text(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    path = make_gtfs_zip(
        {
            "feed_info.txt": "feed_publisher_name,feed_publisher_url,feed_lang\nA,https://example.org,mul\n",
            "translations.txt": (
                "table_name,field_name,language,translation,record_id\n"
                "stops,stop_name,FR,Gare centrale,S1\n"
                "stops,stop_name,nl,Centraal station,S1\n"
                "routes,route_long_name,ja,中央線,R1\n"
                "routes,route_long_name,fr,Ligne centrale,R1\n"
            ),
        }
    )

    details = detect_translations(str(path)).to_details()

    assert details == {
        "has_translations": True,
        "translation_count": 4,
        "languages": ["fr", "ja", "nl"],
        "translated_tables": ["routes", "stops"],
        "feed_lang": "mul",
    }


def test_blank_language_or_text_does_not_claim_translation_support(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    path = make_gtfs_zip(
        {
            "translations.txt": (
                "table_name,field_name,language,translation,record_id\n"
                "stops,stop_name,,Gare,S1\n"
                "stops,stop_name,fr,,S1\n"
            )
        }
    )

    profile = detect_translations(str(path))

    assert profile.has_translations is False
    assert profile.translation_count == 0
