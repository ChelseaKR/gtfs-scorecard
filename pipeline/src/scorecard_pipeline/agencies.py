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


def parse_agencies(  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    raw: object, *, validate_aliases: bool = True, allow_empty: bool = False
) -> list[Agency]:
    """Validate parsed YAML into Agency records.

    ``validate_aliases=False`` defers the alias referential checks to the
    caller: the multi-file loader validates them over the merged registry,
    since an alias may point at an entry in another shard. ``allow_empty``
    lets a single registry file be empty when others supply the entries.
    """
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
        if country not in SUPPORTED_COUNTRIES:
            _fail(
                label,
                f"country must be one of {sorted(SUPPORTED_COUNTRIES)}, got {country!r}. "
                "Supporting a new country is deliberate work (state/province handling, "
                "standards framing; ADR 0026), so extend SUPPORTED_COUNTRIES alongside "
                "that plumbing.",
            )

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
                country=country,
                state=str(entry.get("state") or "").strip(),
                service_type=service_type,
                fare_free=fare_free,
            )
        )
    if not agencies and not allow_empty:
        raise AgencyConfigError("agencies.yaml lists no agencies")
    if validate_aliases:
        _validate_aliases(agencies)
    return agencies


def _validate_aliases(agencies: list[Agency]) -> None:
    """Alias references must resolve and never cycle, across the whole set."""
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


# Curated per-state shards live here (FIX-12): registry/<country>/<state>.yaml.
# agencies.yaml stays the front door for newcomers and the submission flow.
REGISTRY_DIR_NAME = "registry"


def registry_paths(root: Path) -> list[Path]:
    """Every file the registry is loaded from, the intake file first."""
    paths = [root / "agencies.yaml"]
    shard_root = root / REGISTRY_DIR_NAME
    if shard_root.is_dir():
        paths.extend(sorted(p for p in shard_root.rglob("*.yaml") if p.is_file()))
    return [p for p in paths if p.is_file()]


def load_agencies(path: Path | None = None) -> None:
    """Read the registry and populate AGENCIES. Idempotent.

    With an explicit ``path`` (tests, forks pointing at one file) only that
    file is read, exactly as before the FIX-12 split. Without one,
    agencies.yaml and every shard under registry/ are merged: duplicate ids
    are rejected across files with both sources named, and alias references
    are validated over the merged set, since an alias may point into another
    shard.
    """
    if path is not None:
        if not path.exists():
            raise AgencyConfigError(f"no agency registry found at {path}")
        AGENCIES.clear()
        for agency in parse_agencies(yaml.safe_load(path.read_text())):
            register(agency)
        return

    merged = _load_merged_registry(repo_root())
    AGENCIES.clear()
    for agency in merged:
        register(agency)


def _parse_registry_file(file_path: Path, rel: str) -> list[Agency]:
    try:
        return parse_agencies(
            yaml.safe_load(file_path.read_text()),
            validate_aliases=False,
            allow_empty=True,
        )
    except AgencyConfigError as exc:
        # parse_agencies speaks generically of agencies.yaml; name the
        # actual shard so the failing file is one click away in review.
        message = str(exc)
        generic = "agencies.yaml, "
        if rel != "agencies.yaml" and message.startswith(generic):
            raise AgencyConfigError(f"{rel}, {message[len(generic) :]}") from None
        raise


def _load_merged_registry(root: Path) -> list[Agency]:
    paths = registry_paths(root)
    if not paths:
        raise AgencyConfigError(f"no agency registry found at {root / 'agencies.yaml'}")
    merged: list[Agency] = []
    source_of: dict[str, str] = {}
    for file_path in paths:
        rel = file_path.relative_to(root).as_posix()
        parsed = _parse_registry_file(file_path, rel)
        for agency in parsed:
            if agency.id in source_of:
                raise AgencyConfigError(
                    f"duplicate id '{agency.id}': declared in {source_of[agency.id]} "
                    f"and again in {rel}"
                )
            source_of[agency.id] = rel
        merged.extend(parsed)
    if not merged:
        raise AgencyConfigError("the registry lists no agencies")
    _validate_aliases(merged)
    return merged
