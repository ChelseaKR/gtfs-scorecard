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

SUPPORTED_COUNTRY_CODES = frozenset({"CA", "US"})

US_SUBDIVISIONS = {
    "US-AL": "Alabama",
    "US-AK": "Alaska",
    "US-AS": "American Samoa",
    "US-AZ": "Arizona",
    "US-AR": "Arkansas",
    "US-CA": "California",
    "US-CO": "Colorado",
    "US-CT": "Connecticut",
    "US-DE": "Delaware",
    "US-DC": "District of Columbia",
    "US-FL": "Florida",
    "US-GA": "Georgia",
    "US-GU": "Guam",
    "US-HI": "Hawaii",
    "US-ID": "Idaho",
    "US-IL": "Illinois",
    "US-IN": "Indiana",
    "US-IA": "Iowa",
    "US-KS": "Kansas",
    "US-KY": "Kentucky",
    "US-LA": "Louisiana",
    "US-ME": "Maine",
    "US-MD": "Maryland",
    "US-MA": "Massachusetts",
    "US-MI": "Michigan",
    "US-MN": "Minnesota",
    "US-MS": "Mississippi",
    "US-MO": "Missouri",
    "US-MT": "Montana",
    "US-NE": "Nebraska",
    "US-NV": "Nevada",
    "US-NH": "New Hampshire",
    "US-NJ": "New Jersey",
    "US-NM": "New Mexico",
    "US-NY": "New York",
    "US-NC": "North Carolina",
    "US-ND": "North Dakota",
    "US-MP": "Northern Mariana Islands",
    "US-OH": "Ohio",
    "US-OK": "Oklahoma",
    "US-OR": "Oregon",
    "US-PA": "Pennsylvania",
    "US-PR": "Puerto Rico",
    "US-RI": "Rhode Island",
    "US-SC": "South Carolina",
    "US-SD": "South Dakota",
    "US-TN": "Tennessee",
    "US-TX": "Texas",
    "US-UM": "United States Minor Outlying Islands",
    "US-UT": "Utah",
    "US-VT": "Vermont",
    "US-VA": "Virginia",
    "US-VI": "U.S. Virgin Islands",
    "US-WA": "Washington",
    "US-WV": "West Virginia",
    "US-WI": "Wisconsin",
    "US-WY": "Wyoming",
}

CA_SUBDIVISIONS = {
    "CA-AB": "Alberta",
    "CA-BC": "British Columbia",
    "CA-MB": "Manitoba",
    "CA-NB": "New Brunswick",
    "CA-NL": "Newfoundland and Labrador",
    "CA-NS": "Nova Scotia",
    "CA-NT": "Northwest Territories",
    "CA-NU": "Nunavut",
    "CA-ON": "Ontario",
    "CA-PE": "Prince Edward Island",
    "CA-QC": "Quebec",
    "CA-SK": "Saskatchewan",
    "CA-YT": "Yukon",
}

SUBDIVISIONS_BY_COUNTRY = {
    "US": US_SUBDIVISIONS,
    "CA": CA_SUBDIVISIONS,
}

_SUBDIVISION_CODE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")


def _name_key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


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
