"""Locale-catalog integrity tests."""

from __future__ import annotations

import pytest

from scorecard_pipeline.i18n import (
    PSEUDOLOCALE,
    SUPPORTED_LOCALES,
    load_app_catalog,
    load_catalog,
    pseudolocalize_text,
    validate_catalogs,
)


def test_locale_catalogs_have_matching_keys() -> None:
    validate_catalogs()
    english = set(load_catalog("en"))
    assert english
    assert all(set(load_catalog(locale)) == english for locale in SUPPORTED_LOCALES)


def test_unsupported_locale_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported locale"):
        load_catalog("fr")


def test_unsupported_app_locale_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported locale"):
        load_app_catalog("es")


def test_app_catalog_loads_and_is_non_empty() -> None:
    catalog = load_app_catalog("en")
    assert catalog
    assert all(isinstance(value, str) and value.strip() for value in catalog.values())


def test_pseudolocale_expands_marks_and_keeps_placeholders() -> None:
    text = "Could not load {path}{detail}."
    pseudo = pseudolocalize_text(text)
    assert pseudo.startswith("⟦")
    assert pseudo.endswith("⟧")
    assert "{path}" in pseudo
    assert "{detail}" in pseudo
    assert len(pseudo) >= len(text) * 1.4
    # Deterministic: the derived catalog can never drift between renders.
    assert pseudo == pseudolocalize_text(text)


def test_pseudolocale_catalog_mirrors_english_keys() -> None:
    english = load_app_catalog("en")
    pseudo = load_app_catalog(PSEUDOLOCALE)
    assert set(pseudo) == set(english)
    assert all(value.startswith("⟦") for value in pseudo.values())
