"""Download and archive static GTFS feeds.

One dated snapshot per agency per day, kept under data/raw/. Fetching is
idempotent: if today's snapshot already exists it is reused unless forced.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Agency, raw_dir
from .net import FetchTrace, UnsafeURLError, safe_get

log = logging.getLogger(__name__)

# Many agencies serve their public GTFS from behind a WAF or CDN that rejects
# non-browser User-Agents with a 403 (the same way it would a scraper), which
# blocked legitimate fetches of feeds the agency publishes for exactly this kind
# of consumption. Present as a current browser, the way Google's and Apple's
# transit fetchers and ordinary trip planners do, with the Accept headers a
# browser sends. We still fetch once a day and honour polling etiquette.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
FEED_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/zip,application/octet-stream,application/x-zip-compressed,*/*",
}
# (connect, read) timeouts. A reachable server completes the TCP handshake in
# well under a second; a host firewalling our IP range never answers, so a short
# connect timeout fails it fast instead of blocking the whole shard for minutes.
CONNECT_TIMEOUT = 12
READ_TIMEOUT = 120
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
# A flaky WAF often serves the next request; a few backed-off retries clear most
# transient 403/429/5xx. Connection timeouts are not retried (see net.py).
FETCH_RETRIES = 3

# Versioned contract for the archive view consumed by Scorecard-owned readers.
# The canonical validator always receives raw producer bytes regardless.
RAW_READER_ARCHIVE_PROFILE = "raw-v1"
FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE = "flat-single-root-v1"

# Archive-level limits are intentionally tighter than net.safe_get's generic
# download ceiling. GTFS feeds are text-heavy and normally compress well, so a
# huge entry, extreme ratio, or multi-gigabyte expanded archive is more likely
# to be a zip bomb than a legitimate schedule. These checks run before the Java
# validator opens untrusted bytes (the mitigation documented in vex.json).
MAX_GTFS_DOWNLOAD_BYTES = 256 * 1024 * 1024
MAX_GTFS_ENTRIES = 200_000
MAX_GTFS_ENTRY_BYTES = 512 * 1024 * 1024
MAX_GTFS_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_GTFS_COMPRESSION_RATIO = 1_000
COMPRESSION_RATIO_MIN_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class FetchProvenance:
    """How a feed's bytes were actually obtained.

    ``source`` is "origin" (the agency's configured URL) or "mirror" (the
    Mobility Database hosted copy). ``final_url`` is the URL that served the
    bytes. ``max_attempts`` is the configured attempt ceiling for that fetch
    (retries + 1), not an observed count — safe_get does not report how many
    attempts it used. ``origin_error`` names the exception class that pushed
    the fetch to the mirror; None on an origin fetch.
    """

    source: str
    final_url: str
    max_attempts: int
    origin_error: str | None = None


@dataclass(frozen=True)
class FetchResult:
    """A downloaded (or reused) static GTFS snapshot.

    The provenance fields (source, final_url, user_agent, max_attempts,
    origin_error) record how the bytes were obtained so the published artifact
    can state it (docs/ideation FIX-01). A fresh download writes them to a
    provenance.json sidecar next to gtfs.zip; a reused snapshot reads that
    sidecar back. Snapshots that predate the sidecar carry source="unknown"
    with final_url falling back to the configured feed URL, because how those
    bytes were fetched was never recorded on disk.
    """

    agency_id: str
    path: Path
    url: str
    fetched_date: dt.date
    sha256: str
    size_bytes: int
    reused: bool
    source: str = "unknown"
    final_url: str = ""
    user_agent: str = USER_AGENT
    max_attempts: int | None = None
    origin_error: str | None = None
    # The canonical validator always receives ``path``. Scorecard's table
    # readers receive this deterministic view when a producer wrapped every
    # file in one directory or added surrounding filename whitespace.
    reader_path: Path | None = None
    reader_archive_normalized: bool = False

    @property
    def reader_view_path(self) -> Path:
        """Archive path for Scorecard-owned table readers, never validation."""
        return self.reader_path or self.path

    @property
    def reader_archive_profile(self) -> str:
        """Versioned reader-view contract carried into comparison evidence."""
        return (
            FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE
            if self.reader_archive_normalized
            else RAW_READER_ARCHIVE_PROFILE
        )


@dataclass(frozen=True)
class ReaderArchive:
    """A safe archive view for Scorecard's own GTFS table readers."""

    path: Path
    normalized: bool


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_gtfs_archive(path: Path) -> None:
    """Reject archive shapes that can exhaust the validator worker.

    Reading the central directory does not extract member contents. The limits
    therefore stop oversized or implausibly compressed entries before the
    embedded gtfs-validator and Apache Commons Compress parse attacker-controlled
    data.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("response is not a readable zip archive") from exc

    if len(entries) > MAX_GTFS_ENTRIES:
        raise ValueError(
            f"GTFS archive has {len(entries):,} entries; limit is {MAX_GTFS_ENTRIES:,}"
        )

    expanded = 0
    for entry in entries:
        if entry.is_dir():
            continue
        if entry.file_size > MAX_GTFS_ENTRY_BYTES:
            raise ValueError(
                f"GTFS archive entry {entry.filename!r} expands to {entry.file_size:,} bytes; "
                f"limit is {MAX_GTFS_ENTRY_BYTES:,}"
            )
        expanded += entry.file_size
        if expanded > MAX_GTFS_UNCOMPRESSED_BYTES:
            raise ValueError(
                f"GTFS archive expands beyond the {MAX_GTFS_UNCOMPRESSED_BYTES:,}-byte limit"
            )
        ratio = entry.file_size / max(entry.compress_size, 1)
        if entry.file_size >= COMPRESSION_RATIO_MIN_BYTES and ratio > MAX_GTFS_COMPRESSION_RATIO:
            raise ValueError(
                f"GTFS archive entry {entry.filename!r} has an unsafe compression ratio"
            )


ReaderMember = tuple[zipfile.ZipInfo, tuple[str, ...]]
ReaderMapping = list[tuple[zipfile.ZipInfo, str]]


def _reader_members(archive: zipfile.ZipFile) -> list[ReaderMember]:
    """Non-directory members with safe, unambiguous path components."""
    parsed: list[ReaderMember] = []
    for entry in archive.infolist():
        if entry.is_dir():
            continue
        name = entry.filename
        if not name or "\x00" in name or "\\" in name or name.startswith("/"):
            raise ValueError(f"GTFS archive has an unsafe member path: {name!r}")
        parts = tuple(name.split("/"))
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"GTFS archive has an unsafe member path: {name!r}")
        parsed.append((entry, parts))
    return parsed


def _reader_mapping(parsed: list[ReaderMember]) -> ReaderMapping | None:
    """The one allowed filename mapping, or None when no view is needed."""
    root_files = [item for item in parsed if len(item[1]) == 1]
    nested_files = [item for item in parsed if len(item[1]) > 1]
    if root_files:
        if not any(parts[0].strip() != parts[0] for _, parts in root_files):
            return None
        if nested_files:
            raise ValueError(
                "GTFS archive mixes root and nested files; filename normalization "
                "would be ambiguous"
            )
        return [(entry, parts[0].strip()) for entry, parts in root_files]
    if not nested_files:
        return None
    if len({parts[0] for _, parts in nested_files}) != 1:
        raise ValueError("GTFS archive has multiple possible root folders")
    if any(len(parts) != 2 for _, parts in nested_files):
        raise ValueError("GTFS archive is nested deeper than one common root folder")
    return [(entry, parts[1].strip()) for entry, parts in nested_files]


def _validate_reader_targets(mapping: ReaderMapping) -> None:
    targets: set[str] = set()
    for _entry, target in mapping:
        if not target or target in {".", ".."}:
            raise ValueError("GTFS archive has an empty filename after normalization")
        if target in targets:
            raise ValueError(f"GTFS archive member paths collide after normalization: {target!r}")
        targets.add(target)


def _write_reader_archive(archive: zipfile.ZipFile, mapping: ReaderMapping, output: Path) -> None:
    tmp = output.with_suffix(f"{output.suffix}.part")
    tmp.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(tmp, "w", allowZip64=True) as normalized:
            for source, target in sorted(mapping, key=lambda item: item[1]):
                info = zipfile.ZipInfo(target, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o600 << 16
                with (
                    archive.open(source) as src,
                    normalized.open(info, "w", force_zip64=True) as dst,
                ):
                    shutil.copyfileobj(src, dst, length=1 << 20)
        tmp.replace(output)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def prepare_reader_archive(path: Path) -> ReaderArchive:
    """Return a deterministic flat view for Scorecard-owned table readers.

    GTFS requires its text files at the archive root, but a small class of
    producer exports wraps every file in one directory or adds surrounding
    whitespace to filenames. The canonical validator must still see those raw
    packaging errors. Our readers use a separate view so freshness,
    completeness, and descriptive features do not all become falsely empty.

    Only two unambiguous transforms are allowed: strip one common root folder,
    and trim surrounding whitespace from a root filename. Mixed roots, deeper
    trees, unsafe components, and names that collide after trimming are rejected
    instead of guessing. A canonical root feed with harmless nested extras needs
    no transform and conservatively stays on ``raw-v1``; a transformable wrapped
    root mixed with another root is rejected. ``path`` itself is never modified.
    """
    # Reproduce and any future direct caller get the same zip-bomb boundary as
    # fetch_static before we stream a single member into the reader view.
    _validate_gtfs_archive(path)
    output = path.with_name(f"{path.stem}.reader{path.suffix or '.zip'}")
    try:
        with zipfile.ZipFile(path) as archive:
            mapping = _reader_mapping(_reader_members(archive))
            if mapping is None:
                output.unlink(missing_ok=True)
                return ReaderArchive(path=path, normalized=False)
            _validate_reader_targets(mapping)
            _write_reader_archive(archive, mapping, output)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("response is not a readable zip archive") from exc
    return ReaderArchive(path=output, normalized=True)


def _download_with_mirror_fallback(agency: Agency) -> tuple[bytes, FetchProvenance]:
    """Fetch the agency's feed, falling back to the Mobility Database's hosted
    mirror when the origin is unreachable.

    Some agencies firewall datacenter IP ranges (the feed times out from CI) or
    sit behind a bot filter (a 403). MobilityData keeps a hosted copy on Google
    Cloud Storage that is reachable regardless, so when the origin fails we score
    that mirror rather than drop the agency. SSRF rejections are never retried or
    mirrored; they mean the URL itself is unsafe.

    Returns the body plus a FetchProvenance stating which URL actually served it,
    so the published artifact can say "we scored the mirror copy" instead of
    passing a mirror fetch off as an origin fetch.
    """
    import requests

    try:
        trace = FetchTrace()
        body = safe_get(
            agency.static_gtfs_url,
            headers=FEED_HEADERS,
            timeout=TIMEOUT,
            max_bytes=MAX_GTFS_DOWNLOAD_BYTES,
            retries=FETCH_RETRIES,
            trace=trace,
        )
        return body, FetchProvenance(
            source="origin",
            final_url=trace.final_url or agency.static_gtfs_url,
            max_attempts=FETCH_RETRIES + 1,
        )
    except (requests.exceptions.RequestException, UnsafeURLError) as origin_exc:
        from .mobilitydb import hosted_mirror_url

        mirror = None
        if not isinstance(origin_exc, UnsafeURLError):
            mirror = hosted_mirror_url(
                agency.id, agency.name, agency.static_gtfs_url, agency.mdb_id
            )
        if not mirror:
            raise
        log.warning(
            "%s: origin %s unreachable (%s); falling back to Mobility Database mirror %s",
            agency.id,
            agency.static_gtfs_url,
            type(origin_exc).__name__,
            mirror,
        )
        trace = FetchTrace()
        body = safe_get(
            mirror,
            headers=FEED_HEADERS,
            timeout=TIMEOUT,
            max_bytes=MAX_GTFS_DOWNLOAD_BYTES,
            trace=trace,
        )
        return body, FetchProvenance(
            source="mirror",
            final_url=trace.final_url or mirror,
            max_attempts=1,  # the mirror fetch is a single attempt (no retries)
            origin_error=type(origin_exc).__name__,
        )


# Sidecar written next to gtfs.zip on a fresh download, so a rerun that reuses
# the snapshot can still say how those exact bytes were fetched.
PROVENANCE_FILENAME = "provenance.json"


def _write_provenance_sidecar(dest: Path, prov: FetchProvenance) -> None:
    payload: dict[str, Any] = {
        "source": prov.source,
        "final_url": prov.final_url,
        "user_agent": USER_AGENT,
        "max_attempts": prov.max_attempts,
    }
    if prov.origin_error:
        payload["origin_error"] = prov.origin_error
    sidecar = dest.parent / PROVENANCE_FILENAME
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_provenance_sidecar(dest: Path) -> dict[str, Any]:
    """Read the provenance recorded when the snapshot was downloaded.

    Snapshots that predate provenance recording have no sidecar; return {} so
    the caller falls back to source="unknown" rather than guessing.
    """
    sidecar = dest.parent / PROVENANCE_FILENAME
    try:
        data = json.loads(sidecar.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def fetch_static(agency: Agency, date: dt.date, force: bool = False) -> FetchResult:
    """Download the agency's static GTFS zip for the given snapshot date.

    Returns the existing snapshot when one is already on disk for that date,
    so re-running the pipeline never re-downloads or changes history. A reused
    snapshot's provenance comes from its provenance.json sidecar when present;
    older snapshots without one report source="unknown", since how those bytes
    were fetched is not recorded on disk.
    """
    dest = raw_dir() / agency.id / date.isoformat() / "gtfs.zip"
    if dest.exists() and not force:
        log.info("%s: reusing snapshot %s", agency.id, dest)
        _validate_gtfs_archive(dest)
        reader_archive = prepare_reader_archive(dest)
        recorded = _read_provenance_sidecar(dest)
        max_attempts = recorded.get("max_attempts")
        return FetchResult(
            agency_id=agency.id,
            path=dest,
            url=agency.static_gtfs_url,
            fetched_date=date,
            sha256=_sha256(dest),
            size_bytes=dest.stat().st_size,
            reused=True,
            source=str(recorded.get("source", "unknown")),
            final_url=str(recorded.get("final_url", agency.static_gtfs_url)),
            user_agent=str(recorded.get("user_agent", USER_AGENT)),
            max_attempts=max_attempts if isinstance(max_attempts, int) else None,
            origin_error=str(recorded["origin_error"]) if recorded.get("origin_error") else None,
            reader_path=reader_archive.path,
            reader_archive_normalized=reader_archive.normalized,
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("%s: downloading %s", agency.id, agency.static_gtfs_url)
    body, prov = _download_with_mirror_fallback(agency)

    tmp = dest.with_suffix(".zip.part")
    tmp.write_bytes(body)
    if not zipfile.is_zipfile(tmp):
        tmp.unlink()
        raise ValueError(f"{agency.id}: response from {agency.static_gtfs_url} is not a zip")
    try:
        _validate_gtfs_archive(tmp)
    except ValueError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)
    _write_provenance_sidecar(dest, prov)
    reader_archive = prepare_reader_archive(dest)

    return FetchResult(
        agency_id=agency.id,
        path=dest,
        url=agency.static_gtfs_url,
        fetched_date=date,
        sha256=_sha256(dest),
        size_bytes=dest.stat().st_size,
        reused=False,
        source=prov.source,
        final_url=prov.final_url,
        user_agent=USER_AGENT,
        max_attempts=prov.max_attempts,
        origin_error=prov.origin_error,
        reader_path=reader_archive.path,
        reader_archive_normalized=reader_archive.normalized,
    )
