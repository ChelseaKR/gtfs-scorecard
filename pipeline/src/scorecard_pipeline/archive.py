"""Content-addressed raw GTFS zip archive: makes any published grade reproducible.

FIX-02 (docs/ideation/02-large-scale-fixes.md). Raw snapshots (data/raw/) are
gitignored and die with the CI runner; only the feed's sha256 survives in the
published artifact (publish.py: ``artifact["feed"]["sha256"]``). This module
keeps the actual bytes, deduplicated by that same hash, so a disputed grade, a
validator-upgrade study (FIX-06), a backfill (EXP-03), or
``scorecard reproduce <agency> <date>`` (reproduce.py) can pull the exact zip
that was scored, at any later date.

Storage is content-addressed and gated the same way vcache.py gates the
validator-result cache: a local dedup directory
(``data/raw-archive/<hash prefix>/<sha256>.zip``) is always written and always
tried first; an S3 tier (``RAW_ARCHIVE_BUCKET``, falling back to
``ARTIFACTS_BUCKET`` so one variable turns every S3 tier on together) is used
when configured, keeping the archive durable once CI runners stop carrying
data/raw between runs. Because feeds change at most weekly for most agencies,
the S3 tier only uploads a hash it does not already hold (a HEAD check before
every PUT), so growth is incremental — most days write nothing — rather than
one zip per agency per run.

Unlike vcache, which is a pure performance optimization and swallows every S3
error, this archive is the reproducibility record itself: writes stay
best-effort (a storage hiccup must never fail a score), but a ``fetch`` miss
is reported to the caller as ``ArchiveMiss``, not swallowed, since
``scorecard reproduce`` needs to say "the bytes for this hash are not
archived" rather than silently return nothing.

Private by default: this module never makes the bucket contents public. Serving
archived bytes back to the pipeline (or to an operator running
``scorecard reproduce``) is safe regardless of a feed's license; public
redistribution of a re-served copy needs the license question answered first
(flagged as a legal gate in docs/ideation/04-impact-and-sequencing.md) — this
module does not implement or expose that path.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .config import repo_root

log = logging.getLogger(__name__)


class ArchiveMiss(RuntimeError):
    """The requested hash is not archived: neither the local dedup directory
    nor, if configured, the S3 tier holds it."""


def _local_dir() -> Path:
    return repo_root() / "data" / "raw-archive"


def local_path(sha256: str) -> Path:
    """The local dedup path for a feed hash.

    Sharded by the hash's first two hex characters so the directory never
    holds more than ~1/256th of the archive in one listing (the same reasoning
    as a git object store's fanout)."""
    return _local_dir() / sha256[:2] / f"{sha256}.zip"


def _write_local(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".zip.part")
    tmp.write_bytes(data)
    tmp.replace(dest)


# --- Optional S3 tier -------------------------------------------------------


def _archive_bucket() -> str | None:
    """Bucket for the durable archive tier, or None to stay local-only.

    ``RAW_ARCHIVE_BUCKET`` lets the raw archive live in a different bucket than
    the public artifacts; absent that, it reuses ``ARTIFACTS_BUCKET`` under a
    private prefix (mirrors vcache._cache_bucket)."""
    return os.environ.get("RAW_ARCHIVE_BUCKET") or os.environ.get("ARTIFACTS_BUCKET") or None


def _s3_key(sha256: str) -> str:
    # The artifacts distribution enforces a viewer-request allowlist and an
    # origin policy that both exclude this prefix. Keeping the raw archive out
    # of data/artifacts/ makes that private boundary fail closed.
    return f"feeds/{sha256}.zip"


def _s3_client() -> Any:  # pragma: no cover - thin boto3 wrapper, faked in tests
    # Lazy: boto3 is an optional dependency, present only when archiving to S3.
    import boto3  # type: ignore[import-not-found]

    return boto3.client("s3", region_name=os.environ.get("AWS_REGION") or "us-west-2")


def _s3_has(bucket: str, sha256: str) -> bool:
    try:
        _s3_client().head_object(Bucket=bucket, Key=_s3_key(sha256))
        return True
    except Exception as exc:
        log.debug("raw archive S3 head check failed for %s: %s", sha256, exc)
        return False


def _s3_store(bucket: str, sha256: str, data: bytes) -> None:
    try:
        _s3_client().put_object(
            Bucket=bucket, Key=_s3_key(sha256), Body=data, ContentType="application/zip"
        )
    except Exception as exc:
        log.warning("raw archive S3 write failed for %s: %s", sha256, exc)


def _s3_load(bucket: str, sha256: str) -> bytes | None:
    try:
        obj = _s3_client().get_object(Bucket=bucket, Key=_s3_key(sha256))
        return obj["Body"].read()  # type: ignore[no-any-return]
    except Exception as exc:
        log.debug("raw archive S3 read miss for %s: %s", sha256, exc)
        return None


# --- Public API -------------------------------------------------------------


def store(sha256: str, path: Path) -> Path:
    """Archive one feed's bytes, deduplicated by content hash; return the
    local dedup path.

    Writes the local copy only when this hash is not already on disk (most
    calls are a no-op past the first agency/day that produced these exact
    bytes). If a durable bucket is configured, uploads only when that hash is
    not already stored there, so a feed that scores identically day after day
    costs one upload total, not one per run."""
    dest = local_path(sha256)
    if not dest.exists():
        _write_local(dest, path.read_bytes())

    bucket = _archive_bucket()
    if bucket and not _s3_has(bucket, sha256):
        _s3_store(bucket, sha256, dest.read_bytes())
    return dest


def fetch(sha256: str) -> bytes:
    """The archived bytes for a feed hash: local dedup copy first, then the S3
    tier if configured, writing an S3 hit through to the local copy so a
    second reproduce run against the same checkout costs no network call.

    Raises ``ArchiveMiss`` when neither tier has the hash."""
    dest = local_path(sha256)
    if dest.exists():
        return dest.read_bytes()

    bucket = _archive_bucket()
    if bucket:
        body = _s3_load(bucket, sha256)
        if body is not None:
            _write_local(dest, body)
            return body

    where = (
        f"checked local and s3://{bucket}"
        if bucket
        else "checked local only; no archive bucket configured"
    )
    raise ArchiveMiss(f"feed {sha256} is not in the raw archive ({where})")
