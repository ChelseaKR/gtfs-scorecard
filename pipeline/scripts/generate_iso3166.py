"""Generate the packaged global ISO country and subdivision vocabulary.

Identifiers and subdivision names come from pycountry's pinned Debian
``iso-codes`` snapshot. Country display names come from Babel's pinned Unicode
CLDR snapshot because they are intended for menus and practitioner-facing UI.
Neither dependency is needed at runtime; installed tools read the committed JSON.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any

import pycountry
from babel import Locale

PYCOUNTRY_VERSION = "26.2.16"
BABEL_VERSION = "2.18.0"
EXPECTED_COUNTRIES = 249
EXPECTED_SUBDIVISIONS = 5_046
COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
SUBDIVISION_CODE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")

# Preserve the only current US/Canada public label that differs from the pinned
# ISO snapshot. These are display overrides, never additional accepted codes.
SUBDIVISION_DISPLAY_OVERRIDES = {"US-VI": "U.S. Virgin Islands"}

OUTPUT = (
    Path(__file__).resolve().parents[1] / "src" / "scorecard_pipeline" / "data" / "iso3166.json"
)


def _require_version(distribution: str, expected: str) -> None:
    actual = importlib.metadata.version(distribution)
    if actual != expected:
        raise RuntimeError(f"{distribution} {expected} is required, found {actual}")


def build_registry() -> dict[str, Any]:
    """Return the deterministic registry object from the pinned data sources."""
    _require_version("pycountry", PYCOUNTRY_VERSION)
    _require_version("Babel", BABEL_VERSION)
    english = Locale.parse("en")

    countries: dict[str, dict[str, object]] = {}
    for country in sorted(pycountry.countries, key=lambda row: row.alpha_2):
        code = country.alpha_2
        if not COUNTRY_CODE.fullmatch(code):
            raise RuntimeError(f"unexpected ISO 3166-1 code {code!r}")
        countries[code] = {
            "name": str(english.territories.get(code) or country.name),
            "subdivisions": {},
        }

    subdivision_count = 0
    for subdivision in sorted(pycountry.subdivisions, key=lambda row: row.code):
        code = subdivision.code
        country_code = subdivision.country_code
        if not SUBDIVISION_CODE.fullmatch(code) or not code.startswith(f"{country_code}-"):
            raise RuntimeError(f"unexpected ISO 3166-2 code {code!r}")
        if country_code not in countries:
            raise RuntimeError(f"subdivision {code} references unknown country {country_code}")
        subdivisions = countries[country_code]["subdivisions"]
        if not isinstance(subdivisions, dict):  # defensive assertion for the generator itself
            raise RuntimeError(f"country {country_code} subdivisions are malformed")
        subdivisions[code] = SUBDIVISION_DISPLAY_OVERRIDES.get(code, subdivision.name)
        subdivision_count += 1

    if len(countries) != EXPECTED_COUNTRIES or subdivision_count != EXPECTED_SUBDIVISIONS:
        raise RuntimeError(
            "pinned ISO source changed unexpectedly: "
            f"found {len(countries)} countries and {subdivision_count} subdivisions"
        )

    return {
        "schema_version": 1,
        "source": {
            "country_display_names": {
                "name": "Unicode CLDR via Babel",
                "url": "https://cldr.unicode.org/translation/displaynames/countryregion-territory-names",
                "version": BABEL_VERSION,
            },
            "iso_codes": {
                "name": "Debian iso-codes via pycountry",
                "url": "https://salsa.debian.org/debian/iso-codes",
                "version": PYCOUNTRY_VERSION,
            },
        },
        "countries": countries,
    }


def rendered_registry() -> str:
    """Serialize the generated artifact with stable ordering and whitespace."""
    return json.dumps(build_registry(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the committed registry is stale",
    )
    args = parser.parse_args()
    expected = rendered_registry()
    if args.check:
        try:
            actual = OUTPUT.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"could not read generated registry {OUTPUT}: {exc}", file=sys.stderr)
            return 1
        if actual != expected:
            print(
                "generated ISO registry is stale; run "
                "'cd pipeline && uv run python scripts/generate_iso3166.py'",
                file=sys.stderr,
            )
            return 1
        print(
            f"ISO registry is current ({EXPECTED_COUNTRIES} countries, "
            f"{EXPECTED_SUBDIVISIONS} subdivisions)"
        )
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
