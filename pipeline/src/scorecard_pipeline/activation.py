"""Validate bounded agency selections for manual production activation.

The workflow input is deliberately parsed in Python instead of interpolated
into shell: operator-supplied text is data, every selected id must already be
in the curated registry, and one dispatch can never fan out beyond the
documented safety bound.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

from .agencies import ID_PATTERN

MAX_ACTIVATION_TARGETS = 25
_SEPARATOR = re.compile(r"[,\s]+")
_ARTIFACT_PREFIX = "data/artifacts/"
_HYDRATED_NAMESPACES = ("rollups", "changes", "run")
DEFAULT_HYDRATION_WORKERS = 16
MAX_HYDRATION_WORKERS = 32
_MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class ActivationTargetError(ValueError):
    """A manual activation selection is unsafe or does not match the registry."""


class ActivationHydrationError(RuntimeError):
    """The authoritative activation corpus could not be hydrated safely."""


class _S3Client(Protocol):
    """The small boto3 S3 surface the hydrator needs (and tests can fake)."""

    def get_object(self, **kwargs: object) -> dict[str, Any]: ...

    def get_paginator(self, operation_name: str) -> Any: ...


@dataclass(frozen=True)
class HydrationResult:
    """Counts from one bounded authoritative-corpus hydration."""

    agencies: int
    objects: int
    optional_misses: int
    selected_objects: int
    skipped_unregistered: int


def parse_activation_targets(
    raw: str,
    known_ids: Collection[str],
    *,
    limit: int = MAX_ACTIVATION_TARGETS,
) -> list[str]:
    """Return validated registry ids from comma or whitespace separated input.

    Inputs are never silently canonicalized. NFKC/casefold normalization is
    used only to detect visually surprising duplicates such as ``agency`` and
    ``AGENCY``; each accepted token must still be the exact lowercase registry
    id supplied by the operator.
    """
    tokens = [token for token in _SEPARATOR.split(raw.strip()) if token]
    if not tokens:
        raise ActivationTargetError("provide at least one agency id")
    if len(tokens) > limit:
        raise ActivationTargetError(
            f"at most {limit} agency ids may be activated in one run (received {len(tokens)})"
        )

    normalized: dict[str, str] = {}
    for token in tokens:
        key = unicodedata.normalize("NFKC", token).casefold()
        if previous := normalized.get(key):
            raise ActivationTargetError(
                f"duplicate agency id after normalization: {previous!r} and {token!r}"
            )
        normalized[key] = token

    malformed = [token for token in tokens if ID_PATTERN.fullmatch(token) is None]
    if malformed:
        raise ActivationTargetError(
            "malformed agency id(s): "
            + ", ".join(repr(token) for token in malformed)
            + "; use exact lowercase registry slugs"
        )

    unknown = [token for token in tokens if token not in known_ids]
    if unknown:
        raise ActivationTargetError("unknown agency id(s): " + ", ".join(unknown))
    return tokens


def _s3_client(workers: int) -> _S3Client:  # pragma: no cover - thin boto3 wrapper
    """Build a pooled S3 client with bounded standard retries."""
    import boto3  # type: ignore[import-not-found]
    from botocore.config import Config  # type: ignore[import-not-found]

    return cast(
        _S3Client,
        boto3.client(
            "s3",
            config=Config(
                max_pool_connections=workers,
                retries={"mode": "standard", "total_max_attempts": 6},
            ),
        ),
    )


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", {})
    if not isinstance(response, dict):
        return ""
    error = response.get("Error", {})
    return str(error.get("Code", "")) if isinstance(error, dict) else ""


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(data)
        temporary.replace(path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _artifact_destination(root: Path, key: str) -> Path:
    """Map a public artifact key below root without trusting S3 path text."""
    if not key.startswith(_ARTIFACT_PREFIX):
        raise ActivationHydrationError(f"artifact key is outside {_ARTIFACT_PREFIX}: {key!r}")
    raw_parts = key.removeprefix(_ARTIFACT_PREFIX).split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise ActivationHydrationError(f"unsafe artifact key: {key!r}")
    relative = PurePosixPath(*raw_parts)
    if relative.is_absolute():
        raise ActivationHydrationError(f"unsafe artifact key: {key!r}")
    return root.joinpath(*relative.parts)


def _destination_map(root: Path, keys: Collection[str]) -> dict[str, Path]:
    """Map distinct S3 keys to distinct local paths across common filesystems."""
    destinations: dict[str, Path] = {}
    identities: dict[tuple[str, ...], str] = {}
    for key in sorted(keys):
        destination = _artifact_destination(root, key)
        identity = tuple(
            unicodedata.normalize("NFC", part).casefold()
            for part in destination.relative_to(root).parts
        )
        if previous := identities.get(identity):
            raise ActivationHydrationError(
                f"artifact keys map to the same local path: {previous!r} and {key!r}"
            )
        identities[identity] = key
        destinations[key] = destination
    return destinations


def _list_prefix(client: _S3Client, bucket: str, prefix: str) -> set[str]:
    """List one deliberately bounded selected or aggregate prefix."""
    keys: set[str] = set()
    try:
        pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        for page in pages:
            for item in page.get("Contents", []):
                key = str(item.get("Key", ""))
                if key and not key.endswith("/"):
                    keys.add(key)
    except Exception as exc:
        raise ActivationHydrationError(f"could not list s3://{bucket}/{prefix}: {exc}") from exc
    return keys


def _download_one(
    client: _S3Client,
    bucket: str,
    key: str,
    destination: Path,
    *,
    optional: bool,
) -> bool:
    """Stream one exact object to an atomic local path; return false on an optional miss."""
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if optional and _error_code(exc) in _MISSING_CODES:
            return False
        raise ActivationHydrationError(f"could not read s3://{bucket}/{key}: {exc}") from exc

    last_modified = response.get("LastModified")
    if not isinstance(last_modified, dt.datetime):
        raise ActivationHydrationError(f"s3://{bucket}/{key} omitted LastModified")
    body = response.get("Body")
    if body is None:
        raise ActivationHydrationError(f"s3://{bucket}/{key} omitted Body")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            shutil.copyfileobj(body, output, length=1024 * 1024)
        temporary.replace(destination)
        timestamp = last_modified.timestamp()
        os.utime(destination, (timestamp, timestamp))
    except Exception as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ActivationHydrationError(f"could not write {destination} from {key}: {exc}") from exc
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()
    return True


def _read_index(
    client: _S3Client,
    bucket: str,
    artifacts_root: Path,
    index_before: Path,
    etag_out: Path,
) -> dict[str, Any]:
    """Capture the compact index bytes and their ETag from the same GET response."""
    key = f"{_ARTIFACT_PREFIX}index.json"
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        etag = str(response["ETag"])
    except Exception as exc:
        raise ActivationHydrationError(f"could not capture s3://{bucket}/{key}: {exc}") from exc
    if not isinstance(body, bytes) or not etag:
        raise ActivationHydrationError("authoritative index response omitted bytes or ETag")
    try:
        index = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ActivationHydrationError(
            f"authoritative index.json is not valid JSON: {exc}"
        ) from exc
    if not isinstance(index, dict) or not isinstance(index.get("agencies"), dict):
        raise ActivationHydrationError("authoritative index.json has no agencies object")

    _atomic_write(artifacts_root / "index.json", body)
    _atomic_write(index_before, body)
    _atomic_write(etag_out, f"{etag}\n".encode())
    return index


def _registered_index_ids(index: dict[str, Any], known_ids: Collection[str]) -> list[str]:
    """Apply the same registry-bounded listing policy as reindex."""
    registered: list[str] = []
    skipped: list[str] = []
    for raw_id in index["agencies"]:
        agency_id = str(raw_id)
        if ID_PATTERN.fullmatch(agency_id) is None or agency_id not in known_ids:
            skipped.append(agency_id)
        else:
            registered.append(agency_id)
    if skipped:
        print(
            f"::warning title=unregistered index entries::skipping {len(skipped)} "
            "index entries that are not in agencies.yaml",
            file=sys.stderr,
        )
    return sorted(registered)


def _canonical_snapshot_date(value: object, agency_id: str, source: str) -> str:
    """Return a strict YYYY-MM-DD date safe to use as one path segment."""
    raw = str(value)
    try:
        parsed = dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise ActivationHydrationError(
            f"authoritative {source} snapshot date is invalid for {agency_id}: {raw!r}"
        ) from exc
    if parsed.isoformat() != raw:
        raise ActivationHydrationError(
            f"authoritative {source} snapshot date is not canonical for {agency_id}: {raw!r}"
        )
    return raw


def _indexed_current_dates(index: dict[str, Any], agency_ids: Collection[str]) -> dict[str, str]:
    """Return each registered index entry's validated current snapshot date."""
    dates: dict[str, str] = {}
    for agency_id in agency_ids:
        try:
            indexed_current = index["agencies"][agency_id]["history"][-1]
            value = indexed_current["date"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ActivationHydrationError(
                f"authoritative index history is malformed for {agency_id}: {exc}"
            ) from exc
        dates[agency_id] = _canonical_snapshot_date(value, agency_id, "index")
    return dates


def _validate_and_materialize_current(
    artifacts_root: Path,
    index: dict[str, Any],
    agency_ids: Collection[str],
    targets: Collection[str],
    current_dates: dict[str, str],
) -> None:
    """Verify latest against the captured index and supply reindex's local dated input."""
    from .publish import _history_entry

    target_set = set(targets)
    for agency_id in agency_ids:
        latest_path = artifacts_root / agency_id / "latest.json"
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            artifact_id = str(latest["agency"]["id"])
            snapshot_date = _canonical_snapshot_date(latest["snapshot_date"], agency_id, "latest")
            history = index["agencies"][agency_id]["history"]
            indexed_current = history[-1]
            indexed_date = current_dates[agency_id]
            latest_current = _history_entry(latest)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, OSError) as exc:
            raise ActivationHydrationError(
                f"authoritative current artifact is malformed for {agency_id}: {exc}"
            ) from exc
        if artifact_id != agency_id:
            raise ActivationHydrationError(
                f"authoritative latest identity mismatch for {agency_id}: {artifact_id!r}"
            )
        if snapshot_date != indexed_date:
            raise ActivationHydrationError(
                f"authoritative latest/index date mismatch for {agency_id}: "
                f"{snapshot_date!r} != {indexed_date!r}"
            )
        if any(latest_current.get(field) != value for field, value in indexed_current.items()):
            raise ActivationHydrationError(
                f"authoritative latest/index summary mismatch for {agency_id}"
            )
        if agency_id in target_set:
            # The selected directory is fully hydrated and the scorer must
            # produce its new dated snapshot. Do not recreate an expired object.
            continue
        dated_path = artifacts_root / agency_id / f"{snapshot_date}.json"
        latest_bytes = latest_path.read_bytes()
        if dated_path.exists():
            if dated_path.read_bytes() != latest_bytes:
                raise ActivationHydrationError(
                    f"authoritative latest/dated payload mismatch for {agency_id}"
                )
        else:
            # Lifecycle retention may remove the immutable dated object while
            # latest.json remains current. Reconstruct only the local reindex
            # input; publication never uploads non-selected agency paths.
            _atomic_write(dated_path, latest_bytes)


