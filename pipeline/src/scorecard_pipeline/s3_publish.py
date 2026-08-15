"""Publish the artifact tree to S3 by comparing content, not clocks.

``aws s3 sync`` transfers a file when its size differs from the destination
object *or* when its modification time is newer. CI checks the repository out
fresh on every run, so every local file is always newer than every object and
the daily collect job re-uploads the entire published tree. Measured on the
committed corpus that is about 28,700 objects a day, of which roughly 3,100
actually changed.

The flag that looks like the fix, ``--size-only``, is not safe here. It would
compare byte length alone, so a re-scored artifact that happens to keep the
same length (a grade moving ``B`` to ``C``, a count going ``19`` to ``20``,
a same-width timestamp) would silently stop publishing. Silently publishing
stale scores is the failure this pipeline has already had once; see the shard
staging comment in ``.github/workflows/scorecard.yml``.

This module compares content instead. One paginated ``ListObjectsV2`` over the
destination prefix returns every object's size and ETag. The artifacts bucket
encrypts with SSE-S3 (``AES256``, ``infra/artifacts/main.tf``) and this module
always writes with a single ``PutObject``, so a published object's ETag is the
MD5 of its bytes. A local file is skipped only when its size matches the object
and the object's ETag equals the MD5 of the local bytes.

Everything else uploads:

- no object at that key
- a different size
- an ETag that is not a 32-character hex MD5, which means either a multipart
  ETag left behind by an earlier ``aws s3 sync`` or some future bucket change
  that stops S3 from reporting a content MD5
- an MD5 that does not match

Every uncertain case therefore uploads. The comparison can over-upload; it has
no path that skips a file whose bytes differ from the published object. The
decision is also re-read from S3 on every run, so it never depends on a local
timestamp, a cache restored from elsewhere, or a manifest this code wrote
earlier and might have failed to keep true.

MD5 is used as a change detector against the one value S3 reports for free,
not as a security control. The inputs are the pipeline's own generated
artifacts, so there is no party in a position to craft a colliding pair.

Publication remains additive for dated evidence. The one bounded exception is
a retirement manifest produced from the curated registry: it expands agency
ids into the fixed mutable public filenames and deletes only those exact keys.
Arbitrary keys and date-shaped JSON can never enter that deletion path.
"""

from __future__ import annotations

import fnmatch
import hashlib
import logging
import re
from collections.abc import Collection, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from .artifact_lifecycle import (
    RETIREMENT_MANIFEST_NAME,
    RetirementManifestError,
    load_retirement_agency_ids,
    retirement_key_suffixes,
)

log = logging.getLogger(__name__)

DEFAULT_PUBLISH_WORKERS = 16
MAX_PUBLISH_WORKERS = 32
S3_CONNECT_TIMEOUT_SECONDS = 5
S3_READ_TIMEOUT_SECONDS = 60
_HASH_CHUNK_BYTES = 1024 * 1024
_MAX_DELETE_OBJECTS = 1000

# S3 reports the content MD5 as the ETag only for single-part, SSE-S3 objects.
# Anything else (a multipart ETag such as "abc...-3") fails this and uploads.
_CONTENT_MD5_ETAG = re.compile(r"\A[0-9a-f]{32}\Z")

# Pinned so the published Content-Type never depends on whichever
# /etc/mime.types the runner image happens to ship. These are the extensions
# the artifact tree actually contains.
_CONTENT_TYPES = {
    ".csv": "text/csv",
    ".geojson": "application/geo+json",
    ".json": "application/json",
    ".md": "text/markdown",
    ".svg": "image/svg+xml",
}


class PublishError(RuntimeError):
    """An artifact could not be published, so the run must fail closed."""


