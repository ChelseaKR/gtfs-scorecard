"""Country and subdivision normalization for the supported agency registry.

The registry stores ISO 3166 identifiers, while source catalogs sometimes
provide a subdivision name instead of a code.  Normalization is deliberately
conservative: only supported countries and known subdivisions are returned.
Unknown values stay unknown rather than being inferred from a city or agency
name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .jurisdictions import JURISDICTIONS

COUNTRY_NAMES = JURISDICTIONS.country_names
SUBDIVISIONS_BY_COUNTRY = JURISDICTIONS.subdivisions_by_country
SUPPORTED_COUNTRY_CODES = frozenset(COUNTRY_NAMES)

# Compatibility exports used by existing callers and tests. Their values now
# come from jurisdictions.yaml, so extending the registry does not require
# another country-specific constant in Python.
US_SUBDIVISIONS = SUBDIVISIONS_BY_COUNTRY["US"]
CA_SUBDIVISIONS = SUBDIVISIONS_BY_COUNTRY.get("CA", {})

_SUBDIVISION_CODE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")


def _name_key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def country_name(country_code: str, fallback: str = "Unlocated") -> str:
    """Configured practitioner-facing country name, or *fallback* when unknown."""
    return COUNTRY_NAMES.get(country_code.strip().upper(), fallback)


_SUBDIVISION_CODES_BY_NAME = {
    country: {_name_key(name): code for code, name in subdivisions.items()}
    for country, subdivisions in SUBDIVISIONS_BY_COUNTRY.items()
}

# Mobility Database source rows known to contain a city or region in the
# subdivision field. Keep this allowlist narrow so unknown places are not
# silently assigned to a jurisdiction.
_MDB_SUBDIVISION_FIXUPS = {
    ("US", "chicago"): "US-IL",
    ("US", "lake tahoe"): "US-CA",
}

# Common catalog variants of official ISO subdivision names.
_SUBDIVISION_NAME_ALIASES = {
    ("US", "virgin islands, u.s."): "US-VI",
    ("US", "us virgin islands"): "US-VI",
    ("CA", "newfoundland & labrador"): "CA-NL",
    ("CA", "québec"): "CA-QC",
}


@dataclass(frozen=True)
class NormalizedLocation:
    """Canonical registry location plus machine-readable normalization issues."""

    country_code: str
    subdivision_code: str
    subdivision_name: str
    issues: tuple[str, ...] = ()

    @property
    def country(self) -> str:
        """Compatibility alias for callers whose models use ``country``."""
        return self.country_code


def resolve_published_location(
    *,
    registry_country: str = "",
    registry_subdivision_code: str = "",
    registry_subdivision_name: str = "",
    artifact_country: str = "",
    artifact_subdivision_code: str = "",
    artifact_subdivision_name: str = "",
    legacy_state: str = "",
) -> NormalizedLocation:
    """Resolve an output location without guessing from names or feed content.

    The curated registry is authoritative, a persisted artifact is the fallback
    for retained scorecards no longer in the registry, and the old US ``state``
    field is the final compatibility source. Empty subdivision fields at a
    higher-precedence source do not hide valid lower-precedence fields, but a
    subdivision is only accepted when it belongs to the selected country.
    """
    registry_code = normalize_country_code(registry_country)
    artifact_code = normalize_country_code(artifact_country)
    # Historical artifacts predate the country field and are US records by
    # contract. This default must also cover retained pages that no longer have
    # a registry entry or state lookup; otherwise a render would turn them into
    # an invalid empty-country row.
    country = registry_code or artifact_code or "US"

    candidates = (
        (registry_code, registry_subdivision_code, registry_subdivision_name),
        (artifact_code, artifact_subdivision_code, artifact_subdivision_name),
    )
    for source_country, subdivision_code, subdivision_name in candidates:
        if source_country != country or not (subdivision_code.strip() or subdivision_name.strip()):
            continue
        location = normalize_location(country, subdivision_code, subdivision_name)
        if location.subdivision_code or location.subdivision_name:
            return location

    if country == "US" and legacy_state.strip():
        code, name = normalize_subdivision(country, legacy_state)
        if code:
            return NormalizedLocation(country, code, name)
    return NormalizedLocation(country, "", "")


def normalize_country_code(country_code: str) -> str:
    """Return a supported canonical ISO 3166-1 alpha-2 code, or ``""``."""
    normalized = country_code.strip().upper()
    return normalized if normalized in SUPPORTED_COUNTRY_CODES else ""


def is_valid_country_code(country_code: str) -> bool:
    """Whether *country_code* is already a supported canonical alpha-2 code."""
    return country_code in SUPPORTED_COUNTRY_CODES


def is_valid_subdivision_code(country_code: str, subdivision_code: str) -> bool:
    """Whether a canonical ISO 3166-2 code exists under the given country."""
    if not is_valid_country_code(country_code) or not _SUBDIVISION_CODE.fullmatch(subdivision_code):
        return False
    if not subdivision_code.startswith(f"{country_code}-"):
        return False
    return subdivision_code in SUBDIVISIONS_BY_COUNTRY[country_code]


def normalize_subdivision(country_code: str, subdivision: str) -> tuple[str, str]:
    """Return ``(ISO code, canonical name)`` for a known subdivision.

    ``subdivision`` may be an ISO 3166-2 code, a canonical name, a supported
    name alias, or one of the explicitly documented Mobility Database fixups.
    Unknown and cross-country values return ``("", "")``.
    """
    country = normalize_country_code(country_code)
    if not country:
        return "", ""

    value = subdivision.strip()
    candidate_code = value.upper()
    subdivisions = SUBDIVISIONS_BY_COUNTRY[country]
    if is_valid_subdivision_code(country, candidate_code):
        return candidate_code, subdivisions[candidate_code]

    key = _name_key(value)
    code = _SUBDIVISION_CODES_BY_NAME[country].get(key)
    if code is None:
        code = _SUBDIVISION_NAME_ALIASES.get((country, key))
    if code is None:
        code = _MDB_SUBDIVISION_FIXUPS.get((country, key))
    if code is None:
        return "", ""
    return code, subdivisions[code]


def normalize_location(
    country_code: str,
    subdivision_code: str = "",
    subdivision_name: str = "",
) -> NormalizedLocation:
    """Normalize catalog location fields without inferring unknown values.

    A recognized code is authoritative. If it is absent or invalid, a known
    subdivision name is used. Unknown names are preserved without a guessed
    code. ``issues`` distinguishes unsupported countries, malformed or
    cross-country codes, unknown codes/names, and code/name conflicts so strict
    config loaders can reject them while catalog ingestion can retain evidence.
    """
    country = normalize_country_code(country_code)
    if not country:
        preserved_name = " ".join(subdivision_name.strip().split())
        return NormalizedLocation("", "", preserved_name, ("unsupported_country",))

    raw_code = subdivision_code.strip()
    raw_name = " ".join(subdivision_name.strip().split())
    issues: list[str] = []
    code = ""
    name = ""

    if raw_code:
        candidate_code = raw_code.upper()
        if not _SUBDIVISION_CODE.fullmatch(candidate_code):
            issues.append("malformed_subdivision_code")
        elif not candidate_code.startswith(f"{country}-"):
            issues.append("subdivision_country_mismatch")
        elif candidate_code not in SUBDIVISIONS_BY_COUNTRY[country]:
            issues.append("unknown_subdivision_code")
        else:
            code = candidate_code
            name = SUBDIVISIONS_BY_COUNTRY[country][code]

    name_code, canonical_name = normalize_subdivision(country, raw_name)
    if code:
        if name_code and name_code != code:
            issues.append("subdivision_name_mismatch")
    elif name_code:
        code, name = name_code, canonical_name
    elif raw_name:
        name = raw_name
        issues.append("unknown_subdivision_name")

    return NormalizedLocation(country, code, name, tuple(issues))
