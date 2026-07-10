"""Locale-catalog integrity tests."""

from __future__ import annotations

import pytest

from scorecard_pipeline.i18n import SUPPORTED_LOCALES, load_catalog, validate_catalogs


def test_locale_catalogs_have_matching_keys() -> None:
    validate_catalogs()
    english = set(load_catalog("en"))
    assert english
    assert all(set(load_catalog(locale)) == english for locale in SUPPORTED_LOCALES)


def test_unsupported_locale_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported locale"):
        load_catalog("fr")
