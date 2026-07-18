"""Load the agency registry from one legacy file or an explicit shard manifest.

Phase 4: any agency can be added with a YAML block and no code change
(docs/add-your-agency.md). The loader validates entries up front so a typo
in a community PR fails with a sentence, not a stack trace mid-pipeline.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import NoReturn

import yaml

from .config import AGENCIES, Agency, ReuseEvidence, repo_root
from .location import SUPPORTED_COUNTRY_CODES, normalize_location

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
NTD_ID_PATTERN = re.compile(r"^\d{4,5}$")
RT_KINDS = ("trip_updates", "vehicle_positions", "service_alerts")

FEED_STATUSES = {"active", "deprecated", "inactive", "development"}
REUSE_EVIDENCE_KEYS = {
    "decision",
    "source_kind",
    "provider_source_url",
    "terms_url",
    "scope",
    "attribution",
    "reviewed_by",
    "reviewed_on",
    "identity_reviewed",
}
REUSE_SOURCE_KINDS = {"official_portal", "provider"}
REUSE_SCOPES = {"gtfs_schedule"}
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AgencyConfigError(ValueError):
    """The agency registry is malformed; the message says exactly where."""


def _today() -> dt.date:
    """Current local date, split out so date-bound validation is deterministic in tests."""
    return dt.date.today()


def _fail(entry_label: str, message: str, source: str = "agencies.yaml") -> NoReturn:
    raise AgencyConfigError(f"{source}, {entry_label}: {message}")


def _require_url(entry_label: str, field: str, value: object, source: str) -> str:
    if not isinstance(value, str) or not value.startswith(("https://", "http://")):
        _fail(entry_label, f"{field} must be an http(s) URL, got {value!r}", source)
    return str(value)


def _require_nonempty_text(entry_label: str, field: str, value: object, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(entry_label, f"{field} must be a non-empty string", source)
    return value.strip()


def _parse_reuse_scope(
    raw: object, *, entry_label: str, field: str, source: str
) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        _fail(entry_label, f"{field} must be a non-empty list", source)
    if not all(isinstance(item, str) for item in raw):
        _fail(entry_label, f"{field} entries must be strings", source)
    scope = tuple(raw)
    if len(scope) != len(set(scope)):
        _fail(entry_label, f"{field} entries must be unique", source)
    unknown_scopes = set(scope) - REUSE_SCOPES
    if unknown_scopes:
        _fail(
            entry_label,
            f"{field} contains unknown value(s): {', '.join(sorted(unknown_scopes))}",
            source,
        )
    return scope


def _require_iso_date(entry_label: str, field: str, value: object, source: str) -> str:
    if not isinstance(value, str) or not ISO_DATE_PATTERN.fullmatch(value):
        _fail(entry_label, f"{field} must be an ISO date (YYYY-MM-DD)", source)
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        _fail(entry_label, f"{field} must be a valid ISO date", source)
    return value


def _parse_reuse_evidence(raw: object, *, entry_label: str, source: str) -> ReuseEvidence:
    field = "reuse_evidence"
    if not isinstance(raw, dict):
        _fail(entry_label, f"{field} must be a mapping of reviewed evidence", source)

    unknown = set(raw) - REUSE_EVIDENCE_KEYS
    if unknown:
        _fail(
            entry_label,
            f"unknown {field} field(s): {', '.join(sorted(unknown))}",
            source,
        )
    missing = REUSE_EVIDENCE_KEYS - set(raw)
    if missing:
        _fail(
            entry_label,
            f"{field} missing required field(s): {', '.join(sorted(missing))}",
            source,
        )

    decision = raw["decision"]
    if decision != "approved":
        _fail(entry_label, f"{field}.decision must be exactly 'approved'", source)

    source_kind = raw["source_kind"]
    if not isinstance(source_kind, str) or source_kind not in REUSE_SOURCE_KINDS:
        _fail(
            entry_label,
            f"{field}.source_kind must be one of {sorted(REUSE_SOURCE_KINDS)}",
            source,
        )

    provider_source_url = _require_url(
        entry_label,
        f"{field}.provider_source_url",
        raw["provider_source_url"],
        source,
    )
    terms_url = _require_url(entry_label, f"{field}.terms_url", raw["terms_url"], source)

    scope = _parse_reuse_scope(
        raw["scope"], entry_label=entry_label, field=f"{field}.scope", source=source
    )
    attribution = _require_nonempty_text(
        entry_label, f"{field}.attribution", raw["attribution"], source
    )
    reviewed_by = _require_nonempty_text(
        entry_label, f"{field}.reviewed_by", raw["reviewed_by"], source
    )
    reviewed_on = _require_iso_date(entry_label, f"{field}.reviewed_on", raw["reviewed_on"], source)
    if dt.date.fromisoformat(reviewed_on) > _today():
        _fail(entry_label, f"{field}.reviewed_on must not be in the future", source)

    identity_reviewed = raw["identity_reviewed"]
    if not isinstance(identity_reviewed, bool):
        _fail(entry_label, f"{field}.identity_reviewed must be true or false", source)

    return ReuseEvidence(
        decision=decision,
        source_kind=source_kind,
        provider_source_url=provider_source_url,
        terms_url=terms_url,
        scope=scope,
        attribution=attribution,
        reviewed_by=reviewed_by,
        reviewed_on=reviewed_on,
        identity_reviewed=identity_reviewed,
    )


def parse_agencies(  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    raw: object,
    *,
    source: str = "agencies.yaml",
    entry_sources: list[str] | None = None,
) -> list[Agency]:
    """Validate parsed YAML into Agency records."""
    if not isinstance(raw, dict) or not isinstance(raw.get("agencies"), list):
        raise AgencyConfigError(f"{source} must contain a top-level 'agencies:' list")

    entries = raw["agencies"]
    if entry_sources is not None and len(entry_sources) != len(entries):
        raise ValueError("entry_sources must match the number of agency entries")

    agencies: list[Agency] = []
    seen: set[str] = set()
    agency_sources: dict[str, str] = {}
    for i, entry in enumerate(entries):
        entry_source = entry_sources[i] if entry_sources is not None else source
        label = f"entry {i + 1}"
        if not isinstance(entry, dict):
            _fail(label, "each agency must be a mapping of fields", entry_source)
        agency_id = entry.get("id")
        if not isinstance(agency_id, str) or not ID_PATTERN.match(agency_id):
            _fail(
                label,
                f"id must be a lowercase slug (letters/digits/-/_), got {agency_id!r}",
                entry_source,
            )
        label = f"agency '{agency_id}'"
        if agency_id in seen:
            _fail(label, "duplicate id", entry_source)
        seen.add(str(agency_id))
        agency_sources[str(agency_id)] = entry_source

        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            _fail(label, "name is required", entry_source)

        static_url = _require_url(
            label, "static_gtfs_url", entry.get("static_gtfs_url"), entry_source
        )

        rt_urls_raw = entry.get("rt_urls") or {}
        if not isinstance(rt_urls_raw, dict):
            _fail(label, "rt_urls must be a mapping of feed kind to URL", entry_source)
        rt_urls: dict[str, str] = {}
        for kind, url in rt_urls_raw.items():
            if kind not in RT_KINDS:
                _fail(
                    label,
                    f"unknown rt_urls kind {kind!r}; expected one of {RT_KINDS}",
                    entry_source,
                )
            rt_urls[str(kind)] = _require_url(label, f"rt_urls.{kind}", url, entry_source)

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
            "large_feed",
            "reuse_evidence",
        }
        if unknown:
            _fail(label, f"unknown field(s): {', '.join(sorted(unknown))}", entry_source)

        # NTD IDs are FTA-assigned digit strings (five digits today, four on
        # older records). Validate the shape when set so a typo is caught before
        # it shows on a real agency's page; empty is fine and means "unknown".
        ntd_id = str(entry.get("ntd_id") or "").strip()
        if ntd_id and not NTD_ID_PATTERN.match(ntd_id):
            _fail(
                label,
                f"ntd_id must be a 4- or 5-digit NTD number, got {ntd_id!r}",
                entry_source,
            )

        service_type = str(entry.get("service_type") or "fixed").strip()
        if service_type not in ("fixed", "seasonal", "demand_response"):
            _fail(
                label,
                f"service_type must be fixed, seasonal, or demand_response, got {service_type!r}",
                entry_source,
            )

        fare_free = entry.get("fare_free", False)
        if not isinstance(fare_free, bool):
            _fail(label, f"fare_free must be true or false, got {fare_free!r}", entry_source)

        large_feed = entry.get("large_feed", False)
        if not isinstance(large_feed, bool):
            _fail(label, f"large_feed must be true or false, got {large_feed!r}", entry_source)

        organization_id = str(entry.get("organization_id") or "").strip()
        if organization_id and not ID_PATTERN.match(organization_id):
            _fail(
                label,
                f"organization_id must be a lowercase slug, got {organization_id!r}",
                entry_source,
            )
        alias_of = str(entry.get("alias_of") or "").strip()
        if alias_of and not ID_PATTERN.match(alias_of):
            _fail(
                label,
                f"alias_of must be a lowercase agency id, got {alias_of!r}",
                entry_source,
            )
        if alias_of == agency_id:
            _fail(label, "alias_of cannot point to the same entry", entry_source)
        feed_status = str(entry.get("feed_status") or "active").strip().lower()
        if feed_status not in FEED_STATUSES:
            _fail(
                label,
                f"feed_status must be one of {sorted(FEED_STATUSES)}, got {feed_status!r}",
                entry_source,
            )
        official_raw = entry.get("is_official")
        if official_raw is not None and not isinstance(official_raw, bool):
            _fail(label, f"is_official must be true or false, got {official_raw!r}", entry_source)

        reuse_evidence = None
        if "reuse_evidence" in entry:
            reuse_evidence = _parse_reuse_evidence(
                entry["reuse_evidence"], entry_label=label, source=entry_source
            )

        country = str(entry.get("country") or "US").strip().upper()
        subdivision_code = str(entry.get("subdivision_code") or "").strip().upper()
        subdivision_name = str(entry.get("subdivision_name") or "").strip()
        state = str(entry.get("state") or "").strip()
        if country != "US" and state:
            _fail(
                label,
                "state is a deprecated US-only field; use subdivision_code/name",
                entry_source,
            )
        if country not in SUPPORTED_COUNTRY_CODES:
            _fail(
                label,
                f"country must be an assigned ISO 3166-1 alpha-2 code, got {country!r}",
                entry_source,
            )
        location = normalize_location(country, subdivision_code, subdivision_name)
        issue_messages = {
            "malformed_subdivision_code": (
                "subdivision_code must be an ISO 3166-2 code such as US-CA or CA-ON"
            ),
            "subdivision_country_mismatch": "subdivision_code country prefix must match country",
            "unknown_subdivision_code": "subdivision_code is not recognized for this country",
            "subdivision_name_mismatch": "subdivision_code and subdivision_name disagree",
            "ambiguous_subdivision_name": (
                "subdivision_name matches more than one ISO subdivision; provide subdivision_code"
            ),
        }
        blocking_issues = [issue for issue in location.issues if issue in issue_messages]
        if blocking_issues:
            _fail(label, issue_messages[blocking_issues[0]], entry_source)
        if state:
            legacy_location = normalize_location(country, "", state)
            if legacy_location.issues:
                _fail(label, "state must be a recognized US state or territory name", entry_source)
            if location.subdivision_name and (
                location.subdivision_code != legacy_location.subdivision_code
                or location.subdivision_name != legacy_location.subdivision_name
            ):
                _fail(label, "state conflicts with subdivision_code/name", entry_source)
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
                large_feed=large_feed,
                reuse_evidence=reuse_evidence,
            )
        )
    if not agencies:
        raise AgencyConfigError(f"{source} lists no agencies")
    by_id = {agency.id: agency for agency in agencies}
    for agency in agencies:
        if agency.alias_of and agency.alias_of not in by_id:
            _fail(
                f"agency '{agency.id}'",
                f"alias_of references unknown id {agency.alias_of!r}",
                agency_sources[agency.id],
            )
    # Resolve chains only after every direct target is known to exist. This
    # keeps A -> B -> missing a configuration error attributed to B instead of
    # leaking a KeyError while walking A's chain.
    for agency in agencies:
        seen_aliases = {agency.id}
        target = agency.alias_of
        while target:
            if target in seen_aliases:
                _fail(
                    f"agency '{agency.id}'",
                    "alias_of contains a cycle",
                    agency_sources[agency.id],
                )
            seen_aliases.add(target)
            target = by_id[target].alias_of
    return agencies


def _read_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text())
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise AgencyConfigError(f"could not read agency registry {path}: {exc}") from exc


def _unlisted_registry_shards(manifest_path: Path, listed: set[Path]) -> list[Path]:
    discovered = {
        candidate.resolve()
        for pattern in ("*.yaml", "*.yml")
        for candidate in manifest_path.parent.rglob(pattern)
        if candidate.resolve() != manifest_path.resolve()
    }
    return sorted(discovered - listed)


def _resolve_manifest_shard(
    root: Path,
    registry_root: Path,
    manifest_path: Path,
    index: int,
    value: object,
    seen: set[Path],
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise AgencyConfigError(f"{manifest_path}, shard {index}: path must be a non-empty string")
    relative = Path(value)
    if relative.is_absolute():
        raise AgencyConfigError(f"{manifest_path}, shard {index}: path must be relative")
    shard_path = (root / relative).resolve()
    if not shard_path.is_relative_to(root.resolve()):
        raise AgencyConfigError(
            f"{manifest_path}, shard {index}: path must stay within the repository"
        )
    if not shard_path.is_relative_to(registry_root) or shard_path == manifest_path.resolve():
        raise AgencyConfigError(
            f"{manifest_path}, shard {index}: path must stay within the registry directory"
        )
    if shard_path in seen:
        raise AgencyConfigError(f"{manifest_path}, shard {index}: duplicate path {value!r}")
    if not shard_path.is_file():
        raise AgencyConfigError(f"{manifest_path}, shard {index}: shard not found at {shard_path}")
    return shard_path


def _manifest_shards(root: Path, manifest_path: Path) -> list[Path]:
    raw = _read_yaml(manifest_path)
    if not isinstance(raw, dict) or set(raw) != {"shards"} or not isinstance(raw["shards"], list):
        raise AgencyConfigError(f"{manifest_path} must contain only a top-level 'shards:' list")
    if not raw["shards"]:
        raise AgencyConfigError(f"{manifest_path} lists no registry shards")

    paths: list[Path] = []
    seen: set[Path] = set()
    resolved_registry = manifest_path.parent.resolve()
    for index, value in enumerate(raw["shards"], start=1):
        shard_path = _resolve_manifest_shard(
            root, resolved_registry, manifest_path, index, value, seen
        )
        seen.add(shard_path)
        paths.append(shard_path)
    unlisted = _unlisted_registry_shards(manifest_path, seen)
    if unlisted:
        rendered = ", ".join(str(path.relative_to(root.resolve())) for path in unlisted)
        raise AgencyConfigError(f"{manifest_path}: unlisted registry shard(s): {rendered}")
    return paths


def _load_manifest(root: Path, manifest_path: Path) -> list[Agency]:
    entries: list[object] = []
    sources: list[str] = []
    for shard_path in _manifest_shards(root, manifest_path):
        raw = _read_yaml(shard_path)
        if not isinstance(raw, dict) or not isinstance(raw.get("agencies"), list):
            raise AgencyConfigError(f"{shard_path} must contain a top-level 'agencies:' list")
        shard_entries = raw["agencies"]
        if not shard_entries:
            raise AgencyConfigError(f"{shard_path} lists no agencies")
        entries.extend(shard_entries)
        sources.extend([str(shard_path)] * len(shard_entries))
    return parse_agencies({"agencies": entries}, source=str(manifest_path), entry_sources=sources)


def registry_paths(root: Path | None = None) -> list[Path]:
    """Return every writable registry data file in manifest order.

    This is the writer-side companion to :func:`read_agencies`: textual editors
    must update the selected legacy file or each explicit shard, never discover
    arbitrary YAML files on their own and drift from the validated manifest.
    """
    selected_root = (root or repo_root()).resolve()
    legacy_path = selected_root / "agencies.yaml"
    registry_dir = selected_root / "registry"
    manifest_path = registry_dir / "index.yaml"
    if manifest_path.exists() and legacy_path.exists():
        raise AgencyConfigError(
            f"ambiguous agency registry: both {legacy_path} and {manifest_path} exist"
        )
    if registry_dir.exists() and not manifest_path.is_file():
        raise AgencyConfigError(
            f"partial agency registry migration: {registry_dir} exists without index.yaml"
        )
    if manifest_path.is_file():
        return _manifest_shards(selected_root, manifest_path)
    if legacy_path.is_file():
        return [legacy_path]
    raise AgencyConfigError(f"no agency registry found at {legacy_path} or {manifest_path}")


def read_agencies(path: Path | None = None) -> list[Agency]:
    """Read a legacy registry or shard manifest without changing global state.

    Passing a file preserves the original explicit-file API. The default mode
    selects exactly one repository layout: ``agencies.yaml``, or
    ``registry/index.yaml`` plus every shard it lists. A present ``registry``
    directory without its index is rejected as a partial migration.
    """
    if path is not None:
        if not path.is_file():
            raise AgencyConfigError(f"no agency registry found at {path}")
        agencies = parse_agencies(_read_yaml(path), source=str(path))
    else:
        root = repo_root().resolve()
        legacy_path = root / "agencies.yaml"
        selected_paths = registry_paths(root)
        if selected_paths == [legacy_path]:
            agencies = parse_agencies(_read_yaml(legacy_path), source=str(legacy_path))
        else:
            agencies = _load_manifest(root, root / "registry" / "index.yaml")

    return agencies


def load_agencies(path: Path | None = None) -> None:
    """Populate the global registry atomically from the selected layout."""
    agencies = read_agencies(path)

    replacement = {agency.id: agency for agency in agencies}
    AGENCIES.clear()
    AGENCIES.update(replacement)
