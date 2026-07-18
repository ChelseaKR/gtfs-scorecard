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


def test_pseudolocale_preview_expands_catalog_strings(page: Page, base_url: str) -> None:
    # The derived en-XA preview must reach every catalog-rendered string
    # (visible ⟦…⟧ markers prove the copy came from the catalog, not a
    # hardcoded literal) without breaking the single-column layout.
    page.goto(f"{base_url}/app/?l10n=en-XA#/agency/agency-that-is-not-tracked")
    box = page.wait_for_selector(".error-box")
    assert box is not None
    text = box.inner_text()
    assert "⟦" in text
    assert "⟧" in text
    result = page.evaluate(
        """() => ({
          lang: document.documentElement.lang,
          pageWidth: document.documentElement.scrollWidth,
          viewport: document.documentElement.clientWidth,
        })"""
    )
    assert result["lang"] == "en-XA"
    assert result["pageWidth"] <= result["viewport"]


def test_locale_preview_fails_closed_to_english(page: Page, base_url: str) -> None:
    # An unsupported preview tag must leave the page in reviewed English:
    # no partial locale, no pseudolocale markers.
    page.goto(f"{base_url}/app/?l10n=xx-nope#/agency/agency-that-is-not-tracked")
    box = page.wait_for_selector(".error-box")
    assert box is not None
    text = box.inner_text()
    assert "No scorecard for" in text
    assert "⟦" not in text
    assert page.evaluate("document.documentElement.lang") == "en"


def test_rtl_direction_holds_on_a_rendered_route(page: Page, base_url: str) -> None:
    # The RTL browser contract on a real rendered route, not just the shell:
    # flipping the declared language must mirror the document without
    # horizontal overflow.
    page.goto(f"{base_url}/app/")
    page.wait_for_selector("#main h1")
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
