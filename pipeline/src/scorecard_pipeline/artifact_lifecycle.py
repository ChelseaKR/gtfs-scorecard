"""Lifecycle boundary between historical and current per-agency artifacts.

Dated score snapshots are an append-only evidence record. The other public
files beside them are mutable pointers to a feed's current state. When a
registry record is retired, those pointers must disappear locally and from the
authoritative object store without deleting its dated history.

``reconcile_retired_current_artifacts`` writes a small local control manifest
for the S3 publisher. The manifest contains agency ids rather than arbitrary
keys; the publisher expands only the fixed filename allowlist below. This keeps
retirement cleanup incapable of deleting dated artifacts or other namespaces.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# These are the mutable per-agency names exposed by both the Pages assembly
# allowlist and the CloudFront viewer-request allowlist. Date-shaped JSON is
# deliberately absent: retirement preserves historical evidence.
MUTABLE_PUBLIC_ARTIFACT_NAMES = (
    "latest.json",
    "badge.json",
    "badge.svg",
    "conformance.json",
    "mark.svg",
    "geometry.geojson",
)

RETIREMENT_MANIFEST_NAME = ".retired-current-artifacts.json"
RETIREMENT_MANIFEST_SCHEMA_VERSION = 1
RESERVED_ARTIFACT_DIRS = frozenset({"rollups", "changes", "run"})

# The public artifact path contract is narrower than the registry parser's
# legacy underscore allowance. An id outside this shape is not reachable as an
# agency artifact through the CDN and is never admitted to a deletion plan.
_PUBLIC_AGENCY_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class RetirementManifestError(ValueError):
    """A retirement manifest is malformed or could target an unsafe path."""


class _AgencyRecord(Protocol):
    @property
    def is_canonical_feed(self) -> bool: ...


@dataclass(frozen=True)
class RetirementPlan:
    """The local result of reconciling noncurrent agency directories."""

    agency_ids: tuple[str, ...]
    removed_files: int
    manifest_path: Path


def retirement_manifest_path(artifact_root: Path) -> Path:
    """Return the local control-manifest path for an artifact tree."""
    return artifact_root / RETIREMENT_MANIFEST_NAME


def _retired_agency_ids(
    artifact_root: Path, registry: Mapping[str, _AgencyRecord]
) -> tuple[str, ...]:
    """Return known noncurrent ids, including stale hydrated directories."""
    if not registry:
        # Without a loaded registry there is no authority for declaring an id
        # retired. Library callers keep their historical behavior.
        return ()

    retired = {
        agency_id
        for agency_id, agency in registry.items()
        if not agency.is_canonical_feed and _PUBLIC_AGENCY_ID.fullmatch(agency_id)
    }
    if artifact_root.exists():
        for path in artifact_root.iterdir():
            if not path.is_dir() or path.name in RESERVED_ARTIFACT_DIRS:
                continue
            agency = registry.get(path.name)
            if (agency is None or not agency.is_canonical_feed) and _PUBLIC_AGENCY_ID.fullmatch(
                path.name
            ):
                retired.add(path.name)
    return tuple(sorted(retired))


def _write_manifest(path: Path, agency_ids: tuple[str, ...]) -> None:
    payload = {
        "schema_version": RETIREMENT_MANIFEST_SCHEMA_VERSION,
        "agency_ids": list(agency_ids),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def reconcile_retired_current_artifacts(
    artifact_root: Path, registry: Mapping[str, _AgencyRecord]
) -> RetirementPlan:
    """Remove local current pointers for retired ids and write their S3 plan.

    The fixed filename list is applied whether or not a file currently exists.
    That distinction matters in CI: collect hydrates every ``latest.json`` but
    does not hydrate every badge or geometry object, while all of them may still
    exist in the additive S3 store.
    """
    agency_ids = _retired_agency_ids(artifact_root, registry)
    removed = 0
    for agency_id in agency_ids:
        agency_dir = artifact_root / agency_id
        # Never follow an unexpected directory symlink during local cleanup.
        # The id still remains in the S3 plan, where it expands to plain keys.
        if agency_dir.is_symlink():
            continue
        for name in MUTABLE_PUBLIC_ARTIFACT_NAMES:
            path = agency_dir / name
            if path.is_file() or path.is_symlink():
                path.unlink()
                removed += 1

    manifest = retirement_manifest_path(artifact_root)
    _write_manifest(manifest, agency_ids)
    return RetirementPlan(
        agency_ids=agency_ids,
        removed_files=removed,
        manifest_path=manifest,
    )


def load_retirement_agency_ids(path: Path) -> tuple[str, ...]:
    """Read and strictly validate a retirement control manifest."""
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise RetirementManifestError(f"could not read retirement manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RetirementManifestError("retirement manifest root must be an object")
    if set(payload) != {"schema_version", "agency_ids"}:
        raise RetirementManifestError(
            "retirement manifest must contain only schema_version and agency_ids"
        )
    if payload.get("schema_version") != RETIREMENT_MANIFEST_SCHEMA_VERSION:
        raise RetirementManifestError("unsupported retirement manifest schema_version")
    raw_ids = payload.get("agency_ids")
    if not isinstance(raw_ids, list) or not all(isinstance(item, str) for item in raw_ids):
        raise RetirementManifestError("retirement manifest agency_ids must be a string array")
    agency_ids = tuple(raw_ids)
    if agency_ids != tuple(sorted(set(agency_ids))):
        raise RetirementManifestError("retirement manifest agency_ids must be sorted and unique")
    unsafe = [agency_id for agency_id in agency_ids if not _PUBLIC_AGENCY_ID.fullmatch(agency_id)]
    if unsafe:
        raise RetirementManifestError("retirement manifest contains an unsafe agency id")
    if set(agency_ids) & RESERVED_ARTIFACT_DIRS:
        raise RetirementManifestError("retirement manifest targets a reserved artifact namespace")
    return agency_ids


def retirement_key_suffixes(agency_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Expand ids into exact relative keys from the fixed mutable allowlist."""
    return tuple(
        f"{agency_id}/{name}" for agency_id in agency_ids for name in MUTABLE_PUBLIC_ARTIFACT_NAMES
    )
