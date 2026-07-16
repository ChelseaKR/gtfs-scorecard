"""Detect rider-facing translations published in a GTFS Schedule feed.

``translations.txt`` is an optional GTFS file that lets a publisher provide
customer-facing text in more than one language.  This module records adoption
for consumer discovery; it does not validate the file or change a score.  The
canonical MobilityData validator remains responsible for structural findings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gtfs import read_tables


@dataclass(frozen=True)
class TranslationsProfile:
    """Usable translation rows and the languages and tables they cover."""

    has_translations: bool
    translation_count: int
    languages: tuple[str, ...]
    translated_tables: tuple[str, ...]
    feed_lang: str | None

    def to_details(self) -> dict[str, Any]:
        return {
            "has_translations": self.has_translations,
            "translation_count": self.translation_count,
            "languages": list(self.languages),
            "translated_tables": list(self.translated_tables),
            "feed_lang": self.feed_lang,
        }


def _language_tag(value: str) -> str:
    """Normalize a language tag only enough for case-insensitive grouping.

    BCP 47 tags are case-insensitive.  Validation and more invasive repair are
    deliberately left to the canonical validator, so an invalid publisher value
    is never silently rewritten into a different claim here.
    """
    return value.strip().casefold()


def detect_translations(gtfs_zip_path: str) -> TranslationsProfile:
    """Record usable ``translations.txt`` rows without grading their absence.

    A row counts when it carries both a language tag and translated text.  Blank
    or malformed rows do not become a positive capability signal; the validator
    can still report their structural errors.  Missing files return a measured
    negative profile, while older scorecard artifacts remain explicitly unknown
    because they have no ``translations`` detail block at all.
    """
    tables = read_tables(gtfs_zip_path, ["translations.txt", "feed_info.txt"])
    rows = [
        row
        for row in tables["translations.txt"]
        if row.get("language", "").strip() and row.get("translation", "").strip()
    ]
    languages = sorted({_language_tag(row["language"]) for row in rows})
    translated_tables = sorted(
        {row.get("table_name", "").strip() for row in rows if row.get("table_name", "").strip()},
        key=str.casefold,
    )
    feed_info = tables["feed_info.txt"][0] if tables["feed_info.txt"] else {}
    feed_lang = feed_info.get("feed_lang", "").strip() or None
    return TranslationsProfile(
        has_translations=bool(rows),
        translation_count=len(rows),
        languages=tuple(languages),
        translated_tables=tuple(translated_tables),
        feed_lang=feed_lang,
    )
