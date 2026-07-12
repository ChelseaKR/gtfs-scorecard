"""Tests for conservative ISO country and subdivision normalization."""

from scorecard_pipeline.location import (
    CA_SUBDIVISIONS,
    US_SUBDIVISIONS,
    NormalizedLocation,
    is_valid_country_code,
    is_valid_subdivision_code,
    normalize_country_code,
    normalize_location,
    normalize_subdivision,
    resolve_published_location,
)


def test_country_normalization_supports_us_and_canada_only() -> None:
    assert normalize_country_code(" us ") == "US"
    assert normalize_country_code("ca") == "CA"
    assert normalize_country_code("USA") == ""
    assert normalize_country_code("GB") == ""
    assert is_valid_country_code("US")
    assert not is_valid_country_code("us")


def test_maps_cover_us_states_territories_and_canadian_subdivisions() -> None:
    assert len(US_SUBDIVISIONS) == 57
    assert US_SUBDIVISIONS["US-DC"] == "District of Columbia"
    assert US_SUBDIVISIONS["US-PR"] == "Puerto Rico"
    assert US_SUBDIVISIONS["US-UM"] == "United States Minor Outlying Islands"
    assert len(CA_SUBDIVISIONS) == 13
    assert CA_SUBDIVISIONS["CA-NU"] == "Nunavut"
    assert CA_SUBDIVISIONS["CA-QC"] == "Quebec"


def test_subdivision_code_requires_pattern_prefix_and_known_code() -> None:
    assert is_valid_subdivision_code("US", "US-CA")
    assert is_valid_subdivision_code("CA", "CA-BC")
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
        "", "", "England", ("unsupported_country",)
    )


def test_normalize_location_distinguishes_bad_codes_and_conflicts() -> None:
    assert normalize_location("US", "California", "").issues == ("malformed_subdivision_code",)
    assert normalize_location("US", "CA-BC", "").issues == ("subdivision_country_mismatch",)
    assert normalize_location("US", "US-XX", "").issues == ("unknown_subdivision_code",)
    assert normalize_location("US", "US-IL", "California").issues == ("subdivision_name_mismatch",)


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
