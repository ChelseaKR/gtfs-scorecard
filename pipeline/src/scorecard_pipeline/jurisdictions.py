"""Load the configured ISO countries and first-level subdivisions.

The scorecard's location contract is configuration, not application logic. A
country becomes available to the agency registry when it is listed in the root
``jurisdictions.yaml`` with a display name and its accepted ISO 3166-2 codes.
The loader is strict so a typo cannot silently create a new public grouping.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import yaml

from .config import repo_root

_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_SUBDIVISION_CODE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")

# ISO 3166-1 alpha-2 assignments, pinned so the curated activation boundary
# rejects plausible-looking typos such as UK, UU, and ZZ. The published JSON
# schemas intentionally validate shape only, so consumers remain forward-
# compatible when ISO assigns a future code; this set is updated deliberately
# as part of country activation review.
ISO_ALPHA2_CODES = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
    BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
    CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
    DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
    HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP
    KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY
    MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
    NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS
    PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR
    SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ
    UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """.split()  # noqa: SIM905 - compact, auditable ISO assignment table
)


class JurisdictionConfigError(ValueError):
    """The jurisdiction registry is malformed."""


@dataclass(frozen=True)
class Country:
    """One configured country and its canonical subdivision labels."""

    code: str
    name: str
    subdivisions: dict[str, str]


@dataclass(frozen=True)
class JurisdictionRegistry:
    """Validated country records keyed by ISO 3166-1 alpha-2 code."""

    countries: dict[str, Country]

    @property
    def country_names(self) -> dict[str, str]:
        return {code: country.name for code, country in self.countries.items()}

    @property
    def subdivisions_by_country(self) -> dict[str, dict[str, str]]:
        return {code: dict(country.subdivisions) for code, country in self.countries.items()}


def _fail(source: str, message: str) -> NoReturn:
    raise JurisdictionConfigError(f"{source}: {message}")


def _name_key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _parse_subdivisions(country_code: str, raw: object, source: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        _fail(source, f"country {country_code} subdivisions must be a mapping")
    subdivisions: dict[str, str] = {}
    names: dict[str, str] = {}
    for subdivision_code, subdivision_name in raw.items():
        if not isinstance(subdivision_code, str) or not _SUBDIVISION_CODE.fullmatch(
            subdivision_code
        ):
            _fail(
                source,
                f"country {country_code} has malformed subdivision code {subdivision_code!r}",
            )
        if not subdivision_code.startswith(f"{country_code}-"):
            _fail(
                source,
                f"subdivision {subdivision_code} must use country prefix {country_code}-",
            )
        if not isinstance(subdivision_name, str) or not subdivision_name.strip():
            _fail(source, f"subdivision {subdivision_code} name must be a non-empty string")
        canonical_name = " ".join(subdivision_name.strip().split())
        name_key = _name_key(canonical_name)
        if name_key in names:
            _fail(
                source,
                f"country {country_code} has duplicate subdivision name {canonical_name!r} "
                f"for {names[name_key]} and {subdivision_code}",
            )
        names[name_key] = subdivision_code
        subdivisions[subdivision_code] = canonical_name
    return subdivisions


def _parse_country(raw_code: object, value: object, source: str) -> Country:
    if not isinstance(raw_code, str) or not _COUNTRY_CODE.fullmatch(raw_code):
        _fail(source, f"country code must be uppercase ISO alpha-2, got {raw_code!r}")
    if raw_code not in ISO_ALPHA2_CODES:
        _fail(source, f"country code is not an assigned ISO 3166-1 alpha-2 code: {raw_code!r}")
    if not isinstance(value, dict) or set(value) != {"name", "subdivisions"}:
        _fail(source, f"country {raw_code} must contain only name and subdivisions")
    name = value["name"]
    if not isinstance(name, str) or not name.strip():
        _fail(source, f"country {raw_code} name must be a non-empty string")
    subdivisions = _parse_subdivisions(raw_code, value["subdivisions"], source)
    return Country(raw_code, " ".join(name.strip().split()), subdivisions)


def parse_jurisdictions(raw: object, *, source: str = "jurisdictions.yaml") -> JurisdictionRegistry:
    """Validate parsed YAML into an immutable jurisdiction registry."""
    if not isinstance(raw, dict) or set(raw) != {"countries"}:
        _fail(source, "must contain only a top-level 'countries:' mapping")
    countries_raw = raw["countries"]
    if not isinstance(countries_raw, dict) or not countries_raw:
        _fail(source, "countries must be a non-empty mapping")

    countries: dict[str, Country] = {}
    for raw_code, value in countries_raw.items():
        country = _parse_country(raw_code, value, source)
        countries[country.code] = country

    if "US" not in countries:
        _fail(source, "US is required because omitted agency country defaults to US")
    return JurisdictionRegistry(countries)


def _reject_duplicate_keys(node: yaml.Node | None, source: str) -> None:
    """Reject duplicate mapping keys before PyYAML can overwrite them."""
    if isinstance(node, yaml.MappingNode):
        seen: set[tuple[str, str]] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                key = (key_node.tag, key_node.value)
                if key in seen:
                    _fail(source, f"duplicate YAML key {key_node.value!r}")
                seen.add(key)
            _reject_duplicate_keys(value_node, source)
    elif isinstance(node, yaml.SequenceNode):
        for child in node.value:
            _reject_duplicate_keys(child, source)


def _parse_yaml(text: str, source: str) -> object:
    node = yaml.compose(text, Loader=yaml.SafeLoader)
    _reject_duplicate_keys(node, source)
    return yaml.safe_load(text)


def _default_source() -> tuple[str, str]:
    """Deployment override when present; packaged defaults for installed tools."""
    root_path = repo_root() / "jurisdictions.yaml"
    if os.environ.get("SCORECARD_ROOT") or root_path.exists():
        return str(root_path), root_path.read_text(encoding="utf-8")
    packaged = Path(__file__).with_name("jurisdictions.yaml")
    return "scorecard_pipeline/jurisdictions.yaml", packaged.read_text(encoding="utf-8")


def load_jurisdictions(path: Path | None = None) -> JurisdictionRegistry:
    """Read an explicit deployment registry or the packaged default."""
    try:
        if path is None:
            source, text = _default_source()
        else:
            source = str(path)
            text = path.read_text(encoding="utf-8")
        raw = _parse_yaml(text, source)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        location = str(path) if path is not None else str(repo_root() / "jurisdictions.yaml")
        raise JurisdictionConfigError(
            f"could not read jurisdiction registry {location}: {exc}"
        ) from exc
    return parse_jurisdictions(raw, source=source)


JURISDICTIONS = load_jurisdictions()