class _S3Client(Protocol):
    """The small boto3 S3 surface this module needs (and tests can fake)."""

    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def delete_objects(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_paginator(self, operation_name: str) -> Any: ...


@dataclass(frozen=True)
class RemoteObject:
    """What one ListObjectsV2 entry tells us about a published object."""

    size: int
    etag: str


@dataclass(frozen=True)
class LocalFile:
    """One candidate file, already resolved to the key it would publish to."""

    key: str
    path: Path
    size: int


@dataclass(frozen=True)
class PublishResult:
    """Counts from one publish pass."""

    uploaded: int
    skipped: int
    listed: int
    retired: int

    @property
    def considered(self) -> int:
        return self.uploaded + self.skipped


def s3_client(workers: int) -> _S3Client:  # pragma: no cover - thin boto3 wrapper
    """Build a pooled S3 client with bounded standard retries and timeouts."""
    import boto3  # type: ignore[import-not-found]
    from botocore.config import Config  # type: ignore[import-not-found]

    return cast(
        _S3Client,
        boto3.client(
            "s3",
            config=Config(
                connect_timeout=S3_CONNECT_TIMEOUT_SECONDS,
                max_pool_connections=max(workers, 1),
                read_timeout=S3_READ_TIMEOUT_SECONDS,
                retries={"mode": "standard", "total_max_attempts": 6},
            ),
        ),
    )


def file_md5(path: Path) -> str:
    """Return the hex MD5 of a file, read in bounded chunks."""
    # Change detection against the value S3 already reports as the ETag, not a
    # security control; see the module docstring.
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def normalize_etag(raw: object) -> str:
    """Strip the quoting S3 puts around an ETag and case-fold it."""
    return str(raw or "").strip('"').strip().lower()


def normalize_prefix(prefix: str) -> str:
    """Return the destination prefix as a key prefix ending in one slash."""
    return prefix.strip("/") + "/" if prefix.strip("/") else ""


def is_excluded(key_suffix: str, patterns: Sequence[str]) -> bool:
    """Match a path relative to the publish root against ``--exclude`` globs.

    ``fnmatch`` wildcards cross ``/`` here exactly as they do in the AWS CLI's
    filters, so the patterns already in the workflows keep their meaning.
    """
    return any(fnmatch.fnmatchcase(key_suffix, pattern) for pattern in patterns)


def content_type(path: Path) -> str | None:
    """Return the Content-Type to publish, or None to let S3 default it."""
    return _CONTENT_TYPES.get(path.suffix.lower())


def local_files(root: Path, prefix: str, excludes: Sequence[str]) -> list[LocalFile]:
    """Walk the publish root into the keys it would write, in stable order."""
    key_prefix = normalize_prefix(prefix)
    found: list[LocalFile] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        suffix = path.relative_to(root).as_posix()
        # Local control data is consumed by this publisher and is never itself
        # part of the public artifact namespace.
        if suffix in {RETIREMENT_MANIFEST_NAME, f"{RETIREMENT_MANIFEST_NAME}.tmp"}:
            continue
        if is_excluded(suffix, excludes):
            continue
        found.append(LocalFile(key=key_prefix + suffix, path=path, size=path.stat().st_size))
    return found


def remote_objects(client: _S3Client, bucket: str, prefix: str) -> dict[str, RemoteObject]:
    """List the destination prefix once into {key: size and ETag}."""
    index: dict[str, RemoteObject] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=normalize_prefix(prefix)):
        for entry in page.get("Contents", []) or []:
            key = str(entry.get("Key", ""))
            if not key:
                continue
            index[key] = RemoteObject(
                size=int(entry.get("Size", -1)),
                etag=normalize_etag(entry.get("ETag")),
            )
    return index


def needs_upload(local: LocalFile, remote: RemoteObject | None) -> bool:
    """Decide whether a file must be published, resolving every doubt as yes."""
    if remote is None:
        return True
    if remote.size != local.size:
        return True
    if not _CONTENT_MD5_ETAG.match(remote.etag):
        # A multipart or otherwise non-MD5 ETag cannot prove the bytes match.
        return True
    return remote.etag != file_md5(local.path)


def changed_files(
    files: Sequence[LocalFile],
    remote: dict[str, RemoteObject],
    *,
    workers: int = DEFAULT_PUBLISH_WORKERS,
) -> list[LocalFile]:
    """Return the subset of ``files`` whose published bytes are not current."""
    if not files:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, MAX_PUBLISH_WORKERS))) as pool:
        verdicts = list(pool.map(lambda f: needs_upload(f, remote.get(f.key)), files))
    return [f for f, upload in zip(files, verdicts, strict=True) if upload]


def _put_object(
    client: _S3Client,
    bucket: str,
    local: LocalFile,
    cache_control: str | None,
) -> None:
    """Write one object with a single PutObject, so its ETag stays a content MD5."""
    extra: dict[str, Any] = {}
    if cache_control:
        extra["CacheControl"] = cache_control
    guessed = content_type(local.path)
    if guessed:
        extra["ContentType"] = guessed
    try:
        with local.path.open("rb") as body:
            client.put_object(Bucket=bucket, Key=local.key, Body=body, **extra)
    except Exception as exc:
        raise PublishError(f"could not publish s3://{bucket}/{local.key}: {exc}") from exc


