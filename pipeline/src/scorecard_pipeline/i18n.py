"""Small, explicit locale catalog for localized public surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SUPPORTED_LOCALES = ("en", "es")
CATALOG_DIR = Path(__file__).with_name("locales")


def load_catalog(locale: str) -> dict[str, Any]:
    """Load a reviewed locale catalog; unsupported locales fail closed."""
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"unsupported locale: {locale}")
    data = json.loads((CATALOG_DIR / f"{locale}.json").read_text())
    if not isinstance(data, dict):
        raise ValueError(f"locale catalog {locale} must be an object")
    return data


def validate_catalogs() -> None:
    """Require every locale to carry the same message keys as English."""
    source = load_catalog("en")
    source_keys = set(source)
    for locale in SUPPORTED_LOCALES[1:]:
        catalog = load_catalog(locale)
        if set(catalog) != source_keys:
            missing = sorted(source_keys - set(catalog))
            extra = sorted(set(catalog) - source_keys)
            raise ValueError(f"locale {locale} key mismatch; missing={missing}, extra={extra}")
