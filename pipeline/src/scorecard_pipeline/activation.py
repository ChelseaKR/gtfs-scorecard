"""Validate bounded agency selections for manual production activation.

The workflow input is deliberately parsed in Python instead of interpolated
into shell: operator-supplied text is data, every selected id must already be
in the curated registry, and one dispatch can never fan out beyond the
documented safety bound.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from collections.abc import Callable, Collection
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
S3_CONNECT_TIMEOUT_SECONDS = 5
S3_READ_TIMEOUT_SECONDS = 30
S3_OBJECT_READ_ATTEMPTS = 3
S3_OBJECT_RETRY_BASE_SECONDS = 0.25
_STREAM_CHUNK_BYTES = 1024 * 1024
_MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})
_TRANSIENT_CODES = frozenset(
    {
        "408",
        "429",
        "500",
        "502",
        "503",
        "504",
        "InternalError",
        "PriorRequestNotComplete",
        "RequestTimeout",
        "RequestTimeoutException",
        "ServiceUnavailable",
        "SlowDown",
        "Throttling",
        "ThrottlingException",
    }
)
_TRANSIENT_EXCEPTION_NAMES = frozenset(
    {
        "ChecksumError",
        "ConnectionClosedError",
        "ConnectTimeoutError",
        "EndpointConnectionError",
        "HTTPClientError",
        "IncompleteReadError",
        "ProtocolError",
        "ReadTimeoutError",
        "ResponseStreamingError",
        "SSLError",
    }
)


class ActivationTargetError(ValueError):
    """A manual activation selection is unsafe or does not match the registry."""


class ActivationHydrationError(RuntimeError):
    """The authoritative activation corpus could not be hydrated safely."""


class _RetryableObjectRead(RuntimeError):
    """A remote object attempt failed before its full body was consumed."""


class _S3Client(Protocol):
    """The small boto3 S3 surface the hydrator needs (and tests can fake)."""

    def get_object(self, **kwargs: object) -> dict[str, Any]: ...

    def get_paginator(self, operation_name: str) -> Any: ...


class _BinaryWriter(Protocol):
    def write(self, data: bytes) -> int: ...


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
    """Build a pooled S3 client with bounded standard retries and timeouts."""
    import boto3  # type: ignore[import-not-found]
    from botocore.config import Config  # type: ignore[import-not-found]

    return cast(
        _S3Client,
        boto3.client(
            "s3",
            config=Config(
                connect_timeout=S3_CONNECT_TIMEOUT_SECONDS,
                max_pool_connections=workers,
                read_timeout=S3_READ_TIMEOUT_SECONDS,
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


def _http_status(exc: Exception) -> int | None:
    response = getattr(exc, "response", {})
    if not isinstance(response, dict):
        return None
    metadata = response.get("ResponseMetadata", {})
    if not isinstance(metadata, dict):
        return None
    status = metadata.get("HTTPStatusCode")
    return status if isinstance(status, int) else None


def _is_transient_remote_error(exc: Exception) -> bool:
    """Classify only remote GET/read failures that are safe to repeat in full."""
    if _error_code(exc) in _TRANSIENT_CODES:
        return True
    status = _http_status(exc)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    # This classifier is called only around client.get_object and body.read.
    # OSError therefore represents socket/TLS transport failure, never a local
    # destination error (local mkdir/write/replace/utime calls are kept outside
    # the classified blocks below).
    return isinstance(exc, (TimeoutError, ConnectionError, OSError)) or (
        type(exc).__name__ in _TRANSIENT_EXCEPTION_NAMES
    )


def _retry_delay(completed_attempt: int) -> float:
    """Return deterministic exponential backoff after a failed 1-based attempt."""
    return S3_OBJECT_RETRY_BASE_SECONDS * (2.0 ** (completed_attempt - 1))


def _get_object(
    client: _S3Client,
    bucket: str,
    key: str,
    *,
    optional: bool,
) -> dict[str, Any] | None:
    """Issue one GET, distinguishing optional misses, transient, and permanent errors."""
    try:
        return client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if optional and _error_code(exc) in _MISSING_CODES:
            return None
        if _is_transient_remote_error(exc):
            raise _RetryableObjectRead(str(exc)) from exc
        raise ActivationHydrationError(f"could not read s3://{bucket}/{key}: {exc}") from exc


def _stream_body(body: object, output: _BinaryWriter, bucket: str, key: str) -> None:
    """Consume a remote body while keeping local write errors out of retry handling."""
    read = getattr(body, "read", None)
    if not callable(read):
        raise ActivationHydrationError(f"s3://{bucket}/{key} Body is not readable")
    while True:
        try:
            chunk = read(_STREAM_CHUNK_BYTES)
        except Exception as exc:
            if _is_transient_remote_error(exc):
                raise _RetryableObjectRead(str(exc)) from exc
            raise ActivationHydrationError(f"could not stream s3://{bucket}/{key}: {exc}") from exc
        if chunk == b"":
            return
        if not isinstance(chunk, bytes):
            raise ActivationHydrationError(f"s3://{bucket}/{key} Body returned non-byte content")
        # Deliberately outside the remote exception classifier: a filesystem
        # failure must abort, not trigger another S3 attempt.
        output.write(chunk)


def _close_body(body: object | None) -> None:
    if body is None:
        return
    close = getattr(body, "close", None)
    if callable(close):
        close()


def _retry_or_raise(
    exc: _RetryableObjectRead,
    *,
    bucket: str,
    key: str,
    completed_attempt: int,
    sleeper: Callable[[float], None],
) -> None:
    """Sleep before another whole-object attempt, or fail closed at the bound."""
    cause = exc.__cause__ if isinstance(exc.__cause__, Exception) else exc
    if completed_attempt >= S3_OBJECT_READ_ATTEMPTS:
        raise ActivationHydrationError(
            f"could not read s3://{bucket}/{key} after {S3_OBJECT_READ_ATTEMPTS} attempts: {cause}"
        ) from cause
    sleeper(_retry_delay(completed_attempt))


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
    sleeper: Callable[[float], None],
) -> bool:
    """Stream one exact object to an atomic local path; retry remote truncation in full."""
    for completed_attempt in range(1, S3_OBJECT_READ_ATTEMPTS + 1):
        body: object | None = None
        temporary: Path | None = None
        try:
            response = _get_object(client, bucket, key, optional=optional)
            if response is None:
                return False

            body = response.get("Body")
            if body is None:
                raise ActivationHydrationError(f"s3://{bucket}/{key} omitted Body")
            last_modified = response.get("LastModified")
            if not isinstance(last_modified, dt.datetime):
                raise ActivationHydrationError(f"s3://{bucket}/{key} omitted LastModified")

            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary = Path(output.name)
                _stream_body(body, output, bucket, key)

            # Set the source mtime on the unique temporary before its atomic
            # replacement. A local utime failure therefore cannot leave a
            # partially completed destination that looks authoritative.
            timestamp = last_modified.timestamp()
            os.utime(temporary, (timestamp, timestamp))
            temporary.replace(destination)
            temporary = None
            return True
        except _RetryableObjectRead as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
                temporary = None
            _close_body(body)
            body = None
            _retry_or_raise(
                exc,
                bucket=bucket,
                key=key,
                completed_attempt=completed_attempt,
                sleeper=sleeper,
            )
        except ActivationHydrationError:
            raise
        except Exception as exc:
            # Local path/create/write/flush/replace/utime failures never enter
            # the remote classifier and therefore fail closed without retry.
            raise ActivationHydrationError(
                f"could not write {destination} from {key}: {exc}"
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            _close_body(body)
    raise AssertionError("unreachable bounded object read loop")


def _read_index(
    client: _S3Client,
    bucket: str,
    artifacts_root: Path,
    index_before: Path,
    etag_out: Path,
    *,
    sleeper: Callable[[float], None],
) -> dict[str, Any]:
    """Capture the compact index bytes and their ETag from the same GET response."""
    key = f"{_ARTIFACT_PREFIX}index.json"
    response: dict[str, Any] | None = None
    body_bytes: bytes | None = None
    for completed_attempt in range(1, S3_OBJECT_READ_ATTEMPTS + 1):
        body: object | None = None
        try:
            response = _get_object(client, bucket, key, optional=False)
            if response is None:  # pragma: no cover - optional=False contract
                raise AssertionError("required index GET returned an optional miss")
            body = response.get("Body")
            if body is None:
                raise ActivationHydrationError(f"s3://{bucket}/{key} omitted Body")
            output = io.BytesIO()
            _stream_body(body, output, bucket, key)
            body_bytes = output.getvalue()
            break
        except _RetryableObjectRead as exc:
            _close_body(body)
            body = None
            _retry_or_raise(
                exc,
                bucket=bucket,
                key=key,
                completed_attempt=completed_attempt,
                sleeper=sleeper,
            )
        finally:
            _close_body(body)
    if response is None or body_bytes is None:  # pragma: no cover - loop contract
        raise AssertionError("bounded index read exited without a response")

    etag_value = response.get("ETag")
    etag = str(etag_value) if etag_value is not None else ""
    if not etag:
        raise ActivationHydrationError("authoritative index response omitted bytes or ETag")
    try:
        index = json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ActivationHydrationError(
            f"authoritative index.json is not valid JSON: {exc}"
        ) from exc
    if not isinstance(index, dict) or not isinstance(index.get("agencies"), dict):
        raise ActivationHydrationError("authoritative index.json has no agencies object")

    _atomic_write(artifacts_root / "index.json", body_bytes)
    _atomic_write(index_before, body_bytes)
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
    sleeper: Callable[[float], None] = time.sleep,
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
    index = _read_index(
        s3,
        bucket,
        artifacts_root,
        index_before,
        etag_out,
        sleeper=sleeper,
    )
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
                sleeper=sleeper,
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
                sleeper=sleeper,
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
