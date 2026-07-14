"""Download and archive static GTFS feeds.

One dated snapshot per agency per day, kept under data/raw/. Fetching is
idempotent: if today's snapshot already exists it is reused unless forced.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
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
    )
