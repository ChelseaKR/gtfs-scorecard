"""Tests for conservative ISO country and subdivision normalization."""

from pathlib import Path

import pytest

from scorecard_pipeline.jurisdictions import (
    ISO_ALPHA2_CODES,
    JURISDICTIONS,
    JurisdictionConfigError,
    load_jurisdictions,
    parse_jurisdictions,
)
from scorecard_pipeline.location import (
    CA_SUBDIVISIONS,
    COUNTRY_NAMES,
    US_SUBDIVISIONS,
    NormalizedLocation,
    is_valid_country_code,
    is_valid_subdivision_code,
    normalize_country_code,
    normalize_location,
    normalize_subdivision,
    resolve_published_location,
)


def _registry_raw(countries: dict[str, object]) -> dict[str, object]:
    return {"schema_version": 1, "source": {"test": "fixture"}, "countries": countries}


def test_country_normalization_supports_every_assigned_iso_country() -> None:
    assert normalize_country_code(" us ") == "US"
    assert normalize_country_code("ca") == "CA"
    assert normalize_country_code("gb") == "GB"
    assert normalize_country_code("jp") == "JP"
    assert normalize_country_code("za") == "ZA"
    assert normalize_country_code("USA") == ""
    assert normalize_country_code("XK") == ""
    assert normalize_country_code("ZZ") == ""
    assert is_valid_country_code("US")
    assert not is_valid_country_code("us")


def test_global_vocabulary_preserves_current_labels_and_covers_all_iso_records() -> None:
    assert len(COUNTRY_NAMES) == 249
    assert sum(len(country.subdivisions) for country in JURISDICTIONS.countries.values()) == 5_046
    assert COUNTRY_NAMES["US"] == "United States"
    assert COUNTRY_NAMES["CA"] == "Canada"
    assert COUNTRY_NAMES["GB"] == "United Kingdom"
    assert COUNTRY_NAMES["KR"] == "South Korea"
    assert len(US_SUBDIVISIONS) == 57
    assert US_SUBDIVISIONS["US-DC"] == "District of Columbia"
    assert US_SUBDIVISIONS["US-PR"] == "Puerto Rico"
    assert US_SUBDIVISIONS["US-UM"] == "United States Minor Outlying Islands"
    assert len(CA_SUBDIVISIONS) == 13
    assert CA_SUBDIVISIONS["CA-NU"] == "Nunavut"
    assert CA_SUBDIVISIONS["CA-QC"] == "Quebec"
    assert US_SUBDIVISIONS["US-VI"] == "U.S. Virgin Islands"


def test_global_vocabulary_has_representative_subdivisions_across_regions() -> None:
    assert len(ISO_ALPHA2_CODES) == 249
    expected = {
        "JP-13": "Tokyo",
        "BR-SP": "São Paulo",
        "ZA-GP": "Gauteng",
        "IN-DL": "Delhi",
        "GB-ENG": "England",
        "FR-ARA": "Auvergne-Rhône-Alpes",
        "TR-34": "İstanbul",
    }
    for code, name in expected.items():
        assert JURISDICTIONS.countries[code[:2]].subdivisions[code] == name


def test_generated_registry_parser_rejects_cross_country_codes() -> None:
    with pytest.raises(JurisdictionConfigError, match="must use country prefix GB-"):
        parse_jurisdictions(
            _registry_raw({"GB": {"name": "United Kingdom", "subdivisions": {"CA-ON": "England"}}})
        )


def test_generated_registry_file_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "iso3166.json"
    path.write_text(
        '{"schema_version":1,"source":{"test":"fixture"},"countries":{},"countries":{}}'
    )
    with pytest.raises(JurisdictionConfigError, match="duplicate JSON key 'countries'"):
        load_jurisdictions(path)


def test_packaged_global_registry_is_present_for_installed_tools() -> None:
    root = Path(__file__).resolve().parents[2]
    packaged = root / "pipeline" / "src" / "scorecard_pipeline" / "data" / "iso3166.json"
    assert packaged.is_file()
    assert packaged.stat().st_size > 100_000


def test_load_jurisdictions_reports_a_missing_explicit_file(tmp_path: Path) -> None:
    with pytest.raises(JurisdictionConfigError, match="could not read jurisdiction registry"):
        load_jurisdictions(tmp_path / "missing.json")


def test_subdivision_code_requires_pattern_prefix_and_known_code() -> None:
    assert is_valid_subdivision_code("US", "US-CA")
    assert is_valid_subdivision_code("CA", "CA-BC")
    assert is_valid_subdivision_code("JP", "JP-13")
    assert is_valid_subdivision_code("ZA", "ZA-GP")
    assert not is_valid_subdivision_code("US", "CA-BC")
    assert not is_valid_subdivision_code("US", "US-XX")
    assert not is_valid_subdivision_code("US", "us-ca")
    assert not is_valid_subdivision_code("USA", "US-CA")


