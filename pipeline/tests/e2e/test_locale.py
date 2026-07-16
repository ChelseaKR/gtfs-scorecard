"""Browser-level contracts for locale-aware presentation primitives."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_locale_primitives_format_and_fallback(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/app/")
    result = page.evaluate(
        """async () => {
          const locale = await import('/src/locale.js');
          return {
            spanishDate: locale.formatDate('2026-07-12', 'es'),
            spanishNumber: locale.formatNumber(12345, 'es'),
            malformedDate: locale.formatDate('not-a-date', 'es'),
            invalidDirection: locale.localeDirection('not_a_locale'),
            frenchName: locale.formatLanguageName('fr', 'en'),
          };
        }"""
    )
    assert "2026" in result["spanishDate"]
    assert "12" in result["spanishDate"]
    assert result["spanishNumber"] != "12345"
    assert result["malformedDate"] == "not-a-date"
    assert result["invalidDirection"] == "ltr"
    assert result["frenchName"] == "French (fr)"


def test_document_direction_follows_declared_language(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/app/")
    result = page.evaluate(
        """async () => {
          const locale = await import('/src/locale.js');
          document.documentElement.lang = 'ar';
          locale.applyDocumentDirection();
          return {
            direction: document.documentElement.dir,
            pageWidth: document.documentElement.scrollWidth,
            viewport: document.documentElement.clientWidth,
          };
        }"""
    )
    assert result["direction"] == "rtl"
    assert result["pageWidth"] <= result["viewport"]