def hydrate_activation_corpus(
    *,
    bucket: str,
    targets: Collection[str],
    known_ids: Collection[str],
    artifacts_root: Path,
    index_before: Path,
    etag_out: Path,
    liveness_out: Path,
    workers: int = DEFAULT_HYDRATION_WORKERS,
    client: _S3Client | None = None,
) -> HydrationResult:
    """Hydrate the complete committed current corpus plus bounded mutable state.

    ``index.json`` is the commit manifest. Its registered agency ids drive exact
    ``latest.json``, indexed-current dated, and optional ``fixlog.json`` GETs, so
    retained dated history is never recursively listed. A missing current dated
    object falls back locally to byte-identical latest; a retained one must match.
    Exact downloads keep their S3 modification time so later bounded syncs skip
    unchanged files. Only selected agency directories and the three small
    stateful namespaces are listed in full.
    """
    if not bucket.strip():
        raise ActivationHydrationError("artifact bucket is required")
    if not 1 <= workers <= MAX_HYDRATION_WORKERS:
        raise ActivationHydrationError(
            f"hydration workers must be between 1 and {MAX_HYDRATION_WORKERS}"
        )
    try:
        validated_targets = parse_activation_targets(" ".join(targets), known_ids)
    except ActivationTargetError as exc:
        raise ActivationHydrationError(str(exc)) from exc

    s3 = client or _s3_client(workers)
    index = _read_index(s3, bucket, artifacts_root, index_before, etag_out)
    agency_ids = _registered_index_ids(index, known_ids)
    current_dates = _indexed_current_dates(index, agency_ids)

    listed: set[str] = set()
    selected_keys: set[str] = set()
    for namespace in _HYDRATED_NAMESPACES:
        listed.update(_list_prefix(s3, bucket, f"{_ARTIFACT_PREFIX}{namespace}/"))
    for agency_id in validated_targets:
        keys = _list_prefix(s3, bucket, f"{_ARTIFACT_PREFIX}{agency_id}/")
        selected_keys.update(keys)
        listed.update(keys)

    required = {f"{_ARTIFACT_PREFIX}{agency_id}/latest.json" for agency_id in agency_ids}
    required.update(listed)
    optional = {f"{_ARTIFACT_PREFIX}{agency_id}/fixlog.json" for agency_id in agency_ids} - required
    target_set = set(validated_targets)
    optional.update(
        f"{_ARTIFACT_PREFIX}{agency_id}/{current_dates[agency_id]}.json"
        for agency_id in agency_ids
        if agency_id not in target_set
    )
    optional.difference_update(required)

    destinations = _destination_map(artifacts_root, required | optional)
    # Liveness is outside the artifacts prefix and is optional until the first
    # intraday refresh has published it.
    liveness_key = "data/liveness.json"

    downloaded = 0
    optional_misses = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="activation-s3") as executor:
        futures = {
            executor.submit(
                _download_one,
                s3,
                bucket,
                key,
                destination,
                optional=key in optional,
            ): key
            for key, destination in destinations.items()
        }
        futures[
            executor.submit(
                _download_one,
                s3,
                bucket,
                liveness_key,
                liveness_out,
                optional=True,
            )
        ] = liveness_key
        try:
            for future in as_completed(futures):
                if future.result():
                    downloaded += 1
                else:
                    optional_misses += 1
        except Exception:
            for future in futures:
                future.cancel()
            raise

    _validate_and_materialize_current(
        artifacts_root,
        index,
        agency_ids,
        validated_targets,
        current_dates,
    )
    return HydrationResult(
        agencies=len(agency_ids),
        objects=downloaded,
        optional_misses=optional_misses,
        selected_objects=len(selected_keys),
        skipped_unregistered=len(index["agencies"]) - len(agency_ids),
    )
