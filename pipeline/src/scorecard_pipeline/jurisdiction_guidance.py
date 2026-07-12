"""Jurisdiction-aware references shown beside a GTFS Scorecard result.

The scoring contract is global and unchanged by this module.  These records
only explain which published guidance is useful to a reader in a particular
place.  Keeping that distinction in one Python source prevents the static
renderer and browser app from accidentally presenting a US requirement to a
Canadian agency, or a support program as a scoring authority.
"""

from __future__ import annotations

from typing import Any

UNIVERSAL_GUIDANCE: dict[str, Any] = {
    "scope": "all",
    "name": "GTFS and rider-information guidance",
    "note": (
        "The scorecard is a data-quality lens, not a compliance determination. "
        "Its universal references describe good GTFS and useful rider information."
    ),
    "references": [
        {
            "name": "GTFS Schedule Best Practices",
            "url": "https://gtfs.org/schedule/best-practices/",
        },
        {
            "name": "GTFS-Realtime Best Practices",
            "url": "https://gtfs.org/realtime/best-practices/",
        },
        {
            "name": "MobilityData grading scheme",
            "url": "https://github.com/MobilityData/gtfs-grading-scheme",
        },
        {
            "name": "Google Transit publication guidance",
            "url": "https://support.google.com/transitpartners/answer/1111481",
        },
    ],
    "category_notes": {
        "correctness": (
            "GTFS Schedule best practices, checked by the MobilityData validator. "
            "MobilityData grading covers stop locations, route names, and colors. "
            "Google Transit requires a feed to pass validation for publication."
        ),
        "freshness": (
            "GTFS Schedule best practices call for a dataset that stays current. "
            "An expired calendar can remove service from Google Transit and "
            "other rider trip planners."
        ),
        "completeness": (
            "GTFS Best Practices for rider-facing fields. MobilityData grading "
            "covers stop names and headsigns."
        ),
        "realtime": (
            "GTFS-Realtime best practices: a stable URL, high uptime, and frequent updates."
        ),
    },
}

US_NTD_GUIDANCE: dict[str, Any] = {
    "scope": "US",
    "kind": "requirement",
    "name": "FTA National Transit Database GTFS requirement",
    "url": "https://www.transit.dot.gov/ntd",
    "note": (
        "For US NTD reporters with qualifying service, the federal requirement "
        "calls for a public, valid, current GTFS feed and annual certification."
    ),
    "category_notes": {
        "correctness": "FTA NTD readiness also checks that the published feed is valid.",
        "freshness": "FTA NTD readiness also checks that the published feed is current.",
    },
}

JURISDICTION_GUIDANCE: dict[str, dict[str, str]] = {
    "US-CA": {
        "scope": "US-CA",
        "kind": "guideline",
        "name": "California Transit Data Guidelines",
        "url": "https://dot.ca.gov/cal-itp/california-transit-data-guidelines",
        "note": (
            "Caltrans' published quality guidelines and compliance checklist; "
            "this rubric is anchored to them."
        ),
    }
}

SUPPORT_RESOURCES: dict[str, dict[str, str]] = {
    "US-CO": {
        "scope": "US-CO",
        "kind": "support",
        "name": "CDOT Digital Transit Mobility",
        "url": "https://www.codot.gov/programs/innovativemobility/mobility-technology/digital-transit-mobility",
        "note": "Colorado's program coordinating GTFS data across transit providers.",
    },
    "US-MI": {
        "scope": "US-MI",
        "kind": "support",
        "name": "Michigan Public Transit Open Data Program",
        "url": "https://miruralmobility.org/",
        "note": "MDOT's program helping agencies produce and maintain GTFS and GTFS-Flex.",
    },
    "US-MN": {
        "scope": "US-MN",
        "kind": "support",
        "name": "MnDOT Transit",
        "url": "https://www.dot.state.mn.us/transit/",
        "note": "Minnesota's statewide transit program and data resources.",
    },
    "US-OR": {
        "scope": "US-OR",
        "kind": "support",
        "name": "Oregon ODOT Public Transportation",
        "url": "https://www.oregon.gov/odot/rptd/pages/index.aspx",
        "note": "ODOT's Public Transportation Division, which supports statewide GTFS.",
    },
    "US-WA": {
        "scope": "US-WA",
        "kind": "support",
        "name": "WSDOT Transportation Data",
        "url": "https://wsdot.wa.gov/about/transportation-data",
        "note": "WSDOT builds and publishes GTFS for Washington transit agencies.",
    },
}

US_STATE_SUBDIVISION_CODES = {
    "California": "US-CA",
    "Colorado": "US-CO",
    "Michigan": "US-MI",
    "Minnesota": "US-MN",
    "Oregon": "US-OR",
    "Washington": "US-WA",
}


def resolve_subdivision_code(
    country: str = "US", subdivision_code: str = "", state: str = ""
) -> str:
    """Return a normalized ISO 3166-2 code, with a legacy US state fallback."""
    code = subdivision_code.strip().upper()
    if code:
        return code
    if country.upper() == "US":
        return US_STATE_SUBDIVISION_CODES.get(state.strip(), "")
    return ""


def guidance_for(
    country: str = "US", subdivision_code: str = "", state: str = ""
) -> dict[str, Any]:
    """Return presentation overlays for one agency without changing its score."""
    normalized_country = country.strip().upper() or "US"
    code = resolve_subdivision_code(normalized_country, subdivision_code, state)
    return {
        "universal": UNIVERSAL_GUIDANCE,
        "national": US_NTD_GUIDANCE if normalized_country == "US" else None,
        "jurisdiction": JURISDICTION_GUIDANCE.get(code),
        "support": SUPPORT_RESOURCES.get(code),
    }
