"""Load the packaged global ISO country and subdivision vocabulary.

The ISO registry describes valid location identifiers, not product activation.
Every assigned ISO 3166-1 country and ISO 3166-2 subdivision is accepted. The
agency registry separately determines where the scorecard currently has data.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import NoReturn

_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_SUBDIVISION_CODE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")
_PACKAGED_REGISTRY = "data/iso3166.json"


class JurisdictionConfigError(ValueError):
    """The generated jurisdiction registry is malformed."""


@dataclass(frozen=True)
class Country:
    """One assigned ISO country and its canonical subdivision labels."""

    code: str
    name: str
    subdivisions: dict[str, str]


@dataclass(frozen=True)
class JurisdictionRegistry:
    """Validated assigned-country records keyed by ISO 3166-1 alpha-2 code."""

    countries: dict[str, Country]

    @property
    def country_names(self) -> dict[str, str]:
        return {code: country.name for code, country in self.countries.items()}

    @property
    def subdivisions_by_country(self) -> dict[str, dict[str, str]]:
        return {code: dict(country.subdivisions) for code, country in self.countries.items()}


def _fail(source: str, message: str) -> NoReturn:
    raise JurisdictionConfigError(f"{source}: {message}")


def _parse_subdivisions(country_code: str, raw: object, source: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        _fail(source, f"country {country_code} subdivisions must be a mapping")
    subdivisions: dict[str, str] = {}
    for subdivision_code, subdivision_name in raw.items():
        if not isinstance(subdivision_code, str) or not _SUBDIVISION_CODE.fullmatch(
            subdivision_code
        ):
            _fail(
                source,
                f"country {country_code} has malformed subdivision code {subdivision_code!r}",
            )
        if not subdivision_code.startswith(f"{country_code}-"):
            _fail(source, f"subdivision {subdivision_code} must use country prefix {country_code}-")
        if not isinstance(subdivision_name, str) or not subdivision_name.strip():
            _fail(source, f"subdivision {subdivision_code} name must be a non-empty string")
        subdivisions[subdivision_code] = " ".join(subdivision_name.strip().split())
    return subdivisions


def _parse_country(raw_code: object, value: object, source: str) -> Country:
    if not isinstance(raw_code, str) or not _COUNTRY_CODE.fullmatch(raw_code):
        _fail(source, f"country code must be uppercase ISO alpha-2, got {raw_code!r}")
    if not isinstance(value, dict) or set(value) != {"name", "subdivisions"}:
        _fail(source, f"country {raw_code} must contain only name and subdivisions")
    name = value["name"]
    if not isinstance(name, str) or not name.strip():
        _fail(source, f"country {raw_code} name must be a non-empty string")
    subdivisions = _parse_subdivisions(raw_code, value["subdivisions"], source)
    return Country(raw_code, " ".join(name.strip().split()), subdivisions)


def parse_jurisdictions(
    raw: object, *, source: str = "scorecard_pipeline/data/iso3166.json"
) -> JurisdictionRegistry:
    """Validate a generated registry object into the immutable runtime model."""
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "source", "countries"}:
        _fail(source, "must contain only schema_version, source, and countries")
    if raw["schema_version"] != 1:
        _fail(source, f"unsupported schema_version {raw['schema_version']!r}")
    if not isinstance(raw["source"], dict) or not raw["source"]:
        _fail(source, "source must be a non-empty mapping")
    countries_raw = raw["countries"]
    if not isinstance(countries_raw, dict) or not countries_raw:
        _fail(source, "countries must be a non-empty mapping")

    countries: dict[str, Country] = {}
    for raw_code, value in countries_raw.items():
        country = _parse_country(raw_code, value, source)
        countries[country.code] = country
    return JurisdictionRegistry(countries)


def load_jurisdictions(path: Path | None = None) -> JurisdictionRegistry:
    """Read an explicit generated artifact or the copy bundled in the wheel."""
    source = str(path) if path is not None else f"scorecard_pipeline/{_PACKAGED_REGISTRY}"
    try:
        if path is not None:
            text = path.read_text(encoding="utf-8")
        else:
            text = (
                files("scorecard_pipeline").joinpath(_PACKAGED_REGISTRY).read_text(encoding="utf-8")
            )

        def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    _fail(source, f"duplicate JSON key {key!r}")
                result[key] = value
            return result

        raw = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JurisdictionConfigError(
            f"could not read jurisdiction registry {source}: {exc}"
        ) from exc
    return parse_jurisdictions(raw, source=source)


JURISDICTIONS = load_jurisdictions()
ISO_ALPHA2_CODES = frozenset(JURISDICTIONS.countries)
