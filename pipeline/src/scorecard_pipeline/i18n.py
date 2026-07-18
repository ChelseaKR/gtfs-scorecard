"""Small, explicit locale catalogs for localized public surfaces.

Two catalogs share one contract. The rider catalog (``en.json``/``es.json``)
carries the reviewed strings behind the Spanish-first lookup. The app catalog
(``app.en.json``) carries the interactive app's externalized strings; English
is its only reviewed locale, and the derived ``en-XA`` pseudolocale exists so
layout and concatenation defects surface before any production language is
added. A production locale still requires a named language steward
(docs/global-expansion.md); nothing here weakens that gate.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

SUPPORTED_LOCALES = ("en", "es")
APP_CATALOG_LOCALES = ("en",)
PSEUDOLOCALE = "en-XA"
CATALOG_DIR = Path(__file__).with_name("locales")

_PLACEHOLDER = re.compile(r"\{\w+\}")

# Accented stand-ins for ASCII letters. Readable enough to navigate the page,
# foreign enough that an unexternalized string stands out immediately.
_PSEUDO_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "ÅƁÇÐÉƑĜĤÎĴĶĻḾÑÖÞǪŘŠŢÛVŴXÝŽåƀçðéƒĝĥîĵķļḿñöþǫřšţûvŵxýž",
)


def load_catalog(locale: str) -> dict[str, Any]:
    """Load a reviewed locale catalog; unsupported locales fail closed."""
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"unsupported locale: {locale}")
    return _read_catalog(f"{locale}.json")


def load_app_catalog(locale: str) -> dict[str, Any]:
    """Load the interactive app's catalog; unsupported locales fail closed.

    ``en`` is the reviewed source. The ``en-XA`` pseudolocale is derived from
    it on demand rather than stored, so the two can never drift.
    """
    if locale in APP_CATALOG_LOCALES:
        return _read_catalog(f"app.{locale}.json")
    if locale == PSEUDOLOCALE:
        return pseudolocalize_catalog(_read_catalog("app.en.json"))
    raise ValueError(f"unsupported locale: {locale}")


def _read_catalog(filename: str) -> dict[str, Any]:
    data = json.loads((CATALOG_DIR / filename).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"locale catalog {filename} must be an object")
    return data


def pseudolocalize_text(text: str) -> str:
    """A deterministic pseudolocale rendering of one catalog string.

    Letters gain accents, ``{placeholder}`` tokens survive verbatim so
    interpolation still works, and the string grows by at least forty percent
    inside visible ⟦…⟧ markers. A clipped marker or a truncated tail in the
    browser means the layout cannot absorb longer translations.
    """
    parts: list[str] = []
    cursor = 0
    for match in _PLACEHOLDER.finditer(text):
        parts.append(text[cursor : match.start()].translate(_PSEUDO_MAP))
        parts.append(match.group())
        cursor = match.end()
    parts.append(text[cursor:].translate(_PSEUDO_MAP))
    padding = "·" * max(1, math.ceil(len(text) * 0.4))
    return f"⟦{''.join(parts)}{padding}⟧"


def pseudolocalize_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """Pseudolocalize every string value of an English catalog."""
    return {key: pseudolocalize_text(str(value)) for key, value in catalog.items()}


def _placeholder_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in _PLACEHOLDER.findall(text):
        counts[token] = counts.get(token, 0) + 1
    return counts


def _validate_rider_catalogs() -> None:
    source = load_catalog("en")
    source_keys = set(source)
    for locale in SUPPORTED_LOCALES[1:]:
        catalog = load_catalog(locale)
        if set(catalog) != source_keys:
            missing = sorted(source_keys - set(catalog))
            extra = sorted(set(catalog) - source_keys)
            raise ValueError(f"locale {locale} key mismatch; missing={missing}, extra={extra}")
        for key in source_keys:
            if _placeholder_counts(str(catalog[key])) != _placeholder_counts(str(source[key])):
                raise ValueError(f"locale {locale} placeholder mismatch in {key}")


def _validate_app_catalogs() -> None:
    for locale in (*APP_CATALOG_LOCALES, PSEUDOLOCALE):
        for key, value in load_app_catalog(locale).items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"app catalog {locale} has an empty value for {key}")
            if value.count("{") != value.count("}"):
                raise ValueError(f"app catalog {locale} has unbalanced braces in {key}")
    english_app = load_app_catalog("en")
    for key, value in load_app_catalog(PSEUDOLOCALE).items():
        if _placeholder_counts(value) != _placeholder_counts(str(english_app[key])):
            raise ValueError(f"pseudolocale dropped a placeholder in {key}")


def validate_catalogs() -> None:
    """Require every locale to carry the same message keys as English, with
    matching placeholders, and require the app catalog to be well formed."""
    _validate_rider_catalogs()
    _validate_app_catalogs()