def _upload_all(
    client: _S3Client,
    bucket: str,
    uploads: Sequence[LocalFile],
    cache_control: str | None,
    workers: int,
) -> None:
    """Upload every changed file, failing the whole publish on the first error."""
    if not uploads:
        return
    with ThreadPoolExecutor(max_workers=max(1, min(workers, MAX_PUBLISH_WORKERS))) as pool:
        # list() drains the lazy map so any PublishError surfaces here.
        list(pool.map(lambda f: _put_object(client, bucket, f, cache_control), uploads))


def _retirement_keys(
    manifest: Path | None,
    prefix: str,
    protected_agency_ids: Collection[str],
) -> tuple[str, ...]:
    """Resolve a manifest into exact mutable keys, never arbitrary paths."""
    if manifest is None:
        return ()
    try:
        agency_ids = load_retirement_agency_ids(manifest)
    except RetirementManifestError as exc:
        raise PublishError(str(exc)) from exc
    protected = sorted(set(agency_ids) & set(protected_agency_ids))
    if protected:
        raise PublishError(
            "retirement manifest includes current canonical agency id(s): " + ", ".join(protected)
        )
    key_prefix = normalize_prefix(prefix)
    return tuple(key_prefix + suffix for suffix in retirement_key_suffixes(agency_ids))


def _retire_current_objects(client: _S3Client, bucket: str, keys: Sequence[str]) -> None:
    """Delete exact mutable keys in bounded S3 batches, failing closed."""
    for start in range(0, len(keys), _MAX_DELETE_OBJECTS):
        batch = keys[start : start + _MAX_DELETE_OBJECTS]
        try:
            response = client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
            )
        except Exception as exc:
            raise PublishError(
                f"could not retire current artifacts in s3://{bucket}: {exc}"
            ) from exc
        errors = response.get("Errors", []) or []
        if errors:
            first = errors[0]
            key = str(first.get("Key") or "unknown")
            code = str(first.get("Code") or "unknown")
            raise PublishError(f"could not retire s3://{bucket}/{key}: {code}")


def publish_tree(
    client: _S3Client,
    *,
    root: Path,
    bucket: str,
    prefix: str,
    excludes: Sequence[str] = (),
    cache_control: str | None = None,
    workers: int = DEFAULT_PUBLISH_WORKERS,
    retirement_manifest: Path | None = None,
    protected_agency_ids: Collection[str] = (),
) -> PublishResult:
    """Publish ``root`` under ``prefix``, uploading only objects whose bytes changed.

    Dated history remains additive. The only deletions are exact mutable
    per-agency filenames expanded from a strictly validated retirement
    manifest. This lets a registry retirement revoke current-looking pointers
    without granting the publisher a general tree-sync deletion surface.
    """
    if not root.is_dir():
        raise PublishError(f"publish root does not exist: {root}")
    files = local_files(root, prefix, excludes)
    retirements = _retirement_keys(retirement_manifest, prefix, protected_agency_ids)
    conflicts = sorted({local.key for local in files} & set(retirements))
    if conflicts:
        raise PublishError(
            "local publish tree still contains a current artifact scheduled for retirement: "
            + conflicts[0]
        )
    remote = remote_objects(client, bucket, prefix)
    listed = len(remote)
    existing_retirements = tuple(key for key in retirements if key in remote)
    # Retire before uploading the rebuilt catalog. If a later upload fails, a
    # stale direct pointer stays unavailable instead of being revived outside
    # the catalog. The next serialized workflow run can complete the aggregate
    # update idempotently. Listing first also avoids creating a fresh S3 delete
    # marker on every run for a key whose current version is already deleted.
    _retire_current_objects(client, bucket, existing_retirements)
    for key in existing_retirements:
        remote.pop(key, None)
    uploads = changed_files(files, remote, workers=workers)
    _upload_all(client, bucket, uploads, cache_control, workers)
    return PublishResult(
        uploaded=len(uploads),
        skipped=len(files) - len(uploads),
        listed=listed,
        retired=len(existing_retirements),
    )
