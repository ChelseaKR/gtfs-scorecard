"""Load the agency registry from agencies.yaml (repo root).

Phase 4: any agency can be added with a YAML block and no code change
(docs/add-your-agency.md). The loader validates entries up front so a typo
in a community PR fails with a sentence, not a stack trace mid-pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .config import AGENCIES, Agency, register, repo_root
from .location import normalize_location

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
NTD_ID_PATTERN = re.compile(r"^\d{4,5}$")
RT_KINDS = ("trip_updates", "vehicle_positions", "service_alerts")

# Countries the pipeline knows how to render fairly (state/province handling,
# standards framing per ADR 0026). A typo like "UU" must fail here, not pass a
# shape check and silently drop the agency from the US-only surfaces.
SUPPORTED_COUNTRIES = {"US", "CA"}
FEED_STATUSES = {"active", "deprecated", "inactive", "development"}


class AgencyConfigError(ValueError):
    """agencies.yaml is malformed; the message says exactly where."""


def _fail(entry_label: str, message: str) -> None:
    raise AgencyConfigError(f"agencies.yaml, {entry_label}: {message}")


def _require_url(entry_label: str, field: str, value: object) -> str:
    if not isinstance(value, str) or not value.startswith(("https://", "http://")):
        _fail(entry_label, f"{field} must be an http(s) URL, got {value!r}")
    return str(value)


def parse_agencies(raw: object) -> list[Agency]:  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    """Validate parsed YAML into Agency records."""
    if not isinstance(raw, dict) or not isinstance(raw.get("agencies"), list):
        raise AgencyConfigError("agencies.yaml must contain a top-level 'agencies:' list")

    agencies: list[Agency] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw["agencies"]):
        label = f"entry {i + 1}"
        if not isinstance(entry, dict):
            _fail(label, "each agency must be a mapping of fields")
        agency_id = entry.get("id")
        if not isinstance(agency_id, str) or not ID_PATTERN.match(agency_id):
            _fail(label, f"id must be a lowercase slug (letters/digits/-/_), got {agency_id!r}")
        label = f"agency '{agency_id}'"
        if agency_id in seen:
            _fail(label, "duplicate id")
        seen.add(str(agency_id))

        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            _fail(label, "name is required")

        static_url = _require_url(label, "static_gtfs_url", entry.get("static_gtfs_url"))

        rt_urls_raw = entry.get("rt_urls") or {}
        if not isinstance(rt_urls_raw, dict):
            _fail(label, "rt_urls must be a mapping of feed kind to URL")
        rt_urls: dict[str, str] = {}
        for kind, url in rt_urls_raw.items():
            if kind not in RT_KINDS:
                _fail(label, f"unknown rt_urls kind {kind!r}; expected one of {RT_KINDS}")
            rt_urls[str(kind)] = _require_url(label, f"rt_urls.{kind}", url)

        unknown = set(entry) - {
            "id",
            "name",
            "static_gtfs_url",
            "rt_urls",
            "rt_note",
            "license_note",
            "operating_note",
            "ntd_note",
            "mdb_id",
            "organization_id",
            "alias_of",
            "feed_variant",
            "feed_status",
            "is_official",
            "ntd_id",
            "country",
            "subdivision_code",
            "subdivision_name",
            "state",
            "service_type",
            "fare_free",
        }
        if unknown:
            _fail(label, f"unknown field(s): {', '.join(sorted(unknown))}")

        # NTD IDs are FTA-assigned digit strings (five digits today, four on
        # older records). Validate the shape when set so a typo is caught before
        # it shows on a real agency's page; empty is fine and means "unknown".
        ntd_id = str(entry.get("ntd_id") or "").strip()
        if ntd_id and not NTD_ID_PATTERN.match(ntd_id):
            _fail(label, f"ntd_id must be a 4- or 5-digit NTD number, got {ntd_id!r}")

        service_type = str(entry.get("service_type") or "fixed").strip()
        if service_type not in ("fixed", "seasonal", "demand_response"):
            _fail(
                label,
                f"service_type must be fixed, seasonal, or demand_response, got {service_type!r}",
            )

        fare_free = entry.get("fare_free", False)
        if not isinstance(fare_free, bool):
            _fail(label, f"fare_free must be true or false, got {fare_free!r}")

        organization_id = str(entry.get("organization_id") or "").strip()
        if organization_id and not ID_PATTERN.match(organization_id):
            _fail(label, f"organization_id must be a lowercase slug, got {organization_id!r}")
        alias_of = str(entry.get("alias_of") or "").strip()
        if alias_of and not ID_PATTERN.match(alias_of):
            _fail(label, f"alias_of must be a lowercase agency id, got {alias_of!r}")
        if alias_of == agency_id:
            _fail(label, "alias_of cannot point to the same entry")
        feed_status = str(entry.get("feed_status") or "active").strip().lower()
        if feed_status not in FEED_STATUSES:
            _fail(label, f"feed_status must be one of {sorted(FEED_STATUSES)}, got {feed_status!r}")
        official_raw = entry.get("is_official")
        if official_raw is not None and not isinstance(official_raw, bool):
            _fail(label, f"is_official must be true or false, got {official_raw!r}")

        country = str(entry.get("country") or "US").strip().upper()
        subdivision_code = str(entry.get("subdivision_code") or "").strip().upper()
        subdivision_name = str(entry.get("subdivision_name") or "").strip()
        state = str(entry.get("state") or "").strip()
        if country != "US" and state:
            _fail(label, "state is a deprecated US-only field; use subdivision_code/name")
        if country not in SUPPORTED_COUNTRIES:
            _fail(
                label,
                f"country must be one of {sorted(SUPPORTED_COUNTRIES)}, got {country!r}. "
                "Supporting a new country is deliberate work (state/province handling, "
                "standards framing; ADR 0026), so extend SUPPORTED_COUNTRIES alongside "
                "that plumbing.",
            )
        location = normalize_location(country, subdivision_code, subdivision_name)
        issue_messages = {
            "malformed_subdivision_code": (
                "subdivision_code must be an ISO 3166-2 code such as US-CA or CA-ON"
            ),
            "subdivision_country_mismatch": "subdivision_code country prefix must match country",
            "unknown_subdivision_code": "subdivision_code is not recognized for this country",
            "subdivision_name_mismatch": "subdivision_code and subdivision_name disagree",
        }
        blocking_issues = [issue for issue in location.issues if issue in issue_messages]
        if blocking_issues:
            _fail(label, issue_messages[blocking_issues[0]])
        if state:
            legacy_location = normalize_location(country, "", state)
            if legacy_location.issues:
                _fail(label, "state must be a recognized US state or territory name")
            if location.subdivision_name and (
                location.subdivision_code != legacy_location.subdivision_code
                or location.subdivision_name != legacy_location.subdivision_name
            ):
                _fail(label, "state conflicts with subdivision_code/name")
            location = legacy_location

        agencies.append(
            Agency(
                id=str(agency_id),
                name=str(name).strip(),
                static_gtfs_url=static_url,
                rt_urls=rt_urls,
                rt_note=str(entry.get("rt_note") or "").strip(),
                license_note=str(entry.get("license_note") or "").strip(),
                operating_note=str(entry.get("operating_note") or "").strip(),
                ntd_note=str(entry.get("ntd_note") or "").strip(),
                mdb_id=str(entry.get("mdb_id") or "").strip(),
                organization_id=organization_id,
                alias_of=alias_of,
                feed_variant=str(entry.get("feed_variant") or "").strip(),
                feed_status=feed_status,
                is_official=official_raw,
                ntd_id=ntd_id,
                country=location.country,
                subdivision_code=location.subdivision_code,
                subdivision_name=location.subdivision_name,
                state=state,
                service_type=service_type,
                fare_free=fare_free,
            )
        )
    if not agencies:
        raise AgencyConfigError("agencies.yaml lists no agencies")
    by_id = {agency.id: agency for agency in agencies}
    for agency in agencies:
        if agency.alias_of and agency.alias_of not in by_id:
            _fail(f"agency '{agency.id}'", f"alias_of references unknown id {agency.alias_of!r}")
        seen_aliases = {agency.id}
        target = agency.alias_of
        while target:
            if target in seen_aliases:
                _fail(f"agency '{agency.id}'", "alias_of contains a cycle")
            seen_aliases.add(target)
            target = by_id[target].alias_of
    return agencies


def load_agencies(path: Path | None = None) -> None:
    """Read agencies.yaml and populate the registry. Idempotent."""
    config_path = path or repo_root() / "agencies.yaml"
    if not config_path.exists():
        raise AgencyConfigError(f"no agency registry found at {config_path}")
    AGENCIES.clear()
    for agency in parse_agencies(yaml.safe_load(config_path.read_text())):
        register(agency)