def test_normalize_subdivision_accepts_codes_names_and_aliases() -> None:
    assert normalize_subdivision("US", "us-ca") == ("US-CA", "California")
    assert normalize_subdivision(" us ", "  new   york ") == ("US-NY", "New York")
    assert normalize_subdivision("CA", "Québec") == ("CA-QC", "Quebec")
    assert normalize_subdivision("CA", "Newfoundland & Labrador") == (
        "CA-NL",
        "Newfoundland and Labrador",
    )
    assert normalize_subdivision("jp", "tokyo") == ("JP-13", "Tokyo")
    assert normalize_subdivision("BR", "São Paulo") == ("BR-SP", "São Paulo")


def test_ambiguous_global_subdivision_names_require_a_code() -> None:
    assert normalize_subdivision("AZ", "Lənkəran") == ("", "")
    assert normalize_location("AZ", "", "Lənkəran") == NormalizedLocation(
        "AZ", "", "Lənkəran", ("ambiguous_subdivision_name",)
    )
    assert normalize_location("AZ", "AZ-LA", "Lənkəran") == NormalizedLocation(
        "AZ", "AZ-LA", "Lənkəran"
    )


def test_normalize_subdivision_applies_only_known_mdb_fixups() -> None:
    assert normalize_subdivision("US", "Chicago") == ("US-IL", "Illinois")
    assert normalize_subdivision("US", "Lake Tahoe") == ("US-CA", "California")
    assert normalize_subdivision("US", "Davis") == ("", "")
    assert normalize_subdivision("CA", "Chicago") == ("", "")


def test_normalize_location_prefers_a_valid_code() -> None:
    assert normalize_location("us", "us-il", "California") == NormalizedLocation(
        country_code="US",
        subdivision_code="US-IL",
        subdivision_name="Illinois",
        issues=("subdivision_name_mismatch",),
    )


def test_normalize_location_falls_back_to_name_but_does_not_guess() -> None:
    assert normalize_location("CA", "CA-XX", "Ontario") == NormalizedLocation(
        country_code="CA",
        subdivision_code="CA-ON",
        subdivision_name="Ontario",
        issues=("unknown_subdivision_code",),
    )
    assert normalize_location("US", "", "  Unknown  Region ") == NormalizedLocation(
        "US", "", "Unknown Region", ("unknown_subdivision_name",)
    )
    assert normalize_location("GB", "GB-ENG", "England") == NormalizedLocation(
        "GB", "GB-ENG", "England"
    )


def test_normalize_location_distinguishes_bad_codes_and_conflicts() -> None:
    assert normalize_location("US", "California", "").issues == ("malformed_subdivision_code",)
    assert normalize_location("US", "CA-BC", "").issues == ("subdivision_country_mismatch",)
    assert normalize_location("US", "US-XX", "").issues == ("unknown_subdivision_code",)
    assert normalize_location("US", "US-IL", "California").issues == ("subdivision_name_mismatch",)
    assert normalize_location("GB", "GB-ENG", "Englnd").issues == ("subdivision_name_mismatch",)


def test_normalized_location_exposes_country_alias() -> None:
    assert normalize_location("ca", "CA-BC").country == "CA"


def test_published_location_precedence_is_registry_artifact_then_legacy() -> None:
    registry = resolve_published_location(
        registry_country="CA",
        registry_subdivision_code="CA-ON",
        registry_subdivision_name="Ontario",
        artifact_country="US",
        artifact_subdivision_code="US-NY",
        legacy_state="California",
    )
    assert (registry.country_code, registry.subdivision_code) == ("CA", "CA-ON")

    artifact = resolve_published_location(
        artifact_country="CA",
        artifact_subdivision_code="CA-BC",
        artifact_subdivision_name="British Columbia",
        legacy_state="California",
    )
    assert (artifact.country_code, artifact.subdivision_code) == ("CA", "CA-BC")

    legacy = resolve_published_location(legacy_state="California")
    assert (legacy.country_code, legacy.subdivision_code, legacy.subdivision_name) == (
        "US",
        "US-CA",
        "California",
    )


def test_published_location_defaults_retained_legacy_artifact_to_us() -> None:
    retained = resolve_published_location()
    assert retained == NormalizedLocation("US", "", "")


def test_published_location_does_not_mix_cross_country_fallbacks() -> None:
    unresolved = resolve_published_location(
        registry_country="CA",
        artifact_country="US",
        artifact_subdivision_code="US-CA",
        legacy_state="California",
    )
    assert unresolved == NormalizedLocation("CA", "", "")
